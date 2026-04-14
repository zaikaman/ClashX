from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from typing import Any

from src.services.bot_builder_service import BotBuilderService
from src.services.runtime_observability_service import RuntimeObservabilityService
from src.services.bot_runtime_engine import BotRuntimeEngine
from src.services.trading_service import TradingService
from src.workers.bot_runtime_worker import BotRuntimeWorker


def _graph_rules() -> dict[str, Any]:
    return {
        "graph": {
            "version": 1,
            "entry": "builder-entry",
            "nodes": [
                {"id": "builder-entry", "kind": "entry", "position": {"x": 0, "y": 0}},
                {
                    "id": "condition-breakout",
                    "kind": "condition",
                    "position": {"x": 180, "y": 80},
                    "config": {"type": "price_above", "symbol": "BTC", "value": 100000},
                },
                {
                    "id": "action-open",
                    "kind": "action",
                    "position": {"x": 380, "y": 80},
                    "config": {"type": "open_long", "symbol": "BTC", "size_usd": 200, "leverage": 3},
                },
            ],
            "edges": [
                {"id": "edge-entry-condition", "source": "builder-entry", "target": "condition-breakout"},
                {"id": "edge-condition-action", "source": "condition-breakout", "target": "action-open"},
            ],
        }
    }


def _seed_tables() -> dict[str, list[dict[str, Any]]]:
    return {
        "bot_definitions": [
            {
                "id": "bot-1",
                "user_id": "user-1",
                "wallet_address": "wallet-1",
                "name": "Momentum Bot",
                "description": "Supabase runtime test",
                "visibility": "private",
                "market_scope": "Pacifica perpetuals",
                "strategy_type": "rules",
                "authoring_mode": "visual",
                "rules_version": 1,
                "rules_json": _graph_rules(),
                "created_at": "2026-03-16T00:00:00+00:00",
                "updated_at": "2026-03-16T00:00:00+00:00",
            }
        ],
        "bot_runtimes": [
            {
                "id": "runtime-1",
                "bot_definition_id": "bot-1",
                "user_id": "user-1",
                "wallet_address": "wallet-1",
                "status": "active",
                "mode": "live",
                "risk_policy_json": {
                    "max_leverage": 5,
                    "max_order_size_usd": 250,
                    "allocated_capital_usd": 200,
                    "cooldown_seconds": 45,
                    "max_drawdown_pct": 18,
                    "_runtime_state": {},
                },
                "deployed_at": "2026-03-16T00:00:00+00:00",
                "stopped_at": None,
                "updated_at": "2026-03-16T00:00:00+00:00",
            }
        ],
        "bot_execution_events": [],
        "bot_action_claims": [],
        "bot_trade_sync_state": [],
        "bot_trade_lots": [],
        "bot_trade_closures": [],
        "bot_leaderboard_snapshots": [],
        "bot_copy_execution_events": [],
        "bot_copy_relationships": [],
        "portfolio_allocation_members": [],
        "bot_backtest_runs": [],
        "bot_invite_access": [],
        "bot_publish_snapshots": [],
        "bot_publishing_settings": [],
        "bot_strategy_versions": [],
        "featured_bots": [],
        "bot_clones": [],
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
        cache_ttl_seconds: float | None = None,
    ) -> list[dict[str, Any]]:
        del columns, cache_ttl_seconds
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
        cache_ttl_seconds: float | None = None,
    ) -> dict[str, Any] | None:
        rows = self.select(table, columns=columns, filters=filters, order=order, limit=1, cache_ttl_seconds=cache_ttl_seconds)
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
        del upsert, on_conflict, returning
        items = payload if isinstance(payload, list) else [payload]
        stored = [deepcopy(item) for item in items]
        self.tables.setdefault(table, []).extend(stored)
        return [deepcopy(item) for item in stored]

    def update(
        self,
        table: str,
        values: dict[str, Any],
        *,
        filters: dict[str, Any],
        returning: str = "representation",
    ) -> list[dict[str, Any]]:
        del returning
        updated: list[dict[str, Any]] = []
        for row in self.tables.get(table, []):
            if not self._matches(row, filters):
                continue
            row.update(deepcopy(values))
            updated.append(deepcopy(row))
        return updated

    def delete(self, table: str, *, filters: dict[str, Any]) -> None:
        remaining = [row for row in self.tables.get(table, []) if not self._matches(row, filters)]
        self.tables[table] = remaining

    @staticmethod
    def _matches(row: dict[str, Any], filters: dict[str, Any] | None) -> bool:
        if not filters:
            return True
        for key, expected in filters.items():
            if isinstance(expected, tuple):
                operator, operand = expected
                if operator == "in":
                    if row.get(key) not in operand:
                        return False
                    continue
                if operator != "eq" or row.get(key) != operand:
                    return False
                continue
            if row.get(key) != expected:
                return False
        return True


class CountingFakeSupabaseRestClient(FakeSupabaseRestClient):
    def __init__(self, tables: dict[str, list[dict[str, Any]]]) -> None:
        super().__init__(tables)
        self.select_calls: list[tuple[str, dict[str, Any] | None, str]] = []
        self.maybe_one_calls: list[tuple[str, dict[str, Any] | None, str]] = []
        self.update_calls: list[tuple[str, dict[str, Any], dict[str, Any]]] = []

    def select(
        self,
        table: str,
        *,
        columns: str = "*",
        filters: dict[str, Any] | None = None,
        order: str | None = None,
        limit: int | None = None,
        cache_ttl_seconds: float | None = None,
    ) -> list[dict[str, Any]]:
        self.select_calls.append((table, deepcopy(filters), columns))
        return super().select(
            table,
            columns=columns,
            filters=filters,
            order=order,
            limit=limit,
            cache_ttl_seconds=cache_ttl_seconds,
        )

    def maybe_one(
        self,
        table: str,
        *,
        columns: str = "*",
        filters: dict[str, Any] | None = None,
        order: str | None = None,
        cache_ttl_seconds: float | None = None,
    ) -> dict[str, Any] | None:
        self.maybe_one_calls.append((table, deepcopy(filters), columns))
        return super().maybe_one(
            table,
            columns=columns,
            filters=filters,
            order=order,
            cache_ttl_seconds=cache_ttl_seconds,
        )

    def update(
        self,
        table: str,
        values: dict[str, Any],
        *,
        filters: dict[str, Any],
        returning: str = "representation",
    ) -> list[dict[str, Any]]:
        self.update_calls.append((table, deepcopy(values), deepcopy(filters)))
        return super().update(table, values, filters=filters, returning=returning)


class FakeAuthService:
    def get_trading_credentials(self, db: Any, wallet_address: str) -> dict[str, str] | None:
        del db
        if wallet_address != "wallet-1":
            return None
        return {
            "account_address": wallet_address,
            "agent_wallet_address": "agent-1",
            "agent_private_key": "secret",
        }


class FakeReadinessService:
    async def require_ready(self, db: Any, wallet_address: str) -> dict[str, Any]:
        del db, wallet_address
        return {"ready": True}


