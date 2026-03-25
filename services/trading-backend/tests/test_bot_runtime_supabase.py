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

    def update(
        self,
        table: str,
        values: dict[str, Any],
        *,
        filters: dict[str, Any],
    ) -> list[dict[str, Any]]:
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
                if operator != "eq" or row.get(key) != operand:
                    return False
                continue
            if row.get(key) != expected:
                return False
        return True


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
    fake_supabase = FakeSupabaseRestClient(tables)
    service = BotBuilderService()
    service.supabase = fake_supabase

    service.delete_bot(None, bot_id="bot-1", wallet_address="wallet-1")

    assert fake_supabase.tables["bot_definitions"] == []
    assert fake_supabase.tables["bot_runtimes"] == []
    assert fake_supabase.tables["bot_execution_events"] == []


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


def test_list_runtime_events_returns_empty_list_when_runtime_is_missing() -> None:
    tables = _seed_tables()
    tables["bot_runtimes"] = []
    fake_supabase = FakeSupabaseRestClient(tables)
    engine = BotRuntimeEngine()
    engine._supabase = fake_supabase

    events = engine.list_runtime_events(None, bot_id="bot-1", wallet_address="wallet-1", user_id="user-1", limit=100)

    assert events == []


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
    assert fake_pacifica.orders[1]["amount"] == 0.005
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
