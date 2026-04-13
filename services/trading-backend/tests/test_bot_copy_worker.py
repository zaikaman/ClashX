import asyncio
import uuid

import pytest

from src.workers.bot_copy_worker import BotCopyWorker
from src.workers import bot_copy_worker as bot_copy_worker_module


class FakePacificaClient:
    def __init__(self) -> None:
        self.orders: list[dict] = []
        self._positions: dict[str, list[dict]] = {}
        self._margin_settings: dict[str, dict[str, int]] = {}

    async def get_markets(self) -> list[dict]:
        return [{"symbol": "BTC", "mark_price": 105000, "tick_size": 0.5, "lot_size": 0.001, "min_order_size": 10.0, "max_leverage": 20}]

    async def get_positions(self, wallet_address: str) -> list[dict]:
        return [dict(position) for position in self._positions.get(wallet_address, [])]

    async def get_account_settings(self, wallet_address: str) -> list[dict]:
        wallet_settings = self._margin_settings.get(wallet_address, {})
        return [
            {"symbol": symbol, "isolated": False, "leverage": leverage}
            for symbol, leverage in wallet_settings.items()
        ]

    async def place_order(self, payload: dict) -> dict:
        self.orders.append(dict(payload))
        if payload["type"] == "update_leverage":
            wallet_settings = self._margin_settings.setdefault(payload["account"], {})
            wallet_settings[payload["symbol"]] = int(payload["leverage"])
        if payload["type"] == "create_market_order" and not payload.get("reduce_only"):
            wallet_positions = self._positions.setdefault(payload["account"], [])
            wallet_positions[:] = [
                {
                    "symbol": payload["symbol"],
                    "side": payload["side"],
                    "amount": payload["amount"],
                    "entry_price": 105000.0,
                    "mark_price": 105000.0,
                }
            ]
        if payload["type"] == "create_market_order" and payload.get("reduce_only"):
            self._positions[payload["account"]] = []
        return {
            "status": "submitted",
            "request_id": f"req-{len(self.orders)}",
            "network": "testnet",
        }


def test_copy_worker_executes_limit_and_cancel_actions_with_mirrored_client_order_ids() -> None:
    worker = BotCopyWorker(poll_interval_seconds=0.01)
    fake_pacifica = FakePacificaClient()
    worker._pacifica = fake_pacifica

    relationship = {"id": "rel-123"}
    source_event = {
        "id": "source-event-1",
        "request_payload": {
            "type": "place_limit_order",
            "symbol": "BTC",
            "side": "long",
            "price": 100000.12,
            "size_usd": 200,
            "leverage": 2,
        },
        "result_payload": {"request_id": "source-order-77"},
    }

    asyncio.run(
        worker._execute_action(
            relationship=relationship,
            source_event=source_event,
            action=source_event["request_payload"],
            scale_bps=10_000,
            credentials={
                "account_address": "wallet-1",
                "agent_wallet_address": "agent-1",
                "agent_private_key": "secret",
            },
            market_lookup={"BTC": {"mark_price": 105000, "tick_size": 0.5, "lot_size": 0.001, "min_order_size": 0.001, "max_leverage": 20}},
            position_lookup={},
        )
    )
    asyncio.run(
        worker._execute_action(
            relationship=relationship,
            source_event={
                "id": "source-event-2",
                "request_payload": {"type": "cancel_order", "symbol": "BTC", "order_id": "source-order-77"},
                "result_payload": {},
            },
            action={"type": "cancel_order", "symbol": "BTC", "order_id": "source-order-77"},
            scale_bps=10_000,
            credentials={
                "account_address": "wallet-1",
                "agent_wallet_address": "agent-1",
                "agent_private_key": "secret",
            },
            market_lookup={"BTC": {"mark_price": 105000, "tick_size": 0.5, "lot_size": 0.001, "min_order_size": 0.001, "max_leverage": 20}},
            position_lookup={},
        )
    )

    assert [order["type"] for order in fake_pacifica.orders] == ["update_leverage", "create_order", "cancel_order"]
    assert fake_pacifica.orders[1]["client_order_id"] == "mirror-rel123-sourceorder77"
    assert fake_pacifica.orders[1]["price"] == 100000.0
    assert fake_pacifica.orders[2]["client_order_id"] == "mirror-rel123-sourceorder77"


