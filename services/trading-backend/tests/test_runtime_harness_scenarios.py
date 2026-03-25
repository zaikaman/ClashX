from __future__ import annotations

from tests.helpers.runtime_harness import RuntimeHarness


def test_runtime_harness_opens_short_without_ui_or_api_setup() -> None:
    harness = (
        RuntimeHarness()
        .with_market(symbol="BTC", mark_price=105_000.0, lot_size=0.001, tick_size=0.5, max_leverage=5)
        .with_margin_settings([{"symbol": "BTC", "isolated": False, "leverage": 3}])
        .with_bot(
            conditions=[{"type": "price_below", "symbol": "BTC", "value": 200000}],
            actions=[{"type": "open_short", "symbol": "BTC", "size_usd": 105.0, "leverage": 3}],
            risk_policy={"max_open_positions": 1, "cooldown_seconds": 0},
        )
    )

    harness.process_once()

    assert [call.get("type") for call in harness.pacifica_calls()] == ["create_market_order"]
    assert harness.pacifica_calls()[0]["side"] == "ask"
    assert harness.runtime_state()["managed_positions"]["BTC"]["side"] == "ask"


def test_runtime_harness_batches_limit_create_and_cancel_actions() -> None:
    harness = (
        RuntimeHarness()
        .with_market()
        .with_open_orders(
            [{"symbol": "BTC", "order_id": 101, "side": "bid", "price": 100000.0, "tick_level": 200000}]
        )
        .with_bot(
            conditions=[{"type": "price_below", "symbol": "BTC", "value": 200000}],
            actions=[
                {
                    "type": "place_limit_order",
                    "symbol": "BTC",
                    "side": "long",
                    "price": 100000.0,
                    "quantity": 0.002,
                    "leverage": 2,
                },
                {"type": "cancel_order", "symbol": "BTC", "order_id": 101},
            ],
            risk_policy={"max_open_positions": 3, "cooldown_seconds": 0},
        )
    )

    harness.process_once()

    assert len(harness.batch_calls()) == 1
    assert [item["type"] for item in harness.batch_calls()[0]] == ["create_order", "cancel_order"]
    executed = [event for event in harness.execution_events() if event.get("event_type") == "action.executed"]
    assert len(executed) == 2
