from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any


def _resolve_timestamp(value: str | None = None) -> str:
    if isinstance(value, str) and value.strip():
        return value
    return datetime.now(tz=UTC).isoformat()


def _publish_state_for_visibility(visibility: str) -> str:
    normalized = visibility.strip() or "private"
    if normalized == "public":
        return "published"
    if normalized == "unlisted":
        return "unlisted"
    if normalized == "invite_only":
        return "invite_only"
    return "draft"


@dataclass(frozen=True, slots=True)
class BotPublishingSettingsRecord:
    id: str
    bot_definition_id: str
    user_id: str
    visibility: str
    access_mode: str
    publish_state: str
    listed_at: str | None
    hero_headline: str
    access_note: str
    featured_collection_key: str | None
    featured_collection_title: str | None
    featured_rank: int
    created_at: str
    updated_at: str

    @classmethod
    def create(
        cls,
        *,
        bot_definition_id: str,
        user_id: str,
        visibility: str,
        hero_headline: str | None = None,
        access_note: str | None = None,
        featured_collection_key: str | None = None,
        featured_collection_title: str | None = None,
        featured_rank: int = 0,
        created_at: str | None = None,
    ) -> "BotPublishingSettingsRecord":
        timestamp = _resolve_timestamp(created_at)
        publish_state = _publish_state_for_visibility(visibility)
        return cls(
            id=str(uuid.uuid4()),
            bot_definition_id=bot_definition_id,
            user_id=user_id,
            visibility=visibility.strip() or "private",
            access_mode=visibility.strip() or "private",
            publish_state=publish_state,
            listed_at=timestamp if publish_state in {"published", "unlisted", "invite_only"} else None,
            hero_headline=(hero_headline or "").strip(),
            access_note=(access_note or "").strip(),
            featured_collection_key=(featured_collection_key or "").strip() or None,
            featured_collection_title=(featured_collection_title or "").strip() or None,
            featured_rank=max(0, int(featured_rank)),
            created_at=timestamp,
            updated_at=timestamp,
        )

    def to_row(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "bot_definition_id": self.bot_definition_id,
            "user_id": self.user_id,
            "visibility": self.visibility,
            "access_mode": self.access_mode,
            "publish_state": self.publish_state,
            "listed_at": self.listed_at,
            "hero_headline": self.hero_headline,
            "access_note": self.access_note,
            "featured_collection_key": self.featured_collection_key,
            "featured_collection_title": self.featured_collection_title,
            "featured_rank": self.featured_rank,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
