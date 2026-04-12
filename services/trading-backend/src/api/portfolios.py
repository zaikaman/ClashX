from __future__ import annotations

from datetime import datetime
from typing import Any as Session

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field

from src.api.auth import AuthenticatedUser, ensure_wallet_owned, require_authenticated_user, resolve_app_user_id
from src.db.session import get_db
from src.services.portfolio_allocator_service import PortfolioAllocatorService

router = APIRouter(prefix="/api/portfolios", tags=["portfolios"])
portfolio_allocator_service = PortfolioAllocatorService()


class PortfolioMemberInput(BaseModel):
    source_runtime_id: str
    target_weight_pct: float = Field(gt=0)
    max_scale_bps: int = Field(default=20_000, ge=500, le=30_000)


class PortfolioRiskPolicyInput(BaseModel):
    max_drawdown_pct: float = Field(default=18, ge=5, le=95)
    max_member_drawdown_pct: float = Field(default=22, ge=5, le=95)
    min_trust_score: int = Field(default=55, ge=0, le=100)
    max_active_members: int = Field(default=5, ge=1, le=20)
    auto_pause_on_source_stale: bool = True
    kill_switch_on_breach: bool = True


class PortfolioCreateRequest(BaseModel):
    wallet_address: str = Field(min_length=8)
    name: str = Field(min_length=2, max_length=120)
    description: str = Field(default="", max_length=500)
    rebalance_mode: str = Field(default="drift")
    rebalance_interval_minutes: int = Field(default=60, ge=5, le=1440)
    drift_threshold_pct: float = Field(default=6, ge=0.5, le=100)
    target_notional_usd: float = Field(ge=50, le=1_000_000)
    members: list[PortfolioMemberInput] = Field(min_length=1, max_length=12)
    risk_policy: PortfolioRiskPolicyInput = Field(default_factory=PortfolioRiskPolicyInput)
    activate_on_create: bool = True


class PortfolioUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    status: str | None = None
    rebalance_mode: str | None = None
    rebalance_interval_minutes: int | None = Field(default=None, ge=5, le=1440)
    drift_threshold_pct: float | None = Field(default=None, ge=0.5, le=100)
    target_notional_usd: float | None = Field(default=None, ge=50, le=1_000_000)
    members: list[PortfolioMemberInput] | None = None
    risk_policy: PortfolioRiskPolicyInput | None = None


class PortfolioKillSwitchRequest(BaseModel):
    engaged: bool
    reason: str | None = Field(default=None, max_length=280)


class PortfolioRiskPolicyResponse(BaseModel):
    max_drawdown_pct: float
    max_member_drawdown_pct: float
    min_trust_score: int
    max_active_members: int
    auto_pause_on_source_stale: bool
    kill_switch_on_breach: bool


class PortfolioMemberResponse(BaseModel):
    id: str
    source_runtime_id: str
    source_bot_definition_id: str
    source_bot_name: str
    target_weight_pct: float
    target_notional_usd: float
    max_scale_bps: int
    target_scale_bps: int
    latest_scale_bps: int
    status: str
    relationship_id: str | None = None
    relationship_status: str | None = None
    trust_score: int
    risk_grade: str
    drift_status: str
    member_live_pnl_pct: float
    member_drawdown_pct: float
    scale_drift_pct: float
    last_rebalanced_at: datetime | None = None


class PortfolioHealthResponse(BaseModel):
    health: str
    total_target_notional_usd: float
    current_total_notional_usd: float
    aggregate_live_pnl_usd: float
    aggregate_drawdown_pct: float
    risk_budget_used_pct: float
    should_kill_switch: bool
    needs_rebalance: bool
    alert_count: int
    alerts: list[str]


class PortfolioRebalanceEventResponse(BaseModel):
    id: str
    trigger: str
    status: str
    summary_json: dict
    created_at: datetime