def test_copy_worker_executes_market_twap_and_cancel_all_actions() -> None:
    worker = BotCopyWorker(poll_interval_seconds=0.01)
    fake_pacifica = FakePacificaClient()
    worker._pacifica = fake_pacifica

    credentials = {
        "account_address": "wallet-1",
        "agent_wallet_address": "agent-1",
        "agent_private_key": "secret",
    }
    market_lookup = {"BTC": {"mark_price": 105000, "tick_size": 0.5, "lot_size": 0.001, "min_order_size": 0.001, "max_leverage": 20}}

    asyncio.run(
        worker._execute_action(
            relationship={"id": "rel-456"},
            source_event={"id": "evt-market", "request_payload": {}, "result_payload": {}},
            action={
                "type": "place_market_order",
                "symbol": "BTC",
                "side": "short",
                "size_usd": 150,
                "leverage": 3,
                "slippage_percent": 0.5,
            },
            scale_bps=5_000,
            credentials=credentials,
            market_lookup=market_lookup,
            position_lookup={},
        )
    )
    asyncio.run(
        worker._execute_action(
            relationship={"id": "rel-456"},
            source_event={
                "id": "evt-twap",
                "request_payload": {},
                "result_payload": {"request_id": "twap-55"},
            },
            action={
                "type": "place_twap_order",
                "symbol": "BTC",
                "side": "long",
                "size_usd": 200,
                "leverage": 2,
                "duration_seconds": 180,
            },
            scale_bps=10_000,
            credentials=credentials,
            market_lookup=market_lookup,
            position_lookup={},
        )
    )
    asyncio.run(
        worker._execute_action(
            relationship={"id": "rel-456"},
            source_event={"id": "evt-cancel-all", "request_payload": {}, "result_payload": {}},
            action={"type": "cancel_all_orders", "all_symbols": True, "exclude_reduce_only": False},
            scale_bps=10_000,
            credentials=credentials,
            market_lookup=market_lookup,
            position_lookup={},
        )
    )

    assert [order["type"] for order in fake_pacifica.orders] == [
        "update_leverage",
        "create_market_order",
        "update_leverage",
        "create_twap_order",
        "cancel_all_orders",
    ]
    assert fake_pacifica.orders[1]["side"] == "ask"
    assert fake_pacifica.orders[3]["client_order_id"] == "mirror-rel456-twap55"
    assert fake_pacifica.orders[4]["all_symbols"] is True
    assert "symbol" not in fake_pacifica.orders[4]


def test_copy_worker_allows_small_mirrored_market_sizes() -> None:
    worker = BotCopyWorker(poll_interval_seconds=0.01)
    fake_pacifica = FakePacificaClient()
    worker._pacifica = fake_pacifica

    asyncio.run(
        worker._execute_action(
            relationship={"id": "rel-small"},
            source_event={"id": "evt-small", "request_payload": {}, "result_payload": {}},
            action={
                "type": "open_long",
                "symbol": "BTC",
                "size_usd": 75,
                "leverage": 8,
            },
            scale_bps=10_000,
            credentials={
                "account_address": "wallet-1",
                "agent_wallet_address": "agent-1",
                "agent_private_key": "secret",
            },
            market_lookup={"BTC": {"mark_price": 105000, "tick_size": 0.5, "lot_size": 0.001, "min_order_size": 10.0, "max_leverage": 20}},
            position_lookup={},
        )
    )

    assert [order["type"] for order in fake_pacifica.orders] == ["update_leverage", "create_market_order"]
    assert fake_pacifica.orders[1]["amount"] == 0.005


def test_copy_worker_sets_tpsl_with_required_close_side() -> None:
    worker = BotCopyWorker(poll_interval_seconds=0.01)
    fake_pacifica = FakePacificaClient()
    worker._pacifica = fake_pacifica

    asyncio.run(
        worker._execute_action(
            relationship={"id": "rel-tpsl"},
            source_event={"id": "evt-tpsl", "request_payload": {}, "result_payload": {}},
            action={
                "type": "set_tpsl",
                "symbol": "BTC",
                "take_profit_pct": 1.0,
                "stop_loss_pct": 1.0,
            },
            scale_bps=10_000,
            credentials={
                "account_address": "wallet-1",
                "agent_wallet_address": "agent-1",
                "agent_private_key": "secret",
            },
            market_lookup={"BTC": {"mark_price": 82.424167, "tick_size": 0.01, "lot_size": 0.001, "min_order_size": 10.0, "max_leverage": 20}},
            position_lookup={
                "BTC": {
                    "symbol": "BTC",
                    "side": "ask",
                    "amount": 0.005,
                    "mark_price": 82.424167,
                }
            },
        )
    )

    assert fake_pacifica.orders[0]["type"] == "set_position_tpsl"
    assert fake_pacifica.orders[0]["side"] == "bid"
    assert fake_pacifica.orders[0]["take_profit"]["amount"] == 0.005
    assert fake_pacifica.orders[0]["stop_loss"]["amount"] == 0.005
    assert fake_pacifica.orders[0]["take_profit"]["stop_price"] == 81.59
    assert fake_pacifica.orders[0]["stop_loss"]["stop_price"] == 83.25


