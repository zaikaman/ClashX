from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from src.core.settings import get_settings
from src.models.bot_definition import BotDefinition
from src.models.bot_execution_event import BotExecutionEvent
from src.models.bot_runtime import BotRuntime
from src.services.supabase_rest import SupabaseRestClient


class RuntimeHealthService:
    def __init__(self) -> None:
        self._settings = get_settings()
        self._supabase = SupabaseRestClient() if self._settings.use_supabase_api else None

    def get_health(
        self,
        db: Session,
        *,
        bot_id: str,
        wallet_address: str,
        user_id: str,
    ) -> dict[str, Any]:
        runtime = self._resolve_runtime(
            db,
            bot_id=bot_id,
            wallet_address=wallet_address,
            user_id=user_id,
        )
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

        if self._settings.use_supabase_api:
            assert self._supabase is not None
            recent_events = self._supabase.select(
                "bot_execution_events",
                filters={"runtime_id": runtime["id"]},
                order="created_at.desc",
                limit=50,
            )
            latest_event = recent_events[0] if recent_events else None
            runtime_updated_at = self._as_datetime(runtime["updated_at"])
            latest_event_at = self._as_datetime(latest_event["created_at"]) if latest_event else None
        else:
            latest_event = db.scalar(
                select(BotExecutionEvent)
                .where(BotExecutionEvent.runtime_id == runtime.id)
                .order_by(desc(BotExecutionEvent.created_at))
                .limit(1)
            )
            recent_events = list(
                db.scalars(
                    select(BotExecutionEvent)
                    .where(BotExecutionEvent.runtime_id == runtime.id)
                    .order_by(desc(BotExecutionEvent.created_at))
                    .limit(50)
                ).all()
            )
            runtime_updated_at = runtime.updated_at
            latest_event_at = latest_event.created_at if latest_event else None

        now = datetime.now(tz=UTC)
        heartbeat_reference = runtime_updated_at
        if latest_event_at and latest_event_at > heartbeat_reference:
            heartbeat_reference = latest_event_at

        heartbeat_age_seconds = max(0, int((now - heartbeat_reference).total_seconds()))
        recent_errors = len([event for event in recent_events if self._get_value(event, "status") == "error"])
        error_rate_recent = round(recent_errors / len(recent_events), 4) if recent_events else 0.0

        health = "healthy"
        reasons: list[str] = []

        runtime_status = self._get_value(runtime, "status")
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
            "runtime_id": self._get_value(runtime, "id"),
            "health": health,
            "status": runtime_status,
            "mode": self._get_value(runtime, "mode"),
            "last_runtime_update": runtime_updated_at,
            "last_event_at": latest_event_at,
            "heartbeat_age_seconds": heartbeat_age_seconds,
            "error_rate_recent": error_rate_recent,
            "reasons": reasons,
        }

    def _resolve_runtime(
        self,
        db: Session,
        *,
        bot_id: str,
        wallet_address: str,
        user_id: str,
    ) -> BotRuntime | dict[str, Any] | None:
        if self._settings.use_supabase_api:
            assert self._supabase is not None
            definition = self._supabase.maybe_one(
                "bot_definitions",
                filters={"id": bot_id, "wallet_address": wallet_address},
            )
            if definition is None:
                raise ValueError("Bot not found")
            return self._supabase.maybe_one(
                "bot_runtimes",
                filters={"bot_definition_id": definition["id"], "wallet_address": wallet_address},
            )

        definition = db.scalar(
            select(BotDefinition)
            .where(
                BotDefinition.id == bot_id,
                BotDefinition.wallet_address == wallet_address,
                BotDefinition.user_id == user_id,
            )
            .limit(1)
        )
        if definition is None:
            raise ValueError("Bot not found")

        return db.scalar(
            select(BotRuntime)
            .where(
                BotRuntime.bot_definition_id == definition.id,
                BotRuntime.wallet_address == wallet_address,
            )
            .limit(1)
        )

    @staticmethod
    def _get_value(item: BotRuntime | BotExecutionEvent | dict[str, Any], key: str) -> Any:
        if isinstance(item, dict):
            return item.get(key)
        return getattr(item, key)

    @staticmethod
    def _as_datetime(value: datetime | str) -> datetime:
        if isinstance(value, datetime):
            return value
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed
