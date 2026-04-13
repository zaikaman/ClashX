from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from src.api.auth import AuthenticatedUser
from src.services.ai_job_runner_service import AiJobRunnerService


@dataclass
class _FakeJobService:
    running_jobs: list[str] = field(default_factory=list)
    progress_jobs: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    completed_jobs: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    failed_jobs: list[tuple[str, str]] = field(default_factory=list)
    fail_complete: bool = False

    def mark_running(self, *, job_id: str) -> dict[str, Any] | None:
        self.running_jobs.append(job_id)
        return {"id": job_id, "status": "running"}

    def mark_completed(self, *, job_id: str, result_payload: dict[str, Any]) -> dict[str, Any] | None:
        if self.fail_complete:
            raise RuntimeError("Could not persist completed AI job.")
        self.completed_jobs.append((job_id, result_payload))
        return {"id": job_id, "status": "completed"}

    def update_progress(self, *, job_id: str, progress_payload: dict[str, Any]) -> dict[str, Any] | None:
        self.progress_jobs.append((job_id, progress_payload))
        return {"id": job_id, "status": "running"}

    def mark_failed(self, *, job_id: str, error_detail: str) -> dict[str, Any] | None:
        self.failed_jobs.append((job_id, error_detail))
        return {"id": job_id, "status": "failed"}


class _FakeBuilderAiService:
    def __init__(self, *, should_fail: bool = False) -> None:
        self.should_fail = should_fail

    async def generate_draft(
        self,
        messages: list[dict[str, str]],
        available_markets: list[str],
        current_draft: dict[str, Any] | None,
    ) -> dict[str, Any]:
        if self.should_fail:
            raise RuntimeError("Builder provider timed out.")
        return {
            "reply": f"Built for {available_markets[0]}",
            "draft": {
                "name": "Draft",
                "description": "Generated",
                "marketSelection": "selected",
                "markets": available_markets,
                "conditions": [{"type": "price_above", "symbol": available_markets[0]}],
                "actions": [{"type": "open_long", "symbol": available_markets[0]}],
            },
        }


class _FakeCopilotConversationService:
    def __init__(self, *, should_fail: bool = False) -> None:
        self.should_fail = should_fail

    async def send_message(
        self,
        *,
        user: AuthenticatedUser,
        content: str,
        conversation_id: str | None = None,
        wallet_address: str | None = None,
    ) -> dict[str, Any]:
        del user
        if self.should_fail:
            raise RuntimeError("OpenAI request timed out.")
        return {
            "conversationId": conversation_id or "conv-1",
            "conversation": {
                "id": conversation_id or "conv-1",
                "title": content,
                "walletAddress": wallet_address or "wallet-abc",
                "messageCount": 2,
                "lastMessagePreview": "Done",
                "createdAt": "2026-04-10T00:00:00+00:00",
                "updatedAt": "2026-04-10T00:00:00+00:00",
                "latestMessageAt": "2026-04-10T00:00:00+00:00",
            },
            "assistantMessage": {
                "id": "assistant-1",
                "role": "assistant",
                "content": "Done",
                "toolCalls": [],
                "followUps": [],
                "provider": "OpenAI",
                "createdAt": "2026-04-10T00:00:00+00:00",
            },
            "reply": "Done",
            "followUps": [],
            "toolCalls": [],
            "provider": "OpenAI",
            "usedWalletAddress": wallet_address,
        }


