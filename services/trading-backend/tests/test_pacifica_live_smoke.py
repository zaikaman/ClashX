from __future__ import annotations

import asyncio
import math
from typing import Any

import pytest

from src.core.settings import get_settings
from src.services.pacifica_auth_service import PacificaAuthService
from src.services.pacifica_market_data_service import PacificaMarketDataService
from src.services.trading_snapshot_cache_service import TradingSnapshotCacheService
from src.services.trading_service import TradingService


pytestmark = [pytest.mark.live, pytest.mark.smoke]


def _normalize_symbol(value: str) -> str:
    return value.upper().removesuffix("-PERP").strip()


def _opposite_side(side: str) -> str:
    return "short" if side == "long" else "long"


def _round_up_to_step(value: float, step: float) -> float:
    if step <= 0:
        return value
    units = math.ceil(value / step)
    precision = max(0, len(str(step).split(".")[1]) if "." in str(step) else 0)
    return round(units * step, precision)


async def _pick_market(service: TradingService) -> dict[str, Any]:
    markets = await service.pacifica.get_markets()
    eligible: list[tuple[float, dict[str, Any]]] = []
    for market in markets:
        mark_price = float(market.get("mark_price") or 0)
        min_order_size = float(market.get("min_order_size") or 0)
        if mark_price <= 0 or min_order_size <= 0:
            continue
        eligible.append((mark_price * min_order_size, market))
    if not eligible:
        raise AssertionError("Pacifica returned no eligible testnet markets")
    eligible.sort(key=lambda item: item[0])
    return eligible[0][1]


def _build_quantity(market: dict[str, Any], leverage: int = 1) -> float:
    min_order_size = float(market.get("min_order_size") or 0)
    mark_price = float(market.get("mark_price") or 0)
    lot_size = float(market.get("lot_size") or 0)
    if min_order_size <= 0 or mark_price <= 0:
        raise AssertionError("Selected market did not expose usable order sizing metadata")
    minimum_notional_usd = max(min_order_size, 10.0)
    base_quantity = max((minimum_notional_usd * 1.1) / mark_price, lot_size or 0)
    quantity = _round_up_to_step(base_quantity, lot_size or min_order_size)
    notional = quantity * mark_price
    margin_estimate = notional / max(leverage, 1)
    if margin_estimate <= 0:
        raise AssertionError("Unable to derive a positive live smoke quantity")
    return quantity


async def _wait_for_position(
    service: TradingService,
    wallet_address: str,
    symbol: str,
    *,
    expect_open: bool,
    timeout_seconds: float = 30.0,
    interval_seconds: float = 1.0,
) -> dict[str, Any] | None:
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    normalized_symbol = _normalize_symbol(symbol)
    while True:
        positions = await service.pacifica.get_positions(wallet_address)
        matching = next(
            (item for item in positions if _normalize_symbol(str(item.get("symbol") or "")) == normalized_symbol),
            None,
        )
        if expect_open and matching is not None and abs(float(matching.get("amount") or 0)) > 0:
            return matching
        if not expect_open and matching is None:
            return None
        if asyncio.get_running_loop().time() >= deadline:
            state = "open" if expect_open else "closed"
            raise AssertionError(f"Timed out waiting for {normalized_symbol} position to become {state}")
        await asyncio.sleep(interval_seconds)


async def _wait_for_open_order(
    service: TradingService,
    wallet_address: str,
    symbol: str,
    *,
    order_id: int,
    expect_present: bool,
    timeout_seconds: float = 30.0,
    interval_seconds: float = 1.0,
) -> dict[str, Any] | None:
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    normalized_symbol = _normalize_symbol(symbol)
    while True:
        orders = await service.pacifica.get_open_orders(wallet_address)
        matching = next(
            (
                item
                for item in orders
                if _normalize_symbol(str(item.get("symbol") or "")) == normalized_symbol
                and int(item.get("order_id") or 0) == order_id
            ),
            None,
        )
        if expect_present and matching is not None:
            return matching
        if not expect_present and matching is None:
            return None
        if asyncio.get_running_loop().time() >= deadline:
            state = "present" if expect_present else "removed"
            raise AssertionError(f"Timed out waiting for {normalized_symbol} open order {order_id} to be {state}")
        await asyncio.sleep(interval_seconds)


