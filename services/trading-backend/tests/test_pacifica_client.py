from __future__ import annotations

import asyncio
import uuid
from types import SimpleNamespace
from typing import Any

import httpx

from src.services.pacifica_client import PacificaClient
from src.services.pacifica_market_data_service import PacificaMarketDataService
from src.workers.bot_runtime_worker import BotRuntimeWorker


def test_normalize_payload_canonicalizes_custom_client_order_ids() -> None:
    client = object.__new__(PacificaClient)
    client.settings = SimpleNamespace(pacifica_builder_code="")

    normalized = client._normalize_payload(
        "set_position_tpsl",
        {
            "account": "wallet-1",
            "symbol": "BTC",
            "side": "ask",
            "take_profit": {
                "stop_price": 120_000,
                "amount": 0.1,
                "client_order_id": "maker-entry-001",
            },
            "stop_loss": {
                "stop_price": 99_800,
                "amount": 0.1,
                "client_order_id": "maker-entry-001",
            },
        },
        account="wallet-1",
    )

    take_profit_id = normalized["take_profit"]["client_order_id"]
    stop_loss_id = normalized["stop_loss"]["client_order_id"]

    assert take_profit_id == PacificaClient.canonicalize_client_order_id(
        "maker-entry-001",
        account="wallet-1",
        symbol="BTC",
        scope="take_profit.client_order_id",
    )
    assert stop_loss_id == PacificaClient.canonicalize_client_order_id(
        "maker-entry-001",
        account="wallet-1",
        symbol="BTC",
        scope="stop_loss.client_order_id",
    )
    assert take_profit_id != stop_loss_id
    assert str(uuid.UUID(take_profit_id)) == take_profit_id
    assert str(uuid.UUID(stop_loss_id)) == stop_loss_id


def test_normalize_payload_preserves_existing_uuid_client_order_id() -> None:
    client = object.__new__(PacificaClient)
    client.settings = SimpleNamespace(pacifica_builder_code="")
    existing = str(uuid.uuid4())

    normalized = client._normalize_payload(
        "create_order",
        {
            "account": "wallet-1",
            "symbol": "BTC",
            "side": "bid",
            "price": 100_000,
            "amount": 0.1,
            "tif": "GTC",
            "reduce_only": False,
            "client_order_id": existing,
        },
        account="wallet-1",
    )

    assert normalized["client_order_id"] == existing


