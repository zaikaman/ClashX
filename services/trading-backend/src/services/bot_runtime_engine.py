from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from typing import Any

import anyio

from src.services.bot_risk_service import BotRiskService
from src.services.event_broadcaster import broadcaster
from src.services.pacifica_auth_service import PacificaAuthService
from src.services.pacifica_readiness_service import PacificaReadinessService
from src.services.supabase_rest import SupabaseRestClient


class BotRuntimeEngine:
    def __init__(self) -> None:
        self._supabase = SupabaseRestClient()
        self._auth = PacificaAuthService()
        self._readiness = PacificaReadinessService()
        self._risk = BotRiskService()

    def deploy_runtime(
        self,
        db: Any,
        *,
        bot_id: str,
        wallet_address: str,
        user_id: str,
        risk_policy_json: dict[str, Any] | None,
    ) -> dict[str, Any]:
        del db
        bot = self._resolve_bot(bot_id=bot_id, wallet_address=wallet_address, user_id=user_id)
        runtime = self._resolve_runtime(bot_definition_id=bot["id"], wallet_address=wallet_address)
        self._require_runtime_readiness(wallet_address)

        now = datetime.now(tz=UTC).isoformat()
        normalized_policy = self._risk.normalize_policy(risk_policy_json)
        if runtime is None:
            runtime = self._supabase.insert(
                "bot_runtimes",
                {
                    "id": str(uuid.uuid4()),
                    "bot_definition_id": bot["id"],
                    "user_id": bot["user_id"],
                    "wallet_address": wallet_address,
                    "status": "active",
                    "mode": "live",
                    "risk_policy_json": normalized_policy,
                    "deployed_at": now,
                    "stopped_at": None,
                    "updated_at": now,
                },
            )[0]
        else:
            merged_policy = dict(runtime.get("risk_policy_json") or {})
            if isinstance(risk_policy_json, dict):
                merged_policy.update(risk_policy_json)
            runtime = self._supabase.update(
                "bot_runtimes",
                {
                    "status": "active",
                    "mode": "live",
                    "risk_policy_json": self._risk.normalize_policy(merged_policy),
                    "deployed_at": runtime.get("deployed_at") or now,
                    "stopped_at": None,
                    "updated_at": now,
                },
                filters={"id": runtime["id"]},
            )[0]

        self._supabase.insert(
            "bot_execution_events",
            {
                "id": str(uuid.uuid4()),
                "runtime_id": runtime["id"],
                "event_type": "runtime.deployed",
                "decision_summary": "runtime transitioned to active",
                "request_payload": {"bot_id": bot["id"]},
                "result_payload": {"status": runtime["status"]},
                "status": "success",
                "created_at": now,
            },
        )
        self._publish_event(user_id=runtime["user_id"], event="bot.runtime.deployed", payload=self.serialize_runtime(runtime))
        return self.serialize_runtime(runtime)

    def pause_runtime(self, db: Any, *, bot_id: str, wallet_address: str, user_id: str) -> dict[str, Any]:
        del db
        runtime = self._require_runtime(bot_id=bot_id, wallet_address=wallet_address, user_id=user_id)
        if runtime["status"] == "stopped":
            raise ValueError("Stopped runtime cannot be paused")
        now = datetime.now(tz=UTC).isoformat()
        runtime = self._supabase.update("bot_runtimes", {"status": "paused", "updated_at": now}, filters={"id": runtime["id"]})[0]
        self._append_runtime_transition(runtime=runtime, event_type="runtime.paused")
        self._publish_event(user_id=runtime["user_id"], event="bot.runtime.paused", payload=self.serialize_runtime(runtime))
        return self.serialize_runtime(runtime)

    def resume_runtime(self, db: Any, *, bot_id: str, wallet_address: str, user_id: str) -> dict[str, Any]:
        del db
        runtime = self._require_runtime(bot_id=bot_id, wallet_address=wallet_address, user_id=user_id)
        if runtime["status"] == "stopped":
            raise ValueError("Stopped runtime cannot be resumed")
        if self._auth.get_trading_credentials(None, wallet_address) is None:
            raise ValueError("Authorize a delegated Pacifica agent wallet before resuming this bot.")
        now = datetime.now(tz=UTC).isoformat()
        runtime = self._supabase.update("bot_runtimes", {"status": "active", "updated_at": now}, filters={"id": runtime["id"]})[0]
        self._append_runtime_transition(runtime=runtime, event_type="runtime.resumed")
        self._publish_event(user_id=runtime["user_id"], event="bot.runtime.resumed", payload=self.serialize_runtime(runtime))
        return self.serialize_runtime(runtime)

    def stop_runtime(self, db: Any, *, bot_id: str, wallet_address: str, user_id: str) -> dict[str, Any]:
        del db
        runtime = self._require_runtime(bot_id=bot_id, wallet_address=wallet_address, user_id=user_id)
        now = datetime.now(tz=UTC).isoformat()
        runtime = self._supabase.update(
            "bot_runtimes",
            {"status": "stopped", "stopped_at": now, "updated_at": now},
            filters={"id": runtime["id"]},
        )[0]
        self._append_runtime_transition(runtime=runtime, event_type="runtime.stopped")
        self._publish_event(user_id=runtime["user_id"], event="bot.runtime.stopped", payload=self.serialize_runtime(runtime))
        return self.serialize_runtime(runtime)

    def list_runtime_events(self, db: Any, *, bot_id: str, wallet_address: str, user_id: str, limit: int) -> list[dict[str, Any]]:
        del db
        bot = self._resolve_bot(bot_id=bot_id, wallet_address=wallet_address, user_id=user_id)
        runtime = self._resolve_runtime(bot_definition_id=bot["id"], wallet_address=wallet_address)
        if runtime is None:
            return []
        rows = self._supabase.select("bot_execution_events", filters={"runtime_id": runtime["id"]}, order="created_at.desc", limit=limit)
        return [self.serialize_event(row) for row in rows]

    def list_runtimes_for_wallet(self, db: Any, *, wallet_address: str, user_id: str) -> list[dict[str, Any]]:
        del db, user_id
        rows = self._supabase.select(
            "bot_runtimes",
            columns="id,bot_definition_id,user_id,wallet_address,status,mode,risk_policy_json,deployed_at,stopped_at,updated_at",
            filters={"wallet_address": wallet_address},
            order="updated_at.desc",
        )
        return [self.serialize_runtime(row) for row in rows]

    def get_runtime(self, db: Any, *, bot_id: str, wallet_address: str, user_id: str) -> dict[str, Any] | None:
        del db
        bot = self._resolve_bot(bot_id=bot_id, wallet_address=wallet_address, user_id=user_id)
        runtime = self._resolve_runtime(bot_definition_id=bot["id"], wallet_address=wallet_address)
        return self.serialize_runtime(runtime) if runtime is not None else None

    def get_active_runtimes(self, db: Any) -> list[dict[str, Any]]:
        del db
        return self._supabase.select("bot_runtimes", filters={"status": "active"})

    def append_execution_event(
        self,
        db: Any,
        *,
        runtime: dict[str, Any],
        event_type: str,
        decision_summary: str,
        request_payload: dict[str, Any],
        result_payload: dict[str, Any],
        status: str,
        error_reason: str | None = None,
    ) -> dict[str, Any]:
        del db
        return self._supabase.insert(
            "bot_execution_events",
            {
                "id": str(uuid.uuid4()),
                "runtime_id": runtime["id"],
                "event_type": event_type,
                "decision_summary": decision_summary,
                "request_payload": request_payload,
                "result_payload": result_payload,
                "status": status,
                "error_reason": error_reason,
                "created_at": datetime.now(tz=UTC).isoformat(),
            },
        )[0]

    @staticmethod
    def serialize_runtime(runtime: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": runtime["id"],
            "bot_definition_id": runtime["bot_definition_id"],
            "user_id": runtime["user_id"],
            "wallet_address": runtime["wallet_address"],
            "status": runtime["status"],
            "mode": runtime["mode"],
            "risk_policy_json": runtime["risk_policy_json"],
            "deployed_at": runtime.get("deployed_at"),
            "stopped_at": runtime.get("stopped_at"),
            "updated_at": runtime["updated_at"],
        }

    @staticmethod
    def serialize_event(event: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": event["id"],
            "runtime_id": event["runtime_id"],
            "event_type": event["event_type"],
            "decision_summary": event["decision_summary"],
            "request_payload": event["request_payload"],
            "result_payload": event["result_payload"],
            "status": event["status"],
            "error_reason": event.get("error_reason"),
            "created_at": event["created_at"],
        }

    def _require_runtime(self, *, bot_id: str, wallet_address: str, user_id: str) -> dict[str, Any]:
        bot = self._resolve_bot(bot_id=bot_id, wallet_address=wallet_address, user_id=user_id)
        runtime = self._resolve_runtime(bot_definition_id=bot["id"], wallet_address=wallet_address)
        if runtime is None:
            raise ValueError("Bot runtime not found")
        return runtime

    def _resolve_bot(self, *, bot_id: str, wallet_address: str, user_id: str) -> dict[str, Any]:
        del user_id
        bot = self._supabase.maybe_one("bot_definitions", filters={"id": bot_id, "wallet_address": wallet_address})
        if bot is None:
            raise ValueError("Bot not found")
        return bot

    def _resolve_runtime(self, *, bot_definition_id: str, wallet_address: str) -> dict[str, Any] | None:
        return self._supabase.maybe_one("bot_runtimes", filters={"bot_definition_id": bot_definition_id, "wallet_address": wallet_address})

    def _append_runtime_transition(self, *, runtime: dict[str, Any], event_type: str) -> None:
        self._supabase.insert(
            "bot_execution_events",
            {
                "id": str(uuid.uuid4()),
                "runtime_id": runtime["id"],
                "event_type": event_type,
                "decision_summary": f"runtime transitioned to {runtime['status']}",
                "request_payload": {},
                "result_payload": {"status": runtime["status"]},
                "status": "success",
                "created_at": datetime.now(tz=UTC).isoformat(),
            },
        )

    def _require_runtime_readiness(self, wallet_address: str) -> dict[str, Any]:
        try:
            return anyio.from_thread.run(self._readiness.require_ready, None, wallet_address)
        except RuntimeError:
            # Fall back for direct synchronous calls outside FastAPI's worker thread bridge.
            return asyncio.run(self._readiness.require_ready(None, wallet_address))

    @staticmethod
    def _publish_event(*, user_id: str, event: str, payload: dict[str, Any]) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        loop.create_task(broadcaster.publish(channel=f"user:{user_id}", event=event, payload=payload))
