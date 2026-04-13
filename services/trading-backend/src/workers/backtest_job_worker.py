from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import UTC, datetime, timedelta
from time import monotonic, perf_counter
from typing import Any

from src.core.performance_metrics import get_performance_metrics_store
from src.services.ai_job_runner_service import AiJobRunnerService
from src.services.ai_job_service import AiJobService
from src.services.bot_backtest_service import BotBacktestService
from src.services.supabase_rest import SupabaseRestClient, SupabaseRestError
from src.services.worker_coordination_service import WorkerCoordinationService


logger = logging.getLogger(__name__)
DEFAULT_BACKTEST_JOB_POLL_SECONDS = 5.0
BACKTEST_JOB_LEASE_TTL_SECONDS = 5 * 60
BACKTEST_JOB_STALE_AFTER_SECONDS = 2 * 60
BACKTEST_JOB_BATCH_SIZE = 6


class BacktestJobWorker:
    def __init__(
        self,
        poll_interval_seconds: float = DEFAULT_BACKTEST_JOB_POLL_SECONDS,
        *,
        stale_after_seconds: int = BACKTEST_JOB_STALE_AFTER_SECONDS,
        supabase: SupabaseRestClient | None = None,
        job_service: AiJobService | None = None,
        runner: AiJobRunnerService | None = None,
        coordination: WorkerCoordinationService | None = None,
    ) -> None:
        self.poll_interval_seconds = poll_interval_seconds
        self.stale_after_seconds = stale_after_seconds
        self._task: asyncio.Task | None = None
        self._running = False
        self._supabase = supabase or SupabaseRestClient()
        self._jobs = job_service or AiJobService(supabase=self._supabase)
        self._runner = runner or AiJobRunnerService(
            job_service=self._jobs,
            bot_backtest_service=BotBacktestService(supabase=self._supabase),
        )
        self._coordination = coordination or WorkerCoordinationService(self._supabase)
        self._metrics = get_performance_metrics_store()
        self._held_leases: dict[str, float] = {}
        self.last_iteration_at: str | None = None
        self.last_error: str | None = None

    def start(self) -> asyncio.Task:
        if self._task and not self._task.done():
            return self._task
        self._running = True
        self._task = asyncio.create_task(self.run_forever(), name="backtest-job-worker")
        return self._task

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        self._release_held_leases()

    async def run_forever(self) -> None:
        while self._running:
            iteration_started = perf_counter()
            try:
                candidates = await asyncio.to_thread(self._load_candidate_jobs)
                for job in candidates:
                    job_id = str(job.get("id") or "").strip()
                    if not job_id:
                        continue
                    lease_key = self._lease_key(job_id)
                    if not self._claim_local_lease(lease_key, ttl_seconds=BACKTEST_JOB_LEASE_TTL_SECONDS):
                        continue
                    await self._process_job(job)
                self.last_iteration_at = datetime.now(tz=UTC).isoformat()
                self.last_error = None
            except SupabaseRestError as exc:
                self.last_error = str(exc)
                if exc.is_retryable:
                    logger.warning("Backtest job worker iteration deferred because Supabase is temporarily unavailable: %s", exc)
                else:
                    logger.exception("Backtest job worker iteration failed")
            except Exception as exc:
                self.last_error = str(exc)
                logger.exception("Backtest job worker iteration failed")
            finally:
                self._metrics.record("worker:backtest_job:iteration", (perf_counter() - iteration_started) * 1000.0)
            await asyncio.sleep(self.poll_interval_seconds)

    def _load_candidate_jobs(self) -> list[dict[str, Any]]:
        queued = self._jobs.list_jobs(
            job_type="backtest_run",
            statuses=["queued"],
            order="created_at.asc",
            limit=BACKTEST_JOB_BATCH_SIZE,
        )
        stale_before = (datetime.now(tz=UTC) - timedelta(seconds=self.stale_after_seconds)).isoformat()
        stale_running = self._jobs.list_jobs(
            job_type="backtest_run",
            statuses=["running"],
            updated_before=stale_before,
            order="updated_at.asc",
            limit=BACKTEST_JOB_BATCH_SIZE,
        )
        seen: set[str] = set()
        candidates: list[dict[str, Any]] = []
        for row in [*queued, *stale_running]:
            job_id = str(row.get("id") or "").strip()
            if not job_id or job_id in seen:
                continue
            seen.add(job_id)
            candidates.append(row)
        return candidates

    async def _process_job(self, job: dict[str, Any]) -> None:
        job_id = str(job.get("id") or "").strip()
        request_payload = job.get("request_payload_json") if isinstance(job.get("request_payload_json"), dict) else {}
        result_payload = job.get("result_payload_json") if isinstance(job.get("result_payload_json"), dict) else {}
        resume_checkpoint = result_payload.get("checkpoint") if isinstance(result_payload.get("checkpoint"), dict) else None
        lease_key = self._lease_key(job_id)

        def heartbeat() -> None:
            self._claim_local_lease(lease_key, ttl_seconds=BACKTEST_JOB_LEASE_TTL_SECONDS)

        try:
            bot_id = str(request_payload.get("bot_id") or "").strip()
            wallet_address = str(request_payload.get("wallet_address") or "").strip()
            user_id = str(request_payload.get("user_id") or "").strip()
            if not bot_id or not wallet_address or not user_id:
                raise ValueError("Backtest job payload is missing bot or wallet identity fields.")

            await self._runner._run_backtest_run_job(
                job_id=job_id,
                bot_id=bot_id,
                wallet_address=wallet_address,
                user_id=user_id,
                interval=str(request_payload.get("interval") or "").strip() or None,
                start_time=int(request_payload.get("start_time") or 0),
                end_time=int(request_payload.get("end_time") or 0),
                initial_capital_usd=float(request_payload.get("initial_capital_usd") or 0),
                assumptions=request_payload.get("assumptions") if isinstance(request_payload.get("assumptions"), dict) else None,
                resume_checkpoint=resume_checkpoint,
                heartbeat=heartbeat,
            )
        except ValueError as exc:
            self._jobs.mark_failed(job_id=job_id, error_detail=str(exc))
        finally:
            self._release_lease(lease_key)

    def _claim_local_lease(self, lease_key: str, *, ttl_seconds: int) -> bool:
        refresh_at = self._held_leases.get(lease_key)
        if refresh_at is not None and monotonic() < refresh_at:
            return True
        claimed = self._coordination.try_claim_lease(lease_key, ttl_seconds=ttl_seconds)
        if not claimed:
            self._held_leases.pop(lease_key, None)
            return False
        self._held_leases[lease_key] = monotonic() + max(1.0, ttl_seconds * 0.6)
        return True

    def _release_lease(self, lease_key: str) -> None:
        if lease_key not in self._held_leases:
            return
        self._coordination.release_lease(lease_key)
        self._held_leases.pop(lease_key, None)

    def _release_held_leases(self) -> None:
        for lease_key in list(self._held_leases):
            self._coordination.release_lease(lease_key)
        self._held_leases.clear()

    @staticmethod
    def _lease_key(job_id: str) -> str:
        return f"ai-job:backtest:{job_id}"

    @property
    def is_running(self) -> bool:
        return bool(self._task and not self._task.done())
