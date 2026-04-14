from __future__ import annotations

import asyncio
from copy import deepcopy
from typing import Any

from src.services.bot_copy_engine import BotCopyEngine
from src.services.bot_leaderboard_engine import BotLeaderboardEngine
from src.services.bot_performance_service import BotPerformanceService
from src.services.supabase_rest import SupabaseRestError


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
        items = payload if isinstance(payload, list) else [payload]
        conflict_columns = self._conflict_columns(table, items, on_conflict)
        table_rows = self.tables.setdefault(table, [])
        stored = [deepcopy(item) for item in items]

        if upsert and conflict_columns:
            for item in stored:
                key = self._conflict_key(item, conflict_columns)
                matched_index = next(
                    (index for index, row in enumerate(table_rows) if self._conflict_key(row, conflict_columns) == key),
                    None,
                )
                if matched_index is None:
                    table_rows.append(item)
                    continue
                table_rows[matched_index] = item
            return [deepcopy(item) for item in stored]

        if conflict_columns:
            existing_keys = {self._conflict_key(row, conflict_columns) for row in table_rows}
            payload_keys: set[tuple[Any, ...]] = set()
            for item in stored:
                key = self._conflict_key(item, conflict_columns)
                if key in existing_keys or key in payload_keys:
                    raise SupabaseRestError(
                        f'duplicate key value violates unique constraint "{table}_pkey"',
                        status_code=409,
                    )
                payload_keys.add(key)

        table_rows.extend(stored)
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

    @staticmethod
    def _conflict_columns(
        table: str,
        items: list[dict[str, Any]],
        on_conflict: str | None,
    ) -> tuple[str, ...] | None:
        if on_conflict:
            return tuple(part.strip() for part in on_conflict.split(",") if part.strip())
        if table == "bot_trade_sync_state":
            return ("runtime_id",)
        if any("id" in item for item in items):
            return ("id",)
        return None

    @staticmethod
    def _conflict_key(item: dict[str, Any], columns: tuple[str, ...]) -> tuple[Any, ...]:
        return tuple(item.get(column) for column in columns)


class NoDeleteSupabaseRestClient(FakeSupabaseRestClient):
    def delete(self, table: str, *, filters: dict[str, Any]) -> None:
        del table, filters


class RuntimeFkSupabaseRestClient(FakeSupabaseRestClient):
    def insert(
        self,
        table: str,
        payload: dict[str, Any] | list[dict[str, Any]],
        *,
        upsert: bool = False,
        on_conflict: str | None = None,
    ) -> list[dict[str, Any]]:
        if table in {"bot_trade_lots", "bot_trade_closures", "bot_trade_sync_state"}:
            items = payload if isinstance(payload, list) else [payload]
            runtime_ids = {str(item.get("runtime_id") or "") for item in items}
            known_runtime_ids = {str(row.get("id") or "") for row in self.tables.get("bot_runtimes", [])}
            if any(runtime_id and runtime_id not in known_runtime_ids for runtime_id in runtime_ids):
                raise SupabaseRestError(
                    'insert or update on table "bot_trade_sync_state" violates foreign key constraint "bot_trade_sync_state_runtime_id_fkey"',
                    status_code=409,
                )
        return super().insert(table, payload, upsert=upsert, on_conflict=on_conflict)


