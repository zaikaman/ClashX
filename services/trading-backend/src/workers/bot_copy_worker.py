from __future__ import annotations

import asyncio
import contextlib
import logging
import uuid
from datetime import UTC, datetime
from time import monotonic
from decimal import ROUND_DOWN, ROUND_UP, Decimal
from time import perf_counter
from typing import Any

from src.core.performance_metrics import get_performance_metrics_store
from src.services.event_broadcaster import broadcaster
from src.services.pacifica_auth_service import PacificaAuthService
from src.services.pacifica_client import PacificaClientError, get_pacifica_client
from src.services.supabase_rest import SupabaseRestClient, SupabaseRestError
from src.services.worker_coordination_service import WorkerCoordinationService


logger = logging.getLogger(__name__)
POSITION_MUTATING_ACTION_TYPES = {"open_long", "open_short", "place_market_order", "close_position"}
POSITION_REQUIRED_ACTION_TYPES = {"close_position", "set_tpsl"}


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
        self._source_event_queue: asyncio.Queue[tuple[str, dict[str, Any]]] = asyncio.Queue()
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

    def submit_source_event(self, *, source_runtime_id: str, source_event: dict[str, Any]) -> None:
        self._source_event_queue.put_nowait((source_runtime_id, dict(source_event)))

    async def run_forever(self) -> None:
        next_poll_at = monotonic()
        while self._running:
            try:
                timeout_seconds = max(0.0, next_poll_at - monotonic())
                source_runtime_id, source_event = await asyncio.wait_for(
                    self._source_event_queue.get(),
                    timeout=timeout_seconds,
                )
            except TimeoutError:
                await self._run_poll_iteration()
                next_poll_at = monotonic() + self.poll_interval_seconds
                continue

            event_started = perf_counter()
            try:
                await self._process_source_runtime_event(
                    source_runtime_id=source_runtime_id,
                    source_event=source_event,
                )
                self.last_iteration_at = datetime.now(tz=UTC).isoformat()
                self.last_error = None
            except SupabaseRestError as exc:
                self.last_error = str(exc)
                if exc.is_retryable:
                    logger.warning(
                        "Bot copy worker source event deferred because Supabase is temporarily unavailable: %s",
                        exc,
                    )
                else:
                    logger.exception("Bot copy worker source event failed")
            except Exception as exc:
                self.last_error = str(exc)
                logger.exception("Bot copy worker source event failed")
            finally:
                self._metrics.record("worker:bot_copy:source_event", (perf_counter() - event_started) * 1000.0)

            if monotonic() >= next_poll_at:
                await self._run_poll_iteration()
                next_poll_at = monotonic() + self.poll_interval_seconds

    async def _run_poll_iteration(self) -> None:
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

    async def _process_source_runtime_event(self, *, source_runtime_id: str, source_event: dict[str, Any]) -> None:
        relationships = await asyncio.to_thread(
            self._supabase.select,
            "bot_copy_relationships",
            columns="id,source_runtime_id,follower_user_id,follower_wallet_address,scale_bps,updated_at",
            filters={
                "status": "active",
                "mode": "mirror",
                "source_runtime_id": source_runtime_id,
            },
        )
        for relationship in relationships:
            lease_key = f"bot-copy:{relationship['id']}"
            if not self._claim_local_lease(
                lease_key,
                ttl_seconds=max(20, int(self.poll_interval_seconds * 3)),
            ):
                continue
            await self._process_relationship_source_events(
                relationship,
                [source_event],
                verify_source_runtime_active=False,
            )

    async def _process_relationship(self, relationship: dict[str, Any]) -> None:
        await self._process_relationship_source_events(
            relationship,
            verify_source_runtime_active=True,
        )

    async def _process_relationship_source_events(
        self,
        relationship: dict[str, Any],
        source_events: list[dict[str, Any]] | None = None,
        *,
        verify_source_runtime_active: bool,
    ) -> None:
        if verify_source_runtime_active:
            runtime = await asyncio.to_thread(
                self._supabase.maybe_one,
                "bot_runtimes",
                columns="id,status",
                filters={"id": relationship["source_runtime_id"]},
                cache_ttl_seconds=30,
            )
            if runtime is None or runtime["status"] != "active":
                return

        resolved_source_events = source_events
        if resolved_source_events is None:
            resolved_source_events = list(
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
        if not resolved_source_events:
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

        markets, follower_positions = await asyncio.gather(
            self._safe_load(self._pacifica.get_markets, []),
            self._safe_load(lambda: self._pacifica.get_positions(relationship["follower_wallet_address"]), []),
        )
        market_lookup = self._build_symbol_lookup(markets)
        position_lookup = self._build_symbol_lookup(follower_positions)
        latest_processed_at = self._parse_timestamp(relationship.get("updated_at"))

        for source_event in resolved_source_events:
            source_event_created_at = self._parse_timestamp(source_event.get("created_at"))
            if source_event_created_at is not None and (
                latest_processed_at is None or source_event_created_at > latest_processed_at
            ):
                latest_processed_at = source_event_created_at
            marker = f"bot_copy.mirror:{relationship['id']}:{source_event['id']}"
            seen = await asyncio.to_thread(
                self._supabase.maybe_one,
                "audit_events",
                filters={"action": marker},
            )
            if seen is not None:
                continue

            action = source_event["request_payload"] if isinstance(source_event.get("request_payload"), dict) else {}
            action_type = str(action.get("type") or "")
            symbol = self._normalize_symbol(action.get("symbol"))
            if action_type in POSITION_REQUIRED_ACTION_TYPES:
                position_lookup = await self._refresh_position_lookup(
                    relationship["follower_wallet_address"],
                    current_lookup=position_lookup,
                    symbol=symbol or None,
                    attempts=4 if action_type == "set_tpsl" else 1,
                    delay_seconds=0.5 if action_type == "set_tpsl" else 0.0,
                )
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

            if status == "mirrored" and action_type in POSITION_MUTATING_ACTION_TYPES:
                position_lookup = await self._refresh_position_lookup(
                    relationship["follower_wallet_address"],
                    current_lookup=position_lookup,
                    symbol=symbol or None,
                    attempts=4 if action_type != "close_position" else 1,
                    delay_seconds=0.5 if action_type != "close_position" else 0.0,
                )

            execution_record = self._build_execution_record(
                relationship=relationship,
                source_event=source_event,
                action=action,
                result=result,
                status=status,
                error_reason=error_reason,
            )
            await asyncio.to_thread(
                self._supabase.insert,
                "bot_copy_execution_events",
                execution_record,
                returning="minimal",
            )
            await asyncio.to_thread(
                self._supabase.insert,
                "audit_events",
                {
                    "id": str(uuid.uuid4()),
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

        updated_at = latest_processed_at.isoformat() if latest_processed_at is not None else datetime.now(tz=UTC).isoformat()
        await asyncio.to_thread(
            self._supabase.update,
            "bot_copy_relationships",
            {"updated_at": updated_at},
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
        }
        if symbol:
            payload["symbol"] = symbol

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
            self._validate_market_leverage(market_lookup=market_lookup, symbol=symbol, leverage=leverage)
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
                await self._ensure_leverage(
                    wallet_address=credentials["account_address"],
                    credentials=credentials,
                    symbol=symbol,
                    leverage=leverage,
                )
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
            self._validate_market_leverage(market_lookup=market_lookup, symbol=symbol, leverage=leverage)
            reduce_only = self._to_bool(action.get("reduce_only"), False)
            normalized_price = self._build_limit_order_price(
                symbol=symbol,
                side=side,
                price=price,
                market_lookup=market_lookup,
            )
            amount = self._resolve_order_quantity(
                action=action,
                scale_bps=scale_bps,
                market_lookup=market_lookup,
                symbol=symbol,
                reference_price=price,
            )
            if not reduce_only:
                await self._ensure_leverage(
                    wallet_address=credentials["account_address"],
                    credentials=credentials,
                    symbol=symbol,
                    leverage=leverage,
                )
            response = await self._pacifica.place_order(
                {
                    "type": "create_order",
                    **payload,
                    "side": "bid" if side == "long" else "ask",
                    "amount": amount,
                    "price": normalized_price,
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
                "reference_price": normalized_price,
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
            self._validate_market_leverage(market_lookup=market_lookup, symbol=symbol, leverage=leverage)
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
                await self._ensure_leverage(
                    wallet_address=credentials["account_address"],
                    credentials=credentials,
                    symbol=symbol,
                    leverage=leverage,
                )
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
            response = await self._pacifica.place_order(
                {"type": "create_market_order", **payload, "side": close_side, "amount": amount, "reduce_only": True}
            )
            response["execution_meta"] = {
                "symbol": symbol,
                "side": close_side,
                "position_side": "long" if side in {"bid", "long"} else "short",
                "amount": amount,
                "reduce_only": True,
                "reference_price": float(
                    follower_position.get("mark_price")
                    or (market_lookup.get(symbol) or {}).get("mark_price")
                    or 0
                ),
            }
            return response

        if action_type == "set_tpsl":
            follower_position = position_lookup.get(symbol)
            if not isinstance(follower_position, dict):
                raise ValueError("No follower position available for TP/SL")
            amount = abs(float(follower_position.get("amount") or 0))
            market = market_lookup.get(symbol) or {}
            mark_price = float(follower_position.get("mark_price") or market.get("mark_price") or 0)
            tick_size = float(market.get("tick_size") or 0)
            if amount <= 0 or mark_price <= 0:
                raise ValueError("Cannot set TP/SL without valid follower position")
            tp_pct = float(action.get("take_profit_pct") or 0)
            sl_pct = float(action.get("stop_loss_pct") or 0)
            side = str(follower_position.get("side") or "").lower()
            close_side = "ask" if side in {"bid", "long"} else "bid"
            source_take_profit, source_stop_loss = self._extract_source_tpsl_orders(source_event=source_event)
            source_take_profit_price = self._to_float((source_take_profit or {}).get("stop_price"), 0.0)
            source_stop_loss_price = self._to_float((source_stop_loss or {}).get("stop_price"), 0.0)
            if source_take_profit_price > 0 and source_stop_loss_price > 0:
                take_profit_price = source_take_profit_price
                stop_loss_price = source_stop_loss_price
            elif side in {"bid", "long"}:
                take_profit_price = self._normalize_price_to_tick(
                    mark_price * (1 + tp_pct / 100),
                    tick_size=tick_size,
                    rounding=ROUND_UP,
                )
                stop_loss_price = self._normalize_price_to_tick(
                    mark_price * (1 - sl_pct / 100),
                    tick_size=tick_size,
                    rounding=ROUND_DOWN,
                )
            else:
                take_profit_price = self._normalize_price_to_tick(
                    mark_price * (1 - tp_pct / 100),
                    tick_size=tick_size,
                    rounding=ROUND_DOWN,
                )
                stop_loss_price = self._normalize_price_to_tick(
                    mark_price * (1 + sl_pct / 100),
                    tick_size=tick_size,
                    rounding=ROUND_UP,
                )
            min_reference_price, max_reference_price = self._protective_price_bounds(
                position=follower_position,
                market=market,
            )
            if side in {"bid", "long"}:
                take_profit_price = self._ensure_price_above_reference(
                    take_profit_price,
                    reference_price=max_reference_price,
                    tick_size=tick_size,
                )
                stop_loss_price = self._ensure_price_below_reference(
                    stop_loss_price,
                    reference_price=min_reference_price,
                    tick_size=tick_size,
                )
            else:
                take_profit_price = self._ensure_price_below_reference(
                    take_profit_price,
                    reference_price=min_reference_price,
                    tick_size=tick_size,
                )
                stop_loss_price = self._ensure_price_above_reference(
                    stop_loss_price,
                    reference_price=max_reference_price,
                    tick_size=tick_size,
                )
            take_profit_request = {"amount": amount, "stop_price": take_profit_price}
            stop_loss_request = {"amount": amount, "stop_price": stop_loss_price}
            mirrored_take_profit_client_order_id = self._mirror_nested_client_order_id(
                relationship=relationship,
                source_order=source_take_profit,
            )
            mirrored_stop_loss_client_order_id = self._mirror_nested_client_order_id(
                relationship=relationship,
                source_order=source_stop_loss,
            )
            if mirrored_take_profit_client_order_id:
                take_profit_request["client_order_id"] = mirrored_take_profit_client_order_id
            if mirrored_stop_loss_client_order_id:
                stop_loss_request["client_order_id"] = mirrored_stop_loss_client_order_id
            response = await self._pacifica.place_order(
                {
                    "type": "set_position_tpsl",
                    **payload,
                    "side": close_side,
                    "take_profit": take_profit_request,
                    "stop_loss": stop_loss_request,
                }
            )
            response["execution_meta"] = {
                "symbol": symbol,
                "side": side,
                "position_side": "long" if side in {"bid", "long"} else "short",
                "amount": amount,
                "reduce_only": False,
                "reference_price": mark_price,
                "take_profit_client_order_id": mirrored_take_profit_client_order_id,
                "stop_loss_client_order_id": mirrored_stop_loss_client_order_id,
            }
            return response

        if action_type == "update_leverage":
            if not symbol:
                raise ValueError("Leverage updates require a symbol")
            leverage = max(1, int(float(action.get("leverage") or 1)))
            self._validate_market_leverage(market_lookup=market_lookup, symbol=symbol, leverage=leverage)
            response = await self._pacifica.place_order({"type": "update_leverage", **payload, "leverage": leverage})
            response["execution_meta"] = {
                "symbol": symbol,
                "side": None,
                "position_side": None,
                "amount": 0.0,
                "reduce_only": False,
                "reference_price": float((market_lookup.get(symbol) or {}).get("mark_price") or 0),
            }
            return response

        if action_type == "cancel_order":
            if not symbol:
                raise ValueError("Cancel order requires a symbol")
            response = await self._pacifica.place_order(
                {
                    "type": "cancel_order",
                    **payload,
                    **self._extract_mirrored_order_identifier(relationship=relationship, source_event=source_event, action=action),
                }
            )
            response["execution_meta"] = {
                "symbol": symbol,
                "side": str(action.get("side") or "").lower().strip() or None,
                "position_side": None,
                "amount": 0.0,
                "reduce_only": self._to_bool(action.get("reduce_only"), False),
                "reference_price": float((market_lookup.get(symbol) or {}).get("mark_price") or 0),
            }
            return response

        if action_type == "cancel_twap_order":
            if not symbol:
                raise ValueError("Cancel TWAP order requires a symbol")
            response = await self._pacifica.place_order(
                {
                    "type": "cancel_twap_order",
                    **payload,
                    **self._extract_mirrored_order_identifier(relationship=relationship, source_event=source_event, action=action),
                }
            )
            response["execution_meta"] = {
                "symbol": symbol,
                "side": str(action.get("side") or "").lower().strip() or None,
                "position_side": None,
                "amount": 0.0,
                "reduce_only": self._to_bool(action.get("reduce_only"), False),
                "reference_price": float((market_lookup.get(symbol) or {}).get("mark_price") or 0),
            }
            return response

        if action_type == "cancel_all_orders":
            if not self._to_bool(action.get("all_symbols"), True) and not symbol:
                raise ValueError("Cancel all orders requires a symbol when all_symbols is false")
            response = await self._pacifica.place_order(
                {
                    "type": "cancel_all_orders",
                    **payload,
                    "all_symbols": self._to_bool(action.get("all_symbols"), True),
                    "exclude_reduce_only": self._to_bool(action.get("exclude_reduce_only"), False),
                }
            )
            response["execution_meta"] = {
                "symbol": symbol or None,
                "side": None,
                "position_side": None,
                "amount": 0.0,
                "reduce_only": False,
                "reference_price": float((market_lookup.get(symbol) or {}).get("mark_price") or 0) if symbol else 0.0,
            }
            return response

        raise ValueError(f"Unsupported mirrored action type: {action_type}")

    async def _safe_load(self, loader: Any, fallback: Any) -> Any:
        try:
            return await loader()
        except PacificaClientError:
            return fallback

    async def _ensure_leverage(
        self,
        *,
        wallet_address: str,
        credentials: dict[str, str],
        symbol: str,
        leverage: int,
    ) -> None:
        settings = await self._safe_load(lambda: self._pacifica.get_account_settings(wallet_address), [])
        current = next(
            (
                item
                for item in settings
                if self._normalize_symbol(item.get("symbol")) == symbol
            ),
            None,
        )
        if isinstance(current, dict) and int(current.get("leverage") or 0) == leverage:
            return
        await self._pacifica.place_order(
            {
                "type": "update_leverage",
                "account": credentials["account_address"],
                "agent_wallet": credentials["agent_wallet_address"],
                "__agent_private_key": credentials["agent_private_key"],
                "symbol": symbol,
                "leverage": leverage,
            }
        )
        for attempt in range(4):
            settings = await self._safe_load(lambda: self._pacifica.get_account_settings(wallet_address), [])
            current = next(
                (
                    item
                    for item in settings
                    if self._normalize_symbol(item.get("symbol")) == symbol
                ),
                None,
            )
            if isinstance(current, dict) and int(current.get("leverage") or 0) == leverage:
                return
            if attempt < 3:
                await asyncio.sleep(0.25)
        raise ValueError(f"Failed to confirm {symbol} leverage is set to {leverage}x before mirroring the order.")

    @classmethod
    def _build_symbol_lookup(cls, rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        return {
            cls._normalize_symbol(item.get("symbol")): item
            for item in rows
            if isinstance(item, dict) and cls._normalize_symbol(item.get("symbol"))
        }

    async def _refresh_position_lookup(
        self,
        wallet_address: str,
        *,
        current_lookup: dict[str, dict[str, Any]],
        symbol: str | None,
        attempts: int,
        delay_seconds: float,
    ) -> dict[str, dict[str, Any]]:
        refreshed_lookup = current_lookup
        for attempt in range(max(1, attempts)):
            positions = await self._safe_load(lambda: self._pacifica.get_positions(wallet_address), None)
            if isinstance(positions, list):
                refreshed_lookup = self._build_symbol_lookup(positions)
            if not symbol or symbol in refreshed_lookup:
                return refreshed_lookup
            if delay_seconds > 0 and attempt + 1 < max(1, attempts):
                await asyncio.sleep(delay_seconds)
        return refreshed_lookup

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
        market = self._resolve_market(market_lookup, symbol)
        raw_quantity = float(action.get("quantity") or 0)
        scaled_quantity = raw_quantity * (scale_bps / 10_000)
        if scaled_quantity > 0:
            return self._normalize_order_quantity(
                scaled_quantity,
                lot_size=float(market.get("lot_size") or 0),
                symbol=symbol,
            )

        resolved_price = reference_price if reference_price is not None else float(market.get("mark_price") or 0)
        if resolved_price <= 0:
            raise ValueError("Cannot mirror open action without valid mark price and size")
        size_usd = float(action.get("size_usd") or 0)
        mirrored_size_usd = size_usd * (scale_bps / 10_000)
        if mirrored_size_usd <= 0:
            raise ValueError("Cannot mirror open action without valid mark price and size")
        leverage = 1 if self._to_bool(action.get("reduce_only"), False) else max(1, int(float(action.get("leverage") or 1)))
        return self._normalize_order_quantity(
            (mirrored_size_usd * leverage) / resolved_price,
            lot_size=float(market.get("lot_size") or 0),
            symbol=symbol,
        )

    @staticmethod
    def _resolve_market(market_lookup: dict[str, dict[str, Any]], symbol: str) -> dict[str, Any]:
        market = market_lookup.get(symbol)
        if isinstance(market, dict):
            return market
        raise ValueError(f"Market price unavailable for {symbol}")

    @staticmethod
    def _normalize_order_quantity(quantity: float, *, lot_size: float, symbol: str) -> float:
        normalized = Decimal(str(quantity))
        if lot_size > 0:
            step = Decimal(str(lot_size))
            normalized = (normalized / step).to_integral_value(rounding=ROUND_DOWN) * step
        normalized_float = float(normalized)
        if normalized_float <= 0:
            raise ValueError(f"Order size is below the minimum tradable increment for {symbol}.")
        return normalized_float

    @staticmethod
    def _normalize_price_to_tick(price: float, *, tick_size: float, rounding: str) -> float:
        normalized = Decimal(str(price))
        if tick_size > 0:
            tick = Decimal(str(tick_size))
            normalized = (normalized / tick).to_integral_value(rounding=rounding) * tick
        return float(normalized)

    @staticmethod
    def _protective_price_bounds(*, position: dict[str, Any], market: dict[str, Any]) -> tuple[float, float]:
        candidates: list[float] = []
        for source in (position, market):
            if not isinstance(source, dict):
                continue
            for key in ("mark_price", "mid_price", "oracle_price"):
                try:
                    value = float(source.get(key) or 0.0)
                except (TypeError, ValueError):
                    value = 0.0
                if value > 0:
                    candidates.append(value)
        if not candidates:
            return 0.0, 0.0
        return min(candidates), max(candidates)

    @classmethod
    def _ensure_price_above_reference(cls, price: float, *, reference_price: float, tick_size: float) -> float:
        if reference_price <= 0 or price > reference_price:
            return price
        minimum_valid_price = reference_price + (tick_size if tick_size > 0 else max(reference_price * 1e-6, 1e-6))
        return cls._normalize_price_to_tick(
            minimum_valid_price,
            tick_size=tick_size,
            rounding=ROUND_UP,
        )

    @classmethod
    def _ensure_price_below_reference(cls, price: float, *, reference_price: float, tick_size: float) -> float:
        if reference_price <= 0 or price < reference_price:
            return price
        maximum_valid_price = reference_price - (tick_size if tick_size > 0 else max(reference_price * 1e-6, 1e-6))
        if maximum_valid_price <= 0:
            return price
        return cls._normalize_price_to_tick(
            maximum_valid_price,
            tick_size=tick_size,
            rounding=ROUND_DOWN,
        )

    def _build_limit_order_price(
        self,
        *,
        symbol: str,
        side: str,
        price: float,
        market_lookup: dict[str, dict[str, Any]],
    ) -> float:
        market = self._resolve_market(market_lookup, symbol)
        tick_size = float(market.get("tick_size") or 0)
        rounding = ROUND_DOWN if side == "long" else ROUND_UP
        return self._normalize_price_to_tick(
            price,
            tick_size=tick_size,
            rounding=rounding,
        )

    def _validate_market_leverage(
        self,
        *,
        market_lookup: dict[str, dict[str, Any]],
        symbol: str,
        leverage: int,
    ) -> None:
        market = market_lookup.get(symbol)
        if not isinstance(market, dict):
            return
        market_max_leverage = self._to_int(market.get("max_leverage"))
        if market_max_leverage is None or market_max_leverage <= 0:
            return
        if leverage > market_max_leverage:
            raise ValueError(
                f"Requested leverage {leverage} exceeds {symbol} market max leverage {market_max_leverage}."
            )

    @staticmethod
    def _to_int(value: Any) -> int | None:
        try:
            if value in (None, ""):
                return None
            return int(float(value))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _to_float(value: Any, default: float = 0.0) -> float:
        try:
            if value in (None, ""):
                return default
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _normalize_symbol(value: Any) -> str:
        return str(value or "").upper().replace("-PERP", "").strip()

    @staticmethod
    def _parse_timestamp(value: Any) -> datetime | None:
        if not value:
            return None
        if isinstance(value, datetime):
            return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)

    @staticmethod
    def _extract_source_tpsl_orders(source_event: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        result_payload = source_event.get("result_payload") if isinstance(source_event.get("result_payload"), dict) else {}
        request_payload = result_payload.get("payload") if isinstance(result_payload.get("payload"), dict) else {}
        take_profit = request_payload.get("take_profit") if isinstance(request_payload.get("take_profit"), dict) else None
        stop_loss = request_payload.get("stop_loss") if isinstance(request_payload.get("stop_loss"), dict) else None
        return take_profit, stop_loss

    def _mirror_nested_client_order_id(
        self,
        *,
        relationship: dict[str, Any],
        source_order: dict[str, Any] | None,
    ) -> str | None:
        if not isinstance(source_order, dict):
            return None
        source_identifier = self._source_order_identifier(source_order)
        if not source_identifier:
            return None
        return self._mirrored_order_key(
            relationship_id=str(relationship["id"]),
            source_identifier=source_identifier,
        )

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

    def _build_execution_record(
        self,
        *,
        relationship: dict[str, Any],
        source_event: dict[str, Any],
        action: dict[str, Any],
        result: dict[str, Any],
        status: str,
        error_reason: str | None,
    ) -> dict[str, Any]:
        now = datetime.now(tz=UTC).isoformat()
        execution_meta = result.get("execution_meta") if isinstance(result.get("execution_meta"), dict) else {}
        response_payload = result.get("response") if isinstance(result.get("response"), dict) else {}
        action_type = str(action.get("type") or "")
        symbol = str(execution_meta.get("symbol") or action.get("symbol") or "").upper().replace("-PERP", "")
        order_side = execution_meta.get("side")
        normalized_order_side = None
        if isinstance(order_side, str):
            normalized_order_side = "long" if order_side in {"bid", "long"} else "short" if order_side in {"ask", "short"} else order_side
        action_side = str(action.get("side") or "").lower().strip()
        reduce_only = bool(execution_meta.get("reduce_only")) or self._to_bool(action.get("reduce_only"), False) or action_type == "close_position"
        position_side = execution_meta.get("position_side")
        if not isinstance(position_side, str) or not position_side:
            if action_type == "open_long":
                position_side = "long"
            elif action_type == "open_short":
                position_side = "short"
            elif action_type in {"place_market_order", "place_limit_order", "place_twap_order"}:
                position_side = action_side if action_side in {"long", "short"} else normalized_order_side
            else:
                position_side = normalized_order_side
        copied_quantity = float(execution_meta.get("amount") or action.get("quantity") or 0)
        reference_price = float(execution_meta.get("reference_price") or action.get("price") or 0)
        if reference_price <= 0:
            reference_price = float(action.get("mark_price") or 0)
        return {
            "id": str(uuid.uuid4()),
            "relationship_id": relationship["id"],
            "source_runtime_id": relationship["source_runtime_id"],
            "source_event_id": source_event["id"],
            "follower_user_id": relationship["follower_user_id"],
            "follower_wallet_address": relationship["follower_wallet_address"],
            "symbol": symbol,
            "side": normalized_order_side,
            "position_side": position_side,
            "action_type": action_type,
            "reduce_only": reduce_only,
            "requested_quantity": float(action.get("quantity") or 0),
            "copied_quantity": copied_quantity,
            "reference_price": reference_price,
            "notional_estimate_usd": round(copied_quantity * reference_price, 2) if copied_quantity > 0 and reference_price > 0 else 0.0,
            "request_id": result.get("request_id"),
            "client_order_id": response_payload.get("client_order_id") or action.get("client_order_id"),
            "status": "mirrored" if status == "mirrored" else "error",
            "error_reason": error_reason,
            "result_payload_json": result,
            "created_at": now,
            "updated_at": now,
        }

    @property
    def is_running(self) -> bool:
        return bool(self._task and not self._task.done())
