from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import UTC, datetime

from src.services.event_broadcaster import broadcaster
from src.services.pacifica_auth_service import PacificaAuthService
from src.services.pacifica_client import PacificaClient, PacificaClientError
from src.services.supabase_rest import SupabaseRestClient
from src.services.worker_coordination_service import WorkerCoordinationService


logger = logging.getLogger(__name__)


class CopyWorker:
    def __init__(self, poll_interval_seconds: float = 10.0) -> None:
        self.poll_interval_seconds = poll_interval_seconds
        self._task: asyncio.Task | None = None
        self._running = False
        self._pacifica = PacificaClient()
        self._auth = PacificaAuthService()
        self._supabase = SupabaseRestClient()
        self._coordination = WorkerCoordinationService(self._supabase)
        self.last_iteration_at: str | None = None
        self.last_error: str | None = None

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
            try:
                active = self._supabase.select("copy_relationships", filters={"status": "active"})
                bucket = int(datetime.now(tz=UTC).timestamp() // 30)
                for relationship in active:
                    lease_key = f"copy:{relationship['id']}"
                    if not self._coordination.try_claim_lease(
                        lease_key, ttl_seconds=max(20, int(self.poll_interval_seconds * 3))
                    ):
                        continue
                    try:
                        await self._process_relationship(relationship, bucket=bucket)
                    finally:
                        self._coordination.release_lease(lease_key)
                self.last_iteration_at = datetime.now(tz=UTC).isoformat()
                self.last_error = None
            except Exception as exc:
                self.last_error = str(exc)
                logger.exception("Copy worker iteration failed")
            await asyncio.sleep(self.poll_interval_seconds)

    async def _process_relationship(self, relationship: dict[str, object], *, bucket: int) -> None:
        source = self._supabase.maybe_one("users", filters={"id": relationship["source_user_id"]})
        follower = self._supabase.maybe_one("users", filters={"id": relationship["follower_user_id"]})
        if source is None or follower is None:
            return
        credentials = self._auth.get_trading_credentials(None, follower["wallet_address"])
        if credentials is None:
            return
        try:
            positions = await self._pacifica.get_positions(source["wallet_address"])
        except PacificaClientError:
            return

        for position in positions:
            source_ref = f"tick:{bucket}:{position['symbol']}:{relationship['source_user_id']}"
            existing = self._supabase.maybe_one(
                "copy_execution_events",
                filters={"copy_relationship_id": relationship["id"], "source_order_ref": source_ref},
            )
            if existing is not None:
                continue
            mirrored_size = round(position["amount"] * (relationship["scale_bps"] / 10_000), 4)
            order_response = await self._pacifica.place_order(
                {
                    "account": credentials["account_address"],
                    "agent_wallet": credentials["agent_wallet_address"],
                    "__agent_private_key": credentials["agent_private_key"],
                    "symbol": position["symbol"],
                    "side": position["side"],
                    "amount": mirrored_size,
                    "type": "create_market_order",
                    "source_user_id": source["id"],
                }
            )
            event = self._supabase.insert(
                "copy_execution_events",
                {
                    "id": f"{relationship['id']}-{bucket}-{position['symbol']}",
                    "copy_relationship_id": relationship["id"],
                    "source_order_ref": source_ref,
                    "mirrored_order_ref": order_response["request_id"],
                    "symbol": position["symbol"],
                    "side": position["side"],
                    "size_source": position["amount"],
                    "size_mirrored": mirrored_size,
                    "status": "mirrored",
                    "created_at": datetime.now(tz=UTC).isoformat(),
                },
            )[0]
            await broadcaster.publish(
                channel=f"user:{follower['id']}",
                event="copy.execution.mirrored",
                payload={
                    "relationship_id": relationship["id"],
                    "event": {
                        "id": event["id"],
                        "symbol": event["symbol"],
                        "side": event["side"],
                        "size_source": event["size_source"],
                        "size_mirrored": event["size_mirrored"],
                        "status": event["status"],
                        "created_at": event["created_at"],
                    },
                },
            )

        self._supabase.update(
            "copy_relationships",
            {"updated_at": datetime.now(tz=UTC).isoformat()},
            filters={"id": relationship["id"]},
        )

    @property
    def is_running(self) -> bool:
        return bool(self._task and not self._task.done())
