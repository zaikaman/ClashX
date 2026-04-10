from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import UTC, datetime
from time import monotonic
from time import perf_counter

from src.core.performance_metrics import get_performance_metrics_store
from src.services.portfolio_allocator_service import PortfolioAllocatorService
from src.services.supabase_rest import SupabaseRestClient, SupabaseRestError
from src.services.worker_coordination_service import WorkerCoordinationService


logger = logging.getLogger(__name__)


class PortfolioAllocatorWorker:
    def __init__(self, poll_interval_seconds: float = 12.0) -> None:
        self.poll_interval_seconds = poll_interval_seconds
        self._task: asyncio.Task | None = None
        self._running = False
        self._supabase = SupabaseRestClient()
        self._coordination = WorkerCoordinationService(self._supabase)
        self._metrics = get_performance_metrics_store()
        self._allocator = PortfolioAllocatorService()
        self._held_leases: dict[str, float] = {}
        self.last_iteration_at: str | None = None
        self.last_error: str | None = None

    def start(self) -> asyncio.Task:
        if self._task and not self._task.done():
            return self._task
        self._running = True
        self._task = asyncio.create_task(self.run_forever(), name="portfolio-allocator-worker")
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
                baskets = await asyncio.to_thread(
                    self._supabase.select,
                    "portfolio_baskets",
                    columns="id",
                    filters={"status": ("in", ["active", "paused", "killed"])},
                )
                for basket in baskets:
                    lease_key = f"portfolio-allocator:{basket['id']}"
                    if not self._claim_local_lease(
                        lease_key,
                        ttl_seconds=max(20, int(self.poll_interval_seconds * 3)),
                    ):
                        continue
                    await self._process_basket(str(basket["id"]))
                self.last_iteration_at = datetime.now(tz=UTC).isoformat()
                self.last_error = None
            except SupabaseRestError as exc:
                self.last_error = str(exc)
                if exc.is_retryable:
                    logger.warning("Portfolio allocator worker deferred because Supabase is temporarily unavailable: %s", exc)
                else:
                    logger.exception("Portfolio allocator worker iteration failed")
            except Exception as exc:
                self.last_error = str(exc)
                logger.exception("Portfolio allocator worker iteration failed")
            finally:
                self._metrics.record("worker:portfolio_allocator:iteration", (perf_counter() - iteration_started) * 1000.0)
            await asyncio.sleep(self.poll_interval_seconds)

    async def _process_basket(self, portfolio_id: str) -> None:
        detail = await asyncio.to_thread(self._allocator.refresh_portfolio_metrics, portfolio_id=portfolio_id)
        health = detail["health"]
        if health["should_kill_switch"] and detail["status"] == "active":
            reason = "; ".join(health["alerts"][:2]) or "Portfolio risk policy breach"
            await self._allocator.set_kill_switch(
                portfolio_id=portfolio_id,
                wallet_address=detail["wallet_address"],
                engaged=True,
                reason=reason,
                trigger="worker_risk",
            )
            return
        if health["needs_rebalance"] and detail["status"] == "active":
            await self._allocator.rebalance_portfolio(
                portfolio_id=portfolio_id,
                wallet_address=detail["wallet_address"],
                trigger="worker_cycle",
            )

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
