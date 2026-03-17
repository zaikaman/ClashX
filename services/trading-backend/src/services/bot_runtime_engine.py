from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from src.core.settings import get_settings
from src.models.bot_definition import BotDefinition
from src.models.bot_execution_event import BotExecutionEvent
from src.models.bot_runtime import BotRuntime
from src.services.bot_risk_service import BotRiskService
from src.services.event_broadcaster import broadcaster
from src.services.pacifica_auth_service import PacificaAuthService
from src.services.pacifica_readiness_service import PacificaReadinessService
from src.services.supabase_rest import SupabaseRestClient


class BotRuntimeEngine:
    def __init__(self) -> None:
        self._settings = get_settings()
        self._supabase = SupabaseRestClient() if self._settings.use_supabase_api else None
        self._auth = PacificaAuthService()
        self._readiness = PacificaReadinessService()
        self._risk = BotRiskService()

    def deploy_runtime(
        self,
        db: Session,
        *,
        bot_id: str,
        wallet_address: str,
        user_id: str,
        risk_policy_json: dict[str, Any] | None,
    ) -> dict[str, Any]:
        bot = self._resolve_bot(db, bot_id=bot_id, wallet_address=wallet_address, user_id=user_id)
        runtime = self._resolve_runtime(
            db,
            bot_definition_id=bot["id"] if isinstance(bot, dict) else bot.id,
            wallet_address=wallet_address,
        )
        asyncio.run(self._readiness.require_ready(db, wallet_address))

        now = datetime.now(tz=UTC)
        normalized_policy = self._risk.normalize_policy(risk_policy_json)
        bot_id_value = bot["id"] if isinstance(bot, dict) else bot.id
        bot_user_id = bot["user_id"] if isinstance(bot, dict) else bot.user_id
        now_value = now.isoformat() if self._settings.use_supabase_api else now

        if self._settings.use_supabase_api:
            assert self._supabase is not None
            if runtime is None:
                runtime_payload = {
                    "id": str(uuid.uuid4()),
                    "bot_definition_id": bot_id_value,
                    "user_id": bot_user_id,
                    "wallet_address": wallet_address,
                    "status": "active",
                    "mode": "live",
                    "risk_policy_json": normalized_policy,
                    "deployed_at": now_value,
                    "stopped_at": None,
                    "updated_at": now_value,
                }
                runtime = self._supabase.insert("bot_runtimes", runtime_payload)[0]
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
                        "deployed_at": runtime.get("deployed_at") or now_value,
                        "stopped_at": None,
                        "updated_at": now_value,
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
                    "request_payload": {"bot_id": bot_id_value},
                    "result_payload": {"status": runtime["status"]},
                    "status": "success",
                    "created_at": now_value,
                },
            )
            self._publish_event(user_id=runtime["user_id"], event="bot.runtime.deployed", payload=self.serialize_runtime(runtime))
            return self.serialize_runtime(runtime)

        if runtime is None:
            runtime = BotRuntime(
                bot_definition_id=bot_id_value,
                user_id=bot_user_id,
                wallet_address=wallet_address,
                status="active",
                mode="live",
                risk_policy_json=normalized_policy,
                deployed_at=now,
                stopped_at=None,
                updated_at=now,
            )
            db.add(runtime)
            db.flush()
        else:
            merged_policy = dict(runtime.risk_policy_json or {})
            if isinstance(risk_policy_json, dict):
                merged_policy.update(risk_policy_json)
            runtime.status = "active"
            runtime.mode = "live"
            runtime.risk_policy_json = self._risk.normalize_policy(merged_policy)
            runtime.deployed_at = runtime.deployed_at or now
            runtime.stopped_at = None
            runtime.updated_at = now

        event = BotExecutionEvent(
            runtime_id=runtime.id,
            event_type="runtime.deployed",
            decision_summary="runtime transitioned to active",
            request_payload={"bot_id": bot.id},
            result_payload={"status": runtime.status},
            status="success",
        )
        db.add(event)
        db.commit()
        db.refresh(runtime)
        self._publish_event(user_id=runtime.user_id, event="bot.runtime.deployed", payload=self.serialize_runtime(runtime))
        return self.serialize_runtime(runtime)

    def pause_runtime(self, db: Session, *, bot_id: str, wallet_address: str, user_id: str) -> dict[str, Any]:
        runtime = self._require_runtime(db, bot_id=bot_id, wallet_address=wallet_address, user_id=user_id)
        if self._get_value(runtime, "status") == "stopped":
            raise ValueError("Stopped runtime cannot be paused")
        now = datetime.now(tz=UTC)
        if self._settings.use_supabase_api:
            assert self._supabase is not None
            runtime = self._supabase.update(
                "bot_runtimes",
                {"status": "paused", "updated_at": now.isoformat()},
                filters={"id": self._get_value(runtime, "id")},
            )[0]
            self._append_runtime_transition(db, runtime=runtime, event_type="runtime.paused")
            self._publish_event(user_id=self._get_value(runtime, "user_id"), event="bot.runtime.paused", payload=self.serialize_runtime(runtime))
            return self.serialize_runtime(runtime)

        runtime.status = "paused"
        runtime.updated_at = now
        self._append_runtime_transition(db, runtime=runtime, event_type="runtime.paused")
        db.commit()
        db.refresh(runtime)
        self._publish_event(user_id=runtime.user_id, event="bot.runtime.paused", payload=self.serialize_runtime(runtime))
        return self.serialize_runtime(runtime)

    def resume_runtime(self, db: Session, *, bot_id: str, wallet_address: str, user_id: str) -> dict[str, Any]:
        runtime = self._require_runtime(db, bot_id=bot_id, wallet_address=wallet_address, user_id=user_id)
        if self._get_value(runtime, "status") == "stopped":
            raise ValueError("Stopped runtime cannot be resumed")
        if self._auth.get_trading_credentials(db, wallet_address) is None:
            raise ValueError("Authorize a delegated Pacifica agent wallet before resuming this bot.")
        now = datetime.now(tz=UTC)
        if self._settings.use_supabase_api:
            assert self._supabase is not None
            runtime = self._supabase.update(
                "bot_runtimes",
                {"status": "active", "updated_at": now.isoformat()},
                filters={"id": self._get_value(runtime, "id")},
            )[0]
            self._append_runtime_transition(db, runtime=runtime, event_type="runtime.resumed")
            self._publish_event(user_id=self._get_value(runtime, "user_id"), event="bot.runtime.resumed", payload=self.serialize_runtime(runtime))
            return self.serialize_runtime(runtime)

        runtime.status = "active"
        runtime.updated_at = now
        self._append_runtime_transition(db, runtime=runtime, event_type="runtime.resumed")
        db.commit()
        db.refresh(runtime)
        self._publish_event(user_id=runtime.user_id, event="bot.runtime.resumed", payload=self.serialize_runtime(runtime))
        return self.serialize_runtime(runtime)

    def stop_runtime(self, db: Session, *, bot_id: str, wallet_address: str, user_id: str) -> dict[str, Any]:
        runtime = self._require_runtime(db, bot_id=bot_id, wallet_address=wallet_address, user_id=user_id)
        now = datetime.now(tz=UTC)
        if self._settings.use_supabase_api:
            assert self._supabase is not None
            runtime = self._supabase.update(
                "bot_runtimes",
                {
                    "status": "stopped",
                    "stopped_at": now.isoformat(),
                    "updated_at": now.isoformat(),
                },
                filters={"id": self._get_value(runtime, "id")},
            )[0]
            self._append_runtime_transition(db, runtime=runtime, event_type="runtime.stopped")
            self._publish_event(user_id=self._get_value(runtime, "user_id"), event="bot.runtime.stopped", payload=self.serialize_runtime(runtime))
            return self.serialize_runtime(runtime)

        runtime.status = "stopped"
        runtime.stopped_at = now
        runtime.updated_at = now
        self._append_runtime_transition(db, runtime=runtime, event_type="runtime.stopped")
        db.commit()
        db.refresh(runtime)
        self._publish_event(user_id=runtime.user_id, event="bot.runtime.stopped", payload=self.serialize_runtime(runtime))
        return self.serialize_runtime(runtime)

    def list_runtime_events(
        self,
        db: Session,
        *,
        bot_id: str,
        wallet_address: str,
        user_id: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        runtime = self._require_runtime(db, bot_id=bot_id, wallet_address=wallet_address, user_id=user_id)
        if self._settings.use_supabase_api:
            assert self._supabase is not None
            rows = self._supabase.select(
                "bot_execution_events",
                filters={"runtime_id": self._get_value(runtime, "id")},
                order="created_at.desc",
                limit=limit,
            )
            return [self.serialize_event(row) for row in rows]
        rows = list(
            db.scalars(
                select(BotExecutionEvent)
                .where(BotExecutionEvent.runtime_id == runtime.id)
                .order_by(desc(BotExecutionEvent.created_at))
                .limit(limit)
            ).all()
        )
        return [self.serialize_event(row) for row in rows]

    def list_runtimes_for_wallet(
        self,
        db: Session,
        *,
        wallet_address: str,
        user_id: str,
    ) -> list[dict[str, Any]]:
        if self._settings.use_supabase_api:
            assert self._supabase is not None
            rows = self._supabase.select(
                "bot_runtimes",
                filters={"wallet_address": wallet_address},
                order="updated_at.desc",
            )
            return [self.serialize_runtime(row) for row in rows]

        rows = list(
            db.scalars(
                select(BotRuntime)
                .where(
                    BotRuntime.wallet_address == wallet_address,
                    BotRuntime.user_id == user_id,
                )
                .order_by(desc(BotRuntime.updated_at))
            ).all()
        )
        return [self.serialize_runtime(row) for row in rows]

    def get_active_runtimes(self, db: Session) -> list[BotRuntime] | list[dict[str, Any]]:
        if self._settings.use_supabase_api:
            assert self._supabase is not None
            return self._supabase.select("bot_runtimes", filters={"status": "active"})
        return list(db.scalars(select(BotRuntime).where(BotRuntime.status == "active")).all())

    def append_execution_event(
        self,
        db: Session,
        *,
        runtime: BotRuntime,
        event_type: str,
        decision_summary: str,
        request_payload: dict[str, Any],
        result_payload: dict[str, Any],
        status: str,
        error_reason: str | None = None,
    ) -> BotExecutionEvent | dict[str, Any]:
        if self._settings.use_supabase_api:
            assert self._supabase is not None
            event = {
                "id": str(uuid.uuid4()),
                "runtime_id": self._get_value(runtime, "id"),
                "event_type": event_type,
                "decision_summary": decision_summary,
                "request_payload": request_payload,
                "result_payload": result_payload,
                "status": status,
                "error_reason": error_reason,
                "created_at": datetime.now(tz=UTC).isoformat(),
            }
            return self._supabase.insert("bot_execution_events", event)[0]

        event = BotExecutionEvent(
            runtime_id=runtime.id,
            event_type=event_type,
            decision_summary=decision_summary,
            request_payload=request_payload,
            result_payload=result_payload,
            status=status,
            error_reason=error_reason,
        )
        db.add(event)
        db.flush()
        return event

    @staticmethod
    def serialize_runtime(runtime: BotRuntime | dict[str, Any]) -> dict[str, Any]:
        if isinstance(runtime, dict):
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
        return {
            "id": runtime.id,
            "bot_definition_id": runtime.bot_definition_id,
            "user_id": runtime.user_id,
            "wallet_address": runtime.wallet_address,
            "status": runtime.status,
            "mode": runtime.mode,
            "risk_policy_json": runtime.risk_policy_json,
            "deployed_at": runtime.deployed_at,
            "stopped_at": runtime.stopped_at,
            "updated_at": runtime.updated_at,
        }

    @staticmethod
    def serialize_event(event: BotExecutionEvent | dict[str, Any]) -> dict[str, Any]:
        if isinstance(event, dict):
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
        return {
            "id": event.id,
            "runtime_id": event.runtime_id,
            "event_type": event.event_type,
            "decision_summary": event.decision_summary,
            "request_payload": event.request_payload,
            "result_payload": event.result_payload,
            "status": event.status,
            "error_reason": event.error_reason,
            "created_at": event.created_at,
        }

    def _require_runtime(self, db: Session, *, bot_id: str, wallet_address: str, user_id: str) -> BotRuntime | dict[str, Any]:
        bot = self._resolve_bot(db, bot_id=bot_id, wallet_address=wallet_address, user_id=user_id)
        runtime = self._resolve_runtime(
            db,
            bot_definition_id=self._get_value(bot, "id"),
            wallet_address=wallet_address,
        )
        if runtime is None:
            raise ValueError("Bot runtime not found")
        return runtime

    def _resolve_bot(self, db: Session, *, bot_id: str, wallet_address: str, user_id: str) -> BotDefinition | dict[str, Any]:
        if self._settings.use_supabase_api:
            assert self._supabase is not None
            bot = self._supabase.maybe_one(
                "bot_definitions",
                filters={"id": bot_id, "wallet_address": wallet_address},
            )
            if bot is None:
                raise ValueError("Bot not found")
            return bot

        bot = db.scalar(
            select(BotDefinition)
            .where(
                BotDefinition.id == bot_id,
                BotDefinition.wallet_address == wallet_address,
                BotDefinition.user_id == user_id,
            )
            .limit(1)
        )
        if bot is None:
            raise ValueError("Bot not found")
        return bot

    def _resolve_runtime(self, db: Session, *, bot_definition_id: str, wallet_address: str) -> BotRuntime | dict[str, Any] | None:
        if self._settings.use_supabase_api:
            assert self._supabase is not None
            return self._supabase.maybe_one(
                "bot_runtimes",
                filters={"bot_definition_id": bot_definition_id, "wallet_address": wallet_address},
            )
        return db.scalar(
            select(BotRuntime)
            .where(
                BotRuntime.bot_definition_id == bot_definition_id,
                BotRuntime.wallet_address == wallet_address,
            )
            .limit(1)
        )

    def _append_runtime_transition(self, db: Session, *, runtime: BotRuntime | dict[str, Any], event_type: str) -> None:
        if self._settings.use_supabase_api:
            assert self._supabase is not None
            self._supabase.insert(
                "bot_execution_events",
                {
                    "id": str(uuid.uuid4()),
                    "runtime_id": self._get_value(runtime, "id"),
                    "event_type": event_type,
                    "decision_summary": f"runtime transitioned to {self._get_value(runtime, 'status')}",
                    "request_payload": {},
                    "result_payload": {"status": self._get_value(runtime, "status")},
                    "status": "success",
                    "created_at": datetime.now(tz=UTC).isoformat(),
                },
            )
            return
        event = BotExecutionEvent(
            runtime_id=runtime.id,
            event_type=event_type,
            decision_summary=f"runtime transitioned to {runtime.status}",
            request_payload={},
            result_payload={"status": runtime.status},
            status="success",
        )
        db.add(event)

    @staticmethod
    def _publish_event(*, user_id: str, event: str, payload: dict[str, Any]) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        loop.create_task(broadcaster.publish(channel=f"user:{user_id}", event=event, payload=payload))

    @staticmethod
    def _get_value(payload: BotRuntime | BotDefinition | dict[str, Any], key: str) -> Any:
        if isinstance(payload, dict):
            return payload.get(key)
        return getattr(payload, key)
