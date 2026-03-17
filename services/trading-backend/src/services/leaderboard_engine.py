from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from src.services.event_broadcaster import broadcaster
from src.services.pacifica_client import PacificaClient
from src.services.supabase_rest import SupabaseRestClient


class LeaderboardEngine:
    def __init__(self, pacifica_client: PacificaClient | None = None) -> None:
        self.pacifica_client = pacifica_client or PacificaClient()
        self.supabase = SupabaseRestClient()

    async def refresh_league(self, db: Any, league_id: str) -> list[dict]:
        del db
        participants = self.supabase.select("league_participants", filters={"league_id": league_id, "is_active": True})
        user_ids = [participant["user_id"] for participant in participants]
        users = {row["id"]: row for row in self.supabase.select("users", filters={"id": ("in", user_ids)})} if user_ids else {}
        now = datetime.now(tz=UTC).isoformat()
        rows: list[dict] = []
        for participant in participants:
            user = users.get(participant["user_id"])
            if user is None:
                continue
            positions = await self.pacifica_client.get_positions(user["wallet_address"])
            position_history = await self.pacifica_client.get_position_history(user["wallet_address"], limit=100)
            rows.append(
                {
                    "user": user,
                    "created_at": datetime.fromisoformat(user["created_at"].replace("Z", "+00:00")),
                    "unrealized_pnl": self._compute_unrealized_pnl(positions),
                    "realized_pnl": self._compute_realized_pnl(position_history),
                    "win_streak": int(self._compute_win_streak(position_history)),
                }
            )
        rows.sort(key=lambda row: (-row["unrealized_pnl"], -row["win_streak"], row["created_at"]))
        self.supabase.delete("leaderboard_snapshots", filters={"league_id": league_id})
        payload: list[dict] = []
        leaderboard: list[dict] = []
        for index, row in enumerate(rows, start=1):
            payload.append(
                {
                    "id": str(uuid.uuid4()),
                    "league_id": league_id,
                    "user_id": row["user"]["id"],
                    "rank": index,
                    "unrealized_pnl": row["unrealized_pnl"],
                    "realized_pnl": row["realized_pnl"],
                    "win_streak": row["win_streak"],
                    "captured_at": now,
                }
            )
            leaderboard.append(
                {
                    "user_id": row["user"]["id"],
                    "display_name": row["user"].get("display_name") or row["user"]["wallet_address"][:8],
                    "wallet_address": row["user"]["wallet_address"],
                    "rank": index,
                    "unrealized_pnl": row["unrealized_pnl"],
                    "realized_pnl": row["realized_pnl"],
                    "win_streak": row["win_streak"],
                    "captured_at": now,
                }
            )
        if payload:
            self.supabase.insert("leaderboard_snapshots", payload)
        await broadcaster.publish(channel=f"league:{league_id}", event="leaderboard.update", payload={"league_id": league_id, "rows": leaderboard, "captured_at": now})
        return leaderboard

    @staticmethod
    def _compute_unrealized_pnl(positions: list[dict]) -> float:
        total = 0.0
        for position in positions:
            amount = float(position.get("amount", 0) or 0)
            entry_price = float(position.get("entry_price", 0) or 0)
            mark_price = float(position.get("mark_price", 0) or 0)
            side = str(position.get("side", "")).lower()
            if amount == 0 or entry_price == 0 or mark_price == 0:
                continue
            direction = -1.0 if side in {"ask", "short", "sell"} else 1.0
            total += (mark_price - entry_price) * amount * direction
        return round(total, 2)

    @staticmethod
    def _compute_realized_pnl(position_history: list[dict]) -> float:
        return round(sum(float(item.get("pnl", 0) or 0) for item in position_history), 2)

    @staticmethod
    def _compute_win_streak(position_history: list[dict]) -> int:
        streak = 0
        for item in sorted(position_history, key=lambda entry: str(entry.get("created_at") or ""), reverse=True):
            event_type = str(item.get("event_type", "")).lower()
            if not event_type.startswith("close"):
                continue
            pnl = float(item.get("pnl", 0) or 0)
            if pnl > 0:
                streak += 1
                continue
            break
        return streak
