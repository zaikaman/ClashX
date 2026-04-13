from __future__ import annotations

import asyncio
from copy import deepcopy
from typing import Any

import pytest

from src.services.bot_backtest_service import BotBacktestService, MARKET_UNIVERSE_SYMBOL
from src.services.pacifica_client import PacificaClientError


BASE_TIME_MS = 1_710_000_000_000
FIFTEEN_MINUTES_MS = 900_000
ONE_MINUTE_MS = 60_000


def _symbol_candle(
    symbol: str,
    offset: int,
    open_price: float,
    high_price: float,
    low_price: float,
    close_price: float,
    volume: float = 1000.0,
    interval: str = "15m",
    interval_ms: int = FIFTEEN_MINUTES_MS,
) -> dict[str, Any]:
    open_time = BASE_TIME_MS + offset * interval_ms
    close_time = open_time + interval_ms
    return {
        "open_time": open_time,
        "close_time": close_time,
        "symbol": symbol,
        "interval": interval,
        "open": open_price,
        "high": high_price,
        "low": low_price,
        "close": close_price,
        "volume": volume,
        "trade_count": 10,
    }


def _candle(
    offset: int,
    open_price: float,
    high_price: float,
    low_price: float,
    close_price: float,
    volume: float = 1000.0,
    *,
    interval: str = "15m",
    interval_ms: int = FIFTEEN_MINUTES_MS,
) -> dict[str, Any]:
    return _symbol_candle("BTC", offset, open_price, high_price, low_price, close_price, volume, interval=interval, interval_ms=interval_ms)


def _graph_rules(nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "graph": {
            "version": 1,
            "entry": "builder-entry",
            "nodes": [{"id": "builder-entry", "kind": "entry", "position": {"x": 0, "y": 0}}, *nodes],
            "edges": edges,
        }
    }


