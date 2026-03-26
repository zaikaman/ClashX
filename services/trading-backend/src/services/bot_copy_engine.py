from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from src.services.bot_builder_service import BotBuilderService
from src.services.bot_leaderboard_engine import BotLeaderboardEngine
from src.services.bot_performance_service import BotPerformanceService
from src.services.event_broadcaster import broadcaster
from src.services.pacifica_auth_service import PacificaAuthService
from src.services.pacifica_client import PacificaClient, get_pacifica_client
from src.services.supabase_rest import SupabaseRestClient


SNAPSHOT_TTL_SECONDS = 60


class BotCopyEngine:
    def __init__(self, *, leaderboard_engine: BotLeaderboardEngine | None = None, pacifica_client: PacificaClient | None = None) -> None:
        resolved_pacifica = pacifica_client or get_pacifica_client()
        self.supabase = SupabaseRestClient()
        self.leaderboard_engine = leaderboard_engine or BotLeaderboardEngine(pacifica_client=resolved_pacifica)
        self.pacifica_client = resolved_pacifica
        self.performance_service = BotPerformanceService(pacifica_client=self.pacifica_client, supabase=self.supabase)
        self.auth_service = PacificaAuthService()
        self.builder_service = BotBuilderService()

    async def get_or_refresh_leaderboard(self, db: Any, *, limit: int) -> list[dict]:
        del db
        latest = self.supabase.maybe_one("bot_leaderboard_snapshots", order="captured_at.desc")
        if latest is None or self._snapshot_is_stale(latest.get("captured_at")):
            return await self.leaderboard_engine.refresh_public_leaderboard(None, limit=limit)
        snapshots = self.supabase.select("bot_leaderboard_snapshots", filters={"captured_at": latest["captured_at"]}, order="rank.asc", limit=limit)
        runtime_ids = [row["runtime_id"] for row in snapshots]
        runtimes = {row["id"]: row for row in self.supabase.select("bot_runtimes", filters={"id": ("in", runtime_ids)})} if runtime_ids else {}
        definition_ids = [runtime["bot_definition_id"] for runtime in runtimes.values()]
        definitions = {row["id"]: row for row in self.supabase.select("bot_definitions", filters={"id": ("in", definition_ids)})} if definition_ids else {}
        rows: list[dict] = []
        for snapshot in snapshots:
            runtime = runtimes.get(snapshot["runtime_id"])
            if runtime is None:
                continue
            definition = definitions.get(runtime["bot_definition_id"])
            if definition is None or definition["visibility"] != "public":
                continue
            rows.append({"runtime_id": runtime["id"], "bot_definition_id": definition["id"], "bot_name": definition["name"], "strategy_type": definition["strategy_type"], "authoring_mode": definition["authoring_mode"], "rank": snapshot["rank"], "pnl_total": snapshot["pnl_total"], "pnl_unrealized": snapshot["pnl_unrealized"], "win_streak": snapshot["win_streak"], "drawdown": snapshot["drawdown"], "captured_at": snapshot["captured_at"]})
        return rows

    async def runtime_profile(self, db: Any, *, runtime_id: str) -> dict:
        del db
        runtime = self.supabase.maybe_one("bot_runtimes", filters={"id": runtime_id})
        if runtime is None:
            raise ValueError("Runtime not found")
        definition = self.supabase.maybe_one("bot_definitions", filters={"id": runtime["bot_definition_id"]})
        if definition is None:
            raise ValueError("Bot definition not found")
        latest_snapshot = self.supabase.maybe_one("bot_leaderboard_snapshots", filters={"runtime_id": runtime_id}, order="captured_at.desc")
        if latest_snapshot is None or self._snapshot_is_stale(latest_snapshot.get("captured_at")):
            await self.leaderboard_engine.refresh_public_leaderboard(None, limit=100)
            latest_snapshot = self.supabase.maybe_one("bot_leaderboard_snapshots", filters={"runtime_id": runtime_id}, order="captured_at.desc")
        recent_events = self.supabase.select("bot_execution_events", filters={"runtime_id": runtime_id}, order="created_at.desc", limit=12)
        return {
            "runtime_id": runtime["id"],
            "bot_definition_id": definition["id"],
            "bot_name": definition["name"],
            "description": definition["description"],
            "strategy_type": definition["strategy_type"],
            "authoring_mode": definition["authoring_mode"],
            "status": runtime["status"],
            "mode": runtime["mode"],
            "risk_policy_json": runtime["risk_policy_json"],
            "rank": latest_snapshot["rank"] if latest_snapshot else None,
            "pnl_total": latest_snapshot["pnl_total"] if latest_snapshot else 0.0,
            "pnl_unrealized": latest_snapshot["pnl_unrealized"] if latest_snapshot else 0.0,
            "win_streak": latest_snapshot["win_streak"] if latest_snapshot else 0,
            "drawdown": latest_snapshot["drawdown"] if latest_snapshot else 0.0,
            "recent_events": [{"id": event["id"], "event_type": event["event_type"], "decision_summary": event["decision_summary"], "status": event["status"], "created_at": event["created_at"]} for event in recent_events],
        }

    async def preview_mirror(self, db: Any, *, runtime_id: str, follower_wallet_address: str, scale_bps: int) -> dict:
        del db
        self._validate_scale_bps(scale_bps)
        runtime = self.supabase.maybe_one("bot_runtimes", filters={"id": runtime_id})
        if runtime is None:
            raise ValueError("Source runtime not found")
        source_definition = self.supabase.maybe_one("bot_definitions", filters={"id": runtime["bot_definition_id"]})
        if source_definition is None or source_definition["visibility"] != "public":
            raise ValueError("Source bot is not available for mirroring")
        if runtime["wallet_address"] == follower_wallet_address:
            raise ValueError("You cannot mirror your own runtime")
        performance = await self.performance_service.calculate_runtime_performance(runtime)
        mirrored_positions: list[dict] = []
        total_notional = 0.0
        for position in performance["positions"]:
            mirrored_size = round(float(position.get("amount", 0) or 0) * (scale_bps / 10_000), 4)
            mark_price = float(position.get("mark_price", 0) or 0)
            notional = round(mirrored_size * mark_price, 2)
            total_notional += notional
            mirrored_positions.append({"symbol": str(position.get("symbol") or ""), "side": str(position.get("side") or ""), "size_source": float(position.get("amount", 0) or 0), "size_mirrored": mirrored_size, "mark_price": mark_price, "notional_estimate": notional})
        return {"source_runtime_id": runtime["id"], "source_bot_definition_id": source_definition["id"], "source_bot_name": source_definition["name"], "source_wallet_address": runtime["wallet_address"], "follower_wallet_address": follower_wallet_address, "mode": "mirror", "scale_bps": scale_bps, "warnings": self._build_mirror_warnings(total_notional=total_notional, position_count=len(mirrored_positions)), "mirrored_positions": mirrored_positions}

    async def activate_mirror(self, db: Any, *, runtime_id: str, follower_wallet_address: str, follower_display_name: str | None, scale_bps: int, risk_ack_version: str) -> dict:
        del db
        self.auth_service.require_active_authorization(None, follower_wallet_address)
        preview = await self.preview_mirror(None, runtime_id=runtime_id, follower_wallet_address=follower_wallet_address, scale_bps=scale_bps)
        follower = self._find_or_create_follower(wallet_address=follower_wallet_address, display_name=follower_display_name)
        active = self.supabase.select("bot_copy_relationships", filters={"follower_user_id": follower["id"], "status": "active"})
        now = datetime.now(tz=UTC).isoformat()
        for relationship in active:
            if relationship["source_runtime_id"] != runtime_id:
                self.supabase.update("bot_copy_relationships", {"status": "stopped", "updated_at": now}, filters={"id": relationship["id"]})
        relationship = self.supabase.maybe_one("bot_copy_relationships", filters={"follower_user_id": follower["id"], "source_runtime_id": runtime_id})
        if relationship is None:
            relationship = self.supabase.insert("bot_copy_relationships", {"id": str(uuid.uuid4()), "source_runtime_id": runtime_id, "follower_user_id": follower["id"], "follower_wallet_address": follower_wallet_address, "mode": "mirror", "scale_bps": scale_bps, "status": "active", "risk_ack_version": risk_ack_version, "confirmed_at": now, "updated_at": now})[0]
        else:
            relationship = self.supabase.update("bot_copy_relationships", {"mode": "mirror", "scale_bps": scale_bps, "status": "active", "risk_ack_version": risk_ack_version, "confirmed_at": now, "updated_at": now}, filters={"id": relationship["id"]})[0]
        self.supabase.insert("audit_events", {"id": str(uuid.uuid4()), "user_id": follower["id"], "action": "bot_copy.mirror.activated", "payload": {"relationship_id": relationship["id"], "source_runtime_id": runtime_id, "scale_bps": scale_bps}, "created_at": now})
        await broadcaster.publish(channel=f"user:{follower['id']}", event="bot.copy.updated", payload={"relationship_id": relationship["id"], "status": relationship["status"], "source_runtime_id": relationship["source_runtime_id"], "scale_bps": relationship["scale_bps"], "preview": preview})
        return self.serialize_relationship(None, relationship)

    def create_clone(self, db: Any, *, runtime_id: str, wallet_address: str, name: str | None, description: str | None, visibility: str) -> dict:
        del db
        runtime = self.supabase.maybe_one("bot_runtimes", filters={"id": runtime_id})
        if runtime is None:
            raise ValueError("Source runtime not found")
        source_definition = self.supabase.maybe_one("bot_definitions", filters={"id": runtime["bot_definition_id"]})
        if source_definition is None:
            raise ValueError("Source bot definition not found")
        if source_definition["visibility"] not in {"public", "unlisted"}:
            raise ValueError("Source bot is not cloneable")
        clone_name = (name or f"{source_definition['name']} Clone").strip()
        clone_description = (description or source_definition["description"] or "Cloned bot draft").strip()
        cloned = self.builder_service.create_bot(None, wallet_address=wallet_address, name=clone_name, description=clone_description, visibility=visibility, market_scope=source_definition["market_scope"], strategy_type=source_definition["strategy_type"], authoring_mode=source_definition["authoring_mode"], rules_version=source_definition["rules_version"], rules_json=source_definition["rules_json"])
        follower = self.supabase.maybe_one("users", filters={"wallet_address": wallet_address})
        if follower is None:
            raise ValueError("Follower user not found")
        clone_record = self.supabase.insert("bot_clones", {"id": str(uuid.uuid4()), "source_bot_definition_id": source_definition["id"], "new_bot_definition_id": cloned["id"], "created_by_user_id": follower["id"], "created_at": datetime.now(tz=UTC).isoformat()})[0]
        self.supabase.insert("audit_events", {"id": str(uuid.uuid4()), "user_id": follower["id"], "action": "bot_copy.clone.created", "payload": {"runtime_id": runtime_id, "source_bot_definition_id": source_definition["id"], "new_bot_definition_id": cloned["id"]}, "created_at": datetime.now(tz=UTC).isoformat()})
        return {"clone_id": clone_record["id"], "source_runtime_id": runtime_id, "source_bot_definition_id": source_definition["id"], "new_bot_definition_id": cloned["id"], "created_by_user_id": follower["id"], "created_at": clone_record["created_at"]}

    def list_relationships(self, db: Any, *, follower_wallet_address: str) -> list[dict]:
        del db
        rows = self.supabase.select("bot_copy_relationships", filters={"follower_wallet_address": follower_wallet_address}, order="updated_at.desc")
        return [self.serialize_relationship(None, row) for row in rows]

    def list_clones(self, db: Any, *, wallet_address: str) -> list[dict]:
        del db
        follower = self.supabase.maybe_one("users", filters={"wallet_address": wallet_address})
        if follower is None:
            return []
        rows = self.supabase.select("bot_clones", filters={"created_by_user_id": follower["id"]}, order="created_at.desc")
        definition_ids = [* [row["source_bot_definition_id"] for row in rows], * [row["new_bot_definition_id"] for row in rows]]
        definitions = {row["id"]: row for row in self.supabase.select("bot_definitions", filters={"id": ("in", definition_ids)})} if definition_ids else {}
        return [{"clone_id": row["id"], "source_bot_definition_id": row["source_bot_definition_id"], "source_bot_name": definitions.get(row["source_bot_definition_id"], {}).get("name", "Unknown"), "new_bot_definition_id": row["new_bot_definition_id"], "new_bot_name": definitions.get(row["new_bot_definition_id"], {}).get("name", "Unknown"), "created_at": row["created_at"]} for row in rows]

    async def update_relationship(self, db: Any, *, relationship_id: str, scale_bps: int | None, status: str | None) -> dict:
        del db
        relationship = self.supabase.maybe_one("bot_copy_relationships", filters={"id": relationship_id})
        if relationship is None:
            raise ValueError("Bot copy relationship not found")
        values: dict[str, object] = {"updated_at": datetime.now(tz=UTC).isoformat()}
        if scale_bps is not None:
            self._validate_scale_bps(scale_bps)
            values["scale_bps"] = scale_bps
        if status is not None:
            values["status"] = status
        relationship = self.supabase.update("bot_copy_relationships", values, filters={"id": relationship_id})[0]
        self.supabase.insert("audit_events", {"id": str(uuid.uuid4()), "user_id": relationship["follower_user_id"], "action": "bot_copy.mirror.updated", "payload": {"relationship_id": relationship["id"], "scale_bps": relationship["scale_bps"], "status": relationship["status"]}, "created_at": datetime.now(tz=UTC).isoformat()})
        await broadcaster.publish(channel=f"user:{relationship['follower_user_id']}", event="bot.copy.updated", payload={"relationship_id": relationship["id"], "status": relationship["status"], "scale_bps": relationship["scale_bps"]})
        return self.serialize_relationship(None, relationship)

    async def stop_relationship(self, db: Any, *, relationship_id: str) -> dict:
        return await self.update_relationship(db, relationship_id=relationship_id, scale_bps=None, status="stopped")

    def serialize_relationship(self, db: Any, relationship: dict[str, Any]) -> dict:
        del db
        source_runtime = self.supabase.maybe_one("bot_runtimes", filters={"id": relationship["source_runtime_id"]})
        source_definition = self.supabase.maybe_one("bot_definitions", filters={"id": source_runtime["bot_definition_id"]}) if source_runtime else None
        follower = self.supabase.maybe_one("users", filters={"id": relationship["follower_user_id"]})
        return {
            "id": relationship["id"],
            "source_runtime_id": relationship["source_runtime_id"],
            "source_bot_definition_id": source_definition["id"] if source_definition else "",
            "source_bot_name": source_definition["name"] if source_definition else "Unknown",
            "follower_user_id": relationship["follower_user_id"],
            "follower_wallet_address": relationship["follower_wallet_address"],
            "mode": relationship["mode"],
            "scale_bps": relationship["scale_bps"],
            "status": relationship["status"],
            "risk_ack_version": relationship["risk_ack_version"],
            "confirmed_at": relationship["confirmed_at"],
            "updated_at": relationship["updated_at"],
            "follower_display_name": follower.get("display_name") if follower else None,
        }

    @staticmethod
    def _validate_scale_bps(scale_bps: int) -> None:
        if scale_bps < 500 or scale_bps > 30_000:
            raise ValueError("scale_bps must be between 500 and 30000")

    @staticmethod
    def _build_mirror_warnings(*, total_notional: float, position_count: int) -> list[str]:
        warnings = ["Mirroring executes live orders on your delegated wallet.", "Slippage, fees, and liquidations can deviate from source runtime performance."]
        if total_notional > 0:
            warnings.append(f"Estimated mirrored notional from current positions: ${total_notional:,.2f}.")
        if position_count == 0:
            warnings.append("Source runtime currently has no open positions to mirror.")
        return warnings

    def _find_or_create_follower(self, *, wallet_address: str, display_name: str | None) -> dict[str, Any]:
        follower = self.supabase.maybe_one("users", filters={"wallet_address": wallet_address})
        if follower is None:
            return self.supabase.insert("users", {"id": str(uuid.uuid4()), "wallet_address": wallet_address, "display_name": (display_name or wallet_address[:8]).strip(), "auth_provider": "privy", "created_at": datetime.now(tz=UTC).isoformat()}, upsert=True, on_conflict="wallet_address")[0]
        if display_name:
            return self.supabase.update("users", {"display_name": display_name.strip()}, filters={"id": follower["id"]})[0]
        return follower

    @staticmethod
    def _snapshot_is_stale(value: Any) -> bool:
        if not value:
            return True
        if isinstance(value, datetime):
            captured_at = value
        else:
            captured_at = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if captured_at.tzinfo is None:
            captured_at = captured_at.replace(tzinfo=UTC)
        return datetime.now(tz=UTC) - captured_at > timedelta(seconds=SNAPSHOT_TTL_SECONDS)