def test_copy_worker_mirrors_exact_source_tpsl_prices_and_client_order_ids() -> None:
    worker = BotCopyWorker(poll_interval_seconds=0.01)
    fake_pacifica = FakePacificaClient()
    worker._pacifica = fake_pacifica

    asyncio.run(
        worker._execute_action(
            relationship={"id": "cc3d63e8-504f-41c6-b71c-34f7d5a1d343"},
            source_event={
                "id": "evt-source-tpsl",
                "request_payload": {"type": "set_tpsl", "symbol": "BTC"},
                "result_payload": {
                    "payload": {
                        "side": "bid",
                        "symbol": "BTC",
                        "stop_loss": {
                            "amount": "0.00845",
                            "stop_price": "71684.0",
                            "client_order_id": "8e1fbbec-a47b-53c4-9d6d-c5ac17f57b73",
                        },
                        "take_profit": {
                            "amount": "0.00845",
                            "stop_price": "69554.0",
                            "client_order_id": "7eea60ea-6aa9-5117-8973-54060cf78745",
                        },
                    }
                },
            },
            action={
                "type": "set_tpsl",
                "symbol": "BTC",
                "take_profit_pct": 2.0,
                "stop_loss_pct": 1.0,
            },
            scale_bps=10_000,
            credentials={
                "account_address": "wallet-1",
                "agent_wallet_address": "agent-1",
                "agent_private_key": "secret",
            },
            market_lookup={"BTC": {"mark_price": 70958.5, "tick_size": 1.0, "lot_size": 0.00001, "max_leverage": 20}},
            position_lookup={
                "BTC": {
                    "symbol": "BTC",
                    "side": "ask",
                    "amount": 0.00845,
                    "mark_price": 70958.5,
                }
            },
        )
    )

    assert fake_pacifica.orders[0]["take_profit"]["stop_price"] == 69554.0
    assert fake_pacifica.orders[0]["stop_loss"]["stop_price"] == 71684.0
    assert fake_pacifica.orders[0]["take_profit"]["client_order_id"] == "mirror-cc3d63e8504f-7eea60ea6aa95117897354060cf78745"
    assert fake_pacifica.orders[0]["stop_loss"]["client_order_id"] == "mirror-cc3d63e8504f-8e1fbbeca47b53c49d6dc5ac17f57b73"


def test_copy_worker_reduce_only_size_ignores_leverage_multiplier() -> None:
    worker = BotCopyWorker(poll_interval_seconds=0.01)
    fake_pacifica = FakePacificaClient()
    worker._pacifica = fake_pacifica

    asyncio.run(
        worker._execute_action(
            relationship={"id": "rel-reduce"},
            source_event={"id": "evt-reduce", "request_payload": {}, "result_payload": {}},
            action={
                "type": "place_market_order",
                "symbol": "BTC",
                "side": "short",
                "size_usd": 100,
                "leverage": 8,
                "reduce_only": True,
            },
            scale_bps=10_000,
            credentials={
                "account_address": "wallet-1",
                "agent_wallet_address": "agent-1",
                "agent_private_key": "secret",
            },
            market_lookup={"BTC": {"mark_price": 100, "tick_size": 0.5, "lot_size": 0.01, "max_leverage": 20}},
            position_lookup={},
        )
    )

    assert [order["type"] for order in fake_pacifica.orders] == ["create_market_order"]
    assert fake_pacifica.orders[0]["amount"] == 1.0


def test_copy_worker_skips_update_leverage_when_setting_already_matches() -> None:
    worker = BotCopyWorker(poll_interval_seconds=0.01)
    fake_pacifica = FakePacificaClient()
    fake_pacifica._margin_settings["wallet-1"] = {"BTC": 8}
    worker._pacifica = fake_pacifica

    asyncio.run(
        worker._execute_action(
            relationship={"id": "rel-match"},
            source_event={"id": "evt-match", "request_payload": {}, "result_payload": {}},
            action={
                "type": "open_short",
                "symbol": "BTC",
                "size_usd": 75,
                "leverage": 8,
            },
            scale_bps=10_000,
            credentials={
                "account_address": "wallet-1",
                "agent_wallet_address": "agent-1",
                "agent_private_key": "secret",
            },
            market_lookup={"BTC": {"mark_price": 105000, "tick_size": 0.5, "lot_size": 0.001, "max_leverage": 20}},
            position_lookup={},
        )
    )

    assert [order["type"] for order in fake_pacifica.orders] == ["create_market_order"]


