from __future__ import annotations

import asyncio
from collections.abc import Sequence
from typing import Any

from src.api.auth import AuthenticatedUser
from src.services.ai_job_service import AiJobService
from src.services.builder_ai_service import BuilderAiService
from src.services.copilot_conversation_service import CopilotConversationService


class AiJobRunnerService:
    def __init__(
        self,
        *,
        job_service: AiJobService | None = None,
        builder_ai_service: BuilderAiService | None = None,
        copilot_conversation_service: CopilotConversationService | None = None,
    ) -> None:
        self._job_service = job_service or AiJobService()
        self._builder_ai = builder_ai_service or BuilderAiService()
        self._copilot_conversations = copilot_conversation_service or CopilotConversationService()
        self._tasks: set[asyncio.Task[None]] = set()

    def start_builder_ai_chat_job(
        self,
        *,
        job_id: str,
        messages: Sequence[dict[str, str]],
        available_markets: Sequence[str],
        current_draft: dict[str, Any] | None,
    ) -> None:
        self._launch(
            self._run_builder_ai_chat_job(
                job_id=job_id,
                messages=[dict(message) for message in messages],
                available_markets=[str(market) for market in available_markets],
                current_draft=dict(current_draft) if isinstance(current_draft, dict) else None,
            ),
            name=f"builder-ai-job:{job_id}",
        )

    def start_copilot_chat_job(
        self,
        *,
        job_id: str,
        user: AuthenticatedUser,
        content: str,
        conversation_id: str | None,
        wallet_address: str | None,
    ) -> None:
        self._launch(
            self._run_copilot_chat_job(
                job_id=job_id,
                user=user,
                content=content,
                conversation_id=conversation_id,
                wallet_address=wallet_address,
            ),
            name=f"copilot-chat-job:{job_id}",
        )

    def _launch(self, coro: Any, *, name: str) -> None:
        task = asyncio.create_task(coro, name=name)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _run_builder_ai_chat_job(
        self,
        *,
        job_id: str,
        messages: list[dict[str, str]],
        available_markets: list[str],
        current_draft: dict[str, Any] | None,
    ) -> None:
        self._job_service.mark_running(job_id=job_id)
        try:
            result = await self._builder_ai.generate_draft(
                messages=messages,
                available_markets=available_markets,
                current_draft=current_draft,
            )
        except Exception as exc:
            self._job_service.mark_failed(job_id=job_id, error_detail=str(exc) or "Builder AI job failed.")
            return
        self._job_service.mark_completed(job_id=job_id, result_payload=result)

    async def _run_copilot_chat_job(
        self,
        *,
        job_id: str,
        user: AuthenticatedUser,
        content: str,
        conversation_id: str | None,
        wallet_address: str | None,
    ) -> None:
        self._job_service.mark_running(job_id=job_id)
        try:
            result = await self._copilot_conversations.send_message(
                user=user,
                content=content,
                conversation_id=conversation_id,
                wallet_address=wallet_address,
            )
        except Exception as exc:
            self._job_service.mark_failed(job_id=job_id, error_detail=str(exc) or "Copilot job failed.")
            return
        self._job_service.mark_completed(job_id=job_id, result_payload=result)
