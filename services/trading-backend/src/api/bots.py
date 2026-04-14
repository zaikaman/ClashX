from __future__ import annotations
from datetime import datetime
from typing import Literal
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from typing import Any as Session

from src.api.auth import AuthenticatedUser, ensure_wallet_owned, require_authenticated_user, resolve_app_user_id
from src.api.marketplace import marketplace_service
from src.db.session import get_db
from src.services.bot_builder_service import BotBuilderService
from src.services.bot_performance_service import BotPerformanceService
from src.services.bot_runtime_engine import BotRuntimeEngine
from src.services.bot_runtime_snapshot_service import BotRuntimeSnapshotService
from src.services.runtime_health_service import RuntimeHealthService
from src.services.runtime_observability_service import RuntimeObservabilityService

router = APIRouter(prefix="/api/bots", tags=["bots"])
bot_builder_service = BotBuilderService()
bot_runtime_engine = BotRuntimeEngine()
bot_performance_service = BotPerformanceService()
bot_runtime_snapshot_service = BotRuntimeSnapshotService()
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
    sync_runtime_allowed_symbols: bool | None = None


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


class BotExecutionEventSummaryResponse(BaseModel):
    id: str
    runtime_id: str
    event_type: str
    decision_summary: str
    action_type: str | None = None
    symbol: str | None = None
    leverage: float | None = None
    size_usd: float | None = None
    status: str
    error_reason: str | None = None
    outcome_summary: str
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


def _resolve_wallet_user_id(user: AuthenticatedUser, wallet_address: str | None) -> tuple[str, str]:
    resolved_wallet = _resolve_wallet(user, wallet_address)
    return resolved_wallet, resolve_app_user_id(user, resolved_wallet)


def _schedule_marketplace_refresh(background_tasks: BackgroundTasks) -> None:
    background_tasks.add_task(marketplace_service.refresh_after_publication, limit=120)


async def _build_runtime_performance(runtime: dict[str, Any] | None) -> RuntimePerformanceResponse | None:
    if runtime is None:
        return None
    payload = await bot_performance_service.calculate_runtime_performance(runtime)
    return RuntimePerformanceResponse.model_validate(payload)


def _normalize_symbol(value: Any) -> str:
    return str(value or "").upper().replace("-PERP", "").strip()


def _normalize_position_side(value: Any) -> str:
    normalized = str(value or "").lower().strip()
    if normalized in {"bid", "long", "buy"}:
        return "long"
    if normalized in {"ask", "short", "sell"}:
        return "short"
    return normalized


def _to_float(value: Any) -> float:
    try:
        if value in (None, ""):
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _build_fast_runtime_positions(
    runtime_state: dict[str, Any],
    *,
    live_position_lookup: dict[str, dict[str, Any]],
    live_positions_loaded: bool,
) -> tuple[list[RuntimePositionResponse], float]:
    managed_positions = runtime_state.get("managed_positions")
    if not isinstance(managed_positions, dict):
        return [], 0.0

    positions: list[RuntimePositionResponse] = []
    unrealized_total = 0.0
    for managed_position in managed_positions.values():
        if not isinstance(managed_position, dict):
            continue
        symbol = _normalize_symbol(managed_position.get("symbol"))
        amount = abs(_to_float(managed_position.get("amount")))
        side = _normalize_position_side(managed_position.get("side"))
        entry_price = _to_float(managed_position.get("entry_price"))
        if not symbol or amount <= 0 or entry_price <= 0 or side not in {"long", "short"}:
            continue

        live_position = live_position_lookup.get(symbol)
        live_side = _normalize_position_side((live_position or {}).get("side"))
        if live_positions_loaded and (
            live_position is None or live_side != side or abs(_to_float((live_position or {}).get("amount"))) <= 0
        ):
            continue

        mark_price = _to_float((live_position or {}).get("mark_price")) or _to_float(managed_position.get("mark_price"))
        if mark_price <= 0:
            mark_price = entry_price

        unrealized_pnl = (mark_price - entry_price) * amount if side == "long" else (entry_price - mark_price) * amount
        unrealized_total += unrealized_pnl
        positions.append(
            RuntimePositionResponse(
                symbol=symbol,
                side=side,
                amount=round(amount, 8),
                entry_price=round(entry_price, 8),
                mark_price=round(mark_price, 8),
                unrealized_pnl=round(unrealized_pnl, 8),
            )
        )

    return positions, round(unrealized_total, 2)


