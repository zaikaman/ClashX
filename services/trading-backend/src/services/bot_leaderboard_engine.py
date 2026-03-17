from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from src.services.bot_performance_service import BotPerformanceService
from src.services.event_broadcaster import broadcaster
from src.services.pacifica_client import PacificaClient
from src.services.supabase_rest import SupabaseRestClient


class BotLeaderboardEngine:
    def __init__(self, pacifica_client: PacificaClient | None = None) -> None:
        self.supabase = SupabaseRestClient()
        self.pacifica_client = pacifica_client or PacificaClient()
        self.performance_service = BotPerformanceService(pacifica_client=self.pacifica_client, supabase=self.supabase)

    async def refresh_public_leaderboard(self, db: Any, *, limit: int = 100) -> list[dict]:
        del db
        runtimes = self.supabase.select("bot_runtimes", filters={"status": "active"})
        definition_ids = [str(runtime["bot_definition_id"]) for runtime in runtimes]
        definitions = {
            row["id"]: row
            for row in self.supabase.select("bot_definitions", filters={"id": ("in", definition_ids), "visibility": "public"})
        } if definition_ids else {}
        ranked_rows: list[dict] = []
        for runtime in runtimes:
            definition = definitions.get(runtime["bot_definition_id"])
            if definition is None:
                continue
            performance = await self.performance_service.calculate_runtime_performance(runtime)
            ranked_rows.append(
                {
                    "runtime": runtime,
                    "definition": definition,
                    "pnl_total": performance["pnl_total"],
                    "pnl_unrealized": performance["pnl_unrealized"],
                    "win_streak": performance["win_streak"],
                    "drawdown": self._extract_drawdown(runtime.get("risk_policy_json")),
                }
            )
        ranked_rows.sort(
            key=lambda item: (-item["pnl_total"], -item["win_streak"], item["drawdown"], str(item["runtime"].get("updated_at") or ""))
        )
        captured_at = datetime.now(tz=UTC).isoformat()
        self.supabase.delete("bot_leaderboard_snapshots", filters={"captured_at": ("lte", captured_at)})
        leaderboard: list[dict] = []
        snapshots_payload: list[dict] = []
        for index, item in enumerate(ranked_rows[:limit], start=1):
            runtime = item["runtime"]
            definition = item["definition"]
            snapshots_payload.append(
                {
                    "id": str(uuid.uuid4()),
                    "runtime_id": runtime["id"],
                    "rank": index,
                    "pnl_total": item["pnl_total"],
                    "pnl_unrealized": item["pnl_unrealized"],
                    "win_streak": item["win_streak"],
                    "drawdown": item["drawdown"],
                    "captured_at": captured_at,
                }
            )
            leaderboard.append(
                {
                    "runtime_id": runtime["id"],
                    "bot_definition_id": definition["id"],
                    "bot_name": definition["name"],
                    "strategy_type": definition["strategy_type"],
                    "authoring_mode": definition["authoring_mode"],
                    "rank": index,
                    "pnl_total": item["pnl_total"],
                    "pnl_unrealized": item["pnl_unrealized"],
                    "win_streak": item["win_streak"],
                    "drawdown": item["drawdown"],
                    "captured_at": captured_at,
                }
            )
        if snapshots_payload:
            self.supabase.insert("bot_leaderboard_snapshots", snapshots_payload)
        await broadcaster.publish(channel="bots:leaderboard", event="bots.leaderboard.update", payload={"captured_at": captured_at, "rows": leaderboard})
        return leaderboard

    @staticmethod
    def _extract_drawdown(risk_policy_json: dict | None) -> float:
        if not isinstance(risk_policy_json, dict):
            return 0.0
        runtime_state = risk_policy_json.get("_runtime_state")
        if not isinstance(runtime_state, dict):
            return 0.0
        try:
            return float(runtime_state.get("drawdown_pct", 0.0) or 0.0)
        except (TypeError, ValueError):
            return 0.0
