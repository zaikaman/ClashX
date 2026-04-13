from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field

from src.api.auth import AuthenticatedUser, ensure_wallet_owned, require_authenticated_user
from src.services.telegram_service import TelegramService

router = APIRouter(prefix="/api/telegram", tags=["telegram"])
telegram_service = TelegramService()


class TelegramCommandResponse(BaseModel):
    command: str
    description: str


class TelegramNotificationPrefsResponse(BaseModel):
    critical_alerts: bool
    execution_failures: bool
    copy_activity: bool
    trade_activity: bool


class TelegramConnectionStatusResponse(BaseModel):
    wallet_address: str
    bot_username: str | None = None
    bot_link: str
    deeplink_url: str | None = None
    link_expires_at: datetime | None = None
    connected: bool
    telegram_username: str | None = None
    telegram_first_name: str | None = None
    chat_label: str | None = None
    connected_at: datetime | None = None
    last_interaction_at: datetime | None = None
    notifications_enabled: bool
    notification_prefs: TelegramNotificationPrefsResponse
    token_configured: bool
    webhook_url_configured: bool
    webhook_secret_configured: bool
    webhook_ready: bool
    commands: list[TelegramCommandResponse]


class TelegramWalletRequest(BaseModel):
    wallet_address: str = Field(min_length=8)


class TelegramPreferencesRequest(BaseModel):
    wallet_address: str = Field(min_length=8)
    notifications_enabled: bool | None = None
    critical_alerts: bool | None = None
    execution_failures: bool | None = None
    copy_activity: bool | None = None
    trade_activity: bool | None = None


@router.get("", response_model=TelegramConnectionStatusResponse)
def get_telegram_status(
    wallet_address: str = Query(min_length=8),
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> TelegramConnectionStatusResponse:
    ensure_wallet_owned(user, wallet_address)
    return TelegramConnectionStatusResponse.model_validate(
        telegram_service.get_connection_status(wallet_address=wallet_address)
    )


@router.post("/link", response_model=TelegramConnectionStatusResponse)
def create_telegram_link(
    payload: TelegramWalletRequest,
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> TelegramConnectionStatusResponse:
    ensure_wallet_owned(user, payload.wallet_address)
    try:
        status_payload = telegram_service.issue_link_code(wallet_address=payload.wallet_address)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return TelegramConnectionStatusResponse.model_validate(status_payload)


@router.patch("/preferences", response_model=TelegramConnectionStatusResponse)
def patch_telegram_preferences(
    payload: TelegramPreferencesRequest,
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> TelegramConnectionStatusResponse:
    ensure_wallet_owned(user, payload.wallet_address)
    status_payload = telegram_service.update_preferences(
        wallet_address=payload.wallet_address,
        notifications_enabled=payload.notifications_enabled,
        preference_overrides={
            key: value
            for key, value in {
                "critical_alerts": payload.critical_alerts,
                "execution_failures": payload.execution_failures,
                "copy_activity": payload.copy_activity,
                "trade_activity": payload.trade_activity,
            }.items()
            if value is not None
        },
    )
    return TelegramConnectionStatusResponse.model_validate(status_payload)


@router.post("/test", response_model=TelegramConnectionStatusResponse)
async def send_test_telegram_message(
    payload: TelegramWalletRequest,
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> TelegramConnectionStatusResponse:
    ensure_wallet_owned(user, payload.wallet_address)
    try:
        status_payload = await telegram_service.send_test_message(wallet_address=payload.wallet_address)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return TelegramConnectionStatusResponse.model_validate(status_payload)


@router.post("/disconnect", response_model=TelegramConnectionStatusResponse)
async def disconnect_telegram(
    payload: TelegramWalletRequest,
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> TelegramConnectionStatusResponse:
    ensure_wallet_owned(user, payload.wallet_address)
    status_payload = await telegram_service.disconnect_wallet(
        wallet_address=payload.wallet_address,
        notify_chat=True,
    )
    return TelegramConnectionStatusResponse.model_validate(status_payload)


@router.post("/webhook", status_code=status.HTTP_204_NO_CONTENT)
async def telegram_webhook(request: Request) -> Response:
    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid Telegram webhook payload") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid Telegram webhook payload")
    try:
        await telegram_service.handle_webhook(
            update=payload,
            secret_token=request.headers.get("X-Telegram-Bot-Api-Secret-Token"),
        )
    except PermissionError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