def _build_fast_runtime_performance(
    runtime: dict[str, Any] | None,
    *,
    live_position_lookup: dict[str, dict[str, Any]] | None = None,
    live_positions_loaded: bool = False,
) -> RuntimePerformanceResponse | None:
    if runtime is None:
        return None
    risk_policy = runtime.get("risk_policy_json") if isinstance(runtime.get("risk_policy_json"), dict) else {}
    runtime_state = risk_policy.get("_runtime_state") if isinstance(risk_policy.get("_runtime_state"), dict) else {}

    allocated_capital = float(runtime_state.get("allocated_capital_usd") or risk_policy.get("allocated_capital_usd") or 0.0)
    pnl_total = float(runtime_state.get("pnl_total_usd") or 0.0)
    pnl_realized = float(runtime_state.get("realized_pnl_usd") or 0.0)
    pnl_unrealized = float(runtime_state.get("unrealized_pnl_usd") or 0.0)
    win_streak = int(runtime_state.get("win_streak") or 0)
    positions, live_unrealized = _build_fast_runtime_positions(
        runtime_state,
        live_position_lookup=live_position_lookup or {},
        live_positions_loaded=live_positions_loaded,
    )
    if positions:
        pnl_unrealized = live_unrealized
        pnl_total = pnl_realized + pnl_unrealized
    pnl_total_pct = (pnl_total / allocated_capital * 100.0) if allocated_capital > 0 else 0.0

    return RuntimePerformanceResponse(
        pnl_total=pnl_total,
        pnl_total_pct=pnl_total_pct,
        pnl_realized=pnl_realized,
        pnl_unrealized=pnl_unrealized,
        win_streak=win_streak,
        positions=positions,
    )


