from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from typing import Any as Session

from src.api.auth import AuthenticatedUser, ensure_wallet_owned, require_authenticated_user
from src.db.session import get_db
from src.services.creator_marketplace_service import CreatorMarketplaceService

router = APIRouter(prefix="/api/marketplace", tags=["marketplace"])
marketplace_service = CreatorMarketplaceService()


class MarketplaceCopyStatsResponse(BaseModel):
    mirror_count: int
    active_mirror_count: int
    clone_count: int


class MarketplacePublishingSummaryResponse(BaseModel):
    visibility: str
    access_mode: str
    publish_state: str
    hero_headline: str = ""
    access_note: str = ""
    featured_collection_title: str | None = None
    featured_rank: int
    is_featured: bool = False
    invite_count: int = 0


class MarketplaceDiscoveryRowResponse(BaseModel):
    runtime_id: str
    bot_definition_id: str
    bot_name: str
    strategy_type: str
    authoring_mode: str
    rank: int
    pnl_total: float
    pnl_unrealized: float
    win_streak: int
    drawdown: float
    captured_at: str
    trust: dict[str, Any]
    drift: dict[str, Any]
    passport: dict[str, Any]
    creator: dict[str, Any]
    copy_stats: MarketplaceCopyStatsResponse
    publishing: MarketplacePublishingSummaryResponse


class FeaturedShelfResponse(BaseModel):
    collection_key: str
    title: str
    subtitle: str
    bots: list[MarketplaceDiscoveryRowResponse]


class CreatorHighlightResponse(BaseModel):
    creator_id: str
    wallet_address: str
    display_name: str
    public_bot_count: int
    active_runtime_count: int
    mirror_count: int
    active_mirror_count: int
    clone_count: int
    average_trust_score: int
    best_rank: int | None = None
    reputation_score: int
    reputation_label: str
    summary: str
    tags: list[str]
    headline: str = ""
    bio: str = ""
    follower_count: int = 0
    featured_bot_count: int = 0
    marketplace_reach_score: int
    spotlight_bot: dict[str, Any]


class MarketplaceOverviewDiscoveryRowResponse(BaseModel):
    runtime_id: str
    bot_definition_id: str
    bot_name: str
    strategy_type: str
    rank: int
    pnl_total: float
    trust: dict[str, Any]
    creator: dict[str, Any]
    copy_stats: MarketplaceCopyStatsResponse
    publishing: MarketplacePublishingSummaryResponse


class MarketplaceOverviewFeaturedShelfResponse(BaseModel):
    collection_key: str
    title: str
    subtitle: str
    bots: list[MarketplaceOverviewDiscoveryRowResponse]


class MarketplaceOverviewResponse(BaseModel):
    discover: list[MarketplaceOverviewDiscoveryRowResponse]
    featured: list[MarketplaceOverviewFeaturedShelfResponse]
    creators: list[CreatorHighlightResponse]


class CreatorMarketplaceProfileResponse(BaseModel):
    creator_id: str
    wallet_address: str
    display_name: str
    public_bot_count: int
    active_runtime_count: int
    mirror_count: int
    active_mirror_count: int
    clone_count: int
    average_trust_score: int
    best_rank: int | None = None
    reputation_score: int
    reputation_label: str
    summary: str
    tags: list[str]
    headline: str = ""
    bio: str = ""
    slug: str = ""
    social_links_json: dict[str, Any] = Field(default_factory=dict)
    featured_collection_title: str = "Featured strategies"
    follower_count: int = 0
    featured_bot_count: int = 0
    marketplace_reach_score: int = 0
    bots: list[MarketplaceDiscoveryRowResponse] = Field(default_factory=list)
    featured_bots: list[MarketplaceDiscoveryRowResponse] = Field(default_factory=list)


class PublishingCreatorProfileResponse(BaseModel):
    display_name: str
    headline: str = ""
    bio: str = ""
    slug: str = ""
    featured_collection_title: str = "Featured strategies"


class PublishingSettingsResponse(BaseModel):
    bot_definition_id: str
    visibility: str
    access_mode: str
    publish_state: str
    hero_headline: str = ""
    access_note: str = ""
    featured_collection_title: str | None = None
    featured_rank: int
    is_featured: bool = False
    invite_wallet_addresses: list[str] = Field(default_factory=list)
    invite_count: int = 0
    creator_profile: PublishingCreatorProfileResponse