class _FakePacificaClient:
    def __init__(self, response_payload: dict[str, Any]) -> None:
        self.response_payload = response_payload
        self.requests: list[dict[str, Any]] = []

    async def place_order(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.requests.append(payload)
        return {
            "status": "submitted",
            "request_id": "req-1",
            "network": "testnet",
            "payload": self.response_payload,
        }


async def _noop_ensure_leverage(**_: Any) -> None:
    return None


class _FakeHttpResponse:
    def __init__(
        self,
        payload: list[dict[str, Any]],
        *,
        status_code: int = 200,
        text: str = "ok",
        headers: dict[str, str] | None = None,
    ) -> None:
        self._payload = payload
        self.status_code = status_code
        self.text = text
        self.headers = headers or {}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            request = httpx.Request("GET", "https://pacifica.test")
            response = httpx.Response(self.status_code, request=request, text=self.text, headers=self.headers)
            raise httpx.HTTPStatusError("request failed", request=request, response=response)
        return None

    def json(self) -> list[dict[str, Any]]:
        return self._payload


class _FakeHttpClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def get(self, url: str, *, params: dict[str, Any], headers: dict[str, str]) -> _FakeHttpResponse:
        self.calls.append({"url": url, "params": params, "headers": headers})
        interval_ms = 60_000 if params["interval"] == "1m" else 900_000
        start_time = int(params["start_time"])
        return _FakeHttpResponse(
            [
                {
                    "symbol": params["symbol"],
                    "interval": params["interval"],
                    "openTime": start_time,
                    "closeTime": start_time + interval_ms,
                    "open": "100000",
                    "high": "101000",
                    "low": "99000",
                    "close": "100500",
                    "volume": "42",
                    "tradeCount": 7,
                }
            ]
        )


class _ChunkedFakeHttpClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def get(self, url: str, *, params: dict[str, Any], headers: dict[str, str]) -> _FakeHttpResponse:
        self.calls.append({"url": url, "params": params, "headers": headers})
        start_time = int(params["start_time"])
        end_time = int(params["end_time"])
        return _FakeHttpResponse(
            [
                {
                    "symbol": params["symbol"],
                    "interval": params["interval"],
                    "openTime": start_time,
                    "closeTime": start_time + 60_000,
                    "open": "100000",
                    "high": "101000",
                    "low": "99000",
                    "close": "100500",
                    "volume": "42",
                    "tradeCount": 7,
                },
                {
                    "symbol": params["symbol"],
                    "interval": params["interval"],
                    "openTime": end_time,
                    "closeTime": end_time + 60_000,
                    "open": "100500",
                    "high": "101500",
                    "low": "99500",
                    "close": "101000",
                    "volume": "43",
                    "tradeCount": 8,
                },
            ]
        )


class _RetryingFakeHttpClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self._attempts_by_window: dict[tuple[int, int], int] = {}

    async def get(self, url: str, *, params: dict[str, Any], headers: dict[str, str]) -> _FakeHttpResponse:
        self.calls.append({"url": url, "params": params, "headers": headers})
        start_time = int(params["start_time"])
        end_time = int(params["end_time"])
        window_key = (start_time, end_time)
        attempt = self._attempts_by_window.get(window_key, 0)
        self._attempts_by_window[window_key] = attempt + 1
        if attempt == 0:
            return _FakeHttpResponse(
                [],
                status_code=429,
                text='{"success":false,"error":"rate limited"}',
                headers={"Retry-After": "0"},
            )
        return _FakeHttpResponse(
            [
                {
                    "symbol": params["symbol"],
                    "interval": params["interval"],
                    "openTime": start_time,
                    "closeTime": start_time + 60_000,
                    "open": "100000",
                    "high": "101000",
                    "low": "99000",
                    "close": "100500",
                    "volume": "42",
                    "tradeCount": 7,
                }
            ]
        )


async def _noop_throttle(**_: Any) -> None:
    return None


def test_load_candle_lookup_backfills_sparse_windows_until_lookback_is_satisfied() -> None:
    service = object.__new__(PacificaMarketDataService)
    service._candle_cache = {}
    service._candle_lock = asyncio.Lock()
    step = 300_000

    async def fake_load_candles(*, symbol: str, timeframe: str, start_time: int, end_time: int) -> list[dict[str, Any]]:
        del symbol, timeframe
        if end_time >= 10 * step:
            opens = [37 * step, 38 * step, 39 * step]
        else:
            opens = [0, 1 * step, 2 * step, 3 * step, 4 * step]
        return [
            {
                "open_time": open_time,
                "close_time": open_time + step - 1,
                "symbol": "BTC",
                "interval": "5m",
                "open": 100.0,
                "high": 101.0,
                "low": 99.0,
                "close": 100.5,
                "volume": 42.0,
                "trade_count": 7,
            }
            for open_time in opens
            if start_time <= open_time <= end_time
        ]

    service._load_candles = fake_load_candles

    candles = asyncio.run(
        service._load_candles_with_backfill(
            symbol="BTC",
            timeframe="5m",
            lookback=8,
            boundary_end=(50 * step) - 1,
        )
    )

    assert [item["open_time"] for item in candles] == [
        0,
        1 * step,
        2 * step,
        3 * step,
        4 * step,
        37 * step,
        38 * step,
        39 * step,
    ]


def test_normalize_payload_preserves_tick_level_without_injecting_user_alias() -> None:
    client = object.__new__(PacificaClient)
    client.settings = SimpleNamespace(pacifica_builder_code="")

    normalized = client._normalize_payload(
        "create_order",
        {
            "account": "wallet-1",
            "symbol": "BTC",
            "side": "bid",
            "price": 100_000,
            "amount": 0.1,
            "tick_level": "200000",
            "tif": "GTC",
        },
        account="wallet-1",
    )

    assert "user" not in normalized
    assert normalized["tick_level"] == 200000


def test_normalize_payload_cancel_order_ignores_side_and_tick_level_hints() -> None:
    client = object.__new__(PacificaClient)
    client.settings = SimpleNamespace(pacifica_builder_code="")

    normalized = client._normalize_payload(
        "cancel_order",
        {
            "account": "wallet-1",
            "symbol": "BTC",
            "order_id": "101",
            "side": "bid",
            "tick_level": "200000",
        },
        account="wallet-1",
    )

    assert normalized == {
        "symbol": "BTC",
        "order_id": "101",
    }


def test_get_kline_sends_snake_case_and_legacy_camel_case_query_params() -> None:
    client = object.__new__(PacificaClient)
    client.settings = SimpleNamespace(pacifica_rest_url="https://pacifica.test")
    client._http = _FakeHttpClient()
    client._throttle = _noop_throttle

    candles = asyncio.run(
        client.get_kline(
            "BTC",
            interval="15m",
            start_time=1_000,
            end_time=2_000,
        )
    )

    assert client._http.calls[0]["params"] == {
        "symbol": "BTC",
        "interval": "15m",
        "start_time": 0,
        "startTime": 0,
        "end_time": 0,
        "endTime": 0,
    }
    assert candles[0]["trade_count"] == 7


def test_get_mark_kline_uses_mark_endpoint() -> None:
    client = object.__new__(PacificaClient)
    client.settings = SimpleNamespace(pacifica_rest_url="https://pacifica.test")
    client._http = _FakeHttpClient()
    client._throttle = _noop_throttle

    candles = asyncio.run(
        client.get_mark_kline(
            "BTC",
            interval="1m",
            start_time=1_000,
            end_time=2_000,
        )
    )

    assert client._http.calls[0]["url"] == "https://pacifica.test/kline/mark"
    assert candles[0]["symbol"] == "BTC"


def test_get_kline_chunks_long_ranges_into_multiple_requests() -> None:
    client = object.__new__(PacificaClient)
    client.settings = SimpleNamespace(pacifica_rest_url="https://pacifica.test")
    client._http = _ChunkedFakeHttpClient()
    client._throttle = _noop_throttle

    candles = asyncio.run(
        client.get_kline(
            "BTC",
            interval="15m",
            start_time=0,
            end_time=900_000 * 4_001,
        )
    )

    assert len(client._http.calls) == 2
    assert client._http.calls[0]["params"]["start_time"] == 0
    assert client._http.calls[0]["params"]["end_time"] == 900_000 * 3_999
    assert client._http.calls[1]["params"]["start_time"] == 900_000 * 4_000
    assert client._http.calls[1]["params"]["end_time"] == 900_000 * 4_001
    assert len(candles) == 4
    assert candles[0]["open_time"] == 0
    assert candles[-1]["open_time"] == 900_000 * 4_001


def test_get_kline_retries_rate_limited_windows() -> None:
    client = object.__new__(PacificaClient)
    client.settings = SimpleNamespace(pacifica_rest_url="https://pacifica.test")
    client._http = _RetryingFakeHttpClient()
    client._throttle = _noop_throttle

    candles = asyncio.run(
        client.get_kline(
            "BTC",
            interval="15m",
            start_time=0,
            end_time=900_000,
        )
    )

    assert len(client._http.calls) == 2
    assert len(candles) == 1
    assert candles[0]["open_time"] == 0


def test_load_candle_lookup_falls_back_to_mark_candles_when_trade_feed_is_sparse() -> None:
    service = object.__new__(PacificaMarketDataService)
    service._candle_cache = {}
    service._candle_lock = asyncio.Lock()

    async def fake_load_candles(*, symbol: str, timeframe: str, start_time: int, end_time: int) -> list[dict[str, Any]]:
        del symbol, timeframe, start_time, end_time
        return []

    async def fake_load_mark_candles(*, symbol: str, timeframe: str, start_time: int, end_time: int) -> list[dict[str, Any]]:
        del symbol, timeframe, start_time, end_time
        return [
            {
                "open_time": 0,
                "close_time": 59_999,
                "symbol": "BTC",
                "interval": "1m",
                "open": 100.0,
                "high": 101.0,
                "low": 99.0,
                "close": 100.5,
                "volume": 0.0,
                "trade_count": 0,
            },
            {
                "open_time": 60_000,
                "close_time": 119_999,
                "symbol": "BTC",
                "interval": "1m",
                "open": 100.5,
                "high": 101.5,
                "low": 100.0,
                "close": 101.0,
                "volume": 0.0,
                "trade_count": 0,
            },
        ]

    service._load_candles = fake_load_candles
    service._load_mark_candles = fake_load_mark_candles

    candles = asyncio.run(
        service._load_candles_with_backfill(
            symbol="BTC",
            timeframe="1m",
            lookback=2,
            boundary_end=120_000,
        )
    )

    assert [item["open_time"] for item in candles] == [0, 60_000]
    assert all(item["trade_count"] == 0 for item in candles)


def test_execute_action_uses_normalized_client_order_id_from_client_payload() -> None:
    normalized_id = str(uuid.uuid4())
    worker = object.__new__(BotRuntimeWorker)
    worker._pacifica = _FakePacificaClient({"client_order_id": normalized_id})
    worker._ensure_leverage = _noop_ensure_leverage

    response = asyncio.run(
        worker._execute_action(
            runtime={"id": "runtime-1"},
            runtime_state={},
            action={
                "type": "place_limit_order",
                "symbol": "BTC",
                "side": "long",
                "price": 99_500,
                "quantity": 0.01,
                "leverage": 3,
                "reduce_only": False,
                "client_order_id": "maker-entry-001",
            },
            credentials={
                "account_address": "wallet-1",
                "agent_wallet_address": "agent-1",
                "agent_private_key": "secret",
            },
            market_lookup={"BTC": {"lot_size": 0.001, "mark_price": 105_000}},
            position_lookup={},
        )
    )

    assert response["execution_meta"]["client_order_id"] == normalized_id


def test_execute_action_uses_normalized_tpsl_ids_from_client_payload() -> None:
    take_profit_id = str(uuid.uuid4())
    stop_loss_id = str(uuid.uuid4())
    worker = object.__new__(BotRuntimeWorker)
    worker._pacifica = _FakePacificaClient(
        {
            "take_profit": {"client_order_id": take_profit_id},
            "stop_loss": {"client_order_id": stop_loss_id},
        }
    )

    response = asyncio.run(
        worker._execute_action(
            runtime={"id": "runtime-1"},
            runtime_state={
                "managed_positions": {
                    "BTC": {
                        "symbol": "BTC",
                        "amount": 0.01,
                        "side": "bid",
                        "entry_client_order_id": "maker-entry-001",
                    }
                }
            },
            action={
                "type": "set_tpsl",
                "symbol": "BTC",
                "take_profit_pct": 1.8,
                "stop_loss_pct": 0.9,
            },
            credentials={
                "account_address": "wallet-1",
                "agent_wallet_address": "agent-1",
                "agent_private_key": "secret",
            },
            market_lookup={"BTC": {"tick_size": 0.5, "mark_price": 105_000}},
            position_lookup={
                "BTC": {
                    "symbol": "BTC",
                    "side": "bid",
                    "amount": 0.01,
                    "mark_price": 105_000,
                }
            },
        )
    )

    assert response["execution_meta"]["take_profit_client_order_id"] == take_profit_id
    assert response["execution_meta"]["stop_loss_client_order_id"] == stop_loss_id
