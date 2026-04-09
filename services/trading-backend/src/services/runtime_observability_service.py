from __future__ import annotations

import uuid
from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import Any

from src.services.bot_risk_service import BotRiskService
from src.services.rules_engine import RulesEngine
from src.services.supabase_rest import SupabaseRestClient


class RuntimeObservabilityService:
    def __init__(self) -> None:
        self._supabase = SupabaseRestClient()
        self._risk = BotRiskService()
        self._rules = RulesEngine()

    def get_overview(self, db: Any, *, bot_id: str, wallet_address: str, user_id: str) -> dict[str, Any]:
        del db, user_id
        runtime = self._resolve_runtime(bot_id=bot_id, wallet_address=wallet_address)
        if runtime is None:
            return self._draft_overview_payload()
        snapshot = self._build_snapshot(runtime)
        return {"health": self._build_health_payload(snapshot), "metrics": self._build_metrics_payload(snapshot)}

    def get_overviews_for_wallet(
        self,
        db: Any,
        *,
        wallet_address: str,
        user_id: str,
    ) -> dict[str, dict[str, Any]]:
        del db, user_id
        definitions = self._supabase.select("bot_definitions", filters={"wallet_address": wallet_address})
        if not definitions:
            return {}

        runtimes = self._supabase.select("bot_runtimes", filters={"wallet_address": wallet_address})
        runtime_by_bot_id = {
            str(runtime.get("bot_definition_id") or "").strip(): runtime
            for runtime in runtimes
            if str(runtime.get("bot_definition_id") or "").strip()
        }
        runtime_ids = [
            str(runtime.get("id") or "").strip()
            for runtime in runtimes
            if str(runtime.get("id") or "").strip()
        ]
        events_by_runtime = self._load_runtime_events_map(runtime_ids)
        now = datetime.now(tz=UTC)

        overviews_by_bot: dict[str, dict[str, Any]] = {}
        for definition in definitions:
            bot_id = str(definition.get("id") or "").strip()
            if not bot_id:
                continue
            runtime = runtime_by_bot_id.get(bot_id)
            if runtime is None:
                overviews_by_bot[bot_id] = self._draft_overview_payload()
                continue
            snapshot = self._build_snapshot(runtime, events=events_by_runtime.get(str(runtime["id"]), []), now=now)
            overviews_by_bot[bot_id] = {
                "health": self._build_health_payload(snapshot),
                "metrics": self._build_metrics_payload(snapshot),
            }
        return overviews_by_bot

    def get_metrics(self, db: Any, *, bot_id: str, wallet_address: str, user_id: str) -> dict[str, Any]:
        del db, user_id
        return self._build_metrics_payload(self._build_snapshot(self._require_runtime(bot_id=bot_id, wallet_address=wallet_address)))

    def get_risk_state(self, db: Any, *, bot_id: str, wallet_address: str, user_id: str) -> dict[str, Any]:
        del db, user_id
        runtime = self._require_runtime(bot_id=bot_id, wallet_address=wallet_address)
        policy = runtime["risk_policy_json"] if isinstance(runtime.get("risk_policy_json"), dict) else {}
        runtime_state = policy.get("_runtime_state") if isinstance(policy.get("_runtime_state"), dict) else {}
        return {
            "runtime_id": runtime["id"],
            "risk_policy_json": policy,
            "runtime_state": runtime_state,
            "updated_at": runtime["updated_at"],
        }

    def update_risk_policy(
        self,
        db: Any,
        *,
        bot_id: str,
        wallet_address: str,
        user_id: str,
        risk_policy_json: dict[str, Any],
    ) -> dict[str, Any]:
        del db
        runtime = self._require_runtime(bot_id=bot_id, wallet_address=wallet_address)
        definition = self._supabase.maybe_one("bot_definitions", filters={"id": bot_id, "wallet_address": wallet_address})
        if definition is None:
            raise ValueError("Bot not found")
        existing = runtime["risk_policy_json"] if isinstance(runtime.get("risk_policy_json"), dict) else {}
        runtime_state = existing.get("_runtime_state") if isinstance(existing.get("_runtime_state"), dict) else {}
        next_policy = self._risk.normalize_policy({**existing, **risk_policy_json, "_runtime_state": runtime_state})
        if str(next_policy.get("sizing_mode") or "fixed_usd") == "risk_adjusted":
            rules_json = definition.get("rules_json") if isinstance(definition.get("rules_json"), dict) else {}
            issues = self._rules.risk_adjusted_sizing_issues(rules_json=rules_json)
            if issues:
                raise ValueError("Risk-adjusted sizing is not available for this bot: " + "; ".join(issues))
        updated_at = datetime.now(tz=UTC).isoformat()
        runtime = self._supabase.update(
            "bot_runtimes",
            {"risk_policy_json": next_policy, "updated_at": updated_at},
            filters={"id": runtime["id"]},
        )[0]
        self._supabase.insert(
            "audit_events",
            {
                "id": str(uuid.uuid4()),
                "user_id": user_id,
                "action": "bot.runtime.risk_policy.updated",
                "payload": {"runtime_id": runtime["id"], "bot_id": bot_id, "updated_keys": sorted(risk_policy_json.keys())},
                "created_at": updated_at,
            },
        )
        policy = runtime["risk_policy_json"] if isinstance(runtime.get("risk_policy_json"), dict) else {}
        runtime_state_next = policy.get("_runtime_state") if isinstance(policy.get("_runtime_state"), dict) else {}
        return {"runtime_id": runtime["id"], "risk_policy_json": policy, "runtime_state": runtime_state_next, "updated_at": runtime["updated_at"]}

    def _require_runtime(self, *, bot_id: str, wallet_address: str) -> dict[str, Any]:
        runtime = self._resolve_runtime(bot_id=bot_id, wallet_address=wallet_address)
        if runtime is None:
            raise ValueError("Bot runtime not found")
        return runtime

    def _resolve_runtime(self, *, bot_id: str, wallet_address: str) -> dict[str, Any] | None:
        definition = self._supabase.maybe_one("bot_definitions", filters={"id": bot_id, "wallet_address": wallet_address})
        if definition is None:
            raise ValueError("Bot not found")
        return self._supabase.maybe_one("bot_runtimes", filters={"bot_definition_id": definition["id"], "wallet_address": wallet_address})

    def _build_snapshot(
        self,
        runtime: dict[str, Any],
        *,
        events: list[dict[str, Any]] | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        resolved_now = now or datetime.now(tz=UTC)
        window_start = resolved_now - timedelta(hours=24)
        resolved_events = events
        if resolved_events is None:
            resolved_events = self._supabase.select(
                "bot_execution_events",
                filters={"runtime_id": runtime["id"]},
                order="created_at.desc",
                limit=500,
            )
        recent_window = [event for event in resolved_events if self._as_datetime(event["created_at"]) >= window_start]
        return {
            "runtime": runtime,
            "events": resolved_events,
            "recent_window": recent_window,
            "runtime_updated_at": self._as_datetime(runtime["updated_at"]),
            "runtime_deployed_at": runtime.get("deployed_at"),
            "now": resolved_now,
        }

    def _draft_overview_payload(self) -> dict[str, Any]:
        return {
            "health": {
                "runtime_id": None,
                "health": "not_deployed",
                "status": "draft",
                "mode": "live",
                "last_runtime_update": None,
                "last_event_at": None,
                "heartbeat_age_seconds": None,
                "error_rate_recent": 0.0,
                "reasons": ["Runtime has not been deployed yet"],
            },
            "metrics": {
                "runtime_id": "",
                "status": "draft",
                "uptime_seconds": None,
                "window_hours": 24,
                "events_total": 0,
                "actions_total": 0,
                "actions_success": 0,
                "actions_error": 0,
                "actions_skipped": 0,
                "success_rate": 1.0,
                "status_counts": {},
                "event_type_counts": {},
                "failure_reasons": [],
                "recent_failures": [],
                "last_event_at": None,
            },
        }

    def _load_runtime_events_map(self, runtime_ids: list[str]) -> dict[str, list[dict[str, Any]]]:
        normalized_runtime_ids = [runtime_id for runtime_id in runtime_ids if runtime_id]
        if not normalized_runtime_ids:
            return {}

        rows = self._supabase.select(
            "bot_execution_events",
            columns="id,runtime_id,event_type,decision_summary,status,error_reason,created_at",
            filters={"runtime_id": ("in", normalized_runtime_ids)},
            order="created_at.desc",
            limit=max(500, len(normalized_runtime_ids) * 500),
        )
        events_by_runtime: dict[str, list[dict[str, Any]]] = {runtime_id: [] for runtime_id in normalized_runtime_ids}
        for row in rows:
            runtime_id = str(row.get("runtime_id") or "").strip()
            if runtime_id not in events_by_runtime or len(events_by_runtime[runtime_id]) >= 500:
                continue
            events_by_runtime[runtime_id].append(row)
        return events_by_runtime

    def _build_metrics_payload(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        runtime = snapshot["runtime"]
        events = snapshot["events"]
        recent_window = snapshot["recent_window"]
        now = snapshot["now"]
        runtime_deployed_at = snapshot["runtime_deployed_at"]
        action_events = [event for event in recent_window if str(event.get("event_type") or "").startswith("action.")]
        actions_total = len(action_events)
        actions_success = len([event for event in action_events if event.get("status") == "success"])
        actions_error = len([event for event in action_events if event.get("status") == "error"])
        actions_skipped = len([event for event in action_events if event.get("status") == "skipped"])
        event_type_counter = Counter(str(event.get("event_type")) for event in recent_window)
        status_counter = Counter(str(event.get("status")) for event in recent_window)
        failure_reasons = Counter((event.get("error_reason") or "unknown") for event in recent_window if event.get("status") == "error")
        recent_failures = [
            {
                "id": event["id"],
                "event_type": event["event_type"],
                "error_reason": event.get("error_reason") or "unknown",
                "decision_summary": event["decision_summary"],
                "created_at": event["created_at"],
            }
            for event in events
            if event.get("status") == "error"
        ][:15]
        last_event_at = self._as_datetime(events[0]["created_at"]) if events else None
        uptime_seconds = None
        if runtime_deployed_at is not None:
            uptime_seconds = max(0, int((now - self._as_datetime(runtime_deployed_at)).total_seconds()))
        success_rate = round(actions_success / actions_total, 4) if actions_total > 0 else 1.0
        return {
            "runtime_id": runtime["id"],
            "status": runtime["status"],
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

    def _build_health_payload(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        runtime = snapshot["runtime"]
        events = snapshot["events"]
        recent_window = snapshot["recent_window"]
        runtime_updated_at = snapshot["runtime_updated_at"]
        now = snapshot["now"]
        latest_event_at = self._as_datetime(events[0]["created_at"]) if events else None
        heartbeat_reference = runtime_updated_at if latest_event_at is None or runtime_updated_at > latest_event_at else latest_event_at
        heartbeat_age_seconds = max(0, int((now - heartbeat_reference).total_seconds()))
        recent_errors = len([event for event in recent_window if event.get("status") == "error"])
        error_rate_recent = round(recent_errors / len(recent_window), 4) if recent_window else 0.0
        health = "healthy"
        reasons: list[str] = []
        runtime_status = str(runtime["status"])
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