class FakeSupabaseRestClient:
    def __init__(self, tables: dict[str, list[dict[str, Any]]]) -> None:
        self.tables = {name: [deepcopy(row) for row in rows] for name, rows in tables.items()}

    def select(
        self,
        table: str,
        *,
        columns: str = "*",
        filters: dict[str, Any] | None = None,
        order: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        del columns
        rows = [deepcopy(row) for row in self.tables.get(table, []) if self._matches(row, filters)]
        if order:
            field, _, direction = order.partition(".")
            rows.sort(key=lambda row: row.get(field) or "", reverse=direction.lower() == "desc")
        if limit is not None:
            rows = rows[:limit]
        return rows

    def maybe_one(
        self,
        table: str,
        *,
        columns: str = "*",
        filters: dict[str, Any] | None = None,
        order: str | None = None,
    ) -> dict[str, Any] | None:
        rows = self.select(table, columns=columns, filters=filters, order=order, limit=1)
        return rows[0] if rows else None

    def insert(
        self,
        table: str,
        payload: dict[str, Any] | list[dict[str, Any]],
        *,
        upsert: bool = False,
        on_conflict: str | None = None,
        returning: str = "representation",
    ) -> list[dict[str, Any]]:
        del upsert, on_conflict
        items = payload if isinstance(payload, list) else [payload]
        stored = [deepcopy(item) for item in items]
        self.tables.setdefault(table, []).extend(stored)
        if returning == "minimal":
            return []
        return [deepcopy(item) for item in stored]

    @staticmethod
    def _matches(row: dict[str, Any], filters: dict[str, Any] | None) -> bool:
        if not filters:
            return True
        for key, expected in filters.items():
            if row.get(key) != expected:
                return False
        return True


class FakePacificaClient:
    def __init__(self, candle_rows: dict[tuple[str, str], list[dict[str, Any]]]) -> None:
        self.candle_rows = {(symbol, interval): [deepcopy(row) for row in rows] for (symbol, interval), rows in candle_rows.items()}

    async def get_kline(
        self,
        symbol: str,
        *,
        interval: str = "15m",
        start_time: int,
        end_time: int | None = None,
    ) -> list[dict[str, Any]]:
        rows = self.candle_rows.get((symbol, interval), [])
        resolved_end = end_time if end_time is not None else 2**63 - 1
        return [
            deepcopy(row)
            for row in rows
            if int(row.get("close_time") or 0) >= start_time and int(row.get("close_time") or 0) <= resolved_end
        ]


class FailingPacificaClient(FakePacificaClient):
    async def get_kline(
        self,
        symbol: str,
        *,
        interval: str = "15m",
        start_time: int,
        end_time: int | None = None,
    ) -> list[dict[str, Any]]:
        del symbol, interval, start_time, end_time
        raise PacificaClientError(
            'Pacifica kline request failed (429): {"success":false,"error":"rate limited"}',
            status_code=429,
        )


def _tables(rules_json: dict[str, Any], *, wallet_address: str = "wallet-a", user_id: str = "user-a", bot_id: str = "bot-a") -> dict[str, list[dict[str, Any]]]:
    return {
        "bot_definitions": [
            {
                "id": bot_id,
                "user_id": user_id,
                "wallet_address": wallet_address,
                "name": "Backtest Bot",
                "description": "Replay rules",
                "visibility": "private",
                "market_scope": "Pacifica perpetuals / BTC",
                "strategy_type": "rules",
                "authoring_mode": "visual",
                "rules_version": 1,
                "rules_json": rules_json,
                "created_at": "2026-03-16T00:00:00+00:00",
                "updated_at": "2026-03-16T00:00:00+00:00",
            }
        ],
        "bot_backtest_runs": [],
    }


def _service(rules_json: dict[str, Any], candles: list[dict[str, Any]], *, wallet_address: str = "wallet-a", user_id: str = "user-a", bot_id: str = "bot-a") -> tuple[BotBacktestService, FakeSupabaseRestClient]:
    supabase = FakeSupabaseRestClient(_tables(rules_json, wallet_address=wallet_address, user_id=user_id, bot_id=bot_id))
    pacifica = FakePacificaClient({("BTC", "15m"): candles})
    return BotBacktestService(pacifica_client=pacifica, supabase=supabase), supabase


def _service_with_candle_map(
    rules_json: dict[str, Any],
    candle_rows: dict[tuple[str, str], list[dict[str, Any]]],
    *,
    wallet_address: str = "wallet-a",
    user_id: str = "user-a",
    bot_id: str = "bot-a",
) -> tuple[BotBacktestService, FakeSupabaseRestClient]:
    supabase = FakeSupabaseRestClient(_tables(rules_json, wallet_address=wallet_address, user_id=user_id, bot_id=bot_id))
    pacifica = FakePacificaClient(candle_rows)
    return BotBacktestService(pacifica_client=pacifica, supabase=supabase), supabase


def test_backtest_profitable_long_then_close() -> None:
    rules_json = _graph_rules(
        nodes=[
            {"id": "condition-open", "kind": "condition", "position": {"x": 120, "y": 80}, "config": {"type": "price_above", "symbol": "BTC", "value": 90}},
            {"id": "action-open", "kind": "action", "position": {"x": 320, "y": 80}, "config": {"type": "open_long", "symbol": "BTC", "size_usd": 100, "leverage": 1}},
            {"id": "condition-close", "kind": "condition", "position": {"x": 120, "y": 220}, "config": {"type": "position_pnl_above", "symbol": "BTC", "value": 20}},
            {"id": "action-close", "kind": "action", "position": {"x": 320, "y": 220}, "config": {"type": "close_position", "symbol": "BTC"}},
        ],
        edges=[
            {"id": "edge-open-1", "source": "builder-entry", "target": "condition-open"},
            {"id": "edge-open-2", "source": "condition-open", "target": "action-open"},
            {"id": "edge-close-1", "source": "builder-entry", "target": "condition-close"},
            {"id": "edge-close-2", "source": "condition-close", "target": "action-close"},
        ],
    )
    candles = [
        _candle(0, 99, 101, 98, 100),
        _candle(1, 100, 131, 100, 130),
    ]
    service, _ = _service(rules_json, candles)

    run = asyncio.run(
        service.run_backtest(
            None,
            bot_id="bot-a",
            wallet_address="wallet-a",
            user_id="user-a",
            interval="15m",
            start_time=BASE_TIME_MS,
            end_time=BASE_TIME_MS + 3 * FIFTEEN_MINUTES_MS,
            initial_capital_usd=10_000,
        )
    )

    assert run["status"] == "completed"
    assert run["trade_count"] == 1
    assert run["pnl_total"] > 0
    assert run["result_json"]["trades"][0]["close_reason"] == "action_close"


def test_backtest_emits_progress_updates_during_execution() -> None:
    rules_json = _graph_rules(
        nodes=[
            {"id": "condition-open", "kind": "condition", "position": {"x": 120, "y": 80}, "config": {"type": "price_above", "symbol": "BTC", "value": 90}},
            {"id": "action-open", "kind": "action", "position": {"x": 320, "y": 80}, "config": {"type": "open_long", "symbol": "BTC", "size_usd": 100, "leverage": 1}},
        ],
        edges=[
            {"id": "edge-open-1", "source": "builder-entry", "target": "condition-open"},
            {"id": "edge-open-2", "source": "condition-open", "target": "action-open"},
        ],
    )
    candles = [_candle(index, 99, 101, 98, 100 + (index % 3)) for index in range(12)]
    service, _ = _service(rules_json, candles)
    events: list[dict[str, Any]] = []

    async def collect_progress(payload: dict[str, Any]) -> None:
        events.append(payload)

    run = asyncio.run(
        service.run_backtest(
            None,
            bot_id="bot-a",
            wallet_address="wallet-a",
            user_id="user-a",
            interval="15m",
            start_time=BASE_TIME_MS,
            end_time=BASE_TIME_MS + 12 * FIFTEEN_MINUTES_MS,
            initial_capital_usd=10_000,
            progress=collect_progress,
        )
    )

    assert run["status"] == "completed"
    assert events
    assert any(event["stage"] == "Loading market history" for event in events)
    assert any(event["stage"] == "Simulating strategy" for event in events)
    assert events[-1]["progress"] == 100.0


def test_backtest_can_resume_from_checkpoint_and_match_full_result() -> None:
    rules_json = _graph_rules(
        nodes=[
            {"id": "condition-open", "kind": "condition", "position": {"x": 120, "y": 80}, "config": {"type": "price_above", "symbol": "BTC", "value": 90}},
            {"id": "action-open", "kind": "action", "position": {"x": 320, "y": 80}, "config": {"type": "open_long", "symbol": "BTC", "size_usd": 100, "leverage": 1}},
        ],
        edges=[
            {"id": "edge-open-1", "source": "builder-entry", "target": "condition-open"},
            {"id": "edge-open-2", "source": "condition-open", "target": "action-open"},
        ],
    )
    candles = [_candle(index, 99 + index, 101 + index, 98 + index, 100 + index) for index in range(48)]

    baseline_service, _ = _service(rules_json, candles)
    baseline_run = asyncio.run(
        baseline_service.run_backtest(
            None,
            bot_id="bot-a",
            wallet_address="wallet-a",
            user_id="user-a",
            interval="15m",
            start_time=BASE_TIME_MS,
            end_time=BASE_TIME_MS + 49 * FIFTEEN_MINUTES_MS,
            initial_capital_usd=10_000,
        )
    )

    checkpoint_service, _ = _service(rules_json, candles)
    progress_events: list[dict[str, Any]] = []

    async def collect_progress(payload: dict[str, Any]) -> None:
        progress_events.append(deepcopy(payload))

    asyncio.run(
        checkpoint_service.run_backtest(
            None,
            bot_id="bot-a",
            wallet_address="wallet-a",
            user_id="user-a",
            interval="15m",
            start_time=BASE_TIME_MS,
            end_time=BASE_TIME_MS + 49 * FIFTEEN_MINUTES_MS,
            initial_capital_usd=10_000,
            progress=collect_progress,
        )
    )

    resume_checkpoint = next(
        event["checkpoint"]
        for event in progress_events
        if event["stage"] == "Simulating strategy" and int(event.get("metrics", {}).get("processed_bars", 0)) >= 12
    )

    resumed_service, _ = _service(rules_json, candles)
    resumed_run = asyncio.run(
        resumed_service.run_backtest(
            None,
            bot_id="bot-a",
            wallet_address="wallet-a",
            user_id="user-a",
            interval="15m",
            start_time=BASE_TIME_MS,
            end_time=BASE_TIME_MS + 49 * FIFTEEN_MINUTES_MS,
            initial_capital_usd=10_000,
            resume_checkpoint=resume_checkpoint,
        )
    )

    assert resumed_run["status"] == baseline_run["status"]
    assert resumed_run["trade_count"] == baseline_run["trade_count"]
    assert resumed_run["pnl_total"] == baseline_run["pnl_total"]
    assert resumed_run["max_drawdown_pct"] == baseline_run["max_drawdown_pct"]
    assert resumed_run["result_json"] == baseline_run["result_json"]


def test_backtest_persists_history_row_with_snapshots_and_inputs() -> None:
    rules_json = _graph_rules(
        nodes=[
            {"id": "condition-open", "kind": "condition", "position": {"x": 120, "y": 80}, "config": {"type": "price_above", "symbol": "BTC", "value": 90}},
            {"id": "action-open", "kind": "action", "position": {"x": 320, "y": 80}, "config": {"type": "open_long", "symbol": "BTC", "size_usd": 100, "leverage": 1}},
        ],
        edges=[
            {"id": "edge-open-1", "source": "builder-entry", "target": "condition-open"},
            {"id": "edge-open-2", "source": "condition-open", "target": "action-open"},
        ],
    )
    candles = [_candle(0, 99, 101, 98, 100), _candle(1, 100, 106, 100, 105)]
    service, supabase = _service(rules_json, candles)

    run = asyncio.run(
        service.run_backtest(
            None,
            bot_id="bot-a",
            wallet_address="wallet-a",
            user_id="user-a",
            interval="15m",
            start_time=BASE_TIME_MS,
            end_time=BASE_TIME_MS + 3 * FIFTEEN_MINUTES_MS,
            initial_capital_usd=10_000,
            assumptions={"fee_bps": 4, "slippage_bps": 5, "funding_bps_per_interval": 0},
        )
    )

    assert len(supabase.tables["bot_backtest_runs"]) == 1
    persisted = supabase.tables["bot_backtest_runs"][0]
    assert persisted["id"] == run["id"]
    assert persisted["bot_name_snapshot"] == "Backtest Bot"
    assert persisted["market_scope_snapshot"] == "Pacifica perpetuals / BTC"
    assert persisted["strategy_type_snapshot"] == "rules"
    assert persisted["assumption_config_json"] == {"fee_bps": 4.0, "slippage_bps": 5.0, "funding_bps_per_interval": 0.0}
    assert persisted["failure_reason"] is None
    assert persisted["result_json"]["summary"]["symbols"] == ["BTC"]
    assert run["assumption_config_json"] == {"fee_bps": 4.0, "slippage_bps": 5.0, "funding_bps_per_interval": 0.0}


def test_backtest_losing_trade_tracks_drawdown() -> None:
    rules_json = _graph_rules(
        nodes=[
            {"id": "condition-open", "kind": "condition", "position": {"x": 120, "y": 80}, "config": {"type": "price_above", "symbol": "BTC", "value": 90}},
            {"id": "action-open", "kind": "action", "position": {"x": 320, "y": 80}, "config": {"type": "open_long", "symbol": "BTC", "size_usd": 100, "leverage": 1}},
            {"id": "condition-close", "kind": "condition", "position": {"x": 120, "y": 220}, "config": {"type": "position_pnl_below", "symbol": "BTC", "value": -10}},
            {"id": "action-close", "kind": "action", "position": {"x": 320, "y": 220}, "config": {"type": "close_position", "symbol": "BTC"}},
        ],
        edges=[
            {"id": "edge-open-1", "source": "builder-entry", "target": "condition-open"},
            {"id": "edge-open-2", "source": "condition-open", "target": "action-open"},
            {"id": "edge-close-1", "source": "builder-entry", "target": "condition-close"},
            {"id": "edge-close-2", "source": "condition-close", "target": "action-close"},
        ],
    )
    candles = [
        _candle(0, 99, 101, 98, 100),
        _candle(1, 100, 100, 84, 85),
    ]
    service, _ = _service(rules_json, candles)

    run = asyncio.run(
        service.run_backtest(
            None,
            bot_id="bot-a",
            wallet_address="wallet-a",
            user_id="user-a",
            interval="15m",
            start_time=BASE_TIME_MS,
            end_time=BASE_TIME_MS + 3 * FIFTEEN_MINUTES_MS,
            initial_capital_usd=10_000,
        )
    )

    assert run["pnl_total"] < 0
    assert run["max_drawdown_pct"] > 0


def test_backtest_infers_smallest_indicator_timeframe_when_interval_is_missing() -> None:
    rules_json = _graph_rules(
        nodes=[
            {
                "id": "condition-open",
                "kind": "condition",
                "position": {"x": 120, "y": 80},
                "config": {"type": "rsi_above", "symbol": "BTC", "timeframe": "1m", "period": 2, "value": 60},
            },
            {
                "id": "action-open",
                "kind": "action",
                "position": {"x": 320, "y": 80},
                "config": {"type": "open_long", "symbol": "BTC", "size_usd": 100, "leverage": 1},
            },
        ],
        edges=[
            {"id": "edge-open-1", "source": "builder-entry", "target": "condition-open"},
            {"id": "edge-open-2", "source": "condition-open", "target": "action-open"},
        ],
    )
    candles = [
        _candle(0, 100, 101, 99, 100, interval="1m", interval_ms=ONE_MINUTE_MS),
        _candle(1, 100, 103, 100, 102, interval="1m", interval_ms=ONE_MINUTE_MS),
        _candle(2, 102, 106, 102, 105, interval="1m", interval_ms=ONE_MINUTE_MS),
        _candle(3, 105, 108, 104, 107, interval="1m", interval_ms=ONE_MINUTE_MS),
    ]
    service, _ = _service_with_candle_map(rules_json, {("BTC", "1m"): candles})

    run = asyncio.run(
        service.run_backtest(
            None,
            bot_id="bot-a",
            wallet_address="wallet-a",
            user_id="user-a",
            interval=None,
            start_time=BASE_TIME_MS,
            end_time=BASE_TIME_MS + 5 * ONE_MINUTE_MS,
            initial_capital_usd=10_000,
        )
    )

    assert run["status"] == "completed"
    assert run["interval"] == "1m"
    assert run["trade_count"] == 0


def test_backtest_prefers_stop_loss_when_tp_and_sl_touch_same_bar() -> None:
    rules_json = _graph_rules(
        nodes=[
            {"id": "condition-open", "kind": "condition", "position": {"x": 120, "y": 80}, "config": {"type": "price_above", "symbol": "BTC", "value": 90}},
            {"id": "action-open", "kind": "action", "position": {"x": 320, "y": 80}, "config": {"type": "open_long", "symbol": "BTC", "size_usd": 100, "leverage": 1}},
            {"id": "action-tpsl", "kind": "action", "position": {"x": 520, "y": 80}, "config": {"type": "set_tpsl", "symbol": "BTC", "take_profit_pct": 5, "stop_loss_pct": 5}},
        ],
        edges=[
            {"id": "edge-open-1", "source": "builder-entry", "target": "condition-open"},
            {"id": "edge-open-2", "source": "condition-open", "target": "action-open"},
            {"id": "edge-open-3", "source": "action-open", "target": "action-tpsl"},
        ],
    )
    candles = [
        _candle(0, 99, 101, 98, 100),
        _candle(1, 100, 106, 94, 101),
    ]
    service, _ = _service(rules_json, candles)

    run = asyncio.run(
        service.run_backtest(
            None,
            bot_id="bot-a",
            wallet_address="wallet-a",
            user_id="user-a",
            interval="15m",
            start_time=BASE_TIME_MS,
            end_time=BASE_TIME_MS + 3 * FIFTEEN_MINUTES_MS,
            initial_capital_usd=10_000,
        )
    )

    trade = run["result_json"]["trades"][0]
    assert trade["close_reason"] == "stop_loss"
    assert trade["pnl_usd"] < 0


def test_backtest_honors_cooldown_and_indicator_conditions() -> None:
    rules_json = _graph_rules(
        nodes=[
            {"id": "condition-open", "kind": "condition", "position": {"x": 120, "y": 80}, "config": {"type": "price_above", "symbol": "BTC", "value": 90}},
            {"id": "action-open", "kind": "action", "position": {"x": 320, "y": 80}, "config": {"type": "open_long", "symbol": "BTC", "size_usd": 100, "leverage": 1}},
            {"id": "condition-rsi", "kind": "condition", "position": {"x": 120, "y": 220}, "config": {"type": "rsi_above", "symbol": "BTC", "timeframe": "15m", "period": 2, "value": 60}},
            {"id": "condition-cooldown", "kind": "condition", "position": {"x": 320, "y": 220}, "config": {"type": "cooldown_elapsed", "symbol": "BTC", "seconds": 1800}},
            {"id": "condition-profit", "kind": "condition", "position": {"x": 520, "y": 220}, "config": {"type": "position_in_profit", "symbol": "BTC"}},
            {"id": "action-close", "kind": "action", "position": {"x": 720, "y": 220}, "config": {"type": "close_position", "symbol": "BTC"}},
        ],
        edges=[
            {"id": "edge-open-1", "source": "builder-entry", "target": "condition-open"},
            {"id": "edge-open-2", "source": "condition-open", "target": "action-open"},
            {"id": "edge-close-1", "source": "builder-entry", "target": "condition-rsi"},
            {"id": "edge-close-2", "source": "condition-rsi", "target": "condition-cooldown"},
            {"id": "edge-close-3", "source": "condition-cooldown", "target": "condition-profit"},
            {"id": "edge-close-4", "source": "condition-profit", "target": "action-close"},
        ],
    )
    candles = [
        _candle(0, 99, 101, 98, 100),
        _candle(1, 100, 106, 100, 105),
        _candle(2, 105, 111, 104, 110),
    ]
    service, _ = _service(rules_json, candles)

    run = asyncio.run(
        service.run_backtest(
            None,
            bot_id="bot-a",
            wallet_address="wallet-a",
            user_id="user-a",
            interval="15m",
            start_time=BASE_TIME_MS,
            end_time=BASE_TIME_MS + 4 * FIFTEEN_MINUTES_MS,
            initial_capital_usd=10_000,
        )
    )

    trigger_events = run["result_json"]["trigger_events"]
    assert len([event for event in trigger_events if event["title"] == "close position"]) == 1
    assert run["trade_count"] == 1


def test_backtest_records_trade_timing_and_realized_equity_exactly() -> None:
    rules_json = _graph_rules(
        nodes=[
            {"id": "condition-open", "kind": "condition", "position": {"x": 120, "y": 80}, "config": {"type": "price_above", "symbol": "BTC", "value": 90}},
            {"id": "action-open", "kind": "action", "position": {"x": 320, "y": 80}, "config": {"type": "open_long", "symbol": "BTC", "size_usd": 100, "leverage": 1}},
            {"id": "condition-close", "kind": "condition", "position": {"x": 120, "y": 220}, "config": {"type": "position_pnl_above", "symbol": "BTC", "value": 20}},
            {"id": "action-close", "kind": "action", "position": {"x": 320, "y": 220}, "config": {"type": "close_position", "symbol": "BTC"}},
        ],
        edges=[
            {"id": "edge-open-1", "source": "builder-entry", "target": "condition-open"},
            {"id": "edge-open-2", "source": "condition-open", "target": "action-open"},
            {"id": "edge-close-1", "source": "builder-entry", "target": "condition-close"},
            {"id": "edge-close-2", "source": "condition-close", "target": "action-close"},
        ],
    )
    candles = [
        _candle(0, 99, 101, 98, 100),
        _candle(1, 100, 131, 100, 130),
    ]
    service, _ = _service(rules_json, candles)

    run = asyncio.run(
        service.run_backtest(
            None,
            bot_id="bot-a",
            wallet_address="wallet-a",
            user_id="user-a",
            interval="15m",
            start_time=BASE_TIME_MS,
            end_time=BASE_TIME_MS + 3 * FIFTEEN_MINUTES_MS,
            initial_capital_usd=10_000,
        )
    )

    trade = run["result_json"]["trades"][0]
    assert trade["entry_price"] == 100.0
    assert trade["exit_price"] == 130.0
    assert trade["pnl_usd"] == 30.0
    assert trade["duration_seconds"] == 900
    assert trade["entry_time"] == service._iso_from_ms(BASE_TIME_MS + FIFTEEN_MINUTES_MS)
    assert trade["exit_time"] == service._iso_from_ms(BASE_TIME_MS + 2 * FIFTEEN_MINUTES_MS)
    assert run["result_json"]["equity_curve"] == [
        {"time": BASE_TIME_MS + FIFTEEN_MINUTES_MS, "equity": 10_000.0, "realized_pnl": 0.0, "unrealized_pnl": 0.0},
        {"time": BASE_TIME_MS + 2 * FIFTEEN_MINUTES_MS, "equity": 10_030.0, "realized_pnl": 30.0, "unrealized_pnl": 0.0},
    ]
    assert run["result_json"]["summary"]["ending_equity"] == 10_030.0


def test_backtest_models_fees_slippage_and_funding() -> None:
    rules_json = _graph_rules(
        nodes=[
            {"id": "condition-open", "kind": "condition", "position": {"x": 120, "y": 80}, "config": {"type": "price_above", "symbol": "BTC", "value": 90}},
            {"id": "action-open", "kind": "action", "position": {"x": 320, "y": 80}, "config": {"type": "open_long", "symbol": "BTC", "size_usd": 100, "leverage": 1}},
            {"id": "condition-close", "kind": "condition", "position": {"x": 120, "y": 220}, "config": {"type": "position_pnl_above", "symbol": "BTC", "value": 20}},
            {"id": "action-close", "kind": "action", "position": {"x": 320, "y": 220}, "config": {"type": "close_position", "symbol": "BTC"}},
        ],
        edges=[
            {"id": "edge-open-1", "source": "builder-entry", "target": "condition-open"},
            {"id": "edge-open-2", "source": "condition-open", "target": "action-open"},
            {"id": "edge-close-1", "source": "builder-entry", "target": "condition-close"},
            {"id": "edge-close-2", "source": "condition-close", "target": "action-close"},
        ],
    )
    candles = [
        _candle(0, 99, 101, 98, 100),
        _candle(1, 100, 131, 100, 130),
    ]
    service, _ = _service(rules_json, candles)

    run = asyncio.run(
        service.run_backtest(
            None,
            bot_id="bot-a",
            wallet_address="wallet-a",
            user_id="user-a",
            interval="15m",
            start_time=BASE_TIME_MS,
            end_time=BASE_TIME_MS + 3 * FIFTEEN_MINUTES_MS,
            initial_capital_usd=10_000,
            assumptions={"fee_bps": 10, "slippage_bps": 50, "funding_bps_per_interval": 10},
        )
    )

    trade = run["result_json"]["trades"][0]
    summary = run["result_json"]["summary"]

    assert run["result_json"]["assumption_config"] == {
        "fee_bps": 10.0,
        "slippage_bps": 50.0,
        "funding_bps_per_interval": 10.0,
    }
    assert trade["entry_price"] == pytest.approx(100.5)
    assert trade["exit_price"] == pytest.approx(129.35)
    assert trade["gross_pnl_usd"] == pytest.approx(28.70646766)
    assert trade["fees_paid_usd"] == pytest.approx(0.22870647)
    assert trade["funding_pnl_usd"] == pytest.approx(-0.12935323)
    assert trade["pnl_usd"] == pytest.approx(28.34840797)
    assert trade["pnl_usd"] < trade["gross_pnl_usd"]
    assert summary["gross_pnl_total"] == pytest.approx(trade["gross_pnl_usd"])
    assert summary["fees_paid_usd"] == pytest.approx(trade["fees_paid_usd"])
    assert summary["funding_pnl_usd"] == pytest.approx(trade["funding_pnl_usd"])
    assert summary["ending_equity"] == pytest.approx(10_028.34840797)
    assert run["result_json"]["equity_curve"][0]["equity"] < 10_000
    assert any("fees" in line.lower() for line in run["result_json"]["assumptions"])
    assert any("slippage" in line.lower() for line in run["result_json"]["assumptions"])
    assert any("funding" in line.lower() for line in run["result_json"]["assumptions"])


def test_backtest_reversal_closes_existing_trade_and_carries_new_open_position() -> None:
    rules_json = _graph_rules(
        nodes=[
            {"id": "condition-open-long", "kind": "condition", "position": {"x": 120, "y": 80}, "config": {"type": "price_above", "symbol": "BTC", "value": 90}},
            {"id": "action-open-long", "kind": "action", "position": {"x": 320, "y": 80}, "config": {"type": "open_long", "symbol": "BTC", "size_usd": 100, "leverage": 1}},
            {"id": "condition-open-short", "kind": "condition", "position": {"x": 120, "y": 220}, "config": {"type": "price_below", "symbol": "BTC", "value": 95}},
            {"id": "action-open-short", "kind": "action", "position": {"x": 320, "y": 220}, "config": {"type": "open_short", "symbol": "BTC", "size_usd": 100, "leverage": 1}},
        ],
        edges=[
            {"id": "edge-open-long-1", "source": "builder-entry", "target": "condition-open-long"},
            {"id": "edge-open-long-2", "source": "condition-open-long", "target": "action-open-long"},
            {"id": "edge-open-short-1", "source": "builder-entry", "target": "condition-open-short"},
            {"id": "edge-open-short-2", "source": "condition-open-short", "target": "action-open-short"},
        ],
    )
    candles = [
        _candle(0, 99, 101, 98, 100),
        _candle(1, 100, 101, 79, 80),
        _candle(2, 80, 82, 74, 75),
    ]
    service, _ = _service(rules_json, candles)

    run = asyncio.run(
        service.run_backtest(
            None,
            bot_id="bot-a",
            wallet_address="wallet-a",
            user_id="user-a",
            interval="15m",
            start_time=BASE_TIME_MS,
            end_time=BASE_TIME_MS + 4 * FIFTEEN_MINUTES_MS,
            initial_capital_usd=10_000,
        )
    )

    closed_trade, open_trade = run["result_json"]["trades"]
    assert closed_trade["status"] == "closed"
    assert closed_trade["side"] == "long"
    assert closed_trade["close_reason"] == "action_reverse"
    assert closed_trade["pnl_usd"] == -20.0
    assert closed_trade["duration_seconds"] == 900
    assert open_trade["status"] == "open"
    assert open_trade["side"] == "short"
    assert open_trade["entry_price"] == 80.0
    assert open_trade["unrealized_pnl"] == 6.25
    assert run["trade_count"] == 1
    assert run["result_json"]["summary"]["realized_pnl"] == -20.0
    assert run["result_json"]["summary"]["unrealized_pnl"] == 6.25
    assert run["result_json"]["summary"]["ending_equity"] == 9_986.25
    assert run["result_json"]["equity_curve"][-1]["equity"] == 9_986.25


def test_backtest_aggregates_multi_symbol_equity_and_price_series() -> None:
    rules_json = _graph_rules(
        nodes=[
            {
                "id": "condition-open",
                "kind": "condition",
                "position": {"x": 120, "y": 80},
                "config": {"type": "price_above", "symbol": MARKET_UNIVERSE_SYMBOL, "value": 90},
            },
            {
                "id": "action-open",
                "kind": "action",
                "position": {"x": 320, "y": 80},
                "config": {"type": "open_long", "symbol": MARKET_UNIVERSE_SYMBOL, "size_usd": 100, "leverage": 1},
            },
        ],
        edges=[
            {"id": "edge-open-1", "source": "builder-entry", "target": "condition-open"},
            {"id": "edge-open-2", "source": "condition-open", "target": "action-open"},
        ],
    )
    tables = _tables(rules_json)
    tables["bot_definitions"][0]["market_scope"] = "Pacifica perpetuals / BTC,ETH"
    supabase = FakeSupabaseRestClient(tables)
    pacifica = FakePacificaClient(
        {
            ("BTC", "15m"): [
                _symbol_candle("BTC", 0, 99, 101, 98, 100),
                _symbol_candle("BTC", 1, 100, 106, 99, 105),
            ],
            ("ETH", "15m"): [
                _symbol_candle("ETH", 0, 199, 201, 198, 200),
                _symbol_candle("ETH", 1, 200, 211, 199, 210),
            ],
        }
    )
    service = BotBacktestService(pacifica_client=pacifica, supabase=supabase)

    run = asyncio.run(
        service.run_backtest(
            None,
            bot_id="bot-a",
            wallet_address="wallet-a",
            user_id="user-a",
            interval="15m",
            start_time=BASE_TIME_MS,
            end_time=BASE_TIME_MS + 3 * FIFTEEN_MINUTES_MS,
            initial_capital_usd=10_000,
        )
    )

    assert run["status"] == "completed"
    assert run["trade_count"] == 0
    assert len(run["result_json"]["trades"]) == 2
    assert {trade["symbol"] for trade in run["result_json"]["trades"]} == {"BTC", "ETH"}
    assert run["result_json"]["summary"]["symbols"] == ["BTC", "ETH"]
    assert run["result_json"]["summary"]["unrealized_pnl"] == 10.0
    assert run["result_json"]["summary"]["ending_equity"] == 10_010.0
    assert run["result_json"]["equity_curve"][-1]["unrealized_pnl"] == 10.0
    assert sorted(run["result_json"]["price_series"]["series_by_symbol"]) == ["BTC", "ETH"]


def test_backtest_returns_failed_run_for_unsupported_actions() -> None:
    rules_json = _graph_rules(
        nodes=[
            {"id": "condition-open", "kind": "condition", "position": {"x": 120, "y": 80}, "config": {"type": "price_above", "symbol": "BTC", "value": 90}},
            {"id": "action-open", "kind": "action", "position": {"x": 320, "y": 80}, "config": {"type": "place_limit_order", "symbol": "BTC", "price": 99, "quantity": 1, "side": "long"}},
        ],
        edges=[
            {"id": "edge-open-1", "source": "builder-entry", "target": "condition-open"},
            {"id": "edge-open-2", "source": "condition-open", "target": "action-open"},
        ],
    )
    candles = [_candle(0, 99, 101, 98, 100)]
    service, supabase = _service(rules_json, candles)

    run = asyncio.run(
        service.run_backtest(
            None,
            bot_id="bot-a",
            wallet_address="wallet-a",
            user_id="user-a",
            interval="15m",
            start_time=BASE_TIME_MS,
            end_time=BASE_TIME_MS + 2 * FIFTEEN_MINUTES_MS,
            initial_capital_usd=10_000,
        )
    )

    assert run["status"] == "failed"
    assert run["result_json"]["preflight_issues"]
    assert run["result_json"]["execution_issues"] == []
    assert run["failure_reason"] == run["result_json"]["preflight_issues"][0]
    assert supabase.tables["bot_backtest_runs"][0]["failure_reason"] == run["failure_reason"]


def test_backtest_runtime_failures_are_reported_as_execution_issues() -> None:
    rules_json = _graph_rules(
        nodes=[
            {"id": "condition-open", "kind": "condition", "position": {"x": 120, "y": 80}, "config": {"type": "price_above", "symbol": "BTC", "value": 90}},
            {"id": "action-open", "kind": "action", "position": {"x": 320, "y": 80}, "config": {"type": "open_long", "symbol": "BTC", "size_usd": 100, "leverage": 1}},
        ],
        edges=[
            {"id": "edge-open-1", "source": "builder-entry", "target": "condition-open"},
            {"id": "edge-open-2", "source": "condition-open", "target": "action-open"},
        ],
    )
    supabase = FakeSupabaseRestClient(_tables(rules_json))
    service = BotBacktestService(pacifica_client=FailingPacificaClient({}), supabase=supabase)

    run = asyncio.run(
        service.run_backtest(
            None,
            bot_id="bot-a",
            wallet_address="wallet-a",
            user_id="user-a",
            interval="15m",
            start_time=BASE_TIME_MS,
            end_time=BASE_TIME_MS + 2 * FIFTEEN_MINUTES_MS,
            initial_capital_usd=10_000,
        )
    )

    assert run["status"] == "failed"
    assert run["result_json"]["preflight_issues"] == []
    assert run["result_json"]["execution_issues"]
    assert run["failure_reason"] == run["result_json"]["execution_issues"][0]


def test_backtest_allows_ranges_longer_than_two_thousand_bars() -> None:
    rules_json = _graph_rules(
        nodes=[
            {"id": "condition-open", "kind": "condition", "position": {"x": 120, "y": 80}, "config": {"type": "price_above", "symbol": "BTC", "value": 90}},
            {"id": "action-open", "kind": "action", "position": {"x": 320, "y": 80}, "config": {"type": "open_long", "symbol": "BTC", "size_usd": 100, "leverage": 1}},
        ],
        edges=[
            {"id": "edge-open-1", "source": "builder-entry", "target": "condition-open"},
            {"id": "edge-open-2", "source": "condition-open", "target": "action-open"},
        ],
    )
    candles = [_candle(index, 99, 101, 98, 100 + (index % 5)) for index in range(2_005)]
    service, _ = _service(rules_json, candles)

    run = asyncio.run(
        service.run_backtest(
            None,
            bot_id="bot-a",
            wallet_address="wallet-a",
            user_id="user-a",
            interval="15m",
            start_time=BASE_TIME_MS,
            end_time=BASE_TIME_MS + 2_006 * FIFTEEN_MINUTES_MS,
            initial_capital_usd=10_000,
        )
    )

    assert run["status"] == "completed"
    assert len(run["result_json"]["equity_curve"]) == 2_005
    assert run["result_json"].get("preflight_issues") in (None, [])


def test_backtest_skips_symbols_without_history_when_others_are_available() -> None:
    rules_json = _graph_rules(
        nodes=[
            {
                "id": "condition-open",
                "kind": "condition",
                "position": {"x": 120, "y": 80},
                "config": {"type": "price_above", "symbol": MARKET_UNIVERSE_SYMBOL, "value": 90},
            },
            {
                "id": "action-open",
                "kind": "action",
                "position": {"x": 320, "y": 80},
                "config": {"type": "open_long", "symbol": MARKET_UNIVERSE_SYMBOL, "size_usd": 100, "leverage": 1},
            },
        ],
        edges=[
            {"id": "edge-open-1", "source": "builder-entry", "target": "condition-open"},
            {"id": "edge-open-2", "source": "condition-open", "target": "action-open"},
        ],
    )
    tables = _tables(rules_json)
    tables["bot_definitions"][0]["market_scope"] = "Pacifica perpetuals / BTC,COPPER"
    supabase = FakeSupabaseRestClient(tables)
    pacifica = FakePacificaClient(
        {
            ("BTC", "15m"): [_candle(0, 99, 101, 98, 100), _candle(1, 100, 104, 99, 103)],
            ("COPPER", "15m"): [],
        }
    )
    service = BotBacktestService(pacifica_client=pacifica, supabase=supabase)

    run = asyncio.run(
        service.run_backtest(
            None,
            bot_id="bot-a",
            wallet_address="wallet-a",
            user_id="user-a",
            interval="15m",
            start_time=BASE_TIME_MS,
            end_time=BASE_TIME_MS + 3 * FIFTEEN_MINUTES_MS,
            initial_capital_usd=10_000,
        )
    )

    assert run["status"] == "completed"
    assert run["result_json"]["summary"]["symbols"] == ["BTC"]
    assert run["result_json"]["summary"]["requested_symbols"] == ["BTC", "COPPER"]
    assert run["result_json"]["summary"]["skipped_symbols"] == ["COPPER"]
    assert any("skipped" in line.lower() for line in run["result_json"]["assumptions"])


def test_backtest_runs_are_scoped_to_wallet_history_and_detail() -> None:
    rules_json = _graph_rules(
        nodes=[
            {"id": "condition-open", "kind": "condition", "position": {"x": 120, "y": 80}, "config": {"type": "price_above", "symbol": "BTC", "value": 90}},
            {"id": "action-open", "kind": "action", "position": {"x": 320, "y": 80}, "config": {"type": "open_long", "symbol": "BTC", "size_usd": 100, "leverage": 1}},
        ],
        edges=[
            {"id": "edge-open-1", "source": "builder-entry", "target": "condition-open"},
            {"id": "edge-open-2", "source": "condition-open", "target": "action-open"},
        ],
    )
    candles = [_candle(0, 99, 101, 98, 100)]
    tables = {
        "bot_definitions": [
            *_tables(rules_json, wallet_address="wallet-a", user_id="user-a", bot_id="bot-a")["bot_definitions"],
            *_tables(rules_json, wallet_address="wallet-b", user_id="user-b", bot_id="bot-b")["bot_definitions"],
        ],
        "bot_backtest_runs": [],
    }
    supabase = FakeSupabaseRestClient(tables)
    pacifica = FakePacificaClient({("BTC", "15m"): candles})
    service = BotBacktestService(pacifica_client=pacifica, supabase=supabase)

    run_a = asyncio.run(
        service.run_backtest(
            None,
            bot_id="bot-a",
            wallet_address="wallet-a",
            user_id="user-a",
            interval="15m",
            start_time=BASE_TIME_MS,
            end_time=BASE_TIME_MS + 2 * FIFTEEN_MINUTES_MS,
            initial_capital_usd=10_000,
        )
    )
    asyncio.run(
        service.run_backtest(
            None,
            bot_id="bot-b",
            wallet_address="wallet-b",
            user_id="user-b",
            interval="15m",
            start_time=BASE_TIME_MS,
            end_time=BASE_TIME_MS + 2 * FIFTEEN_MINUTES_MS,
            initial_capital_usd=10_000,
        )
    )

    wallet_a_runs = service.list_runs(None, wallet_address="wallet-a", user_id="user-a")
    assert len(wallet_a_runs) == 1
    assert wallet_a_runs[0]["id"] == run_a["id"]

    detail = service.get_run(None, run_id=run_a["id"], wallet_address="wallet-a", user_id="user-a")
    assert detail["id"] == run_a["id"]

    with pytest.raises(ValueError, match="Backtest run not found"):
        service.get_run(None, run_id=run_a["id"], wallet_address="wallet-b", user_id="user-b")


def test_list_runs_returns_full_history_without_truncation() -> None:
    rules_json = _graph_rules(
        nodes=[
            {"id": "condition-open", "kind": "condition", "position": {"x": 120, "y": 80}, "config": {"type": "price_above", "symbol": "BTC", "value": 90}},
            {"id": "action-open", "kind": "action", "position": {"x": 320, "y": 80}, "config": {"type": "open_long", "symbol": "BTC", "size_usd": 100, "leverage": 1}},
        ],
        edges=[
            {"id": "edge-open-1", "source": "builder-entry", "target": "condition-open"},
            {"id": "edge-open-2", "source": "condition-open", "target": "action-open"},
        ],
    )
    candles = [_candle(0, 99, 101, 98, 100)]
    service, supabase = _service(rules_json, candles)

    for index in range(105):
        supabase.insert(
            "bot_backtest_runs",
            {
                "id": f"run-{index}",
                "bot_definition_id": "bot-a",
                "user_id": "user-a",
                "wallet_address": "wallet-a",
                "bot_name_snapshot": "Backtest Bot",
                "rules_snapshot_json": rules_json,
                "interval": "15m",
                "start_time": BASE_TIME_MS,
                "end_time": BASE_TIME_MS + 2 * FIFTEEN_MINUTES_MS,
                "initial_capital_usd": 10_000,
                "execution_model": "candle_close_v1",
                "pnl_total": float(index),
                "pnl_total_pct": float(index) / 100.0,
                "max_drawdown_pct": 1.0,
                "win_rate": 50.0,
                "trade_count": 1,
                "status": "completed",
                "result_json": {"summary": {"symbols": ["BTC"]}},
                "created_at": f"2026-03-16T00:00:{index % 60:02d}+00:00",
                "completed_at": f"2026-03-16T00:01:{index % 60:02d}+00:00",
                "updated_at": f"2026-03-16T00:01:{index % 60:02d}+00:00",
            },
        )

    runs = service.list_runs(None, wallet_address="wallet-a", user_id="user-a")

    assert len(runs) == 105
