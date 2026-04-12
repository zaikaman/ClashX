import asyncio
import uuid

from src.workers.bot_copy_worker import BotCopyWorker
from src.workers import bot_copy_worker as bot_copy_worker_module


class FakePacificaClient:
    def __init__(self) -> None:
        self.orders: list[dict] = []

    async def get_markets(self) -> list[dict]:
        return [{"symbol": "BTC", "mark_price": 105000, "lot_size": 0.001, "min_order_size": 0.001}]

    async def get_positions(self, wallet_address: str) -> list[dict]:
        del wallet_address
        return []

    async def place_order(self, payload: dict) -> dict:
        self.orders.append(dict(payload))
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
            "price": 100000,
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
            market_lookup={"BTC": {"mark_price": 105000, "lot_size": 0.001, "min_order_size": 0.001}},
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
            market_lookup={"BTC": {"mark_price": 105000, "lot_size": 0.001, "min_order_size": 0.001}},
            position_lookup={},
        )
    )

    assert [order["type"] for order in fake_pacifica.orders] == ["update_leverage", "create_order", "cancel_order"]
    assert fake_pacifica.orders[1]["client_order_id"] == "mirror-rel123-sourceorder77"
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
    market_lookup = {"BTC": {"mark_price": 105000, "lot_size": 0.001, "min_order_size": 0.001}}

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


class FakeSupabaseForProcessRelationship:
    def __init__(self) -> None:
        self.insert_calls: list[tuple[str, dict, str]] = []
        self.update_calls: list[tuple[str, dict, dict]] = []

    def maybe_one(self, table: str, **kwargs):
        filters = kwargs.get("filters") or {}
        if table == "bot_runtimes":
            return {"id": filters.get("id"), "status": "active"}
        if table == "audit_events":
            return None
        raise AssertionError(f"Unexpected maybe_one table: {table}")

    def select(self, table: str, **kwargs):
        if table == "bot_execution_events":
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
