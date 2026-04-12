from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from time import monotonic
from typing import Any

from src.core.settings import get_settings
from src.services.supabase_rest import SupabaseRestClient, SupabaseRestError


logger = logging.getLogger(__name__)
ACTION_CLAIM_TTL_SECONDS = 90
LEASE_CLEANUP_INTERVAL_SECONDS = 15 * 60
LEASE_CLEANUP_RETENTION_SECONDS = 24 * 60 * 60
LEASE_CLEANUP_BATCH_SIZE = 5000
RETRYABLE_TERMINAL_ACTION_EVENTS = {"action.failed"}
NON_RETRYABLE_TERMINAL_ACTION_EVENTS = {"action.executed"}


class WorkerCoordinationService:
    def __init__(self, supabase: SupabaseRestClient | None = None) -> None:
        self._settings = get_settings()
        self._supabase = supabase or SupabaseRestClient()
        self._owner_id = self._settings.worker_instance_id
        self._next_lease_cleanup_at = 0.0

    def try_claim_lease(self, lease_key: str, *, ttl_seconds: int) -> bool:
        now = datetime.now(tz=UTC)
        self._cleanup_expired_leases_if_due(now)
        expires_at = (now + timedelta(seconds=ttl_seconds)).isoformat()
        payload = {
            "lease_key": lease_key,
            "owner_id": self._owner_id,
            "expires_at": expires_at,
            "updated_at": now.isoformat(),
        }
        try:
            current_lease = self._supabase.maybe_one(
                "worker_leases",
                filters={"lease_key": lease_key},
            )
        except SupabaseRestError as exc:
            if exc.is_retryable:
                logger.warning("Skipping lease lookup for %s because Supabase is temporarily unavailable: %s", lease_key, exc)
                return False
            raise

        if isinstance(current_lease, dict):
            return self._try_update_existing_lease(
                lease_key=lease_key,
                current_lease=current_lease,
                now=now,
                expires_at=expires_at,
            )

        try:
            self._supabase.insert("worker_leases", payload, returning="minimal")
            return True
        except SupabaseRestError as exc:
            if exc.status_code == 409:
                pass
            elif exc.is_retryable:
                logger.warning("Skipping lease claim for %s because Supabase is temporarily unavailable: %s", lease_key, exc)
                return False
            else:
                raise
        try:
            current_lease = self._supabase.maybe_one(
                "worker_leases",
                filters={"lease_key": lease_key},
            )
        except SupabaseRestError as exc:
            if exc.is_retryable:
                logger.warning(
                    "Skipping lease conflict lookup for %s because Supabase is temporarily unavailable: %s",
                    lease_key,
                    exc,
                )
                return False
            raise
        if not isinstance(current_lease, dict):
            return False
        return self._try_update_existing_lease(
            lease_key=lease_key,
            current_lease=current_lease,
            now=now,
            expires_at=expires_at,
        )

    def _try_update_existing_lease(
        self,
        *,
        lease_key: str,
        current_lease: dict[str, Any],
        now: datetime,
        expires_at: str,
    ) -> bool:
        current_owner = str(current_lease.get("owner_id") or "")
        current_expiry = self._parse_timestamp(current_lease.get("expires_at"))
        if current_owner != self._owner_id and (current_expiry is None or current_expiry > now):
            return False

        try:
            if current_owner == self._owner_id:
                renewed = self._supabase.update(
                    "worker_leases",
                    {"owner_id": self._owner_id, "expires_at": expires_at, "updated_at": now.isoformat()},
                    filters={"lease_key": lease_key, "owner_id": self._owner_id},
                )
            else:
                renewed = self._supabase.update(
                    "worker_leases",
                    {"owner_id": self._owner_id, "expires_at": expires_at, "updated_at": now.isoformat()},
                    filters={"lease_key": lease_key, "expires_at": ("lt", now.isoformat())},
                )
        except SupabaseRestError as exc:
            if exc.is_retryable:
                logger.warning(
                    "Skipping lease update for %s because Supabase is temporarily unavailable: %s",
                    lease_key,
                    exc,
                )
                return False
            raise
        return bool(renewed)

    def release_lease(self, lease_key: str) -> None:
        now = datetime.now(tz=UTC).isoformat()
        try:
            self._supabase.update(
                "worker_leases",
                {"expires_at": now, "updated_at": now},
                filters={"lease_key": lease_key, "owner_id": self._owner_id},
            )
        except SupabaseRestError as exc:
            if exc.is_retryable:
                logger.warning("Deferred lease release for %s because Supabase is temporarily unavailable: %s", lease_key, exc)
                return
            raise

    def _cleanup_expired_leases_if_due(self, now: datetime) -> None:
        if monotonic() < self._next_lease_cleanup_at:
            return
        self._next_lease_cleanup_at = monotonic() + LEASE_CLEANUP_INTERVAL_SECONDS
        cutoff = (now - timedelta(seconds=LEASE_CLEANUP_RETENTION_SECONDS)).isoformat()
        try:
            stale_leases = self._supabase.select(
                "worker_leases",
                columns="lease_key",
                filters={"expires_at": ("lt", cutoff)},
                order="expires_at.asc",
                limit=LEASE_CLEANUP_BATCH_SIZE,
            )
        except SupabaseRestError as exc:
            if exc.is_retryable:
                logger.warning("Skipping worker lease cleanup lookup because Supabase is temporarily unavailable: %s", exc)
                return
            logger.exception("Worker lease cleanup lookup failed")
            return

        stale_keys = [str(row.get("lease_key") or "") for row in stale_leases if isinstance(row, dict) and row.get("lease_key")]
        if not stale_keys:
            return

        try:
            self._supabase.delete(
                "worker_leases",
                filters={
                    "lease_key": ("in", stale_keys),
                    "expires_at": ("lt", cutoff),
                },
            )
        except SupabaseRestError as exc:
            if exc.is_retryable:
                logger.warning("Skipping worker lease cleanup delete because Supabase is temporarily unavailable: %s", exc)
                return
            logger.exception("Worker lease cleanup delete failed")

    def try_claim_action(self, *, runtime_id: str, idempotency_key: str) -> bool:
        claim_payload = {
            "id": str(uuid.uuid4()),
            "runtime_id": runtime_id,
            "idempotency_key": idempotency_key,
            "claimed_by": self._owner_id,
            "created_at": datetime.now(tz=UTC).isoformat(),
        }
        try:
            self._supabase.insert("bot_action_claims", claim_payload, returning="minimal")
            return True
        except SupabaseRestError as exc:
            if exc.status_code == 409:
                pass
            elif exc.is_retryable:
                logger.warning(
                    "Skipping action claim for runtime %s and key %s because Supabase is temporarily unavailable: %s",
                    runtime_id,
                    idempotency_key,
                    exc,
                )
                return False
            else:
                raise

        if not self._should_reclaim_action_claim(runtime_id=runtime_id, idempotency_key=idempotency_key):
            return False

        try:
            self._supabase.delete(
                "bot_action_claims",
                filters={"runtime_id": runtime_id, "idempotency_key": idempotency_key},
            )
        except SupabaseRestError as exc:
            if exc.is_retryable:
                logger.warning(
                    "Skipping action-claim reclaim for runtime %s and key %s because Supabase is temporarily unavailable: %s",
                    runtime_id,
                    idempotency_key,
                    exc,
                )
                return False
            raise
        try:
            self._supabase.insert("bot_action_claims", claim_payload, returning="minimal")
            return True
        except SupabaseRestError as exc:
            if exc.status_code == 409:
                return False
            if exc.is_retryable:
                logger.warning(
                    "Skipping reclaimed action claim for runtime %s and key %s because Supabase is temporarily unavailable: %s",
                    runtime_id,
                    idempotency_key,
                    exc,
                )
                return False
            raise

    def _should_reclaim_action_claim(self, *, runtime_id: str, idempotency_key: str) -> bool:
        try:
            claim = self._supabase.maybe_one(
                "bot_action_claims",
                filters={"runtime_id": runtime_id, "idempotency_key": idempotency_key},
                order="created_at.desc",
            )
        except SupabaseRestError as exc:
            if exc.is_retryable:
                logger.warning(
                    "Skipping action-claim reclaim check for runtime %s and key %s because Supabase is temporarily unavailable: %s",
                    runtime_id,
                    idempotency_key,
                    exc,
                )
                return False
            raise
        if not isinstance(claim, dict):
            return False

        try:
            terminal_event = self._supabase.maybe_one(
                "bot_execution_events",
                filters={"runtime_id": runtime_id, "decision_summary": idempotency_key},
                order="created_at.desc",
            )
        except SupabaseRestError as exc:
            if exc.is_retryable:
                logger.warning(
                    "Skipping action-claim terminal-event lookup for runtime %s and key %s because Supabase is temporarily unavailable: %s",
                    runtime_id,
                    idempotency_key,
                    exc,
                )
                return False
            raise
        if (
            isinstance(terminal_event, dict)
            and str(terminal_event.get("event_type") or "") in NON_RETRYABLE_TERMINAL_ACTION_EVENTS
        ):
            logger.info(
                "Keeping completed action claim for runtime %s and key %s",
                runtime_id,
                idempotency_key,
            )
            return False

        if (
            isinstance(terminal_event, dict)
            and str(terminal_event.get("event_type") or "") in RETRYABLE_TERMINAL_ACTION_EVENTS
        ):
            logger.warning(
                "Reclaiming failed action claim for runtime %s and key %s",
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
