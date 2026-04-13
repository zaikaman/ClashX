from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Any as Session

from src.api.auth import AuthenticatedUser, ensure_wallet_owned, require_authenticated_user, resolve_app_user_id
from src.db.session import get_db
from src.services.ai_job_service import AiJobStatus, AiJobType, AiJobService, JOB_STATUS_COLUMNS
from src.services.bot_builder_service import BotBuilderService
from src.services.bot_backtest_service import BotBacktestService

router = APIRouter(prefix="/api/backtests", tags=["backtests"])
bot_backtest_service = BotBacktestService()
bot_builder_service = BotBuilderService()
ai_job_service = AiJobService()
ACTIVE_BACKTEST_JOB_STATUSES: list[AiJobStatus] = ["queued", "running", "failed"]
DEFAULT_BACKTEST_RUN_HISTORY_LIMIT = 50
BOOTSTRAP_BACKTEST_RUN_HISTORY_LIMIT = 40


class BacktestAssumptionConfigRequest(BaseModel):
    fee_bps: float = Field(default=0.0, ge=0)
    slippage_bps: float = Field(default=0.0, ge=0)
    funding_bps_per_interval: float = Field(default=0.0)


class BacktestRunRequest(BaseModel):
    wallet_address: str | None = Field(default=None, min_length=8)
    bot_id: str = Field(min_length=2)
    interval: str | None = Field(default=None)
    start_time: int = Field(ge=0)
    end_time: int = Field(ge=0)
    initial_capital_usd: float = Field(default=10_000, gt=0)
    assumptions: BacktestAssumptionConfigRequest | None = None


class BacktestRunSummaryResponse(BaseModel):
    id: str
    bot_definition_id: str
    bot_name_snapshot: str
    market_scope_snapshot: str | None = None
    strategy_type_snapshot: str | None = None
    interval: str
    start_time: int
    end_time: int
    initial_capital_usd: float
    execution_model: str
    pnl_total: float
    pnl_total_pct: float
    max_drawdown_pct: float
    win_rate: float
    trade_count: int
    status: str
    assumption_config_json: dict[str, Any] = Field(default_factory=dict)
    failure_reason: str | None = None
    created_at: str
    completed_at: str | None = None
    updated_at: str


class BacktestRunDetailResponse(BacktestRunSummaryResponse):
    user_id: str
    wallet_address: str
    rules_snapshot_json: dict[str, Any]
    result_json: dict[str, Any]


class BacktestBotOptionResponse(BaseModel):
    id: str
    name: str
    description: str
    strategy_type: str
    market_scope: str
    inferred_backtest_interval: str
    updated_at: str


class BacktestRunJobCreateResponse(BaseModel):
    id: str
    jobType: AiJobType
    status: AiJobStatus


class BacktestRunJobStatusResponse(BaseModel):
    id: str
    jobType: AiJobType
    status: AiJobStatus
    progress: dict[str, Any] = Field(default_factory=dict)
    result: BacktestRunDetailResponse | None = None
    errorDetail: str | None = None
    createdAt: str | None = None
    updatedAt: str | None = None
    completedAt: str | None = None


class BacktestsBootstrapResponse(BaseModel):
    bots: list[BacktestBotOptionResponse]
    runs: list[BacktestRunSummaryResponse]
    jobs: list[BacktestRunJobStatusResponse] = Field(default_factory=list)


def _resolve_wallet(user: AuthenticatedUser, wallet_address: str | None) -> str:
    resolved = wallet_address or (user.wallet_addresses[0] if user.wallet_addresses else None)
    if not resolved:
        raise HTTPException(status_code=400, detail="No wallet address available")
    ensure_wallet_owned(user, resolved)
    return resolved


def _resolve_wallet_user_id(user: AuthenticatedUser, wallet_address: str | None) -> tuple[str, str]:
    resolved_wallet = _resolve_wallet(user, wallet_address)
    return resolved_wallet, resolve_app_user_id(user, resolved_wallet)


def _serialize_backtest_job(
    job: dict[str, Any],
    *,
    resolved_run: dict[str, Any] | None = None,
) -> BacktestRunJobStatusResponse:
    result_payload = job.get("result_payload_json") if isinstance(job.get("result_payload_json"), dict) else {}
    progress_payload = (
        {key: value for key, value in result_payload.items() if key != "checkpoint"}
        if result_payload.get("type") == "progress"
        else {}
    )
    run_payload = resolved_run if isinstance(resolved_run, dict) else None
    if run_payload is None and result_payload.get("type") == "result" and isinstance(result_payload.get("run"), dict):
        run_payload = result_payload.get("run")
    return BacktestRunJobStatusResponse(
        id=str(job.get("id") or ""),
        jobType="backtest_run",
        status=str(job.get("status") or "queued"),
        progress=progress_payload,
        result=BacktestRunDetailResponse.model_validate(run_payload) if run_payload is not None else None,
        errorDetail=str(job.get("error_detail") or "") or None,
        createdAt=job.get("created_at"),
        updatedAt=job.get("updated_at"),
        completedAt=job.get("completed_at"),
    )


