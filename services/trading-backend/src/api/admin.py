from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from src.api.auth import AuthenticatedUser, require_authenticated_user
from src.db.session import get_db
from src.services.supabase_rest import SupabaseRestClient

router = APIRouter(prefix="/api/admin", tags=["admin"])
supabase = SupabaseRestClient()


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
def create_bot_competition(payload: BotCompetitionCreateRequest, db=Depends(get_db), _: AuthenticatedUser = Depends(require_authenticated_user)) -> BotCompetitionResponse:
    del db
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
            "rules_json": {"competition_type": "bot", "scoring": "pnl+streak"},
            "created_at": datetime.now().astimezone().isoformat(),
        },
    )[0]
    return BotCompetitionResponse.model_validate(row)


@router.get("/bot-competitions", response_model=list[BotCompetitionResponse])
def list_bot_competitions(db=Depends(get_db), _: AuthenticatedUser = Depends(require_authenticated_user)) -> list[BotCompetitionResponse]:
    del db
    rows = supabase.select("leagues", order="created_at.desc", limit=100)
    return [BotCompetitionResponse.model_validate(row) for row in rows]
