from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from typing import Any as Session

from src.api.auth import AuthenticatedUser, ensure_wallet_owned, require_authenticated_user
from src.db.session import get_db
from src.services.bot_copy_dashboard_service import BotCopyDashboardService
from src.services.bot_copy_engine import BotCopyEngine
from src.services.creator_marketplace_service import CreatorMarketplaceService
from src.services.pacifica_client import PacificaClientError

router = APIRouter(prefix="/api/bot-copy", tags=["bot-copy"])
bot_copy_engine = BotCopyEngine()
marketplace_service = CreatorMarketplaceService()
dashboard_service = BotCopyDashboardService()


def _require_owned_bot_copy_relationship(relationship_id: str, user: AuthenticatedUser) -> None:
    relationship = bot_copy_engine.supabase.maybe_one("bot_copy_relationships", filters={"id": relationship_id})
    if relationship is None:
        raise HTTPException(status_code=404, detail="Bot copy relationship not found")
    ensure_wallet_owned(user, relationship["follower_wallet_address"])


class BotLeaderboardRow(BaseModel):
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
    captured_at: datetime
    trust: "TrustMetricsResponse"
    drift: "DriftMetricsResponse"
    passport: "StrategyPassportResponse"
    creator: "CreatorSummaryResponse"


class BotLeaderboardCandidateRow(BaseModel):
    runtime_id: str
    bot_definition_id: str
    bot_name: str
    strategy_type: str
    rank: int
    drawdown: float
    trust: "TrustMetricsResponse"


class RuntimeEventSummary(BaseModel):
    id: str
    event_type: str
    decision_summary: str
    status: str
    created_at: datetime


class BotRuntimeProfileResponse(BaseModel):
    runtime_id: str
    bot_definition_id: str
    bot_name: str
    description: str
    strategy_type: str
    authoring_mode: str
    status: str
    mode: str
    risk_policy_json: dict
    rank: int | None = None
    pnl_total: float
    pnl_unrealized: float
    win_streak: int
    drawdown: float
    recent_events: list[RuntimeEventSummary]
    trust: "TrustMetricsResponse"
    drift: "DriftMetricsResponse"
    passport: "StrategyPassportResponse"
    creator: "CreatorProfileResponse"


class TrustBadgeResponse(BaseModel):
    label: str
    tone: str
    detail: str


class TrustMetricsResponse(BaseModel):
    trust_score: int
    uptime_pct: float
    failure_rate_pct: float
    health: str
    heartbeat_age_seconds: int
    risk_grade: str
    risk_score: int
    summary: str
    badges: list[TrustBadgeResponse]


class DriftMetricsResponse(BaseModel):
    status: str
    score: int
    summary: str
    live_pnl_pct: float | None = None
    benchmark_pnl_pct: float | None = None
    return_gap_pct: float | None = None
    live_drawdown_pct: float
    benchmark_drawdown_pct: float | None = None
    drawdown_gap_pct: float | None = None
    benchmark_run_id: str | None = None
    benchmark_completed_at: datetime | None = None


class StrategyVersionSummaryResponse(BaseModel):
    id: str
    bot_definition_id: str
    version_number: int
    change_kind: str
    visibility_snapshot: str
    name_snapshot: str
    is_public_release: bool
    created_at: datetime
    label: str


class PublishSnapshotResponse(BaseModel):
    id: str
    bot_definition_id: str
    strategy_version_id: str | None = None
    runtime_id: str | None = None
    visibility_snapshot: str
    publish_state: str
    summary_json: dict
    created_at: datetime


class StrategyPassportResponse(BaseModel):
    market_scope: str
    strategy_type: str
    authoring_mode: str
    rules_version: int
    current_version: int
    release_count: int
    public_since: datetime | None = None
    last_published_at: datetime | None = None
    latest_backtest_at: datetime | None = None
    latest_backtest_run_id: str | None = None
    version_history: list[StrategyVersionSummaryResponse]
    publish_history: list[PublishSnapshotResponse]