def test_copy_worker_rejects_leverage_above_market_max() -> None:
    worker = BotCopyWorker(poll_interval_seconds=0.01)

    with pytest.raises(ValueError, match="Requested leverage 8 exceeds BTC market max leverage 5."):
        asyncio.run(
            worker._execute_action(
                relationship={"id": "rel-lev"},
                source_event={"id": "evt-lev", "request_payload": {}, "result_payload": {}},
                action={
                    "type": "open_long",
                    "symbol": "BTC",
                    "size_usd": 75,
                    "leverage": 8,
                },
                scale_bps=10_000,
                credentials={
                    "account_address": "wallet-1",
                    "agent_wallet_address": "agent-1",
                    "agent_private_key": "secret",
                },
                market_lookup={"BTC": {"mark_price": 105000, "tick_size": 0.5, "lot_size": 0.001, "max_leverage": 5}},
                position_lookup={},
            )
        )


class FakeSupabaseForProcessRelationship:
    def __init__(self, source_events: list[dict] | None = None) -> None:
        self.insert_calls: list[tuple[str, dict, str]] = []
        self.update_calls: list[tuple[str, dict, dict]] = []
        self.source_events = list(source_events or [])

    def maybe_one(self, table: str, **kwargs):
        filters = kwargs.get("filters") or {}
        if table == "bot_runtimes":
            return {"id": filters.get("id"), "status": "active"}
        if table == "audit_events":
            return None
        raise AssertionError(f"Unexpected maybe_one table: {table}")

    def select(self, table: str, **kwargs):
        if table == "bot_execution_events":
            if self.source_events:
                return sorted(self.source_events, key=lambda item: item.get("created_at") or "", reverse=True)
            return [
                {
                    "id": "source-event-1",
                    "request_payload": {
                        "type": "open_long",
                        "symbol": "BTC",
                        "size_usd": 150,
                        "leverage": 2,
                    },
                    "result_payload": {},
                    "created_at": "2026-04-12T12:28:28.167974+00:00",
                }
            ]
        raise AssertionError(f"Unexpected select table: {table}")

    def insert(self, table: str, payload: dict, *, returning: str = "representation"):
        self.insert_calls.append((table, dict(payload), returning))
        return []

    def update(self, table: str, values: dict, *, filters: dict, returning: str = "representation"):
        self.update_calls.append((table, dict(values), dict(filters)))
        return [{"id": filters["id"], **values}]


class FakeSupabaseForQueuedSourceEvent(FakeSupabaseForProcessRelationship):
    def __init__(self, relationship: dict[str, str], source_events: list[dict] | None = None) -> None:
        super().__init__(source_events=source_events)
        self.relationship = dict(relationship)

    def select(self, table: str, **kwargs):
        if table == "bot_copy_relationships":
            filters = kwargs.get("filters") or {}
            if filters.get("source_runtime_id") == self.relationship["source_runtime_id"]:
                return [dict(self.relationship)]
            return []
        return super().select(table, **kwargs)


class FakeAuthService:
    def get_trading_credentials(self, db, wallet_address: str):
        del db, wallet_address
        return {
            "account_address": "wallet-1",
            "agent_wallet_address": "agent-1",
            "agent_private_key": "secret",
        }


async def _noop_publish(*, channel: str, event: str, payload: dict) -> None:
    del channel, event, payload


def test_copy_worker_records_uuid_audit_event_ids_when_processing_relationship(monkeypatch) -> None:
    worker = BotCopyWorker(poll_interval_seconds=0.01)
    fake_pacifica = FakePacificaClient()
    fake_supabase = FakeSupabaseForProcessRelationship()
    worker._pacifica = fake_pacifica
    worker._auth = FakeAuthService()
    worker._supabase = fake_supabase
    worker._claim_local_lease = lambda lease_key, *, ttl_seconds: True
    monkeypatch.setattr(bot_copy_worker_module.broadcaster, "publish", _noop_publish)

    asyncio.run(
        worker._process_relationship(
            {
                "id": "046b4691-80dc-4eda-8171-73753f6f7606",
                "source_runtime_id": "runtime-1",
                "follower_user_id": "user-1",
                "follower_wallet_address": "wallet-1",
                "scale_bps": 10_000,
                "updated_at": "2026-04-12T07:14:16.66341+00:00",
            }
        )
    )

    audit_insert = next(payload for table, payload, _ in fake_supabase.insert_calls if table == "audit_events")
    assert uuid.UUID(audit_insert["id"])
    assert audit_insert["action"] == "bot_copy.mirror:046b4691-80dc-4eda-8171-73753f6f7606:source-event-1"
    assert fake_pacifica.orders[1]["type"] == "create_market_order"
    assert any(table == "bot_copy_relationships" for table, _, _ in fake_supabase.update_calls)


