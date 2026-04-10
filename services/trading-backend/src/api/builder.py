from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.services.ai_job_runner_service import AiJobRunnerService
from src.services.ai_job_service import AiJobStatus, AiJobType, AiJobService
from src.services.builder_ai_service import BuilderAiService
from src.services.builder_catalog_service import BuilderCatalogService

router = APIRouter(prefix="/api/builder", tags=["builder"])
builder_catalog_service = BuilderCatalogService()
builder_ai_service = BuilderAiService()
ai_job_service = AiJobService()
ai_job_runner = AiJobRunnerService(job_service=ai_job_service, builder_ai_service=builder_ai_service)


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


class BuilderAiChatJobCreateResponse(BaseModel):
    id: str
    jobType: AiJobType
    status: AiJobStatus


class BuilderAiChatJobStatusResponse(BaseModel):
    id: str
    jobType: AiJobType
    status: AiJobStatus
    result: BuilderAiChatResponse | None = None
    errorDetail: str | None = None
    createdAt: str | None = None
    updatedAt: str | None = None
    completedAt: str | None = None


def _serialize_job_status(row: dict[str, Any]) -> BuilderAiChatJobStatusResponse:
    result_payload = row.get("result_payload_json")
    result = BuilderAiChatResponse.model_validate(result_payload) if isinstance(result_payload, dict) and result_payload else None
    return BuilderAiChatJobStatusResponse(
        id=str(row.get("id") or ""),
        jobType=str(row.get("job_type") or "builder_ai_chat"),
        status=str(row.get("status") or "queued"),
        result=result,
        errorDetail=str(row.get("error_detail") or "") or None,
        createdAt=row.get("created_at"),
        updatedAt=row.get("updated_at"),
        completedAt=row.get("completed_at"),
    )


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


@router.post("/ai-chat/jobs", response_model=BuilderAiChatJobCreateResponse)
async def create_ai_chat_job(payload: BuilderAiChatRequest) -> BuilderAiChatJobCreateResponse:
    if not payload.messages:
        raise HTTPException(status_code=400, detail="At least one chat message is required.")
    job = ai_job_service.create_job(
        job_type="builder_ai_chat",
        request_payload={
            "messages": [message.model_dump() for message in payload.messages],
            "availableMarkets": payload.available_markets,
            "currentDraft": payload.current_draft,
        },
    )
    ai_job_runner.start_builder_ai_chat_job(
        job_id=job["id"],
        messages=[message.model_dump() for message in payload.messages],
        available_markets=payload.available_markets,
        current_draft=payload.current_draft,
    )
    return BuilderAiChatJobCreateResponse(
        id=job["id"],
        jobType="builder_ai_chat",
        status="queued",
    )


@router.get("/ai-chat/jobs/{job_id}", response_model=BuilderAiChatJobStatusResponse)
async def get_ai_chat_job(job_id: str) -> BuilderAiChatJobStatusResponse:
    job = ai_job_service.get_job(job_id=job_id)
    if job is None or job.get("job_type") != "builder_ai_chat":
        raise HTTPException(status_code=404, detail="AI job not found.")
    return _serialize_job_status(job)