class CreatorSummaryResponse(BaseModel):
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


class CreatorBotSummaryResponse(BaseModel):
    runtime_id: str
    bot_definition_id: str
    bot_name: str
    strategy_type: str
    rank: int | None = None
    pnl_total: float
    drawdown: float
    trust_score: int
    risk_grade: str
    drift_status: str
    captured_at: datetime | None = None


class CreatorProfileResponse(CreatorSummaryResponse):
    bots: list[CreatorBotSummaryResponse] = Field(default_factory=list)


class MirrorPosition(BaseModel):
    symbol: str
    side: str
    size_source: float
    size_mirrored: float
    mark_price: float
    notional_estimate: float


class MirrorPreviewRequest(BaseModel):
    source_runtime_id: str
    follower_wallet_address: str = Field(min_length=8)
    scale_bps: int = Field(ge=500, le=30_000)


class MirrorPreviewResponse(BaseModel):
    source_runtime_id: str
    source_bot_definition_id: str
    source_bot_name: str
    source_wallet_address: str
    follower_wallet_address: str
    mode: str
    scale_bps: int
    warnings: list[str]
    mirrored_positions: list[MirrorPosition]


class MirrorActivateRequest(MirrorPreviewRequest):
    follower_display_name: str | None = Field(default=None, max_length=80)
    risk_ack_version: str = "v1"


class CloneRequest(BaseModel):
    source_runtime_id: str
    wallet_address: str = Field(min_length=8)
    name: str | None = Field(default=None, min_length=2, max_length=120)
    description: str | None = None
    visibility: str = "private"


class CloneResponse(BaseModel):
    clone_id: str
    source_runtime_id: str
    source_bot_definition_id: str
    new_bot_definition_id: str
    created_by_user_id: str
    created_at: datetime


class CloneListItemResponse(BaseModel):
    clone_id: str
    source_bot_definition_id: str
    source_bot_name: str
    new_bot_definition_id: str
    new_bot_name: str
    created_at: datetime


class BotCopyRelationshipPatchRequest(BaseModel):
    scale_bps: int | None = Field(default=None, ge=500, le=30_000)
    status: str | None = None


class BotCopyRelationshipResponse(BaseModel):
    id: str
    source_runtime_id: str
    source_bot_definition_id: str
    source_bot_name: str
    follower_user_id: str
    follower_wallet_address: str
    mode: str
    scale_bps: int
    status: str
    risk_ack_version: str
    confirmed_at: datetime
    updated_at: datetime
    follower_display_name: str | None = None


class BotCopyDashboardSummaryResponse(BaseModel):
    active_follows: int
    open_positions: int
    copied_open_notional_usd: float
    copied_unrealized_pnl_usd: float
    copied_realized_pnl_usd_24h: float
    copied_realized_pnl_usd_7d: float
    readiness_status: str


class BotCopyDashboardReadinessResponse(BaseModel):
    can_copy: bool
    authorization_status: str
    blockers: list[str]


class BotCopyDashboardAlertResponse(BaseModel):
    kind: str
    title: str
    detail: str
    severity: str


class BotCopyDashboardPositionResponse(BaseModel):
    relationship_id: str
    symbol: str
    side: str
    quantity: float
    entry_price: float
    mark_price: float
    notional_usd: float
    unrealized_pnl_usd: float
    opened_at: datetime | None = None
    last_synced_at: datetime | None = None


class BotCopyDashboardFollowResponse(BaseModel):
    id: str
    source_runtime_id: str
    source_bot_definition_id: str
    source_bot_name: str
    source_rank: int | None = None
    source_drawdown_pct: float
    source_trust_score: int
    source_risk_grade: str | None = None
    source_health: str | None = None
    source_drift_status: str | None = None
    creator_display_name: str | None = None
    scale_bps: int
    status: str
    confirmed_at: datetime
    updated_at: datetime
    copied_open_notional_usd: float
    copied_unrealized_pnl_usd: float
    copied_position_count: int
    positions: list[BotCopyDashboardPositionResponse]
    last_execution_at: datetime | None = None
    last_execution_status: str | None = None
    last_execution_symbol: str | None = None
    max_notional_usd: float | None = None


