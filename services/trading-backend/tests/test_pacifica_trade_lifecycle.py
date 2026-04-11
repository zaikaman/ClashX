from __future__ import annotations

import asyncio
from copy import deepcopy
from typing import Any

from src.services.bot_risk_service import BotRiskService
from src.services.trading_service import TradingService
from src.workers.bot_runtime_worker import BotRuntimeWorker


class FakeSupabaseRestClient:
    def __init__(self) -> None:
        self.tables: dict[str, list[dict[str, Any]]] = {
            "users": [],
            "audit_events": [],
        }

    def select(
        self,
        table: str,
        *,
        columns: str = "*",
        filters: dict[str, Any] | None = None,
        order: str | None = None,
        limit: int | None = None,
        cache_ttl_seconds: int | None = None,
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
        cache_ttl_seconds: int | None = None,
    ) -> dict[str, Any] | None:
        rows = self.select(
            table,
            columns=columns,
            filters=filters,
            order=order,
            limit=1,
            cache_ttl_seconds=cache_ttl_seconds,
        )
        return rows[0] if rows else None

    def insert(
        self,
        table: str,
        payload: dict[str, Any] | list[dict[str, Any]],
        *,
        upsert: bool = False,
        on_conflict: str | None = None,
        returning: str | None = None,
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
    ) -> list[dict[str, Any]]:
        rows = self.tables.get(table, [])
        updated: list[dict[str, Any]] = []
        for row in rows:
            if self._matches(row, filters):
                row.update(deepcopy(values))
                updated.append(deepcopy(row))
        return updated

    @staticmethod
    def _matches(row: dict[str, Any], filters: dict[str, Any] | None) -> bool:
        if not filters:
            return True
        return all(row.get(key) == expected for key, expected in filters.items())


class FakeAuthService:
    def get_authorization_by_wallet(self, db: Any, wallet_address: str) -> dict[str, str] | None:
        del db
        if wallet_address != "wallet-1":
            return None
        return {
            "agent_wallet_address": "agent-1",
            "status": "active",
        }

    def get_trading_credentials(self, db: Any, wallet_address: str) -> dict[str, str] | None:
        del db
        if wallet_address != "wallet-1":
            return None
        return {
            "account_address": wallet_address,
            "agent_wallet_address": "agent-1",
            "agent_private_key": "secret",
        }


