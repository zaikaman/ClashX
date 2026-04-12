from __future__ import annotations

import asyncio
import time
from functools import lru_cache

from src.core.settings import get_settings
from src.services.worker_coordination_service import WorkerCoordinationService


class PacificaRateLimiter:
    def __init__(self, coordination: WorkerCoordinationService | None = None) -> None:
        self._settings = get_settings()
        self._coordination = coordination or WorkerCoordinationService()
        self._cursor = 0
        self._cursor_lock = asyncio.Lock()

    async def acquire(self, *, bucket: str, units: int = 1) -> None:
        for _ in range(max(1, units)):
            await self._acquire_global_token()
            if bucket != "global":
                await self._acquire_bucket_token(bucket)

    async def _acquire_global_token(self) -> None:
        await self._acquire_token("global", self._settings.pacifica_global_requests_per_second)

    async def _acquire_bucket_token(self, bucket: str) -> None:
        limits = {
            "public": self._settings.pacifica_public_requests_per_second,
            "private": self._settings.pacifica_private_requests_per_second,
            "write": self._settings.pacifica_write_requests_per_second,
        }
        limit = limits.get(bucket, self._settings.pacifica_global_requests_per_second)
        await self._acquire_token(bucket, limit)

    async def _acquire_token(self, bucket: str, limit: int) -> None:
        while True:
            now = time.time()
            window_start = int(now)
            ttl_seconds = self._lease_ttl_seconds(now=now)
            start_slot = await self._next_slot(limit)
            for offset in range(limit):
                slot = (start_slot + offset) % limit
                lease_key = self._lease_key(bucket=bucket, slot=slot)
                claimed = await asyncio.to_thread(
                    self._coordination.try_claim_lease,
                    lease_key,
                    ttl_seconds=ttl_seconds,
                )
                if claimed:
                    return
            await asyncio.sleep(max(0.01, (window_start + 1) - time.time()))

    async def _next_slot(self, limit: int) -> int:
        async with self._cursor_lock:
            slot = self._cursor % limit
            self._cursor += 1
            return slot

    @staticmethod
    def _lease_key(*, bucket: str, slot: int) -> str:
        return f"rate-budget:{bucket}:{slot}"

    @staticmethod
    def _lease_ttl_seconds(*, now: float) -> float:
        window_end = int(now) + 1
        return max(0.05, (window_end - now) + 0.05)


@lru_cache(maxsize=1)
def get_pacifica_rate_limiter() -> PacificaRateLimiter:
    return PacificaRateLimiter()
