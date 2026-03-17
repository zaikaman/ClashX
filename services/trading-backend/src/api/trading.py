from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.api.auth import AuthenticatedUser, ensure_wallet_owned, require_authenticated_user
from src.db.session import get_db
from src.services.pacifica_client import PacificaClientError
from src.services.trading_service import TradingService

router = APIRouter(prefix="/api/trading", tags=["trading"])
trading_service = TradingService()


def _upstream_status(exc: PacificaClientError) -> int:
    if exc.status_code is not None and 400 <= exc.status_code < 500:
        return exc.status_code
    return 502


class TradingSummaryResponse(BaseModel):
    balance: float
    fee_level: int
    portfolio_value: float
    total_unrealized_pnl: float
    total_realized_pnl: float
    open_notional: float
    position_count: int
    open_order_count: int
    win_rate: float | None = None


class PortfolioPointResponse(BaseModel):
    timestamp: datetime
    equity: float


class MarketInfoResponse(BaseModel):
    symbol: str
    display_symbol: str
    mark_price: float
    mid_price: float = 0.0
    oracle_price: float = 0.0
    funding_rate: float
    next_funding_rate: float
    min_order_size: float
    max_order_size: float
    max_leverage: int
    isolated_only: bool
    tick_size: float = 0.0
    lot_size: float = 0.0
    open_interest: float = 0.0
    volume_24h: float = 0.0
    yesterday_price: float = 0.0
    updated_at: datetime | None = None


class TradingCandleResponse(BaseModel):
    open_time: int
    close_time: int
    symbol: str
    interval: str
    open: float
    close: float
    high: float
    low: float
    volume: float
    trade_count: int


class TradingPositionResponse(BaseModel):
    id: str
    symbol: str
    display_symbol: str
    side: Literal["long", "short"]
    quantity: float
    notional_usd: float
    entry_price: float
    mark_price: float
    margin: float
    leverage: float | None = None
    isolated: bool = False
    unrealized_pnl: float
    unrealized_pnl_pct: float
    updated_at: datetime | None = None


class TradingOrderResponse(BaseModel):
    id: str
    order_id: str
    client_order_id: str | None = None
    symbol: str
    display_symbol: str
    side: Literal["long", "short"]
    order_type: str
    quantity: float
    filled_quantity: float
    remaining_quantity: float
    notional_usd: float
    limit_price: float | None = None
    reduce_only: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None


class TradingFillResponse(BaseModel):
    id: str
    symbol: str
    display_symbol: str
    side: Literal["long", "short"]
    event_type: str
    quantity: float
    notional_usd: float
    fill_price: float
    fee: float
    pnl: float
    liquidity: Literal["maker", "taker"]
    filled_at: datetime | None = None


class TradingActivityResponse(BaseModel):
    id: str | None = None
    action: str
    payload: dict[str, Any]
    created_at: datetime | None = None


class TradingAccountResponse(BaseModel):
    user_id: str
    wallet_address: str
    account_address: str
    agent_wallet_address: str | None = None
    authorization_status: str
    can_trade: bool
    summary: TradingSummaryResponse
    portfolio: list[PortfolioPointResponse]
    markets: list[MarketInfoResponse]
    positions: list[TradingPositionResponse]
    orders: list[TradingOrderResponse]
    fills: list[TradingFillResponse]
    activity: list[TradingActivityResponse]
    updated_at: datetime


class CreateOrderRequest(BaseModel):
    wallet_address: str | None = Field(default=None, min_length=8)
    symbol: str = Field(min_length=2, max_length=32)
    side: Literal["long", "short"]
    order_type: Literal["market", "limit"] = "market"
    leverage: int = Field(ge=1, le=100)
    size_usd: float | None = Field(default=None, gt=0)
    quantity: float | None = Field(default=None, gt=0)
    limit_price: float | None = Field(default=None, gt=0)
    reduce_only: bool = False
    tif: str = Field(default="GTC", min_length=2, max_length=8)
    slippage_percent: float = Field(default=0.5, gt=0, le=5)


class OrderMutationResponse(BaseModel):
    status: str
    request_id: str
    network: str
    snapshot: TradingAccountResponse


def _resolve_wallet(user: AuthenticatedUser, wallet_address: str | None) -> str:
    resolved = wallet_address or (user.wallet_addresses[0] if user.wallet_addresses else None)
    if not resolved:
        raise HTTPException(status_code=400, detail="No authenticated wallet is available")
    ensure_wallet_owned(user, resolved)
    return resolved