async def _wait_for_new_open_order(
    service: TradingService,
    wallet_address: str,
    symbol: str,
    *,
    existing_order_ids: set[int],
    timeout_seconds: float = 30.0,
    interval_seconds: float = 1.0,
) -> dict[str, Any]:
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    normalized_symbol = _normalize_symbol(symbol)
    while True:
        orders = await service.pacifica.get_open_orders(wallet_address)
        for item in orders:
            if _normalize_symbol(str(item.get("symbol") or "")) != normalized_symbol:
                continue
            order_id = int(item.get("order_id") or 0)
            if order_id <= 0 or order_id in existing_order_ids:
                continue
            return item
        if asyncio.get_running_loop().time() >= deadline:
            raise AssertionError(f"Timed out waiting for a new open order on {normalized_symbol}")
        await asyncio.sleep(interval_seconds)


async def _close_existing_position_if_any(service: TradingService, wallet_address: str, symbol: str) -> None:
    positions = await service.pacifica.get_positions(wallet_address)
    position = next(
        (item for item in positions if _normalize_symbol(str(item.get("symbol") or "")) == _normalize_symbol(symbol)),
        None,
    )
    if position is None:
        return
    opened_side = "long" if str(position.get("side") or "").lower() in {"bid", "long"} else "short"
    quantity = abs(float(position.get("amount") or 0))
    await service.place_order(
        None,
        wallet_address=wallet_address,
        symbol=symbol,
        side=_opposite_side(opened_side),
        order_type="market",
        leverage=1,
        quantity=quantity,
        reduce_only=True,
    )
    await _wait_for_position(service, wallet_address, symbol, expect_open=False)


async def _live_market_roundtrip() -> None:
    settings = get_settings()
    service = TradingService()
    service.market_data = PacificaMarketDataService(service.pacifica)
    service.snapshot_cache = TradingSnapshotCacheService()
    wallet_address = settings.pacifica_account_address
    market = await _pick_market(service)
    symbol = _normalize_symbol(str(market.get("symbol") or market.get("display_symbol") or ""))
    quantity = _build_quantity(market)

    await _close_existing_position_if_any(service, wallet_address, symbol)

    open_result = await service.place_order(
        None,
        wallet_address=wallet_address,
        symbol=symbol,
        side="long",
        order_type="market",
        leverage=1,
        quantity=quantity,
    )
    assert open_result["status"] == "submitted"

    position = await _wait_for_position(service, wallet_address, symbol, expect_open=True)
    assert position is not None
    close_quantity = abs(float(position.get("amount") or 0))

    close_result = await service.place_order(
        None,
        wallet_address=wallet_address,
        symbol=symbol,
        side="short",
        order_type="market",
        leverage=1,
        quantity=close_quantity,
        reduce_only=True,
    )
    assert close_result["status"] == "submitted"
    await _wait_for_position(service, wallet_address, symbol, expect_open=False)


async def _live_limit_ioc_submission() -> None:
    settings = get_settings()
    service = TradingService()
    service.market_data = PacificaMarketDataService(service.pacifica)
    service.snapshot_cache = TradingSnapshotCacheService()
    wallet_address = settings.pacifica_account_address
    market = await _pick_market(service)
    symbol = _normalize_symbol(str(market.get("symbol") or market.get("display_symbol") or ""))
    mark_price = float(market.get("mark_price") or 0)
    tick_size = float(market.get("tick_size") or 0)
    quantity = _build_quantity(market)
    limit_price = max(tick_size or 0.5, mark_price * 0.8)
    if tick_size > 0:
        limit_price = math.floor(limit_price / tick_size) * tick_size

    minimum_notional_usd = max(float(market.get("min_order_size") or 0), 10.0)
    quantity = _round_up_to_step(
        max(quantity, (minimum_notional_usd * 1.1) / max(limit_price, tick_size or 0.000001)),
        float(market.get("lot_size") or 0) or 1.0,
    )

    result = await service.place_order(
        None,
        wallet_address=wallet_address,
        symbol=symbol,
        side="long",
        order_type="limit",
        leverage=1,
        quantity=quantity,
        limit_price=limit_price,
        tif="IOC",
    )
    assert result["status"] == "submitted"
    await asyncio.sleep(2)
    positions = await service.pacifica.get_positions(wallet_address)
    matching_positions = [
        item for item in positions if _normalize_symbol(str(item.get("symbol") or "")) == symbol
    ]
    assert matching_positions == []


