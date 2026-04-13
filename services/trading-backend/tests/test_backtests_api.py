from __future__ import annotations

import asyncio

from src.api.auth import AuthenticatedUser
from src.api.backtests import (
    BacktestRunRequest,
    create_backtest_run_job,
    get_backtest_run_job,
    get_backtests_bootstrap,
    list_backtest_run_jobs,
)


def _job_user() -> AuthenticatedUser:
    return AuthenticatedUser(user_id="user-1", wallet_addresses=["wallet-abc"])


def _completed_run_payload() -> dict[str, object]:
    return {
        "id": "run-1",
        "bot_definition_id": "bot-1",
        "bot_name_snapshot": "Momentum",
        "market_scope_snapshot": "BTC-PERP",
        "strategy_type_snapshot": "trend",
        "interval": "1m",
        "start_time": 1,
        "end_time": 2,
        "initial_capital_usd": 10_000,
        "execution_model": "close_only",
        "pnl_total": 125.0,
        "pnl_total_pct": 1.25,
        "max_drawdown_pct": 3.0,
        "win_rate": 54.0,
        "trade_count": 12,
        "status": "completed",
        "assumption_config_json": {},
        "failure_reason": None,
        "created_at": "2026-04-10T00:00:00+00:00",
        "completed_at": "2026-04-10T00:00:05+00:00",
        "updated_at": "2026-04-10T00:00:05+00:00",
        "user_id": "user-1",
        "wallet_address": "wallet-abc",
        "rules_snapshot_json": {"conditions": [], "actions": []},
        "result_json": {
            "equity_curve": [],
            "price_series": {
                "primary_symbol": "BTC-PERP",
                "series_by_symbol": {"BTC-PERP": []},
            },
            "trades": [],
            "trigger_events": [],
            "summary": {
                "primary_symbol": "BTC-PERP",
                "symbols": ["BTC-PERP"],
                "interval": "1m",
                "initial_capital_usd": 10_000,
                "ending_equity": 10_125,
                "realized_pnl": 125.0,
                "unrealized_pnl": 0.0,
                "gross_pnl_total": 125.0,
                "pnl_total": 125.0,
                "pnl_total_pct": 1.25,
                "max_drawdown_pct": 3.0,
                "win_rate": 54.0,
                "trade_count": 12,
                "winning_trades": 6,
                "losing_trades": 6,
                "avg_trade_duration_seconds": 3600,
                "fees_paid_usd": 2.0,
                "funding_pnl_usd": 0.0,
            },
            "assumptions": [],
        },
    }


def test_create_backtest_run_job_returns_queued_job(monkeypatch) -> None:
    created: dict[str, object] = {}

    monkeypatch.setattr(
        "src.api.backtests.ai_job_service.create_job",
        lambda **kwargs: created.setdefault("job", {"id": "job-1", **kwargs}) or created["job"],
    )

    response = asyncio.run(
        create_backtest_run_job(
            BacktestRunRequest(
                wallet_address="wallet-abc",
                bot_id="bot-1",
                interval="1m",
                start_time=1,
                end_time=2,
                initial_capital_usd=10_000,
            ),
            user=_job_user(),
        )
    )

    assert response.id == "job-1"
    assert response.status == "queued"
    assert response.jobType == "backtest_run"
    assert created["job"]["wallet_address"] == "wallet-abc"
    assert created["job"]["request_payload"]["bot_id"] == "bot-1"
    assert created["job"]["request_payload"]["interval"] == "1m"


def test_list_backtest_run_jobs_returns_recent_wallet_jobs(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.api.backtests.ai_job_service.list_jobs",
        lambda **kwargs: [
            {
                "id": "job-2",
                "job_type": "backtest_run",
                "status": "queued",
                "result_payload_json": {},
                "error_detail": None,
                "created_at": "2026-04-10T00:00:00+00:00",
                "updated_at": "2026-04-10T00:00:00+00:00",
                "completed_at": None,
            }
        ],
    )

    response = asyncio.run(list_backtest_run_jobs(wallet_address="wallet-abc", limit=10, user=_job_user()))

    assert len(response) == 1
    assert response[0].id == "job-2"
    assert response[0].status == "queued"
    assert response[0].createdAt == "2026-04-10T00:00:00+00:00"


def test_get_backtest_run_job_returns_live_progress(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.api.backtests.ai_job_service.get_job_for_wallets",
        lambda **kwargs: {
            "id": kwargs["job_id"],
            "job_type": "backtest_run",
            "status": "running",
            "result_payload_json": {
                "type": "progress",
                "progress": 56,
                "stage": "Preparing replay timeline",
                "detail": "Aligned 100 replay bars across 2 active markets.",
                "interval": "1m",
                "metrics": {
                    "processed_bars": 0,
                    "total_bars": 100,
                },
            },
            "error_detail": None,
            "created_at": "2026-04-10T00:00:00+00:00",
            "updated_at": "2026-04-10T00:00:01+00:00",
            "completed_at": None,
        },
    )

    response = asyncio.run(get_backtest_run_job("job-1", user=_job_user()))

    assert response.id == "job-1"
    assert response.status == "running"
    assert response.progress["stage"] == "Preparing replay timeline"
    assert response.result is None


def test_get_backtest_run_job_returns_completed_result(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.api.backtests.ai_job_service.get_job_for_wallets",
        lambda **kwargs: {
            "id": kwargs["job_id"],
            "job_type": "backtest_run",
            "status": "completed",
            "result_payload_json": {
                "type": "result",
                "run": _completed_run_payload(),
            },
            "error_detail": None,
            "created_at": "2026-04-10T00:00:00+00:00",
            "updated_at": "2026-04-10T00:00:05+00:00",
            "completed_at": "2026-04-10T00:00:05+00:00",
        },
    )

    response = asyncio.run(get_backtest_run_job("job-1", user=_job_user()))

    assert response.id == "job-1"
    assert response.status == "completed"
    assert response.result is not None
    assert response.result.id == "run-1"
    assert response.result.result_json["summary"]["interval"] == "1m"


def test_get_backtests_bootstrap_includes_recent_backtest_jobs(monkeypatch) -> None:
    monkeypatch.setattr("src.api.backtests.bot_builder_service.list_bots", lambda db, wallet_address: [])
    monkeypatch.setattr(
        "src.api.backtests.bot_backtest_service.list_runs",
        lambda db, wallet_address, user_id, bot_id: [],
    )
    monkeypatch.setattr(
        "src.api.backtests.ai_job_service.list_jobs",
        lambda **kwargs: [
            {
                "id": "job-3",
                "job_type": "backtest_run",
                "status": "running",
                "result_payload_json": {
                    "type": "progress",
                    "progress": 22,
                    "stage": "Loading market history",
                    "detail": "Fetching 4 windows.",
                    "interval": "1m",
                },
                "error_detail": None,
                "created_at": "2026-04-10T00:00:00+00:00",
                "updated_at": "2026-04-10T00:00:02+00:00",
                "completed_at": None,
            }
        ],
    )

    response = get_backtests_bootstrap(wallet_address="wallet-abc", bot_id=None, db=None, user=_job_user())

    assert response.jobs[0].id == "job-3"
    assert response.jobs[0].status == "running"
    assert response.jobs[0].progress["progress"] == 22