class PublishingSettingsUpdateRequest(BaseModel):
    wallet_address: str = Field(min_length=8)
    visibility: str
    hero_headline: str | None = Field(default=None, max_length=180)
    access_note: str | None = Field(default=None, max_length=180)
    is_featured: bool = False
    featured_collection_title: str | None = Field(default=None, max_length=80)
    featured_rank: int = Field(default=0, ge=0, le=50)
    invite_wallet_addresses: list[str] = Field(default_factory=list)
    creator_display_name: str | None = Field(default=None, max_length=80)
    creator_headline: str | None = Field(default=None, max_length=180)
    creator_bio: str | None = Field(default=None, max_length=400)


def _set_marketplace_cache_headers(response: Response) -> None:
    response.headers["Cache-Control"] = "public, max-age=15, stale-while-revalidate=45"


@router.get("/overview", response_model=MarketplaceOverviewResponse)
async def get_marketplace_overview(
    response: Response,
    discover_limit: int = Query(default=36, ge=1, le=96),
    featured_limit: int = Query(default=4, ge=1, le=12),
    creator_limit: int = Query(default=6, ge=1, le=24),
) -> MarketplaceOverviewResponse:
    _set_marketplace_cache_headers(response)
    payload = await marketplace_service.get_marketplace_overview(
        discover_limit=discover_limit,
        featured_limit=featured_limit,
        creator_limit=creator_limit,
    )
    return MarketplaceOverviewResponse.model_validate(payload)


@router.get("/discover", response_model=list[MarketplaceDiscoveryRowResponse])
async def discover_public_bots(
    response: Response,
    limit: int = Query(default=24, ge=1, le=96),
    strategy_type: str | None = Query(default=None),
    creator_id: str | None = Query(default=None),
) -> list[MarketplaceDiscoveryRowResponse]:
    _set_marketplace_cache_headers(response)
    rows = await marketplace_service.discover_public_bots(limit=limit, strategy_type=strategy_type, creator_id=creator_id)
    return [MarketplaceDiscoveryRowResponse.model_validate(row) for row in rows]


@router.get("/featured", response_model=list[FeaturedShelfResponse])
async def list_featured_shelves(
    response: Response,
    limit: int = Query(default=4, ge=1, le=12),
) -> list[FeaturedShelfResponse]:
    _set_marketplace_cache_headers(response)
    rows = await marketplace_service.list_featured_shelves(limit=limit)
    return [FeaturedShelfResponse.model_validate(row) for row in rows]


@router.get("/creators", response_model=list[CreatorHighlightResponse])
async def list_creator_highlights(
    response: Response,
    limit: int = Query(default=6, ge=1, le=24),
) -> list[CreatorHighlightResponse]:
    _set_marketplace_cache_headers(response)
    rows = await marketplace_service.list_creator_highlights(limit=limit)
    return [CreatorHighlightResponse.model_validate(row) for row in rows]


@router.get("/creators/{creator_id}", response_model=CreatorMarketplaceProfileResponse)
async def get_creator_profile(
    response: Response,
    creator_id: str,
) -> CreatorMarketplaceProfileResponse:
    _set_marketplace_cache_headers(response)
    try:
        payload = await marketplace_service.get_creator_profile(creator_id=creator_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return CreatorMarketplaceProfileResponse.model_validate(payload)


@router.get("/publishing/{bot_id}", response_model=PublishingSettingsResponse)
def get_publishing_settings(
    bot_id: str,
    response: Response,
    wallet_address: str = Query(min_length=8),
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> PublishingSettingsResponse:
    del db
    response.headers["Cache-Control"] = "private, max-age=30, stale-while-revalidate=120"
    ensure_wallet_owned(user, wallet_address)
    try:
        payload = marketplace_service.get_publishing_settings(bot_id=bot_id, wallet_address=wallet_address)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return PublishingSettingsResponse.model_validate(payload)


@router.patch("/publishing/{bot_id}", response_model=PublishingSettingsResponse)
def patch_publishing_settings(
    bot_id: str,
    payload: PublishingSettingsUpdateRequest,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> PublishingSettingsResponse:
    del db
    ensure_wallet_owned(user, payload.wallet_address)
    try:
        result = marketplace_service.update_publishing(
            bot_id=bot_id,
            wallet_address=payload.wallet_address,
            visibility=payload.visibility,
            hero_headline=payload.hero_headline,
            access_note=payload.access_note,
            is_featured=payload.is_featured,
            featured_collection_title=payload.featured_collection_title,
            featured_rank=payload.featured_rank,
            invite_wallet_addresses=payload.invite_wallet_addresses,
            creator_display_name=payload.creator_display_name,
            creator_headline=payload.creator_headline,
            creator_bio=payload.creator_bio,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return PublishingSettingsResponse.model_validate(result)
