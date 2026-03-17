from __future__ import annotations

import asyncio
import contextlib
from datetime import UTC, datetime

from sqlalchemy import select

from src.core.settings import get_settings
from src.db.session import SessionLocal
from src.models.copy_execution_event import CopyExecutionEvent
from src.models.copy_relationship import CopyRelationship
from src.models.user import User
from src.services.event_broadcaster import broadcaster
from src.services.pacifica_auth_service import PacificaAuthService
from src.services.pacifica_client import PacificaClient, PacificaClientError


class CopyWorker:
    def __init__(self, poll_interval_seconds: float = 10.0) -> None:
        self.poll_interval_seconds = poll_interval_seconds
        self._task: asyncio.Task | None = None
        self._running = False
        self._settings = get_settings()
        self._pacifica = PacificaClient()
        self._auth = PacificaAuthService()

    def start(self) -> asyncio.Task:
        if self._task and not self._task.done():
            return self._task
        self._running = True
        self._task = asyncio.create_task(self.run_forever(), name="copy-worker")
        return self._task

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

    async def run_forever(self) -> None:
        while self._running:
            if self._settings.use_supabase_api:
                await asyncio.sleep(self.poll_interval_seconds)
                continue
            db = SessionLocal()
            try:
                active = list(
                    db.scalars(select(CopyRelationship).where(CopyRelationship.status == "active")).all()
                )
                bucket = int(datetime.now(tz=UTC).timestamp() // 30)
                for relationship in active:
                    source = db.get(User, relationship.source_user_id)
                    follower = db.get(User, relationship.follower_user_id)
                    if source is None or follower is None:
                        continue
                    credentials = self._auth.get_trading_credentials(db, follower.wallet_address)
                    if credentials is None:
                        continue
                    try:
                        positions = await self._pacifica.get_positions(source.wallet_address)
                    except PacificaClientError:
                        continue
                    for position in positions:
                        source_ref = f"tick:{bucket}:{position['symbol']}:{relationship.source_user_id}"
                        existing = db.scalar(
                            select(CopyExecutionEvent).where(
                                CopyExecutionEvent.copy_relationship_id == relationship.id,
                                CopyExecutionEvent.source_order_ref == source_ref,
                            )
                        )
                        if existing is not None:
                            continue
                        mirrored_size = round(position["amount"] * (relationship.scale_bps / 10_000), 4)
                        order_response = await self._pacifica.place_order(
                            {
                                "account": credentials["account_address"],
                                "agent_wallet": credentials["agent_wallet_address"],
                                "__agent_private_key": credentials["agent_private_key"],
                                "symbol": position["symbol"],
                                "side": position["side"],
                                "amount": mirrored_size,
                                "type": "create_market_order",
                                "source_user_id": source.id,
                            }
                        )
                        event = CopyExecutionEvent(
                            copy_relationship_id=relationship.id,
                            source_order_ref=source_ref,
                            mirrored_order_ref=order_response["request_id"],
                            symbol=position["symbol"],
                            side=position["side"],
                            size_source=position["amount"],
                            size_mirrored=mirrored_size,
                            status="mirrored",
                        )
                        db.add(event)
                        db.flush()
                        await broadcaster.publish(
                            channel=f"user:{follower.id}",
                            event="copy.execution.mirrored",
                            payload={
                                "relationship_id": relationship.id,
                                "event": {
                                    "id": event.id,
                                    "symbol": event.symbol,
                                    "side": event.side,
                                    "size_source": event.size_source,
                                    "size_mirrored": event.size_mirrored,
                                    "status": event.status,
                                    "created_at": event.created_at.isoformat(),
                                },
                            },
                        )
                    relationship.updated_at = datetime.now(tz=UTC)
                db.commit()
            finally:
                db.close()
            await asyncio.sleep(self.poll_interval_seconds)
