from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from src.core.settings import get_settings
from src.services.supabase_rest import SupabaseRestClient, SupabaseRestError


logger = logging.getLogger(__name__)
ACTION_CLAIM_TTL_SECONDS = 90
TERMINAL_ACTION_EVENTS = {"action.executed", "action.failed"}


class WorkerCoordinationService:
    def __init__(self, supabase: SupabaseRestClient | None = None) -> None:
        self._settings = get_settings()
        self._supabase = supabase or SupabaseRestClient()
        self._owner_id = self._settings.worker_instance_id

    def try_claim_lease(self, lease_key: str, *, ttl_seconds: int) -> bool:
        now = datetime.now(tz=UTC)
        expires_at = (now + timedelta(seconds=ttl_seconds)).isoformat()
        payload = {
            "lease_key": lease_key,
            "owner_id": self._owner_id,
            "expires_at": expires_at,
            "updated_at": now.isoformat(),
        }
        try:
            self._supabase.insert("worker_leases", payload)
            return True
        except SupabaseRestError as exc:
            if exc.status_code != 409:
                raise
        updated = self._supabase.update(
            "worker_leases",
            {"owner_id": self._owner_id, "expires_at": expires_at, "updated_at": now.isoformat()},
            filters={"lease_key": lease_key, "expires_at": ("lt", now.isoformat())},
        )
        return bool(updated)

    def release_lease(self, lease_key: str) -> None:
        now = datetime.now(tz=UTC).isoformat()
        self._supabase.update(
            "worker_leases",
            {"expires_at": now, "updated_at": now},
            filters={"lease_key": lease_key, "owner_id": self._owner_id},
        )

    def try_claim_action(self, *, runtime_id: str, idempotency_key: str) -> bool:
        claim_payload = {
            "id": str(uuid.uuid4()),
            "runtime_id": runtime_id,
            "idempotency_key": idempotency_key,
            "claimed_by": self._owner_id,
            "created_at": datetime.now(tz=UTC).isoformat(),
        }
        try:
            self._supabase.insert("bot_action_claims", claim_payload)
            return True
        except SupabaseRestError as exc:
            if exc.status_code != 409:
                raise

        if not self._should_reclaim_action_claim(runtime_id=runtime_id, idempotency_key=idempotency_key):
            return False

        self._supabase.delete(
            "bot_action_claims",
            filters={"runtime_id": runtime_id, "idempotency_key": idempotency_key},
        )
        try:
            self._supabase.insert("bot_action_claims", claim_payload)
            return True
        except SupabaseRestError as exc:
            if exc.status_code == 409:
                return False
            raise

    def _should_reclaim_action_claim(self, *, runtime_id: str, idempotency_key: str) -> bool:
        claim = self._supabase.maybe_one(
            "bot_action_claims",
            filters={"runtime_id": runtime_id, "idempotency_key": idempotency_key},
            order="created_at.desc",
        )
        if not isinstance(claim, dict):
            return False

        terminal_event = self._supabase.maybe_one(
            "bot_execution_events",
            filters={"runtime_id": runtime_id, "decision_summary": idempotency_key},
            order="created_at.desc",
        )
        if isinstance(terminal_event, dict) and str(terminal_event.get("event_type") or "") in TERMINAL_ACTION_EVENTS:
            logger.warning(
                "Reclaiming terminal action claim for runtime %s and key %s",
                runtime_id,
                idempotency_key,
            )
            return True

        created_at = self._parse_timestamp(claim.get("created_at"))
        if created_at is None:
            return False
        if (datetime.now(tz=UTC) - created_at).total_seconds() < ACTION_CLAIM_TTL_SECONDS:
            return False

        logger.warning(
            "Reclaiming stale action claim for runtime %s and key %s after %ss",
            runtime_id,
            idempotency_key,
            ACTION_CLAIM_TTL_SECONDS,
        )
        return True

    @staticmethod
    def _parse_timestamp(value: Any) -> datetime | None:
        if value in (None, ""):
            return None
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
