from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from src.services.supabase_rest import SupabaseRestClient


class LeagueService:
    def __init__(self, supabase: SupabaseRestClient | None = None) -> None:
        self.supabase = supabase or SupabaseRestClient()

    def list_leagues(self, db: Any, status: str | None = None) -> list[dict]:
        del db
        filters = {"status": status} if status else None
        leagues = self.supabase.select("leagues", filters=filters, order="start_at.desc")
        registrations = self.supabase.select("league_participants", filters={"is_active": True})
        registration_counts: dict[str, int] = {}
        for registration in registrations:
            league_id = registration["league_id"]
            registration_counts[league_id] = registration_counts.get(league_id, 0) + 1
        return [
            {
                "id": league["id"],
                "name": league["name"],
                "description": league["description"],
                "status": league["status"],
                "market_scope": league["market_scope"],
                "start_at": league["start_at"],
                "end_at": league["end_at"],
                "registration_count": registration_counts.get(league["id"], 0),
            }
            for league in leagues
        ]

    def register_bot(self, db: Any, *, league_id: str, wallet_address: str, display_name: str | None = None) -> dict:
        del db
        league = self.supabase.maybe_one("leagues", filters={"id": league_id})
        if league is None:
            raise ValueError("Competition not found")
        if league["status"] != "live":
            raise ValueError("Only live competitions accept registrations")
        user = self.supabase.maybe_one("users", filters={"wallet_address": wallet_address})
        if user is None:
            user = self.supabase.insert(
                "users",
                {
                    "id": str(uuid.uuid4()),
                    "wallet_address": wallet_address,
                    "display_name": display_name or wallet_address[:8],
                    "auth_provider": "privy",
                    "created_at": datetime.now(tz=UTC).isoformat(),
                },
            )[0]
        elif display_name and user.get("display_name") != display_name:
            user = self.supabase.update("users", {"display_name": display_name}, filters={"id": user["id"]})[0]
        memberships = self.supabase.select("league_participants", filters={"user_id": user["id"], "is_active": True})
        if memberships:
            league_ids = [membership["league_id"] for membership in memberships]
            live_leagues = self.supabase.select("leagues", filters={"id": ("in", league_ids), "status": "live"})
            for live in live_leagues:
                if live["id"] == league_id:
                    return {"league_id": league_id, "already_registered": True}
                raise ValueError("Wallet already has a bot registered in another live competition")
        self.supabase.insert(
            "league_participants",
            {
                "id": str(uuid.uuid4()),
                "league_id": league_id,
                "user_id": user["id"],
                "joined_at": datetime.now(tz=UTC).isoformat(),
                "is_active": True,
            },
        )
        return {"league_id": league_id, "user_id": user["id"], "display_name": user.get("display_name"), "already_registered": False}

    def join_league(self, db: Any, *, league_id: str, wallet_address: str, display_name: str | None = None) -> dict:
        return self.register_bot(db, league_id=league_id, wallet_address=wallet_address, display_name=display_name)

    def get_league(self, db: Any, league_id: str) -> dict[str, Any] | None:
        del db
        return self.supabase.maybe_one("leagues", filters={"id": league_id})

    def get_live_leagues(self, db: Any) -> list[dict[str, Any]]:
        del db
        return self.supabase.select("leagues", filters={"status": "live"})

    def get_leaderboard(self, db: Any, league_id: str, limit: int = 100) -> list[dict]:
        del db
        rows = self.supabase.select("leaderboard_snapshots", filters={"league_id": league_id}, order="captured_at.desc", limit=limit)
        if not rows:
            return []
        latest = rows[0]["captured_at"]
        rows = [row for row in rows if row["captured_at"] == latest][:limit]
        user_ids = [row["user_id"] for row in rows]
        users = {row["id"]: row for row in self.supabase.select("users", filters={"id": ("in", user_ids)})} if user_ids else {}
        rows.sort(key=lambda row: row["rank"])
        return [
            {
                "user_id": row["user_id"],
                "display_name": users.get(row["user_id"], {}).get("display_name") or users.get(row["user_id"], {}).get("wallet_address", "")[:8],
                "wallet_address": users.get(row["user_id"], {}).get("wallet_address", ""),
                "rank": row["rank"],
                "unrealized_pnl": row["unrealized_pnl"],
                "realized_pnl": row["realized_pnl"],
                "win_streak": row["win_streak"],
                "captured_at": row["captured_at"],
            }
            for row in rows
        ]
