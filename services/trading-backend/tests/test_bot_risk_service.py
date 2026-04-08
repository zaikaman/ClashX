from src.services.bot_risk_service import BotRiskService


def test_sync_performance_computes_allocation_based_drawdown() -> None:
    service = BotRiskService()

    policy = service.sync_performance(
        policy={"allocated_capital_usd": 100, "max_drawdown_pct": 10},
        pnl_total=-12.5,
        pnl_realized=-8.0,
        pnl_unrealized=-4.5,
    )

    state = policy["_runtime_state"]
    assert state["allocated_capital_usd"] == 100.0
    assert state["realized_pnl_usd"] == -8.0
    assert state["unrealized_pnl_usd"] == -4.5
    assert state["pnl_total_usd"] == -12.5
    assert state["drawdown_amount_usd"] == 12.5
    assert state["drawdown_pct"] == 12.5


def test_drawdown_breach_reason_uses_allocated_capital_threshold() -> None:
    service = BotRiskService()
    policy = service.sync_performance(
        policy={"allocated_capital_usd": 100, "max_drawdown_pct": 10},
        pnl_total=-12.0,
        pnl_realized=-5.0,
        pnl_unrealized=-7.0,
    )

    reason = service.drawdown_breach_reason(policy=policy, runtime_state=policy["_runtime_state"])

    assert reason is not None
    assert "$12.00" in reason
    assert "12.00%" in reason
    assert "$100.00" in reason


def test_assess_action_blocks_quantity_based_limit_order_above_max_order_value() -> None:
    service = BotRiskService()

    issues = service.assess_action(
        policy={"max_order_size_usd": 200},
        action={
            "type": "place_limit_order",
            "symbol": "BTC",
            "quantity": 1.0,
            "price": 100_000.0,
            "leverage": 1,
        },
        runtime_state={},
        market_lookup={"BTC": {"mark_price": 100_000.0, "max_leverage": 5}},
    )

    assert "requested order value 100000 exceeds max_order_size_usd 200" in issues


def test_assess_action_allows_reduce_only_limit_exit_without_entry_conflicts() -> None:
    service = BotRiskService()

    issues = service.assess_action(
        policy={"max_open_positions": 1, "max_order_size_usd": 5_000},
        action={
            "type": "place_limit_order",
            "symbol": "BTC",
            "quantity": 0.01,
            "price": 100_000.0,
            "leverage": 1,
            "reduce_only": True,
        },
        runtime_state={
            "managed_positions": {
                "BTC": {
                    "symbol": "BTC",
                    "amount": 0.01,
                }
            }
        },
        position_lookup={"BTC": {"symbol": "BTC", "amount": 0.01}},
        open_order_lookup={},
        market_lookup={"BTC": {"mark_price": 100_000.0, "max_leverage": 5}},
    )

    assert issues == []


def test_assess_action_blocks_reduce_only_twap_without_managed_position() -> None:
    service = BotRiskService()

    issues = service.assess_action(
        policy={"max_open_positions": 1, "max_order_size_usd": 5_000},
        action={
            "type": "place_twap_order",
            "symbol": "BTC",
            "quantity": 0.01,
            "duration_seconds": 900,
            "leverage": 1,
            "reduce_only": True,
        },
        runtime_state={"managed_positions": {}},
        position_lookup={},
        open_order_lookup={},
        market_lookup={"BTC": {"mark_price": 100_000.0, "max_leverage": 5}},
    )

    assert issues == ["bot does not manage an open position on BTC"]


def test_normalize_policy_includes_runtime_sizing_fields() -> None:
    service = BotRiskService()

    policy = service.normalize_policy(
        {
            "sizing_mode": "risk_adjusted",
            "fixed_usd_amount": 125,
            "risk_per_trade_pct": 1.5,
        }
    )

    assert policy["sizing_mode"] == "risk_adjusted"
    assert policy["fixed_usd_amount"] == 125.0
    assert policy["risk_per_trade_pct"] == 1.5
