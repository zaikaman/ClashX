from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import UTC, datetime
from time import monotonic
from decimal import ROUND_DOWN, Decimal
from time import perf_counter
from typing import Any

from src.core.performance_metrics import get_performance_metrics_store
from src.services.event_broadcaster import broadcaster
from src.services.pacifica_auth_service import PacificaAuthService
from src.services.pacifica_client import PacificaClientError, get_pacifica_client
from src.services.supabase_rest import SupabaseRestClient, SupabaseRestError
from src.services.worker_coordination_service import WorkerCoordinationService


logger = logging.getLogger(__name__)


class BotCopyWorker:
    def __init__(self, poll_interval_seconds: float = 30.0) -> None:
        self.poll_interval_seconds = poll_interval_seconds
        self._task: asyncio.Task | None = None
        self._running = False
        self._pacifica = get_pacifica_client()
        self._auth = PacificaAuthService()
        self._supabase = SupabaseRestClient()
        self._coordination = WorkerCoordinationService(self._supabase)
        self._metrics = get_performance_metrics_store()
        self._held_leases: dict[str, float] = {}
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
        self._release_held_leases()

    async def run_forever(self) -> None:
        while self._running:
            iteration_started = perf_counter()
            try:
                active = await asyncio.to_thread(
                    self._supabase.select,
                    "bot_copy_relationships",
                    columns="id,source_runtime_id,follower_user_id,follower_wallet_address,scale_bps,updated_at",
                    filters={"status": "active", "mode": "mirror"},
                )
                for relationship in active:
                    lease_key = f"bot-copy:{relationship['id']}"
                    if not self._claim_local_lease(
                        lease_key,
                        ttl_seconds=max(20, int(self.poll_interval_seconds * 3)),
                    ):
                        continue
                    await self._process_relationship(relationship)
                self.last_iteration_at = datetime.now(tz=UTC).isoformat()
                self.last_error = None
            except SupabaseRestError as exc:
                self.last_error = str(exc)
                if exc.is_retryable:
                    logger.warning("Bot copy worker iteration deferred because Supabase is temporarily unavailable: %s", exc)
                else:
                    logger.exception("Bot copy worker iteration failed")
            except Exception as exc:
                self.last_error = str(exc)
                logger.exception("Bot copy worker iteration failed")
            finally:
                self._metrics.record("worker:bot_copy:iteration", (perf_counter() - iteration_started) * 1000.0)
            await asyncio.sleep(self.poll_interval_seconds)

    async def _process_relationship(self, relationship: dict[str, Any]) -> None:
        runtime = await asyncio.to_thread(
            self._supabase.maybe_one,
            "bot_runtimes",
            columns="id,status",
            filters={"id": relationship["source_runtime_id"]},
            cache_ttl_seconds=30,
        )
        if runtime is None or runtime["status"] != "active":
            return

        credentials = self._auth.get_trading_credentials(None, relationship["follower_wallet_address"])
        if credentials is None:
            await asyncio.to_thread(
                self._supabase.update,
                "bot_copy_relationships",
                {"status": "paused", "updated_at": datetime.now(tz=UTC).isoformat()},
                filters={"id": relationship["id"]},
            )
            return

        source_events = list(
            reversed(
                await asyncio.to_thread(
                    self._supabase.select,
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
            seen = await asyncio.to_thread(
                self._supabase.maybe_one,
                "audit_events",
                filters={"action": marker},
            )
            if seen is not None:
                continue

            action = source_event["request_payload"] if isinstance(source_event.get("request_payload"), dict) else {}
            try:
                result = await self._execute_action(
                    relationship=relationship,
                    source_event=source_event,
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

            await asyncio.to_thread(
                self._supabase.insert,
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
                returning="minimal",
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

        await asyncio.to_thread(
            self._supabase.update,
            "bot_copy_relationships",
            {"updated_at": datetime.now(tz=UTC).isoformat()},
            filters={"id": relationship["id"]},
        )

    def _claim_local_lease(self, lease_key: str, *, ttl_seconds: int) -> bool:
        refresh_at = self._held_leases.get(lease_key)
        if refresh_at is not None and monotonic() < refresh_at:
            return True
        claimed = self._coordination.try_claim_lease(lease_key, ttl_seconds=ttl_seconds)
        if not claimed:
            self._held_leases.pop(lease_key, None)
            return False
        self._held_leases[lease_key] = monotonic() + max(1.0, ttl_seconds * 0.6)
        return True

    def _release_held_leases(self) -> None:
        for lease_key in list(self._held_leases):
            self._coordination.release_lease(lease_key)
        self._held_leases.clear()

    async def _execute_action(
        self,
        *,
        relationship: dict[str, Any],
        source_event: dict[str, Any],
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

        if action_type in {"open_long", "open_short", "place_market_order"}:
            if not symbol:
                raise ValueError("Market orders require a symbol")
            side = (
                "long"
                if action_type == "open_long"
                else "short"
                if action_type == "open_short"
                else str(action.get("side") or "").lower().strip()
            )
            if side not in {"long", "short"}:
                raise ValueError("Market orders require side to be long or short")
            leverage = max(1, int(float(action.get("leverage") or 1)))
            reduce_only = self._to_bool(action.get("reduce_only"), False)
            mark_price = float((market_lookup.get(symbol) or {}).get("mark_price") or 0)
            amount = self._resolve_order_quantity(
                action=action,
                scale_bps=scale_bps,
                market_lookup=market_lookup,
                symbol=symbol,
                reference_price=None,
            )
            if not reduce_only:
                await self._pacifica.place_order({"type": "update_leverage", **payload, "leverage": leverage})
            response = await self._pacifica.place_order(
                {
                    "type": "create_market_order",
                    **payload,
                    "side": "bid" if side == "long" else "ask",
                    "amount": amount,
                    "reduce_only": reduce_only,
                    "slippage_percent": float(action.get("slippage_percent") or 0.5),
                }
            )
            response["execution_meta"] = {
                "symbol": symbol,
                "side": "bid" if side == "long" else "ask",
                "amount": amount,
                "reduce_only": reduce_only,
                "reference_price": mark_price,
            }
            return response

        if action_type == "place_limit_order":
            if not symbol:
                raise ValueError("Limit orders require a symbol")
            side = str(action.get("side") or "").lower().strip()
            if side not in {"long", "short"}:
                raise ValueError("Limit orders require side to be long or short")
            price = float(action.get("price") or 0)
            if price <= 0:
                raise ValueError("Limit orders require a positive price")
            leverage = max(1, int(float(action.get("leverage") or 1)))
            reduce_only = self._to_bool(action.get("reduce_only"), False)
            amount = self._resolve_order_quantity(
                action=action,
                scale_bps=scale_bps,
                market_lookup=market_lookup,
                symbol=symbol,
                reference_price=price,
            )
            if not reduce_only:
                await self._pacifica.place_order({"type": "update_leverage", **payload, "leverage": leverage})
            response = await self._pacifica.place_order(
                {
                    "type": "create_order",
                    **payload,
                    "side": "bid" if side == "long" else "ask",
                    "amount": amount,
                    "price": price,
                    "tif": str(action.get("tif") or "GTC"),
                    "reduce_only": reduce_only,
                    "client_order_id": self._mirror_client_order_id(relationship=relationship, source_event=source_event),
                }
            )
            response["execution_meta"] = {
                "symbol": symbol,
                "side": "bid" if side == "long" else "ask",
                "amount": amount,
                "reduce_only": reduce_only,
                "reference_price": price,
            }
            return response

        if action_type == "place_twap_order":
            if not symbol:
                raise ValueError("TWAP orders require a symbol")
            side = str(action.get("side") or "").lower().strip()
            if side not in {"long", "short"}:
                raise ValueError("TWAP orders require side to be long or short")
            duration_seconds = max(1, int(float(action.get("duration_seconds") or 0)))
            leverage = max(1, int(float(action.get("leverage") or 1)))
            reduce_only = self._to_bool(action.get("reduce_only"), False)
            mark_price = float((market_lookup.get(symbol) or {}).get("mark_price") or 0)
            amount = self._resolve_order_quantity(
                action=action,
                scale_bps=scale_bps,
                market_lookup=market_lookup,
                symbol=symbol,
                reference_price=None,
            )
            if not reduce_only:
                await self._pacifica.place_order({"type": "update_leverage", **payload, "leverage": leverage})
            response = await self._pacifica.place_order(
                {
                    "type": "create_twap_order",
                    **payload,
                    "side": "bid" if side == "long" else "ask",
                    "amount": amount,
                    "reduce_only": reduce_only,
                    "duration_in_seconds": duration_seconds,
                    "slippage_percent": float(action.get("slippage_percent") or 0.5),
                    "client_order_id": self._mirror_client_order_id(relationship=relationship, source_event=source_event),
                }
            )
            response["execution_meta"] = {
                "symbol": symbol,
                "side": "bid" if side == "long" else "ask",
                "amount": amount,
                "reduce_only": reduce_only,
                "reference_price": mark_price,
            }
            return response

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
            if not symbol:
                raise ValueError("Leverage updates require a symbol")
            leverage = max(1, int(float(action.get("leverage") or 1)))
            return await self._pacifica.place_order({"type": "update_leverage", **payload, "leverage": leverage})

        if action_type == "cancel_order":
            if not symbol:
                raise ValueError("Cancel order requires a symbol")
            return await self._pacifica.place_order(
                {
                    "type": "cancel_order",
                    **payload,
                    **self._extract_mirrored_order_identifier(relationship=relationship, source_event=source_event, action=action),
                }
            )

        if action_type == "cancel_twap_order":
            if not symbol:
                raise ValueError("Cancel TWAP order requires a symbol")
            return await self._pacifica.place_order(
                {
                    "type": "cancel_twap_order",
                    **payload,
                    **self._extract_mirrored_order_identifier(relationship=relationship, source_event=source_event, action=action),
                }
            )

        if action_type == "cancel_all_orders":
            if not self._to_bool(action.get("all_symbols"), True) and not symbol:
                raise ValueError("Cancel all orders requires a symbol when all_symbols is false")
            return await self._pacifica.place_order(
                {
                    "type": "cancel_all_orders",
                    **payload,
                    "all_symbols": self._to_bool(action.get("all_symbols"), True),
                    "exclude_reduce_only": self._to_bool(action.get("exclude_reduce_only"), False),
                }
            )

        raise ValueError(f"Unsupported mirrored action type: {action_type}")

    async def _safe_load(self, loader: Any, fallback: Any) -> Any:
        try:
            return await loader()
        except PacificaClientError:
            return fallback

    @staticmethod
    def _to_bool(value: Any, default: bool) -> bool:
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"1", "true", "yes", "y"}:
                return True
            if normalized in {"0", "false", "no", "n"}:
                return False
        return bool(value)

    def _resolve_order_quantity(
        self,
        *,
        action: dict[str, Any],
        scale_bps: int,
        market_lookup: dict[str, dict[str, Any]],
        symbol: str,
        reference_price: float | None,
    ) -> float:
        market = market_lookup.get(symbol) or {}
        raw_quantity = float(action.get("quantity") or 0)
        scaled_quantity = raw_quantity * (scale_bps / 10_000)
        if scaled_quantity > 0:
            return self._normalize_order_quantity(
                scaled_quantity,
                lot_size=float(market.get("lot_size") or 0),
                min_order_size=float(market.get("min_order_size") or 0),
                symbol=symbol,
            )

        resolved_price = reference_price if reference_price is not None else float(market.get("mark_price") or 0)
        if resolved_price <= 0:
            raise ValueError("Cannot mirror open action without valid mark price and size")
        size_usd = float(action.get("size_usd") or 0)
        mirrored_size_usd = size_usd * (scale_bps / 10_000)
        if mirrored_size_usd <= 0:
            raise ValueError("Cannot mirror open action without valid mark price and size")
        leverage = max(1, int(float(action.get("leverage") or 1)))
        return self._normalize_order_quantity(
            (mirrored_size_usd * leverage) / resolved_price,
            lot_size=float(market.get("lot_size") or 0),
            min_order_size=float(market.get("min_order_size") or 0),
            symbol=symbol,
        )

    @staticmethod
    def _normalize_order_quantity(quantity: float, *, lot_size: float, min_order_size: float, symbol: str) -> float:
        normalized = Decimal(str(quantity))
        if lot_size > 0:
            step = Decimal(str(lot_size))
            normalized = (normalized / step).to_integral_value(rounding=ROUND_DOWN) * step
        normalized_float = float(normalized)
        if normalized_float <= 0:
            raise ValueError(f"Order size is below the minimum tradable increment for {symbol}.")
        if min_order_size > 0 and normalized_float < min_order_size:
            raise ValueError(f"Order size for {symbol} must be at least {min_order_size:g}. Adjust the copied size.")
        return normalized_float

    def _extract_mirrored_order_identifier(
        self,
        *,
        relationship: dict[str, Any],
        source_event: dict[str, Any],
        action: dict[str, Any],
    ) -> dict[str, Any]:
        del source_event
        source_identifier = self._source_order_identifier(action)
        if not source_identifier:
            raise ValueError("Action requires order_id or client_order_id")
        return {
            "client_order_id": self._mirrored_order_key(
                relationship_id=str(relationship["id"]),
                source_identifier=source_identifier,
            )
        }

    def _mirror_client_order_id(self, *, relationship: dict[str, Any], source_event: dict[str, Any]) -> str:
        action = source_event.get("request_payload") if isinstance(source_event.get("request_payload"), dict) else {}
        source_identifier = self._source_order_identifier(action)
        if not source_identifier:
            result_payload = source_event.get("result_payload") if isinstance(source_event.get("result_payload"), dict) else {}
            source_identifier = str(
                result_payload.get("request_id")
                or ((result_payload.get("response") or {}).get("order_id") if isinstance(result_payload.get("response"), dict) else "")
                or ((result_payload.get("response") or {}).get("client_order_id") if isinstance(result_payload.get("response"), dict) else "")
                or source_event.get("id")
                or ""
            ).strip()
        if not source_identifier:
            raise ValueError("Source order is missing a stable identifier")
        return self._mirrored_order_key(
            relationship_id=str(relationship["id"]),
            source_identifier=source_identifier,
        )

    @staticmethod
    def _source_order_identifier(action: dict[str, Any]) -> str:
        client_order_id = str(action.get("client_order_id") or "").strip()
        if client_order_id:
            return client_order_id
        order_id = action.get("order_id")
        if order_id not in (None, ""):
            return str(order_id).strip()
        return ""

    @staticmethod
    def _mirrored_order_key(*, relationship_id: str, source_identifier: str) -> str:
        trimmed_relationship = relationship_id.replace("-", "")[:12]
        trimmed_source = source_identifier.replace(" ", "").replace("-", "")[:32]
        return f"mirror-{trimmed_relationship}-{trimmed_source}"

    @property
    def is_running(self) -> bool:
        return bool(self._task and not self._task.done())
