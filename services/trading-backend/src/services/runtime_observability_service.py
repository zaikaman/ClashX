from __future__ import annotations

import uuid
from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from src.core.settings import get_settings
from src.models.audit_event import AuditEvent
from src.models.bot_definition import BotDefinition
from src.models.bot_execution_event import BotExecutionEvent
from src.models.bot_runtime import BotRuntime
from src.services.supabase_rest import SupabaseRestClient


class RuntimeObservabilityService:
    def __init__(self) -> None:
        self._settings = get_settings()
        self._supabase = SupabaseRestClient() if self._settings.use_supabase_api else None

    def get_metrics(
        self,
        db: Session,
        *,
        bot_id: str,
        wallet_address: str,
        user_id: str,
    ) -> dict[str, Any]:
        runtime = self._require_runtime(
            db,
            bot_id=bot_id,
            wallet_address=wallet_address,
            user_id=user_id,
        )

        window_start = datetime.now(tz=UTC) - timedelta(hours=24)
        if self._settings.use_supabase_api:
            assert self._supabase is not None
            events = self._supabase.select(
                "bot_execution_events",
                filters={"runtime_id": runtime["id"]},
                order="created_at.desc",
                limit=500,
            )
            recent_window = [
                event for event in events if self._as_datetime(event["created_at"]) >= window_start
            ]
            runtime_id = runtime["id"]
            runtime_status = runtime["status"]
            runtime_deployed_at = runtime.get("deployed_at")
        else:
            events = list(
                db.scalars(
                    select(BotExecutionEvent)
                    .where(BotExecutionEvent.runtime_id == runtime.id)
                    .order_by(desc(BotExecutionEvent.created_at))
                    .limit(500)
                ).all()
            )
            recent_window = [event for event in events if event.created_at >= window_start]
            runtime_id = runtime.id
            runtime_status = runtime.status
            runtime_deployed_at = runtime.deployed_at

        action_events = [event for event in recent_window if str(self._get_value(event, "event_type")).startswith("action.")]
        actions_total = len(action_events)
        actions_success = len([event for event in action_events if self._get_value(event, "status") == "success"])
        actions_error = len([event for event in action_events if self._get_value(event, "status") == "error"])
        actions_skipped = len([event for event in action_events if self._get_value(event, "status") == "skipped"])

        event_type_counter = Counter(str(self._get_value(event, "event_type")) for event in recent_window)
        status_counter = Counter(str(self._get_value(event, "status")) for event in recent_window)

        failure_reasons = Counter(
            (self._get_value(event, "error_reason") or "unknown")
            for event in recent_window
            if self._get_value(event, "status") == "error"
        )

        recent_failures = [
            {
                "id": self._get_value(event, "id"),
                "event_type": self._get_value(event, "event_type"),
                "error_reason": self._get_value(event, "error_reason") or "unknown",
                "decision_summary": self._get_value(event, "decision_summary"),
                "created_at": self._get_value(event, "created_at"),
            }
            for event in events
            if self._get_value(event, "status") == "error"
        ][:15]

        last_event_at = self._as_datetime(self._get_value(events[0], "created_at")) if events else None
        uptime_seconds = None
        if runtime_deployed_at is not None:
            deployed_at = self._as_datetime(runtime_deployed_at) if isinstance(runtime_deployed_at, str) else runtime_deployed_at
            uptime_seconds = max(0, int((datetime.now(tz=UTC) - deployed_at).total_seconds()))

        success_rate = round(actions_success / actions_total, 4) if actions_total > 0 else 1.0

        return {
            "runtime_id": runtime_id,
            "status": runtime_status,
            "uptime_seconds": uptime_seconds,
            "window_hours": 24,
            "events_total": len(recent_window),
            "actions_total": actions_total,
            "actions_success": actions_success,
            "actions_error": actions_error,
            "actions_skipped": actions_skipped,
            "success_rate": success_rate,
            "status_counts": dict(status_counter),
            "event_type_counts": dict(event_type_counter),
            "failure_reasons": [{"reason": reason, "count": count} for reason, count in failure_reasons.most_common(8)],
            "recent_failures": recent_failures,
            "last_event_at": last_event_at,
        }

    def get_risk_state(
        self,
        db: Session,
        *,
        bot_id: str,
        wallet_address: str,
        user_id: str,
    ) -> dict[str, Any]:
        runtime = self._require_runtime(
            db,
            bot_id=bot_id,
            wallet_address=wallet_address,
            user_id=user_id,
        )
        if isinstance(runtime, dict):
            policy = runtime["risk_policy_json"] if isinstance(runtime.get("risk_policy_json"), dict) else {}
        else:
            policy = runtime.risk_policy_json if isinstance(runtime.risk_policy_json, dict) else {}
        runtime_state = policy.get("_runtime_state") if isinstance(policy.get("_runtime_state"), dict) else {}
        return {
            "runtime_id": self._get_value(runtime, "id"),
            "risk_policy_json": policy,
            "runtime_state": runtime_state,
            "updated_at": self._get_value(runtime, "updated_at"),
        }

    def update_risk_policy(
        self,
        db: Session,
        *,
        bot_id: str,
        wallet_address: str,
        user_id: str,
        risk_policy_json: dict[str, Any],
    ) -> dict[str, Any]:
        runtime = self._require_runtime(
            db,
            bot_id=bot_id,
            wallet_address=wallet_address,
            user_id=user_id,
        )
        existing = runtime["risk_policy_json"] if isinstance(runtime, dict) and isinstance(runtime.get("risk_policy_json"), dict) else runtime.risk_policy_json if isinstance(runtime.risk_policy_json, dict) else {}
        runtime_state = existing.get("_runtime_state") if isinstance(existing.get("_runtime_state"), dict) else {}

        next_policy = {
            **existing,
            **risk_policy_json,
            "_runtime_state": runtime_state,
        }
        updated_at = datetime.now(tz=UTC)

        if self._settings.use_supabase_api:
            assert self._supabase is not None
            runtime = self._supabase.update(
                "bot_runtimes",
                {"risk_policy_json": next_policy, "updated_at": updated_at.isoformat()},
                filters={"id": runtime["id"]},
            )[0]
            self._supabase.insert(
                "audit_events",
                {
                    "id": str(uuid.uuid4()),
                    "user_id": runtime["user_id"],
                    "action": "bot.runtime.risk_policy.updated",
                    "payload": {
                        "runtime_id": runtime["id"],
                        "bot_id": bot_id,
                        "updated_keys": sorted(risk_policy_json.keys()),
                    },
                    "created_at": updated_at.isoformat(),
                },
            )
            policy = runtime["risk_policy_json"] if isinstance(runtime.get("risk_policy_json"), dict) else {}
            runtime_state_next = policy.get("_runtime_state") if isinstance(policy.get("_runtime_state"), dict) else {}
            return {
                "runtime_id": runtime["id"],
                "risk_policy_json": policy,
                "runtime_state": runtime_state_next,
                "updated_at": runtime["updated_at"],
            }

        runtime.risk_policy_json = next_policy
        runtime.updated_at = updated_at

        db.add(
            AuditEvent(
                user_id=user_id,
                action="bot.runtime.risk_policy.updated",
                payload={
                    "runtime_id": runtime.id,
                    "bot_id": bot_id,
                    "updated_keys": sorted(risk_policy_json.keys()),
                },
            )
        )
        db.commit()
        db.refresh(runtime)

        policy = runtime.risk_policy_json if isinstance(runtime.risk_policy_json, dict) else {}
        runtime_state_next = policy.get("_runtime_state") if isinstance(policy.get("_runtime_state"), dict) else {}
        return {
            "runtime_id": runtime.id,
            "risk_policy_json": policy,
            "runtime_state": runtime_state_next,
            "updated_at": runtime.updated_at,
        }

    def _require_runtime(
        self,
        db: Session,
        *,
        bot_id: str,
        wallet_address: str,
        user_id: str,
    ) -> BotRuntime | dict[str, Any]:
        if self._settings.use_supabase_api:
            assert self._supabase is not None
            definition = self._supabase.maybe_one(
                "bot_definitions",
                filters={"id": bot_id, "wallet_address": wallet_address},
            )
            if definition is None:
                raise ValueError("Bot not found")
            runtime = self._supabase.maybe_one(
                "bot_runtimes",
                filters={"bot_definition_id": definition["id"], "wallet_address": wallet_address},
            )
            if runtime is None:
                raise ValueError("Bot runtime not found")
            return runtime

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

        runtime = db.scalar(
            select(BotRuntime)
            .where(
                BotRuntime.bot_definition_id == definition.id,
                BotRuntime.wallet_address == wallet_address,
            )
            .limit(1)
        )
        if runtime is None:
            raise ValueError("Bot runtime not found")
        return runtime

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
