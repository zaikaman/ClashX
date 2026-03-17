from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from src.services.supabase_rest import SupabaseRestClient


class RuntimeHealthService:
    def __init__(self) -> None:
        self._supabase = SupabaseRestClient()

    def get_health(self, db: Any, *, bot_id: str, wallet_address: str, user_id: str) -> dict[str, Any]:
        del db, user_id
        definition = self._supabase.maybe_one("bot_definitions", filters={"id": bot_id, "wallet_address": wallet_address})
        if definition is None:
            raise ValueError("Bot not found")
        runtime = self._supabase.maybe_one("bot_runtimes", filters={"bot_definition_id": definition["id"], "wallet_address": wallet_address})
        if runtime is None:
            return {
                "runtime_id": None,
                "health": "not_deployed",
                "status": "draft",
                "mode": "live",
                "last_runtime_update": None,
                "last_event_at": None,
                "heartbeat_age_seconds": None,
                "error_rate_recent": 0.0,
                "reasons": ["Runtime has not been deployed yet"],
            }

        recent_events = self._supabase.select("bot_execution_events", filters={"runtime_id": runtime["id"]}, order="created_at.desc", limit=50)
        latest_event = recent_events[0] if recent_events else None
        runtime_updated_at = self._as_datetime(runtime["updated_at"])
        latest_event_at = self._as_datetime(latest_event["created_at"]) if latest_event else None
        now = datetime.now(tz=UTC)
        heartbeat_reference = max(filter(None, [runtime_updated_at, latest_event_at]))
        heartbeat_age_seconds = max(0, int((now - heartbeat_reference).total_seconds()))
        recent_errors = len([event for event in recent_events if event.get("status") == "error"])
        error_rate_recent = round(recent_errors / len(recent_events), 4) if recent_events else 0.0

        health = "healthy"
        reasons: list[str] = []
        runtime_status = runtime["status"]
        if runtime_status in {"stopped", "failed"}:
            health = runtime_status
            reasons.append(f"Runtime status is {runtime_status}")
        else:
            if heartbeat_age_seconds > 600:
                health = "offline"
                reasons.append("No runtime heartbeat for over 10 minutes")
            elif heartbeat_age_seconds > 150:
                health = "stale"
                reasons.append("Runtime heartbeat is stale")
            if error_rate_recent >= 0.35 and health not in {"offline", "stale"}:
                health = "degraded"
                reasons.append("High runtime error rate detected")
            elif error_rate_recent >= 0.35:
                reasons.append("High runtime error rate detected")
            if runtime_status == "paused" and health in {"healthy", "degraded"}:
                health = "paused"
                reasons.append("Runtime is paused")
        if not reasons:
            reasons.append("Runtime heartbeat and execution flow are healthy")
        return {
            "runtime_id": runtime["id"],
            "health": health,
            "status": runtime_status,
            "mode": runtime["mode"],
            "last_runtime_update": runtime_updated_at,
            "last_event_at": latest_event_at,
            "heartbeat_age_seconds": heartbeat_age_seconds,
            "error_rate_recent": error_rate_recent,
            "reasons": reasons,
        }

    @staticmethod
    def _as_datetime(value: datetime | str) -> datetime:
        if isinstance(value, datetime):
            return value
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed
