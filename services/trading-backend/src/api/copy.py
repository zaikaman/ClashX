from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.api.auth import AuthenticatedUser, ensure_wallet_owned, require_authenticated_user
from src.db.session import get_db
from src.services.copy_engine import CopyEngine
from src.services.pacifica_client import PacificaClientError

router = APIRouter(prefix="/api/copy", tags=["copy"])
copy_engine = CopyEngine()


class CopyPreviewRequest(BaseModel):
    source_user_id: str
    follower_wallet_address: str = Field(min_length=8)
    scale_bps: int = Field(ge=500, le=30_000)


class CopyConfirmRequest(CopyPreviewRequest):
    follower_display_name: str | None = Field(default=None, max_length=80)
    risk_ack_version: str = "v1"
    confirmation_phrase: str = Field(min_length=4)


class CopyRelationshipPatchRequest(BaseModel):
    scale_bps: int | None = Field(default=None, ge=500, le=30_000)
    status: str | None = None


class MirroredPosition(BaseModel):
    symbol: str
    side: str
    size_source: float
    size_mirrored: float
    mark_price: float
    notional_estimate: float


class CopyExecutionEventResponse(BaseModel):
    id: str | None = None
    symbol: str
    side: str
    size_source: float
    size_mirrored: float
    status: str
    error_reason: str | None = None
    created_at: datetime | None = None


class CopyRelationshipResponse(BaseModel):
    id: str
    follower_user_id: str
    follower_wallet_address: str
    source_user_id: str
    source_display_name: str
    source_wallet_address: str
    scale_bps: int
    status: str
    risk_ack_version: str
    confirmed_at: datetime
    updated_at: datetime
    events: list[CopyExecutionEventResponse]


class CopyPreviewResponse(BaseModel):
    source_user_id: str
    source_display_name: str
    source_wallet_address: str
    follower_wallet_address: str
    scale_bps: int
    warnings: list[str]
    confirmation_phrase: str
    source_rank: int | None = None
    source_win_streak: int = 0
    mirrored_positions: list[MirroredPosition]


@router.get("", response_model=list[CopyRelationshipResponse])
def list_copy_relationships(
    wallet_address: str = Query(min_length=8),
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> list[CopyRelationshipResponse]:
    ensure_wallet_owned(user, wallet_address)
    rows = copy_engine.list_relationships(db, wallet_address)
    return [CopyRelationshipResponse.model_validate(item) for item in rows]


@router.post("/preview", response_model=CopyPreviewResponse)
async def preview_copy(
    payload: CopyPreviewRequest,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> CopyPreviewResponse:
    ensure_wallet_owned(user, payload.follower_wallet_address)
    try:
        preview = await copy_engine.preview_copy(
            db,
            source_user_id=payload.source_user_id,
            follower_wallet_address=payload.follower_wallet_address,
            scale_bps=payload.scale_bps,
        )
    except (ValueError, PacificaClientError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return CopyPreviewResponse.model_validate(preview)


@router.post("/confirm", response_model=CopyRelationshipResponse)
async def confirm_copy(
    payload: CopyConfirmRequest,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> CopyRelationshipResponse:
    ensure_wallet_owned(user, payload.follower_wallet_address)
    try:
        relationship = await copy_engine.confirm_copy(
            db,
            source_user_id=payload.source_user_id,
            follower_wallet_address=payload.follower_wallet_address,
            follower_display_name=payload.follower_display_name,
            scale_bps=payload.scale_bps,
            risk_ack_version=payload.risk_ack_version,
            confirmation_phrase=payload.confirmation_phrase,
        )
    except (ValueError, PacificaClientError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return CopyRelationshipResponse.model_validate(relationship)


@router.patch("/{relationship_id}", response_model=CopyRelationshipResponse)
async def patch_copy_relationship(
    relationship_id: str,
    payload: CopyRelationshipPatchRequest,
    db: Session = Depends(get_db),
) -> CopyRelationshipResponse:
    try:
        relationship = await copy_engine.update_relationship(
            db,
            relationship_id=relationship_id,
            scale_bps=payload.scale_bps,
            status=payload.status,
        )
    except (ValueError, PacificaClientError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return CopyRelationshipResponse.model_validate(relationship)


@router.delete("/{relationship_id}", response_model=CopyRelationshipResponse)
async def delete_copy_relationship(relationship_id: str, db: Session = Depends(get_db)) -> CopyRelationshipResponse:
    try:
        relationship = await copy_engine.stop_relationship(db, relationship_id)
    except (ValueError, PacificaClientError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return CopyRelationshipResponse.model_validate(relationship)
