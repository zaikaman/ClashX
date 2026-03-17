from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from src.api.auth import authenticate_bearer_token
from src.core.settings import get_settings
from src.db.session import get_db
from src.models.user import User
from src.services.event_broadcaster import broadcaster, queue_to_stream
from src.services.supabase_rest import SupabaseRestClient

router = APIRouter(prefix="/api/stream", tags=["stream"])
settings = get_settings()
supabase = SupabaseRestClient() if settings.use_supabase_api else None


def _resolve_wallet_address(db: Session, user_id: str) -> str | None:
    if settings.use_supabase_api:
        if supabase is None:
            return None
        user = supabase.maybe_one("users", filters={"id": user_id})
        return None if user is None else user.get("wallet_address")

    user = db.get(User, user_id)
    return None if user is None else user.wallet_address


@router.get("/leagues/{league_id}")
async def stream_league_events(league_id: str) -> StreamingResponse:
    channel = f"league:{league_id}"
    queue = broadcaster.subscribe(channel)

    async def event_stream():
        try:
            async for item in queue_to_stream(queue):
                yield item
        finally:
            broadcaster.unsubscribe(channel, queue)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/user/{user_id}")
async def stream_user_events(
    user_id: str,
    token: str = Query(min_length=16),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    return _stream_authenticated_user_channel(user_id=user_id, token=token, db=db)


@router.get("/trading/{user_id}")
async def stream_trading_events(
    user_id: str,
    token: str = Query(min_length=16),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    return _stream_authenticated_user_channel(user_id=user_id, token=token, db=db)


def _stream_authenticated_user_channel(*, user_id: str, token: str, db: Session) -> StreamingResponse:
    authenticated_user = authenticate_bearer_token(token)
    wallet_address = _resolve_wallet_address(db, user_id)
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
