from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from src.api.auth import AuthenticatedUser, require_authenticated_user
from src.services.ai_job_runner_service import AiJobRunnerService
from src.services.ai_job_service import AiJobStatus, AiJobType, AiJobService
from src.services.copilot_conversation_service import CopilotConversationService
from src.services.copilot_service import CopilotService

router = APIRouter(prefix="/api/copilot", tags=["copilot"])
copilot_service = CopilotService()
conversation_service = CopilotConversationService(copilot=copilot_service)
ai_job_service = AiJobService()
ai_job_runner = AiJobRunnerService(job_service=ai_job_service, copilot_conversation_service=conversation_service)


class CopilotChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class CopilotToolTraceResponse(BaseModel):
    tool: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    ok: bool
    resultPreview: str


class CopilotChatRequest(BaseModel):
    conversationId: str | None = None
    content: str | None = None
    messages: list[CopilotChatMessage] = Field(default_factory=list)
    walletAddress: str | None = None


class CopilotConversationMessageResponse(BaseModel):
    id: str
    role: Literal["user", "assistant"]
    content: str
    toolCalls: list[CopilotToolTraceResponse] = Field(default_factory=list)
    followUps: list[str] = Field(default_factory=list)
    provider: str | None = None
    createdAt: datetime


class CopilotConversationSummaryResponse(BaseModel):
    id: str
    title: str
    walletAddress: str
    messageCount: int
    lastMessagePreview: str
    createdAt: datetime
    updatedAt: datetime
    latestMessageAt: datetime


class CopilotConversationDetailResponse(CopilotConversationSummaryResponse):
    summaryMessageCount: int = 0
    summaryText: str = ""
    messages: list[CopilotConversationMessageResponse] = Field(default_factory=list)


class CopilotCreateConversationRequest(BaseModel):
    walletAddress: str | None = None
    title: str | None = None


class CopilotChatResponse(BaseModel):
    conversationId: str
    conversation: CopilotConversationSummaryResponse
    assistantMessage: CopilotConversationMessageResponse
    reply: str
    followUps: list[str] = Field(default_factory=list)
    toolCalls: list[CopilotToolTraceResponse] = Field(default_factory=list)
    provider: str
    usedWalletAddress: str | None = None


class CopilotChatJobCreateResponse(BaseModel):
    id: str
    jobType: AiJobType
    status: AiJobStatus
    conversationId: str | None = None


class CopilotChatJobStatusResponse(BaseModel):
    id: str
    jobType: AiJobType
    status: AiJobStatus
    conversationId: str | None = None
    result: CopilotChatResponse | None = None
    errorDetail: str | None = None
    createdAt: str | None = None
    updatedAt: str | None = None
    completedAt: str | None = None


