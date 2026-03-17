from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from src.services.copy_risk_service import CopyRiskService
from src.services.event_broadcaster import broadcaster
from src.services.pacifica_auth_service import PacificaAuthService
from src.services.pacifica_client import PacificaClient
from src.services.supabase_rest import SupabaseRestClient


class CopyEngine:
    def __init__(self, pacifica_client: PacificaClient | None = None, risk_service: CopyRiskService | None = None) -> None:
        self.pacifica_client = pacifica_client or PacificaClient()
        self.auth_service = PacificaAuthService()
        self.risk_service = risk_service or CopyRiskService()
        self.supabase = SupabaseRestClient()

    async def preview_copy(self, db: Any, *, source_user_id: str, follower_wallet_address: str, scale_bps: int) -> dict:
        del db
        self.risk_service.validate_scale_bps(scale_bps)
        source_user = self.supabase.maybe_one("users", filters={"id": source_user_id})
        if source_user is None:
            raise ValueError("Source bot operator not found")
        if source_user["wallet_address"] == follower_wallet_address:
            raise ValueError("You cannot copy your own wallet")
        positions = await self.pacifica_client.get_positions(source_user["wallet_address"])
        mirrored_positions: list[dict] = []
        total_notional = 0.0
        for position in positions:
            mirrored_size = round(position["amount"] * (scale_bps / 10_000), 4)
            notional = round(mirrored_size * position["mark_price"], 2)
            total_notional += notional
            mirrored_positions.append({"symbol": position["symbol"], "side": position["side"], "size_source": position["amount"], "size_mirrored": mirrored_size, "mark_price": position["mark_price"], "notional_estimate": notional})
        snapshot = self.supabase.maybe_one("leaderboard_snapshots", filters={"user_id": source_user_id}, order="captured_at.desc")
        summary = self.risk_service.build_summary(source_display_name=source_user.get("display_name") or source_user["wallet_address"][:8], scale_bps=scale_bps, notional_estimate=total_notional, position_count=len(mirrored_positions))
        return {"source_user_id": source_user["id"], "source_display_name": source_user.get("display_name") or source_user["wallet_address"][:8], "source_wallet_address": source_user["wallet_address"], "follower_wallet_address": follower_wallet_address, "scale_bps": scale_bps, "warnings": summary.warnings, "confirmation_phrase": summary.confirmation_phrase, "source_rank": snapshot["rank"] if snapshot else None, "source_win_streak": snapshot["win_streak"] if snapshot else 0, "mirrored_positions": mirrored_positions}

    async def confirm_copy(self, db: Any, *, source_user_id: str, follower_wallet_address: str, follower_display_name: str | None, scale_bps: int, risk_ack_version: str, confirmation_phrase: str) -> dict:
        del db
        self.auth_service.require_active_authorization(None, follower_wallet_address)
        preview = await self.preview_copy(None, source_user_id=source_user_id, follower_wallet_address=follower_wallet_address, scale_bps=scale_bps)
        if confirmation_phrase.strip().upper() != preview["confirmation_phrase"]:
            raise ValueError("Confirmation phrase does not match")
        follower = self.supabase.maybe_one("users", filters={"wallet_address": follower_wallet_address})
        if follower is None:
            follower = self.supabase.insert("users", {"id": str(uuid.uuid4()), "wallet_address": follower_wallet_address, "display_name": follower_display_name or follower_wallet_address[:8], "auth_provider": "privy", "created_at": datetime.now(tz=UTC).isoformat()})[0]
        elif follower_display_name and follower.get("display_name") != follower_display_name:
            follower = self.supabase.update("users", {"display_name": follower_display_name}, filters={"id": follower["id"]})[0]
        active = self.supabase.select("copy_relationships", filters={"follower_user_id": follower["id"], "status": "active"})
        now = datetime.now(tz=UTC).isoformat()
        for relationship in active:
            if relationship["source_user_id"] != source_user_id:
                self.supabase.update("copy_relationships", {"status": "stopped", "updated_at": now}, filters={"id": relationship["id"]})
        relationship = self.supabase.maybe_one("copy_relationships", filters={"follower_user_id": follower["id"], "source_user_id": source_user_id})
        if relationship is None:
            relationship = self.supabase.insert("copy_relationships", {"id": str(uuid.uuid4()), "follower_user_id": follower["id"], "source_user_id": source_user_id, "scale_bps": scale_bps, "status": "active", "risk_ack_version": risk_ack_version, "confirmed_at": now, "updated_at": now})[0]
        else:
            relationship = self.supabase.update("copy_relationships", {"scale_bps": scale_bps, "status": "active", "risk_ack_version": risk_ack_version, "confirmed_at": now, "updated_at": now}, filters={"id": relationship["id"]})[0]
        self.supabase.insert("audit_events", {"id": str(uuid.uuid4()), "user_id": follower["id"], "action": "copy.confirmed", "payload": {"source_user_id": source_user_id, "scale_bps": scale_bps, "risk_ack_version": risk_ack_version}, "created_at": now})
        await broadcaster.publish(channel=f"user:{follower['id']}", event="copy.relationship.updated", payload={"relationship_id": relationship["id"], "status": relationship["status"], "source_user_id": source_user_id, "scale_bps": scale_bps, "events": []})
        return self.serialize_relationship(None, relationship)

    def list_relationships(self, db: Any, wallet_address: str) -> list[dict]:
        del db
        follower = self.supabase.maybe_one("users", filters={"wallet_address": wallet_address})
        if follower is None:
            return []
        relationships = self.supabase.select("copy_relationships", filters={"follower_user_id": follower["id"]}, order="updated_at.desc")
        return [self.serialize_relationship(None, relationship) for relationship in relationships]

    async def update_relationship(self, db: Any, *, relationship_id: str, scale_bps: int | None = None, status: str | None = None) -> dict:
        del db
        relationship = self.supabase.maybe_one("copy_relationships", filters={"id": relationship_id})
        if relationship is None:
            raise ValueError("Copy relationship not found")
        values: dict[str, object] = {"updated_at": datetime.now(tz=UTC).isoformat()}
        if scale_bps is not None:
            self.risk_service.validate_scale_bps(scale_bps)
            values["scale_bps"] = scale_bps
        if status is not None:
            values["status"] = status
        relationship = self.supabase.update("copy_relationships", values, filters={"id": relationship_id})[0]
        self.supabase.insert("audit_events", {"id": str(uuid.uuid4()), "user_id": relationship["follower_user_id"], "action": "copy.updated", "payload": {"relationship_id": relationship["id"], "scale_bps": relationship["scale_bps"], "status": relationship["status"]}, "created_at": datetime.now(tz=UTC).isoformat()})
        await broadcaster.publish(channel=f"user:{relationship['follower_user_id']}", event="copy.relationship.updated", payload={"relationship_id": relationship["id"], "status": relationship["status"], "scale_bps": relationship["scale_bps"]})
        return self.serialize_relationship(None, relationship)

    async def stop_relationship(self, db: Any, relationship_id: str) -> dict:
        return await self.update_relationship(db, relationship_id=relationship_id, status="stopped")

    def serialize_relationship(self, db: Any, relationship: dict[str, Any]) -> dict:
        del db
        follower = self.supabase.maybe_one("users", filters={"id": relationship["follower_user_id"]})
        source = self.supabase.maybe_one("users", filters={"id": relationship["source_user_id"]})
        events = self.supabase.select("copy_execution_events", filters={"copy_relationship_id": relationship["id"]}, order="created_at.desc", limit=8)
        return {
            "id": relationship["id"],
            "follower_user_id": relationship["follower_user_id"],
            "follower_wallet_address": follower["wallet_address"] if follower else "",
            "source_user_id": relationship["source_user_id"],
            "source_display_name": source.get("display_name") if source else "Unknown",
            "source_wallet_address": source.get("wallet_address") if source else "",
            "scale_bps": relationship["scale_bps"],
            "status": relationship["status"],
            "risk_ack_version": relationship["risk_ack_version"],
            "confirmed_at": relationship["confirmed_at"],
            "updated_at": relationship["updated_at"],
            "events": [{"id": event["id"], "symbol": event["symbol"], "side": event["side"], "size_source": float(event["size_source"]), "size_mirrored": float(event["size_mirrored"]), "status": event["status"], "error_reason": event.get("error_reason"), "created_at": event["created_at"]} for event in events],
        }
