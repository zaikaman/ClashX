from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any


def _resolve_timestamp(value: str | None = None) -> str:
    if isinstance(value, str) and value.strip():
        return value
    return datetime.now(tz=UTC).isoformat()


@dataclass(frozen=True, slots=True)
class FeaturedBotRecord:
    id: str
    creator_profile_id: str
    bot_definition_id: str
    collection_key: str
    collection_title: str
    shelf_rank: int
    featured_reason: str
    active: bool
    created_at: str
    updated_at: str

    @classmethod
    def create(
        cls,
        *,
        creator_profile_id: str,
        bot_definition_id: str,
        collection_key: str,
        collection_title: str,
        shelf_rank: int = 0,
        featured_reason: str | None = None,
        created_at: str | None = None,
    ) -> "FeaturedBotRecord":
        timestamp = _resolve_timestamp(created_at)
        return cls(
            id=str(uuid.uuid4()),
            creator_profile_id=creator_profile_id,
            bot_definition_id=bot_definition_id,
            collection_key=collection_key.strip() or "featured",
            collection_title=collection_title.strip() or "Featured strategies",
            shelf_rank=max(0, int(shelf_rank)),
            featured_reason=(featured_reason or "").strip(),
            active=True,
            created_at=timestamp,
            updated_at=timestamp,
        )

    def to_row(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "creator_profile_id": self.creator_profile_id,
            "bot_definition_id": self.bot_definition_id,
            "collection_key": self.collection_key,
            "collection_title": self.collection_title,
            "shelf_rank": self.shelf_rank,
            "featured_reason": self.featured_reason,
            "active": self.active,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
