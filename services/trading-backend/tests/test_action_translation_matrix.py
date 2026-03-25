from __future__ import annotations

from tests.helpers.runtime_harness import RuntimeHarness


def test_execute_action_translates_twap_order_payload() -> None:
    harness = RuntimeHarness().with_market()

    response = harness.execute_action(
        {
            "type": "place_twap_order",
            "symbol": "BTC",
            "side": "short",
            "size_usd": 210.0,
            "leverage": 2,
            "duration_seconds": 120,
            "slippage_percent": 0.3,
        }
    )

    assert harness.pacifica_calls()[0]["type"] == "update_leverage"
    assert harness.pacifica_calls()[1]["type"] == "create_twap_order"
    assert harness.pacifica_calls()[1]["side"] == "ask"
    assert harness.pacifica_calls()[1]["duration_in_seconds"] == 120
    assert response["execution_meta"]["side"] == "ask"
    assert response["execution_meta"]["amount"] == 0.004


def test_execute_action_translates_cancel_all_orders_payload() -> None:
    harness = RuntimeHarness().with_market().with_open_orders(
        [
            {"symbol": "BTC", "order_id": 101, "reduce_only": False},
            {"symbol": "BTC", "order_id": 102, "reduce_only": True},
        ]
    )

    harness.execute_action(
        {
            "type": "cancel_all_orders",
            "symbol": "BTC",
            "all_symbols": False,
            "exclude_reduce_only": True,
        }
    )

    assert harness.pacifica_calls()[0]["type"] == "cancel_all_orders"
    assert harness.pacifica_calls()[0]["all_symbols"] is False
    assert harness.pacifica_calls()[0]["exclude_reduce_only"] is True
    assert harness.pacifica._open_orders == [{"symbol": "BTC", "order_id": 102, "reduce_only": True}]


def test_execute_action_translates_cancel_twap_order_identifier() -> None:
    harness = RuntimeHarness().with_market()

    harness.execute_action(
        {
            "type": "cancel_twap_order",
            "symbol": "BTC",
            "client_order_id": "twap-order-1",
        }
    )

    assert harness.pacifica_calls()[0]["type"] == "cancel_twap_order"
    assert harness.pacifica_calls()[0]["client_order_id"] == "twap-order-1"

