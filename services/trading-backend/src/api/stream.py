from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse

from src.api.auth import authenticate_bearer_token
from src.db.session import get_db
from src.services.event_broadcaster import broadcaster, queue_to_stream
from src.services.supabase_rest import SupabaseRestClient

router = APIRouter(prefix="/api/stream", tags=["stream"])
supabase = SupabaseRestClient()


def _resolve_wallet_address(user_id: str) -> str | None:
    user = supabase.maybe_one("users", filters={"id": user_id})
    return None if user is None else user.get("wallet_address")


@router.get("/user/{user_id}")
async def stream_user_events(user_id: str, token: str = Query(min_length=16), db=Depends(get_db)) -> StreamingResponse:
    del db
    return _stream_authenticated_user_channel(user_id=user_id, token=token)


@router.get("/trading/{user_id}")
async def stream_trading_events(user_id: str, token: str = Query(min_length=16), db=Depends(get_db)) -> StreamingResponse:
    del db
    return _stream_authenticated_user_channel(user_id=user_id, token=token)


def _stream_authenticated_user_channel(*, user_id: str, token: str) -> StreamingResponse:
    authenticated_user = authenticate_bearer_token(token)
    wallet_address = _resolve_wallet_address(user_id)
    if wallet_address is None:
        raise HTTPException(status_code=404, detail="User stream not found")
    if wallet_address not in authenticated_user.wallet_addresses:
        raise HTTPException(status_code=403, detail="User stream does not belong to the authenticated wallet")
    channel = f"user:{user_id}"
    queue = broadcaster.subscribe(channel)

    async def event_stream():
        try:
            async for item in queue_to_stream(queue):
                yield item
        finally:
            broadcaster.unsubscribe(channel, queue)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


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