@router.get("/conversations", response_model=list[CopilotConversationSummaryResponse])
def list_copilot_conversations(
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> list[CopilotConversationSummaryResponse]:
    return [CopilotConversationSummaryResponse.model_validate(row) for row in conversation_service.list_conversations(user=user)]


def _runtime_error_status(exc: RuntimeError) -> int:
    message = str(exc).lower()
    if "timed out" in message or "timeout" in message:
        return 504
    return 500


def _resolve_requested_wallet(user: AuthenticatedUser, requested_wallet: str | None) -> str | None:
    wallet = str(requested_wallet or "").strip()
    if wallet:
        if wallet not in user.wallet_addresses:
            raise HTTPException(status_code=400, detail="Wallet is not linked to the authenticated user.")
        return wallet
    if user.wallet_addresses:
        return user.wallet_addresses[0]
    return None


def _serialize_chat_job_status(row: dict[str, Any]) -> CopilotChatJobStatusResponse:
    result_payload = row.get("result_payload_json")
    result = CopilotChatResponse.model_validate(result_payload) if isinstance(result_payload, dict) and result_payload else None
    return CopilotChatJobStatusResponse(
        id=str(row.get("id") or ""),
        jobType=str(row.get("job_type") or "copilot_chat"),
        status=str(row.get("status") or "queued"),
        conversationId=str(row.get("conversation_id") or "") or None,
        result=result,
        errorDetail=str(row.get("error_detail") or "") or None,
        createdAt=row.get("created_at"),
        updatedAt=row.get("updated_at"),
        completedAt=row.get("completed_at"),
    )


@router.post("/conversations", response_model=CopilotConversationSummaryResponse)
def create_copilot_conversation(
    payload: CopilotCreateConversationRequest,
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> CopilotConversationSummaryResponse:
    try:
        created = conversation_service.create_conversation(
            user=user,
            wallet_address=payload.walletAddress,
            title=payload.title,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return CopilotConversationSummaryResponse.model_validate(created)


@router.get("/conversations/{conversation_id}", response_model=CopilotConversationDetailResponse)
def get_copilot_conversation(
    conversation_id: str,
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> CopilotConversationDetailResponse:
    try:
        conversation = conversation_service.get_conversation(user=user, conversation_id=conversation_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return CopilotConversationDetailResponse.model_validate(conversation)


@router.delete("/conversations/{conversation_id}", status_code=204)
def delete_copilot_conversation(
    conversation_id: str,
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> None:
    try:
        conversation_service.delete_conversation(user=user, conversation_id=conversation_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/chat", response_model=CopilotChatResponse)
async def chat_with_copilot(
    payload: CopilotChatRequest,
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> CopilotChatResponse:
    if payload.content is not None:
        try:
            result = await conversation_service.send_message(
                user=user,
                conversation_id=payload.conversationId,
                content=payload.content,
                wallet_address=payload.walletAddress,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400 if "required" in str(exc).lower() or "wallet" in str(exc).lower() else 404, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=_runtime_error_status(exc), detail=str(exc)) from exc
        return CopilotChatResponse.model_validate(result)

    if not payload.messages:
        raise HTTPException(status_code=400, detail="At least one chat message is required.")
    try:
        result = await copilot_service.chat(
            messages=[message.model_dump() for message in payload.messages],
            user=user,
            wallet_address=payload.walletAddress,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=_runtime_error_status(exc), detail=str(exc)) from exc
    return CopilotChatResponse.model_validate(
        {
            "conversationId": payload.conversationId or "legacy-session",
            "conversation": {
                "id": payload.conversationId or "legacy-session",
                "title": "Legacy session",
                "walletAddress": payload.walletAddress or (user.wallet_addresses[0] if user.wallet_addresses else ""),
                "messageCount": len(payload.messages) + 1,
                "lastMessagePreview": result["reply"],
                "createdAt": datetime.now(tz=UTC),
                "updatedAt": datetime.now(tz=UTC),
                "latestMessageAt": datetime.now(tz=UTC),
            },
            "assistantMessage": {
                "id": "legacy-assistant-message",
                "role": "assistant",
                "content": result["reply"],
                "toolCalls": result.get("toolCalls") or [],
                "followUps": result.get("followUps") or [],
                "provider": result.get("provider"),
                "createdAt": datetime.now(tz=UTC),
            },
            **result,
        }
    )


@router.post("/chat/jobs", response_model=CopilotChatJobCreateResponse)
async def create_copilot_chat_job(
    payload: CopilotChatRequest,
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> CopilotChatJobCreateResponse:
    if payload.content is None or not payload.content.strip():
        raise HTTPException(status_code=400, detail="A chat message is required.")

    resolved_wallet = _resolve_requested_wallet(user, payload.walletAddress)
    job = ai_job_service.create_job(
        job_type="copilot_chat",
        wallet_address=resolved_wallet,
        conversation_id=payload.conversationId,
        request_payload={
            "conversationId": payload.conversationId,
            "content": payload.content,
            "walletAddress": resolved_wallet,
        },
    )
    ai_job_runner.start_copilot_chat_job(
        job_id=job["id"],
        user=user,
        content=payload.content,
        conversation_id=payload.conversationId,
        wallet_address=resolved_wallet,
    )
    return CopilotChatJobCreateResponse(
        id=job["id"],
        jobType="copilot_chat",
        status="queued",
        conversationId=payload.conversationId,
    )


@router.get("/chat/jobs/{job_id}", response_model=CopilotChatJobStatusResponse)
async def get_copilot_chat_job(
    job_id: str,
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> CopilotChatJobStatusResponse:
    job = ai_job_service.get_job_for_wallets(job_id=job_id, wallet_addresses=user.wallet_addresses)
    if job is None or job.get("job_type") != "copilot_chat":
        raise HTTPException(status_code=404, detail="Chat job not found.")
    return _serialize_chat_job_status(job)