def _snapshot_overview_payload(snapshot: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(snapshot, dict):
        return None
    payload = bot_runtime_snapshot_service.snapshot_to_overview(snapshot)
    health = payload.get("health")
    metrics = payload.get("metrics")
    if not isinstance(health, dict) or not isinstance(metrics, dict) or not health or not metrics:
        return None
    return payload


def _snapshot_performance_payload(snapshot: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(snapshot, dict):
        return None
    payload = bot_runtime_snapshot_service.snapshot_to_performance(snapshot)
    if not isinstance(payload, dict) or not payload:
        return None
    return payload


@router.get("", response_model=list[BotFleetItemResponse])
async def list_bots(
    response: Response,
    wallet_address: str | None = Query(default=None, min_length=8),
    include_performance: bool = Query(default=True),
    performance_mode: Literal["full", "fast"] = Query(default="full"),
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> list[BotFleetItemResponse]:
    if include_performance:
        response.headers["Cache-Control"] = "private, max-age=2, stale-while-revalidate=8"
    resolved_wallet, resolved_user_id = _resolve_wallet_user_id(user, wallet_address)
    definitions = bot_builder_service.list_bots(db, wallet_address=resolved_wallet)
    runtimes_for_wallet = bot_runtime_engine.list_runtimes_for_wallet(
        db,
        wallet_address=resolved_wallet,
        user_id=resolved_user_id,
    )
    runtimes = {runtime["bot_definition_id"]: runtime for runtime in runtimes_for_wallet}
    snapshots_by_bot = (
        bot_runtime_snapshot_service.list_snapshots_for_wallet(resolved_wallet)
        if include_performance and runtimes_for_wallet
        else {}
    )
    performances: list[RuntimePerformanceResponse | None]
    if include_performance and runtimes_for_wallet and performance_mode == "fast":
        live_runtime_ids = {
            str(runtime.get("id") or "").strip()
            for runtime in runtimes_for_wallet
            if str(runtime.get("status") or "") in {"active", "paused"}
            and str(runtime.get("id") or "").strip()
        }
        fresh_performance_by_runtime = (
            await bot_performance_service.get_cached_runtimes_performance_map(runtimes_for_wallet)
            if live_runtime_ids
            else {}
        )
        performances = [
            (
                RuntimePerformanceResponse.model_validate(fresh_payload)
                if (
                    (runtime := runtimes.get(row["id"])) is not None
                    and (runtime_id := str(runtime.get("id") or "").strip())
                    and runtime_id in live_runtime_ids
                    and (fresh_payload := fresh_performance_by_runtime.get(runtime_id)) is not None
                )
                else RuntimePerformanceResponse.model_validate(snapshot_payload)
                if (snapshot_payload := _snapshot_performance_payload(snapshots_by_bot.get(row["id"]))) is not None
                else _build_fast_runtime_performance(runtimes.get(row["id"]))
            )
            for row in definitions
        ]
    elif include_performance and runtimes_for_wallet:
        performance_by_runtime: dict[str, dict[str, Any]] = {}
        missing_runtimes: list[dict[str, Any]] = []
        for runtime in runtimes_for_wallet:
            snapshot_payload = _snapshot_performance_payload(
                snapshots_by_bot.get(str(runtime.get("bot_definition_id") or "").strip())
            )
            runtime_id = str(runtime.get("id") or "").strip()
            if snapshot_payload is not None and runtime_id:
                performance_by_runtime[runtime_id] = snapshot_payload
            else:
                missing_runtimes.append(runtime)
        if missing_runtimes:
            performance_by_runtime.update(
                await bot_performance_service.get_cached_runtimes_performance_map(missing_runtimes)
            )
        performances = [
            RuntimePerformanceResponse.model_validate(payload)
            if (payload := performance_by_runtime.get(str((runtimes.get(row["id"]) or {}).get("id") or "").strip()))
            is not None
            else None
            for row in definitions
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
    background_tasks: BackgroundTasks,
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
    if str(bot.get("visibility") or "") == "public":
        _schedule_marketplace_refresh(background_tasks)
    return BotDefinitionResponse.model_validate(bot)


@router.get("/runtime-overviews", response_model=dict[str, RuntimeOverviewResponse])
async def list_runtime_overviews(
    response: Response,
    wallet_address: str | None = Query(default=None, min_length=8),
    include_performance: bool = Query(default=False),
    performance_mode: Literal["full", "fast"] = Query(default="fast"),
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> dict[str, RuntimeOverviewResponse]:
    response.headers["Cache-Control"] = "private, max-age=2, stale-while-revalidate=8"
    resolved_wallet, resolved_user_id = _resolve_wallet_user_id(user, wallet_address)
    definitions = bot_builder_service.list_bots(db, wallet_address=resolved_wallet)
    runtimes_for_wallet = bot_runtime_engine.list_runtimes_for_wallet(
        db,
        wallet_address=resolved_wallet,
        user_id=resolved_user_id,
    )
    runtime_by_bot = {
        str(runtime.get("bot_definition_id") or "").strip(): runtime
        for runtime in runtimes_for_wallet
        if str(runtime.get("bot_definition_id") or "").strip()
    }
    snapshots_by_bot = bot_runtime_snapshot_service.list_snapshots_for_wallet(resolved_wallet)
    payload: dict[str, dict[str, Any]] = {}
    missing_live_overviews = False
    for definition in definitions:
        bot_id = str(definition.get("id") or "").strip()
        if not bot_id:
            continue
        snapshot_payload = _snapshot_overview_payload(snapshots_by_bot.get(bot_id))
        if snapshot_payload is not None:
            payload[bot_id] = snapshot_payload
            continue
        if bot_id in runtime_by_bot:
            missing_live_overviews = True
            continue
        payload[bot_id] = runtime_observability_service.draft_overview_payload()
    if missing_live_overviews:
        live_payload = runtime_observability_service.get_overviews_for_wallet(
            db,
            wallet_address=resolved_wallet,
            user_id=resolved_user_id,
        )
        for definition in definitions:
            bot_id = str(definition.get("id") or "").strip()
            if bot_id and bot_id not in payload:
                payload[bot_id] = live_payload.get(bot_id) or runtime_observability_service.draft_overview_payload()
    performance_by_bot: dict[str, RuntimePerformanceResponse | None] = {
        bot_id: None
        for bot_id in payload
    }
    if include_performance and runtimes_for_wallet:
        if performance_mode == "fast":
            performance_by_bot.update(
                {
                    bot_id: (
                        RuntimePerformanceResponse.model_validate(snapshot_payload)
                        if (snapshot_payload := _snapshot_performance_payload(snapshots_by_bot.get(bot_id)))
                        is not None
                        else _build_fast_runtime_performance(runtime)
                    )
                    for runtime in runtimes_for_wallet
                    if (bot_id := str(runtime.get("bot_definition_id") or "").strip())
                }
            )
        else:
            performance_by_runtime: dict[str, dict[str, Any]] = {}
            missing_runtimes: list[dict[str, Any]] = []
            for runtime in runtimes_for_wallet:
                bot_id = str(runtime.get("bot_definition_id") or "").strip()
                runtime_id = str(runtime.get("id") or "").strip()
                snapshot_payload = _snapshot_performance_payload(snapshots_by_bot.get(bot_id))
                if snapshot_payload is not None and runtime_id:
                    performance_by_runtime[runtime_id] = snapshot_payload
                else:
                    missing_runtimes.append(runtime)
            if missing_runtimes:
                performance_by_runtime.update(
                    await bot_performance_service.get_cached_runtimes_performance_map(missing_runtimes)
                )
            performance_by_bot.update(
                {
                    bot_id: (
                        RuntimePerformanceResponse.model_validate(payload_by_runtime)
                        if (payload_by_runtime := performance_by_runtime.get(str(runtime.get("id") or "").strip()))
                        is not None
                        else None
                    )
                    for runtime in runtimes_for_wallet
                    if (bot_id := str(runtime.get("bot_definition_id") or "").strip())
                }
            )
    return {
        bot_id: RuntimeOverviewResponse.model_validate(
            {
                **overview,
                "performance": performance_by_bot.get(bot_id),
            }
        )
        for bot_id, overview in payload.items()
    }


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
    background_tasks: BackgroundTasks,
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
            sync_runtime_allowed_symbols=bool(payload.sync_runtime_allowed_symbols),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if str(bot.get("visibility") or "") == "public" or payload.visibility is not None:
        _schedule_marketplace_refresh(background_tasks)
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
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> BotRuntimeResponse:
    resolved_wallet, resolved_user_id = _resolve_wallet_user_id(user, payload.wallet_address)
    try:
        runtime = bot_runtime_engine.deploy_runtime(
            db,
            bot_id=bot_id,
            wallet_address=resolved_wallet,
            user_id=resolved_user_id,
            risk_policy_json=payload.risk_policy_json,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _schedule_marketplace_refresh(background_tasks)
    return BotRuntimeResponse.model_validate(runtime)


@router.post("/{bot_id}/pause", response_model=BotRuntimeResponse)
def pause_bot_runtime(
    bot_id: str,
    wallet_address: str | None = Query(default=None, min_length=8),
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> BotRuntimeResponse:
    resolved_wallet, resolved_user_id = _resolve_wallet_user_id(user, wallet_address)
    try:
        runtime = bot_runtime_engine.pause_runtime(
            db,
            bot_id=bot_id,
            wallet_address=resolved_wallet,
            user_id=resolved_user_id,
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
    resolved_wallet, resolved_user_id = _resolve_wallet_user_id(user, wallet_address)
    try:
        runtime = bot_runtime_engine.resume_runtime(
            db,
            bot_id=bot_id,
            wallet_address=resolved_wallet,
            user_id=resolved_user_id,
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
    resolved_wallet, resolved_user_id = _resolve_wallet_user_id(user, wallet_address)
    try:
        runtime = bot_runtime_engine.stop_runtime(
            db,
            bot_id=bot_id,
            wallet_address=resolved_wallet,
            user_id=resolved_user_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return BotRuntimeResponse.model_validate(runtime)


@router.get("/{bot_id}/events", response_model=list[BotExecutionEventSummaryResponse])
def list_bot_runtime_events(
    bot_id: str,
    response: Response,
    wallet_address: str | None = Query(default=None, min_length=8),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> list[BotExecutionEventSummaryResponse]:
    response.headers["Cache-Control"] = "private, max-age=2, stale-while-revalidate=8"
    resolved_wallet, resolved_user_id = _resolve_wallet_user_id(user, wallet_address)
    try:
        rows = bot_runtime_engine.list_runtime_events(
            db,
            bot_id=bot_id,
            wallet_address=resolved_wallet,
            user_id=resolved_user_id,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return [BotExecutionEventSummaryResponse.model_validate(row) for row in rows]


@router.get("/{bot_id}/health", response_model=RuntimeHealthResponse)
def get_runtime_health(
    bot_id: str,
    wallet_address: str | None = Query(default=None, min_length=8),
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> RuntimeHealthResponse:
    resolved_wallet, resolved_user_id = _resolve_wallet_user_id(user, wallet_address)
    snapshot = bot_runtime_snapshot_service.get_snapshot_for_bot(bot_id=bot_id, wallet_address=resolved_wallet)
    snapshot_payload = _snapshot_overview_payload(snapshot)
    if snapshot_payload is not None:
        return RuntimeHealthResponse.model_validate(snapshot_payload["health"])
    try:
        payload = runtime_health_service.get_health(
            db,
            bot_id=bot_id,
            wallet_address=resolved_wallet,
            user_id=resolved_user_id,
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
    resolved_wallet, resolved_user_id = _resolve_wallet_user_id(user, wallet_address)
    snapshot = bot_runtime_snapshot_service.get_snapshot_for_bot(bot_id=bot_id, wallet_address=resolved_wallet)
    snapshot_payload = _snapshot_overview_payload(snapshot)
    if snapshot_payload is not None:
        return RuntimeMetricsResponse.model_validate(snapshot_payload["metrics"])
    try:
        payload = runtime_observability_service.get_metrics(
            db,
            bot_id=bot_id,
            wallet_address=resolved_wallet,
            user_id=resolved_user_id,
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
    performance_mode: Literal["full", "fast"] = Query(default="full"),
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> RuntimeOverviewResponse:
    response.headers["Cache-Control"] = "private, max-age=2, stale-while-revalidate=8"
    resolved_wallet, resolved_user_id = _resolve_wallet_user_id(user, wallet_address)
    snapshot = bot_runtime_snapshot_service.get_snapshot_for_bot(bot_id=bot_id, wallet_address=resolved_wallet)
    payload = _snapshot_overview_payload(snapshot)
    if payload is None:
        try:
            payload = runtime_observability_service.get_overview(
                db,
                bot_id=bot_id,
                wallet_address=resolved_wallet,
                user_id=resolved_user_id,
            )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
    performance = None
    if include_performance:
        snapshot_performance = _snapshot_performance_payload(snapshot)
        if snapshot_performance is not None:
            performance = RuntimePerformanceResponse.model_validate(snapshot_performance)
        if performance is None and performance_mode == "fast":
            runtime = bot_runtime_engine.get_runtime(
                db,
                bot_id=bot_id,
                wallet_address=resolved_wallet,
                user_id=resolved_user_id,
            )
            performance = _build_fast_runtime_performance(runtime)
        elif performance is None:
            runtime = bot_runtime_engine.get_runtime(
                db,
                bot_id=bot_id,
                wallet_address=resolved_wallet,
                user_id=resolved_user_id,
            )
            sibling_runtimes = bot_runtime_engine.list_runtimes_for_wallet(
                db,
                wallet_address=resolved_wallet,
                user_id=resolved_user_id,
            )
            cached_performance = await bot_performance_service.get_cached_runtime_performance(
                runtime,
                sibling_runtimes=sibling_runtimes,
            )
            performance = (
                RuntimePerformanceResponse.model_validate(cached_performance)
                if cached_performance is not None
                else None
            )
    return RuntimeOverviewResponse.model_validate({**payload, "performance": performance})


@router.get("/{bot_id}/risk-state", response_model=RuntimeRiskStateResponse)
def get_runtime_risk_state(
    bot_id: str,
    wallet_address: str | None = Query(default=None, min_length=8),
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> RuntimeRiskStateResponse:
    resolved_wallet, resolved_user_id = _resolve_wallet_user_id(user, wallet_address)
    try:
        payload = runtime_observability_service.get_risk_state(
            db,
            bot_id=bot_id,
            wallet_address=resolved_wallet,
            user_id=resolved_user_id,
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
    resolved_wallet, resolved_user_id = _resolve_wallet_user_id(user, payload.wallet_address)
    try:
        state = runtime_observability_service.update_risk_policy(
            db,
            bot_id=bot_id,
            wallet_address=resolved_wallet,
            user_id=resolved_user_id,
            risk_policy_json=payload.risk_policy_json,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RuntimeRiskStateResponse.model_validate(state)
