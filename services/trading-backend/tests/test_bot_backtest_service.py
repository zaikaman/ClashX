from __future__ import annotations

import asyncio
from copy import deepcopy
from typing import Any

import pytest

from src.services.bot_backtest_service import BotBacktestService


BASE_TIME_MS = 1_710_000_000_000
FIFTEEN_MINUTES_MS = 900_000


def _candle(offset: int, open_price: float, high_price: float, low_price: float, close_price: float, volume: float = 1000.0) -> dict[str, Any]:
    open_time = BASE_TIME_MS + offset * FIFTEEN_MINUTES_MS
    close_time = open_time + FIFTEEN_MINUTES_MS
    return {
        "open_time": open_time,
        "close_time": close_time,
        "symbol": "BTC",
        "interval": "15m",
        "open": open_price,
        "high": high_price,
        "low": low_price,
        "close": close_price,
        "volume": volume,
        "trade_count": 10,
    }


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
    ) -> list[dict[str, Any]]:
        del upsert, on_conflict
        items = payload if isinstance(payload, list) else [payload]
        stored = [deepcopy(item) for item in items]
        self.tables.setdefault(table, []).extend(stored)
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
    assert run["result_json"]["trades"][0]["pnl_usd"] < 0


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
    service, _ = _service(rules_json, candles)

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
