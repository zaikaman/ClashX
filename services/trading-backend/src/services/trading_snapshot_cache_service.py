from __future__ import annotations

import asyncio
from copy import deepcopy
from time import time
from typing import Any

from src.core.settings import get_settings


class TradingSnapshotCacheService:
    def __init__(self) -> None:
        self._ttl = get_settings().pacifica_snapshot_cache_ttl_seconds
        self._entries: dict[str, tuple[float, dict[str, Any]]] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    async def get_or_load(self, wallet_address: str, loader: Any) -> dict[str, Any]:
        cached = self._entries.get(wallet_address)
        if cached is not None and (time() - cached[0]) < self._ttl:
            return deepcopy(cached[1])
        lock = self._locks.setdefault(wallet_address, asyncio.Lock())
        async with lock:
            cached = self._entries.get(wallet_address)
            if cached is not None and (time() - cached[0]) < self._ttl:
                return deepcopy(cached[1])
            snapshot = await loader()
            self._entries[wallet_address] = (time(), deepcopy(snapshot))
            return deepcopy(snapshot)

    def invalidate(self, wallet_address: str) -> None:
        self._entries.pop(wallet_address, None)


_snapshot_cache_service: TradingSnapshotCacheService | None = None


def get_trading_snapshot_cache_service() -> TradingSnapshotCacheService:
    global _snapshot_cache_service
    if _snapshot_cache_service is None:
        _snapshot_cache_service = TradingSnapshotCacheService()
    return _snapshot_cache_service
