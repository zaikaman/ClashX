from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from src.api.auth import AuthenticatedUser, ensure_wallet_owned, require_authenticated_user
from src.db.session import get_db
from src.services.pacifica_auth_service import PacificaAuthService
from src.services.pacifica_readiness_service import PacificaReadinessService

router = APIRouter(prefix="/api/pacifica", tags=["pacifica"])
pacifica_auth_service = PacificaAuthService()
pacifica_readiness_service = PacificaReadinessService()


class SigningDraftResponse(BaseModel):
    type: str
    message: str | None = None
    request_payload: dict[str, Any]


class PacificaAuthorizationResponse(BaseModel):
    id: str
    user_id: str
    wallet_address: str
    account_address: str
    agent_wallet_address: str
    status: str
    builder_code: str | None = None
    max_fee_rate: str | None = None
    builder_approval_required: bool = False
    builder_approved_at: datetime | None = None
    agent_bound_at: datetime | None = None
    last_error: str | None = None
    created_at: datetime
    updated_at: datetime
    builder_approval_draft: SigningDraftResponse | None = None
    bind_agent_draft: SigningDraftResponse | None = None


class StartAuthorizationRequest(BaseModel):
    wallet_address: str = Field(min_length=8)
    display_name: str | None = Field(default=None, max_length=80)
    force_reissue: bool = False


class ActivateAuthorizationRequest(BaseModel):
    bind_agent_signature: str = Field(min_length=16)
    builder_approval_signature: str | None = Field(default=None, min_length=16)


class PacificaReadinessStepResponse(BaseModel):
    id: str
    title: str
    verified: bool
    detail: str


class PacificaReadinessMetricsResponse(BaseModel):
    sol_balance: float
    min_sol_balance: float
    equity_usd: float
    min_equity_usd: float
    agent_wallet_address: str | None = None
    authorization_status: str
    builder_code: str | None = None


class PacificaReadinessResponse(BaseModel):
    wallet_address: str
    ready: bool
    blockers: list[str]
    metrics: PacificaReadinessMetricsResponse
    steps: list[PacificaReadinessStepResponse]


@router.get("/authorize", response_model=PacificaAuthorizationResponse | None)
def get_authorization_status(wallet_address: str = Query(min_length=8), db=Depends(get_db), user: AuthenticatedUser = Depends(require_authenticated_user)) -> PacificaAuthorizationResponse | None:
    ensure_wallet_owned(user, wallet_address)
    authorization = pacifica_auth_service.get_authorization_by_wallet(db, wallet_address)
    return PacificaAuthorizationResponse.model_validate(authorization) if authorization else None


@router.get("/readiness", response_model=PacificaReadinessResponse)
async def get_pacifica_readiness(wallet_address: str = Query(min_length=8), db=Depends(get_db), user: AuthenticatedUser = Depends(require_authenticated_user)) -> PacificaReadinessResponse:
    ensure_wallet_owned(user, wallet_address)
    payload = await pacifica_readiness_service.get_readiness(db, wallet_address)
    return PacificaReadinessResponse.model_validate(payload)


@router.post("/authorize/start", response_model=PacificaAuthorizationResponse)
def start_authorization(payload: StartAuthorizationRequest, db=Depends(get_db), user: AuthenticatedUser = Depends(require_authenticated_user)) -> PacificaAuthorizationResponse:
    ensure_wallet_owned(user, payload.wallet_address)
    try:
        authorization = pacifica_auth_service.start_authorization(db, wallet_address=payload.wallet_address, display_name=payload.display_name, force_reissue=payload.force_reissue)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return PacificaAuthorizationResponse.model_validate(authorization)


@router.post("/authorize/{authorization_id}/activate", response_model=PacificaAuthorizationResponse)
def activate_authorization(authorization_id: str, payload: ActivateAuthorizationRequest, db=Depends(get_db), user: AuthenticatedUser = Depends(require_authenticated_user)) -> PacificaAuthorizationResponse:
    matching_authorization = None
    for wallet_address in user.wallet_addresses:
        candidate = pacifica_auth_service.get_authorization_by_wallet(db, wallet_address)
        if candidate is None:
            continue
        if candidate["id"] == authorization_id:
            matching_authorization = candidate
            break
    if matching_authorization is None:
        raise HTTPException(status_code=403, detail="Authorization record does not belong to the authenticated wallet")
    try:
        authorization = pacifica_auth_service.activate_authorization(db, authorization_id=authorization_id, bind_agent_signature=payload.bind_agent_signature, builder_approval_signature=payload.builder_approval_signature)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return PacificaAuthorizationResponse.model_validate(authorization)
