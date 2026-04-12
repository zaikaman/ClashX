from __future__ import annotations

import asyncio
import time
from collections import deque
from functools import lru_cache

from src.core.settings import get_settings

class PacificaRateLimiter:
    def __init__(self) -> None:
        self._settings = get_settings()
        self._bucket_events: dict[str, deque[float]] = {}
        self._bucket_locks: dict[str, asyncio.Lock] = {}

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
        if limit <= 0:
            return
        lock = self._bucket_locks.setdefault(bucket, asyncio.Lock())
        events = self._bucket_events.setdefault(bucket, deque())
        while True:
            sleep_seconds = 0.0
            async with lock:
                now = time.monotonic()
                cutoff = now - 1.0
                while events and events[0] <= cutoff:
                    events.popleft()
                if len(events) < limit:
                    events.append(now)
                    return
                sleep_seconds = max(0.01, 1.0 - (now - events[0]))
            await asyncio.sleep(sleep_seconds)


@lru_cache(maxsize=1)
def get_pacifica_rate_limiter() -> PacificaRateLimiter:
    return PacificaRateLimiter()
