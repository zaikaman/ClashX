from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import UTC, datetime

from src.services.leaderboard_engine import LeaderboardEngine
from src.services.league_service import LeagueService
from src.services.pacifica_client import PacificaClientError
from src.services.worker_coordination_service import WorkerCoordinationService


logger = logging.getLogger(__name__)


class LeaderboardWorker:
    def __init__(self, poll_interval_seconds: float = 5.0) -> None:
        self.poll_interval_seconds = poll_interval_seconds
        self._task: asyncio.Task | None = None
        self._running = False
        self._league_service = LeagueService()
        self._engine = LeaderboardEngine()
        self._coordination = WorkerCoordinationService()
        self.last_iteration_at: str | None = None
        self.last_error: str | None = None

    def start(self) -> asyncio.Task:
        if self._task and not self._task.done():
            return self._task
        self._running = True
        self._task = asyncio.create_task(self.run_forever(), name="leaderboard-worker")
        return self._task

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

    async def run_forever(self) -> None:
        while self._running:
            try:
                leagues = self._league_service.get_live_leagues(None)
                for league in leagues:
                    lease_key = f"leaderboard:{league['id']}"
                    if not self._coordination.try_claim_lease(
                        lease_key, ttl_seconds=max(15, int(self.poll_interval_seconds * 3))
                    ):
                        continue
                    try:
                        await self._engine.refresh_league(None, league["id"])
                    except PacificaClientError:
                        continue
                    finally:
                        self._coordination.release_lease(lease_key)
                self.last_iteration_at = datetime.now(tz=UTC).isoformat()
                self.last_error = None
            except Exception as exc:
                self.last_error = str(exc)
                logger.exception("Leaderboard worker iteration failed")
            await asyncio.sleep(self.poll_interval_seconds)

    @property
    def is_running(self) -> bool:
        return bool(self._task and not self._task.done())
