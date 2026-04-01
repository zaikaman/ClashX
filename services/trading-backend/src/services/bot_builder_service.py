from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from src.models import BotPublishSnapshotRecord, BotStrategyVersionRecord
from src.services.rules_engine import RulesEngine
from src.services.supabase_rest import SupabaseRestClient, SupabaseRestError


class BotBuilderService:
    VALID_AUTHORING_MODES = {"visual"}
    VALID_VISIBILITY = {"private", "public", "unlisted", "invite_only"}
    STRATEGY_VERSION_FIELDS = (
        "name",
        "description",
        "visibility",
        "market_scope",
        "strategy_type",
        "authoring_mode",
        "rules_version",
        "rules_json",
    )
    RUNTIME_DEPENDENT_TABLES = (
        "bot_execution_events",
        "bot_action_claims",
        "bot_trade_sync_state",
        "bot_trade_closures",
        "bot_trade_lots",
        "bot_leaderboard_snapshots",
        "bot_copy_relationships",
    )

    def __init__(self, rules_engine: RulesEngine | None = None) -> None:
        self.supabase = SupabaseRestClient()
        self.rules_engine = rules_engine or RulesEngine()

    def list_bots(self, db: Any, *, wallet_address: str) -> list[dict]:
        del db
        rows = self.supabase.select(
            "bot_definitions",
            columns="id,wallet_address,name,description,visibility,market_scope,strategy_type,authoring_mode,updated_at",
            filters={"wallet_address": wallet_address},
            order="updated_at.desc",
        )
        return [self.serialize_summary(row) for row in rows]

    def get_bot(self, db: Any, *, bot_id: str, wallet_address: str) -> dict:
        del db
        bot = self.supabase.maybe_one("bot_definitions", filters={"id": bot_id, "wallet_address": wallet_address})
        if bot is None:
            raise ValueError("Bot not found")
        return self.serialize(bot)

    def create_bot(
        self,
        db: Any,
        *,
        wallet_address: str,
        name: str,
        description: str,
        visibility: str,
        market_scope: str,
        strategy_type: str,
        authoring_mode: str,
        rules_version: int,
        rules_json: dict,
    ) -> dict:
        del db
        issues = self.validate_definition(
            authoring_mode=authoring_mode,
            visibility=visibility,
            rules_version=rules_version,
            rules_json=rules_json,
        )
        if issues:
            raise ValueError("Invalid bot definition: " + "; ".join(issues))
        user = self._find_or_create_user(wallet_address=wallet_address)
        now = datetime.now(tz=UTC).isoformat()
        row = self.supabase.insert(
            "bot_definitions",
            {
                "id": str(uuid.uuid4()),
                "user_id": user["id"],
                "wallet_address": wallet_address,
                "name": name.strip(),
                "description": description.strip(),
                "visibility": visibility,
                "market_scope": market_scope.strip(),
                "strategy_type": strategy_type.strip(),
                "authoring_mode": authoring_mode,
                "rules_version": rules_version,
                "rules_json": rules_json,
                "created_at": now,
                "updated_at": now,
            },
        )[0]
        self._record_strategy_history(bot=row, created_by_user_id=user["id"], previous_bot=None)
        return self.serialize(row)

    def update_bot(
        self,
        db: Any,
        *,
        bot_id: str,
        wallet_address: str,
        name: str | None = None,
        description: str | None = None,
        visibility: str | None = None,
        market_scope: str | None = None,
        strategy_type: str | None = None,
        authoring_mode: str | None = None,
        rules_version: int | None = None,
        rules_json: dict | None = None,
    ) -> dict:
        del db
        bot = self.supabase.maybe_one("bot_definitions", filters={"id": bot_id, "wallet_address": wallet_address})
        if bot is None:
            raise ValueError("Bot not found")
        next_payload = dict(bot)
        if name is not None:
            next_payload["name"] = name.strip()
        if description is not None:
            next_payload["description"] = description.strip()
        if visibility is not None:
            next_payload["visibility"] = visibility
        if market_scope is not None:
            next_payload["market_scope"] = market_scope.strip()
        if strategy_type is not None:
            next_payload["strategy_type"] = strategy_type.strip()
        if authoring_mode is not None:
            next_payload["authoring_mode"] = authoring_mode
        if rules_version is not None:
            next_payload["rules_version"] = rules_version
        if rules_json is not None:
            next_payload["rules_json"] = rules_json
        issues = self.validate_definition(
            authoring_mode=str(next_payload["authoring_mode"]),
            visibility=str(next_payload["visibility"]),
            rules_version=int(next_payload["rules_version"]),
            rules_json=next_payload["rules_json"],
        )
        if issues:
            raise ValueError("Invalid bot definition: " + "; ".join(issues))
        row = self.supabase.update(
            "bot_definitions",
            {
                "name": next_payload["name"],
                "description": next_payload["description"],
                "visibility": next_payload["visibility"],
                "market_scope": next_payload["market_scope"],
                "strategy_type": next_payload["strategy_type"],
                "authoring_mode": next_payload["authoring_mode"],
                "rules_version": next_payload["rules_version"],
                "rules_json": next_payload["rules_json"],
                "updated_at": datetime.now(tz=UTC).isoformat(),
            },
            filters={"id": bot_id},
        )[0]
        self._record_strategy_history(bot=row, created_by_user_id=str(bot["user_id"]), previous_bot=bot)
        return self.serialize(row)

    def delete_bot(self, db: Any, *, bot_id: str, wallet_address: str) -> None:
        del db
        bot = self.supabase.maybe_one("bot_definitions", filters={"id": bot_id, "wallet_address": wallet_address})
        if bot is None:
            raise ValueError("Bot not found")
        runtimes = self.supabase.select("bot_runtimes", filters={"bot_definition_id": bot_id, "wallet_address": wallet_address})
        if any(runtime.get("status") in {"active", "paused"} for runtime in runtimes):
            raise ValueError("Stop the runtime before deleting this bot.")
        for runtime in runtimes:
            self._delete_runtime_dependencies(runtime_id=runtime["id"])
            self.supabase.delete("bot_runtimes", filters={"id": runtime["id"]})
        self.supabase.delete("bot_definitions", filters={"id": bot_id, "wallet_address": wallet_address})

    def _delete_runtime_dependencies(self, *, runtime_id: str) -> None:
        for table in self.RUNTIME_DEPENDENT_TABLES:
            self.supabase.delete(table, filters={"runtime_id" if table != "bot_copy_relationships" else "source_runtime_id": runtime_id})

    def validate_definition(self, *, authoring_mode: str, visibility: str, rules_version: int, rules_json: dict) -> list[str]:
        issues: list[str] = []
        if authoring_mode not in self.VALID_AUTHORING_MODES:
            issues.append("authoring_mode must be visual")
        if visibility not in self.VALID_VISIBILITY:
            issues.append("visibility must be one of private|public|unlisted|invite_only")
        if rules_version < 1:
            issues.append("rules_version must be >= 1")
        if not isinstance(rules_json, dict):
            issues.append("rules_json must be an object")
        if authoring_mode == "visual" and isinstance(rules_json, dict):
            issues.extend(self.rules_engine.validation_issues(rules_json=rules_json))
        return issues

    def list_strategy_versions(self, *, bot_id: str, limit: int = 8) -> list[dict[str, Any]]:
        try:
            rows = self.supabase.select(
                "bot_strategy_versions",
                filters={"bot_definition_id": bot_id},
                order="version_number.desc",
                limit=limit,
            )
        except SupabaseRestError:
            rows = []
        if rows:
            return [self.serialize_strategy_version(row) for row in rows]

        bot = self.supabase.maybe_one("bot_definitions", filters={"id": bot_id})
        if bot is None:
            return []
        synthesized = BotStrategyVersionRecord.from_bot(
            bot,
            created_by_user_id=str(bot.get("user_id") or ""),
            version_number=max(1, int(bot.get("rules_version") or 1)),
            change_kind="bootstrap",
            created_at=str(bot.get("updated_at") or bot.get("created_at") or datetime.now(tz=UTC).isoformat()),
        )
        return [synthesized.to_summary()]

    def list_publish_snapshots(self, *, bot_id: str, limit: int = 8) -> list[dict[str, Any]]:
        try:
            rows = self.supabase.select(
                "bot_publish_snapshots",
                filters={"bot_definition_id": bot_id},
                order="created_at.desc",
                limit=limit,
            )
        except SupabaseRestError:
            rows = []
        if rows:
            return [self.serialize_publish_snapshot(row) for row in rows]

        bot = self.supabase.maybe_one("bot_definitions", filters={"id": bot_id})
        if bot is None or str(bot.get("visibility") or "private") == "private":
            return []
        synthesized = BotPublishSnapshotRecord.from_version(
            bot=bot,
            strategy_version_id="bootstrap",
            created_at=str(bot.get("updated_at") or bot.get("created_at") or datetime.now(tz=UTC).isoformat()),
        )
        return [self.serialize_publish_snapshot(synthesized.to_row())]

    def _record_strategy_history(
        self,
        *,
        bot: dict[str, Any],
        created_by_user_id: str,
        previous_bot: dict[str, Any] | None,
    ) -> None:
        if previous_bot is not None and not self._strategy_history_changed(previous_bot=previous_bot, next_bot=bot):
            return

        try:
            latest = self.supabase.maybe_one(
                "bot_strategy_versions",
                columns="version_number",
                filters={"bot_definition_id": bot["id"]},
                order="version_number.desc",
            )
        except SupabaseRestError:
            return

        version_number = int(latest["version_number"]) + 1 if latest is not None else 1
        created_at = str(bot.get("updated_at") or bot.get("created_at") or datetime.now(tz=UTC).isoformat())
        record = BotStrategyVersionRecord.from_bot(
            bot,
            created_by_user_id=created_by_user_id,
            version_number=version_number,
            change_kind=self._resolve_change_kind(previous_bot=previous_bot, next_bot=bot),
            created_at=created_at,
        )
        try:
            inserted = self.supabase.insert("bot_strategy_versions", record.to_row())[0]
        except SupabaseRestError:
            return
        if not record.is_public_release:
            return
        publish_record = BotPublishSnapshotRecord.from_version(
            bot=bot,
            strategy_version_id=str(inserted["id"]),
            created_at=created_at,
        )
        try:
            self.supabase.insert("bot_publish_snapshots", publish_record.to_row())
        except SupabaseRestError:
            return

    def _strategy_history_changed(self, *, previous_bot: dict[str, Any], next_bot: dict[str, Any]) -> bool:
        return any(previous_bot.get(field) != next_bot.get(field) for field in self.STRATEGY_VERSION_FIELDS)

    @staticmethod
    def _resolve_change_kind(*, previous_bot: dict[str, Any] | None, next_bot: dict[str, Any]) -> str:
        if previous_bot is None:
            return "created"
        if previous_bot.get("visibility") != next_bot.get("visibility"):
            return "visibility"
        if previous_bot.get("rules_json") != next_bot.get("rules_json"):
            return "logic"
        if previous_bot.get("market_scope") != next_bot.get("market_scope"):
            return "market_scope"
        if previous_bot.get("strategy_type") != next_bot.get("strategy_type"):
            return "strategy_type"
        return "revision"

    def _find_or_create_user(self, *, wallet_address: str) -> dict[str, Any]:
        user = self.supabase.maybe_one("users", filters={"wallet_address": wallet_address})
        if user is not None:
            return user
        return self.supabase.insert(
            "users",
            {
                "id": str(uuid.uuid4()),
                "wallet_address": wallet_address,
                "display_name": wallet_address[:8],
                "auth_provider": "privy",
                "created_at": datetime.now(tz=UTC).isoformat(),
            },
            upsert=True,
            on_conflict="wallet_address",
        )[0]

    @staticmethod
    def serialize(bot: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": bot["id"],
            "user_id": bot["user_id"],
            "wallet_address": bot["wallet_address"],
            "name": bot["name"],
            "description": bot["description"],
            "visibility": bot["visibility"],
            "market_scope": bot["market_scope"],
            "strategy_type": bot["strategy_type"],
            "authoring_mode": bot["authoring_mode"],
            "rules_version": bot["rules_version"],
            "rules_json": bot["rules_json"],
            "created_at": bot["created_at"],
            "updated_at": bot["updated_at"],
        }

    @staticmethod
    def serialize_summary(bot: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": bot["id"],
            "wallet_address": bot["wallet_address"],
            "name": bot["name"],
            "description": bot["description"],
            "visibility": bot["visibility"],
            "market_scope": bot["market_scope"],
            "strategy_type": bot["strategy_type"],
            "authoring_mode": bot["authoring_mode"],
            "updated_at": bot["updated_at"],
        }

    @staticmethod
    def serialize_strategy_version(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": row["id"],
            "bot_definition_id": row["bot_definition_id"],
            "version_number": int(row.get("version_number") or 1),
            "change_kind": row.get("change_kind") or "revision",
            "visibility_snapshot": row.get("visibility_snapshot") or "private",
            "name_snapshot": row.get("name_snapshot") or "",
            "is_public_release": bool(row.get("is_public_release")),
            "created_at": row["created_at"],
            "label": f"v{int(row.get('version_number') or 1)}",
        }

    @staticmethod
    def serialize_publish_snapshot(row: dict[str, Any]) -> dict[str, Any]:
        summary = row.get("summary_json") if isinstance(row.get("summary_json"), dict) else {}
        return {
            "id": row["id"],
            "bot_definition_id": row["bot_definition_id"],
            "strategy_version_id": row.get("strategy_version_id"),
            "runtime_id": row.get("runtime_id"),
            "visibility_snapshot": row.get("visibility_snapshot") or "private",
            "publish_state": row.get("publish_state") or "published",
            "summary_json": summary,
            "created_at": row["created_at"],
        }
