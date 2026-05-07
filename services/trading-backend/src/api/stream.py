import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse

from src.api.auth import authenticate_bearer_token
from src.db.session import get_db
from src.services.event_broadcaster import broadcaster, channel_to_stream
from src.services.supabase_rest import SupabaseRestClient

router = APIRouter(prefix="/api/stream", tags=["stream"])
supabase: SupabaseRestClient | None = None


def _get_supabase() -> SupabaseRestClient:
    global supabase
    if supabase is None:
        supabase = SupabaseRestClient()
    return supabase


def _resolve_wallet_address_sync(user_id: str) -> str | None:
    user = _get_supabase().maybe_one("users", columns="wallet_address", filters={"id": user_id}, cache_ttl_seconds=60)
    return None if user is None else user.get("wallet_address")


async def _resolve_wallet_address(user_id: str) -> str | None:
    return await asyncio.to_thread(_resolve_wallet_address_sync, user_id)


@router.get("/user/{user_id}")
async def stream_user_events(
    user_id: str,
    request: Request,
    token: str = Query(min_length=16),
    db=Depends(get_db),
) -> StreamingResponse:
    del db
    return await _stream_authenticated_user_channel(
        user_id=user_id,
        token=token,
        last_event_id=request.headers.get("last-event-id"),
    )


@router.get("/trading/{user_id}")
async def stream_trading_events(
    user_id: str,
    request: Request,
    token: str = Query(min_length=16),
    db=Depends(get_db),
) -> StreamingResponse:
    del db
    return await _stream_authenticated_user_channel(
        user_id=user_id,
        token=token,
        last_event_id=request.headers.get("last-event-id"),
    )


async def _stream_authenticated_user_channel(*, user_id: str, token: str, last_event_id: str | None) -> StreamingResponse:
    authenticated_user = authenticate_bearer_token(token)
    wallet_address = await _resolve_wallet_address(user_id)
    if wallet_address is None:
        raise HTTPException(status_code=404, detail="User stream not found")
    if wallet_address not in authenticated_user.wallet_addresses:
        raise HTTPException(status_code=403, detail="User stream does not belong to the authenticated wallet")
    channel = f"user:{user_id}"

    async def event_stream():
        async for item in channel_to_stream(channel, last_event_id=last_event_id):
            yield item

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


async def websocket_fallback(websocket: WebSocket) -> None:
    await websocket.accept()
    channel = "fallback:global"
    queue = broadcaster.subscribe(channel)
    try:
        while True:
            payload = await queue.get()
            await websocket.send_text(payload)
    except WebSocketDisconnect:
        broadcaster.unsubscribe(channel, queue)
