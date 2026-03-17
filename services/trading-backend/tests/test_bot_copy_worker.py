import asyncio

from src.workers.bot_copy_worker import BotCopyWorker


class FakePacificaClient:
    def __init__(self) -> None:
        self.orders: list[dict] = []

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
