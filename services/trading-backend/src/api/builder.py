from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from src.services.builder_catalog_service import BuilderCatalogService

router = APIRouter(prefix="/api/builder", tags=["builder"])
builder_catalog_service = BuilderCatalogService()


class BuilderSimulateRequest(BaseModel):
    rules_json: dict = Field(default_factory=dict)
    market_context: dict | None = None


class BuilderSimulateResponse(BaseModel):
    valid: bool
    triggered: bool
    evaluated_conditions: int
    planned_actions: int
    market_context: dict


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
