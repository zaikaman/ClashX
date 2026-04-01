from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any


def _resolve_timestamp(value: str | None = None) -> str:
    if isinstance(value, str) and value.strip():
        return value
    return datetime.now(tz=UTC).isoformat()


def _fallback_display_name(wallet_address: str) -> str:
    trimmed = wallet_address.strip()
    if len(trimmed) <= 10:
        return trimmed
    return f"{trimmed[:6]}...{trimmed[-4:]}"


def _slugify(value: str) -> str:
    lowered = re.sub(r"[^a-z0-9]+", "-", value.strip().lower())
    return lowered.strip("-")


@dataclass(frozen=True, slots=True)
class CreatorMarketplaceProfileRecord:
    id: str
    user_id: str
    display_name: str
    slug: str
    headline: str
    bio: str
    social_links_json: dict[str, Any]
    featured_collection_title: str
    created_at: str
    updated_at: str

    @classmethod
    def create(
        cls,
        *,
        user_id: str,
        wallet_address: str,
        display_name: str | None = None,
        slug: str | None = None,
        headline: str | None = None,
        bio: str | None = None,
        social_links_json: dict[str, Any] | None = None,
        featured_collection_title: str | None = None,
        created_at: str | None = None,
    ) -> "CreatorMarketplaceProfileRecord":
        timestamp = _resolve_timestamp(created_at)
        resolved_display_name = (display_name or _fallback_display_name(wallet_address)).strip() or _fallback_display_name(
            wallet_address
        )
        resolved_slug = _slugify(slug or resolved_display_name or wallet_address)
        return cls(
            id=str(uuid.uuid4()),
            user_id=user_id,
            display_name=resolved_display_name,
            slug=resolved_slug or str(uuid.uuid4()),
            headline=(headline or "Publishing live strategies with clear guardrails.").strip(),
            bio=(bio or "").strip(),
            social_links_json=social_links_json if isinstance(social_links_json, dict) else {},
            featured_collection_title=(featured_collection_title or "Featured strategies").strip(),
            created_at=timestamp,
            updated_at=timestamp,
        )

    def to_row(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "display_name": self.display_name,
            "slug": self.slug,
            "headline": self.headline,
            "bio": self.bio,
            "social_links_json": self.social_links_json,
            "featured_collection_title": self.featured_collection_title,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