def test_copy_worker_refreshes_positions_before_mirroring_tpsl(monkeypatch) -> None:
    worker = BotCopyWorker(poll_interval_seconds=0.01)
    fake_pacifica = FakePacificaClient()
    fake_supabase = FakeSupabaseForProcessRelationship(
        source_events=[
            {
                "id": "source-event-open",
                "request_payload": {
                    "type": "open_long",
                    "symbol": "BTC",
                    "size_usd": 75,
                    "leverage": 8,
                },
                "result_payload": {},
                "created_at": "2026-04-12T22:03:08.487066+00:00",
            },
            {
                "id": "source-event-tpsl",
                "request_payload": {
                    "type": "set_tpsl",
                    "symbol": "BTC",
                    "stop_loss_pct": 1.0,
                    "take_profit_pct": 2.0,
                },
                "result_payload": {},
                "created_at": "2026-04-12T22:03:09.943265+00:00",
            },
        ]
    )
    worker._pacifica = fake_pacifica
    worker._auth = FakeAuthService()
    worker._supabase = fake_supabase
    worker._claim_local_lease = lambda lease_key, *, ttl_seconds: True
    monkeypatch.setattr(bot_copy_worker_module.broadcaster, "publish", _noop_publish)

    asyncio.run(
        worker._process_relationship(
            {
                "id": "046b4691-80dc-4eda-8171-73753f6f7606",
                "source_runtime_id": "runtime-1",
                "follower_user_id": "user-1",
                "follower_wallet_address": "wallet-1",
                "scale_bps": 10_000,
                "updated_at": "2026-04-12T07:14:16.66341+00:00",
            }
        )
    )

    assert [order["type"] for order in fake_pacifica.orders] == [
        "update_leverage",
        "create_market_order",
        "set_position_tpsl",
    ]
    mirrored_execution_rows = [payload for table, payload, _ in fake_supabase.insert_calls if table == "bot_copy_execution_events"]
    assert [row["status"] for row in mirrored_execution_rows] == ["mirrored", "mirrored"]


def test_copy_worker_processes_queued_source_events_without_waiting_for_poll(monkeypatch) -> None:
    worker = BotCopyWorker(poll_interval_seconds=60.0)
    fake_pacifica = FakePacificaClient()
    fake_supabase = FakeSupabaseForQueuedSourceEvent(
        relationship={
            "id": "046b4691-80dc-4eda-8171-73753f6f7606",
            "source_runtime_id": "runtime-1",
            "follower_user_id": "user-1",
            "follower_wallet_address": "wallet-1",
            "scale_bps": 10_000,
            "updated_at": "2026-04-12T07:14:16.663410+00:00",
        }
    )
    worker._pacifica = fake_pacifica
    worker._auth = FakeAuthService()
    worker._supabase = fake_supabase
    worker._claim_local_lease = lambda lease_key, *, ttl_seconds: True
    monkeypatch.setattr(bot_copy_worker_module.broadcaster, "publish", _noop_publish)

    async def scenario() -> None:
        worker.start()
        worker.submit_source_event(
            source_runtime_id="runtime-1",
            source_event={
                "id": "source-event-queued",
                "runtime_id": "runtime-1",
                "event_type": "action.executed",
                "request_payload": {
                    "type": "open_long",
                    "symbol": "BTC",
                    "size_usd": 150,
                    "leverage": 2,
                },
                "result_payload": {},
                "created_at": "2026-04-12T12:28:28.167974+00:00",
            },
        )
        for _ in range(20):
            mirrored_order_submitted = any(order["type"] == "create_market_order" for order in fake_pacifica.orders)
            relationship_cursor_updated = any(
                table == "bot_copy_relationships" for table, _, _ in fake_supabase.update_calls
            )
            if mirrored_order_submitted and relationship_cursor_updated:
                break
            await asyncio.sleep(0.01)
        await worker.stop()

    asyncio.run(scenario())

    assert [order["type"] for order in fake_pacifica.orders] == ["update_leverage", "create_market_order"]
    relationship_updates = [values for table, values, _ in fake_supabase.update_calls if table == "bot_copy_relationships"]
    assert relationship_updates[-1]["updated_at"] == "2026-04-12T12:28:28.167974+00:00"
