from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import UTC, datetime
from time import monotonic
from time import perf_counter

from src.core.performance_metrics import get_performance_metrics_store
from src.services.bot_runtime_snapshot_service import BotRuntimeSnapshotService
from src.services.supabase_rest import SupabaseRestClient, SupabaseRestError
from src.services.worker_coordination_service import WorkerCoordinationService


logger = logging.getLogger(__name__)


class BotRuntimeSnapshotWorker:
    def __init__(self, poll_interval_seconds: float = 30.0) -> None:
        self.poll_interval_seconds = poll_interval_seconds
        self._task: asyncio.Task | None = None
        self._running = False
        self._supabase = SupabaseRestClient()
        self._coordination = WorkerCoordinationService(self._supabase)
        self._metrics = get_performance_metrics_store()
        self._snapshots = BotRuntimeSnapshotService(supabase=self._supabase)
        self._held_leases: dict[str, float] = {}
        self.last_iteration_at: str | None = None
        self.last_error: str | None = None

    def start(self) -> asyncio.Task:
        if self._task and not self._task.done():
            return self._task
        self._running = True
        self._task = asyncio.create_task(self.run_forever(), name="bot-runtime-snapshot-worker")
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
                runtimes = await asyncio.to_thread(
                    self._supabase.select,
                    "bot_runtimes",
                    columns="id,wallet_address",
                )
                wallet_addresses = sorted(
                    {
                        str(runtime.get("wallet_address") or "").strip()
                        for runtime in runtimes
                        if str(runtime.get("wallet_address") or "").strip()
                    }
                )
                for wallet_address in wallet_addresses:
                    lease_key = f"bot-runtime-snapshots:{wallet_address}"
                    if not self._claim_local_lease(
                        lease_key,
                        ttl_seconds=max(45, int(self.poll_interval_seconds * 3)),
                    ):
                        continue
                    await self._snapshots.refresh_wallet_snapshots(wallet_address)
                self.last_iteration_at = datetime.now(tz=UTC).isoformat()
                self.last_error = None
            except SupabaseRestError as exc:
                self.last_error = str(exc)
                if exc.is_retryable:
                    logger.warning("Bot runtime snapshot worker deferred because Supabase is temporarily unavailable: %s", exc)
                else:
                    logger.exception("Bot runtime snapshot worker iteration failed")
            except Exception as exc:
                self.last_error = str(exc)
                logger.exception("Bot runtime snapshot worker iteration failed")
            finally:
                self._metrics.record("worker:bot_runtime_snapshot:iteration", (perf_counter() - iteration_started) * 1000.0)
            await asyncio.sleep(self.poll_interval_seconds)

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

    def _release_held_leases(self) -> None:
        for lease_key in list(self._held_leases):
            self._coordination.release_lease(lease_key)
        self._held_leases.clear()

    @property
    def is_running(self) -> bool:
        return bool(self._task and not self._task.done())
