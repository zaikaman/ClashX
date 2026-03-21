from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Any as Session

from src.api.auth import AuthenticatedUser, ensure_wallet_owned, require_authenticated_user
from src.db.session import get_db
from src.services.bot_builder_service import BotBuilderService
from src.services.bot_backtest_service import BotBacktestService

router = APIRouter(prefix="/api/backtests", tags=["backtests"])
bot_backtest_service = BotBacktestService()
bot_builder_service = BotBuilderService()


class BacktestRunRequest(BaseModel):
    wallet_address: str | None = Field(default=None, min_length=8)
    bot_id: str = Field(min_length=2)
    interval: str = Field(default="15m")
    start_time: int = Field(ge=0)
    end_time: int = Field(ge=0)
    initial_capital_usd: float = Field(default=10_000, gt=0)


class BacktestRunSummaryResponse(BaseModel):
    id: str
    bot_definition_id: str
    bot_name_snapshot: str
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
    updated_at: str


class BacktestsBootstrapResponse(BaseModel):
    bots: list[BacktestBotOptionResponse]
    runs: list[BacktestRunSummaryResponse]
    active_run: BacktestRunDetailResponse | None = None


def _resolve_wallet(user: AuthenticatedUser, wallet_address: str | None) -> str:
    resolved = wallet_address or (user.wallet_addresses[0] if user.wallet_addresses else None)
    if not resolved:
        raise HTTPException(status_code=400, detail="No wallet address available")
    ensure_wallet_owned(user, resolved)
    return resolved


@router.post("/runs", response_model=BacktestRunDetailResponse)
async def create_backtest_run(
    payload: BacktestRunRequest,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> BacktestRunDetailResponse:
    resolved_wallet = _resolve_wallet(user, payload.wallet_address)
    try:
        run = await bot_backtest_service.run_backtest(
            db,
            bot_id=payload.bot_id,
            wallet_address=resolved_wallet,
            user_id=user.user_id,
            interval=payload.interval,
            start_time=payload.start_time,
            end_time=payload.end_time,
            initial_capital_usd=payload.initial_capital_usd,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return BacktestRunDetailResponse.model_validate(run)


@router.get("/runs", response_model=list[BacktestRunSummaryResponse])
def list_backtest_runs(
    wallet_address: str | None = Query(default=None, min_length=8),
    bot_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> list[BacktestRunSummaryResponse]:
    resolved_wallet = _resolve_wallet(user, wallet_address)
    return [
        BacktestRunSummaryResponse.model_validate(row)
        for row in bot_backtest_service.list_runs(
            db,
            wallet_address=resolved_wallet,
            user_id=user.user_id,
            bot_id=bot_id,
        )
    ]


@router.get("/bootstrap", response_model=BacktestsBootstrapResponse)
def get_backtests_bootstrap(
    wallet_address: str | None = Query(default=None, min_length=8),
    bot_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> BacktestsBootstrapResponse:
    resolved_wallet = _resolve_wallet(user, wallet_address)
    bots = bot_builder_service.list_bots(db, wallet_address=resolved_wallet)
    runs = bot_backtest_service.list_runs(
        db,
        wallet_address=resolved_wallet,
        user_id=user.user_id,
        bot_id=bot_id,
    )
    active_run = None
    if runs:
        try:
            active_run = bot_backtest_service.get_run(
                db,
                run_id=str(runs[0]["id"]),
                wallet_address=resolved_wallet,
                user_id=user.user_id,
            )
        except ValueError:
            active_run = None
    return BacktestsBootstrapResponse.model_validate(
        {
            "bots": bots,
            "runs": runs,
            "active_run": active_run,
        }
    )


@router.get("/runs/{run_id}", response_model=BacktestRunDetailResponse)
def get_backtest_run(
    run_id: str,
    wallet_address: str | None = Query(default=None, min_length=8),
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> BacktestRunDetailResponse:
    resolved_wallet = _resolve_wallet(user, wallet_address)
    try:
        run = bot_backtest_service.get_run(
            db,
            run_id=run_id,
            wallet_address=resolved_wallet,
            user_id=user.user_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return BacktestRunDetailResponse.model_validate(run)