class BotCopyDashboardActivityResponse(BaseModel):
    id: str | None = None
    relationship_id: str | None = None
    source_runtime_id: str | None = None
    source_event_id: str | None = None
    symbol: str | None = None
    side: str | None = None
    action_type: str | None = None
    copied_quantity: float
    reference_price: float
    notional_estimate_usd: float
    status: str | None = None
    error_reason: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class BotCopyDashboardDiscoverResponse(BaseModel):
    runtime_id: str | None = None
    bot_definition_id: str | None = None
    bot_name: str | None = None
    strategy_type: str | None = None
    rank: int | None = None
    drawdown: float
    trust_score: int
    creator_display_name: str | None = None
    creator_id: str | None = None


class BotCopyDashboardBasketSummaryResponse(BaseModel):
    id: str | None = None
    name: str | None = None
    status: str | None = None
    member_count: int
    target_notional_usd: float
    current_notional_usd: float
    health: str | None = None
    alert_count: int
    aggregate_live_pnl_usd: float
    aggregate_drawdown_pct: float
    last_rebalanced_at: datetime | None = None


class BotCopyDashboardResponse(BaseModel):
    summary: BotCopyDashboardSummaryResponse
    readiness: BotCopyDashboardReadinessResponse
    alerts: list[BotCopyDashboardAlertResponse]
    follows: list[BotCopyDashboardFollowResponse]
    positions: list[BotCopyDashboardPositionResponse]
    activity: list[BotCopyDashboardActivityResponse]
    discover: list[BotCopyDashboardDiscoverResponse]
    baskets_summary: list[BotCopyDashboardBasketSummaryResponse]


