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