class FakePacificaClient:
    def __init__(
        self,
        *,
        positions: list[dict[str, Any]] | None = None,
        open_orders: list[dict[str, Any]] | None = None,
        account_settings: list[dict[str, Any]] | None = None,
    ) -> None:
        self.orders: list[dict[str, Any]] = []
        self.positions = deepcopy(positions or [])
        self.open_orders = deepcopy(open_orders or [])
        self.account_settings = deepcopy(account_settings or [])
        self.market_requests = 0

    async def get_markets(self) -> list[dict[str, Any]]:
        self.market_requests += 1
        return [
            {
                "symbol": "BTC-PERP",
                "display_symbol": "BTC-PERP",
                "mark_price": 105000,
                "lot_size": 0.001,
                "min_order_size": 0.001,
                "tick_size": 0.5,
                "max_leverage": 5,
            }
        ]

    async def get_positions(self, wallet_address: str, *, price_lookup: dict[str, float] | None = None) -> list[dict[str, Any]]:
        del wallet_address, price_lookup
        return deepcopy(self.positions)

    async def get_open_orders(self, wallet_address: str) -> list[dict[str, Any]]:
        del wallet_address
        return deepcopy(self.open_orders)

    async def get_account_settings(self, wallet_address: str) -> list[dict[str, Any]]:
        del wallet_address
        return deepcopy(self.account_settings)

    async def place_order(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.orders.append(deepcopy(payload))
        return {
            "status": "submitted",
            "request_id": f"req-{len(self.orders)}",
            "network": "testnet",
        }


class FakeIndicatorContextService:
    def __init__(self) -> None:
        self.load_requests = 0

    async def load_candle_lookup(self, rules_json: dict[str, Any]) -> dict[str, Any]:
        del rules_json
        self.load_requests += 1
        return {}


def test_deploy_runtime_persists_supabase_runtime_and_event() -> None:
    fake_supabase = FakeSupabaseRestClient({"bot_definitions": _seed_tables()["bot_definitions"], "bot_runtimes": [], "bot_execution_events": []})
    engine = BotRuntimeEngine()
    engine._supabase = fake_supabase
    engine._auth = FakeAuthService()
    engine._readiness = FakeReadinessService()

    runtime = engine.deploy_runtime(
        None,
        bot_id="bot-1",
        wallet_address="wallet-1",
        user_id="user-1",
        risk_policy_json={"max_order_size_usd": 180},
    )

    assert runtime["status"] == "active"
    assert fake_supabase.tables["bot_runtimes"][0]["bot_definition_id"] == "bot-1"
    assert fake_supabase.tables["bot_runtimes"][0]["risk_policy_json"]["max_order_size_usd"] == 180
    assert fake_supabase.tables["bot_runtimes"][0]["risk_policy_json"]["allocated_capital_usd"] == 200
    assert fake_supabase.tables["bot_execution_events"][0]["event_type"] == "runtime.deployed"


def test_deploy_runtime_defaults_allowed_symbols_from_selected_market_scope() -> None:
    tables = _seed_tables()
    tables["bot_definitions"][0]["rules_json"] = {
        "selected_market_symbols": ["BTC", "ETH", "SOL"],
        "graph": {
            "version": 1,
            "entry": "builder-entry",
            "nodes": [
                {"id": "builder-entry", "kind": "entry", "position": {"x": 0, "y": 0}},
                {
                    "id": "condition-rsi",
                    "kind": "condition",
                    "position": {"x": 180, "y": 80},
                    "config": {
                        "type": "rsi_above",
                        "symbol": "__BOT_MARKET_UNIVERSE__",
                        "timeframe": "1m",
                        "period": 14,
                        "value": 70,
                    },
                },
                {
                    "id": "action-open",
                    "kind": "action",
                    "position": {"x": 380, "y": 80},
                    "config": {"type": "open_long", "symbol": "__BOT_MARKET_UNIVERSE__", "size_usd": 100, "leverage": 3},
                },
            ],
            "edges": [
                {"id": "edge-entry-condition", "source": "builder-entry", "target": "condition-rsi"},
                {"id": "edge-condition-action", "source": "condition-rsi", "target": "action-open"},
            ],
        },
    }
    fake_supabase = FakeSupabaseRestClient({"bot_definitions": tables["bot_definitions"], "bot_runtimes": [], "bot_execution_events": []})
    engine = BotRuntimeEngine()
    engine._supabase = fake_supabase
    engine._auth = FakeAuthService()
    engine._readiness = FakeReadinessService()

    runtime = engine.deploy_runtime(
        None,
        bot_id="bot-1",
        wallet_address="wallet-1",
        user_id="user-1",
        risk_policy_json={"max_order_size_usd": 180},
    )

    assert runtime["risk_policy_json"]["allowed_symbols"] == ["BTC", "ETH", "SOL"]


def test_update_bot_syncs_runtime_allowlist_when_it_still_matches_previous_builder_scope() -> None:
    tables = _seed_tables()
    tables["bot_definitions"][0]["rules_json"] = {
        "selected_market_symbols": ["BTC", "ETH", "SOL"],
        "graph": {
            "version": 1,
            "entry": "builder-entry",
            "nodes": [
                {"id": "builder-entry", "kind": "entry", "position": {"x": 0, "y": 0}},
                {
                    "id": "condition-rsi",
                    "kind": "condition",
                    "position": {"x": 180, "y": 80},
                    "config": {
                        "type": "rsi_above",
                        "symbol": "__BOT_MARKET_UNIVERSE__",
                        "timeframe": "1m",
                        "period": 14,
                        "value": 70,
                    },
                },
                {
                    "id": "action-open",
                    "kind": "action",
                    "position": {"x": 380, "y": 80},
                    "config": {"type": "open_long", "symbol": "__BOT_MARKET_UNIVERSE__", "size_usd": 100, "leverage": 3},
                },
            ],
            "edges": [
                {"id": "edge-entry-condition", "source": "builder-entry", "target": "condition-rsi"},
                {"id": "edge-condition-action", "source": "condition-rsi", "target": "action-open"},
            ],
        },
    }
    tables["bot_runtimes"][0]["risk_policy_json"]["allowed_symbols"] = ["BTC", "ETH", "SOL"]
    fake_supabase = FakeSupabaseRestClient(tables)
    service = BotBuilderService()
    service.supabase = fake_supabase

    service.update_bot(
        None,
        bot_id="bot-1",
        wallet_address="wallet-1",
        rules_json={
            "selected_market_symbols": ["BTC", "ETH", "SOL", "DOGE"],
            "graph": {
                "version": 1,
                "entry": "builder-entry",
                "nodes": [
                    {"id": "builder-entry", "kind": "entry", "position": {"x": 0, "y": 0}},
                    {
                        "id": "condition-rsi",
                        "kind": "condition",
                        "position": {"x": 180, "y": 80},
                        "config": {
                            "type": "rsi_above",
                            "symbol": "__BOT_MARKET_UNIVERSE__",
                            "timeframe": "1m",
                            "period": 14,
                            "value": 70,
                        },
                    },
                    {
                        "id": "action-open",
                        "kind": "action",
                        "position": {"x": 380, "y": 80},
                        "config": {"type": "open_long", "symbol": "__BOT_MARKET_UNIVERSE__", "size_usd": 100, "leverage": 3},
                    },
                ],
                "edges": [
                    {"id": "edge-entry-condition", "source": "builder-entry", "target": "condition-rsi"},
                    {"id": "edge-condition-action", "source": "condition-rsi", "target": "action-open"},
                ],
            },
        },
    )

    assert fake_supabase.tables["bot_runtimes"][0]["risk_policy_json"]["allowed_symbols"] == ["BTC", "ETH", "SOL", "DOGE"]


def test_update_bot_preserves_manual_runtime_allowlist_overrides() -> None:
    tables = _seed_tables()
    tables["bot_definitions"][0]["rules_json"] = {
        "selected_market_symbols": ["BTC", "ETH", "SOL"],
        "graph": _graph_rules()["graph"],
    }
    tables["bot_runtimes"][0]["risk_policy_json"]["allowed_symbols"] = ["BTC"]
    fake_supabase = FakeSupabaseRestClient(tables)
    service = BotBuilderService()
    service.supabase = fake_supabase

    service.update_bot(
        None,
        bot_id="bot-1",
        wallet_address="wallet-1",
        rules_json={
            "selected_market_symbols": ["BTC", "ETH", "SOL", "DOGE"],
            "graph": _graph_rules()["graph"],
        },
    )

    assert fake_supabase.tables["bot_runtimes"][0]["risk_policy_json"]["allowed_symbols"] == ["BTC"]


def test_list_runtimes_for_wallet_returns_serialized_runtime_summaries() -> None:
    fake_supabase = FakeSupabaseRestClient(_seed_tables())
    engine = BotRuntimeEngine()
    engine._supabase = fake_supabase

    runtimes = engine.list_runtimes_for_wallet(None, wallet_address="wallet-1", user_id="user-1")

    assert len(runtimes) == 1
    assert runtimes[0]["bot_definition_id"] == "bot-1"
    assert runtimes[0]["status"] == "active"


def test_delete_bot_removes_stopped_runtime_and_events() -> None:
    tables = _seed_tables()
    tables["bot_runtimes"][0]["status"] = "stopped"
    tables["bot_runtimes"][0]["stopped_at"] = "2026-03-16T01:00:00+00:00"
    tables["bot_execution_events"] = [
        {
            "id": "event-1",
            "runtime_id": "runtime-1",
            "event_type": "runtime.stopped",
            "decision_summary": "runtime transitioned to stopped",
            "request_payload": {},
            "result_payload": {"status": "stopped"},
            "status": "success",
            "error_reason": None,
            "created_at": "2026-03-16T01:00:00+00:00",
        }
    ]
    tables["bot_action_claims"] = [
        {
            "id": "claim-1",
            "runtime_id": "runtime-1",
            "idempotency_key": "idem-1",
            "claimed_by": "worker-1",
            "created_at": "2026-03-16T01:00:00+00:00",
        }
    ]
    tables["bot_trade_sync_state"] = [
        {
            "runtime_id": "runtime-1",
            "synced_at": "2026-03-16T01:00:00+00:00",
            "execution_events_count": 1,
            "position_history_count": 1,
            "last_execution_at": "2026-03-16T01:00:00+00:00",
            "last_history_at": "2026-03-16T01:00:00+00:00",
            "last_error": None,
        }
    ]
    tables["bot_trade_lots"] = [
        {
            "id": "lot-1",
            "runtime_id": "runtime-1",
            "symbol": "BTC",
            "side": "bid",
            "opened_at": "2026-03-16T00:30:00+00:00",
            "source": "bot",
            "source_event_id": "event-1",
            "source_order_id": "order-1",
            "source_history_id": 11,
            "entry_price": 100000.0,
            "quantity_opened": 0.01,
            "quantity_remaining": 0.0,
            "created_at": "2026-03-16T00:30:00+00:00",
            "updated_at": "2026-03-16T01:00:00+00:00",
        }
    ]
    tables["bot_trade_closures"] = [
        {
            "id": "closure-1",
            "runtime_id": "runtime-1",
            "lot_id": "lot-1",
            "symbol": "BTC",
            "side": "bid",
            "closed_at": "2026-03-16T01:00:00+00:00",
            "source": "bot",
            "source_event_id": "event-1",
            "source_order_id": "order-1",
            "source_history_id": 12,
            "quantity_closed": 0.01,
            "entry_price": 100000.0,
            "exit_price": 101000.0,
            "realized_pnl": 10.0,
            "created_at": "2026-03-16T01:00:00+00:00",
        }
    ]
    tables["bot_leaderboard_snapshots"] = [
        {
            "id": "snapshot-1",
            "runtime_id": "runtime-1",
            "rank": 1,
            "pnl_total": 10.0,
            "pnl_unrealized": 0.0,
            "win_streak": 1,
            "drawdown": 0.0,
            "captured_at": "2026-03-16T01:00:00+00:00",
        }
    ]
    tables["bot_copy_relationships"] = [
        {
            "id": "copy-1",
            "source_runtime_id": "runtime-1",
            "follower_user_id": "user-2",
            "follower_wallet_address": "wallet-2",
            "mode": "mirror",
            "scale_bps": 10000,
            "status": "stopped",
            "risk_ack_version": "v1",
            "confirmed_at": "2026-03-16T00:00:00+00:00",
            "updated_at": "2026-03-16T01:00:00+00:00",
        }
    ]
    tables["bot_copy_execution_events"] = [
        {
            "id": "copy-event-1",
            "relationship_id": "copy-1",
            "source_runtime_id": "runtime-1",
            "source_event_id": "event-1",
            "follower_user_id": "user-2",
            "follower_wallet_address": "wallet-2",
            "status": "applied",
            "result_payload_json": {},
            "created_at": "2026-03-16T01:00:00+00:00",
            "updated_at": "2026-03-16T01:00:00+00:00",
        }
    ]
    tables["portfolio_allocation_members"] = [
        {
            "id": "member-1",
            "portfolio_basket_id": "basket-1",
            "source_runtime_id": "runtime-1",
            "relationship_id": "copy-1",
            "status": "active",
            "created_at": "2026-03-16T01:00:00+00:00",
            "updated_at": "2026-03-16T01:00:00+00:00",
        }
    ]
    tables["bot_backtest_runs"] = [
        {
            "id": "backtest-1",
            "bot_definition_id": "bot-1",
            "user_id": "user-1",
            "wallet_address": "wallet-1",
        }
    ]
    tables["bot_invite_access"] = [
        {
            "id": "invite-1",
            "bot_definition_id": "bot-1",
            "invited_wallet_address": "wallet-3",
            "invited_by_user_id": "user-1",
            "status": "active",
        }
    ]
    tables["bot_strategy_versions"] = [
        {
            "id": "version-1",
            "bot_definition_id": "bot-1",
            "created_by_user_id": "user-1",
            "version_number": 1,
        }
    ]
    tables["bot_publish_snapshots"] = [
        {
            "id": "publish-1",
            "bot_definition_id": "bot-1",
            "strategy_version_id": "version-1",
            "runtime_id": "runtime-1",
        }
    ]
    tables["bot_publishing_settings"] = [
        {
            "id": "settings-1",
            "bot_definition_id": "bot-1",
            "user_id": "user-1",
        }
    ]
    tables["featured_bots"] = [
        {
            "id": "featured-1",
            "creator_profile_id": "profile-1",
            "bot_definition_id": "bot-1",
        }
    ]
    tables["bot_clones"] = [
        {
            "id": "clone-1",
            "source_bot_definition_id": "bot-1",
            "new_bot_definition_id": "bot-2",
            "created_by_user_id": "user-2",
        }
    ]
    fake_supabase = FakeSupabaseRestClient(tables)
    service = BotBuilderService()
    service.supabase = fake_supabase

    service.delete_bot(None, bot_id="bot-1", wallet_address="wallet-1")

    assert fake_supabase.tables["bot_definitions"] == []
    assert fake_supabase.tables["bot_runtimes"] == []
    assert fake_supabase.tables["bot_execution_events"] == []
    assert fake_supabase.tables["bot_action_claims"] == []
    assert fake_supabase.tables["bot_trade_sync_state"] == []
    assert fake_supabase.tables["bot_trade_lots"] == []
    assert fake_supabase.tables["bot_trade_closures"] == []
    assert fake_supabase.tables["bot_leaderboard_snapshots"] == []
    assert fake_supabase.tables["bot_copy_execution_events"] == []
    assert fake_supabase.tables["bot_copy_relationships"] == []
    assert fake_supabase.tables["portfolio_allocation_members"] == []
    assert fake_supabase.tables["bot_backtest_runs"] == []
    assert fake_supabase.tables["bot_invite_access"] == []
    assert fake_supabase.tables["bot_publish_snapshots"] == []
    assert fake_supabase.tables["bot_publishing_settings"] == []
    assert fake_supabase.tables["bot_strategy_versions"] == []
    assert fake_supabase.tables["featured_bots"] == []
    assert fake_supabase.tables["bot_clones"] == []


def test_delete_bot_rejects_active_runtime() -> None:
    fake_supabase = FakeSupabaseRestClient(_seed_tables())
    service = BotBuilderService()
    service.supabase = fake_supabase

    try:
        service.delete_bot(None, bot_id="bot-1", wallet_address="wallet-1")
    except ValueError as exc:
        assert str(exc) == "Stop the runtime before deleting this bot."
    else:
        raise AssertionError("Expected delete_bot to reject active runtimes")


def test_runtime_overview_returns_health_and_metrics_from_shared_event_window() -> None:
    tables = _seed_tables()
    now = datetime.now(tz=UTC)
    tables["bot_execution_events"] = [
        {
            "id": "event-2",
            "runtime_id": "runtime-1",
            "event_type": "action.executed",
            "decision_summary": "opened a long",
            "request_payload": {},
            "result_payload": {"status": "success"},
            "status": "success",
            "error_reason": None,
            "created_at": (now - timedelta(minutes=20)).isoformat(),
        },
        {
            "id": "event-1",
            "runtime_id": "runtime-1",
            "event_type": "action.failed",
            "decision_summary": "rejected by guardrail",
            "request_payload": {},
            "result_payload": {"status": "error"},
            "status": "error",
            "error_reason": "risk_limit",
            "created_at": (now - timedelta(minutes=30)).isoformat(),
        },
    ]
    fake_supabase = FakeSupabaseRestClient(tables)
    service = RuntimeObservabilityService()
    service._supabase = fake_supabase

    overview = service.get_overview(None, bot_id="bot-1", wallet_address="wallet-1", user_id="user-1")

    assert overview["health"]["runtime_id"] == "runtime-1"
    assert overview["metrics"]["runtime_id"] == "runtime-1"
    assert overview["metrics"]["events_total"] == 2
    assert overview["metrics"]["actions_total"] == 2
    assert overview["metrics"]["actions_error"] == 1
    assert overview["metrics"]["failure_reasons"][0]["reason"] == "risk_limit"


def test_runtime_overview_returns_draft_snapshot_when_runtime_is_missing() -> None:
    tables = _seed_tables()
    tables["bot_runtimes"] = []
    fake_supabase = FakeSupabaseRestClient(tables)
    service = RuntimeObservabilityService()
    service._supabase = fake_supabase

    overview = service.get_overview(None, bot_id="bot-1", wallet_address="wallet-1", user_id="user-1")

    assert overview["health"]["runtime_id"] is None
    assert overview["health"]["health"] == "not_deployed"
    assert overview["metrics"]["status"] == "draft"
    assert overview["metrics"]["events_total"] == 0


def test_runtime_overviews_for_wallet_batches_runtime_snapshots() -> None:
    tables = _seed_tables()
    tables["bot_definitions"].append(
        {
            "id": "bot-2",
            "user_id": "user-1",
            "wallet_address": "wallet-1",
            "name": "Draft Bot",
            "description": "No runtime yet",
            "visibility": "private",
            "market_scope": "Pacifica perpetuals",
            "strategy_type": "rules",
            "authoring_mode": "visual",
            "rules_version": 1,
            "rules_json": _graph_rules(),
            "created_at": "2026-03-16T00:00:00+00:00",
            "updated_at": "2026-03-16T00:00:00+00:00",
        }
    )
    now = datetime.now(tz=UTC)
    tables["bot_execution_events"] = [
        {
            "id": "event-2",
            "runtime_id": "runtime-1",
            "event_type": "action.executed",
            "decision_summary": "opened a long",
            "request_payload": {},
            "result_payload": {"status": "success"},
            "status": "success",
            "error_reason": None,
            "created_at": (now - timedelta(minutes=10)).isoformat(),
        },
        {
            "id": "event-1",
            "runtime_id": "runtime-1",
            "event_type": "action.failed",
            "decision_summary": "rejected by guardrail",
            "request_payload": {},
            "result_payload": {"status": "error"},
            "status": "error",
            "error_reason": "risk_limit",
            "created_at": (now - timedelta(minutes=15)).isoformat(),
        },
    ]
    fake_supabase = FakeSupabaseRestClient(tables)
    service = RuntimeObservabilityService()
    service._supabase = fake_supabase

    overview_by_bot = service.get_overviews_for_wallet(None, wallet_address="wallet-1", user_id="user-1")

    assert overview_by_bot["bot-1"]["health"]["runtime_id"] == "runtime-1"
    assert overview_by_bot["bot-1"]["metrics"]["events_total"] == 2
    assert overview_by_bot["bot-1"]["metrics"]["actions_total"] == 2
    assert overview_by_bot["bot-2"]["health"]["health"] == "not_deployed"
    assert overview_by_bot["bot-2"]["metrics"]["status"] == "draft"


def test_skip_event_lookup_uses_local_cache_after_first_match() -> None:
    tables = _seed_tables()
    now = datetime.now(tz=UTC)
    request_payload = {
        "type": "open_long",
        "symbol": "BTC",
        "leverage": 2,
        "size_usd": 100,
    }
    result_payload = {"issues": ["existing bot entry order on BTC is still open"]}
    tables["bot_execution_events"] = [
        {
            "id": "event-skip-1",
            "runtime_id": "runtime-1",
            "event_type": "action.skipped",
            "decision_summary": "skip-key",
            "request_payload": request_payload,
            "result_payload": result_payload,
            "status": "skipped",
            "error_reason": None,
            "created_at": now.isoformat(),
        }
    ]
    fake_supabase = CountingFakeSupabaseRestClient(tables)
    worker = BotRuntimeWorker.__new__(BotRuntimeWorker)
    worker._supabase = fake_supabase
    worker._recent_skip_events = {}

    first = asyncio.run(
        worker._should_record_skip_event_async(
            runtime_id="runtime-1",
            decision_summary="skip-key",
            request_payload=request_payload,
            result_payload=result_payload,
        )
    )
    second = asyncio.run(
        worker._should_record_skip_event_async(
            runtime_id="runtime-1",
            decision_summary="skip-key",
            request_payload=request_payload,
            result_payload=result_payload,
        )
    )

    assert first is False
    assert second is False
    assert len(fake_supabase.select_calls) == 1


def test_runtime_worker_keeps_volatile_runtime_state_in_memory() -> None:
    fake_supabase = CountingFakeSupabaseRestClient(_seed_tables())
    worker = BotRuntimeWorker(poll_interval_seconds=0.01)
    worker._supabase = fake_supabase

    runtime = deepcopy(fake_supabase.tables["bot_runtimes"][0])
    runtime_policy = deepcopy(runtime["risk_policy_json"])
    runtime_policy["_runtime_state"] = {
        "wallet_synced_at": "2026-03-16T00:15:00+00:00",
        "performance_synced_at": "2026-03-16T00:15:00+00:00",
        "last_rule_evaluated_at": "2026-03-16T00:15:00+00:00",
        "evaluation_slots": {"fast": 42},
        "observed_open_orders": 2,
        "observed_positions": 1,
    }

    updated_runtime = worker._persist_runtime_policy(runtime, runtime_policy)
    reloaded_runtime = worker._merge_cached_runtime_state(fake_supabase.tables["bot_runtimes"][0])

    assert fake_supabase.update_calls == []
    assert updated_runtime["risk_policy_json"]["_runtime_state"]["wallet_synced_at"] == "2026-03-16T00:15:00+00:00"
    assert reloaded_runtime["risk_policy_json"]["_runtime_state"]["evaluation_slots"] == {"fast": 42}
    assert fake_supabase.tables["bot_runtimes"][0]["risk_policy_json"]["_runtime_state"] == {}


def test_runtime_worker_refreshes_updated_at_as_idle_heartbeat() -> None:
    fake_supabase = CountingFakeSupabaseRestClient(_seed_tables())
    fake_supabase.tables["bot_runtimes"][0]["updated_at"] = "2026-03-16T00:00:00+00:00"
    worker = BotRuntimeWorker(poll_interval_seconds=0.01)
    worker._supabase = fake_supabase

    runtime = asyncio.run(
        worker._process_runtime(
            None,
            deepcopy(fake_supabase.tables["bot_runtimes"][0]),
            bot=deepcopy(fake_supabase.tables["bot_definitions"][0]),
            bot_loaded=True,
            wallet_due=False,
            evaluation_due=False,
        )
    )

    assert len(fake_supabase.update_calls) == 1
    table, values, filters = fake_supabase.update_calls[0]
    assert table == "bot_runtimes"
    assert filters == {"id": "runtime-1"}
    assert values["updated_at"] != "2026-03-16T00:00:00+00:00"
    assert runtime["updated_at"] == fake_supabase.tables["bot_runtimes"][0]["updated_at"]


def test_runtime_worker_reuses_local_runtime_lease_before_refresh() -> None:
    worker = BotRuntimeWorker(poll_interval_seconds=0.01)
    lease_calls: list[tuple[str, int]] = []

    class _FakeCoordination:
        def try_claim_lease(self, lease_key: str, *, ttl_seconds: int) -> bool:
            lease_calls.append((lease_key, ttl_seconds))
            return True

        def release_lease(self, lease_key: str) -> None:
            del lease_key

    worker._coordination = _FakeCoordination()  # type: ignore[assignment]

    first = worker._claim_local_runtime_lease("bot-runtime:runtime-1", ttl_seconds=300)
    second = worker._claim_local_runtime_lease("bot-runtime:runtime-1", ttl_seconds=300)

    assert first is True
    assert second is True
    assert lease_calls == [("bot-runtime:runtime-1", 300)]


def test_list_runtime_events_returns_empty_list_when_runtime_is_missing() -> None:
    tables = _seed_tables()
    tables["bot_runtimes"] = []
    fake_supabase = FakeSupabaseRestClient(tables)
    engine = BotRuntimeEngine()
    engine._supabase = fake_supabase

    events = engine.list_runtime_events(None, bot_id="bot-1", wallet_address="wallet-1", user_id="user-1", limit=100)

    assert events == []


def test_list_runtime_events_humanizes_skipped_action_messages() -> None:
    tables = _seed_tables()
    now = datetime.now(tz=UTC)
    tables["bot_execution_events"] = [
        {
            "id": "event-1",
            "runtime_id": "runtime-1",
            "event_type": "action.skipped",
            "decision_summary": "idem:runtime-1:open_long:fartcoin",
            "request_payload": {
                "type": "open_long",
                "symbol": "FARTCOIN",
                "leverage": 1,
                "size_usd": 444,
            },
            "result_payload": {"issues": ["requested order value 444 exceeds max_order_size_usd 250"]},
            "status": "skipped",
            "error_reason": None,
            "created_at": now.isoformat(),
        }
    ]
    fake_supabase = FakeSupabaseRestClient(tables)
    engine = BotRuntimeEngine()
    engine._supabase = fake_supabase

    events = engine.list_runtime_events(None, bot_id="bot-1", wallet_address="wallet-1", user_id="user-1", limit=20)

    assert len(events) == 1
    assert events[0]["decision_summary"] == "Runtime attempted to open a long position on FARTCOIN with 1x leverage and about $444 notional."
    assert events[0]["outcome_summary"] == "Requested order size is about $444, above the runtime cap of $250."


def test_runtime_worker_executes_supabase_trade_without_sqlalchemy() -> None:
    fake_supabase = FakeSupabaseRestClient(_seed_tables())
    fake_pacifica = FakePacificaClient()
    worker = BotRuntimeWorker(poll_interval_seconds=0.01)
    worker._supabase = fake_supabase
    worker._engine._supabase = fake_supabase
    worker._auth = FakeAuthService()
    worker._pacifica = fake_pacifica
    worker._indicator_context = FakeIndicatorContextService()
    worker._calculate_runtime_performance = _fake_runtime_performance  # type: ignore[method-assign]

    asyncio.run(worker._process_runtime(None, fake_supabase.tables["bot_runtimes"][0]))

    runtime = fake_supabase.tables["bot_runtimes"][0]
    execution_events = fake_supabase.tables["bot_execution_events"]

    assert [order["type"] for order in fake_pacifica.orders] == ["update_leverage", "create_market_order"]
    assert fake_pacifica.orders[0]["leverage"] == 5
    assert fake_pacifica.orders[1]["amount"] == 0.009
    assert runtime["risk_policy_json"]["_runtime_state"]["executions_total"] == 1
    assert runtime["risk_policy_json"]["_runtime_state"]["allocated_capital_usd"] == 200
    assert any(event["event_type"] == "action.executed" for event in execution_events)


async def _fake_runtime_performance(runtime: dict[str, Any]) -> dict[str, Any]:
    del runtime
    return {
        "pnl_total": 0.0,
        "pnl_realized": 0.0,
        "pnl_unrealized": 0.0,
        "win_streak": 0,
        "positions": [],
    }


def test_runtime_worker_stops_bot_when_allocation_drawdown_is_breached() -> None:
    fake_supabase = FakeSupabaseRestClient(_seed_tables())
    fake_pacifica = FakePacificaClient()
    worker = BotRuntimeWorker(poll_interval_seconds=0.01)
    worker._supabase = fake_supabase
    worker._engine._supabase = fake_supabase
    worker._auth = FakeAuthService()
    worker._pacifica = fake_pacifica
    worker._indicator_context = FakeIndicatorContextService()

    async def _breached_runtime_performance(runtime: dict[str, Any]) -> dict[str, Any]:
        del runtime
        return {
            "pnl_total": -41.0,
            "pnl_realized": -15.0,
            "pnl_unrealized": -26.0,
            "win_streak": 0,
            "positions": [],
        }

    worker._calculate_runtime_performance = _breached_runtime_performance  # type: ignore[method-assign]

    asyncio.run(worker._process_runtime(None, fake_supabase.tables["bot_runtimes"][0]))

    runtime = fake_supabase.tables["bot_runtimes"][0]
    execution_events = fake_supabase.tables["bot_execution_events"]

    assert runtime["status"] == "stopped"
    assert fake_pacifica.orders == []
    assert runtime["risk_policy_json"]["_runtime_state"]["drawdown_amount_usd"] == 41.0
    assert runtime["risk_policy_json"]["_runtime_state"]["drawdown_pct"] == 20.5
    assert execution_events[-1]["event_type"] == "runtime.stopped"
    assert "allocated drawdown budget" in execution_events[-1]["decision_summary"]


def test_runtime_worker_skips_market_evaluation_for_entry_only_bot_at_position_capacity() -> None:
    tables = _seed_tables()
    tables["bot_runtimes"][0]["risk_policy_json"]["max_open_positions"] = 1
    tables["bot_runtimes"][0]["risk_policy_json"]["_runtime_state"] = {
        "managed_positions": {
            "BTC": {
                "symbol": "BTC",
                "amount": 0.005,
                "side": "bid",
                "entry_client_order_id": "entry-1",
                "entry_price": 101000,
                "opened_at": "2026-03-16T00:05:00+00:00",
                "updated_at": "2026-03-16T00:05:00+00:00",
            }
        }
    }

    fake_supabase = FakeSupabaseRestClient(tables)
    fake_pacifica = FakePacificaClient(
        positions=[
            {
                "symbol": "BTC-PERP",
                "amount": 0.005,
                "side": "bid",
                "entry_price": 101000,
                "mark_price": 105000,
                "created_at": "2026-03-16T00:05:00+00:00",
                "updated_at": "2026-03-16T00:06:00+00:00",
            }
        ]
    )
    fake_indicator_context = FakeIndicatorContextService()
    worker = BotRuntimeWorker(poll_interval_seconds=0.01)
    worker._supabase = fake_supabase
    worker._engine._supabase = fake_supabase
    worker._auth = FakeAuthService()
    worker._pacifica = fake_pacifica
    worker._indicator_context = fake_indicator_context
    worker._calculate_runtime_performance = _fake_runtime_performance  # type: ignore[method-assign]

    asyncio.run(worker._process_runtime(None, fake_supabase.tables["bot_runtimes"][0]))

    assert fake_pacifica.market_requests == 0
    assert fake_indicator_context.load_requests == 0
    assert fake_pacifica.orders == []
    assert fake_supabase.tables["bot_execution_events"] == []


def test_runtime_worker_allows_new_entry_when_live_position_is_unmanaged() -> None:
    tables = _seed_tables()
    tables["bot_runtimes"][0]["risk_policy_json"]["max_open_positions"] = 1
    tables["bot_runtimes"][0]["risk_policy_json"]["allowed_symbols"] = ["BTC", "ETH", "SOL"]

    fake_supabase = FakeSupabaseRestClient(tables)
    fake_pacifica = FakePacificaClient(
        positions=[
            {
                "symbol": "ETH",
                "amount": 0.25,
                "side": "ask",
                "entry_price": 2200,
                "mark_price": 2190,
                "created_at": "2026-03-16T00:05:00+00:00",
                "updated_at": "2026-03-16T00:06:00+00:00",
            }
        ]
    )
    worker = BotRuntimeWorker(poll_interval_seconds=0.01)
    worker._supabase = fake_supabase
    worker._engine._supabase = fake_supabase
    worker._auth = FakeAuthService()
    worker._pacifica = fake_pacifica
    worker._indicator_context = FakeIndicatorContextService()
    worker._calculate_runtime_performance = _fake_runtime_performance  # type: ignore[method-assign]

    asyncio.run(worker._process_runtime(None, fake_supabase.tables["bot_runtimes"][0]))

    assert len(fake_pacifica.orders) == 2
    assert fake_pacifica.orders[0]["type"] == "update_leverage"
    assert fake_pacifica.orders[1]["symbol"] == "BTC"
    assert fake_pacifica.orders[1]["side"] == "bid"
    assert fake_supabase.tables["bot_execution_events"][-1]["event_type"] == "action.executed"


def test_runtime_worker_builds_rules_position_lookup_from_managed_positions_only() -> None:
    worker = BotRuntimeWorker(poll_interval_seconds=0.01)

    position_lookup = worker._build_managed_position_lookup(
        runtime_state={
            "managed_positions": {
                "BTC": {
                    "symbol": "BTC",
                    "amount": 0.005,
                    "side": "bid",
                    "entry_price": 101000,
                }
            }
        },
        live_position_lookup={
            "BTC": {
                "symbol": "BTC",
                "amount": 0.25,
                "side": "bid",
                "entry_price": 100500,
                "mark_price": 105000,
                "unrealized_pnl": 123.45,
            },
            "SOL": {
                "symbol": "SOL",
                "amount": 5.0,
                "side": "ask",
                "entry_price": 150,
                "mark_price": 149,
            },
        },
    )

    assert set(position_lookup) == {"BTC"}
    assert position_lookup["BTC"]["amount"] == 0.005
    assert position_lookup["BTC"]["entry_price"] == 101000
    assert position_lookup["BTC"]["mark_price"] == 105000
    assert position_lookup["BTC"]["unrealized_pnl"] == 123.45


def test_runtime_worker_skips_market_evaluation_for_unrelated_entry_plus_tpsl_routes_at_position_capacity() -> None:
    tables = _seed_tables()
    tables["bot_definitions"][0]["rules_json"] = {
        "conditions": [{"type": "price_below", "symbol": "ETH", "value": 100000}],
        "actions": [
            {"type": "open_long", "symbol": "ETH", "size_usd": 200, "leverage": 3},
            {"type": "set_tpsl", "symbol": "ETH", "take_profit_pct": 2, "stop_loss_pct": 1},
        ],
    }
    tables["bot_runtimes"][0]["risk_policy_json"]["max_open_positions"] = 1
    tables["bot_runtimes"][0]["risk_policy_json"]["_runtime_state"] = {
        "managed_positions": {
            "BTC": {
                "symbol": "BTC",
                "amount": 0.005,
                "side": "bid",
                "entry_client_order_id": "entry-1",
                "entry_price": 101000,
                "opened_at": "2026-03-16T00:05:00+00:00",
                "updated_at": "2026-03-16T00:05:00+00:00",
            }
        }
    }

    fake_supabase = FakeSupabaseRestClient(tables)
    fake_pacifica = FakePacificaClient(
        positions=[
            {
                "symbol": "BTC-PERP",
                "amount": 0.005,
                "side": "bid",
                "entry_price": 101000,
                "mark_price": 105000,
                "created_at": "2026-03-16T00:05:00+00:00",
                "updated_at": "2026-03-16T00:06:00+00:00",
            }
        ]
    )
    fake_indicator_context = FakeIndicatorContextService()
    worker = BotRuntimeWorker(poll_interval_seconds=0.01)
    worker._supabase = fake_supabase
    worker._engine._supabase = fake_supabase
    worker._auth = FakeAuthService()
    worker._pacifica = fake_pacifica
    worker._indicator_context = fake_indicator_context
    worker._calculate_runtime_performance = _fake_runtime_performance  # type: ignore[method-assign]

    asyncio.run(worker._process_runtime(None, fake_supabase.tables["bot_runtimes"][0]))

    assert fake_pacifica.market_requests == 0
    assert fake_indicator_context.load_requests == 0
    assert fake_pacifica.orders == []
    assert fake_supabase.tables["bot_execution_events"] == []


def test_runtime_worker_prunes_triggered_actions_for_unmanaged_symbols_when_capacity_is_full() -> None:
    worker = BotRuntimeWorker(poll_interval_seconds=0.01)

    actions = worker._prune_triggered_actions(
        actions=[
            {"type": "open_short", "symbol": "XMR", "size_usd": 75, "leverage": 8},
            {"type": "set_tpsl", "symbol": "XMR", "take_profit_pct": 1.5, "stop_loss_pct": 0.7},
            {"type": "set_tpsl", "symbol": "BTC", "take_profit_pct": 1.5, "stop_loss_pct": 0.7},
        ],
        runtime_policy={"max_open_positions": 1},
        runtime_state={
            "managed_positions": {
                "BTC": {
                    "symbol": "BTC",
                    "amount": 0.005,
                    "side": "bid",
                }
            }
        },
        position_lookup={},
        open_order_lookup={},
    )

    assert actions == [
        {"type": "set_tpsl", "symbol": "BTC", "take_profit_pct": 1.5, "stop_loss_pct": 0.7},
    ]


def test_runtime_worker_drops_tpsl_for_pending_symbol_without_managed_position() -> None:
    worker = BotRuntimeWorker(poll_interval_seconds=0.01)

    actions = worker._prune_triggered_actions(
        actions=[
            {"type": "set_tpsl", "symbol": "ETH", "take_profit_pct": 2.0, "stop_loss_pct": 1.0},
        ],
        runtime_policy={"max_open_positions": 1},
        runtime_state={"pending_entry_symbols": {"ETH": "2026-04-14T00:00:00+00:00"}},
        position_lookup={},
        open_order_lookup={},
    )

    assert actions == []


def test_runtime_worker_drops_duplicate_tpsl_when_position_is_already_protected() -> None:
    worker = BotRuntimeWorker(poll_interval_seconds=0.01)

    actions = worker._prune_triggered_actions(
        actions=[
            {"type": "set_tpsl", "symbol": "BTC", "take_profit_pct": 2.0, "stop_loss_pct": 1.0},
        ],
        runtime_policy={"max_open_positions": 1},
        runtime_state={
            "managed_positions": {
                "BTC": {
                    "symbol": "BTC",
                    "amount": 0.005,
                    "side": "bid",
                    "take_profit_client_order_id": "tp-1",
                    "stop_loss_client_order_id": "sl-1",
                }
            }
        },
        position_lookup={"BTC": {"symbol": "BTC", "amount": 0.005}},
        open_order_lookup={
            "BTC": [
                {"symbol": "BTC", "reduce_only": True, "client_order_id": "tp-1"},
                {"symbol": "BTC", "reduce_only": True, "client_order_id": "sl-1"},
            ]
        },
    )

    assert actions == []


def test_runtime_worker_deduplicates_identical_skip_events_within_recent_window() -> None:
    fake_supabase = FakeSupabaseRestClient(_seed_tables())
    worker = BotRuntimeWorker(poll_interval_seconds=0.01)
    worker._supabase = fake_supabase

    fake_supabase.insert(
        "bot_execution_events",
        {
            "id": "event-skip-1",
            "runtime_id": "runtime-1",
            "event_type": "action.skipped",
            "decision_summary": "idem:runtime-1:skip",
            "request_payload": {"type": "open_long", "symbol": "BTC"},
            "result_payload": {"issues": ["max_open_positions 1 reached"]},
            "status": "skipped",
            "error_reason": None,
            "created_at": datetime.now(tz=UTC).isoformat(),
        },
    )

    should_record = worker._should_record_skip_event(
        runtime_id="runtime-1",
        decision_summary="idem:runtime-1:skip",
        request_payload={"type": "open_long", "symbol": "BTC"},
        result_payload={"issues": ["max_open_positions 1 reached"]},
    )

    assert should_record is False


def test_runtime_worker_batches_bot_definition_reads_per_iteration(monkeypatch: Any) -> None:
    tables = _seed_tables()
    tables["bot_definitions"].append(
        {
            "id": "bot-2",
            "user_id": "user-1",
            "wallet_address": "wallet-1",
            "name": "Second Bot",
            "description": "Batch read test",
            "visibility": "private",
            "market_scope": "Pacifica perpetuals",
            "strategy_type": "rules",
            "authoring_mode": "visual",
            "rules_version": 1,
            "rules_json": _graph_rules(),
            "created_at": "2026-03-16T00:00:00+00:00",
            "updated_at": "2026-03-16T00:00:00+00:00",
        }
    )
    tables["bot_runtimes"].append(
        {
            "id": "runtime-2",
            "bot_definition_id": "bot-2",
            "user_id": "user-1",
            "wallet_address": "wallet-1",
            "status": "active",
            "mode": "live",
            "risk_policy_json": {"_runtime_state": {}},
            "deployed_at": "2026-03-16T00:00:00+00:00",
            "stopped_at": None,
            "updated_at": "2026-03-16T00:00:00+00:00",
        }
    )
    fake_supabase = CountingFakeSupabaseRestClient(tables)
    worker = BotRuntimeWorker(poll_interval_seconds=0.01)
    worker._supabase = fake_supabase
    worker._engine._supabase = fake_supabase

    class _FakeCoordination:
        def try_claim_lease(self, lease_key: str, *, ttl_seconds: int) -> bool:
            del lease_key, ttl_seconds
            return True

        def release_lease(self, lease_key: str) -> None:
            del lease_key

    seen_bots: list[str] = []

    async def _fake_process_runtime(
        db: Any,
        runtime: dict[str, Any],
        *,
        bot: dict[str, Any] | None = None,
        bot_loaded: bool = False,
        **_: Any,
    ) -> None:
        del db, runtime
        assert bot_loaded is True
        seen_bots.append(str((bot or {}).get("id") or ""))

    async def _stop_after_iteration(delay: float) -> None:
        del delay
        worker._running = False

    worker._coordination = _FakeCoordination()  # type: ignore[assignment]
    worker._process_runtime = _fake_process_runtime  # type: ignore[method-assign]
    worker._running = True
    monkeypatch.setattr("src.workers.bot_runtime_worker.asyncio.sleep", _stop_after_iteration)

    asyncio.run(worker.run_forever())

    bot_definition_selects = [call for call in fake_supabase.select_calls if call[0] == "bot_definitions"]
    bot_definition_reads = [call for call in fake_supabase.maybe_one_calls if call[0] == "bot_definitions"]

    assert len(bot_definition_selects) == 1
    assert bot_definition_reads == []
    assert seen_bots == ["bot-1", "bot-2"]


def test_runtime_worker_idempotency_key_tracks_execution_state_not_fixed_time_bucket() -> None:
    worker = BotRuntimeWorker(poll_interval_seconds=0.01)

    action = {"type": "open_long", "symbol": "BTC", "size_usd": 100, "leverage": 2}
    first_key = worker._build_idempotency_key(
        runtime_id="runtime-1",
        action=action,
        runtime_state={"executions_total": 0, "failures_total": 0, "last_executed_at": ""},
        position_lookup={},
    )
    second_key = worker._build_idempotency_key(
        runtime_id="runtime-1",
        action=action,
        runtime_state={"executions_total": 1, "failures_total": 0, "last_executed_at": "2026-03-17T00:00:00+00:00"},
        position_lookup={},
    )

    assert first_key != second_key


def test_trading_service_places_orders_with_normalized_perp_market_symbols() -> None:
    service = TradingService()
    fake_pacifica = FakePacificaClient()
    service.pacifica = fake_pacifica
    service.auth_service = FakeAuthService()

    def fake_upsert_user(db: Any, wallet_address: str) -> dict[str, str]:
        del db, wallet_address
        return {"id": "user-1"}

    def fake_record_audit_event(
        db: Any,
        *,
        user_id: str,
        action: str,
        payload: dict[str, Any],
    ) -> None:
        del db, user_id, action, payload

    async def fake_account_snapshot(db: Any, wallet_address: str) -> dict[str, Any]:
        del db
        return {"user_id": "user-1", "wallet_address": wallet_address}

    async def fake_publish_snapshot(
        *,
        user_id: str,
        event: str,
        payload: dict[str, Any],
        snapshot: dict[str, Any],
    ) -> None:
        del user_id, event, payload, snapshot

    service._upsert_user = fake_upsert_user  # type: ignore[method-assign]
    service._record_audit_event = fake_record_audit_event  # type: ignore[method-assign]
    service.get_account_snapshot = fake_account_snapshot  # type: ignore[method-assign]
    service._publish_snapshot = fake_publish_snapshot  # type: ignore[method-assign]

    result = asyncio.run(
        service.place_order(
            None,
            wallet_address="wallet-1",
            symbol="BTC",
            side="long",
            order_type="market",
            leverage=3,
            size_usd=200,
        )
    )

    assert result["status"] == "submitted"
    assert fake_pacifica.orders[0]["type"] == "update_leverage"
    assert fake_pacifica.orders[1]["symbol"] == "BTC"
    assert fake_pacifica.orders[1]["side"] == "bid"
    assert fake_pacifica.orders[1]["amount"] == 0.005


def test_runtime_worker_executes_limit_order_action_directly() -> None:
    worker = BotRuntimeWorker(poll_interval_seconds=0.01)
    fake_pacifica = FakePacificaClient()
    worker._pacifica = fake_pacifica

    response = asyncio.run(
        worker._execute_action(
            action={
                "type": "place_limit_order",
                "symbol": "BTC",
                "side": "long",
                "price": 100000,
                "size_usd": 200,
                "leverage": 2,
                "tif": "GTC",
            },
            credentials={
                "account_address": "wallet-1",
                "agent_wallet_address": "agent-1",
                "agent_private_key": "secret",
            },
            market_lookup={"BTC": {"mark_price": 105000, "lot_size": 0.001, "min_order_size": 0.001, "tick_size": 0.5}},
            position_lookup={},
        )
    )

    assert response["status"] == "submitted"
    assert [order["type"] for order in fake_pacifica.orders] == ["update_leverage", "create_order"]
    assert fake_pacifica.orders[1]["price"] == 100000
    assert fake_pacifica.orders[1]["side"] == "bid"
    assert "tick_level" not in fake_pacifica.orders[1]


def test_runtime_worker_rejects_leverage_above_market_max() -> None:
    worker = BotRuntimeWorker(poll_interval_seconds=0.01)
    worker._pacifica = FakePacificaClient()

    try:
        asyncio.run(
            worker._execute_action(
                action={"type": "open_long", "symbol": "BTC", "size_usd": 105.0, "leverage": 6},
                credentials={
                    "account_address": "wallet-1",
                    "agent_wallet_address": "agent-1",
                    "agent_private_key": "secret",
                },
                market_lookup={"BTC": {"mark_price": 105000, "lot_size": 0.001, "max_leverage": 5}},
                position_lookup={},
            )
        )
    except ValueError as exc:
        assert str(exc) == "Requested leverage 6 exceeds BTC market max leverage 5."
    else:
        raise AssertionError("Expected market leverage guard to reject the action")


def test_runtime_worker_enriches_cancel_order_with_open_order_metadata() -> None:
    worker = BotRuntimeWorker(poll_interval_seconds=0.01)
    fake_pacifica = FakePacificaClient()
    worker._pacifica = fake_pacifica

    response = asyncio.run(
        worker._execute_action(
            action={"type": "cancel_order", "symbol": "BTC", "order_id": 101},
            credentials={
                "account_address": "wallet-1",
                "agent_wallet_address": "agent-1",
                "agent_private_key": "secret",
            },
            market_lookup={"BTC": {"mark_price": 105000, "lot_size": 0.001, "tick_size": 0.5}},
            position_lookup={},
            open_order_lookup={
                "BTC": [
                    {"symbol": "BTC", "order_id": 101, "side": "bid", "price": 100000, "tick_level": 200000}
                ]
            },
        )
    )

    assert response["status"] == "submitted"
    assert fake_pacifica.orders[0]["order_id"] == 101
    assert fake_pacifica.orders[0]["side"] == "bid"
    assert fake_pacifica.orders[0]["tick_level"] == 200000


def test_runtime_worker_executes_twap_and_cancel_actions_directly() -> None:
    worker = BotRuntimeWorker(poll_interval_seconds=0.01)
    fake_pacifica = FakePacificaClient()
    worker._pacifica = fake_pacifica

    asyncio.run(
        worker._execute_action(
            action={
                "type": "place_twap_order",
                "symbol": "BTC",
                "side": "short",
                "size_usd": 150,
                "leverage": 3,
                "duration_seconds": 180,
                "slippage_percent": 0.5,
            },
            credentials={
                "account_address": "wallet-1",
                "agent_wallet_address": "agent-1",
                "agent_private_key": "secret",
            },
            market_lookup={"BTC": {"mark_price": 105000, "lot_size": 0.001, "min_order_size": 0.001}},
            position_lookup={},
        )
    )
    asyncio.run(
        worker._execute_action(
            action={
                "type": "cancel_all_orders",
                "all_symbols": True,
                "exclude_reduce_only": False,
            },
            credentials={
                "account_address": "wallet-1",
                "agent_wallet_address": "agent-1",
                "agent_private_key": "secret",
            },
            market_lookup={"BTC": {"mark_price": 105000, "lot_size": 0.001, "min_order_size": 0.001}},
            position_lookup={},
        )
    )

    assert [order["type"] for order in fake_pacifica.orders] == [
        "update_leverage",
        "create_twap_order",
        "cancel_all_orders",
    ]
    assert fake_pacifica.orders[1]["side"] == "ask"
    assert fake_pacifica.orders[1]["duration_in_seconds"] == 180
    assert fake_pacifica.orders[2]["all_symbols"] is True