@router.post("/runs", response_model=BacktestRunDetailResponse)
async def create_backtest_run(
    payload: BacktestRunRequest,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> BacktestRunDetailResponse:
    resolved_wallet, resolved_user_id = _resolve_wallet_user_id(user, payload.wallet_address)
    try:
        run = await bot_backtest_service.run_backtest(
            db,
            bot_id=payload.bot_id,
            wallet_address=resolved_wallet,
            user_id=resolved_user_id,
            interval=payload.interval,
            start_time=payload.start_time,
            end_time=payload.end_time,
            initial_capital_usd=payload.initial_capital_usd,
            assumptions=payload.assumptions.model_dump() if payload.assumptions is not None else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return BacktestRunDetailResponse.model_validate(run)


@router.post("/runs/jobs", response_model=BacktestRunJobCreateResponse)
async def create_backtest_run_job(
    payload: BacktestRunRequest,
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> BacktestRunJobCreateResponse:
    resolved_wallet, resolved_user_id = _resolve_wallet_user_id(user, payload.wallet_address)
    job = ai_job_service.create_job(
        job_type="backtest_run",
        wallet_address=resolved_wallet,
        request_payload={
            "bot_id": payload.bot_id,
            "wallet_address": resolved_wallet,
            "user_id": resolved_user_id,
            "interval": payload.interval,
            "start_time": payload.start_time,
            "end_time": payload.end_time,
            "initial_capital_usd": payload.initial_capital_usd,
            "assumptions": payload.assumptions.model_dump() if payload.assumptions is not None else None,
        },
    )
    return BacktestRunJobCreateResponse(id=job["id"], jobType="backtest_run", status="queued")


@router.get("/runs/jobs", response_model=list[BacktestRunJobStatusResponse])
async def list_backtest_run_jobs(
    wallet_address: str | None = Query(default=None, min_length=8),
    limit: int = Query(default=10, ge=1, le=25),
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> list[BacktestRunJobStatusResponse]:
    resolved_wallet = _resolve_wallet(user, wallet_address)
    jobs = ai_job_service.list_jobs(
        job_type="backtest_run",
        statuses=ACTIVE_BACKTEST_JOB_STATUSES,
        wallet_addresses=[resolved_wallet],
        order="created_at.desc",
        limit=limit,
        columns=JOB_STATUS_COLUMNS,
    )
    return [_serialize_backtest_job(job) for job in jobs]


@router.get("/runs/jobs/{job_id}", response_model=BacktestRunJobStatusResponse)
async def get_backtest_run_job(
    job_id: str,
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> BacktestRunJobStatusResponse:
    job = ai_job_service.get_job_for_wallets(
        job_id=job_id,
        wallet_addresses=user.wallet_addresses,
        columns=JOB_STATUS_COLUMNS,
    )
    if job is None or job.get("job_type") != "backtest_run":
        raise HTTPException(status_code=404, detail="Backtest job not found.")
    resolved_wallet, resolved_user_id = _resolve_wallet_user_id(
        user,
        str(job.get("wallet_address") or "").strip() or None,
    )
    result_payload = job.get("result_payload_json") if isinstance(job.get("result_payload_json"), dict) else {}
    resolved_run = None
    run_id = str(result_payload.get("run_id") or "").strip()
    if result_payload.get("type") == "result" and run_id:
        try:
            resolved_run = bot_backtest_service.get_run(
                None,
                run_id=run_id,
                wallet_address=resolved_wallet,
                user_id=resolved_user_id,
            )
        except ValueError:
            resolved_run = None
    return _serialize_backtest_job(job, resolved_run=resolved_run)


@router.get("/runs", response_model=list[BacktestRunSummaryResponse])
def list_backtest_runs(
    wallet_address: str | None = Query(default=None, min_length=8),
    bot_id: str | None = Query(default=None),
    limit: int = Query(default=DEFAULT_BACKTEST_RUN_HISTORY_LIMIT, ge=1, le=200),
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> list[BacktestRunSummaryResponse]:
    resolved_wallet, resolved_user_id = _resolve_wallet_user_id(user, wallet_address)
    return [
        BacktestRunSummaryResponse.model_validate(row)
        for row in bot_backtest_service.list_runs(
            db,
            wallet_address=resolved_wallet,
            user_id=resolved_user_id,
            bot_id=bot_id,
            limit=limit,
        )
    ]


@router.get("/bootstrap", response_model=BacktestsBootstrapResponse)
def get_backtests_bootstrap(
    wallet_address: str | None = Query(default=None, min_length=8),
    bot_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> BacktestsBootstrapResponse:
    resolved_wallet, resolved_user_id = _resolve_wallet_user_id(user, wallet_address)
    bots = bot_builder_service.list_bots(db, wallet_address=resolved_wallet)
    runs = bot_backtest_service.list_runs(
        db,
        wallet_address=resolved_wallet,
        user_id=resolved_user_id,
        bot_id=bot_id,
        limit=BOOTSTRAP_BACKTEST_RUN_HISTORY_LIMIT,
    )
    jobs = ai_job_service.list_jobs(
        job_type="backtest_run",
        statuses=ACTIVE_BACKTEST_JOB_STATUSES,
        wallet_addresses=[resolved_wallet],
        order="created_at.desc",
        limit=10,
        columns=JOB_STATUS_COLUMNS,
    )
    return BacktestsBootstrapResponse.model_validate(
        {
            "bots": bots,
            "runs": runs,
            "jobs": [_serialize_backtest_job(job).model_dump(mode="json") for job in jobs],
        }
    )


@router.get("/runs/{run_id}", response_model=BacktestRunDetailResponse)
def get_backtest_run(
    run_id: str,
    wallet_address: str | None = Query(default=None, min_length=8),
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> BacktestRunDetailResponse:
    resolved_wallet, resolved_user_id = _resolve_wallet_user_id(user, wallet_address)
    try:
        run = bot_backtest_service.get_run(
            db,
            run_id=run_id,
            wallet_address=resolved_wallet,
            user_id=resolved_user_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return BacktestRunDetailResponse.model_validate(run)
