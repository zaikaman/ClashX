from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from typing import Any

from src.services.supabase_rest import SupabaseRestError
from src.services.worker_coordination_service import WorkerCoordinationService


class _FakeSupabaseRestClient:
    def __init__(self) -> None:
        self.tables: dict[str, list[dict[str, Any]]] = {
            "worker_leases": [],
            "bot_action_claims": [],
            "bot_execution_events": [],
        }
        self.insert_failures: dict[str, list[SupabaseRestError]] = {}
        self.update_failures: dict[str, list[SupabaseRestError]] = {}
        self.select_failures: dict[str, list[SupabaseRestError]] = {}
        self.delete_failures: dict[str, list[SupabaseRestError]] = {}

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
        self._maybe_raise(self.select_failures, table)
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
        returning: str = "representation",
    ) -> list[dict[str, Any]]:
        del upsert, on_conflict, returning
        self._maybe_raise(self.insert_failures, table)
        items = payload if isinstance(payload, list) else [payload]
        stored: list[dict[str, Any]] = []
        for item in items:
            if table in {"bot_action_claims", "worker_leases"}:
                key_fields = (
                    ("runtime_id", "idempotency_key")
                    if table == "bot_action_claims"
                    else ("lease_key",)
                )
                duplicate = next(
                    (
                        row
                        for row in self.tables[table]
                        if all(row.get(field) == item.get(field) for field in key_fields)
                    ),
                    None,
                )
                if duplicate is not None:
                    message = "duplicate claim" if table == "bot_action_claims" else "duplicate lease"
                    raise SupabaseRestError(message, status_code=409)
            stored_item = deepcopy(item)
            self.tables.setdefault(table, []).append(stored_item)
            stored.append(deepcopy(stored_item))
        return stored

    def update(
        self,
        table: str,
        values: dict[str, Any],
        *,
        filters: dict[str, Any],
    ) -> list[dict[str, Any]]:
        self._maybe_raise(self.update_failures, table)
        updated: list[dict[str, Any]] = []
        for row in self.tables.get(table, []):
            if not self._matches(row, filters):
                continue
            row.update(deepcopy(values))
            updated.append(deepcopy(row))
        return updated

    def delete(self, table: str, *, filters: dict[str, Any]) -> None:
        self._maybe_raise(self.delete_failures, table)
        self.tables[table] = [row for row in self.tables.get(table, []) if not self._matches(row, filters)]

    @staticmethod
    def _matches(row: dict[str, Any], filters: dict[str, Any] | None) -> bool:
        if not filters:
            return True
        for key, expected in filters.items():
            value = row.get(key)
            if isinstance(expected, tuple):
                operator, operand = expected
                if operator == "lt" and not (value is not None and value < operand):
                    return False
                if operator == "gt" and not (value is not None and value > operand):
                    return False
                if operator == "eq" and value != operand:
                    return False
                continue
            if value != expected:
                return False
        return True

    @staticmethod
    def _maybe_raise(
        failures: dict[str, list[SupabaseRestError]],
        table: str,
    ) -> None:
        queued = failures.get(table) or []
        if queued:
            raise queued.pop(0)

    def queue_failure(self, operation: str, table: str, error: SupabaseRestError) -> None:
        queues = {
            "insert": self.insert_failures,
            "update": self.update_failures,
            "select": self.select_failures,
            "delete": self.delete_failures,
        }
        queues[operation].setdefault(table, []).append(error)


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


def test_try_claim_lease_returns_false_when_takeover_hits_transient_supabase_error() -> None:
    supabase = _FakeSupabaseRestClient()
    now = datetime.now(tz=UTC)
    supabase.tables["worker_leases"] = [
        {
            "lease_key": "lease-1",
            "owner_id": "worker-1",
            "expires_at": (now - timedelta(minutes=1)).isoformat(),
            "updated_at": (now - timedelta(minutes=1)).isoformat(),
        }
    ]
    supabase.queue_failure(
        "update",
        "worker_leases",
        SupabaseRestError("temporary outage", status_code=502),
    )
    service = _build_service(supabase)

    assert service.try_claim_lease("lease-1", ttl_seconds=30) is False
    assert supabase.tables["worker_leases"][0]["owner_id"] == "worker-1"


def test_release_lease_ignores_transient_supabase_error() -> None:
    supabase = _FakeSupabaseRestClient()
    now = datetime.now(tz=UTC)
    supabase.tables["worker_leases"] = [
        {
            "lease_key": "lease-1",
            "owner_id": "worker-2",
            "expires_at": (now + timedelta(minutes=1)).isoformat(),
            "updated_at": now.isoformat(),
        }
    ]
    supabase.queue_failure(
        "update",
        "worker_leases",
        SupabaseRestError("temporary outage", status_code=503),
    )
    service = _build_service(supabase)

    service.release_lease("lease-1")
    assert supabase.tables["worker_leases"][0]["owner_id"] == "worker-2"


def test_try_claim_action_returns_false_when_supabase_is_temporarily_unavailable() -> None:
    supabase = _FakeSupabaseRestClient()
    supabase.queue_failure(
        "insert",
        "bot_action_claims",
        SupabaseRestError("temporary outage", status_code=502),
    )
    service = _build_service(supabase)

    assert service.try_claim_action(runtime_id="runtime-1", idempotency_key="idem:1") is False
    assert supabase.tables["bot_action_claims"] == []


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
