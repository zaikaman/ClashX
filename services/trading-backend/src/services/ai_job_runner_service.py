from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence
from typing import Any

from src.api.auth import AuthenticatedUser
from src.services.ai_job_service import AiJobService
from src.services.bot_backtest_service import BotBacktestService
from src.services.builder_ai_service import BuilderAiService
from src.services.copilot_conversation_service import CopilotConversationService

logger = logging.getLogger(__name__)


class AiJobRunnerService:
    def __init__(
        self,
        *,
        job_service: AiJobService | None = None,
        builder_ai_service: BuilderAiService | None = None,
        copilot_conversation_service: CopilotConversationService | None = None,
        bot_backtest_service: BotBacktestService | None = None,
    ) -> None:
        self._job_service = job_service or AiJobService()
        self._builder_ai = builder_ai_service or BuilderAiService()
        self._copilot_conversations = copilot_conversation_service or CopilotConversationService()
        self._bot_backtests = bot_backtest_service or BotBacktestService()
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

    def start_backtest_run_job(
        self,
        *,
        job_id: str,
        bot_id: str,
        wallet_address: str,
        user_id: str,
        interval: str | None,
        start_time: int,
        end_time: int,
        initial_capital_usd: float,
        assumptions: dict[str, Any] | None,
    ) -> None:
        self._launch(
            self._run_backtest_run_job(
                job_id=job_id,
                bot_id=bot_id,
                wallet_address=wallet_address,
                user_id=user_id,
                interval=interval,
                start_time=start_time,
                end_time=end_time,
                initial_capital_usd=initial_capital_usd,
                assumptions=dict(assumptions) if isinstance(assumptions, dict) else None,
            ),
            name=f"backtest-run-job:{job_id}",
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
            logger.exception("Builder AI job %s failed", job_id)
            self._job_service.mark_failed(job_id=job_id, error_detail=str(exc) or "Builder AI job failed.")
            return
        try:
            self._job_service.mark_completed(job_id=job_id, result_payload=result)
        except Exception as exc:
            logger.exception("Builder AI job %s could not be marked completed", job_id)
            self._job_service.mark_failed(job_id=job_id, error_detail=str(exc) or "Builder AI job failed.")

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
            logger.exception("Copilot job %s failed", job_id)
            self._job_service.mark_failed(job_id=job_id, error_detail=str(exc) or "Copilot job failed.")
            return
        try:
            self._job_service.mark_completed(job_id=job_id, result_payload=result)
        except Exception as exc:
            logger.exception("Copilot job %s could not be marked completed", job_id)
            self._job_service.mark_failed(job_id=job_id, error_detail=str(exc) or "Copilot job failed.")

    async def _run_backtest_run_job(
        self,
        *,
        job_id: str,
        bot_id: str,
        wallet_address: str,
        user_id: str,
        interval: str | None,
        start_time: int,
        end_time: int,
        initial_capital_usd: float,
        assumptions: dict[str, Any] | None,
    ) -> None:
        self._job_service.mark_running(job_id=job_id)

        async def progress_callback(payload: dict[str, Any]) -> None:
            self._job_service.update_progress(
                job_id=job_id,
                progress_payload={
                    "type": "progress",
                    **payload,
                },
            )

        try:
            result = await self._bot_backtests.run_backtest(
                None,
                bot_id=bot_id,
                wallet_address=wallet_address,
                user_id=user_id,
                interval=interval,
                start_time=start_time,
                end_time=end_time,
                initial_capital_usd=initial_capital_usd,
                assumptions=assumptions,
                progress=progress_callback,
            )
        except Exception as exc:
            logger.exception("Backtest job %s failed", job_id)
            self._job_service.mark_failed(job_id=job_id, error_detail=str(exc) or "Backtest job failed.")
            return
        try:
            self._job_service.mark_completed(
                job_id=job_id,
                result_payload={
                    "type": "result",
                    "run": result,
                },
            )
        except Exception as exc:
            logger.exception("Backtest job %s could not be marked completed", job_id)
            self._job_service.mark_failed(job_id=job_id, error_detail=str(exc) or "Backtest job failed.")