class PortfolioResponse(BaseModel):
    id: str
    owner_user_id: str
    wallet_address: str
    name: str
    description: str
    status: str
    rebalance_mode: str
    rebalance_interval_minutes: int
    drift_threshold_pct: float
    target_notional_usd: float
    current_notional_usd: float
    kill_switch_reason: str | None = None
    last_rebalanced_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    risk_policy: PortfolioRiskPolicyResponse
    members: list[PortfolioMemberResponse]
    health: PortfolioHealthResponse
    rebalance_history: list[PortfolioRebalanceEventResponse]


@router.get("", response_model=list[PortfolioResponse])
def list_portfolios(
    wallet_address: str = Query(min_length=8),
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> list[PortfolioResponse]:
    del db
    ensure_wallet_owned(user, wallet_address)
    return [PortfolioResponse.model_validate(item) for item in portfolio_allocator_service.list_portfolios(wallet_address=wallet_address)]


@router.get("/{portfolio_id}", response_model=PortfolioResponse)
def get_portfolio(
    portfolio_id: str,
    wallet_address: str = Query(min_length=8),
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> PortfolioResponse:
    del db
    ensure_wallet_owned(user, wallet_address)
    try:
        return PortfolioResponse.model_validate(
            portfolio_allocator_service.get_portfolio(portfolio_id=portfolio_id, wallet_address=wallet_address)
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("", response_model=PortfolioResponse)
async def create_portfolio(
    payload: PortfolioCreateRequest,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> PortfolioResponse:
    del db
    ensure_wallet_owned(user, payload.wallet_address)
    try:
        result = await portfolio_allocator_service.create_portfolio(
            owner_user_id=resolve_app_user_id(user, payload.wallet_address),
            wallet_address=payload.wallet_address,
            name=payload.name,
            description=payload.description,
            rebalance_mode=payload.rebalance_mode,
            rebalance_interval_minutes=payload.rebalance_interval_minutes,
            drift_threshold_pct=payload.drift_threshold_pct,
            target_notional_usd=payload.target_notional_usd,
            members=[item.model_dump() for item in payload.members],
            risk_policy=payload.risk_policy.model_dump(),
            activate_on_create=payload.activate_on_create,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return PortfolioResponse.model_validate(result)


@router.patch("/{portfolio_id}", response_model=PortfolioResponse)
async def update_portfolio(
    portfolio_id: str,
    payload: PortfolioUpdateRequest,
    wallet_address: str = Query(min_length=8),
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> PortfolioResponse:
    del db
    ensure_wallet_owned(user, wallet_address)
    serialized = payload.model_dump(exclude_none=True)
    try:
        result = await portfolio_allocator_service.update_portfolio(
            portfolio_id=portfolio_id,
            wallet_address=wallet_address,
            payload=serialized,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return PortfolioResponse.model_validate(result)


@router.post("/{portfolio_id}/rebalance", response_model=PortfolioResponse)
async def rebalance_portfolio(
    portfolio_id: str,
    wallet_address: str = Query(min_length=8),
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> PortfolioResponse:
    del db
    ensure_wallet_owned(user, wallet_address)
    try:
        result = await portfolio_allocator_service.rebalance_portfolio(
            portfolio_id=portfolio_id,
            wallet_address=wallet_address,
            trigger="manual",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return PortfolioResponse.model_validate(result)


@router.post("/{portfolio_id}/kill-switch", response_model=PortfolioResponse)
async def set_portfolio_kill_switch(
    portfolio_id: str,
    payload: PortfolioKillSwitchRequest,
    wallet_address: str = Query(min_length=8),
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> PortfolioResponse:
    del db
    ensure_wallet_owned(user, wallet_address)
    try:
        result = await portfolio_allocator_service.set_kill_switch(
            portfolio_id=portfolio_id,
            wallet_address=wallet_address,
            engaged=payload.engaged,
            reason=payload.reason,
            trigger="manual_kill_switch",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return PortfolioResponse.model_validate(result)


@router.delete("/{portfolio_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_portfolio(
    portfolio_id: str,
    wallet_address: str = Query(min_length=8),
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> Response:
    del db
    ensure_wallet_owned(user, wallet_address)
    try:
        await portfolio_allocator_service.delete_portfolio(
            portfolio_id=portfolio_id,
            wallet_address=wallet_address,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
