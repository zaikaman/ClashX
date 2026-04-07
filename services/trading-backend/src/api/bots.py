from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Literal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from typing import Any as Session

from src.api.auth import AuthenticatedUser, ensure_wallet_owned, require_authenticated_user
from src.db.session import get_db
from src.services.bot_builder_service import BotBuilderService
from src.services.bot_performance_service import BotPerformanceService
from src.services.bot_runtime_engine import BotRuntimeEngine
from src.services.runtime_health_service import RuntimeHealthService
from src.services.runtime_observability_service import RuntimeObservabilityService

router = APIRouter(prefix="/api/bots", tags=["bots"])
bot_builder_service = BotBuilderService()
bot_runtime_engine = BotRuntimeEngine()
bot_performance_service = BotPerformanceService()
runtime_health_service = RuntimeHealthService()
runtime_observability_service = RuntimeObservabilityService()


class BotDefinitionResponse(BaseModel):
    id: str
    user_id: str
    wallet_address: str
    name: str
    description: str
    visibility: str
    market_scope: str
    strategy_type: str
    authoring_mode: str
    rules_version: int
    rules_json: dict
    created_at: datetime
    updated_at: datetime


class BotRuntimeSummaryResponse(BaseModel):
    id: str
    status: str
    mode: str
    deployed_at: datetime | None = None
    stopped_at: datetime | None = None
    updated_at: datetime


class BotFleetItemResponse(BaseModel):
    id: str
    wallet_address: str
    name: str
    description: str
    visibility: str
    market_scope: str
    strategy_type: str
    authoring_mode: str
    updated_at: datetime
    runtime: BotRuntimeSummaryResponse | None = None
    performance: "RuntimePerformanceResponse | None" = None


class BotCreateRequest(BaseModel):
    wallet_address: str = Field(min_length=8)
    name: str = Field(min_length=2, max_length=120)
    description: str = ""
    visibility: str = "private"
    market_scope: str = "Pacifica perpetuals"
    strategy_type: str = "rules"
    authoring_mode: str = "visual"
    rules_version: int = Field(default=1, ge=1)
    rules_json: dict = Field(default_factory=dict)


class BotUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    description: str | None = None
    visibility: str | None = None
    market_scope: str | None = None
    strategy_type: str | None = None
    authoring_mode: str | None = None
    rules_version: int | None = Field(default=None, ge=1)
    rules_json: dict | None = None


class BotValidationRequest(BaseModel):
    authoring_mode: str
    visibility: str = "private"
    rules_version: int = Field(default=1, ge=1)
    rules_json: dict = Field(default_factory=dict)


class BotValidationResponse(BaseModel):
    valid: bool
    issues: list[str]


class BotRuntimeResponse(BaseModel):
    id: str
    bot_definition_id: str
    user_id: str
    wallet_address: str
    status: str
    mode: str
    risk_policy_json: dict
    deployed_at: datetime | None = None
    stopped_at: datetime | None = None
    updated_at: datetime


class BotExecutionEventResponse(BaseModel):
    id: str
    runtime_id: str
    event_type: str
    decision_summary: str
    request_payload: dict
    result_payload: dict
    status: str
    error_reason: str | None = None
    created_at: datetime


class BotDeployRequest(BaseModel):
    wallet_address: str | None = Field(default=None, min_length=8)
    risk_policy_json: dict[str, Any] = Field(default_factory=dict)


class RuntimeHealthResponse(BaseModel):
    runtime_id: str | None = None
    health: str
    status: str
    mode: str
    last_runtime_update: datetime | None = None
    last_event_at: datetime | None = None
    heartbeat_age_seconds: int | None = None
    error_rate_recent: float
    reasons: list[str]


class RuntimeFailureReason(BaseModel):
    reason: str
    count: int


class RuntimeFailureEvent(BaseModel):
    id: str
    event_type: str
    error_reason: str
    decision_summary: str
    created_at: datetime


