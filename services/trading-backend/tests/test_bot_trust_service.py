from __future__ import annotations

from types import SimpleNamespace

from src.services.bot_risk_service import BotRiskService
from src.services.bot_trust_service import BotTrustService


def test_build_public_runtime_context_includes_passport_trust_and_drift() -> None:
    service = object.__new__(BotTrustService)
    service.risk_service = BotRiskService()
    service.builder_service = SimpleNamespace(
        list_strategy_versions=lambda **_kwargs: [
            {
                "id": "version_3",
                "bot_definition_id": "bot_123",
                "version_number": 3,
                "change_kind": "logic",
                "visibility_snapshot": "public",
                "name_snapshot": "Momentum Prime",
                "is_public_release": True,
                "created_at": "2026-04-01T09:00:00+00:00",
                "label": "v3",
            }
        ],
        list_publish_snapshots=lambda **_kwargs: [
            {
                "id": "publish_1",
                "bot_definition_id": "bot_123",
                "strategy_version_id": "version_3",
                "runtime_id": "runtime_123",
                "visibility_snapshot": "public",
                "publish_state": "published",
                "summary_json": {"name": "Momentum Prime"},
                "created_at": "2026-04-01T09:00:00+00:00",
            }
        ],
    )
    service.supabase = SimpleNamespace(
        select=lambda table, **_kwargs: [
            {
                "id": "event_1",
                "event_type": "action.executed",
                "status": "success",
                "error_reason": None,
                "created_at": "2026-04-01T10:00:00+00:00",
            },
            {
                "id": "event_2",
                "event_type": "action.executed",
                "status": "success",
                "error_reason": None,
                "created_at": "2026-04-01T09:58:00+00:00",
            },
        ]
        if table == "bot_execution_events"
        else [],
        maybe_one=lambda table, **_kwargs: {
            "id": "backtest_123",
            "pnl_total_pct": 11.2,
            "max_drawdown_pct": 4.8,
            "completed_at": "2026-04-01T08:30:00+00:00",
            "status": "completed",
        }
        if table == "bot_backtest_runs"
        else None,
    )

    context = service.build_public_runtime_context(
        runtime={
            "id": "runtime_123",
            "status": "active",
            "updated_at": "2026-04-01T10:00:00+00:00",
            "risk_policy_json": {
                "allocated_capital_usd": 1000,
                "max_leverage": 3,
                "max_drawdown_pct": 12,
                "max_order_size_usd": 180,
                "_runtime_state": {
                    "pnl_total_usd": 108,
                    "drawdown_pct": 5.1,
                },
            },
        },
        definition={
            "id": "bot_123",
            "market_scope": "BTC,ETH",
            "strategy_type": "momentum",
            "authoring_mode": "visual",
            "rules_version": 2,
        },
        latest_snapshot={
            "rank": 2,
            "pnl_total": 108,
            "drawdown": 5.1,
        },
    )

    assert context["passport"]["current_version"] == 3
    assert context["trust"]["trust_score"] >= 80
    assert context["trust"]["risk_grade"] == "A"
    assert context["drift"]["status"] == "aligned"
    assert context["drift"]["benchmark_run_id"] == "backtest_123"
