from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from typing import Any

from src.services.supabase_rest import SupabaseRestError
from src.services.worker_coordination_service import WorkerCoordinationService


class _FakeSupabaseRestClient:
    def __init__(self) -> None:
        self.tables: dict[str, list[dict[str, Any]]] = {
            "bot_action_claims": [],
            "bot_execution_events": [],
        }

    def select(
        self,
        table: str,
        *,
        filters: dict[str, Any] | None = None,
        order: str | None = None,
        limit: int | None = None,
        columns: str = "*",
    ) -> list[dict[str, Any]]:
        del columns
        rows = [deepcopy(row) for row in self.tables.get(table, []) if self._matches(row, filters)]
        if order:
            field, _, direction = order.partition(".")
            rows.sort(key=lambda row: row.get(field), reverse=direction.lower() == "desc")
        if limit is not None:
            rows = rows[:limit]
        return rows

    def maybe_one(
        self,
        table: str,
        *,
        filters: dict[str, Any] | None = None,
        order: str | None = None,
        columns: str = "*",
    ) -> dict[str, Any] | None:
        rows = self.select(table, filters=filters, order=order, limit=1, columns=columns)
        return rows[0] if rows else None

    def insert(
        self,
        table: str,
        payload: dict[str, Any] | list[dict[str, Any]],
        *,
        upsert: bool = False,
        on_conflict: str | None = None,
    ) -> list[dict[str, Any]]:
        del upsert, on_conflict
        items = payload if isinstance(payload, list) else [payload]
        stored: list[dict[str, Any]] = []
        for item in items:
            if table == "bot_action_claims":
                duplicate = next(
                    (
                        row
                        for row in self.tables[table]
                        if row.get("runtime_id") == item.get("runtime_id")
                        and row.get("idempotency_key") == item.get("idempotency_key")
                    ),
                    None,
                )
                if duplicate is not None:
                    raise SupabaseRestError("duplicate claim", status_code=409)
            stored_item = deepcopy(item)
            self.tables.setdefault(table, []).append(stored_item)
            stored.append(deepcopy(stored_item))
        return stored

    def delete(self, table: str, *, filters: dict[str, Any]) -> None:
        self.tables[table] = [row for row in self.tables.get(table, []) if not self._matches(row, filters)]

    @staticmethod
    def _matches(row: dict[str, Any], filters: dict[str, Any] | None) -> bool:
        if not filters:
            return True
        return all(row.get(key) == expected for key, expected in filters.items())


def _build_service(supabase: _FakeSupabaseRestClient, *, owner_id: str = "worker-2") -> WorkerCoordinationService:
    service = WorkerCoordinationService.__new__(WorkerCoordinationService)
    service._supabase = supabase
    service._owner_id = owner_id
    return service


def test_try_claim_action_reclaims_terminal_failed_claim() -> None:
    supabase = _FakeSupabaseRestClient()
    runtime_id = "runtime-1"
    idempotency_key = "idem:runtime-1:2:1:deadbeef"
    supabase.tables["bot_action_claims"] = [
        {
            "id": "claim-1",
            "runtime_id": runtime_id,
            "idempotency_key": idempotency_key,
            "claimed_by": "worker-1",
            "created_at": datetime.now(tz=UTC).isoformat(),
        }
    ]
    supabase.tables["bot_execution_events"] = [
        {
            "id": "event-1",
            "runtime_id": runtime_id,
            "event_type": "action.failed",
            "decision_summary": idempotency_key,
            "created_at": datetime.now(tz=UTC).isoformat(),
        }
    ]

    service = _build_service(supabase)

    assert service.try_claim_action(runtime_id=runtime_id, idempotency_key=idempotency_key) is True
    assert len(supabase.tables["bot_action_claims"]) == 1
    assert supabase.tables["bot_action_claims"][0]["claimed_by"] == "worker-2"


def test_try_claim_action_does_not_reclaim_terminal_executed_claim() -> None:
    supabase = _FakeSupabaseRestClient()
    runtime_id = "runtime-1"
    idempotency_key = "idem:runtime-1:2:1:deadbeef"
    supabase.tables["bot_action_claims"] = [
        {
            "id": "claim-1",
            "runtime_id": runtime_id,
            "idempotency_key": idempotency_key,
            "claimed_by": "worker-1",
            "created_at": datetime.now(tz=UTC).isoformat(),
        }
    ]
    supabase.tables["bot_execution_events"] = [
        {
            "id": "event-1",
            "runtime_id": runtime_id,
            "event_type": "action.executed",
            "decision_summary": idempotency_key,
            "created_at": datetime.now(tz=UTC).isoformat(),
        }
    ]

    service = _build_service(supabase)

    assert service.try_claim_action(runtime_id=runtime_id, idempotency_key=idempotency_key) is False
    assert len(supabase.tables["bot_action_claims"]) == 1
    assert supabase.tables["bot_action_claims"][0]["claimed_by"] == "worker-1"


def test_try_claim_action_does_not_reclaim_recent_inflight_claim() -> None:
    supabase = _FakeSupabaseRestClient()
    runtime_id = "runtime-1"
    idempotency_key = "idem:runtime-1:2:1:deadbeef"
    supabase.tables["bot_action_claims"] = [
        {
            "id": "claim-1",
            "runtime_id": runtime_id,
            "idempotency_key": idempotency_key,
            "claimed_by": "worker-1",
            "created_at": datetime.now(tz=UTC).isoformat(),
        }
    ]

    service = _build_service(supabase)

    assert service.try_claim_action(runtime_id=runtime_id, idempotency_key=idempotency_key) is False
    assert supabase.tables["bot_action_claims"][0]["claimed_by"] == "worker-1"


def test_try_claim_action_reclaims_stale_inflight_claim() -> None:
    supabase = _FakeSupabaseRestClient()
    runtime_id = "runtime-1"
    idempotency_key = "idem:runtime-1:2:1:deadbeef"
    supabase.tables["bot_action_claims"] = [
        {
            "id": "claim-1",
            "runtime_id": runtime_id,
            "idempotency_key": idempotency_key,
            "claimed_by": "worker-1",
            "created_at": (datetime.now(tz=UTC) - timedelta(minutes=5)).isoformat(),
        }
    ]

    service = _build_service(supabase)

    assert service.try_claim_action(runtime_id=runtime_id, idempotency_key=idempotency_key) is True
    assert len(supabase.tables["bot_action_claims"]) == 1
    assert supabase.tables["bot_action_claims"][0]["claimed_by"] == "worker-2"
