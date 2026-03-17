from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from src.core.settings import get_settings
from src.models.leaderboard_snapshot import LeaderboardSnapshot
from src.models.league_participant import LeagueParticipant
from src.models.user import User
from src.services.event_broadcaster import broadcaster
from src.services.pacifica_client import PacificaClient
from src.services.supabase_rest import SupabaseRestClient


class LeaderboardEngine:
    def __init__(self, pacifica_client: PacificaClient | None = None) -> None:
        self.settings = get_settings()
        self.pacifica_client = pacifica_client or PacificaClient()
        self.supabase = SupabaseRestClient() if self.settings.use_supabase_api else None

    async def refresh_league(self, db: Session, league_id: str) -> list[dict]:
        if self.settings.use_supabase_api:
            participants = self.supabase.select("league_participants", filters={"league_id": league_id, "is_active": True})
            user_ids = [participant["user_id"] for participant in participants]
            users = {
                row["id"]: row
                for row in self.supabase.select("users", filters={"id": ("in", user_ids)})
            } if user_ids else {}
            now = datetime.now(tz=UTC)

            rows: list[dict] = []
            for participant in participants:
                user = users.get(participant["user_id"])
                if user is None:
                    continue
                positions = await self.pacifica_client.get_positions(user["wallet_address"])
                position_history = await self.pacifica_client.get_position_history(user["wallet_address"], limit=100)
                unrealized = self._compute_unrealized_pnl(positions)
                realized = self._compute_realized_pnl(position_history)
                win_streak = self._compute_win_streak(position_history)
                created_at = datetime.fromisoformat(user["created_at"].replace("Z", "+00:00"))
                rows.append(
                    {
                        "participant": participant,
                        "user": user,
                        "created_at": created_at,
                        "unrealized_pnl": unrealized,
                        "realized_pnl": realized,
                        "win_streak": int(win_streak),
                    }
                )

            rows.sort(key=lambda row: (-row["unrealized_pnl"], -row["win_streak"], row["created_at"]))
            captured_at = now.isoformat()
            self.supabase.delete("leaderboard_snapshots", filters={"league_id": league_id})

            payload: list[dict] = []
            leaderboard: list[dict] = []
            for index, row in enumerate(rows, start=1):
                payload.append(
                    {
                        "id": self._uuid(),
                        "league_id": league_id,
                        "user_id": row["user"]["id"],
                        "rank": index,
                        "unrealized_pnl": row["unrealized_pnl"],
                        "realized_pnl": row["realized_pnl"],
                        "win_streak": row["win_streak"],
                        "captured_at": captured_at,
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
                        "captured_at": captured_at,
                    }
                )
            if payload:
                self.supabase.insert("leaderboard_snapshots", payload)
            await broadcaster.publish(
                channel=f"league:{league_id}",
                event="leaderboard.update",
                payload={"league_id": league_id, "rows": leaderboard, "captured_at": captured_at},
            )
            return leaderboard

        participants = db.execute(
            select(LeagueParticipant, User)
            .join(User, User.id == LeagueParticipant.user_id)
            .where(LeagueParticipant.league_id == league_id, LeagueParticipant.is_active.is_(True))
        ).all()
        now = datetime.now(tz=UTC)
        rows: list[dict] = []
        for participant, user in participants:
            positions = await self.pacifica_client.get_positions(user.wallet_address)
            position_history = await self.pacifica_client.get_position_history(user.wallet_address, limit=100)
            unrealized = self._compute_unrealized_pnl(positions)
            realized = self._compute_realized_pnl(position_history)
            win_streak = self._compute_win_streak(position_history)
            rows.append(
                {
                    "participant": participant,
                    "user": user,
                    "unrealized_pnl": unrealized,
                    "realized_pnl": realized,
                    "win_streak": int(win_streak),
                }
            )

        rows.sort(key=lambda row: (-row["unrealized_pnl"], -row["win_streak"], row["user"].created_at))

        captured_at = now
        db.execute(delete(LeaderboardSnapshot).where(LeaderboardSnapshot.league_id == league_id))

        leaderboard: list[dict] = []
        for index, row in enumerate(rows, start=1):
            snapshot = LeaderboardSnapshot(
                league_id=league_id,
                user_id=row["user"].id,
                rank=index,
                unrealized_pnl=row["unrealized_pnl"],
                realized_pnl=row["realized_pnl"],
                win_streak=row["win_streak"],
                captured_at=captured_at,
            )
            db.add(snapshot)
            leaderboard.append(
                {
                    "user_id": row["user"].id,
                    "display_name": row["user"].display_name or row["user"].wallet_address[:8],
                    "wallet_address": row["user"].wallet_address,
                    "rank": index,
                    "unrealized_pnl": row["unrealized_pnl"],
                    "realized_pnl": row["realized_pnl"],
                    "win_streak": row["win_streak"],
                    "captured_at": captured_at,
                }
            )

        db.commit()
        await broadcaster.publish(
            channel=f"league:{league_id}",
            event="leaderboard.update",
            payload={"league_id": league_id, "rows": leaderboard, "captured_at": captured_at.isoformat()},
        )
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
        total = 0.0
        for item in position_history:
            total += float(item.get("pnl", 0) or 0)
        return round(total, 2)

    @staticmethod
    def _compute_win_streak(position_history: list[dict]) -> int:
        streak = 0
        for item in sorted(
            position_history,
            key=lambda entry: str(entry.get("created_at") or ""),
            reverse=True,
        ):
            event_type = str(item.get("event_type", "")).lower()
            if not event_type.startswith("close"):
                continue
            pnl = float(item.get("pnl", 0) or 0)
            if pnl > 0:
                streak += 1
                continue
            break
        return streak

    @staticmethod
    def _uuid() -> str:
        import uuid

        return str(uuid.uuid4())