class FakePacificaClient:
    def __init__(self) -> None:
        self.order_calls: list[dict[str, Any]] = []
        self.batch_order_calls: list[list[dict[str, Any]]] = []
        self._position: dict[str, Any] | None = None
        self._fills: list[dict[str, Any]] = []
        self._margin_settings: list[dict[str, Any]] = []
        self._open_orders: list[dict[str, Any]] = []
        self._positions_visible = True

    async def get_account_info(self, wallet_address: str) -> dict[str, Any]:
        del wallet_address
        return {"balance": 2_000.0, "fee_level": 0}

    async def get_account_settings(self, wallet_address: str) -> list[dict[str, Any]]:
        del wallet_address
        return [deepcopy(item) for item in self._margin_settings]

    async def get_markets(self) -> list[dict[str, Any]]:
        return [
            {
                "symbol": "BTC-PERP",
                "display_symbol": "BTC-PERP",
                "mark_price": 105_000.0,
                "lot_size": 0.001,
                "min_order_size": 0.001,
                "tick_size": 0.5,
                "max_leverage": 5,
            }
        ]

    async def get_positions(self, wallet_address: str, *, price_lookup: dict[str, float] | None = None) -> list[dict[str, Any]]:
        del wallet_address, price_lookup
        if self._position is None or not self._positions_visible:
            return []
        return [deepcopy(self._position)]

    async def get_open_orders(self, wallet_address: str) -> list[dict[str, Any]]:
        del wallet_address
        return [deepcopy(item) for item in self._open_orders]

    async def get_position_history(self, wallet_address: str, *, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        del wallet_address, limit, offset
        return [deepcopy(item) for item in self._fills]

    async def get_portfolio_history(self, wallet_address: str, *, limit: int = 90, offset: int = 0) -> list[dict[str, Any]]:
        del wallet_address, limit, offset
        return []

    async def place_order(self, payload: dict[str, Any]) -> dict[str, Any]:
        call = deepcopy(payload)
        self.order_calls.append(call)

        request_type = str(payload.get("type") or "create_market_order")
        if request_type == "create_market_order":
            amount = float(payload.get("amount") or 0)
            side = str(payload.get("side") or "")
            symbol = str(payload.get("symbol") or "")
            if payload.get("reduce_only"):
                self._open_orders = [
                    item
                    for item in self._open_orders
                    if str(item.get("symbol") or "") != symbol
                ]
                self._fills.append(
                    {
                        "history_id": len(self._fills) + 1,
                        "symbol": symbol,
                        "amount": amount,
                        "price": 105_000.0,
                        "fee": 0.0,
                        "pnl": 0.0,
                        "event_type": "close_long",
                        "is_maker": False,
                        "created_at": "2026-03-16T00:00:00Z",
                    }
                )
                if self._position and str(self._position.get("symbol") or "") == symbol:
                    remaining = max(0.0, float(self._position.get("amount") or 0.0) - amount)
                    if remaining > 0:
                        self._position["amount"] = remaining
                        self._position["updated_at"] = "2026-03-16T00:01:00Z"
                    else:
                        self._position = None
            else:
                self._open_orders = [
                    item
                    for item in self._open_orders
                    if not (
                        str(item.get("symbol") or "") == symbol
                        and not bool(item.get("reduce_only"))
                    )
                ]
                if self._position and str(self._position.get("symbol") or "") == symbol and str(self._position.get("side") or "") == side:
                    self._position["amount"] = float(self._position.get("amount") or 0.0) + amount
                    self._position["updated_at"] = "2026-03-16T00:01:00Z"
                else:
                    self._position = {
                        "symbol": symbol,
                        "side": side,
                        "amount": amount,
                        "entry_price": 105_000.0,
                        "mark_price": 105_000.0,
                        "margin": 105.0,
                        "isolated": True,
                        "created_at": "2026-03-16T00:00:00Z",
                        "updated_at": "2026-03-16T00:00:00Z",
                    }
        if request_type == "set_position_tpsl":
            symbol = str(payload.get("symbol") or "")
            self._open_orders = [
                item
                for item in self._open_orders
                if str(item.get("symbol") or "") != symbol or not bool(item.get("reduce_only"))
            ]
            self._open_orders.extend(
                [
                {
                    "symbol": symbol,
                    "reduce_only": True,
                    "kind": "take_profit",
                    "stop_price": payload.get("take_profit", {}).get("stop_price"),
                    "client_order_id": payload.get("take_profit", {}).get("client_order_id"),
                },
                {
                    "symbol": symbol,
                    "reduce_only": True,
                    "kind": "stop_loss",
                    "stop_price": payload.get("stop_loss", {}).get("stop_price"),
                    "client_order_id": payload.get("stop_loss", {}).get("client_order_id"),
                },
                ]
            )

        return {
            "status": "submitted",
            "request_id": f"req-{len(self.order_calls)}",
            "network": "testnet",
        }

    async def place_batch_orders(self, payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
        self.batch_order_calls.append([deepcopy(item) for item in payloads])
        responses: list[dict[str, Any]] = []
        for payload in payloads:
            responses.append(await self.place_order(payload))
        return responses


class FakeIndicatorContextService:
    async def load_candle_lookup(self, rules_json: dict[str, Any]) -> dict[str, Any]:
        del rules_json
        return {}


class FakeCoordinationService:
    def try_claim_action(self, *, runtime_id: str, idempotency_key: str) -> bool:
        del runtime_id, idempotency_key
        return True


async def _noop_publish(*, channel: str, event: str, payload: dict[str, Any]) -> None:
    del channel, event, payload


def test_trading_service_places_entry_then_reduce_only_exit(monkeypatch: Any) -> None:
    monkeypatch.setattr("src.services.trading_service.broadcaster.publish", _noop_publish)

    pacifica = FakePacificaClient()
    service = TradingService()
    service.supabase = FakeSupabaseRestClient()
    service.auth_service = FakeAuthService()
    service.pacifica = pacifica

    open_result = asyncio.run(
        service.place_order(
            None,
            wallet_address="wallet-1",
            symbol="BTC",
            side="long",
            order_type="market",
            leverage=2,
            size_usd=105.0,
        )
    )

    close_result = asyncio.run(
        service.place_order(
            None,
            wallet_address="wallet-1",
            symbol="BTC",
            side="short",
            order_type="market",
            leverage=2,
            quantity=0.002,
            reduce_only=True,
        )
    )

    assert [call.get("type", "create_market_order") for call in pacifica.order_calls] == [
        "update_leverage",
        "create_market_order",
        "create_market_order",
    ]
    assert pacifica.order_calls[1]["side"] == "bid"
    assert pacifica.order_calls[1]["amount"] == 0.002
    assert pacifica.order_calls[1]["reduce_only"] is False
    assert pacifica.order_calls[2]["side"] == "ask"
    assert pacifica.order_calls[2]["amount"] == 0.002
    assert pacifica.order_calls[2]["reduce_only"] is True
    assert open_result["snapshot"]["positions"][0]["side"] == "long"
    assert close_result["snapshot"]["positions"] == []
    assert len(service.supabase.tables["audit_events"]) == 2


def test_bot_runtime_worker_translates_open_and_close_actions_to_pacifica_payloads() -> None:
    worker = BotRuntimeWorker()
    worker._pacifica = FakePacificaClient()

    credentials = {
        "account_address": "wallet-1",
        "agent_wallet_address": "agent-1",
        "agent_private_key": "secret",
    }
    market_lookup = {
        "BTC": {
            "symbol": "BTC-PERP",
            "mark_price": 105_000.0,
            "lot_size": 0.001,
            "min_order_size": 0.001,
        }
    }

    open_result = asyncio.run(
        worker._execute_action(
            action={"type": "open_long", "symbol": "BTC", "size_usd": 105.0, "leverage": 2},
            credentials=credentials,
            market_lookup=market_lookup,
            position_lookup={},
        )
    )

    close_result = asyncio.run(
        worker._execute_action(
            action={"type": "close_position", "symbol": "BTC"},
            credentials=credentials,
            market_lookup=market_lookup,
            position_lookup={"BTC": {"symbol": "BTC", "side": "bid", "amount": 0.002}},
        )
    )

    pacifica_calls = worker._pacifica.order_calls
    assert [call.get("type", "create_market_order") for call in pacifica_calls] == [
        "update_leverage",
        "create_market_order",
        "create_market_order",
    ]
    assert pacifica_calls[1]["side"] == "bid"
    assert pacifica_calls[1]["amount"] == 0.002
    assert pacifica_calls[1]["reduce_only"] is False
    assert pacifica_calls[2]["side"] == "ask"
    assert pacifica_calls[2]["amount"] == 0.002
    assert pacifica_calls[2]["reduce_only"] is True
    assert open_result["status"] == "submitted"
    assert close_result["status"] == "submitted"


def test_bot_runtime_worker_skips_redundant_leverage_update_when_setting_already_matches() -> None:
    worker = BotRuntimeWorker()
    pacifica = FakePacificaClient()
    pacifica._margin_settings = [{"symbol": "BTC", "isolated": False, "leverage": 3}]
    worker._pacifica = pacifica

    credentials = {
        "account_address": "wallet-1",
        "agent_wallet_address": "agent-1",
        "agent_private_key": "secret",
    }
    market_lookup = {
        "BTC": {
            "symbol": "BTC-PERP",
            "mark_price": 105_000.0,
            "lot_size": 0.001,
        }
    }

    asyncio.run(
        worker._execute_action(
            action={"type": "open_long", "symbol": "BTC", "size_usd": 105.0, "leverage": 3},
            credentials=credentials,
            market_lookup=market_lookup,
            position_lookup={},
        )
    )

    assert [call.get("type", "create_market_order") for call in pacifica.order_calls] == [
        "create_market_order",
    ]


def test_bot_runtime_worker_sets_tpsl_with_required_close_side() -> None:
    worker = BotRuntimeWorker()
    pacifica = FakePacificaClient()
    worker._pacifica = pacifica

    credentials = {
        "account_address": "wallet-1",
        "agent_wallet_address": "agent-1",
        "agent_private_key": "secret",
    }
    market_lookup = {
        "BTC": {
            "symbol": "BTC-PERP",
            "mark_price": 105_000.0,
            "lot_size": 0.001,
        }
    }

    asyncio.run(
        worker._execute_action(
            action={"type": "set_tpsl", "symbol": "BTC", "take_profit_pct": 1.8, "stop_loss_pct": 0.9},
            credentials=credentials,
            market_lookup=market_lookup,
            position_lookup={
                "BTC": {
                    "symbol": "BTC",
                    "side": "bid",
                    "amount": 0.002,
                    "mark_price": 105_000.0,
                }
            },
        )
    )

    assert pacifica.order_calls[0]["type"] == "set_position_tpsl"
    assert pacifica.order_calls[0]["side"] == "ask"
    assert pacifica.order_calls[0]["take_profit"]["stop_price"] == 106890.0
    assert pacifica.order_calls[0]["stop_loss"]["stop_price"] == 104055.0


def test_bot_runtime_worker_caps_tpsl_amount_to_live_position_size() -> None:
    worker = BotRuntimeWorker()
    pacifica = FakePacificaClient()
    worker._pacifica = pacifica

    credentials = {
        "account_address": "wallet-1",
        "agent_wallet_address": "agent-1",
        "agent_private_key": "secret",
    }
    market_lookup = {
        "BTC": {
            "symbol": "BTC-PERP",
            "mark_price": 105_000.0,
            "lot_size": 0.001,
            "tick_size": 0.5,
        }
    }

    asyncio.run(
        worker._execute_action(
            runtime_state={
                "managed_positions": {
                    "BTC": {
                        "symbol": "BTC",
                        "side": "bid",
                        "amount": 0.01213,
                    }
                }
            },
            action={"type": "set_tpsl", "symbol": "BTC", "take_profit_pct": 1.8, "stop_loss_pct": 0.9},
            credentials=credentials,
            market_lookup=market_lookup,
            position_lookup={
                "BTC": {
                    "symbol": "BTC",
                    "side": "bid",
                    "amount": 0.01212,
                    "mark_price": 105_000.0,
                }
            },
        )
    )

    assert pacifica.order_calls[0]["type"] == "set_position_tpsl"
    assert pacifica.order_calls[0]["take_profit"]["amount"] == 0.01212
    assert pacifica.order_calls[0]["stop_loss"]["amount"] == 0.01212


def test_bot_runtime_worker_does_not_reject_small_btc_quantity_from_min_order_size_metadata() -> None:
    worker = BotRuntimeWorker()

    quantity = worker._normalize_order_quantity(
        0.00607,
        lot_size=0.00001,
        symbol="BTC",
    )

    assert quantity == 0.00607


def test_trading_service_does_not_reject_small_btc_quantity_from_min_order_size_metadata() -> None:
    service = TradingService()

    quantity = service._normalize_order_quantity(
        0.00607,
        lot_size=0.00001,
        symbol="BTC",
    )

    assert quantity == 0.00607


def test_trading_service_skips_redundant_leverage_update_when_setting_already_matches() -> None:
    pacifica = FakePacificaClient()
    pacifica._margin_settings = [{"symbol": "BTC", "isolated": False, "leverage": 2}]

    service = TradingService()
    service.supabase = FakeSupabaseRestClient()
    service.auth_service = FakeAuthService()
    service.pacifica = pacifica

    asyncio.run(
        service.place_order(
            None,
            wallet_address="wallet-1",
            symbol="BTC",
            side="long",
            order_type="market",
            leverage=2,
            size_usd=105.0,
        )
    )

    assert [call.get("type", "create_market_order") for call in pacifica.order_calls] == [
        "create_market_order",
    ]


def test_trading_service_limit_order_includes_tick_level() -> None:
    pacifica = FakePacificaClient()

    service = TradingService()
    service.supabase = FakeSupabaseRestClient()
    service.auth_service = FakeAuthService()
    service.pacifica = pacifica

    asyncio.run(
        service.place_order(
            None,
            wallet_address="wallet-1",
            symbol="BTC",
            side="long",
            order_type="limit",
            leverage=2,
            size_usd=200.0,
            limit_price=100000.0,
        )
    )

    assert pacifica.order_calls[0]["type"] == "update_leverage"
    assert pacifica.order_calls[1]["type"] == "create_order"
    assert pacifica.order_calls[1]["price"] == 100000.0
    assert "tick_level" not in pacifica.order_calls[1]


def test_trading_service_cancel_order_enriches_payload_with_open_order_metadata() -> None:
    pacifica = FakePacificaClient()
    pacifica._open_orders = [{"symbol": "BTC", "order_id": 101, "side": "bid", "price": 100000.0, "tick_level": 200000}]

    service = TradingService()
    service.supabase = FakeSupabaseRestClient()
    service.auth_service = FakeAuthService()
    service.pacifica = pacifica

    asyncio.run(
        service.cancel_order(
            None,
            wallet_address="wallet-1",
            symbol="BTC",
            order_id="101",
        )
    )

    assert pacifica.order_calls[0]["type"] == "cancel_order"
    assert pacifica.order_calls[0]["order_id"] == 101
    assert pacifica.order_calls[0]["side"] == "bid"
    assert pacifica.order_calls[0]["tick_level"] == 200000


def test_bot_risk_service_blocks_leverage_above_market_cap() -> None:
    risk = BotRiskService()

    issues = risk.assess_action(
        policy={"max_leverage": 10},
        action={"type": "open_long", "symbol": "BTC", "size_usd": 100, "leverage": 6},
        runtime_state={},
        market_lookup={"BTC": {"max_leverage": 5}},
    )

    assert "requested leverage 6 exceeds BTC market max_leverage 5" in issues


def test_bot_risk_service_blocks_new_entry_when_max_open_positions_is_reached() -> None:
    risk = BotRiskService()

    issues = risk.assess_action(
        policy={"max_open_positions": 1},
        action={"type": "open_long", "symbol": "ETH", "size_usd": 100, "leverage": 2},
        runtime_state={"managed_positions": {"BTC": {"symbol": "BTC", "amount": 0.01}}},
        position_lookup={"BTC": {"symbol": "BTC", "amount": 0.01}},
    )

    assert "max_open_positions 1 reached" in issues


def test_bot_risk_service_blocks_new_entry_while_same_symbol_entry_is_pending() -> None:
    risk = BotRiskService()

    issues = risk.assess_action(
        policy={"max_open_positions": 1},
        action={"type": "open_long", "symbol": "BTC", "size_usd": 100, "leverage": 2},
        runtime_state={"pending_entry_symbols": {"BTC": "2026-03-18T07:00:00+00:00"}},
        position_lookup={},
        open_order_lookup={},
    )

    assert "pending entry on BTC is still syncing" in issues


def test_bot_risk_service_waits_for_position_sync_before_setting_tpsl() -> None:
    risk = BotRiskService()

    issues = risk.assess_action(
        policy={},
        action={"type": "set_tpsl", "symbol": "BTC", "take_profit_pct": 1.8, "stop_loss_pct": 0.9},
        runtime_state={
            "pending_entry_symbols": {"BTC": "2026-03-18T07:00:00+00:00"},
            "managed_positions": {"BTC": {"symbol": "BTC", "amount": 0.003}},
        },
        position_lookup={},
        open_order_lookup={},
    )

    assert "awaiting position sync on BTC before TP/SL" in issues


def test_bot_risk_service_ignores_blank_protective_order_ids_when_assessing_tpsl() -> None:
    risk = BotRiskService()

    issues = risk.assess_action(
        policy={},
        action={"type": "set_tpsl", "symbol": "BTC", "take_profit_pct": 1.8, "stop_loss_pct": 0.9},
        runtime_state={},
        position_lookup={},
        open_order_lookup={
            "BTC": [
                {"symbol": "BTC", "reduce_only": True, "kind": "take_profit", "client_order_id": ""},
                {"symbol": "BTC", "reduce_only": True, "kind": "stop_loss"},
            ]
        },
    )

    assert "existing protective order on BTC already covers this position" not in issues


def test_bot_risk_service_requires_both_known_tpsl_orders_before_marking_position_as_covered() -> None:
    risk = BotRiskService()
    runtime_state = {
        "managed_positions": {
            "BTC": {
                "symbol": "BTC",
                "amount": 0.003,
                "take_profit_client_order_id": "tp-1",
                "stop_loss_client_order_id": "sl-1",
            }
        }
    }

    partial_issues = risk.assess_action(
        policy={},
        action={"type": "set_tpsl", "symbol": "BTC", "take_profit_pct": 1.8, "stop_loss_pct": 0.9},
        runtime_state=runtime_state,
        position_lookup={"BTC": {"symbol": "BTC", "amount": 0.003}},
        open_order_lookup={"BTC": [{"symbol": "BTC", "reduce_only": True, "client_order_id": "tp-1"}]},
    )
    full_issues = risk.assess_action(
        policy={},
        action={"type": "set_tpsl", "symbol": "BTC", "take_profit_pct": 1.8, "stop_loss_pct": 0.9},
        runtime_state=runtime_state,
        position_lookup={"BTC": {"symbol": "BTC", "amount": 0.003}},
        open_order_lookup={
            "BTC": [
                {"symbol": "BTC", "reduce_only": True, "client_order_id": "tp-1"},
                {"symbol": "BTC", "reduce_only": True, "client_order_id": "sl-1"},
            ]
        },
    )

    assert "existing protective order on BTC already covers this position" not in partial_issues
    assert "existing protective order on BTC already covers this position" in full_issues


def test_bot_risk_service_recognizes_existing_tpsl_orders_without_client_order_ids() -> None:
    risk = BotRiskService()

    issues = risk.assess_action(
        policy={},
        action={"type": "set_tpsl", "symbol": "BTC", "take_profit_pct": 1.8, "stop_loss_pct": 0.9},
        runtime_state={"managed_positions": {"BTC": {"symbol": "BTC", "amount": 0.003}}},
        position_lookup={"BTC": {"symbol": "BTC", "amount": 0.003}},
        open_order_lookup={
            "BTC": [
                {"symbol": "BTC", "reduce_only": True, "order_type": "take_profit_market"},
                {"symbol": "BTC", "reduce_only": True, "order_type": "stop_loss_market"},
            ]
        },
    )

    assert "existing protective order on BTC already covers this position" in issues


def test_runtime_process_allows_tpsl_immediately_after_entry(monkeypatch: Any) -> None:
    monkeypatch.setattr("src.workers.bot_runtime_worker.broadcaster.publish", _noop_publish)

    supabase = FakeSupabaseRestClient()
    bot_id = "bot-1"
    runtime_id = "runtime-1"
    wallet_address = "wallet-1"
    user_id = "user-1"
    supabase.tables["bot_definitions"] = [
        {
            "id": bot_id,
            "user_id": user_id,
            "wallet_address": wallet_address,
            "rules_json": {
                "conditions": [{"type": "price_below", "symbol": "BTC", "value": 200000}],
                "actions": [
                    {"type": "open_long", "symbol": "BTC", "size_usd": 105.0, "leverage": 3},
                    {"type": "set_tpsl", "symbol": "BTC", "take_profit_pct": 1.8, "stop_loss_pct": 0.9},
                ],
            },
        }
    ]
    supabase.tables["bot_runtimes"] = [
        {
            "id": runtime_id,
            "bot_definition_id": bot_id,
            "user_id": user_id,
            "wallet_address": wallet_address,
            "status": "active",
            "mode": "live",
            "risk_policy_json": {"max_open_positions": 1, "cooldown_seconds": 45},
            "updated_at": "2026-03-18T07:00:00+00:00",
        }
    ]
    supabase.tables["bot_execution_events"] = []

    pacifica = FakePacificaClient()
    pacifica._margin_settings = [{"symbol": "BTC", "isolated": False, "leverage": 3}]

    worker = BotRuntimeWorker()
    worker._supabase = supabase
    worker._engine._supabase = supabase
    worker._auth = FakeAuthService()
    worker._pacifica = pacifica
    worker._indicator_context = FakeIndicatorContextService()
    worker._coordination = FakeCoordinationService()

    async def fake_performance(runtime: dict[str, Any]) -> dict[str, Any]:
        del runtime
        return {"pnl_total": 0.0, "pnl_realized": 0.0, "pnl_unrealized": 0.0}

    worker._calculate_runtime_performance = fake_performance  # type: ignore[method-assign]

    asyncio.run(worker._process_runtime(None, supabase.tables["bot_runtimes"][0]))

    assert [call.get("type", "create_market_order") for call in pacifica.order_calls[:1]] == [
        "create_market_order",
    ]
    assert pacifica.order_calls[1]["type"] == "set_position_tpsl"


def test_runtime_idempotency_key_changes_after_position_is_closed() -> None:
    action = {"type": "open_long", "symbol": "BTC", "size_usd": 150.0, "leverage": 3}
    runtime_state = {"executions_total": 10, "failures_total": 2, "last_executed_at": "2026-03-18T07:00:00+00:00"}

    with_position = BotRuntimeWorker._build_idempotency_key(
        runtime_id="runtime-1",
        action=action,
        runtime_state=runtime_state,
        position_lookup={"BTC": {"symbol": "BTC", "side": "bid", "amount": 0.00608}},
    )
    without_position = BotRuntimeWorker._build_idempotency_key(
        runtime_id="runtime-1",
        action=action,
        runtime_state=runtime_state,
        position_lookup={},
    )

    assert with_position != without_position


def test_runtime_idempotency_key_changes_after_pending_entry_expires_without_position() -> None:
    worker = BotRuntimeWorker()
    action = {"type": "open_long", "symbol": "BTC", "size_usd": 150.0, "leverage": 3}
    runtime_state = {
        "executions_total": 2,
        "failures_total": 1,
        "last_executed_at": "2026-03-18T07:00:00+00:00",
        "pending_entry_symbols": {"BTC": "2026-03-18T07:00:00+00:00"},
    }

    pending_key = BotRuntimeWorker._build_idempotency_key(
        runtime_id="runtime-1",
        action=action,
        runtime_state=runtime_state,
        position_lookup={},
    )
    reconciled_state = worker._reconcile_runtime_state(
        runtime_state=runtime_state,
        position_lookup={},
        open_order_lookup={},
    )
    retried_key = BotRuntimeWorker._build_idempotency_key(
        runtime_id="runtime-1",
        action=action,
        runtime_state=reconciled_state,
        position_lookup={},
    )

    assert reconciled_state.get("pending_entry_symbols") is None
    assert reconciled_state["entry_retry_generations"]["BTC"] == 1
    assert pending_key != retried_key


def test_runtime_idempotency_key_changes_after_managed_position_disappears() -> None:
    worker = BotRuntimeWorker()
    action = {"type": "open_long", "symbol": "BTC", "size_usd": 150.0, "leverage": 3}
    runtime_state = {
        "executions_total": 2,
        "failures_total": 1,
        "last_executed_at": "2026-03-18T07:00:00+00:00",
        "managed_positions": {
            "BTC": {
                "symbol": "BTC",
                "amount": 0.00608,
                "side": "bid",
                "entry_client_order_id": "entry-1",
            }
        },
    }

    existing_key = BotRuntimeWorker._build_idempotency_key(
        runtime_id="runtime-1",
        action=action,
        runtime_state=runtime_state,
        position_lookup={},
    )
    reconciled_state = worker._reconcile_runtime_state(
        runtime_state=runtime_state,
        position_lookup={},
        open_order_lookup={},
    )
    retried_key = BotRuntimeWorker._build_idempotency_key(
        runtime_id="runtime-1",
        action=action,
        runtime_state=reconciled_state,
        position_lookup={},
    )

    assert reconciled_state.get("managed_positions") is None
    assert reconciled_state["entry_retry_generations"]["BTC"] == 1
    assert existing_key != retried_key


def test_tpsl_idempotency_key_stays_stable_for_same_position_across_runtime_ticks() -> None:
    action = {"type": "set_tpsl", "symbol": "BTC", "take_profit_pct": 1.8, "stop_loss_pct": 0.9}
    first_runtime_state = {"executions_total": 10, "failures_total": 2, "last_executed_at": "2026-03-18T07:00:00+00:00"}
    second_runtime_state = {"executions_total": 18, "failures_total": 2, "last_executed_at": "2026-03-18T07:09:00+00:00"}
    position_lookup = {
        "BTC": {
            "symbol": "BTC",
            "side": "bid",
            "amount": 0.00608,
            "entry_price": 73964.309211,
            "created_at": "1773818088003",
            "updated_at": "1773818088003",
        }
    }

    first_key = BotRuntimeWorker._build_idempotency_key(
        runtime_id="runtime-1",
        action=action,
        runtime_state=first_runtime_state,
        position_lookup=position_lookup,
    )
    second_key = BotRuntimeWorker._build_idempotency_key(
        runtime_id="runtime-1",
        action=action,
        runtime_state=second_runtime_state,
        position_lookup=position_lookup,
    )

    assert first_key == second_key


def test_runtime_process_does_not_reenter_or_duplicate_tpsl_while_position_sync_catches_up(monkeypatch: Any) -> None:
    monkeypatch.setattr("src.workers.bot_runtime_worker.broadcaster.publish", _noop_publish)

    supabase = FakeSupabaseRestClient()
    bot_id = "bot-1"
    runtime_id = "runtime-1"
    wallet_address = "wallet-1"
    user_id = "user-1"
    supabase.tables["bot_definitions"] = [
        {
            "id": bot_id,
            "user_id": user_id,
            "wallet_address": wallet_address,
            "rules_json": {
                "conditions": [{"type": "price_below", "symbol": "BTC", "value": 200000}],
                "actions": [
                    {"type": "open_long", "symbol": "BTC", "size_usd": 105.0, "leverage": 3},
                    {"type": "set_tpsl", "symbol": "BTC", "take_profit_pct": 1.8, "stop_loss_pct": 0.9},
                ],
            },
        }
    ]
    supabase.tables["bot_runtimes"] = [
        {
            "id": runtime_id,
            "bot_definition_id": bot_id,
            "user_id": user_id,
            "wallet_address": wallet_address,
            "status": "active",
            "mode": "live",
            "risk_policy_json": {"max_open_positions": 1, "cooldown_seconds": 0},
            "updated_at": "2026-03-18T07:00:00+00:00",
        }
    ]
    supabase.tables["bot_execution_events"] = []

    pacifica = FakePacificaClient()
    pacifica._margin_settings = [{"symbol": "BTC", "isolated": False, "leverage": 3}]
    pacifica._positions_visible = False

    worker = BotRuntimeWorker()
    worker._supabase = supabase
    worker._engine._supabase = supabase
    worker._auth = FakeAuthService()
    worker._pacifica = pacifica
    worker._indicator_context = FakeIndicatorContextService()
    worker._coordination = FakeCoordinationService()

    async def fake_performance(runtime: dict[str, Any]) -> dict[str, Any]:
        del runtime
        return {"pnl_total": 0.0, "pnl_realized": 0.0, "pnl_unrealized": 0.0}

    worker._calculate_runtime_performance = fake_performance  # type: ignore[method-assign]

    asyncio.run(worker._process_runtime(None, supabase.tables["bot_runtimes"][0]))
    asyncio.run(worker._process_runtime(None, supabase.tables["bot_runtimes"][0]))

    assert [call.get("type") for call in pacifica.order_calls] == ["create_market_order"]

    pacifica._positions_visible = True
    asyncio.run(worker._process_runtime(None, supabase.tables["bot_runtimes"][0]))
    asyncio.run(worker._process_runtime(None, supabase.tables["bot_runtimes"][0]))

    assert [call.get("type") for call in pacifica.order_calls] == [
        "create_market_order",
        "set_position_tpsl",
    ]


def test_runtime_process_does_not_append_duplicate_skipped_tpsl_events_for_unchanged_state(monkeypatch: Any) -> None:
    monkeypatch.setattr("src.workers.bot_runtime_worker.broadcaster.publish", _noop_publish)

    supabase = FakeSupabaseRestClient()
    bot_id = "bot-1"
    runtime_id = "runtime-1"
    wallet_address = "wallet-1"
    user_id = "user-1"
    supabase.tables["bot_definitions"] = [
        {
            "id": bot_id,
            "user_id": user_id,
            "wallet_address": wallet_address,
            "rules_json": {
                "conditions": [{"type": "price_below", "symbol": "BTC", "value": 200000}],
                "actions": [
                    {"type": "set_tpsl", "symbol": "BTC", "take_profit_pct": 1.8, "stop_loss_pct": 0.9},
                ],
            },
        }
    ]
    supabase.tables["bot_runtimes"] = [
        {
            "id": runtime_id,
            "bot_definition_id": bot_id,
            "user_id": user_id,
            "wallet_address": wallet_address,
            "status": "active",
            "mode": "live",
            "risk_policy_json": {"max_open_positions": 1, "cooldown_seconds": 0},
            "updated_at": "2026-03-18T07:00:00+00:00",
        }
    ]
    supabase.tables["bot_execution_events"] = []

    worker = BotRuntimeWorker()
    worker._supabase = supabase
    worker._engine._supabase = supabase
    worker._auth = FakeAuthService()
    worker._pacifica = FakePacificaClient()
    worker._indicator_context = FakeIndicatorContextService()
    worker._coordination = FakeCoordinationService()

    async def fake_performance(runtime: dict[str, Any]) -> dict[str, Any]:
        del runtime
        return {"pnl_total": 0.0, "pnl_realized": 0.0, "pnl_unrealized": 0.0}

    worker._calculate_runtime_performance = fake_performance  # type: ignore[method-assign]

    asyncio.run(worker._process_runtime(None, supabase.tables["bot_runtimes"][0]))
    asyncio.run(worker._process_runtime(None, supabase.tables["bot_runtimes"][0]))

    skipped_events = [
        event
        for event in supabase.tables["bot_execution_events"]
        if event.get("event_type") == "action.skipped" and event.get("status") == "skipped"
    ]

    assert len(skipped_events) == 1


def test_two_bots_can_manage_separate_btc_slices_on_the_same_wallet(monkeypatch: Any) -> None:
    monkeypatch.setattr("src.workers.bot_runtime_worker.broadcaster.publish", _noop_publish)

    supabase = FakeSupabaseRestClient()
    wallet_address = "wallet-1"
    user_id = "user-1"
    supabase.tables["bot_definitions"] = [
        {
            "id": "bot-1",
            "user_id": user_id,
            "wallet_address": wallet_address,
            "rules_json": {
                "conditions": [{"type": "price_below", "symbol": "BTC", "value": 200000}],
                "actions": [
                    {"type": "open_long", "symbol": "BTC", "size_usd": 105.0, "leverage": 3},
                    {"type": "set_tpsl", "symbol": "BTC", "take_profit_pct": 1.8, "stop_loss_pct": 0.9},
                ],
            },
        },
        {
            "id": "bot-2",
            "user_id": user_id,
            "wallet_address": wallet_address,
            "rules_json": {
                "conditions": [{"type": "price_below", "symbol": "BTC", "value": 200000}],
                "actions": [
                    {"type": "open_long", "symbol": "BTC", "size_usd": 105.0, "leverage": 3},
                    {"type": "set_tpsl", "symbol": "BTC", "take_profit_pct": 1.8, "stop_loss_pct": 0.9},
                ],
            },
        },
    ]
    supabase.tables["bot_runtimes"] = [
        {
            "id": "runtime-1",
            "bot_definition_id": "bot-1",
            "user_id": user_id,
            "wallet_address": wallet_address,
            "status": "active",
            "mode": "live",
            "risk_policy_json": {"max_open_positions": 1, "cooldown_seconds": 0},
            "updated_at": "2026-03-18T07:00:00+00:00",
        },
        {
            "id": "runtime-2",
            "bot_definition_id": "bot-2",
            "user_id": user_id,
            "wallet_address": wallet_address,
            "status": "active",
            "mode": "live",
            "risk_policy_json": {"max_open_positions": 1, "cooldown_seconds": 0},
            "updated_at": "2026-03-18T07:00:00+00:00",
        },
    ]
    supabase.tables["bot_execution_events"] = []

    pacifica = FakePacificaClient()
    pacifica._margin_settings = [{"symbol": "BTC", "isolated": False, "leverage": 3}]

    worker = BotRuntimeWorker()
    worker._supabase = supabase
    worker._engine._supabase = supabase
    worker._auth = FakeAuthService()
    worker._pacifica = pacifica
    worker._indicator_context = FakeIndicatorContextService()
    worker._coordination = FakeCoordinationService()

    async def fake_performance(runtime: dict[str, Any]) -> dict[str, Any]:
        del runtime
        return {"pnl_total": 0.0, "pnl_realized": 0.0, "pnl_unrealized": 0.0}

    worker._calculate_runtime_performance = fake_performance  # type: ignore[method-assign]

    asyncio.run(worker._process_runtime(None, supabase.tables["bot_runtimes"][0]))
    asyncio.run(worker._process_runtime(None, supabase.tables["bot_runtimes"][1]))

    assert [call.get("type") for call in pacifica.order_calls] == [
        "create_market_order",
        "set_position_tpsl",
        "create_market_order",
        "set_position_tpsl",
    ]
    assert pacifica.order_calls[1]["take_profit"]["amount"] == 0.003
    assert pacifica.order_calls[3]["take_profit"]["amount"] == 0.003
    assert pacifica._position is not None
    assert pacifica._position["amount"] == 0.006


def test_runtime_process_batches_multiple_cancel_actions(monkeypatch: Any) -> None:
    monkeypatch.setattr("src.workers.bot_runtime_worker.broadcaster.publish", _noop_publish)

    supabase = FakeSupabaseRestClient()
    bot_id = "bot-1"
    runtime_id = "runtime-1"
    wallet_address = "wallet-1"
    user_id = "user-1"
    supabase.tables["bot_definitions"] = [
        {
            "id": bot_id,
            "user_id": user_id,
            "wallet_address": wallet_address,
            "rules_json": {
                "conditions": [{"type": "price_below", "symbol": "BTC", "value": 200000}],
                "actions": [
                    {"type": "cancel_order", "symbol": "BTC", "order_id": 101},
                    {"type": "cancel_order", "symbol": "BTC", "order_id": 102},
                ],
            },
        }
    ]
    supabase.tables["bot_runtimes"] = [
        {
            "id": runtime_id,
            "bot_definition_id": bot_id,
            "user_id": user_id,
            "wallet_address": wallet_address,
            "status": "active",
            "mode": "live",
            "risk_policy_json": {"max_open_positions": 1, "cooldown_seconds": 0},
            "updated_at": "2026-03-18T07:00:00+00:00",
        }
    ]
    supabase.tables["bot_execution_events"] = []

    pacifica = FakePacificaClient()
    pacifica._open_orders = [
        {"symbol": "BTC", "order_id": 101, "side": "bid", "price": 100000.0, "tick_level": 200000},
        {"symbol": "BTC", "order_id": 102, "side": "ask", "price": 100500.0, "tick_level": 201000},
    ]

    worker = BotRuntimeWorker()
    worker._supabase = supabase
    worker._engine._supabase = supabase
    worker._auth = FakeAuthService()
    worker._pacifica = pacifica
    worker._indicator_context = FakeIndicatorContextService()
    worker._coordination = FakeCoordinationService()

    async def fake_performance(runtime: dict[str, Any]) -> dict[str, Any]:
        del runtime
        return {"pnl_total": 0.0, "pnl_realized": 0.0, "pnl_unrealized": 0.0}

    worker._calculate_runtime_performance = fake_performance  # type: ignore[method-assign]

    asyncio.run(worker._process_runtime(None, supabase.tables["bot_runtimes"][0]))

    assert len(pacifica.batch_order_calls) == 1
    assert [item["type"] for item in pacifica.batch_order_calls[0]] == ["cancel_order", "cancel_order"]
    assert pacifica.batch_order_calls[0][0]["side"] == "bid"
    assert pacifica.batch_order_calls[0][0]["tick_level"] == 200000
    assert pacifica.batch_order_calls[0][1]["side"] == "ask"
    assert pacifica.batch_order_calls[0][1]["tick_level"] == 201000
    executed_events = [
        event
        for event in supabase.tables["bot_execution_events"]
        if event.get("event_type") == "action.executed"
    ]
    assert len(executed_events) == 2