async def _live_limit_submit_and_cancel() -> None:
    settings = get_settings()
    service = TradingService()
    service.market_data = PacificaMarketDataService(service.pacifica)
    service.snapshot_cache = TradingSnapshotCacheService()
    wallet_address = settings.pacifica_account_address
    market = await _pick_market(service)
    symbol = _normalize_symbol(str(market.get("symbol") or market.get("display_symbol") or ""))
    mark_price = float(market.get("mark_price") or 0)
    tick_size = float(market.get("tick_size") or 0)
    lot_size = float(market.get("lot_size") or 0) or 1.0

    existing_orders = await service.pacifica.get_open_orders(wallet_address)
    existing_order_ids = {
        int(item.get("order_id") or 0)
        for item in existing_orders
        if _normalize_symbol(str(item.get("symbol") or "")) == symbol
    }

    limit_price = max(tick_size or 0.5, mark_price * 0.5)
    if tick_size > 0:
        limit_price = math.floor(limit_price / tick_size) * tick_size

    minimum_notional_usd = max(float(market.get("min_order_size") or 0), 10.0)
    quantity = _round_up_to_step((minimum_notional_usd * 1.2) / max(limit_price, tick_size or 0.000001), lot_size)

    submit_result = await service.place_order(
        None,
        wallet_address=wallet_address,
        symbol=symbol,
        side="long",
        order_type="limit",
        leverage=1,
        quantity=quantity,
        limit_price=limit_price,
        tif="GTC",
    )
    assert submit_result["status"] == "submitted"

    new_order = await _wait_for_new_open_order(
        service,
        wallet_address,
        symbol,
        existing_order_ids=existing_order_ids,
    )
    order_id = int(new_order.get("order_id") or 0)
    assert order_id > 0
    cancelled = False
    try:
        cancel_result = await service.cancel_order(
            None,
            wallet_address=wallet_address,
            symbol=symbol,
            order_id=str(order_id),
        )
        assert cancel_result["status"] == "submitted"
        cancelled = True

        await _wait_for_open_order(
            service,
            wallet_address,
            symbol,
            order_id=order_id,
            expect_present=False,
        )
    finally:
        if cancelled:
            return
        try:
            await service.cancel_order(
                None,
                wallet_address=wallet_address,
                symbol=symbol,
                order_id=str(order_id),
            )
        except Exception:
            pass


def _assert_live_env_ready() -> None:
    settings = get_settings()
    if not settings.pacifica_network.lower().startswith("test"):
        raise AssertionError(f"Live smoke is restricted to testnet, current network is {settings.pacifica_network}")
    if not settings.pacifica_account_address:
        raise AssertionError("PACIFICA_ACCOUNT_ADDRESS is required")
    auth = PacificaAuthService().get_authorization_by_wallet(None, settings.pacifica_account_address)
    if auth is None or auth.get("status") != "active":
        raise AssertionError("Delegated Pacifica authorization must be active before live smoke can run")


def test_live_market_open_close_roundtrip() -> None:
    _assert_live_env_ready()
    asyncio.run(_live_market_roundtrip())


def test_live_limit_ioc_submission() -> None:
    _assert_live_env_ready()
    asyncio.run(_live_limit_ioc_submission())


def test_live_limit_submit_and_cancel() -> None:
    _assert_live_env_ready()
    asyncio.run(_live_limit_submit_and_cancel())