class _FakeBacktestService:
    def __init__(self, *, should_fail: bool = False) -> None:
        self.should_fail = should_fail

    async def run_backtest(
        self,
        db,
        *,
        bot_id: str,
        wallet_address: str,
        user_id: str,
        interval: str | None,
        start_time: int,
        end_time: int,
        initial_capital_usd: float,
        assumptions: dict[str, Any] | None,
        progress,
    ) -> dict[str, Any]:
        del db, assumptions
        if progress is not None:
            await progress(
                {
                    "progress": 14,
                    "stage": "Loading market history",
                    "detail": "Fetching candles.",
                    "interval": interval or "15m",
                    "metrics": {
                        "total_requests": 2,
                        "completed_requests": 0,
                    },
                }
            )
        if self.should_fail:
            raise RuntimeError("Backtest worker failed.")
        return {
            "id": "run-1",
            "bot_definition_id": bot_id,
            "bot_name_snapshot": "Momentum",
            "market_scope_snapshot": "BTC-PERP",
            "strategy_type_snapshot": "trend",
            "interval": interval or "15m",
            "start_time": start_time,
            "end_time": end_time,
            "initial_capital_usd": initial_capital_usd,
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
            "user_id": user_id,
            "wallet_address": wallet_address,
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
                    "interval": interval or "15m",
                    "initial_capital_usd": initial_capital_usd,
                    "ending_equity": initial_capital_usd + 125.0,
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


def _user() -> AuthenticatedUser:
    return AuthenticatedUser(user_id="user-123", wallet_addresses=["wallet-abc"])


def test_builder_ai_job_runner_marks_completed() -> None:
    jobs = _FakeJobService()
    runner = AiJobRunnerService(job_service=jobs, builder_ai_service=_FakeBuilderAiService())

    asyncio.run(
        runner._run_builder_ai_chat_job(
            job_id="job-1",
            messages=[{"role": "user", "content": "Build BTC"}],
            available_markets=["BTC"],
            current_draft=None,
        )
    )

    assert jobs.running_jobs == ["job-1"]
    assert jobs.completed_jobs[0][0] == "job-1"
    assert jobs.completed_jobs[0][1]["draft"]["markets"] == ["BTC"]
    assert jobs.failed_jobs == []


def test_copilot_job_runner_marks_failed() -> None:
    jobs = _FakeJobService()
    runner = AiJobRunnerService(
        job_service=jobs,
        copilot_conversation_service=_FakeCopilotConversationService(should_fail=True),
    )

    asyncio.run(
        runner._run_copilot_chat_job(
            job_id="job-2",
            user=_user(),
            content="Summarize my bots",
            conversation_id="conv-1",
            wallet_address="wallet-abc",
        )
    )

    assert jobs.running_jobs == ["job-2"]
    assert jobs.completed_jobs == []
    assert jobs.failed_jobs == [("job-2", "OpenAI request timed out.")]


def test_builder_ai_job_runner_marks_failed_when_completion_persistence_breaks() -> None:
    jobs = _FakeJobService(fail_complete=True)
    runner = AiJobRunnerService(job_service=jobs, builder_ai_service=_FakeBuilderAiService())

    asyncio.run(
        runner._run_builder_ai_chat_job(
            job_id="job-3",
            messages=[{"role": "user", "content": "Build BTC"}],
            available_markets=["BTC"],
            current_draft=None,
        )
    )

    assert jobs.running_jobs == ["job-3"]
    assert jobs.completed_jobs == []
    assert jobs.failed_jobs == [("job-3", "Could not persist completed AI job.")]


def test_backtest_job_runner_persists_progress_then_result() -> None:
    jobs = _FakeJobService()
    runner = AiJobRunnerService(job_service=jobs, bot_backtest_service=_FakeBacktestService())

    asyncio.run(
        runner._run_backtest_run_job(
            job_id="job-4",
            bot_id="bot-1",
            wallet_address="wallet-abc",
            user_id="user-123",
            interval="1m",
            start_time=1,
            end_time=2,
            initial_capital_usd=10_000,
            assumptions=None,
        )
    )

    assert jobs.running_jobs == ["job-4"]
    assert jobs.progress_jobs == [
        (
            "job-4",
            {
                "type": "progress",
                "progress": 14,
                "stage": "Loading market history",
                "detail": "Fetching candles.",
                "interval": "1m",
                "metrics": {
                    "total_requests": 2,
                    "completed_requests": 0,
                },
            },
        )
    ]
    assert jobs.completed_jobs[0][0] == "job-4"
    assert jobs.completed_jobs[0][1]["type"] == "result"
    assert jobs.completed_jobs[0][1]["run"]["id"] == "run-1"
    assert jobs.failed_jobs == []


def test_backtest_job_runner_offloads_work_from_server_loop(monkeypatch) -> None:
    jobs = _FakeJobService()
    runner = AiJobRunnerService(job_service=jobs, bot_backtest_service=_FakeBacktestService())
    offloaded: dict[str, bool] = {"used": False}
    original_to_thread = asyncio.to_thread

    async def fake_to_thread(func, /, *args, **kwargs):
        offloaded["used"] = True
        return await original_to_thread(func, *args, **kwargs)

    monkeypatch.setattr("src.services.ai_job_runner_service.asyncio.to_thread", fake_to_thread)

    asyncio.run(
        runner._run_backtest_run_job(
            job_id="job-5",
            bot_id="bot-1",
            wallet_address="wallet-abc",
            user_id="user-123",
            interval="1m",
            start_time=1,
            end_time=2,
            initial_capital_usd=10_000,
            assumptions=None,
        )
    )

    assert offloaded["used"] is True
    assert jobs.completed_jobs[0][0] == "job-5"
