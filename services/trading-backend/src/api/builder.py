from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.services.builder_ai_service import BuilderAiService
from src.services.builder_catalog_service import BuilderCatalogService

router = APIRouter(prefix="/api/builder", tags=["builder"])
builder_catalog_service = BuilderCatalogService()
builder_ai_service = BuilderAiService()


class BuilderSimulateRequest(BaseModel):
    rules_json: dict = Field(default_factory=dict)
    market_context: dict | None = None


class BuilderSimulateResponse(BaseModel):
    valid: bool
    triggered: bool
    evaluated_conditions: int
    planned_actions: int
    market_context: dict


class BuilderAiChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class BuilderAiChatRequest(BaseModel):
    messages: list[BuilderAiChatMessage] = Field(default_factory=list)
    available_markets: list[str] = Field(default_factory=list, alias="availableMarkets")
    current_draft: dict[str, Any] | None = Field(default=None, alias="currentDraft")


class BuilderAiChatResponse(BaseModel):
    reply: str
    draft: dict[str, Any]


@router.get("/templates")
def get_templates() -> list[dict]:
    return builder_catalog_service.templates()


@router.get("/blocks")
def get_blocks() -> list[dict]:
    return builder_catalog_service.blocks()


@router.get("/markets")
async def get_markets() -> list[dict]:
    return await builder_catalog_service.markets()


@router.post("/simulate", response_model=BuilderSimulateResponse)
async def simulate(payload: BuilderSimulateRequest) -> BuilderSimulateResponse:
    return BuilderSimulateResponse.model_validate(
        await builder_catalog_service.simulate(payload.rules_json, payload.market_context)
    )


@router.post("/ai-chat", response_model=BuilderAiChatResponse)
async def ai_chat(payload: BuilderAiChatRequest) -> BuilderAiChatResponse:
    if not payload.messages:
        raise HTTPException(status_code=400, detail="At least one chat message is required.")
    try:
        result = await builder_ai_service.generate_draft(
            messages=[message.model_dump() for message in payload.messages],
            available_markets=payload.available_markets,
            current_draft=payload.current_draft,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return BuilderAiChatResponse.model_validate(result)
