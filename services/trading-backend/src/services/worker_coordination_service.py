from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from src.core.settings import get_settings
from src.services.supabase_rest import SupabaseRestClient, SupabaseRestError


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
        try:
            self._supabase.insert(
                "bot_action_claims",
                {
                    "id": str(uuid.uuid4()),
                    "runtime_id": runtime_id,
                    "idempotency_key": idempotency_key,
                    "claimed_by": self._owner_id,
                    "created_at": datetime.now(tz=UTC).isoformat(),
                },
            )
            return True
        except SupabaseRestError as exc:
            if exc.status_code == 409:
                return False
            raise
