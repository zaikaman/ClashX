from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from src.services.supabase_rest import SupabaseRestClient

AiJobType = Literal["builder_ai_chat", "copilot_chat", "backtest_run"]
AiJobStatus = Literal["queued", "running", "completed", "failed"]


def _utc_now() -> str:
    return datetime.now(tz=UTC).isoformat()


class AiJobService:
    def __init__(self, *, supabase: SupabaseRestClient | None = None) -> None:
        self._supabase = supabase or SupabaseRestClient()

    def create_job(
        self,
        *,
        job_type: AiJobType,
        request_payload: dict[str, Any],
        wallet_address: str | None = None,
        conversation_id: str | None = None,
    ) -> dict[str, Any]:
        now = _utc_now()
        row = {
            "id": str(uuid.uuid4()),
            "job_type": job_type,
            "status": "queued",
            "wallet_address": (wallet_address or "").strip() or None,
            "conversation_id": (conversation_id or "").strip() or None,
            "request_payload_json": request_payload,
            "result_payload_json": {},
            "error_detail": None,
            "started_at": None,
            "completed_at": None,
            "created_at": now,
            "updated_at": now,
        }
        self._supabase.insert("ai_job_runs", row, returning="minimal")
        return row

    def get_job(self, *, job_id: str) -> dict[str, Any] | None:
        return self._supabase.maybe_one("ai_job_runs", filters={"id": job_id})

    def get_job_for_wallets(self, *, job_id: str, wallet_addresses: list[str]) -> dict[str, Any] | None:
        normalized_wallets = [wallet.strip() for wallet in wallet_addresses if wallet and wallet.strip()]
        if not normalized_wallets:
            return None
        return self._supabase.maybe_one(
            "ai_job_runs",
            filters={
                "id": job_id,
                "wallet_address": ("in", normalized_wallets),
            },
        )

    def mark_running(self, *, job_id: str) -> dict[str, Any] | None:
        now = _utc_now()
        updated = self._supabase.update(
            "ai_job_runs",
            {
                "status": "running",
                "started_at": now,
                "updated_at": now,
                "error_detail": None,
            },
            filters={"id": job_id},
        )
        return updated[0] if updated else None

    def update_progress(self, *, job_id: str, progress_payload: dict[str, Any]) -> dict[str, Any] | None:
        now = _utc_now()
        updated = self._supabase.update(
            "ai_job_runs",
            {
                "result_payload_json": progress_payload,
                "updated_at": now,
            },
            filters={"id": job_id},
        )
        return updated[0] if updated else None

    def mark_completed(self, *, job_id: str, result_payload: dict[str, Any]) -> dict[str, Any] | None:
        now = _utc_now()
        updated = self._supabase.update(
            "ai_job_runs",
            {
                "status": "completed",
                "result_payload_json": result_payload,
                "error_detail": None,
                "completed_at": now,
                "updated_at": now,
            },
            filters={"id": job_id},
        )
        return updated[0] if updated else None

    def mark_failed(self, *, job_id: str, error_detail: str) -> dict[str, Any] | None:
        now = _utc_now()
        updated = self._supabase.update(
            "ai_job_runs",
            {
                "status": "failed",
                "error_detail": error_detail.strip() or "AI job failed.",
                "completed_at": now,
                "updated_at": now,
            },
            filters={"id": job_id},
        )
        return updated[0] if updated else None
