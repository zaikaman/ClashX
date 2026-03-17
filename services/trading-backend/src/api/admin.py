from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from src.api.auth import AuthenticatedUser, require_authenticated_user
from src.core.settings import get_settings
from src.db.session import get_db
from src.models.league import League
from src.services.supabase_rest import SupabaseRestClient

router = APIRouter(prefix="/api/admin", tags=["admin"])
settings = get_settings()
supabase = SupabaseRestClient() if settings.use_supabase_api else None


class BotCompetitionCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    description: str = Field(default="", max_length=280)
    market_scope: str = Field(min_length=2, max_length=120)
    start_at: datetime
    end_at: datetime


class BotCompetitionResponse(BaseModel):
    id: str
    name: str
    description: str
    status: str
    market_scope: str
    start_at: datetime
    end_at: datetime
    created_at: datetime


@router.post("/bot-competitions", response_model=BotCompetitionResponse)
def create_bot_competition(
    payload: BotCompetitionCreateRequest,
    db: Session = Depends(get_db),
    _: AuthenticatedUser = Depends(require_authenticated_user),
) -> BotCompetitionResponse:
    if settings.use_supabase_api:
        assert supabase is not None
        row = supabase.insert(
            "leagues",
            {
                "id": str(uuid.uuid4()),
                "name": payload.name.strip(),
                "description": payload.description.strip(),
                "status": "draft",
                "market_scope": payload.market_scope.strip(),
                "start_at": payload.start_at.isoformat(),
                "end_at": payload.end_at.isoformat(),
                "rules_json": {
                    "competition_type": "bot",
                    "scoring": "pnl+streak",
                },
                "created_at": datetime.now().astimezone().isoformat(),
            },
        )[0]
        return BotCompetitionResponse.model_validate(row)

    competition = League(
        name=payload.name.strip(),
        description=payload.description.strip(),
        status="draft",
        market_scope=payload.market_scope.strip(),
        start_at=payload.start_at,
        end_at=payload.end_at,
        rules_json={
            "competition_type": "bot",
            "scoring": "pnl+streak",
        },
    )
    db.add(competition)
    db.commit()
    db.refresh(competition)
    return BotCompetitionResponse.model_validate(competition)


@router.get("/bot-competitions", response_model=list[BotCompetitionResponse])
def list_bot_competitions(
    db: Session = Depends(get_db),
    _: AuthenticatedUser = Depends(require_authenticated_user),
) -> list[BotCompetitionResponse]:
    if settings.use_supabase_api:
        assert supabase is not None
        rows = supabase.select("leagues", order="created_at.desc", limit=100)
        return [BotCompetitionResponse.model_validate(row) for row in rows]
    rows = list(db.scalars(select(League).order_by(desc(League.created_at)).limit(100)).all())
    return [BotCompetitionResponse.model_validate(row) for row in rows]
