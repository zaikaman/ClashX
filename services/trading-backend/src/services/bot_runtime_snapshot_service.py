from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

from src.services.bot_performance_service import BotPerformanceService
from src.services.runtime_observability_service import RuntimeObservabilityService
from src.services.supabase_rest import SupabaseRestClient


class BotRuntimeSnapshotService:
    def __init__(
        self,
        *,
        supabase: SupabaseRestClient | None = None,
        performance_service: BotPerformanceService | None = None,
        observability_service: RuntimeObservabilityService | None = None,
    ) -> None:
        self._supabase = supabase or SupabaseRestClient()
        self._performance = performance_service or BotPerformanceService(supabase=self._supabase)
        self._observability = observability_service or RuntimeObservabilityService(supabase=self._supabase)

    async def refresh_wallet_snapshots(self, wallet_address: str) -> dict[str, dict[str, Any]]:
        resolved_wallet = str(wallet_address or "").strip()
        if not resolved_wallet:
            return {}

        runtimes = self._supabase.select(
            "bot_runtimes",
            columns="id,bot_definition_id,user_id,wallet_address,status,mode,risk_policy_json,deployed_at,stopped_at,updated_at",
            filters={"wallet_address": resolved_wallet},
        )
        runtime_ids = [
            str(runtime.get("id") or "").strip()
            for runtime in runtimes
            if str(runtime.get("id") or "").strip()
        ]
        if not runtime_ids:
            self._delete_stale_wallet_snapshots(wallet_address=resolved_wallet, active_runtime_ids=[])
            return {}

        performance_by_runtime = await self._performance.get_cached_runtimes_performance_map(runtimes)
        overviews_by_bot = self._observability.get_overviews_for_wallet(
            None,
            wallet_address=resolved_wallet,
            user_id="",
        )
        now = datetime.now(tz=UTC).isoformat()

        rows: list[dict[str, Any]] = []
        snapshots_by_bot: dict[str, dict[str, Any]] = {}
        for runtime in runtimes:
            runtime_id = str(runtime.get("id") or "").strip()
            bot_definition_id = str(runtime.get("bot_definition_id") or "").strip()
            if not runtime_id or not bot_definition_id:
                continue

            overview = overviews_by_bot.get(bot_definition_id) or self._observability.draft_overview_payload()
            performance = performance_by_runtime.get(runtime_id) or self._performance.empty_performance_payload()
            row = {
                "runtime_id": runtime_id,
                "bot_definition_id": bot_definition_id,
                "user_id": str(runtime.get("user_id") or "").strip() or None,
                "wallet_address": resolved_wallet,
                "status": str(runtime.get("status") or "").strip() or "draft",
                "mode": str(runtime.get("mode") or "").strip() or "live",
                "health_json": overview.get("health") if isinstance(overview.get("health"), dict) else {},
                "metrics_json": overview.get("metrics") if isinstance(overview.get("metrics"), dict) else {},
                "performance_json": performance if isinstance(performance, dict) else self._performance.empty_performance_payload(),
                "source_runtime_updated_at": runtime.get("updated_at"),
                "last_computed_at": now,
            }
            rows.append(row)
            snapshots_by_bot[bot_definition_id] = row

        if rows:
            self._supabase.insert(
                "bot_runtime_snapshots",
                rows,
                upsert=True,
                on_conflict="runtime_id",
                returning="minimal",
            )
        self._delete_stale_wallet_snapshots(wallet_address=resolved_wallet, active_runtime_ids=runtime_ids)
        return snapshots_by_bot

    def list_snapshots_for_wallet(self, wallet_address: str) -> dict[str, dict[str, Any]]:
        resolved_wallet = str(wallet_address or "").strip()
        if not resolved_wallet:
            return {}
        rows = self._supabase.select(
            "bot_runtime_snapshots",
            columns="runtime_id,bot_definition_id,user_id,wallet_address,status,mode,health_json,metrics_json,performance_json,source_runtime_updated_at,last_computed_at",
            filters={"wallet_address": resolved_wallet},
        )
        return {
            str(row.get("bot_definition_id") or "").strip(): row
            for row in rows
            if str(row.get("bot_definition_id") or "").strip()
        }

    def get_snapshot_for_bot(self, *, bot_id: str, wallet_address: str) -> dict[str, Any] | None:
        resolved_bot_id = str(bot_id or "").strip()
        resolved_wallet = str(wallet_address or "").strip()
        if not resolved_bot_id or not resolved_wallet:
            return None
        return self._supabase.maybe_one(
            "bot_runtime_snapshots",
            columns="runtime_id,bot_definition_id,user_id,wallet_address,status,mode,health_json,metrics_json,performance_json,source_runtime_updated_at,last_computed_at",
            filters={"bot_definition_id": resolved_bot_id, "wallet_address": resolved_wallet},
            cache_ttl_seconds=5,
        )

    @staticmethod
    def snapshot_to_overview(snapshot: dict[str, Any]) -> dict[str, Any]:
        return {
            "health": deepcopy(snapshot.get("health_json") if isinstance(snapshot.get("health_json"), dict) else {}),
            "metrics": deepcopy(snapshot.get("metrics_json") if isinstance(snapshot.get("metrics_json"), dict) else {}),
        }

    @staticmethod
    def snapshot_to_performance(snapshot: dict[str, Any]) -> dict[str, Any] | None:
        payload = snapshot.get("performance_json")
        if not isinstance(payload, dict):
            return None
        return deepcopy(payload)

    def _delete_stale_wallet_snapshots(self, *, wallet_address: str, active_runtime_ids: list[str]) -> None:
        existing_rows = self._supabase.select(
            "bot_runtime_snapshots",
            columns="runtime_id",
            filters={"wallet_address": wallet_address},
        )
        active_ids = set(active_runtime_ids)
        for row in existing_rows:
            runtime_id = str(row.get("runtime_id") or "").strip()
            if runtime_id and runtime_id not in active_ids:
                self._supabase.delete("bot_runtime_snapshots", filters={"runtime_id": runtime_id})