@router.get("/creators/{creator_id}", response_model=CreatorProfileResponse)
def get_creator_profile(
    creator_id: str,
    db: Session = Depends(get_db),
) -> CreatorProfileResponse:
    try:
        payload = bot_copy_engine.creator_profile(db, creator_id=creator_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return CreatorProfileResponse.model_validate(payload)


@router.get("/leaderboard", response_model=list[BotLeaderboardRow])
async def list_public_bot_leaderboard(
    response: Response,
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> list[BotLeaderboardRow]:
    response.headers["Cache-Control"] = "public, max-age=15, stale-while-revalidate=45"
    rows = await bot_copy_engine.get_or_refresh_leaderboard(
        db,
        limit=limit,
        include_creator=True,
        include_passport=True,
    )
    return [BotLeaderboardRow.model_validate(row) for row in rows]


@router.get("/leaderboard/candidates", response_model=list[BotLeaderboardCandidateRow])
async def list_public_bot_leaderboard_candidates(
    response: Response,
    limit: int = Query(default=24, ge=1, le=100),
    db: Session = Depends(get_db),
) -> list[BotLeaderboardCandidateRow]:
    del db
    response.headers["Cache-Control"] = "public, max-age=30, stale-while-revalidate=120"
    rows = await marketplace_service.list_candidate_bots(limit=limit)
    return [BotLeaderboardCandidateRow.model_validate(row) for row in rows]


@router.get("/leaderboard/{runtime_id}", response_model=BotRuntimeProfileResponse)
async def get_runtime_profile(
    response: Response,
    runtime_id: str,
    db: Session = Depends(get_db),
) -> BotRuntimeProfileResponse:
    response.headers["Cache-Control"] = "public, max-age=10, stale-while-revalidate=30"
    del db
    try:
        profile = await marketplace_service.get_runtime_profile(runtime_id=runtime_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return BotRuntimeProfileResponse.model_validate(profile)


@router.get("/dashboard", response_model=BotCopyDashboardResponse)
async def get_bot_copy_dashboard(
    response: Response,
    wallet_address: str = Query(min_length=8),
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> BotCopyDashboardResponse:
    del db
    response.headers["Cache-Control"] = "private, max-age=2, stale-while-revalidate=8"
    ensure_wallet_owned(user, wallet_address)
    payload = await dashboard_service.get_dashboard(wallet_address=wallet_address)
    return BotCopyDashboardResponse.model_validate(payload)


@router.get("", response_model=list[BotCopyRelationshipResponse])
def list_bot_copy_relationships(
    wallet_address: str = Query(min_length=8),
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> list[BotCopyRelationshipResponse]:
    ensure_wallet_owned(user, wallet_address)
    rows = bot_copy_engine.list_relationships(db, follower_wallet_address=wallet_address)
    return [BotCopyRelationshipResponse.model_validate(item) for item in rows]


@router.get("/clones", response_model=list[CloneListItemResponse])
def list_clones(
    wallet_address: str = Query(min_length=8),
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> list[CloneListItemResponse]:
    ensure_wallet_owned(user, wallet_address)
    rows = bot_copy_engine.list_clones(db, wallet_address=wallet_address)
    return [CloneListItemResponse.model_validate(item) for item in rows]


@router.post("/preview", response_model=MirrorPreviewResponse)
async def preview_mirror(
    payload: MirrorPreviewRequest,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> MirrorPreviewResponse:
    ensure_wallet_owned(user, payload.follower_wallet_address)
    try:
        preview = await bot_copy_engine.preview_mirror(
            db,
            runtime_id=payload.source_runtime_id,
            follower_wallet_address=payload.follower_wallet_address,
            scale_bps=payload.scale_bps,
        )
    except (ValueError, PacificaClientError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return MirrorPreviewResponse.model_validate(preview)


@router.post("/mirror", response_model=BotCopyRelationshipResponse)
async def activate_mirror(
    payload: MirrorActivateRequest,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> BotCopyRelationshipResponse:
    ensure_wallet_owned(user, payload.follower_wallet_address)
    try:
        relationship = await bot_copy_engine.activate_mirror(
            db,
            runtime_id=payload.source_runtime_id,
            follower_wallet_address=payload.follower_wallet_address,
            follower_display_name=payload.follower_display_name,
            scale_bps=payload.scale_bps,
            risk_ack_version=payload.risk_ack_version,
        )
    except (ValueError, PacificaClientError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return BotCopyRelationshipResponse.model_validate(relationship)


@router.post("/clone", response_model=CloneResponse)
def clone_bot_definition(
    payload: CloneRequest,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> CloneResponse:
    ensure_wallet_owned(user, payload.wallet_address)
    try:
        cloned = bot_copy_engine.create_clone(
            db,
            runtime_id=payload.source_runtime_id,
            wallet_address=payload.wallet_address,
            name=payload.name,
            description=payload.description,
            visibility=payload.visibility,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return CloneResponse.model_validate(cloned)


@router.patch("/{relationship_id}", response_model=BotCopyRelationshipResponse)
async def patch_bot_copy_relationship(
    relationship_id: str,
    payload: BotCopyRelationshipPatchRequest,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> BotCopyRelationshipResponse:
    _require_owned_bot_copy_relationship(relationship_id, user)
    try:
        relationship = await bot_copy_engine.update_relationship(
            db,
            relationship_id=relationship_id,
            scale_bps=payload.scale_bps,
            status=payload.status,
        )
    except (ValueError, PacificaClientError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return BotCopyRelationshipResponse.model_validate(relationship)


@router.delete("/{relationship_id}", response_model=BotCopyRelationshipResponse)
async def delete_bot_copy_relationship(
    relationship_id: str,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> BotCopyRelationshipResponse:
    _require_owned_bot_copy_relationship(relationship_id, user)
    try:
        relationship = await bot_copy_engine.stop_relationship(db, relationship_id=relationship_id)
    except (ValueError, PacificaClientError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return BotCopyRelationshipResponse.model_validate(relationship)
