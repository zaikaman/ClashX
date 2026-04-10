from __future__ import annotations

import asyncio
import logging
import re
import uuid
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

from src.models import (
    BotInviteAccessRecord,
    BotPublishingSettingsRecord,
    CreatorMarketplaceProfileRecord,
)
from src.services.bot_builder_service import BotBuilderService
from src.services.bot_leaderboard_engine import BotLeaderboardEngine
from src.services.bot_trust_service import BotTrustService
from src.services.supabase_rest import SupabaseRestClient, SupabaseRestError


SNAPSHOT_TTL_SECONDS = 60
VALID_VISIBILITY = {"private", "public", "unlisted", "invite_only"}
logger = logging.getLogger(__name__)


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
        self._marketplace_rows_lock = asyncio.Lock()
        self._marketplace_rows_cache: list[dict[str, Any]] = []
        self._marketplace_rows_cache_captured_at: str | None = None
        self._marketplace_rows_cache_built_at: datetime | None = None
        self._marketplace_rows_cache_limit: int = 0
        self._marketplace_overview_rows_lock = asyncio.Lock()
        self._marketplace_overview_rows_cache: list[dict[str, Any]] = []
        self._marketplace_overview_rows_cache_built_at: datetime | None = None
        self._marketplace_overview_rows_cache_limit: int = 0
        self._leaderboard_refresh_task: asyncio.Task[None] | None = None
        self._background_warm_task: asyncio.Task[None] | None = None

    async def discover_public_bots(
        self,
        *,
        limit: int = 24,
        strategy_type: str | None = None,
        creator_id: str | None = None,
    ) -> list[dict[str, Any]]:
        normalized_strategy_type = (strategy_type or "").strip().lower()
        requires_filter_scan = bool(normalized_strategy_type or creator_id)
        rows = await self._load_marketplace_rows(limit=max(limit * 3, 60) if requires_filter_scan else limit)
        filtered: list[dict[str, Any]] = []
        for row in rows:
            if normalized_strategy_type and str(row.get("strategy_type") or "").strip().lower() != normalized_strategy_type:
                continue
            if creator_id and str(row.get("creator", {}).get("creator_id") or "") != creator_id:
                continue
            filtered.append(row)
            if len(filtered) >= limit:
                break
        return filtered

    async def list_featured_shelves(self, *, limit: int = 4) -> list[dict[str, Any]]:
        del limit
        return []

    async def list_creator_highlights(self, *, limit: int = 6) -> list[dict[str, Any]]:
        public_rows = await self._load_marketplace_rows(limit=96)
        return self._build_creator_highlights(public_rows=public_rows, limit=limit)

    async def get_marketplace_overview(
        self,
        *,
        discover_limit: int = 36,
        featured_limit: int = 4,
        creator_limit: int = 6,
    ) -> dict[str, Any]:
        del featured_limit
        public_rows = await self._load_marketplace_overview_rows(limit=max(discover_limit, 120))
        discover_rows = public_rows[:discover_limit]
        return {
            "discover": discover_rows,
            "featured": [],
            "creators": self._build_creator_highlights(public_rows=public_rows, limit=creator_limit),
        }

    async def list_candidate_bots(self, *, limit: int = 24) -> list[dict[str, Any]]:
        rows = await self._load_marketplace_overview_rows(limit=max(limit, 60))
        return [
            {
                "runtime_id": row["runtime_id"],
                "bot_definition_id": row["bot_definition_id"],
                "bot_name": row["bot_name"],
                "strategy_type": row["strategy_type"],
                "rank": row["rank"],
                "drawdown": row["drawdown"],
                "trust": row["trust"],
            }
            for row in rows[:limit]
        ]

    async def start_background_warmup(self) -> None:
        task = self._background_warm_task
        if task is not None and not task.done():
            return
        self._background_warm_task = asyncio.create_task(self._background_warm_loop())

    async def stop_background_warmup(self) -> None:
        task = self._background_warm_task
        if task is None:
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        self._background_warm_task = None

    async def warm_marketplace_overview(self, *, limit: int = 120) -> None:
        latest = self.supabase.maybe_one("bot_leaderboard_snapshots", columns="captured_at", order="captured_at.desc")
        if latest is None or self._snapshot_is_stale(latest.get("captured_at")):
            try:
                await self.leaderboard_engine.refresh_public_leaderboard(None, limit=max(limit, 60))
            except Exception:
                logger.exception("Marketplace overview warm refresh failed")
            finally:
                self._clear_marketplace_cache()
        await self._load_marketplace_overview_rows(limit=max(limit, 120))

    def _build_creator_highlights(self, *, public_rows: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
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
                "featured_bot_count": 0,
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
        follower_count = self._count_creator_followers(creator_id=creator_id)
        marketplace_reach_score = self._marketplace_reach_score(
            active_mirror_count=int(base_profile["active_mirror_count"]),
            follower_count=follower_count,
            public_bot_count=int(base_profile["public_bot_count"]),
            reputation_score=int(base_profile["reputation_score"]),
        )
        return {
            **base_profile,
            "headline": marketplace_profile["headline"],
            "bio": marketplace_profile["bio"],
            "slug": marketplace_profile["slug"],
            "social_links_json": marketplace_profile.get("social_links_json") or {},
            "follower_count": follower_count,
            "featured_bot_count": 0,
            "marketplace_reach_score": marketplace_reach_score,
            "bots": public_rows,
            "featured_bots": [],
        }

    def get_publishing_settings(self, *, bot_id: str, wallet_address: str) -> dict[str, Any]:
        bot = self._require_owned_bot(bot_id=bot_id, wallet_address=wallet_address)
        user = self.supabase.maybe_one("users", filters={"id": bot["user_id"]})
        if user is None:
            raise ValueError("Creator not found")
        creator_profile = self._get_creator_profile_row(user_id=str(user["id"]))
        publishing = self._read_publishing_settings_row(bot_definition_id=str(bot["id"]))
        invites = self._list_invites(bot_id=bot_id)
        creator_display_name = (
            str((creator_profile or {}).get("display_name") or user.get("display_name") or bot.get("wallet_address") or "")[:80]
            or str(bot.get("wallet_address") or "")[:8]
        )
        return {
            "bot_definition_id": bot["id"],
            "visibility": bot["visibility"],
            "access_mode": (publishing or {}).get("access_mode") or bot["visibility"],
            "publish_state": (publishing or {}).get("publish_state") or self._publish_state(str(bot["visibility"])),
            "hero_headline": (publishing or {}).get("hero_headline") or "",
            "access_note": (publishing or {}).get("access_note") or "",
            "featured_collection_title": None,
            "featured_rank": 0,
            "is_featured": False,
            "invite_wallet_addresses": [invite["invited_wallet_address"] for invite in invites],
            "invite_count": len(invites),
            "creator_profile": {
                "display_name": creator_display_name,
                "headline": (creator_profile or {}).get("headline") or "",
                "bio": (creator_profile or {}).get("bio") or "",
                "slug": (creator_profile or {}).get("slug") or "",
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
        del is_featured, featured_collection_title, featured_rank
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

        self._ensure_creator_profile(
            user=user,
            display_name=creator_display_name or user.get("display_name"),
            headline=creator_headline,
            bio=creator_bio,
        )
        publishing = self._upsert_publishing_settings(
            bot=bot,
            hero_headline=hero_headline,
            access_note=access_note,
        )
        self._replace_invites(
            bot_id=bot_id,
            invited_by_user_id=str(bot["user_id"]),
            invite_wallet_addresses=invite_wallet_addresses if normalized_visibility == "invite_only" else [],
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
                    "is_featured": False,
                    "invite_count": len(invite_wallet_addresses if normalized_visibility == "invite_only" else []),
                    "publishing_id": publishing["id"],
                },
                "created_at": datetime.now(tz=UTC).isoformat(),
            },
            returning="minimal",
        )
        self._clear_marketplace_cache()
        return self.get_publishing_settings(bot_id=bot_id, wallet_address=wallet_address)

    async def _load_public_leaderboard_rows(self, *, limit: int) -> list[dict[str, Any]]:
        latest = self.supabase.maybe_one("bot_leaderboard_snapshots", order="captured_at.desc")
        if latest is None:
            self._schedule_public_leaderboard_refresh(limit=max(limit, 60))
            return self._fallback_public_leaderboard_rows(limit=limit)
        if self._snapshot_is_stale(latest.get("captured_at")):
            self._schedule_public_leaderboard_refresh(limit=max(limit, 60))

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
        return rows

    def _fallback_public_leaderboard_rows(self, *, limit: int) -> list[dict[str, Any]]:
        runtimes = self.supabase.select("bot_runtimes", filters={"status": "active"}, order="updated_at.desc", limit=max(limit, 60))
        definition_ids = [str(runtime["bot_definition_id"]) for runtime in runtimes]
        definitions = (
            {
                row["id"]: row
                for row in self.supabase.select(
                    "bot_definitions",
                    filters={"id": ("in", definition_ids), "visibility": "public"},
                )
            }
            if definition_ids
            else {}
        )
        captured_at = datetime.now(tz=UTC).isoformat()
        rows: list[dict[str, Any]] = []
        rank = 1
        for runtime in runtimes:
            definition = definitions.get(runtime["bot_definition_id"])
            if definition is None:
                continue
            state = runtime.get("risk_policy_json") if isinstance(runtime.get("risk_policy_json"), dict) else {}
            runtime_state = state.get("_runtime_state") if isinstance(state.get("_runtime_state"), dict) else {}
            rows.append(
                {
                    "runtime_id": runtime["id"],
                    "bot_definition_id": definition["id"],
                    "bot_name": definition["name"],
                    "strategy_type": definition["strategy_type"],
                    "authoring_mode": definition["authoring_mode"],
                    "rank": rank,
                    "pnl_total": float(runtime_state.get("pnl_total_usd") or 0.0),
                    "pnl_unrealized": float(runtime_state.get("pnl_unrealized_usd") or 0.0),
                    "win_streak": int(runtime_state.get("win_streak") or 0),
                    "drawdown": float(runtime_state.get("drawdown_pct") or 0.0),
                    "captured_at": captured_at,
                }
            )
            rank += 1
            if len(rows) >= limit:
                break
        return rows

    async def _load_public_leaderboard(self, *, limit: int) -> list[dict[str, Any]]:
        return self._augment_public_rows(await self._load_public_leaderboard_rows(limit=limit))

    async def _load_marketplace_rows(self, *, limit: int) -> list[dict[str, Any]]:
        cached_rows = self._get_cached_marketplace_rows(limit=limit)
        if cached_rows is not None:
            return cached_rows

        async with self._marketplace_rows_lock:
            cached_rows = self._get_cached_marketplace_rows(limit=limit)
            if cached_rows is not None:
                return cached_rows

            target_limit = max(limit, 120)
            marketplace_rows = await self._load_public_leaderboard(limit=target_limit)
            captured_at = self._latest_captured_at(marketplace_rows)
            self._marketplace_rows_cache = marketplace_rows
            self._marketplace_rows_cache_captured_at = captured_at
            self._marketplace_rows_cache_built_at = datetime.now(tz=UTC)
            self._marketplace_rows_cache_limit = target_limit
            return marketplace_rows[:limit]

    async def _load_marketplace_overview_rows(self, *, limit: int) -> list[dict[str, Any]]:
        cached_rows = self._get_cached_marketplace_overview_rows(limit=limit)
        if cached_rows is not None:
            return cached_rows

        async with self._marketplace_overview_rows_lock:
            cached_rows = self._get_cached_marketplace_overview_rows(limit=limit)
            if cached_rows is not None:
                return cached_rows

            target_limit = max(limit, 120)
            rows = await self._load_public_leaderboard_rows(limit=target_limit)
            overview_rows = self._augment_marketplace_overview_rows(rows)
            self._marketplace_overview_rows_cache = overview_rows
            self._marketplace_overview_rows_cache_built_at = datetime.now(tz=UTC)
            self._marketplace_overview_rows_cache_limit = target_limit
            return overview_rows[:limit]

    def _get_cached_marketplace_rows(self, *, limit: int) -> list[dict[str, Any]] | None:
        if self._marketplace_rows_cache_limit < limit:
            return None
        if self._marketplace_rows_cache_built_at is None:
            return None
        if datetime.now(tz=UTC) - self._marketplace_rows_cache_built_at > timedelta(seconds=SNAPSHOT_TTL_SECONDS):
            return None
        if not self._marketplace_rows_cache_captured_at:
            return None
        return self._marketplace_rows_cache[:limit]

    def _get_cached_marketplace_overview_rows(self, *, limit: int) -> list[dict[str, Any]] | None:
        if self._marketplace_overview_rows_cache_limit < limit:
            return None
        if self._marketplace_overview_rows_cache_built_at is None:
            return None
        if datetime.now(tz=UTC) - self._marketplace_overview_rows_cache_built_at > timedelta(seconds=SNAPSHOT_TTL_SECONDS):
            return None
        return self._marketplace_overview_rows_cache[:limit]

    def _augment_public_rows(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not rows:
            return []
        runtime_ids = [row["runtime_id"] for row in rows]
        definition_ids = [row["bot_definition_id"] for row in rows]
        runtimes = {
            row["id"]: row
            for row in self.supabase.select(
                "bot_runtimes",
                columns="id,bot_definition_id,user_id,wallet_address,status,mode,risk_policy_json,deployed_at,stopped_at,updated_at",
                filters={"id": ("in", runtime_ids)},
            )
        }
        definitions = {
            row["id"]: row
            for row in self.supabase.select(
                "bot_definitions",
                columns="id,user_id,wallet_address,name,description,visibility,market_scope,strategy_type,authoring_mode,rules_version,rules_json,created_at,updated_at",
                filters={"id": ("in", definition_ids)},
            )
        }
        support = self._build_marketplace_support_maps(rows=rows, definitions=definitions)
        overview_rows: list[dict[str, Any]] = []
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
            overview_rows.append(
                {
                    **row,
                    "trust": public_context["trust"],
                    "drift": public_context["drift"],
                    "passport": public_context["passport"],
                    "copy_stats": support["copy_stats_by_runtime"].get(
                        str(row["runtime_id"]),
                        {"mirror_count": 0, "active_mirror_count": 0, "clone_count": 0},
                    ),
                    "publishing": support["publishing_by_definition"].get(
                        str(row["bot_definition_id"]),
                        {
                            "visibility": "public",
                            "access_mode": "public",
                            "publish_state": "published",
                            "hero_headline": "",
                            "access_note": "",
                            "featured_collection_title": None,
                            "featured_rank": 0,
                            "is_featured": False,
                            "invite_count": 0,
                        },
                    ),
                    "_creator_id": creator_id,
                }
            )
        creator_summaries = self._build_marketplace_creator_summary_map(overview_rows=overview_rows, support=support)
        return [
            {
                key: value
                for key, value in {
                    **row,
                    "creator": creator_summaries.get(str(row.get("_creator_id") or ""), {}),
                }.items()
                if key != "_creator_id"
            }
            for row in overview_rows
        ]

    def _augment_marketplace_overview_rows(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not rows:
            return []

        runtime_ids = [row["runtime_id"] for row in rows]
        definition_ids = [row["bot_definition_id"] for row in rows]
        runtimes = {row["id"]: row for row in self.supabase.select("bot_runtimes", filters={"id": ("in", runtime_ids)})}
        definitions = {
            row["id"]: row for row in self.supabase.select("bot_definitions", filters={"id": ("in", definition_ids)})
        }
        support = self._build_marketplace_support_maps(rows=rows, definitions=definitions)

        overview_rows: list[dict[str, Any]] = []
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
            context = self._build_marketplace_overview_context(runtime=runtime, definition=definition, latest_snapshot=snapshot)
            creator_id = str(definition["user_id"])
            copy_stats = support["copy_stats_by_runtime"].get(
                str(row["runtime_id"]),
                {"mirror_count": 0, "active_mirror_count": 0, "clone_count": 0},
            )
            publishing = support["publishing_by_definition"].get(
                str(row["bot_definition_id"]),
                {
                    "visibility": "public",
                    "access_mode": "public",
                    "publish_state": "published",
                    "hero_headline": "",
                    "access_note": "",
                    "featured_collection_title": None,
                    "featured_rank": 0,
                    "is_featured": False,
                    "invite_count": 0,
                },
            )
            overview_rows.append(
                {
                    **row,
                    "trust": context["trust"],
                    "drift": context["drift"],
                    "passport": {},
                    "copy_stats": copy_stats,
                    "publishing": publishing,
                    "_creator_id": creator_id,
                }
            )

        creator_summaries = self._build_marketplace_creator_summary_map(overview_rows=overview_rows, support=support)
        hydrated_rows: list[dict[str, Any]] = []
        for row in overview_rows:
            creator_id = str(row.get("_creator_id") or "")
            hydrated_rows.append(
                {
                    key: value
                    for key, value in {
                        **row,
                        "creator": creator_summaries.get(creator_id, {}),
                    }.items()
                    if key != "_creator_id"
                }
            )
        return hydrated_rows

    def _build_marketplace_support_maps(
        self,
        *,
        rows: list[dict[str, Any]],
        definitions: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        runtime_ids = [str(row["runtime_id"]) for row in rows]
        definition_ids = [str(row["bot_definition_id"]) for row in rows]
        creator_id_by_runtime = {
            str(row["runtime_id"]): str((definitions.get(row["bot_definition_id"]) or {}).get("user_id") or "")
            for row in rows
        }
        creator_ids = sorted({creator_id for creator_id in creator_id_by_runtime.values() if creator_id})

        relationships = (
            self.supabase.select(
                "bot_copy_relationships",
                columns="source_runtime_id,follower_user_id,status",
                filters={"source_runtime_id": ("in", runtime_ids)},
            )
            if runtime_ids
            else []
        )
        publishing_rows = (
            self.supabase.select(
                "bot_publishing_settings",
                columns="bot_definition_id,visibility,access_mode,publish_state,hero_headline,access_note",
                filters={"bot_definition_id": ("in", definition_ids)},
            )
            if definition_ids
            else []
        )
        invite_rows = (
            self.supabase.select(
                "bot_invite_access",
                columns="bot_definition_id",
                filters={"bot_definition_id": ("in", definition_ids), "status": "active"},
            )
            if definition_ids
            else []
        )
        users = (
            self.supabase.select(
                "users",
                columns="id,wallet_address,display_name",
                filters={"id": ("in", creator_ids)},
            )
            if creator_ids
            else []
        )
        profiles = (
            self.supabase.select(
                "creator_marketplace_profiles",
                columns="id,user_id,display_name,headline,bio,slug",
                filters={"user_id": ("in", creator_ids)},
            )
            if creator_ids
            else []
        )
        clone_rows = (
            self.supabase.select(
                "bot_clones",
                columns="source_bot_definition_id",
                filters={"source_bot_definition_id": ("in", definition_ids)},
            )
            if definition_ids
            else []
        )

        invite_count_by_definition: dict[str, int] = defaultdict(int)
        for row in invite_rows:
            invite_count_by_definition[str(row.get("bot_definition_id") or "")] += 1

        publishing_by_definition: dict[str, dict[str, Any]] = {}
        for row in publishing_rows:
            bot_definition_id = str(row.get("bot_definition_id") or "")
            publishing_by_definition[bot_definition_id] = {
                "visibility": row.get("visibility") or "public",
                "access_mode": row.get("access_mode") or "public",
                "publish_state": row.get("publish_state") or "published",
                "hero_headline": row.get("hero_headline") or "",
                "access_note": row.get("access_note") or "",
                "featured_collection_title": None,
                "featured_rank": 0,
                "is_featured": False,
                "invite_count": invite_count_by_definition.get(bot_definition_id, 0),
            }
        for definition_id in definition_ids:
            publishing_by_definition.setdefault(
                definition_id,
                {
                    "visibility": "public",
                    "access_mode": "public",
                    "publish_state": "published",
                    "hero_headline": "",
                    "access_note": "",
                    "featured_collection_title": None,
                    "featured_rank": 0,
                    "is_featured": False,
                    "invite_count": invite_count_by_definition.get(definition_id, 0),
                },
            )

        relationships_by_runtime: dict[str, list[dict[str, Any]]] = defaultdict(list)
        follower_ids_by_creator: dict[str, set[str]] = defaultdict(set)
        mirror_count_by_creator: dict[str, int] = defaultdict(int)
        active_mirror_count_by_creator: dict[str, int] = defaultdict(int)
        copy_stats_by_runtime: dict[str, dict[str, int]] = {}
        for relationship in relationships:
            runtime_id = str(relationship.get("source_runtime_id") or "")
            relationships_by_runtime[runtime_id].append(relationship)
            creator_id = creator_id_by_runtime.get(runtime_id) or ""
            if not creator_id:
                continue
            mirror_count_by_creator[creator_id] += 1
            if str(relationship.get("status") or "") == "active":
                active_mirror_count_by_creator[creator_id] += 1
            follower_user_id = str(relationship.get("follower_user_id") or "")
            if follower_user_id:
                follower_ids_by_creator[creator_id].add(follower_user_id)

        clone_count_by_definition: dict[str, int] = defaultdict(int)
        clone_count_by_creator: dict[str, int] = defaultdict(int)
        creator_id_by_definition = {
            str(definition_id): str(definition.get("user_id") or "") for definition_id, definition in definitions.items()
        }
        for clone in clone_rows:
            definition_id = str(clone.get("source_bot_definition_id") or "")
            clone_count_by_definition[definition_id] += 1
            creator_id = creator_id_by_definition.get(definition_id) or ""
            if creator_id:
                clone_count_by_creator[creator_id] += 1

        public_bot_count_by_creator: dict[str, int] = defaultdict(int)
        active_runtime_count_by_creator: dict[str, int] = defaultdict(int)
        for row in rows:
            runtime_id = str(row["runtime_id"])
            definition_id = str(row["bot_definition_id"])
            creator_id = creator_id_by_runtime.get(runtime_id) or ""
            row_relationships = relationships_by_runtime.get(runtime_id, [])
            copy_stats_by_runtime[runtime_id] = {
                "mirror_count": len(row_relationships),
                "active_mirror_count": len(
                    [relationship for relationship in row_relationships if str(relationship.get("status") or "") == "active"]
                ),
                "clone_count": clone_count_by_definition.get(definition_id, 0),
            }
            if not creator_id:
                continue
            public_bot_count_by_creator[creator_id] += 1
            active_runtime_count_by_creator[creator_id] += 1

        return {
            "publishing_by_definition": publishing_by_definition,
            "copy_stats_by_runtime": copy_stats_by_runtime,
            "users_by_creator": {str(row.get("id") or ""): row for row in users},
            "profiles_by_creator": {str(row.get("user_id") or ""): row for row in profiles},
            "follower_count_by_creator": {creator_id: len(followers) for creator_id, followers in follower_ids_by_creator.items()},
            "mirror_count_by_creator": mirror_count_by_creator,
            "active_mirror_count_by_creator": active_mirror_count_by_creator,
            "clone_count_by_creator": clone_count_by_creator,
            "public_bot_count_by_creator": public_bot_count_by_creator,
            "active_runtime_count_by_creator": active_runtime_count_by_creator,
        }

    def _build_marketplace_overview_context(
        self,
        *,
        runtime: dict[str, Any],
        definition: dict[str, Any],
        latest_snapshot: dict[str, Any],
    ) -> dict[str, Any]:
        health_metrics = self._marketplace_health_metrics(runtime)
        drift = self._marketplace_drift_summary()
        trust = self.trust_service._build_trust(
            runtime=runtime,
            latest_snapshot=latest_snapshot,
            health_metrics=health_metrics,
            drift=drift,
        )
        return {
            "trust": trust,
            "drift": drift,
        }

    def _build_marketplace_creator_summary_map(
        self,
        *,
        overview_rows: list[dict[str, Any]],
        support: dict[str, Any],
    ) -> dict[str, dict[str, Any]]:
        rows_by_creator: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in overview_rows:
            creator_id = str(row.get("_creator_id") or "")
            if creator_id:
                rows_by_creator[creator_id].append(row)

        creator_summaries: dict[str, dict[str, Any]] = {}
        for creator_id, creator_rows in rows_by_creator.items():
            user = support["users_by_creator"].get(creator_id)
            profile = support["profiles_by_creator"].get(creator_id)
            display_name = (
                str((profile or {}).get("display_name") or (user or {}).get("display_name") or (user or {}).get("wallet_address") or creator_id[:8])
            )[:80]
            trust_scores = [int(row["trust"]["trust_score"]) for row in creator_rows]
            average_trust_score = round(sum(trust_scores) / len(trust_scores)) if trust_scores else 0
            ranked_rows = [int(row["rank"]) for row in creator_rows if row.get("rank") is not None]
            best_rank = min(ranked_rows) if ranked_rows else None
            mirror_count = int(support["mirror_count_by_creator"].get(creator_id, 0))
            active_mirror_count = int(support["active_mirror_count_by_creator"].get(creator_id, 0))
            clone_count = int(support["clone_count_by_creator"].get(creator_id, 0))
            public_bot_count = int(support["public_bot_count_by_creator"].get(creator_id, len(creator_rows)))
            active_runtime_count = int(support["active_runtime_count_by_creator"].get(creator_id, len(creator_rows)))
            reputation_score = self.trust_service._creator_reputation_score(
                average_trust_score=average_trust_score,
                active_mirror_count=active_mirror_count,
                mirror_count=mirror_count,
                clone_count=clone_count,
                public_bot_count=public_bot_count,
                best_rank=best_rank,
            )
            reputation_label = self.trust_service._reputation_label(reputation_score)
            tags = self.trust_service._creator_tags(
                reputation_label=reputation_label,
                best_rank=best_rank,
                active_mirror_count=active_mirror_count,
                public_bot_count=public_bot_count,
            )
            follower_count = int(support["follower_count_by_creator"].get(creator_id, 0))
            creator_summaries[creator_id] = {
                "creator_id": creator_id,
                "wallet_address": str((user or {}).get("wallet_address") or ""),
                "display_name": display_name,
                "public_bot_count": public_bot_count,
                "active_runtime_count": active_runtime_count,
                "mirror_count": mirror_count,
                "active_mirror_count": active_mirror_count,
                "clone_count": clone_count,
                "average_trust_score": average_trust_score,
                "best_rank": best_rank,
                "reputation_score": reputation_score,
                "reputation_label": reputation_label,
                "summary": self.trust_service._creator_summary(
                    display_name=display_name,
                    public_bot_count=public_bot_count,
                    active_mirror_count=active_mirror_count,
                    average_trust_score=average_trust_score,
                ),
                "tags": tags,
                "headline": str((profile or {}).get("headline") or "") or "Publishing live strategies with clear guardrails.",
                "bio": str((profile or {}).get("bio") or ""),
                "slug": str((profile or {}).get("slug") or ""),
                "follower_count": follower_count,
                "featured_bot_count": 0,
                "marketplace_reach_score": self._marketplace_reach_score(
                    active_mirror_count=active_mirror_count,
                    follower_count=follower_count,
                    public_bot_count=public_bot_count,
                    reputation_score=reputation_score,
                ),
            }
        return creator_summaries

    def _marketplace_health_metrics(self, runtime: dict[str, Any]) -> dict[str, Any]:
        runtime_updated_at = self.trust_service._as_datetime(runtime.get("updated_at") or datetime.now(tz=UTC).isoformat())
        heartbeat_age_seconds = max(0, int((datetime.now(tz=UTC) - runtime_updated_at).total_seconds()))
        health = self.trust_service._health_label(
            runtime_status=str(runtime.get("status") or "draft"),
            heartbeat_age_seconds=heartbeat_age_seconds,
            failure_rate_pct=0.0,
        )
        uptime_pct = max(0.0, min(99.9, float(self.trust_service.HEALTH_UPTIME_MAP.get(health, 56.0))))
        return {
            "health": health,
            "heartbeat_age_seconds": heartbeat_age_seconds,
            "latest_event_at": runtime_updated_at.isoformat(),
            "failure_rate_pct": 0.0,
            "actions_total": 0,
            "action_error_count": 0,
            "uptime_pct": uptime_pct,
        }

    @staticmethod
    def _marketplace_drift_summary() -> dict[str, Any]:
        return {
            "status": "unverified",
            "score": 48,
            "summary": "Detailed replay drift is available on the runtime profile.",
            "live_pnl_pct": None,
            "benchmark_pnl_pct": None,
            "return_gap_pct": None,
            "live_drawdown_pct": 0.0,
            "benchmark_drawdown_pct": None,
            "drawdown_gap_pct": None,
            "benchmark_run_id": None,
            "benchmark_completed_at": None,
        }

    def _ensure_creator_profile(
        self,
        *,
        user: dict[str, Any],
        display_name: str | None = None,
        headline: str | None = None,
        bio: str | None = None,
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

    def _get_creator_profile_row(self, *, user_id: str) -> dict[str, Any] | None:
        try:
            return self.supabase.maybe_one("creator_marketplace_profiles", filters={"user_id": user_id})
        except SupabaseRestError:
            return None

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
    ) -> dict[str, Any]:
        existing = self._get_publishing_settings_row(bot_definition_id=str(bot["id"]))
        if existing is None:
            record = BotPublishingSettingsRecord.create(
                bot_definition_id=str(bot["id"]),
                user_id=str(bot["user_id"]),
                visibility=str(bot["visibility"]),
                hero_headline=hero_headline,
                access_note=access_note,
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
            "featured_collection_title": None,
            "featured_rank": 0,
            "updated_at": datetime.now(tz=UTC).isoformat(),
        }
        return self.supabase.update("bot_publishing_settings", values, filters={"id": existing["id"]})[0]

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
        self.supabase.insert("bot_invite_access", payload, returning="minimal")

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

    def _read_publishing_settings_row(self, *, bot_definition_id: str) -> dict[str, Any] | None:
        try:
            return self.supabase.maybe_one("bot_publishing_settings", filters={"bot_definition_id": bot_definition_id})
        except SupabaseRestError:
            return None

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
                    + min(10, public_bot_count * 2)
                ),
            ),
        )

    def _require_owned_bot(self, *, bot_id: str, wallet_address: str) -> dict[str, Any]:
        bot = self.supabase.maybe_one("bot_definitions", filters={"id": bot_id, "wallet_address": wallet_address})
        if bot is None:
            raise ValueError("Bot not found")
        return bot

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

    @staticmethod
    def _latest_captured_at(rows: list[dict[str, Any]]) -> str | None:
        for row in rows:
            captured_at = str(row.get("captured_at") or "").strip()
            if captured_at:
                return captured_at
        return None

    def _clear_marketplace_cache(self) -> None:
        self._marketplace_rows_cache = []
        self._marketplace_rows_cache_captured_at = None
        self._marketplace_rows_cache_built_at = None
        self._marketplace_rows_cache_limit = 0
        self._marketplace_overview_rows_cache = []
        self._marketplace_overview_rows_cache_built_at = None
        self._marketplace_overview_rows_cache_limit = 0

    def _schedule_public_leaderboard_refresh(self, *, limit: int) -> None:
        task = self._leaderboard_refresh_task
        if task is not None and not task.done():
            return
        self._leaderboard_refresh_task = asyncio.create_task(self._run_public_leaderboard_refresh(limit=limit))

    async def _run_public_leaderboard_refresh(self, *, limit: int) -> None:
        try:
            await self.leaderboard_engine.refresh_public_leaderboard(None, limit=max(limit, 60))
        except Exception:
            return
        finally:
            self._clear_marketplace_cache()
            self._leaderboard_refresh_task = None

    async def _background_warm_loop(self) -> None:
        try:
            await self.warm_marketplace_overview(limit=120)
            while True:
                await asyncio.sleep(max(15, SNAPSHOT_TTL_SECONDS // 2))
                await self.warm_marketplace_overview(limit=120)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Marketplace background warm loop stopped unexpectedly")
