from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.api.auth import AuthenticatedUser, ensure_wallet_owned, require_authenticated_user
from src.db.session import get_db
from src.services.leaderboard_engine import LeaderboardEngine
from src.services.league_service import LeagueService
from src.services.pacifica_client import PacificaClientError

router = APIRouter(prefix="/api/leagues", tags=["leagues"])
league_service = LeagueService()
leaderboard_engine = LeaderboardEngine()


class LeagueSummary(BaseModel):
    id: str
    name: str
    description: str
    status: str
    market_scope: str
    start_at: datetime
    end_at: datetime
    registration_count: int


class RegisterBotRequest(BaseModel):
    wallet_address: str = Field(min_length=8)
    display_name: str | None = Field(default=None, max_length=80)


class RegisterBotResponse(BaseModel):
    league_id: str
    user_id: str | None = None
    display_name: str | None = None
    already_registered: bool = False


class LeaderboardEntry(BaseModel):
    user_id: str
    display_name: str
    wallet_address: str
    rank: int
    unrealized_pnl: float
    realized_pnl: float
    win_streak: int
    captured_at: datetime


@router.get("", response_model=list[LeagueSummary])
def list_leagues(
    status: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[LeagueSummary]:
    return [LeagueSummary.model_validate(item) for item in league_service.list_leagues(db, status)]


@router.post("/{league_id}/register-bot", response_model=RegisterBotResponse)
async def register_bot(
    league_id: str,
    payload: RegisterBotRequest,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> RegisterBotResponse:
    ensure_wallet_owned(user, payload.wallet_address)
    try:
        result = league_service.register_bot(
            db,
            league_id=league_id,
            wallet_address=payload.wallet_address,
            display_name=payload.display_name,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        await leaderboard_engine.refresh_league(db, league_id)
    except PacificaClientError:
        pass
    return RegisterBotResponse.model_validate(result)


@router.post("/{league_id}/join", response_model=RegisterBotResponse)
async def join_league_legacy(
    league_id: str,
    payload: RegisterBotRequest,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> RegisterBotResponse:
    return await register_bot(league_id, payload, db, user)


@router.get("/{league_id}/leaderboard", response_model=list[LeaderboardEntry])
def get_leaderboard(
    league_id: str,
    limit: int = Query(default=100, ge=1, le=200),
    db: Session = Depends(get_db),
) -> list[LeaderboardEntry]:
    rows = league_service.get_leaderboard(db, league_id, limit)
    return [LeaderboardEntry.model_validate(row) for row in rows]
