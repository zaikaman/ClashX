from __future__ import annotations

import asyncio
import contextlib

from src.db.session import SessionLocal
from src.services.leaderboard_engine import LeaderboardEngine
from src.services.league_service import LeagueService
from src.services.pacifica_client import PacificaClientError


class LeaderboardWorker:
    def __init__(self, poll_interval_seconds: float = 5.0) -> None:
        self.poll_interval_seconds = poll_interval_seconds
        self._task: asyncio.Task | None = None
        self._running = False
        self._league_service = LeagueService()
        self._engine = LeaderboardEngine()

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
            db = SessionLocal()
            try:
                leagues = self._league_service.get_live_leagues(db)
                for league in leagues:
                    try:
                        await self._engine.refresh_league(db, league.id)
                    except PacificaClientError:
                        continue
            finally:
                db.close()
            await asyncio.sleep(self.poll_interval_seconds)
