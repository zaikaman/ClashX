from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import UTC, datetime
from typing import Any

from src.services.event_broadcaster import broadcaster
from src.services.pacifica_auth_service import PacificaAuthService
from src.services.pacifica_client import PacificaClient, PacificaClientError
from src.services.supabase_rest import SupabaseRestClient
from src.services.worker_coordination_service import WorkerCoordinationService


logger = logging.getLogger(__name__)


class BotCopyWorker:
    def __init__(self, poll_interval_seconds: float = 6.0) -> None:
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
        self._task = asyncio.create_task(self.run_forever(), name="bot-copy-worker")
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
                active = self._supabase.select("bot_copy_relationships", filters={"status": "active", "mode": "mirror"})
                for relationship in active:
                    lease_key = f"bot-copy:{relationship['id']}"
                    if not self._coordination.try_claim_lease(
                        lease_key, ttl_seconds=max(20, int(self.poll_interval_seconds * 3))
                    ):
                        continue
                    try:
                        await self._process_relationship(relationship)
                    finally:
                        self._coordination.release_lease(lease_key)
                self.last_iteration_at = datetime.now(tz=UTC).isoformat()
                self.last_error = None
            except Exception as exc:
                self.last_error = str(exc)
                logger.exception("Bot copy worker iteration failed")
            await asyncio.sleep(self.poll_interval_seconds)

    async def _process_relationship(self, relationship: dict[str, Any]) -> None:
        runtime = self._supabase.maybe_one("bot_runtimes", filters={"id": relationship["source_runtime_id"]})
        if runtime is None or runtime["status"] != "active":
            return

        credentials = self._auth.get_trading_credentials(None, relationship["follower_wallet_address"])
        if credentials is None:
            self._supabase.update(
                "bot_copy_relationships",
                {"status": "paused", "updated_at": datetime.now(tz=UTC).isoformat()},
                filters={"id": relationship["id"]},
            )
            return

        source_events = list(
            reversed(
                self._supabase.select(
                    "bot_execution_events",
                    filters={
                        "runtime_id": relationship["source_runtime_id"],
                        "event_type": "action.executed",
                        "created_at": ("gt", relationship["updated_at"]),
                    },
                    order="created_at.desc",
                    limit=50,
                )
            )
        )
        if not source_events:
            return

        markets, follower_positions = await asyncio.gather(
            self._safe_load(self._pacifica.get_markets, []),
            self._safe_load(lambda: self._pacifica.get_positions(relationship["follower_wallet_address"]), []),
        )
        market_lookup = {str(item.get("symbol") or "").upper(): item for item in markets if isinstance(item, dict)}
        position_lookup = {str(item.get("symbol") or "").upper(): item for item in follower_positions if isinstance(item, dict)}

        for source_event in source_events:
            marker = f"bot_copy.mirror:{relationship['id']}:{source_event['id']}"
            seen = self._supabase.maybe_one("audit_events", filters={"action": marker})
            if seen is not None:
                continue

            action = source_event["request_payload"] if isinstance(source_event.get("request_payload"), dict) else {}
            try:
                result = await self._execute_action(
                    action=action,
                    scale_bps=relationship["scale_bps"],
                    credentials=credentials,
                    market_lookup=market_lookup,
                    position_lookup=position_lookup,
                )
                status = "mirrored"
                error_reason = None
            except (ValueError, PacificaClientError) as exc:
                result = {}
                status = "error"
                error_reason = str(exc)

            self._supabase.insert(
                "audit_events",
                {
                    "id": marker,
                    "user_id": relationship["follower_user_id"],
                    "action": marker,
                    "payload": {
                        "relationship_id": relationship["id"],
                        "source_runtime_id": relationship["source_runtime_id"],
                        "source_event_id": source_event["id"],
                        "status": status,
                        "error_reason": error_reason,
                        "request_payload": action,
                        "result_payload": result,
                    },
                    "created_at": datetime.now(tz=UTC).isoformat(),
                },
            )
            await broadcaster.publish(
                channel=f"user:{relationship['follower_user_id']}",
                event="bot.copy.execution",
                payload={
                    "relationship_id": relationship["id"],
                    "source_event_id": source_event["id"],
                    "status": status,
                    "error_reason": error_reason,
                },
            )

        self._supabase.update(
            "bot_copy_relationships",
            {"updated_at": datetime.now(tz=UTC).isoformat()},
            filters={"id": relationship["id"]},
        )

    async def _execute_action(
        self,
        *,
        action: dict[str, Any],
        scale_bps: int,
        credentials: dict[str, str],
        market_lookup: dict[str, dict[str, Any]],
        position_lookup: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        action_type = str(action.get("type") or "")
        symbol = str(action.get("symbol") or "").upper().replace("-PERP", "")
        payload: dict[str, Any] = {
            "account": credentials["account_address"],
            "agent_wallet": credentials["agent_wallet_address"],
            "__agent_private_key": credentials["agent_private_key"],
            "symbol": symbol,
        }

        if action_type in {"open_long", "open_short"}:
            leverage = max(1, int(float(action.get("leverage") or 1)))
            mark_price = float((market_lookup.get(symbol) or {}).get("mark_price") or 0)
            size_usd = float(action.get("size_usd") or 0)
            mirrored_size_usd = size_usd * (scale_bps / 10_000)
            if mark_price <= 0 or mirrored_size_usd <= 0:
                raise ValueError("Cannot mirror open action without valid mark price and size")
            await self._pacifica.place_order({"type": "update_leverage", **payload, "leverage": leverage})
            amount = (mirrored_size_usd * leverage) / mark_price
            return await self._pacifica.place_order(
                {"type": "create_market_order", **payload, "side": "bid" if action_type == "open_long" else "ask", "amount": amount}
            )

        if action_type == "close_position":
            follower_position = position_lookup.get(symbol)
            if not isinstance(follower_position, dict):
                raise ValueError("No follower position available to close")
            amount = abs(float(follower_position.get("amount") or 0))
            if amount <= 0:
                raise ValueError("No follower position size to close")
            side = str(follower_position.get("side") or "").lower()
            close_side = "ask" if side in {"bid", "long"} else "bid"
            return await self._pacifica.place_order(
                {"type": "create_market_order", **payload, "side": close_side, "amount": amount, "reduce_only": True}
            )

        if action_type == "set_tpsl":
            follower_position = position_lookup.get(symbol)
            if not isinstance(follower_position, dict):
                raise ValueError("No follower position available for TP/SL")
            amount = abs(float(follower_position.get("amount") or 0))
            mark_price = float(follower_position.get("mark_price") or (market_lookup.get(symbol) or {}).get("mark_price") or 0)
            if amount <= 0 or mark_price <= 0:
                raise ValueError("Cannot set TP/SL without valid follower position")
            tp_pct = float(action.get("take_profit_pct") or 0)
            sl_pct = float(action.get("stop_loss_pct") or 0)
            side = str(follower_position.get("side") or "").lower()
            if side in {"bid", "long"}:
                take_profit_price = mark_price * (1 + tp_pct / 100)
                stop_loss_price = mark_price * (1 - sl_pct / 100)
            else:
                take_profit_price = mark_price * (1 - tp_pct / 100)
                stop_loss_price = mark_price * (1 + sl_pct / 100)
            return await self._pacifica.place_order(
                {
                    "type": "set_position_tpsl",
                    **payload,
                    "take_profit": {"stop_price": take_profit_price, "amount": amount},
                    "stop_loss": {"stop_price": stop_loss_price, "amount": amount},
                }
            )

        if action_type == "update_leverage":
            leverage = max(1, int(float(action.get("leverage") or 1)))
            return await self._pacifica.place_order({"type": "update_leverage", **payload, "leverage": leverage})

        raise ValueError(f"Unsupported mirrored action type: {action_type}")

    async def _safe_load(self, loader: Any, fallback: Any) -> Any:
        try:
            return await loader()
        except PacificaClientError:
            return fallback

    @property
    def is_running(self) -> bool:
        return bool(self._task and not self._task.done())
