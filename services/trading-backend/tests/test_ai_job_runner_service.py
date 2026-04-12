from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from src.api.auth import AuthenticatedUser
from src.services.ai_job_runner_service import AiJobRunnerService


@dataclass
class _FakeJobService:
    running_jobs: list[str] = field(default_factory=list)
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
