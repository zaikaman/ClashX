from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Any as Session

from src.api.auth import AuthenticatedUser, ensure_wallet_owned, require_authenticated_user
from src.db.session import get_db
from src.services.bot_copy_engine import BotCopyEngine
from src.services.pacifica_client import PacificaClientError

router = APIRouter(prefix="/api/bot-copy", tags=["bot-copy"])
bot_copy_engine = BotCopyEngine()


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


@router.get("/leaderboard", response_model=list[BotLeaderboardRow])
async def list_public_bot_leaderboard(
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> list[BotLeaderboardRow]:
    rows = await bot_copy_engine.get_or_refresh_leaderboard(db, limit=limit)
    return [BotLeaderboardRow.model_validate(row) for row in rows]


@router.get("/leaderboard/{runtime_id}", response_model=BotRuntimeProfileResponse)
def get_runtime_profile(runtime_id: str, db: Session = Depends(get_db)) -> BotRuntimeProfileResponse:
    try:
        profile = bot_copy_engine.runtime_profile(db, runtime_id=runtime_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return BotRuntimeProfileResponse.model_validate(profile)


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