class RuntimePositionResponse(BaseModel):
    symbol: str
    side: str
    amount: float
    entry_price: float
    mark_price: float
    unrealized_pnl: float


class RuntimePerformanceResponse(BaseModel):
    pnl_total: float
    pnl_total_pct: float
    pnl_realized: float
    pnl_unrealized: float
    win_streak: int
    positions: list[RuntimePositionResponse]


class RuntimeMetricsResponse(BaseModel):
    runtime_id: str
    status: str
    uptime_seconds: int | None = None
    window_hours: int
    events_total: int
    actions_total: int
    actions_success: int
    actions_error: int
    actions_skipped: int
    success_rate: float
    status_counts: dict[str, int]
    event_type_counts: dict[str, int]
    failure_reasons: list[RuntimeFailureReason]
    recent_failures: list[RuntimeFailureEvent]
    last_event_at: datetime | None = None


class RuntimeOverviewResponse(BaseModel):
    health: RuntimeHealthResponse
    metrics: RuntimeMetricsResponse
    performance: RuntimePerformanceResponse | None = None


class RuntimeRiskStateResponse(BaseModel):
    runtime_id: str
    risk_policy_json: dict[str, Any]
    runtime_state: dict[str, Any]
    updated_at: datetime


class RuntimeRiskStateUpdateRequest(BaseModel):
    wallet_address: str | None = Field(default=None, min_length=8)
    risk_policy_json: dict[str, Any] = Field(default_factory=dict)


def _resolve_wallet(user: AuthenticatedUser, wallet_address: str | None) -> str:
    resolved = wallet_address or (user.wallet_addresses[0] if user.wallet_addresses else None)
    if not resolved:
        raise HTTPException(status_code=400, detail="No wallet address available")
    ensure_wallet_owned(user, resolved)
    return resolved


async def _build_runtime_performance(runtime: dict[str, Any] | None) -> RuntimePerformanceResponse | None:
    if runtime is None:
        return None
    payload = await bot_performance_service.calculate_runtime_performance(runtime)
    return RuntimePerformanceResponse.model_validate(payload)


def _build_fast_runtime_performance(runtime: dict[str, Any] | None) -> RuntimePerformanceResponse | None:
    if runtime is None:
        return None
    risk_policy = runtime.get("risk_policy_json") if isinstance(runtime.get("risk_policy_json"), dict) else {}
    runtime_state = risk_policy.get("_runtime_state") if isinstance(risk_policy.get("_runtime_state"), dict) else {}

    allocated_capital = float(runtime_state.get("allocated_capital_usd") or risk_policy.get("allocated_capital_usd") or 0.0)
    pnl_total = float(runtime_state.get("pnl_total_usd") or 0.0)
    pnl_realized = float(runtime_state.get("realized_pnl_usd") or 0.0)
    pnl_unrealized = float(runtime_state.get("unrealized_pnl_usd") or 0.0)
    win_streak = int(runtime_state.get("win_streak") or 0)
    pnl_total_pct = (pnl_total / allocated_capital * 100.0) if allocated_capital > 0 else 0.0

    return RuntimePerformanceResponse(
        pnl_total=pnl_total,
        pnl_total_pct=pnl_total_pct,
        pnl_realized=pnl_realized,
        pnl_unrealized=pnl_unrealized,
        win_streak=win_streak,
        positions=[],
    )


