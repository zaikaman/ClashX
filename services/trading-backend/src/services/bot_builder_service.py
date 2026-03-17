from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from src.services.rules_engine import RulesEngine
from src.services.supabase_rest import SupabaseRestClient


class BotBuilderService:
    VALID_AUTHORING_MODES = {"visual"}
    VALID_VISIBILITY = {"private", "public", "unlisted"}

    def __init__(self, rules_engine: RulesEngine | None = None) -> None:
        self.supabase = SupabaseRestClient()
        self.rules_engine = rules_engine or RulesEngine()

    def list_bots(self, db: Any, *, wallet_address: str) -> list[dict]:
        del db
        rows = self.supabase.select("bot_definitions", filters={"wallet_address": wallet_address}, order="updated_at.desc")
        return [self.serialize(row) for row in rows]

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
        return self.serialize(row)

    def delete_bot(self, db: Any, *, bot_id: str, wallet_address: str) -> None:
        del db
        bot = self.supabase.maybe_one("bot_definitions", filters={"id": bot_id, "wallet_address": wallet_address})
        if bot is None:
            raise ValueError("Bot not found")
        runtime = self.supabase.maybe_one("bot_runtimes", filters={"bot_definition_id": bot_id, "wallet_address": wallet_address})
        if runtime is not None and runtime.get("status") in {"active", "paused"}:
            raise ValueError("Stop the runtime before deleting this bot.")
        if runtime is not None:
            self.supabase.delete("bot_execution_events", filters={"runtime_id": runtime["id"]})
            self.supabase.delete("bot_action_claims", filters={"runtime_id": runtime["id"]})
            self.supabase.delete("bot_runtimes", filters={"id": runtime["id"]})
        self.supabase.delete("bot_definitions", filters={"id": bot_id, "wallet_address": wallet_address})

    def validate_definition(self, *, authoring_mode: str, visibility: str, rules_version: int, rules_json: dict) -> list[str]:
        issues: list[str] = []
        if authoring_mode not in self.VALID_AUTHORING_MODES:
            issues.append("authoring_mode must be visual")
        if visibility not in self.VALID_VISIBILITY:
            issues.append("visibility must be one of private|public|unlisted")
        if rules_version < 1:
            issues.append("rules_version must be >= 1")
        if not isinstance(rules_json, dict):
            issues.append("rules_json must be an object")
        if authoring_mode == "visual" and isinstance(rules_json, dict):
            issues.extend(self.rules_engine.validation_issues(rules_json=rules_json))
        return issues

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
