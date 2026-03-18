from __future__ import annotations

import asyncio
from copy import deepcopy
from typing import Any

from src.services.bot_copy_engine import BotCopyEngine
from src.services.bot_leaderboard_engine import BotLeaderboardEngine
from src.services.bot_performance_service import BotPerformanceService


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
            rows.sort(key=lambda row: row.get(field), reverse=direction.lower() == "desc")
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

    def delete(self, table: str, *, filters: dict[str, Any]) -> None:
        self.tables[table] = [row for row in self.tables.get(table, []) if not self._matches(row, filters)]

    @staticmethod
    def _matches(row: dict[str, Any], filters: dict[str, Any] | None) -> bool:
        if not filters:
            return True
        for key, expected in filters.items():
            value = row.get(key)
            if isinstance(expected, tuple):
                operator, operand = expected
                if operator == "in":
                    if value not in operand:
                        return False
                    continue
                if operator == "lte":
                    if value is None or value > operand:
                        return False
                    continue
                if operator == "gt":
                    if value is None or value <= operand:
                        return False
                    continue
                if operator != "eq" or value != operand:
                    return False
                continue
            if value != expected:
                return False
        return True


class FakePacificaClient:
    def __init__(self) -> None:
        self.order_history: dict[int, list[dict[str, Any]]] = {
            11: [
                {
                    "history_id": 101,
                    "order_id": 11,
                    "symbol": "BTC",
                    "side": "bid",
                    "price": 100.0,
                    "amount": 1.0,
                    "reduce_only": False,
                    "event_type": "fulfill_market",
                    "created_at": "2026-03-17T00:00:00+00:00",
                }
            ],
            22: [
                {
                    "history_id": 202,
                    "order_id": 22,
                    "symbol": "ETH",
                    "side": "bid",
                    "price": 50.0,
                    "amount": 2.0,
                    "reduce_only": False,
                    "event_type": "fulfill_market",
                    "created_at": "2026-03-17T00:01:00+00:00",
                }
            ],
        }
        self.live_positions: dict[str, list[dict[str, Any]]] = {}
        self.position_history: dict[str, list[dict[str, Any]]] = {}

    async def get_order_history_by_id(self, order_id: int) -> list[dict[str, Any]]:
        return deepcopy(self.order_history.get(order_id, []))

    async def get_markets(self) -> list[dict[str, Any]]:
        return [
            {"symbol": "BTC", "mark_price": 110.0},
            {"symbol": "ETH", "mark_price": 40.0},
        ]

    async def get_positions(self, wallet_address: str) -> list[dict[str, Any]]:
        return deepcopy(self.live_positions.get(wallet_address, []))

    async def get_position_history(self, wallet_address: str, *, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        del limit, offset
        return deepcopy(self.position_history.get(wallet_address, []))


def _tables() -> dict[str, list[dict[str, Any]]]:
    return {
        "bot_definitions": [
            {
                "id": "bot-a",
                "user_id": "user-1",
                "wallet_address": "shared-wallet",
                "name": "BTC Bot",
                "description": "Bot A",
                "visibility": "public",
                "market_scope": "Pacifica perpetuals",
                "strategy_type": "rules",
                "authoring_mode": "visual",
                "rules_version": 1,
                "rules_json": {},
                "created_at": "2026-03-17T00:00:00+00:00",
                "updated_at": "2026-03-17T00:00:00+00:00",
            },
            {
                "id": "bot-b",
                "user_id": "user-1",
                "wallet_address": "shared-wallet",
                "name": "ETH Bot",
                "description": "Bot B",
                "visibility": "public",
                "market_scope": "Pacifica perpetuals",
                "strategy_type": "rules",
                "authoring_mode": "visual",
                "rules_version": 1,
                "rules_json": {},
                "created_at": "2026-03-17T00:00:00+00:00",
                "updated_at": "2026-03-17T00:00:00+00:00",
            },
        ],
        "bot_runtimes": [
            {
                "id": "runtime-a",
                "bot_definition_id": "bot-a",
                "user_id": "user-1",
                "wallet_address": "shared-wallet",
                "status": "active",
                "mode": "live",
                "risk_policy_json": {"_runtime_state": {"drawdown_pct": 3.0}},
                "deployed_at": "2026-03-17T00:00:00+00:00",
                "stopped_at": None,
                "updated_at": "2026-03-17T00:00:00+00:00",
            },
            {
                "id": "runtime-b",
                "bot_definition_id": "bot-b",
                "user_id": "user-1",
                "wallet_address": "shared-wallet",
                "status": "active",
                "mode": "live",
                "risk_policy_json": {"_runtime_state": {"drawdown_pct": 1.5}},
                "deployed_at": "2026-03-17T00:00:00+00:00",
                "stopped_at": None,
                "updated_at": "2026-03-17T00:00:00+00:00",
            },
        ],
        "bot_execution_events": [
            {
                "id": "event-a",
                "runtime_id": "runtime-a",
                "event_type": "action.executed",
                "decision_summary": "btc fill",
                "request_payload": {},
                "result_payload": {"response": {"order_id": 11}},
                "status": "success",
                "error_reason": None,
                "created_at": "2026-03-17T00:00:00+00:00",
            },
            {
                "id": "event-b",
                "runtime_id": "runtime-b",
                "event_type": "action.executed",
                "decision_summary": "eth fill",
                "request_payload": {},
                "result_payload": {"response": {"order_id": 22}},
                "status": "success",
                "error_reason": None,
                "created_at": "2026-03-17T00:01:00+00:00",
            },
        ],
        "bot_leaderboard_snapshots": [],
        "audit_events": [],
        "users": [],
    }


async def _noop_publish(*args: Any, **kwargs: Any) -> None:
    del args, kwargs


def test_runtime_performance_is_scoped_to_each_runtime() -> None:
    fake_supabase = FakeSupabaseRestClient(_tables())
    fake_pacifica = FakePacificaClient()
    fake_pacifica.live_positions["shared-wallet"] = [
        {
            "symbol": "BTC",
            "side": "bid",
            "amount": 1.0,
            "entry_price": 100.0,
            "mark_price": 110.0,
        },
        {
            "symbol": "ETH",
            "side": "bid",
            "amount": 2.0,
            "entry_price": 50.0,
            "mark_price": 40.0,
        },
    ]
    service = BotPerformanceService(pacifica_client=fake_pacifica, supabase=fake_supabase)

    runtime_a = fake_supabase.maybe_one("bot_runtimes", filters={"id": "runtime-a"})
    runtime_b = fake_supabase.maybe_one("bot_runtimes", filters={"id": "runtime-b"})

    performance_a = asyncio.run(service.calculate_runtime_performance(runtime_a))
    performance_b = asyncio.run(service.calculate_runtime_performance(runtime_b))

    assert performance_a["positions"][0]["symbol"] == "BTC"
    assert performance_a["pnl_total"] == 10.0
    assert performance_b["positions"][0]["symbol"] == "ETH"
    assert performance_b["pnl_total"] == -20.0


def test_runtime_performance_falls_back_when_order_history_fill_amounts_are_zero() -> None:
    fake_supabase = FakeSupabaseRestClient(
        {
            "bot_execution_events": [
                {
                    "id": "event-a",
                    "runtime_id": "runtime-a",
                    "event_type": "action.executed",
                    "decision_summary": "btc fill",
                    "request_payload": {"type": "open_long", "symbol": "BTC", "size_usd": 100},
                    "result_payload": {
                        "response": {"order_id": 11},
                        "execution_meta": {
                            "symbol": "BTC",
                            "side": "bid",
                            "amount": 1.0,
                            "reduce_only": False,
                            "reference_price": 100.0,
                        },
                    },
                    "status": "success",
                    "error_reason": None,
                    "created_at": "2026-03-17T00:00:00+00:00",
                }
            ]
        }
    )
    fake_pacifica = FakePacificaClient()
    fake_pacifica.live_positions["shared-wallet"] = [
        {
            "symbol": "BTC",
            "side": "bid",
            "amount": 1.0,
            "entry_price": 100.0,
            "mark_price": 110.0,
        }
    ]
    fake_pacifica.order_history[11] = [
        {
            "history_id": 101,
            "order_id": 11,
            "symbol": "BTC",
            "side": "bid",
            "price": 101.0,
            "amount": 0.0,
            "reduce_only": False,
            "event_type": "fulfill_market",
            "created_at": "2026-03-17T00:00:00+00:00",
        }
    ]
    service = BotPerformanceService(pacifica_client=fake_pacifica, supabase=fake_supabase)

    performance = asyncio.run(service.calculate_runtime_performance({"id": "runtime-a", "wallet_address": "shared-wallet"}))

    assert performance["positions"][0]["symbol"] == "BTC"
    assert performance["positions"][0]["amount"] == 1.0
    assert performance["positions"][0]["entry_price"] == 100.0
    assert performance["pnl_total"] == 10.0


def test_public_bot_leaderboard_ranks_runtime_specific_results(monkeypatch: Any) -> None:
    fake_supabase = FakeSupabaseRestClient(_tables())
    fake_pacifica = FakePacificaClient()
    fake_pacifica.live_positions["shared-wallet"] = [
        {
            "symbol": "BTC",
            "side": "bid",
            "amount": 1.0,
            "entry_price": 100.0,
            "mark_price": 110.0,
        },
        {
            "symbol": "ETH",
            "side": "bid",
            "amount": 2.0,
            "entry_price": 50.0,
            "mark_price": 40.0,
        },
    ]
    engine = BotLeaderboardEngine(pacifica_client=fake_pacifica)
    engine.supabase = fake_supabase
    engine.performance_service = BotPerformanceService(pacifica_client=fake_pacifica, supabase=fake_supabase)
    monkeypatch.setattr("src.services.bot_leaderboard_engine.broadcaster.publish", _noop_publish)

    rows = asyncio.run(engine.refresh_public_leaderboard(None, limit=10))

    assert [row["runtime_id"] for row in rows] == ["runtime-a", "runtime-b"]
    assert rows[0]["pnl_total"] == 10.0
    assert rows[1]["pnl_total"] == -20.0


def test_mirror_preview_uses_runtime_positions_not_wallet_positions() -> None:
    fake_supabase = FakeSupabaseRestClient(_tables())
    fake_pacifica = FakePacificaClient()
    fake_pacifica.live_positions["shared-wallet"] = [
        {
            "symbol": "BTC",
            "side": "bid",
            "amount": 1.0,
            "entry_price": 100.0,
            "mark_price": 110.0,
        },
        {
            "symbol": "ETH",
            "side": "bid",
            "amount": 9.0,
            "entry_price": 50.0,
            "mark_price": 60.0,
        }
    ]
    engine = BotLeaderboardEngine(pacifica_client=fake_pacifica)
    engine.supabase = fake_supabase
    engine.performance_service = BotPerformanceService(pacifica_client=fake_pacifica, supabase=fake_supabase)
    bot_copy_engine = BotCopyEngine(leaderboard_engine=engine, pacifica_client=fake_pacifica)
    bot_copy_engine.supabase = fake_supabase
    bot_copy_engine.performance_service = BotPerformanceService(pacifica_client=fake_pacifica, supabase=fake_supabase)

    preview = asyncio.run(
        bot_copy_engine.preview_mirror(
            None,
            runtime_id="runtime-a",
            follower_wallet_address="follower-wallet",
            scale_bps=10_000,
        )
    )

    assert len(preview["mirrored_positions"]) == 1
    assert preview["mirrored_positions"][0]["symbol"] == "BTC"
    assert preview["mirrored_positions"][0]["size_source"] == 1.0


def test_runtime_performance_uses_live_positions_to_drop_manually_closed_exposure() -> None:
    fake_supabase = FakeSupabaseRestClient(_tables())
    fake_pacifica = FakePacificaClient()
    fake_pacifica.live_positions["shared-wallet"] = []
    service = BotPerformanceService(pacifica_client=fake_pacifica, supabase=fake_supabase)

    runtime_a = fake_supabase.maybe_one("bot_runtimes", filters={"id": "runtime-a"})
    performance_a = asyncio.run(service.calculate_runtime_performance(runtime_a))

    assert performance_a["positions"] == []
    assert performance_a["pnl_unrealized"] == 0.0
    assert performance_a["pnl_total"] == 0.0


def test_runtime_performance_attributes_manual_close_realized_pnl_to_bot() -> None:
    fake_supabase = FakeSupabaseRestClient(_tables())
    fake_pacifica = FakePacificaClient()
    fake_pacifica.live_positions["shared-wallet"] = []
    fake_pacifica.position_history["shared-wallet"] = [
        {
            "symbol": "BTC",
            "amount": 1.0,
            "price": 120.0,
            "entry_price": 100.0,
            "fee": 0.0,
            "pnl": 20.0,
            "event_type": "open_long",
            "created_at": "2026-03-17T00:00:00+00:00",
        },
        {
            "symbol": "BTC",
            "amount": 1.0,
            "price": 120.0,
            "entry_price": 100.0,
            "fee": 0.0,
            "pnl": 20.0,
            "event_type": "close_long",
            "created_at": "2026-03-17T00:05:00+00:00",
        },
    ]
    service = BotPerformanceService(pacifica_client=fake_pacifica, supabase=fake_supabase)

    runtime_a = fake_supabase.maybe_one("bot_runtimes", filters={"id": "runtime-a"})
    performance_a = asyncio.run(service.calculate_runtime_performance(runtime_a))

    assert performance_a["positions"] == []
    assert performance_a["pnl_unrealized"] == 0.0
    assert performance_a["pnl_realized"] == 20.0
    assert performance_a["pnl_total"] == 20.0
    assert performance_a["win_streak"] == 1
    assert len(fake_supabase.tables["bot_trade_lots"]) == 1
    assert fake_supabase.tables["bot_trade_lots"][0]["quantity_remaining"] == 0.0
    assert len(fake_supabase.tables["bot_trade_closures"]) == 1
    assert fake_supabase.tables["bot_trade_closures"][0]["source"] == "manual"
    assert fake_supabase.tables["bot_trade_sync_state"][0]["runtime_id"] == "runtime-a"
