from tests.helpers.runtime_harness import RuntimeHarness


def test_apply_runtime_sizing_policy_overrides_with_fixed_usd_amount() -> None:
    harness = RuntimeHarness()

    resolved = harness.worker._apply_runtime_sizing_policy(
        action={"type": "open_long", "symbol": "BTC", "size_usd": 90, "leverage": 3},
        runtime_policy={"sizing_mode": "fixed_usd", "fixed_usd_amount": 125, "max_leverage": 5},
        route_actions=[{"type": "open_long", "symbol": "BTC", "size_usd": 90, "leverage": 3}],
        action_index=0,
    )

    assert resolved["size_usd"] == 125.0
    assert resolved["leverage"] == 5
    assert resolved["_sizing_mode"] == "fixed_usd"


def test_apply_runtime_sizing_policy_uses_builder_stop_loss_for_risk_adjusted_mode() -> None:
    harness = RuntimeHarness()
    route_actions = [
        {"type": "open_long", "symbol": "BTC", "size_usd": 90, "leverage": 4},
        {"type": "set_tpsl", "symbol": "BTC", "take_profit_pct": 1.5, "stop_loss_pct": 1.0},
    ]

    resolved = harness.worker._apply_runtime_sizing_policy(
        action=route_actions[0],
        runtime_policy={
            "sizing_mode": "risk_adjusted",
            "allocated_capital_usd": 1000,
            "risk_per_trade_pct": 1,
            "max_leverage": 5,
        },
        route_actions=route_actions,
        action_index=0,
    )

    assert resolved["size_usd"] == 200.0
    assert resolved["leverage"] == 5
    assert resolved["_sizing_mode"] == "risk_adjusted"
    assert resolved["_stop_loss_pct"] == 1.0
    assert resolved["_risk_budget_usd"] == 10.0


def test_reduce_only_market_order_size_does_not_multiply_by_hidden_leverage() -> None:
    harness = RuntimeHarness().with_market(symbol="BTC", mark_price=100_000.0, lot_size=0.0001)

    quantity = harness.worker._resolve_order_quantity(
        action={"type": "place_market_order", "symbol": "BTC", "size_usd": 200, "leverage": 5, "reduce_only": True},
        market_lookup=harness.worker._build_market_lookup(harness.pacifica._markets),
        symbol="BTC",
        reference_price=None,
    )

    assert quantity == 0.002
