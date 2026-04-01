from __future__ import annotations

import re
import uuid
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

from src.models import (
    BotInviteAccessRecord,
    BotPublishingSettingsRecord,
    CreatorMarketplaceProfileRecord,
    FeaturedBotRecord,
)
from src.services.bot_builder_service import BotBuilderService
from src.services.bot_leaderboard_engine import BotLeaderboardEngine
from src.services.bot_trust_service import BotTrustService
from src.services.supabase_rest import SupabaseRestClient, SupabaseRestError


SNAPSHOT_TTL_SECONDS = 60
VALID_VISIBILITY = {"private", "public", "unlisted", "invite_only"}


def _as_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def _slugify(value: str) -> str:
    lowered = re.sub(r"[^a-z0-9]+", "-", value.strip().lower())
    return lowered.strip("-")


class CreatorMarketplaceService:
    def __init__(self) -> None:
        self.supabase = SupabaseRestClient()
        self.builder_service = BotBuilderService()
        self.leaderboard_engine = BotLeaderboardEngine()
        self.trust_service = BotTrustService()

    async def discover_public_bots(
        self,
        *,
        limit: int = 24,
        strategy_type: str | None = None,
        creator_id: str | None = None,
    ) -> list[dict[str, Any]]:
        rows = await self._load_public_leaderboard(limit=max(limit * 3, 60))
        normalized_strategy_type = (strategy_type or "").strip().lower()
        filtered: list[dict[str, Any]] = []
        for row in rows:
            if normalized_strategy_type and str(row.get("strategy_type") or "").strip().lower() != normalized_strategy_type:
                continue
            if creator_id and str(row.get("creator", {}).get("creator_id") or "") != creator_id:
                continue
            filtered.append(self._attach_marketplace_fields(row))
            if len(filtered) >= limit:
                break
        return filtered

    async def list_featured_shelves(self, *, limit: int = 4) -> list[dict[str, Any]]:
        public_rows = await self.discover_public_bots(limit=120)
        rows_by_bot = {row["bot_definition_id"]: row for row in public_rows}
        featured_rows = self._select_featured_rows()

        grouped_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
        shelf_meta: dict[str, dict[str, Any]] = {}
        for row in featured_rows:
            bot_row = rows_by_bot.get(str(row.get("bot_definition_id") or ""))
            if bot_row is None:
                continue
            collection_key = str(row.get("collection_key") or "featured")
            grouped_rows[collection_key].append(bot_row)
            shelf_meta[collection_key] = {
                "collection_key": collection_key,
                "title": str(row.get("collection_title") or "Featured strategies"),
                "subtitle": str(row.get("featured_reason") or "Curated by creators for copy-ready discovery.").strip()
                or "Curated by creators for copy-ready discovery.",
            }

        shelves: list[dict[str, Any]] = []
        for collection_key, bots in grouped_rows.items():
            bots.sort(
                key=lambda item: (
                    -(1 if item["publishing"]["is_featured"] else 0),
                    int(item["publishing"]["featured_rank"]),
                    int(item["rank"]),
                )
            )
            meta = shelf_meta[collection_key]
            shelves.append(
                {
                    "collection_key": meta["collection_key"],
                    "title": meta["title"],
                    "subtitle": meta["subtitle"],
                    "bots": bots[:4],
                }
            )

        shelves.sort(key=lambda item: item["title"])
        if shelves:
            return shelves[:limit]

        fallback = public_rows[:4]
        if not fallback:
            return []
        return [
            {
                "collection_key": "board-spotlight",
                "title": "Board spotlight",
                "subtitle": "Live strategies with the strongest current mix of rank, trust, and creator demand.",
                "bots": fallback,
            }
        ]

    async def list_creator_highlights(self, *, limit: int = 6) -> list[dict[str, Any]]:
        public_rows = await self.discover_public_bots(limit=96)
        highlights: dict[str, dict[str, Any]] = {}
        for row in public_rows:
            creator = row["creator"]
            creator_id = str(creator["creator_id"])
            existing = highlights.get(creator_id)
            candidate = {
                **creator,
                "headline": creator.get("headline") or creator.get("summary") or "Publishing live strategies with clear guardrails.",
                "bio": creator.get("bio") or "",
                "follower_count": creator.get("follower_count") or 0,
                "featured_bot_count": creator.get("featured_bot_count") or 0,
                "marketplace_reach_score": creator.get("marketplace_reach_score") or creator.get("reputation_score") or 0,
                "spotlight_bot": {
                    "runtime_id": row["runtime_id"],
                    "bot_definition_id": row["bot_definition_id"],
                    "bot_name": row["bot_name"],
                    "rank": row["rank"],
                    "trust_score": row["trust"]["trust_score"],
                    "copy_stats": row["copy_stats"],
                },
            }
            if existing is None or candidate["marketplace_reach_score"] > existing["marketplace_reach_score"]:
                highlights[creator_id] = candidate

        ordered = sorted(
            highlights.values(),
            key=lambda item: (
                -int(item["marketplace_reach_score"]),
                -int(item["reputation_score"]),
                str(item["display_name"]),
            ),
        )
        return ordered[:limit]

    async def get_creator_profile(self, *, creator_id: str) -> dict[str, Any]:
        base_profile = self.trust_service.get_creator_profile(creator_id=creator_id, include_bots=True)
        user = self.supabase.maybe_one("users", filters={"id": creator_id})
        if user is None:
            raise ValueError("Creator not found")

        marketplace_profile = self._ensure_creator_profile(
            user=user,
            display_name=str(base_profile.get("display_name") or user.get("display_name") or user["wallet_address"][:8]),
        )
        public_rows = await self.discover_public_bots(limit=96, creator_id=creator_id)
        featured_ids = {
            str(row.get("bot_definition_id") or "")
            for row in self._select_featured_rows(filters={"creator_profile_id": marketplace_profile["id"], "active": True})
        }
        featured_bots = [row for row in public_rows if row["bot_definition_id"] in featured_ids]
        follower_count = self._count_creator_followers(creator_id=creator_id)
        featured_bot_count = len(featured_bots)
        marketplace_reach_score = self._marketplace_reach_score(
            active_mirror_count=int(base_profile["active_mirror_count"]),
            follower_count=follower_count,
            featured_bot_count=featured_bot_count,
            public_bot_count=int(base_profile["public_bot_count"]),
            reputation_score=int(base_profile["reputation_score"]),
        )
        return {
            **base_profile,
            "headline": marketplace_profile["headline"],
            "bio": marketplace_profile["bio"],
            "slug": marketplace_profile["slug"],
            "social_links_json": marketplace_profile.get("social_links_json") or {},
            "featured_collection_title": marketplace_profile["featured_collection_title"],
            "follower_count": follower_count,
            "featured_bot_count": featured_bot_count,
            "marketplace_reach_score": marketplace_reach_score,
            "bots": public_rows,
            "featured_bots": featured_bots,
        }

    def get_publishing_settings(self, *, bot_id: str, wallet_address: str) -> dict[str, Any]:
        bot = self._require_owned_bot(bot_id=bot_id, wallet_address=wallet_address)
        creator_profile = self._ensure_creator_profile_for_bot(bot)
        publishing = self._ensure_publishing_settings(bot=bot)
        invites = self._list_invites(bot_id=bot_id)
        featured_row = self.supabase.maybe_one("featured_bots", filters={"bot_definition_id": bot_id, "active": True})
        return {
            "bot_definition_id": bot["id"],
            "visibility": bot["visibility"],
            "access_mode": publishing["access_mode"],
            "publish_state": publishing["publish_state"],
            "hero_headline": publishing.get("hero_headline") or "",
            "access_note": publishing.get("access_note") or "",
            "featured_collection_title": publishing.get("featured_collection_title") or creator_profile["featured_collection_title"],
            "featured_rank": int(publishing.get("featured_rank") or 0),
            "is_featured": featured_row is not None,
            "invite_wallet_addresses": [invite["invited_wallet_address"] for invite in invites],
            "invite_count": len(invites),
            "creator_profile": {
                "display_name": creator_profile["display_name"],
                "headline": creator_profile.get("headline") or "",
                "bio": creator_profile.get("bio") or "",
                "slug": creator_profile.get("slug") or "",
                "featured_collection_title": creator_profile.get("featured_collection_title") or "Featured strategies",
            },
        }

    def update_publishing(
        self,
        *,
        bot_id: str,
        wallet_address: str,
        visibility: str,
        hero_headline: str | None,
        access_note: str | None,
        is_featured: bool,
        featured_collection_title: str | None,
        featured_rank: int,
        invite_wallet_addresses: list[str],
        creator_display_name: str | None,
        creator_headline: str | None,
        creator_bio: str | None,
    ) -> dict[str, Any]:
        normalized_visibility = visibility.strip()
        if normalized_visibility not in VALID_VISIBILITY:
            raise ValueError("visibility must be one of private|public|unlisted|invite_only")

        bot = self._require_owned_bot(bot_id=bot_id, wallet_address=wallet_address)
        if bot["visibility"] != normalized_visibility:
            bot = self.builder_service.update_bot(
                None,
                bot_id=bot_id,
                wallet_address=wallet_address,
                visibility=normalized_visibility,
            )

        user = self.supabase.maybe_one("users", filters={"id": bot["user_id"]})
        if user is None:
            raise ValueError("Creator not found")

        creator_profile = self._ensure_creator_profile(
            user=user,
            display_name=creator_display_name or user.get("display_name"),
            headline=creator_headline,
            bio=creator_bio,
            featured_collection_title=featured_collection_title,
        )
        publishing = self._upsert_publishing_settings(
            bot=bot,
            hero_headline=hero_headline,
            access_note=access_note,
            featured_collection_title=featured_collection_title,
            featured_rank=featured_rank,
        )
        self._replace_invites(
            bot_id=bot_id,
            invited_by_user_id=str(bot["user_id"]),
            invite_wallet_addresses=invite_wallet_addresses if normalized_visibility == "invite_only" else [],
        )
        self._sync_featured_row(
            bot=bot,
            creator_profile=creator_profile,
            featured_collection_title=featured_collection_title or creator_profile["featured_collection_title"],
            featured_rank=featured_rank,
            is_featured=is_featured and normalized_visibility == "public",
        )
        self.supabase.insert(
            "audit_events",
            {
                "id": str(uuid.uuid4()),
                "user_id": bot["user_id"],
                "action": "marketplace.publishing.updated",
                "payload": {
                    "bot_definition_id": bot_id,
                    "visibility": normalized_visibility,
                    "is_featured": is_featured and normalized_visibility == "public",
                    "invite_count": len(invite_wallet_addresses if normalized_visibility == "invite_only" else []),
                    "publishing_id": publishing["id"],
                },
                "created_at": datetime.now(tz=UTC).isoformat(),
            },
        )
        return self.get_publishing_settings(bot_id=bot_id, wallet_address=wallet_address)

    async def _load_public_leaderboard(self, *, limit: int) -> list[dict[str, Any]]:
        latest = self.supabase.maybe_one("bot_leaderboard_snapshots", order="captured_at.desc")
        if latest is None or self._snapshot_is_stale(latest.get("captured_at")):
            rows = await self.leaderboard_engine.refresh_public_leaderboard(None, limit=max(limit, 60))
            return self._augment_public_rows(rows)

        snapshots = self.supabase.select(
            "bot_leaderboard_snapshots",
            filters={"captured_at": latest["captured_at"]},
            order="rank.asc",
            limit=limit,
        )
        runtime_ids = [row["runtime_id"] for row in snapshots]
        runtimes = (
            {row["id"]: row for row in self.supabase.select("bot_runtimes", filters={"id": ("in", runtime_ids)})}
            if runtime_ids
            else {}
        )
        definition_ids = [runtime["bot_definition_id"] for runtime in runtimes.values()]
        definitions = (
            {row["id"]: row for row in self.supabase.select("bot_definitions", filters={"id": ("in", definition_ids)})}
            if definition_ids
            else {}
        )
        rows: list[dict[str, Any]] = []
        for snapshot in snapshots:
            runtime = runtimes.get(snapshot["runtime_id"])
            if runtime is None:
                continue
            definition = definitions.get(runtime["bot_definition_id"])
            if definition is None or definition["visibility"] != "public":
                continue
            rows.append(
                {
                    "runtime_id": runtime["id"],
                    "bot_definition_id": definition["id"],
                    "bot_name": definition["name"],
                    "strategy_type": definition["strategy_type"],
                    "authoring_mode": definition["authoring_mode"],
                    "rank": snapshot["rank"],
                    "pnl_total": snapshot["pnl_total"],
                    "pnl_unrealized": snapshot["pnl_unrealized"],
                    "win_streak": snapshot["win_streak"],
                    "drawdown": snapshot["drawdown"],
                    "captured_at": snapshot["captured_at"],
                }
            )
        return self._augment_public_rows(rows)

    def _augment_public_rows(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not rows:
            return []
        runtime_ids = [row["runtime_id"] for row in rows]
        definition_ids = [row["bot_definition_id"] for row in rows]
        runtimes = {row["id"]: row for row in self.supabase.select("bot_runtimes", filters={"id": ("in", runtime_ids)})}
        definitions = {
            row["id"]: row for row in self.supabase.select("bot_definitions", filters={"id": ("in", definition_ids)})
        }
        creator_cache: dict[str, dict[str, Any]] = {}
        augmented: list[dict[str, Any]] = []
        for row in rows:
            runtime = runtimes.get(row["runtime_id"])
            definition = definitions.get(row["bot_definition_id"])
            if runtime is None or definition is None:
                continue
            snapshot = {
                "runtime_id": row["runtime_id"],
                "rank": row["rank"],
                "pnl_total": row["pnl_total"],
                "pnl_unrealized": row["pnl_unrealized"],
                "win_streak": row["win_streak"],
                "drawdown": row["drawdown"],
                "captured_at": row["captured_at"],
            }
            public_context = self.trust_service.build_public_runtime_context(
                runtime=runtime,
                definition=definition,
                latest_snapshot=snapshot,
            )
            creator_id = str(definition["user_id"])
            creator = creator_cache.get(creator_id)
            if creator is None:
                creator = self._augment_creator_summary(
                    self.trust_service.get_creator_profile(creator_id=creator_id, include_bots=False)
                )
                creator_cache[creator_id] = creator
            augmented.append(
                {
                    **row,
                    "trust": public_context["trust"],
                    "drift": public_context["drift"],
                    "passport": public_context["passport"],
                    "creator": creator,
                }
            )
        return augmented

    def _attach_marketplace_fields(self, row: dict[str, Any]) -> dict[str, Any]:
        invites = self._list_invites(bot_id=str(row["bot_definition_id"]))
        publishing = self._get_publishing_settings_row(bot_definition_id=str(row["bot_definition_id"]))
        is_featured = (
            self.supabase.maybe_one("featured_bots", filters={"bot_definition_id": row["bot_definition_id"], "active": True})
            is not None
        )
        return {
            **row,
            "publishing": {
                "visibility": publishing.get("visibility") or "public",
                "access_mode": publishing.get("access_mode") or "public",
                "publish_state": publishing.get("publish_state") or "published",
                "hero_headline": publishing.get("hero_headline") or "",
                "access_note": publishing.get("access_note") or "",
                "featured_collection_title": publishing.get("featured_collection_title"),
                "featured_rank": int(publishing.get("featured_rank") or 0),
                "is_featured": is_featured,
                "invite_count": len(invites),
            },
            "copy_stats": self._bot_copy_stats(
                runtime_id=str(row["runtime_id"]),
                bot_definition_id=str(row["bot_definition_id"]),
            ),
        }

    def _augment_creator_summary(self, summary: dict[str, Any]) -> dict[str, Any]:
        user = self.supabase.maybe_one("users", filters={"id": summary["creator_id"]})
        if user is None:
            return {
                **summary,
                "headline": summary.get("summary") or "",
                "bio": "",
                "slug": "",
                "featured_collection_title": "Featured strategies",
                "follower_count": 0,
                "featured_bot_count": 0,
                "marketplace_reach_score": int(summary.get("reputation_score") or 0),
            }
        profile = self._ensure_creator_profile(user=user, display_name=str(summary.get("display_name") or user["wallet_address"][:8]))
        follower_count = self._count_creator_followers(creator_id=str(summary["creator_id"]))
        featured_rows = self._select_featured_rows(filters={"creator_profile_id": profile["id"], "active": True})
        featured_bot_count = len(featured_rows)
        return {
            **summary,
            "headline": profile.get("headline") or summary.get("summary") or "",
            "bio": profile.get("bio") or "",
            "slug": profile.get("slug") or "",
            "featured_collection_title": profile.get("featured_collection_title") or "Featured strategies",
            "follower_count": follower_count,
            "featured_bot_count": featured_bot_count,
            "marketplace_reach_score": self._marketplace_reach_score(
                active_mirror_count=int(summary.get("active_mirror_count") or 0),
                follower_count=follower_count,
                featured_bot_count=featured_bot_count,
                public_bot_count=int(summary.get("public_bot_count") or 0),
                reputation_score=int(summary.get("reputation_score") or 0),
            ),
        }

    def _ensure_creator_profile_for_bot(self, bot: dict[str, Any]) -> dict[str, Any]:
        user = self.supabase.maybe_one("users", filters={"id": bot["user_id"]})
        if user is None:
            raise ValueError("Creator not found")
        return self._ensure_creator_profile(
            user=user,
            display_name=str(user.get("display_name") or bot.get("wallet_address") or "")[:80],
        )

    def _ensure_creator_profile(
        self,
        *,
        user: dict[str, Any],
        display_name: str | None = None,
        headline: str | None = None,
        bio: str | None = None,
        featured_collection_title: str | None = None,
    ) -> dict[str, Any]:
        profile = self.supabase.maybe_one("creator_marketplace_profiles", filters={"user_id": user["id"]})
        resolved_display_name = (display_name or user.get("display_name") or str(user["wallet_address"])[:8]).strip()
        if profile is None:
            record = CreatorMarketplaceProfileRecord.create(
                user_id=str(user["id"]),
                wallet_address=str(user["wallet_address"]),
                display_name=resolved_display_name,
                headline=headline,
                bio=bio,
                featured_collection_title=featured_collection_title,
            )
            row = record.to_row()
            row["slug"] = self._unique_slug(base_slug=row["slug"], user_id=str(user["id"]))
            created = self.supabase.insert("creator_marketplace_profiles", row)[0]
            if resolved_display_name != (user.get("display_name") or ""):
                self.supabase.update("users", {"display_name": resolved_display_name}, filters={"id": user["id"]})
            return created

        next_display_name = resolved_display_name or profile.get("display_name") or str(user["wallet_address"])[:8]
        values = {
            "display_name": next_display_name,
            "headline": headline if headline is not None else profile.get("headline") or "",
            "bio": bio if bio is not None else profile.get("bio") or "",
            "featured_collection_title": featured_collection_title
            if featured_collection_title is not None
            else profile.get("featured_collection_title") or "Featured strategies",
            "updated_at": datetime.now(tz=UTC).isoformat(),
        }
        requested_slug = self._unique_slug(
            base_slug=_slugify(next_display_name or profile.get("slug") or str(user["wallet_address"])),
            user_id=str(user["id"]),
            current_profile_id=str(profile["id"]),
        )
        if requested_slug:
            values["slug"] = requested_slug
        updated = self.supabase.update("creator_marketplace_profiles", values, filters={"id": profile["id"]})[0]
        if next_display_name != (user.get("display_name") or ""):
            self.supabase.update("users", {"display_name": next_display_name}, filters={"id": user["id"]})
        return updated

    def _unique_slug(self, *, base_slug: str, user_id: str, current_profile_id: str | None = None) -> str:
        candidate_base = base_slug or f"creator-{user_id[:8]}"
        candidate = candidate_base
        suffix = 1
        while True:
            conflict = self.supabase.maybe_one("creator_marketplace_profiles", filters={"slug": candidate})
            if conflict is None or str(conflict.get("id") or "") == (current_profile_id or ""):
                return candidate
            suffix += 1
            candidate = f"{candidate_base}-{suffix}"

    def _upsert_publishing_settings(
        self,
        *,
        bot: dict[str, Any],
        hero_headline: str | None,
        access_note: str | None,
        featured_collection_title: str | None,
        featured_rank: int,
    ) -> dict[str, Any]:
        existing = self._get_publishing_settings_row(bot_definition_id=str(bot["id"]))
        if existing is None:
            record = BotPublishingSettingsRecord.create(
                bot_definition_id=str(bot["id"]),
                user_id=str(bot["user_id"]),
                visibility=str(bot["visibility"]),
                hero_headline=hero_headline,
                access_note=access_note,
                featured_collection_title=featured_collection_title,
                featured_rank=featured_rank,
            )
            return self.supabase.insert("bot_publishing_settings", record.to_row())[0]

        publish_state = self._publish_state(str(bot["visibility"]))
        values = {
            "visibility": str(bot["visibility"]),
            "access_mode": str(bot["visibility"]),
            "publish_state": publish_state,
            "listed_at": existing.get("listed_at") or (datetime.now(tz=UTC).isoformat() if publish_state != "draft" else None),
            "hero_headline": (hero_headline if hero_headline is not None else existing.get("hero_headline") or "").strip(),
            "access_note": (access_note if access_note is not None else existing.get("access_note") or "").strip(),
            "featured_collection_title": (featured_collection_title if featured_collection_title is not None else existing.get("featured_collection_title") or "").strip()
            or None,
            "featured_rank": max(0, int(featured_rank)),
            "updated_at": datetime.now(tz=UTC).isoformat(),
        }
        return self.supabase.update("bot_publishing_settings", values, filters={"id": existing["id"]})[0]

    def _sync_featured_row(
        self,
        *,
        bot: dict[str, Any],
        creator_profile: dict[str, Any],
        featured_collection_title: str,
        featured_rank: int,
        is_featured: bool,
    ) -> None:
        existing = self.supabase.maybe_one("featured_bots", filters={"bot_definition_id": bot["id"]})
        if not is_featured:
            if existing is not None:
                self.supabase.update(
                    "featured_bots",
                    {"active": False, "updated_at": datetime.now(tz=UTC).isoformat()},
                    filters={"id": existing["id"]},
                )
            return

        collection_key = _slugify(featured_collection_title) or "featured"
        values = {
            "creator_profile_id": creator_profile["id"],
            "bot_definition_id": bot["id"],
            "collection_key": collection_key,
            "collection_title": featured_collection_title.strip() or creator_profile["featured_collection_title"],
            "shelf_rank": max(0, int(featured_rank)),
            "featured_reason": "",
            "active": True,
            "updated_at": datetime.now(tz=UTC).isoformat(),
        }
        if existing is None:
            record = FeaturedBotRecord.create(
                creator_profile_id=str(creator_profile["id"]),
                bot_definition_id=str(bot["id"]),
                collection_key=collection_key,
                collection_title=values["collection_title"],
                shelf_rank=featured_rank,
            )
            self.supabase.insert("featured_bots", record.to_row())
            return
        self.supabase.update("featured_bots", values, filters={"id": existing["id"]})

    def _replace_invites(
        self,
        *,
        bot_id: str,
        invited_by_user_id: str,
        invite_wallet_addresses: list[str],
    ) -> None:
        self.supabase.delete("bot_invite_access", filters={"bot_definition_id": bot_id})
        deduped: list[str] = []
        seen: set[str] = set()
        for wallet_address in invite_wallet_addresses:
            trimmed = wallet_address.strip()
            if not trimmed or trimmed in seen:
                continue
            seen.add(trimmed)
            deduped.append(trimmed)
        if not deduped:
            return
        payload = [
            BotInviteAccessRecord.create(
                bot_definition_id=bot_id,
                invited_wallet_address=wallet_address,
                invited_by_user_id=invited_by_user_id,
            ).to_row()
            for wallet_address in deduped
        ]
        self.supabase.insert("bot_invite_access", payload)

    def _list_invites(self, *, bot_id: str) -> list[dict[str, Any]]:
        try:
            return self.supabase.select(
                "bot_invite_access",
                filters={"bot_definition_id": bot_id, "status": "active"},
                order="created_at.asc",
            )
        except SupabaseRestError:
            return []

    def _get_publishing_settings_row(self, *, bot_definition_id: str) -> dict[str, Any] | None:
        try:
            existing = self.supabase.maybe_one("bot_publishing_settings", filters={"bot_definition_id": bot_definition_id})
        except SupabaseRestError:
            existing = None
        if existing is not None:
            return existing
        bot = self.supabase.maybe_one("bot_definitions", filters={"id": bot_definition_id})
        if bot is None:
            return None
        record = BotPublishingSettingsRecord.create(
            bot_definition_id=str(bot["id"]),
            user_id=str(bot["user_id"]),
            visibility=str(bot.get("visibility") or "private"),
        )
        try:
            return self.supabase.insert("bot_publishing_settings", record.to_row())[0]
        except SupabaseRestError:
            return record.to_row()

    def _ensure_publishing_settings(self, *, bot: dict[str, Any]) -> dict[str, Any]:
        publishing = self._get_publishing_settings_row(bot_definition_id=str(bot["id"]))
        if publishing is None:
            raise ValueError("Publishing settings not found")
        return publishing

    def _bot_copy_stats(self, *, runtime_id: str, bot_definition_id: str) -> dict[str, int]:
        relationships = self.supabase.select("bot_copy_relationships", filters={"source_runtime_id": runtime_id})
        clones = self.supabase.select("bot_clones", filters={"source_bot_definition_id": bot_definition_id})
        return {
            "mirror_count": len(relationships),
            "active_mirror_count": len([row for row in relationships if str(row.get("status") or "") == "active"]),
            "clone_count": len(clones),
        }

    def _count_creator_followers(self, *, creator_id: str) -> int:
        definitions = self.supabase.select("bot_definitions", filters={"user_id": creator_id, "visibility": "public"})
        if not definitions:
            return 0
        runtimes = self.supabase.select(
            "bot_runtimes",
            filters={"bot_definition_id": ("in", [row["id"] for row in definitions])},
        )
        if not runtimes:
            return 0
        relationships = self.supabase.select(
            "bot_copy_relationships",
            filters={"source_runtime_id": ("in", [row["id"] for row in runtimes])},
        )
        followers = {str(row.get("follower_user_id") or "") for row in relationships if row.get("follower_user_id")}
        return len(followers)

    @staticmethod
    def _marketplace_reach_score(
        *,
        active_mirror_count: int,
        follower_count: int,
        featured_bot_count: int,
        public_bot_count: int,
        reputation_score: int,
    ) -> int:
        return max(
            0,
            min(
                100,
                round(
                    (reputation_score * 0.52)
                    + min(28, active_mirror_count * 3.4)
                    + min(12, follower_count * 2.0)
                    + min(10, featured_bot_count * 4)
                    + min(10, public_bot_count * 2)
                ),
            ),
        )

    def _require_owned_bot(self, *, bot_id: str, wallet_address: str) -> dict[str, Any]:
        bot = self.supabase.maybe_one("bot_definitions", filters={"id": bot_id, "wallet_address": wallet_address})
        if bot is None:
            raise ValueError("Bot not found")
        return bot

    def _select_featured_rows(self, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        try:
            return self.supabase.select("featured_bots", filters=filters, order="collection_title.asc,shelf_rank.asc")
        except SupabaseRestError:
            return []

    @staticmethod
    def _publish_state(visibility: str) -> str:
        if visibility == "public":
            return "published"
        if visibility == "unlisted":
            return "unlisted"
        if visibility == "invite_only":
            return "invite_only"
        return "draft"

    @staticmethod
    def _snapshot_is_stale(value: Any) -> bool:
        captured_at = _as_datetime(value)
        if captured_at is None:
            return True
        return datetime.now(tz=UTC) - captured_at > timedelta(seconds=SNAPSHOT_TTL_SECONDS)
