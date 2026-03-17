from __future__ import annotations

import argparse
import asyncio
import math
from typing import Any

from src.core.settings import get_settings
from src.services.pacifica_auth_service import PacificaAuthService
from src.services.pacifica_client import PacificaClientError
from src.services.trading_service import TradingService


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


async def _pick_market(service: TradingService, symbol: str | None) -> dict[str, Any]:
    markets = await service.pacifica.get_markets()
    if symbol:
        normalized_symbol = _normalize_symbol(symbol)
        for market in markets:
            market_symbol = _normalize_symbol(str(market.get("symbol") or market.get("display_symbol") or ""))
            if market_symbol == normalized_symbol:
                return market
        raise ValueError(f"Market {normalized_symbol} was not found on Pacifica testnet.")

    eligible: list[tuple[float, dict[str, Any]]] = []
    for market in markets:
        mark_price = float(market.get("mark_price") or 0)
        min_order_size = float(market.get("min_order_size") or 0)
        if mark_price <= 0 or min_order_size <= 0:
            continue
        eligible.append((mark_price * min_order_size, market))
    if not eligible:
        raise ValueError("No eligible Pacifica markets with price and min order size were returned.")
    eligible.sort(key=lambda item: item[0])
    return eligible[0][1]


def _build_entry_quantity(market: dict[str, Any], leverage: int, quantity_override: float | None) -> float:
    if quantity_override is not None:
        return quantity_override

    min_order_size = float(market.get("min_order_size") or 0)
    lot_size = float(market.get("lot_size") or 0)
    if min_order_size <= 0:
        raise ValueError("Selected market did not return a valid min_order_size.")

    base_quantity = max(min_order_size * 1.1, min_order_size + (lot_size or 0))
    quantity = _round_up_to_step(base_quantity, lot_size or min_order_size)
    notional = quantity * float(market.get("mark_price") or 0)
    margin_estimate = notional / max(leverage, 1)
    print(
        f"Selected quantity {quantity:g} on {_normalize_symbol(str(market.get('symbol') or ''))} "
        f"(estimated notional ${notional:,.2f}, estimated margin ${margin_estimate:,.2f})."
    )
    return quantity


async def _poll_position(
    service: TradingService,
    wallet_address: str,
    symbol: str,
    *,
    expect_open: bool,
    timeout_seconds: float,
    interval_seconds: float,
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
            raise TimeoutError(f"Timed out waiting for {normalized_symbol} position to become {state}.")
        await asyncio.sleep(interval_seconds)


async def main() -> None:
    parser = argparse.ArgumentParser(description="Place and close a real Pacifica testnet trade using delegated agent auth.")
    parser.add_argument("--wallet", dest="wallet_address", default=None, help="Pacifica account address. Defaults to PACIFICA_ACCOUNT_ADDRESS.")
    parser.add_argument("--symbol", default=None, help="Market symbol like BTC or ETH. Defaults to the cheapest eligible market.")
    parser.add_argument("--side", default="long", choices=["long", "short"], help="Entry side.")
    parser.add_argument("--leverage", type=int, default=1, help="Entry leverage.")
    parser.add_argument("--quantity", type=float, default=None, help="Exact base quantity to trade. If omitted, a minimal valid quantity is chosen.")
    parser.add_argument("--timeout", type=float, default=20.0, help="Seconds to wait for open and close confirmation.")
    parser.add_argument("--poll-interval", type=float, default=1.0, help="Polling interval in seconds.")
    args = parser.parse_args()

    settings = get_settings()
    wallet_address = (args.wallet_address or settings.pacifica_account_address).strip()
    if not wallet_address:
        raise ValueError("Set PACIFICA_ACCOUNT_ADDRESS or pass --wallet.")
    if not settings.pacifica_network.lower().startswith("test"):
        raise ValueError(f"Refusing to run outside testnet. Current network: {settings.pacifica_network}")

    auth_service = PacificaAuthService()
    authorization = auth_service.get_authorization_by_wallet(None, wallet_address)
    if authorization is None or authorization.get("status") != "active":
        raise ValueError(
            "Delegated Pacifica authorization is not active for this wallet. Complete /api/pacifica/authorize/start and activate first."
        )

    service = TradingService()
    market = await _pick_market(service, args.symbol)
    symbol = _normalize_symbol(str(market.get("symbol") or market.get("display_symbol") or ""))

    existing_positions = await service.pacifica.get_positions(wallet_address)
    if any(_normalize_symbol(str(item.get("symbol") or "")) == symbol for item in existing_positions):
        raise ValueError(f"Refusing to run because wallet {wallet_address} already has an open {symbol} position.")

    quantity = _build_entry_quantity(market, args.leverage, args.quantity)

    print(f"Wallet: {wallet_address}")
    print(f"Network: {settings.pacifica_network}")
    print(f"Market: {symbol}")
    print(f"Entry side: {args.side}")
    print("Submitting entry order...")

    try:
        open_result = await service.place_order(
            None,
            wallet_address=wallet_address,
            symbol=symbol,
            side=args.side,
            order_type="market",
            leverage=max(1, args.leverage),
            quantity=quantity,
        )
        print(f"Entry submitted: request_id={open_result['request_id']} status={open_result['status']}")

        opened_position = await _poll_position(
            service,
            wallet_address,
            symbol,
            expect_open=True,
            timeout_seconds=args.timeout,
            interval_seconds=args.poll_interval,
        )
        assert opened_position is not None
        opened_side = "long" if str(opened_position.get("side") or "").lower() in {"bid", "long"} else "short"
        opened_quantity = abs(float(opened_position.get("amount") or 0))
        print(
            f"Position opened: side={opened_side} quantity={opened_quantity:g} "
            f"entry_price={float(opened_position.get('entry_price') or 0):,.4f}"
        )

        print("Submitting reduce-only close order...")
        close_result = await service.place_order(
            None,
            wallet_address=wallet_address,
            symbol=symbol,
            side=_opposite_side(opened_side),
            order_type="market",
            leverage=max(1, args.leverage),
            quantity=opened_quantity,
            reduce_only=True,
        )
        print(f"Close submitted: request_id={close_result['request_id']} status={close_result['status']}")

        await _poll_position(
            service,
            wallet_address,
            symbol,
            expect_open=False,
            timeout_seconds=args.timeout,
            interval_seconds=args.poll_interval,
        )
        print("Position closed successfully.")
    except PacificaClientError as exc:
        raise SystemExit(f"Pacifica request failed: {exc}") from exc


if __name__ == "__main__":
    asyncio.run(main())
