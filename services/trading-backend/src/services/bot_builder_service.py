from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from src.core.settings import get_settings
from src.models.bot_definition import BotDefinition
from src.models.bot_execution_event import BotExecutionEvent
from src.models.bot_runtime import BotRuntime
from src.models.user import User
from src.services.rules_engine import RulesEngine
from src.services.supabase_rest import SupabaseRestClient


class BotBuilderService:
    VALID_AUTHORING_MODES = {"visual"}
    VALID_VISIBILITY = {"private", "public", "unlisted"}

    def __init__(self, rules_engine: RulesEngine | None = None) -> None:
        self.settings = get_settings()
        self.supabase = SupabaseRestClient() if self.settings.use_supabase_api else None
        self.rules_engine = rules_engine or RulesEngine()

    def list_bots(self, db: Session, *, wallet_address: str) -> list[dict]:
        if self.settings.use_supabase_api:
            assert self.supabase is not None
            rows = self.supabase.select(
                "bot_definitions",
                filters={"wallet_address": wallet_address},
                order="updated_at.desc",
            )
            return [self.serialize(row) for row in rows]
        rows = list(
            db.scalars(
                select(BotDefinition)
                .where(BotDefinition.wallet_address == wallet_address)
                .order_by(desc(BotDefinition.updated_at))
            ).all()
        )
        return [self.serialize(row) for row in rows]

    def get_bot(self, db: Session, *, bot_id: str, wallet_address: str) -> dict:
        if self.settings.use_supabase_api:
            assert self.supabase is not None
            bot = self.supabase.maybe_one(
                "bot_definitions",
                filters={"id": bot_id, "wallet_address": wallet_address},
            )
            if bot is None:
                raise ValueError("Bot not found")
            return self.serialize(bot)
        bot = db.scalar(
            select(BotDefinition)
            .where(BotDefinition.id == bot_id, BotDefinition.wallet_address == wallet_address)
            .limit(1)
        )
        if bot is None:
            raise ValueError("Bot not found")
        return self.serialize(bot)

    def create_bot(
        self,
        db: Session,
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
        user = self._find_or_create_user(db, wallet_address=wallet_address)

        issues = self.validate_definition(
            authoring_mode=authoring_mode,
            visibility=visibility,
            rules_version=rules_version,
            rules_json=rules_json,
        )
        if issues:
            raise ValueError("Invalid bot definition: " + "; ".join(issues))

        if self.settings.use_supabase_api:
            user = self._find_or_create_user(db, wallet_address=wallet_address)
            now = datetime.now(tz=UTC).isoformat()
            assert self.supabase is not None
            payload = {
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
            }
            row = self.supabase.insert("bot_definitions", payload)[0]
            return self.serialize(row)

        now = datetime.now(tz=UTC)
        bot = BotDefinition(
            user_id=user.id,
            wallet_address=wallet_address,
            name=name.strip(),
            description=description.strip(),
            visibility=visibility,
            market_scope=market_scope.strip(),
            strategy_type=strategy_type.strip(),
            authoring_mode=authoring_mode,
            rules_version=rules_version,
            rules_json=rules_json,
            updated_at=now,
        )
        db.add(bot)
        db.commit()
        db.refresh(bot)
        return self.serialize(bot)

    @staticmethod
    def _serialize_user(user: User | dict) -> dict:
        if isinstance(user, dict):
            return user
        return {
            "id": user.id,
            "wallet_address": user.wallet_address,
            "display_name": user.display_name,
            "auth_provider": user.auth_provider,
            "created_at": user.created_at,
        }

    def _find_or_create_user(self, db: Session, *, wallet_address: str) -> User | dict:
        if self.settings.use_supabase_api:
            assert self.supabase is not None
            user = self.supabase.maybe_one("users", filters={"wallet_address": wallet_address})
            if user is None:
                payload = {
                    "id": str(uuid.uuid4()),
                    "wallet_address": wallet_address,
                    "display_name": wallet_address[:8],
                    "auth_provider": "privy",
                    "created_at": datetime.now(tz=UTC).isoformat(),
                }
                user = self.supabase.insert("users", payload, upsert=True, on_conflict="wallet_address")[0]
            return user

        user = db.scalar(select(User).where(User.wallet_address == wallet_address).limit(1))
        if user is None:
            user = User(wallet_address=wallet_address, display_name=wallet_address[:8])
            db.add(user)
            db.flush()
        return user

    def update_bot(
        self,
        db: Session,
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
        if self.settings.use_supabase_api:
            assert self.supabase is not None
            bot = self.supabase.maybe_one(
                "bot_definitions",
                filters={"id": bot_id, "wallet_address": wallet_address},
            )
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

            values = {
                "name": next_payload["name"],
                "description": next_payload["description"],
                "visibility": next_payload["visibility"],
                "market_scope": next_payload["market_scope"],
                "strategy_type": next_payload["strategy_type"],
                "authoring_mode": next_payload["authoring_mode"],
                "rules_version": next_payload["rules_version"],
                "rules_json": next_payload["rules_json"],
                "updated_at": datetime.now(tz=UTC).isoformat(),
            }
            row = self.supabase.update("bot_definitions", values, filters={"id": bot_id})[0]
            return self.serialize(row)

        bot = db.scalar(
            select(BotDefinition)
            .where(BotDefinition.id == bot_id, BotDefinition.wallet_address == wallet_address)
            .limit(1)
        )
        if bot is None:
            raise ValueError("Bot not found")

        if name is not None:
            bot.name = name.strip()
        if description is not None:
            bot.description = description.strip()
        if visibility is not None:
            bot.visibility = visibility
        if market_scope is not None:
            bot.market_scope = market_scope.strip()
        if strategy_type is not None:
            bot.strategy_type = strategy_type.strip()
        if authoring_mode is not None:
            bot.authoring_mode = authoring_mode
        if rules_version is not None:
            bot.rules_version = rules_version
        if rules_json is not None:
            bot.rules_json = rules_json

        issues = self.validate_definition(
            authoring_mode=bot.authoring_mode,
            visibility=bot.visibility,
            rules_version=bot.rules_version,
            rules_json=bot.rules_json,
        )
        if issues:
            raise ValueError("Invalid bot definition: " + "; ".join(issues))

        bot.updated_at = datetime.now(tz=UTC)
        db.commit()
        db.refresh(bot)
        return self.serialize(bot)

    def delete_bot(self, db: Session, *, bot_id: str, wallet_address: str) -> None:
        if self.settings.use_supabase_api:
            assert self.supabase is not None
            bot = self.supabase.maybe_one(
                "bot_definitions",
                filters={"id": bot_id, "wallet_address": wallet_address},
            )
            if bot is None:
                raise ValueError("Bot not found")

            runtime = self.supabase.maybe_one(
                "bot_runtimes",
                filters={"bot_definition_id": bot_id, "wallet_address": wallet_address},
            )
            if runtime is not None and runtime.get("status") in {"active", "paused"}:
                raise ValueError("Stop the runtime before deleting this bot.")

            if runtime is not None:
                self.supabase.delete("bot_execution_events", filters={"runtime_id": runtime["id"]})
                self.supabase.delete("bot_runtimes", filters={"id": runtime["id"]})

            self.supabase.delete("bot_definitions", filters={"id": bot_id, "wallet_address": wallet_address})
            return

        bot = db.scalar(
            select(BotDefinition)
            .where(BotDefinition.id == bot_id, BotDefinition.wallet_address == wallet_address)
            .limit(1)
        )
        if bot is None:
            raise ValueError("Bot not found")

        runtime = db.scalar(
            select(BotRuntime)
            .where(
                BotRuntime.bot_definition_id == bot.id,
                BotRuntime.wallet_address == wallet_address,
            )
            .limit(1)
        )
        if runtime is not None and runtime.status in {"active", "paused"}:
            raise ValueError("Stop the runtime before deleting this bot.")

        if runtime is not None:
            events = list(
                db.scalars(select(BotExecutionEvent).where(BotExecutionEvent.runtime_id == runtime.id)).all()
            )
            for event in events:
                db.delete(event)
            db.delete(runtime)

        db.delete(bot)
        db.commit()

    def validate_definition(
        self,
        *,
        authoring_mode: str,
        visibility: str,
        rules_version: int,
        rules_json: dict,
    ) -> list[str]:
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

    @staticmethod
    def serialize(bot: BotDefinition | dict) -> dict:
        if isinstance(bot, dict):
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
        return {
            "id": bot.id,
            "user_id": bot.user_id,
            "wallet_address": bot.wallet_address,
            "name": bot.name,
            "description": bot.description,
            "visibility": bot.visibility,
            "market_scope": bot.market_scope,
            "strategy_type": bot.strategy_type,
            "authoring_mode": bot.authoring_mode,
            "rules_version": bot.rules_version,
            "rules_json": bot.rules_json,
            "created_at": bot.created_at,
            "updated_at": bot.updated_at,
        }
