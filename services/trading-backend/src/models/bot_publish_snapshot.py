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
class BotPublishSnapshotRecord:
    id: str
    bot_definition_id: str
    strategy_version_id: str
    runtime_id: str | None
    visibility_snapshot: str
    publish_state: str
    summary_json: dict[str, Any]
    created_at: str

    @classmethod
    def from_version(
        cls,
        *,
        bot: dict[str, Any],
        strategy_version_id: str,
        runtime_id: str | None = None,
        created_at: str | None = None,
    ) -> "BotPublishSnapshotRecord":
        visibility = str(bot.get("visibility") or "private")
        return cls(
            id=str(uuid.uuid4()),
            bot_definition_id=str(bot["id"]),
            strategy_version_id=strategy_version_id,
            runtime_id=runtime_id,
            visibility_snapshot=visibility,
            publish_state="published" if visibility == "public" else "invite_only" if visibility == "invite_only" else "preview",
            summary_json={
                "name": str(bot.get("name") or "").strip(),
                "description": str(bot.get("description") or "").strip(),
                "market_scope": str(bot.get("market_scope") or "").strip(),
                "strategy_type": str(bot.get("strategy_type") or "").strip(),
                "authoring_mode": str(bot.get("authoring_mode") or "").strip(),
            },
            created_at=_resolve_created_at(created_at),
        )

    def to_row(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "bot_definition_id": self.bot_definition_id,
            "strategy_version_id": self.strategy_version_id,
            "runtime_id": self.runtime_id,
            "visibility_snapshot": self.visibility_snapshot,
            "publish_state": self.publish_state,
            "summary_json": self.summary_json,
            "created_at": self.created_at,
        }