@router.get("/account", response_model=TradingAccountResponse)
async def get_trading_account(
    wallet_address: str | None = Query(default=None, min_length=8),
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> TradingAccountResponse:
    resolved_wallet = _resolve_wallet(user, wallet_address)
    try:
        snapshot = await trading_service.get_account_snapshot(db, resolved_wallet)
    except PacificaClientError as exc:
        raise HTTPException(status_code=_upstream_status(exc), detail=str(exc)) from exc
    return TradingAccountResponse.model_validate(snapshot)


@router.get("/markets", response_model=list[MarketInfoResponse])
async def get_trading_markets() -> list[MarketInfoResponse]:
    try:
        markets = await trading_service.pacifica.get_markets()
    except PacificaClientError as exc:
        raise HTTPException(status_code=_upstream_status(exc), detail=str(exc)) from exc
    return [MarketInfoResponse.model_validate(item) for item in markets]


@router.get("/chart", response_model=list[TradingCandleResponse])
async def get_trading_chart(
    symbol: str = Query(min_length=2, max_length=32),
    interval: Literal["1m", "5m", "15m", "30m", "1h", "4h", "1d"] = Query(default="15m"),
    lookback: int = Query(default=300, ge=12, le=2_000),
    end_time: int | None = Query(default=None, ge=0),
) -> list[TradingCandleResponse]:
    interval_ms = {
        "1m": 60_000,
        "5m": 300_000,
        "15m": 900_000,
        "30m": 1_800_000,
        "1h": 3_600_000,
        "4h": 14_400_000,
        "1d": 86_400_000,
    }
    normalized_symbol = symbol.upper().removesuffix("-PERP")
    resolved_end_time = end_time or int(datetime.now().timestamp() * 1_000)
    start_time = resolved_end_time - interval_ms[interval] * lookback
    try:
        candles = await trading_service.pacifica.get_kline(
            normalized_symbol,
            interval=interval,
            start_time=start_time,
            end_time=resolved_end_time,
        )
    except PacificaClientError as exc:
        raise HTTPException(status_code=_upstream_status(exc), detail=str(exc)) from exc
    return [TradingCandleResponse.model_validate(item) for item in candles]


@router.get("/positions", response_model=list[TradingPositionResponse])
async def get_trading_positions(
    wallet_address: str | None = Query(default=None, min_length=8),
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> list[TradingPositionResponse]:
    resolved_wallet = _resolve_wallet(user, wallet_address)
    try:
        positions = await trading_service.list_positions(db, resolved_wallet)
    except PacificaClientError as exc:
        raise HTTPException(status_code=_upstream_status(exc), detail=str(exc)) from exc
    return [TradingPositionResponse.model_validate(item) for item in positions]


@router.get("/orders", response_model=list[TradingOrderResponse])
async def get_trading_orders(
    wallet_address: str | None = Query(default=None, min_length=8),
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> list[TradingOrderResponse]:
    resolved_wallet = _resolve_wallet(user, wallet_address)
    try:
        orders = await trading_service.list_orders(db, resolved_wallet)
    except PacificaClientError as exc:
        raise HTTPException(status_code=_upstream_status(exc), detail=str(exc)) from exc
    return [TradingOrderResponse.model_validate(item) for item in orders]


@router.post("/orders", response_model=OrderMutationResponse)
async def create_trading_order(
    payload: CreateOrderRequest,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> OrderMutationResponse:
    resolved_wallet = _resolve_wallet(user, payload.wallet_address)
    try:
        result = await trading_service.place_order(
            db,
            wallet_address=resolved_wallet,
            symbol=payload.symbol,
            side=payload.side,
            order_type=payload.order_type,
            leverage=payload.leverage,
            size_usd=payload.size_usd,
            quantity=payload.quantity,
            limit_price=payload.limit_price,
            reduce_only=payload.reduce_only,
            tif=payload.tif,
            slippage_percent=payload.slippage_percent,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PacificaClientError as exc:
        raise HTTPException(status_code=_upstream_status(exc), detail=str(exc)) from exc
    return OrderMutationResponse.model_validate(result)


@router.delete("/orders/{order_id}", response_model=OrderMutationResponse)
async def cancel_trading_order(
    order_id: str,
    wallet_address: str | None = Query(default=None, min_length=8),
    symbol: str = Query(min_length=2, max_length=32),
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> OrderMutationResponse:
    resolved_wallet = _resolve_wallet(user, wallet_address)
    try:
        result = await trading_service.cancel_order(
            db,
            wallet_address=resolved_wallet,
            symbol=symbol,
            order_id=order_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PacificaClientError as exc:
        raise HTTPException(status_code=_upstream_status(exc), detail=str(exc)) from exc
    return OrderMutationResponse.model_validate(result)