class RetryableLedgerCacheSupabaseRestClient(FakeSupabaseRestClient):
    def select(
        self,
        table: str,
        *,
        columns: str = "*",
        filters: dict[str, Any] | None = None,
        order: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        if table in {"bot_trade_lots", "bot_trade_closures"}:
            raise SupabaseRestError("temporary ledger cache outage", status_code=500)
        return super().select(table, columns=columns, filters=filters, order=order, limit=limit)

    def maybe_one(
        self,
        table: str,
        *,
        columns: str = "*",
        filters: dict[str, Any] | None = None,
        order: str | None = None,
    ) -> dict[str, Any] | None:
        if table == "bot_trade_sync_state":
            raise SupabaseRestError("temporary ledger cache outage", status_code=500)
        return super().maybe_one(table, columns=columns, filters=filters, order=order)

    def insert(
        self,
        table: str,
        payload: dict[str, Any] | list[dict[str, Any]],
        *,
        upsert: bool = False,
        on_conflict: str | None = None,
    ) -> list[dict[str, Any]]:
        if table in {"bot_trade_lots", "bot_trade_closures", "bot_trade_sync_state"}:
            raise SupabaseRestError("temporary ledger cache outage", status_code=500)
        return super().insert(table, payload, upsert=upsert, on_conflict=on_conflict)

    def delete(self, table: str, *, filters: dict[str, Any]) -> None:
        if table in {"bot_trade_lots", "bot_trade_closures", "bot_trade_sync_state"}:
            raise SupabaseRestError("temporary ledger cache outage", status_code=500)
        super().delete(table, filters=filters)


class FakePacificaClient:
    def __init__(self) -> None:
        self.order_history_requests: list[int] = []
        self.position_history_requests: list[tuple[str, int, int]] = []
        self.wallet_order_history_requests: list[tuple[str, int, int]] = []
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
        self.wallet_order_history: dict[str, list[dict[str, Any]]] = {}

    async def get_order_history_by_id(self, order_id: int) -> list[dict[str, Any]]:
        self.order_history_requests.append(order_id)
        return deepcopy(self.order_history.get(order_id, []))

    async def get_markets(self) -> list[dict[str, Any]]:
        return [
            {"symbol": "BTC", "mark_price": 110.0},
            {"symbol": "ETH", "mark_price": 40.0},
        ]

    async def get_positions(self, wallet_address: str, *, price_lookup: dict[str, float] | None = None) -> list[dict[str, Any]]:
        del price_lookup
        return deepcopy(self.live_positions.get(wallet_address, []))

    async def get_position_history(self, wallet_address: str, *, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        self.position_history_requests.append((wallet_address, limit, offset))
        rows = self.position_history.get(wallet_address, [])
        return deepcopy(rows[offset : offset + limit])

    async def get_order_history(self, wallet_address: str, *, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        self.wallet_order_history_requests.append((wallet_address, limit, offset))
        rows = self.wallet_order_history.get(wallet_address, [])
        return deepcopy(rows[offset : offset + limit])


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
    assert performance_a["pnl_total_pct"] == 5.0
    assert performance_b["positions"][0]["symbol"] == "ETH"
    assert performance_b["pnl_total"] == -20.0
    assert performance_b["pnl_total_pct"] == -10.0


def test_batch_runtime_performance_map_scopes_results_to_each_runtime() -> None:
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

    runtimes = fake_supabase.select("bot_runtimes", filters={"wallet_address": "shared-wallet"})
    performance_by_runtime = asyncio.run(service.calculate_runtimes_performance_map(runtimes))

    assert performance_by_runtime["runtime-a"]["positions"][0]["symbol"] == "BTC"
    assert performance_by_runtime["runtime-a"]["pnl_total"] == 10.0
    assert performance_by_runtime["runtime-b"]["positions"][0]["symbol"] == "ETH"
    assert performance_by_runtime["runtime-b"]["pnl_total"] == -20.0
    assert fake_pacifica.position_history_requests[0] == ("shared-wallet", 200, 0)


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
    assert performance["pnl_total_pct"] == 5.0


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


def test_public_bot_leaderboard_groups_performance_refresh_by_wallet(monkeypatch: Any) -> None:
    fake_supabase = FakeSupabaseRestClient(_tables())
    fake_supabase.tables["bot_definitions"].append(
        {
            "id": "bot-c",
            "user_id": "user-c",
            "wallet_address": "other-wallet",
            "name": "Gamma",
            "description": "",
            "visibility": "public",
            "market_scope": "Pacifica perpetuals",
            "strategy_type": "rules",
            "authoring_mode": "visual",
            "rules_version": 1,
            "rules_json": {},
            "created_at": "2026-03-16T00:00:00+00:00",
            "updated_at": "2026-03-16T00:00:00+00:00",
        }
    )
    fake_supabase.tables["bot_runtimes"].append(
        {
            "id": "runtime-c",
            "bot_definition_id": "bot-c",
            "user_id": "user-c",
            "wallet_address": "other-wallet",
            "status": "active",
            "mode": "live",
            "risk_policy_json": {"_runtime_state": {}},
            "deployed_at": "2026-03-16T00:00:00+00:00",
            "stopped_at": None,
            "updated_at": "2026-03-16T00:00:00+00:00",
        }
    )
    engine = BotLeaderboardEngine()
    engine.supabase = fake_supabase

    class _StubPerformanceService:
        def __init__(self) -> None:
            self.group_calls: list[list[str]] = []

        async def calculate_runtimes_performance_map(self, runtimes: list[dict[str, Any]], **_: Any) -> dict[str, dict[str, Any]]:
            self.group_calls.append([str(runtime["id"]) for runtime in runtimes])
            return {
                str(runtime["id"]): {
                    "pnl_total": 100.0 - index,
                    "pnl_unrealized": float(index),
                    "win_streak": 3 - index,
                }
                for index, runtime in enumerate(runtimes)
            }

        async def calculate_runtime_performance(self, runtime: dict[str, Any], **_: Any) -> dict[str, Any]:
            raise AssertionError(f"per-runtime refresh should not be used for {runtime['id']}")

    stub_performance = _StubPerformanceService()
    engine.performance_service = stub_performance  # type: ignore[assignment]
    monkeypatch.setattr("src.services.bot_leaderboard_engine.broadcaster.publish", _noop_publish)

    rows = asyncio.run(engine.refresh_public_leaderboard(None, limit=10))

    assert sorted(sorted(group) for group in stub_performance.group_calls) == [["runtime-a", "runtime-b"], ["runtime-c"]]
    assert {row["runtime_id"] for row in rows} == {"runtime-a", "runtime-b", "runtime-c"}


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
    assert performance_a["pnl_total_pct"] == 0.0


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
    assert performance_a["pnl_total_pct"] == 10.0
    assert performance_a["win_streak"] == 1
    assert len(fake_supabase.tables["bot_trade_lots"]) == 1
    assert fake_supabase.tables["bot_trade_lots"][0]["quantity_remaining"] == 0.0
    assert len(fake_supabase.tables["bot_trade_closures"]) == 1
    assert fake_supabase.tables["bot_trade_closures"][0]["source"] == "manual"
    assert fake_supabase.tables["bot_trade_sync_state"][0]["runtime_id"] == "runtime-a"


def test_runtime_performance_keeps_same_symbol_wallet_closes_scoped_to_the_correct_bot() -> None:
    fake_supabase = FakeSupabaseRestClient(_tables())
    fake_supabase.tables["bot_execution_events"] = [
        {
            "id": "event-a-open",
            "runtime_id": "runtime-a",
            "event_type": "action.executed",
            "decision_summary": "btc open a",
            "request_payload": {"type": "open_long", "symbol": "BTC"},
            "result_payload": {
                "execution_meta": {
                    "symbol": "BTC",
                    "side": "bid",
                    "amount": 1.0,
                    "reduce_only": False,
                    "reference_price": 100.0,
                }
            },
            "status": "success",
            "error_reason": None,
            "created_at": "2026-03-17T00:00:00+00:00",
        },
        {
            "id": "event-b-open",
            "runtime_id": "runtime-b",
            "event_type": "action.executed",
            "decision_summary": "btc open b",
            "request_payload": {"type": "open_long", "symbol": "BTC"},
            "result_payload": {
                "execution_meta": {
                    "symbol": "BTC",
                    "side": "bid",
                    "amount": 1.0,
                    "reduce_only": False,
                    "reference_price": 110.0,
                }
            },
            "status": "success",
            "error_reason": None,
            "created_at": "2026-03-17T00:02:00+00:00",
        },
    ]
    fake_pacifica = FakePacificaClient()
    fake_pacifica.live_positions["shared-wallet"] = [
        {
            "symbol": "BTC",
            "side": "bid",
            "amount": 1.0,
            "entry_price": 110.0,
            "mark_price": 120.0,
        }
    ]
    fake_pacifica.position_history["shared-wallet"] = [
        {
            "history_id": 1,
            "symbol": "BTC",
            "amount": 1.0,
            "price": 100.0,
            "entry_price": 100.0,
            "fee": 0.0,
            "pnl": 0.0,
            "event_type": "open_long",
            "created_at": "2026-03-17T00:00:00+00:00",
        },
        {
            "history_id": 2,
            "symbol": "BTC",
            "amount": 1.0,
            "price": 110.0,
            "entry_price": 110.0,
            "fee": 0.0,
            "pnl": 0.0,
            "event_type": "open_long",
            "created_at": "2026-03-17T00:02:00+00:00",
        },
        {
            "history_id": 3,
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
    runtime_b = fake_supabase.maybe_one("bot_runtimes", filters={"id": "runtime-b"})

    performance_a = asyncio.run(service.calculate_runtime_performance(runtime_a))
    performance_b = asyncio.run(service.calculate_runtime_performance(runtime_b))

    assert performance_a["positions"] == []
    assert performance_a["pnl_realized"] == 20.0
    assert performance_a["win_streak"] == 1
    assert performance_b["pnl_realized"] == 0.0
    assert performance_b["pnl_unrealized"] == 10.0
    assert performance_b["win_streak"] == 0
    assert performance_b["positions"][0]["symbol"] == "BTC"
    assert performance_b["positions"][0]["entry_price"] == 110.0
    assert performance_b["positions"][0]["mark_price"] == 120.0
    assert performance_b["positions"][0]["unrealized_pnl"] == 10.0


def test_runtime_performance_realigns_single_live_owner_to_latest_entry_runtime() -> None:
    fake_supabase = FakeSupabaseRestClient(_tables())
    fake_supabase.tables["bot_execution_events"] = [
        {
            "id": "event-a-open",
            "runtime_id": "runtime-a",
            "event_type": "action.executed",
            "decision_summary": "btc long a",
            "request_payload": {"type": "open_long", "symbol": "BTC"},
            "result_payload": {
                "execution_meta": {
                    "symbol": "BTC",
                    "side": "bid",
                    "amount": 1.0,
                    "reduce_only": False,
                    "reference_price": 90.0,
                }
            },
            "status": "success",
            "error_reason": None,
            "created_at": "2026-03-17T00:00:00+00:00",
        },
        {
            "id": "event-b-short",
            "runtime_id": "runtime-b",
            "event_type": "action.executed",
            "decision_summary": "btc short b",
            "request_payload": {"type": "open_short", "symbol": "BTC"},
            "result_payload": {
                "execution_meta": {
                    "symbol": "BTC",
                    "side": "ask",
                    "amount": 2.0,
                    "reduce_only": False,
                    "reference_price": 110.0,
                }
            },
            "status": "success",
            "error_reason": None,
            "created_at": "2026-03-17T00:05:00+00:00",
        },
        {
            "id": "event-b-latest-long",
            "runtime_id": "runtime-b",
            "event_type": "action.executed",
            "decision_summary": "btc long b",
            "request_payload": {"type": "open_long", "symbol": "BTC"},
            "result_payload": {
                "execution_meta": {
                    "symbol": "BTC",
                    "side": "bid",
                    "amount": 1.0,
                    "reduce_only": False,
                    "reference_price": 100.0,
                }
            },
            "status": "success",
            "error_reason": None,
            "created_at": "2026-03-17T00:10:00+00:00",
        },
    ]
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
    service = BotPerformanceService(pacifica_client=fake_pacifica, supabase=fake_supabase)

    runtimes = fake_supabase.select("bot_runtimes", filters={"wallet_address": "shared-wallet"})
    performance_by_runtime = asyncio.run(service.calculate_runtimes_performance_map(runtimes))

    assert performance_by_runtime["runtime-a"]["positions"] == []
    assert len(performance_by_runtime["runtime-b"]["positions"]) == 1
    assert performance_by_runtime["runtime-b"]["positions"][0]["symbol"] == "BTC"
    assert performance_by_runtime["runtime-b"]["positions"][0]["side"] == "long"
    assert performance_by_runtime["runtime-b"]["positions"][0]["amount"] == 1.0


def test_runtime_performance_loads_manual_close_from_later_position_history_pages() -> None:
    fake_supabase = FakeSupabaseRestClient(_tables())
    fake_pacifica = FakePacificaClient()
    fake_pacifica.live_positions["shared-wallet"] = []
    fake_pacifica.position_history["shared-wallet"] = [
        {
            "history_id": index + 1,
            "symbol": "SOL",
            "amount": 1.0,
            "price": 10.0,
            "entry_price": 10.0,
            "fee": 0.0,
            "pnl": 0.0,
            "event_type": "open_long",
            "created_at": f"2026-03-16T{index // 60:02d}:{index % 60:02d}:00+00:00",
        }
        for index in range(200)
    ] + [
        {
            "history_id": 1001,
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
            "history_id": 1002,
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
    assert performance_a["pnl_realized"] == 20.0
    assert performance_a["win_streak"] == 1
    assert fake_pacifica.position_history_requests[:2] == [
        ("shared-wallet", 200, 0),
        ("shared-wallet", 200, 200),
    ]


def test_runtime_performance_recovers_bot_open_from_request_history_when_fill_is_missing() -> None:
    fake_supabase = FakeSupabaseRestClient(_tables())
    fake_supabase.tables["bot_execution_events"] = [
        {
            "id": "event-a-open",
            "runtime_id": "runtime-a",
            "event_type": "action.executed",
            "decision_summary": "btc open a",
            "request_payload": {"type": "open_long", "symbol": "BTC", "size_usd": 100},
            "result_payload": {},
            "status": "success",
            "error_reason": None,
            "created_at": "2026-03-17T00:00:00+00:00",
        }
    ]
    fake_pacifica = FakePacificaClient()
    fake_pacifica.live_positions["shared-wallet"] = []
    fake_pacifica.position_history["shared-wallet"] = [
        {
            "history_id": 1001,
            "symbol": "BTC",
            "amount": 1.0,
            "price": 100.0,
            "entry_price": 100.0,
            "fee": 0.0,
            "pnl": 0.0,
            "event_type": "open_long",
            "created_at": "2026-03-17T00:00:01+00:00",
        },
        {
            "history_id": 1002,
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
    assert performance_a["pnl_realized"] == 20.0
    assert performance_a["win_streak"] == 1


def test_runtime_performance_uses_latest_execution_events_window() -> None:
    fake_supabase = FakeSupabaseRestClient(_tables())
    fake_supabase.tables["bot_runtimes"] = [
        runtime for runtime in fake_supabase.tables["bot_runtimes"] if runtime["id"] == "runtime-a"
    ]
    old_events: list[dict[str, Any]] = []
    for index in range(1000):
        old_events.append(
            {
                "id": f"event-old-{index}",
                "runtime_id": "runtime-a",
                "event_type": "action.executed",
                "decision_summary": "old eth open",
                "request_payload": {"type": "open_short", "symbol": "ETH"},
                "result_payload": {
                    "request_id": f"old-{index}",
                    "execution_meta": {
                        "symbol": "ETH",
                        "side": "ask",
                        "amount": 1.0,
                        "reduce_only": False,
                        "reference_price": 50.0,
                    },
                },
                "status": "success",
                "error_reason": None,
                "created_at": f"2026-03-16T{(index // 60) % 24:02d}:{index % 60:02d}:00+00:00",
            }
        )
    latest_event = {
        "id": "event-latest-btc-open",
        "runtime_id": "runtime-a",
        "event_type": "action.executed",
        "decision_summary": "latest btc open",
        "request_payload": {"type": "open_long", "symbol": "BTC"},
        "result_payload": {
            "request_id": "latest-open",
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
        "created_at": "2026-03-17T00:30:00+00:00",
    }
    fake_supabase.tables["bot_execution_events"] = [*old_events, latest_event]

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
    service = BotPerformanceService(pacifica_client=fake_pacifica, supabase=fake_supabase)

    runtime_a = fake_supabase.maybe_one("bot_runtimes", filters={"id": "runtime-a"})
    performance_a = asyncio.run(service.calculate_runtime_performance(runtime_a))

    assert len(performance_a["positions"]) == 1
    assert performance_a["positions"][0]["symbol"] == "BTC"
    assert performance_a["positions"][0]["side"] == "long"
    assert performance_a["positions"][0]["amount"] == 1.0


def test_runtime_performance_realizes_manual_close_from_wallet_order_history() -> None:
    fake_supabase = FakeSupabaseRestClient(_tables())
    fake_pacifica = FakePacificaClient()
    fake_pacifica.live_positions["shared-wallet"] = []
    fake_pacifica.position_history["shared-wallet"] = [
        {
            "history_id": 7001,
            "symbol": "BTC",
            "amount": 1.0,
            "price": 120.0,
            "entry_price": 100.0,
            "fee": 0.0,
            "pnl": 20.0,
            "event_type": "fulfill_taker",
            "created_at": 1773991707301,
        }
    ]
    fake_pacifica.wallet_order_history["shared-wallet"] = [
        {
            "order_id": 9001,
            "symbol": "BTC",
            "side": "ask",
            "price": 120.0,
            "amount": 1.0,
            "reduce_only": True,
            "order_status": "filled",
            "client_order_id": None,
            "created_at": 1773991707301,
        }
    ]
    service = BotPerformanceService(pacifica_client=fake_pacifica, supabase=fake_supabase)

    runtime_a = fake_supabase.maybe_one("bot_runtimes", filters={"id": "runtime-a"})
    performance_a = asyncio.run(service.calculate_runtime_performance(runtime_a))

    assert performance_a["positions"] == []
    assert performance_a["pnl_realized"] == 20.0
    assert performance_a["win_streak"] == 1
    assert fake_pacifica.wallet_order_history_requests[0] == ("shared-wallet", 200, 0)


def test_runtime_performance_invalidates_cached_ledger_when_manual_close_arrives_without_new_bot_event() -> None:
    fake_supabase = FakeSupabaseRestClient(_tables())
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
    service = BotPerformanceService(pacifica_client=fake_pacifica, supabase=fake_supabase)

    runtime_a = fake_supabase.maybe_one("bot_runtimes", filters={"id": "runtime-a"})
    initial = asyncio.run(service.calculate_runtime_performance(runtime_a))

    assert initial["pnl_realized"] == 0.0
    assert initial["pnl_unrealized"] == 10.0

    fake_pacifica.live_positions["shared-wallet"] = []
    fake_pacifica.wallet_order_history["shared-wallet"] = [
        {
            "order_id": 9002,
            "symbol": "BTC",
            "side": "ask",
            "price": 120.0,
            "amount": 1.0,
            "reduce_only": True,
            "order_status": "filled",
            "client_order_id": None,
            "created_at": 1773991707301,
        }
    ]
    fake_pacifica.wallet_order_history_requests.clear()

    refreshed = asyncio.run(service.calculate_runtime_performance(runtime_a))

    assert refreshed["positions"] == []
    assert refreshed["pnl_realized"] == 20.0
    assert refreshed["pnl_unrealized"] == 0.0
    assert refreshed["win_streak"] == 1
    assert fake_pacifica.wallet_order_history_requests


def test_runtime_performance_persists_ledger_idempotently_when_same_rows_already_exist() -> None:
    seeded_supabase = FakeSupabaseRestClient(_tables())
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
    seeded_service = BotPerformanceService(pacifica_client=fake_pacifica, supabase=seeded_supabase)
    runtime_a = seeded_supabase.maybe_one("bot_runtimes", filters={"id": "runtime-a"})

    asyncio.run(seeded_service.calculate_runtime_performance(runtime_a))

    racey_supabase = NoDeleteSupabaseRestClient(seeded_supabase.tables)
    racey_service = BotPerformanceService(pacifica_client=fake_pacifica, supabase=racey_supabase)

    performance = asyncio.run(racey_service.calculate_runtime_performance(runtime_a))

    assert performance["pnl_total"] == 10.0
    assert len(racey_supabase.tables["bot_trade_lots"]) == 1
    assert len(racey_supabase.tables["bot_trade_sync_state"]) == 1


def test_runtime_performance_skips_ledger_persistence_when_runtime_is_deleted_midflight() -> None:
    fake_supabase = RuntimeFkSupabaseRestClient(_tables())
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
    runtime_a = fake_supabase.maybe_one("bot_runtimes", filters={"id": "runtime-a"})
    fake_supabase.delete("bot_runtimes", filters={"id": "runtime-a"})

    service = BotPerformanceService(pacifica_client=fake_pacifica, supabase=fake_supabase)
    performance = asyncio.run(service.calculate_runtime_performance(runtime_a))

    assert performance["pnl_total"] == 10.0
    assert fake_supabase.tables.get("bot_trade_lots", []) == []
    assert fake_supabase.tables.get("bot_trade_closures", []) == []
    assert fake_supabase.tables.get("bot_trade_sync_state", []) == []


def test_runtime_performance_ignores_retryable_ledger_cache_failures() -> None:
    fake_supabase = RetryableLedgerCacheSupabaseRestClient(_tables())
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
    service = BotPerformanceService(pacifica_client=fake_pacifica, supabase=fake_supabase)
    runtime_a = fake_supabase.maybe_one("bot_runtimes", filters={"id": "runtime-a"})

    performance = asyncio.run(service.calculate_runtime_performance(runtime_a))

    assert performance["pnl_total"] == 10.0
    assert performance["pnl_unrealized"] == 10.0
    assert performance["positions"][0]["symbol"] == "BTC"
    assert fake_pacifica.order_history_requests == [11]
    assert fake_supabase.tables.get("bot_trade_lots", []) == []
    assert fake_supabase.tables.get("bot_trade_closures", []) == []
    assert fake_supabase.tables.get("bot_trade_sync_state", []) == []


def test_runtime_performance_reuses_persisted_ledger_without_reloading_order_history() -> None:
    fake_supabase = FakeSupabaseRestClient(_tables())
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
    service = BotPerformanceService(pacifica_client=fake_pacifica, supabase=fake_supabase)
    runtime_a = fake_supabase.maybe_one("bot_runtimes", filters={"id": "runtime-a"})

    initial = asyncio.run(service.calculate_runtime_performance(runtime_a))

    assert initial["pnl_total"] == 10.0
    assert fake_pacifica.order_history_requests == [11]

    fake_pacifica.order_history_requests.clear()

    cached = asyncio.run(service.calculate_runtime_performance(runtime_a))

    assert cached["pnl_total"] == 10.0
    assert cached["positions"][0]["symbol"] == "BTC"
    assert fake_pacifica.order_history_requests == []
