from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from dataclasses import dataclass
from time import time
from typing import Any

import websockets

from src.core.settings import get_settings
from src.services.pacifica_client import PacificaClient, PacificaClientError, get_pacifica_client


logger = logging.getLogger(__name__)
TIMEFRAME_TO_MS: dict[str, int] = {
    "1m": 60_000,
    "5m": 300_000,
    "15m": 900_000,
    "30m": 1_800_000,
    "1h": 3_600_000,
    "4h": 14_400_000,
    "1d": 86_400_000,
}


@dataclass
class _CandleCacheEntry:
    candles: list[dict[str, Any]]
    lookback: int
    boundary_end: int


class PacificaMarketDataService:
    def __init__(self, pacifica_client: PacificaClient | None = None) -> None:
        self._settings = get_settings()
        self._pacifica = pacifica_client or get_pacifica_client()
        self._running = False
        self._ws_task: asyncio.Task | None = None
        self._market_info_cache: list[dict[str, Any]] = []
        self._market_info_updated_at = 0.0
        self._rest_price_cache: dict[str, dict[str, Any]] = {}
        self._rest_price_updated_at = 0.0
        self._ws_price_cache: dict[str, dict[str, Any]] = {}
        self._ws_price_updated_at = 0.0
        self._candle_cache: dict[tuple[str, str], _CandleCacheEntry] = {}
        self._market_lock = asyncio.Lock()
        self._price_lock = asyncio.Lock()
        self._candle_lock = asyncio.Lock()

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._ws_task = asyncio.create_task(self._run_price_subscription(), name="pacifica-price-feed")

    async def stop(self) -> None:
        self._running = False
        if self._ws_task is not None:
            self._ws_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._ws_task
            self._ws_task = None

    async def get_markets(self, *, force_refresh: bool = False) -> list[dict[str, Any]]:
        market_info, prices = await asyncio.gather(
            self._get_market_info(force_refresh=force_refresh),
            self._get_price_rows(force_refresh=force_refresh),
        )
        return self._merge_market_rows(market_info, prices)

    async def get_price_lookup(self) -> dict[str, float]:
        rows = await self._get_price_rows()
        lookup: dict[str, float] = {}
        for symbol, item in rows.items():
            mark_price = self._coerce_float(item.get("mark_price"), 0.0)
            if mark_price > 0:
                lookup[symbol] = mark_price
        return lookup

    async def load_candle_lookup(
        self,
        requests: list[dict[str, Any]],
    ) -> dict[str, dict[str, list[dict[str, Any]]]]:
        if not requests:
            return {}
        resolved_end_time = int(time() * 1_000)
        normalized_requests: list[tuple[str, str, int, int]] = []
        required_lookbacks: dict[tuple[str, str, int], int] = {}
        for request in requests:
            symbol = str(request.get("symbol") or "").upper().replace("-PERP", "").strip()
            timeframe = str(request.get("timeframe") or "").strip().lower()
            lookback = max(1, int(request.get("lookback") or 1))
            timeframe_ms = TIMEFRAME_TO_MS.get(timeframe)
            if not symbol or timeframe_ms is None:
                continue
            boundary_end = (resolved_end_time // timeframe_ms) * timeframe_ms
            normalized_requests.append((symbol, timeframe, lookback, boundary_end))
            dedupe_key = (symbol, timeframe, boundary_end)
            required_lookbacks[dedupe_key] = max(required_lookbacks.get(dedupe_key, 0), lookback)

        pending_fetches: list[tuple[tuple[str, str], int, int, asyncio.Task[list[dict[str, Any]]]]] = []
        for (symbol, timeframe, boundary_end), lookback in required_lookbacks.items():
            cache_key = (symbol, timeframe)
            cached = self._candle_cache.get(cache_key)
            if cached is not None and cached.boundary_end == boundary_end and cached.lookback >= lookback:
                continue
            timeframe_ms = TIMEFRAME_TO_MS[timeframe]
            start_time = boundary_end - timeframe_ms * lookback
            pending_fetches.append(
                (
                    cache_key,
                    lookback,
                    boundary_end,
                    asyncio.create_task(
                        self._load_candles(
                            symbol=symbol,
                            timeframe=timeframe,
                            start_time=start_time,
                            end_time=boundary_end,
                        )
                    ),
                )
            )

        if pending_fetches:
            resolved_candles = await asyncio.gather(*(task for _, _, _, task in pending_fetches))
            async with self._candle_lock:
                for (cache_key, lookback, boundary_end, _), candles in zip(pending_fetches, resolved_candles, strict=False):
                    self._candle_cache[cache_key] = _CandleCacheEntry(
                        candles=candles,
                        lookback=lookback,
                        boundary_end=boundary_end,
                    )

        lookup: dict[str, dict[str, list[dict[str, Any]]]] = {}
        for symbol, timeframe, lookback, _ in normalized_requests:
            cached = self._candle_cache.get((symbol, timeframe))
            if cached is None:
                continue
            candle_window = cached.candles[-lookback:] if len(cached.candles) > lookback else cached.candles
            lookup.setdefault(symbol, {})[timeframe] = self._clone_candles(candle_window)
        return lookup

    async def _get_market_info(self, *, force_refresh: bool = False) -> list[dict[str, Any]]:
        ttl = self._settings.pacifica_market_cache_ttl_seconds
        if not force_refresh and self._market_info_cache and (time() - self._market_info_updated_at) < ttl:
            return self._clone_rows(self._market_info_cache)
        async with self._market_lock:
            if not force_refresh and self._market_info_cache and (time() - self._market_info_updated_at) < ttl:
                return self._clone_rows(self._market_info_cache)
            rows = await self._pacifica.get_market_info()
            self._market_info_cache = rows
            self._market_info_updated_at = time()
            return self._clone_rows(rows)

    async def _get_price_rows(self, *, force_refresh: bool = False) -> dict[str, dict[str, Any]]:
        ws_stale = (time() - self._ws_price_updated_at) >= self._settings.pacifica_price_cache_ttl_seconds
        if not force_refresh and self._ws_price_cache and not ws_stale:
            return self._clone_price_rows(self._ws_price_cache)
        async with self._price_lock:
            rest_stale = (time() - self._rest_price_updated_at) >= self._settings.pacifica_price_cache_ttl_seconds
            if force_refresh or not self._rest_price_cache or rest_stale:
                rows = await self._pacifica.get_prices()
                self._rest_price_cache = {
                    str(item.get("symbol") or "").upper().replace("-PERP", "").strip(): item
                    for item in rows
                    if str(item.get("symbol") or "").strip()
                }
                self._rest_price_updated_at = time()
        return self._clone_price_rows(self._ws_price_cache or self._rest_price_cache)

    async def _load_candles(
        self,
        *,
        symbol: str,
        timeframe: str,
        start_time: int,
        end_time: int,
    ) -> list[dict[str, Any]]:
        try:
            return await self._pacifica.get_kline(
                symbol,
                interval=timeframe,
                start_time=start_time,
                end_time=end_time,
            )
        except PacificaClientError:
            return []

    async def _run_price_subscription(self) -> None:
        while self._running:
            try:
                async with websockets.connect(self._settings.pacifica_ws_url, ping_interval=30) as websocket:
                    await websocket.send(json.dumps({"method": "subscribe", "params": {"source": "prices"}}))
                    async for message in websocket:
                        if not self._running:
                            return
                        self._ingest_price_message(message)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # pragma: no cover - network instability
                logger.warning("Pacifica price feed disconnected: %s", exc)
                await asyncio.sleep(2)

    def _ingest_price_message(self, message: str) -> None:
        try:
            payload = json.loads(message)
        except ValueError:
            return
        rows = self._extract_price_rows(payload)
        if not rows:
            return
        merged = dict(self._ws_price_cache)
        for row in rows:
            symbol = str(row.get("symbol") or "").upper().replace("-PERP", "").strip()
            if not symbol:
                continue
            merged[symbol] = row
        self._ws_price_cache = merged
        self._ws_price_updated_at = time()

    def _extract_price_rows(self, payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return [self._normalize_price_row(item) for item in payload if isinstance(item, dict)]
        if not isinstance(payload, dict):
            return []
        if "symbol" in payload:
            normalized = self._normalize_price_row(payload)
            return [normalized] if normalized else []
        for key in ("data", "prices", "result"):
            nested = payload.get(key)
            if isinstance(nested, list):
                return [self._normalize_price_row(item) for item in nested if isinstance(item, dict)]
            if isinstance(nested, dict):
                normalized = self._normalize_price_row(nested)
                return [normalized] if normalized else []
        return []

    def _normalize_price_row(self, row: dict[str, Any]) -> dict[str, Any]:
        symbol = str(row.get("symbol") or row.get("s") or "").upper().replace("-PERP", "").strip()
        if not symbol:
            return {}
        return {
            "symbol": symbol,
            "mark_price": self._coerce_float(row.get("mark", row.get("mid", row.get("oracle"))), 0.0),
            "mid_price": self._coerce_float(row.get("mid"), 0.0),
            "oracle_price": self._coerce_float(row.get("oracle"), 0.0),
            "funding_rate": self._coerce_float(row.get("funding", row.get("funding_rate")), 0.0),
            "next_funding_rate": self._coerce_float(row.get("next_funding", row.get("next_funding_rate")), 0.0),
            "open_interest": self._coerce_float(row.get("open_interest", row.get("openInterest")), 0.0),
            "volume_24h": self._coerce_float(row.get("volume_24h", row.get("volume24h")), 0.0),
            "yesterday_price": self._coerce_float(row.get("yesterday_price", row.get("yesterdayPrice")), 0.0),
            "updated_at": row.get("timestamp") or row.get("updated_at") or row.get("updatedAt"),
        }

    def _merge_market_rows(
        self,
        market_info: list[dict[str, Any]],
        prices: dict[str, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        markets: list[dict[str, Any]] = []
        for row in market_info:
            symbol = str(row.get("symbol") or "").upper().replace("-PERP", "").strip()
            if not symbol:
                continue
            live_price = prices.get(symbol, {})
            markets.append(
                {
                    "symbol": symbol,
                    "display_symbol": f"{symbol}-PERP",
                    "mark_price": self._coerce_float(
                        live_price.get("mark_price"),
                        self._coerce_float(row.get("mark_price", row.get("markPrice")), 0.0),
                    ),
                    "mid_price": self._coerce_float(live_price.get("mid_price"), 0.0),
                    "oracle_price": self._coerce_float(live_price.get("oracle_price"), 0.0),
                    "funding_rate": self._coerce_float(
                        live_price.get("funding_rate"),
                        self._coerce_float(row.get("funding_rate", row.get("fundingRate")), 0.0),
                    ),
                    "next_funding_rate": self._coerce_float(
                        live_price.get("next_funding_rate"),
                        self._coerce_float(row.get("next_funding_rate", row.get("nextFundingRate")), 0.0),
                    ),
                    "min_order_size": self._coerce_float(row.get("min_order_size", row.get("minOrderSize")), 0.0),
                    "max_order_size": self._coerce_float(row.get("max_order_size", row.get("maxOrderSize")), 0.0),
                    "max_leverage": self._coerce_int(row.get("max_leverage", row.get("maxLeverage")), 0),
                    "isolated_only": self._coerce_bool(row.get("isolated_only", row.get("isolatedOnly")), False),
                    "tick_size": self._coerce_float(row.get("tick_size", row.get("tickSize")), 0.0),
                    "lot_size": self._coerce_float(row.get("lot_size", row.get("lotSize")), 0.0),
                    "open_interest": self._coerce_float(live_price.get("open_interest"), 0.0),
                    "volume_24h": self._coerce_float(live_price.get("volume_24h"), 0.0),
                    "yesterday_price": self._coerce_float(live_price.get("yesterday_price"), 0.0),
                    "updated_at": live_price.get("updated_at")
                    or row.get("updated_at")
                    or row.get("updatedAt")
                    or row.get("created_at")
                    or row.get("createdAt"),
                }
            )
        markets.sort(key=lambda item: item.get("volume_24h", 0.0), reverse=True)
        return markets

    @staticmethod
    def _coerce_float(value: Any, default: float = 0.0) -> float:
        try:
            if value in (None, ""):
                return default
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _coerce_int(value: Any, default: int = 0) -> int:
        try:
            if value in (None, ""):
                return default
            return int(float(value))
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _coerce_bool(value: Any, default: bool = False) -> bool:
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"true", "1", "yes", "y"}:
                return True
            if normalized in {"false", "0", "no", "n"}:
                return False
        return bool(value)

    @staticmethod
    def _clone_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [dict(item) for item in rows]

    @staticmethod
    def _clone_price_rows(rows: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
        return {symbol: dict(item) for symbol, item in rows.items()}

    @staticmethod
    def _clone_candles(candles: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [dict(candle) for candle in candles]


_market_data_service: PacificaMarketDataService | None = None


def get_pacifica_market_data_service() -> PacificaMarketDataService:
    global _market_data_service
    if _market_data_service is None:
        _market_data_service = PacificaMarketDataService()
    return _market_data_service
