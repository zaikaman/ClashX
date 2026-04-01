from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any


def _resolve_created_at(value: str | None = None) -> str:
    if isinstance(value, str) and value.strip():
        return value
    return datetime.now(tz=UTC).isoformat()


@dataclass(frozen=True, slots=True)
class BotStrategyVersionRecord:
    id: str
    bot_definition_id: str
    created_by_user_id: str
    version_number: int
    change_kind: str
    visibility_snapshot: str
    name_snapshot: str
    description_snapshot: str
    market_scope_snapshot: str
    strategy_type_snapshot: str
    authoring_mode_snapshot: str
    rules_version_snapshot: int
    rules_json_snapshot: dict[str, Any]
    is_public_release: bool
    created_at: str

    @classmethod
    def from_bot(
        cls,
        bot: dict[str, Any],
        *,
        created_by_user_id: str,
        version_number: int,
        change_kind: str,
        created_at: str | None = None,
    ) -> "BotStrategyVersionRecord":
        visibility = str(bot.get("visibility") or "private")
        return cls(
            id=str(uuid.uuid4()),
            bot_definition_id=str(bot["id"]),
            created_by_user_id=created_by_user_id,
            version_number=max(1, int(version_number)),
            change_kind=change_kind.strip() or "revision",
            visibility_snapshot=visibility,
            name_snapshot=str(bot.get("name") or "").strip(),
            description_snapshot=str(bot.get("description") or "").strip(),
            market_scope_snapshot=str(bot.get("market_scope") or "").strip(),
            strategy_type_snapshot=str(bot.get("strategy_type") or "").strip(),
            authoring_mode_snapshot=str(bot.get("authoring_mode") or "").strip(),
            rules_version_snapshot=max(1, int(bot.get("rules_version") or 1)),
            rules_json_snapshot=bot.get("rules_json") if isinstance(bot.get("rules_json"), dict) else {},
            is_public_release=visibility in {"public", "unlisted", "invite_only"},
            created_at=_resolve_created_at(created_at),
        )

    def to_row(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "bot_definition_id": self.bot_definition_id,
            "created_by_user_id": self.created_by_user_id,
            "version_number": self.version_number,
            "change_kind": self.change_kind,
            "visibility_snapshot": self.visibility_snapshot,
            "name_snapshot": self.name_snapshot,
            "description_snapshot": self.description_snapshot,
            "market_scope_snapshot": self.market_scope_snapshot,
            "strategy_type_snapshot": self.strategy_type_snapshot,
            "authoring_mode_snapshot": self.authoring_mode_snapshot,
            "rules_version_snapshot": self.rules_version_snapshot,
            "rules_json_snapshot": self.rules_json_snapshot,
            "is_public_release": self.is_public_release,
            "created_at": self.created_at,
        }

    def to_summary(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "bot_definition_id": self.bot_definition_id,
            "version_number": self.version_number,
            "change_kind": self.change_kind,
            "visibility_snapshot": self.visibility_snapshot,
            "name_snapshot": self.name_snapshot,
            "is_public_release": self.is_public_release,
            "created_at": self.created_at,
            "label": f"v{self.version_number}",
        }