@router.get("", response_model=list[BotFleetItemResponse])
async def list_bots(
    response: Response,
    wallet_address: str | None = Query(default=None, min_length=8),
    include_performance: bool = Query(default=True),
    performance_mode: Literal["full", "fast"] = Query(default="full"),
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> list[BotFleetItemResponse]:
    if performance_mode == "fast":
        response.headers["Cache-Control"] = "private, max-age=2, stale-while-revalidate=8"
    resolved_wallet = _resolve_wallet(user, wallet_address)
    definitions = bot_builder_service.list_bots(db, wallet_address=resolved_wallet)
    runtimes_for_wallet = bot_runtime_engine.list_runtimes_for_wallet(
        db,
        wallet_address=resolved_wallet,
        user_id=user.user_id,
    )
    runtimes = {runtime["bot_definition_id"]: runtime for runtime in runtimes_for_wallet}
    performances: list[RuntimePerformanceResponse | None]
    if include_performance and runtimes_for_wallet and performance_mode == "fast":
        performances = [_build_fast_runtime_performance(runtimes.get(row["id"])) for row in definitions]
    elif include_performance and runtimes_for_wallet:
        market_lookup = await bot_performance_service.load_market_lookup()
        live_position_lookup, live_positions_loaded = await bot_performance_service.load_live_position_lookup_for_wallet(
            resolved_wallet
        )
        manual_close_history = await bot_performance_service.load_position_history_for_wallet(resolved_wallet)
        performance_payloads = await asyncio.gather(
            *[
                bot_performance_service.calculate_runtime_performance(
                    runtime,
                    market_lookup=market_lookup,
                    live_position_lookup=live_position_lookup,
                    manual_close_history=manual_close_history,
                    live_positions_loaded=live_positions_loaded,
                )
                if runtime is not None
                else asyncio.sleep(0, result=None)
                for runtime in (runtimes.get(row["id"]) for row in definitions)
            ]
        )
        performances = [
            RuntimePerformanceResponse.model_validate(payload) if payload is not None else None
            for payload in performance_payloads
        ]
    else:
        performances = [None] * len(definitions)
    return [
        BotFleetItemResponse.model_validate(
            {
                "id": row["id"],
                "wallet_address": row["wallet_address"],
                "name": row["name"],
                "description": row["description"],
                "visibility": row["visibility"],
                "market_scope": row["market_scope"],
                "strategy_type": row["strategy_type"],
                "authoring_mode": row["authoring_mode"],
                "updated_at": row["updated_at"],
                "runtime": runtimes.get(row["id"]),
                "performance": performances[index],
            }
        )
        for index, row in enumerate(definitions)
    ]


@router.post("", response_model=BotDefinitionResponse)
def create_bot(
    payload: BotCreateRequest,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> BotDefinitionResponse:
    ensure_wallet_owned(user, payload.wallet_address)
    try:
        bot = bot_builder_service.create_bot(
            db,
            wallet_address=payload.wallet_address,
            name=payload.name,
            description=payload.description,
            visibility=payload.visibility,
            market_scope=payload.market_scope,
            strategy_type=payload.strategy_type,
            authoring_mode=payload.authoring_mode,
            rules_version=payload.rules_version,
            rules_json=payload.rules_json,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return BotDefinitionResponse.model_validate(bot)


@router.get("/{bot_id}", response_model=BotDefinitionResponse)
def get_bot(
    bot_id: str,
    wallet_address: str | None = Query(default=None, min_length=8),
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> BotDefinitionResponse:
    resolved_wallet = _resolve_wallet(user, wallet_address)
    try:
        bot = bot_builder_service.get_bot(db, bot_id=bot_id, wallet_address=resolved_wallet)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return BotDefinitionResponse.model_validate(bot)


@router.patch("/{bot_id}", response_model=BotDefinitionResponse)
def patch_bot(
    bot_id: str,
    payload: BotUpdateRequest,
    wallet_address: str | None = Query(default=None, min_length=8),
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> BotDefinitionResponse:
    resolved_wallet = _resolve_wallet(user, wallet_address)
    try:
        bot = bot_builder_service.update_bot(
            db,
            bot_id=bot_id,
            wallet_address=resolved_wallet,
            name=payload.name,
            description=payload.description,
            visibility=payload.visibility,
            market_scope=payload.market_scope,
            strategy_type=payload.strategy_type,
            authoring_mode=payload.authoring_mode,
            rules_version=payload.rules_version,
            rules_json=payload.rules_json,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return BotDefinitionResponse.model_validate(bot)


@router.delete("/{bot_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_bot(
    bot_id: str,
    wallet_address: str | None = Query(default=None, min_length=8),
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> Response:
    resolved_wallet = _resolve_wallet(user, wallet_address)
    try:
        bot_builder_service.delete_bot(db, bot_id=bot_id, wallet_address=resolved_wallet)
    except ValueError as exc:
        detail = str(exc)
        raise HTTPException(status_code=404 if detail == "Bot not found" else 400, detail=detail) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{bot_id}/validate", response_model=BotValidationResponse)
def validate_existing_bot(
    bot_id: str,
    wallet_address: str | None = Query(default=None, min_length=8),
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> BotValidationResponse:
    resolved_wallet = _resolve_wallet(user, wallet_address)
    try:
        bot = bot_builder_service.get_bot(db, bot_id=bot_id, wallet_address=resolved_wallet)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    issues = bot_builder_service.validate_definition(
        authoring_mode=bot["authoring_mode"],
        visibility=bot["visibility"],
        rules_version=bot["rules_version"],
        rules_json=bot["rules_json"],
    )
    return BotValidationResponse(valid=len(issues) == 0, issues=issues)


@router.post("/validate", response_model=BotValidationResponse)
def validate_draft(payload: BotValidationRequest) -> BotValidationResponse:
    issues = bot_builder_service.validate_definition(
        authoring_mode=payload.authoring_mode,
        visibility=payload.visibility,
        rules_version=payload.rules_version,
        rules_json=payload.rules_json,
    )
    return BotValidationResponse(valid=len(issues) == 0, issues=issues)


@router.post("/{bot_id}/deploy", response_model=BotRuntimeResponse)
def deploy_bot_runtime(
    bot_id: str,
    payload: BotDeployRequest,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> BotRuntimeResponse:
    resolved_wallet = _resolve_wallet(user, payload.wallet_address)
    try:
        runtime = bot_runtime_engine.deploy_runtime(
            db,
            bot_id=bot_id,
            wallet_address=resolved_wallet,
            user_id=user.user_id,
            risk_policy_json=payload.risk_policy_json,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return BotRuntimeResponse.model_validate(runtime)


@router.post("/{bot_id}/pause", response_model=BotRuntimeResponse)
def pause_bot_runtime(
    bot_id: str,
    wallet_address: str | None = Query(default=None, min_length=8),
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> BotRuntimeResponse:
    resolved_wallet = _resolve_wallet(user, wallet_address)
    try:
        runtime = bot_runtime_engine.pause_runtime(
            db,
            bot_id=bot_id,
            wallet_address=resolved_wallet,
            user_id=user.user_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return BotRuntimeResponse.model_validate(runtime)


@router.post("/{bot_id}/resume", response_model=BotRuntimeResponse)
def resume_bot_runtime(
    bot_id: str,
    wallet_address: str | None = Query(default=None, min_length=8),
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> BotRuntimeResponse:
    resolved_wallet = _resolve_wallet(user, wallet_address)
    try:
        runtime = bot_runtime_engine.resume_runtime(
            db,
            bot_id=bot_id,
            wallet_address=resolved_wallet,
            user_id=user.user_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return BotRuntimeResponse.model_validate(runtime)


@router.post("/{bot_id}/stop", response_model=BotRuntimeResponse)
def stop_bot_runtime(
    bot_id: str,
    wallet_address: str | None = Query(default=None, min_length=8),
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> BotRuntimeResponse:
    resolved_wallet = _resolve_wallet(user, wallet_address)
    try:
        runtime = bot_runtime_engine.stop_runtime(
            db,
            bot_id=bot_id,
            wallet_address=resolved_wallet,
            user_id=user.user_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return BotRuntimeResponse.model_validate(runtime)


@router.get("/{bot_id}/events", response_model=list[BotExecutionEventResponse])
def list_bot_runtime_events(
    bot_id: str,
    wallet_address: str | None = Query(default=None, min_length=8),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> list[BotExecutionEventResponse]:
    resolved_wallet = _resolve_wallet(user, wallet_address)
    try:
        rows = bot_runtime_engine.list_runtime_events(
            db,
            bot_id=bot_id,
            wallet_address=resolved_wallet,
            user_id=user.user_id,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return [BotExecutionEventResponse.model_validate(row) for row in rows]


@router.get("/{bot_id}/health", response_model=RuntimeHealthResponse)
def get_runtime_health(
    bot_id: str,
    wallet_address: str | None = Query(default=None, min_length=8),
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> RuntimeHealthResponse:
    resolved_wallet = _resolve_wallet(user, wallet_address)
    try:
        payload = runtime_health_service.get_health(
            db,
            bot_id=bot_id,
            wallet_address=resolved_wallet,
            user_id=user.user_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return RuntimeHealthResponse.model_validate(payload)


@router.get("/{bot_id}/metrics", response_model=RuntimeMetricsResponse)
def get_runtime_metrics(
    bot_id: str,
    wallet_address: str | None = Query(default=None, min_length=8),
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> RuntimeMetricsResponse:
    resolved_wallet = _resolve_wallet(user, wallet_address)
    try:
        payload = runtime_observability_service.get_metrics(
            db,
            bot_id=bot_id,
            wallet_address=resolved_wallet,
            user_id=user.user_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return RuntimeMetricsResponse.model_validate(payload)


@router.get("/{bot_id}/runtime-overview", response_model=RuntimeOverviewResponse)
async def get_runtime_overview(
    bot_id: str,
    response: Response,
    wallet_address: str | None = Query(default=None, min_length=8),
    include_performance: bool = Query(default=False),
    performance_mode: Literal["full", "fast"] = Query(default="fast"),
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> RuntimeOverviewResponse:
    if not include_performance or performance_mode == "fast":
        response.headers["Cache-Control"] = "private, max-age=2, stale-while-revalidate=8"
    resolved_wallet = _resolve_wallet(user, wallet_address)
    try:
        payload = runtime_observability_service.get_overview(
            db,
            bot_id=bot_id,
            wallet_address=resolved_wallet,
            user_id=user.user_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    performance = None
    if include_performance:
        runtime = bot_runtime_engine.get_runtime(
            db,
            bot_id=bot_id,
            wallet_address=resolved_wallet,
            user_id=user.user_id,
        )
        if performance_mode == "fast":
            performance = _build_fast_runtime_performance(runtime)
        else:
            performance = await _build_runtime_performance(runtime)
    return RuntimeOverviewResponse.model_validate({**payload, "performance": performance})


@router.get("/{bot_id}/risk-state", response_model=RuntimeRiskStateResponse)
def get_runtime_risk_state(
    bot_id: str,
    wallet_address: str | None = Query(default=None, min_length=8),
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> RuntimeRiskStateResponse:
    resolved_wallet = _resolve_wallet(user, wallet_address)
    try:
        payload = runtime_observability_service.get_risk_state(
            db,
            bot_id=bot_id,
            wallet_address=resolved_wallet,
            user_id=user.user_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return RuntimeRiskStateResponse.model_validate(payload)


@router.patch("/{bot_id}/risk-state", response_model=RuntimeRiskStateResponse)
def patch_runtime_risk_state(
    bot_id: str,
    payload: RuntimeRiskStateUpdateRequest,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> RuntimeRiskStateResponse:
    resolved_wallet = _resolve_wallet(user, payload.wallet_address)
    try:
        state = runtime_observability_service.update_risk_policy(
            db,
            bot_id=bot_id,
            wallet_address=resolved_wallet,
            user_id=user.user_id,
            risk_policy_json=payload.risk_policy_json,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RuntimeRiskStateResponse.model_validate(state)
