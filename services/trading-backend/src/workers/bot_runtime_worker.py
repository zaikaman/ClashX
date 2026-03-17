from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import logging
from datetime import UTC, datetime
from decimal import ROUND_DOWN, Decimal
from typing import Any

from src.services.bot_risk_service import BotRiskService
from src.services.bot_runtime_engine import BotRuntimeEngine
from src.services.event_broadcaster import broadcaster
from src.services.indicator_context_service import IndicatorContextService
from src.services.pacifica_auth_service import PacificaAuthService
from src.services.pacifica_client import PacificaClient, PacificaClientError
from src.services.rules_engine import RulesEngine
from src.services.supabase_rest import SupabaseRestClient
from src.services.worker_coordination_service import WorkerCoordinationService


logger = logging.getLogger(__name__)


class BotRuntimeWorker:
    def __init__(self, poll_interval_seconds: float = 4.0) -> None:
        self.poll_interval_seconds = poll_interval_seconds
        self._task: asyncio.Task | None = None
        self._running = False
        self._engine = BotRuntimeEngine()
        self._rules = RulesEngine()
        self._risk = BotRiskService()
        self._auth = PacificaAuthService()
        self._pacifica = PacificaClient()
        self._indicator_context = IndicatorContextService(self._pacifica)
        self._supabase = SupabaseRestClient()
        self._coordination = WorkerCoordinationService(self._supabase)
        self.last_iteration_at: str | None = None
        self.last_error: str | None = None

    def start(self) -> asyncio.Task:
        if self._task and not self._task.done():
            return self._task
        self._running = True
        self._task = asyncio.create_task(self.run_forever(), name="bot-runtime-worker")
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
                runtimes = list(self._engine.get_active_runtimes(None))
                for runtime in runtimes:
                    lease_key = f"bot-runtime:{runtime['id']}"
                    if not self._coordination.try_claim_lease(
                        lease_key, ttl_seconds=max(15, int(self.poll_interval_seconds * 3))
                    ):
                        continue
                    try:
                        await self._process_runtime(None, runtime)
                    finally:
                        self._coordination.release_lease(lease_key)
                self.last_iteration_at = datetime.now(tz=UTC).isoformat()
                self.last_error = None
            except Exception as exc:
                self.last_error = str(exc)
                logger.exception("Bot runtime worker iteration failed")
            await asyncio.sleep(self.poll_interval_seconds)

    async def _process_runtime(self, db: Any, runtime: dict[str, Any]) -> None:
        del db
        now = datetime.now(tz=UTC)
        bot = self._supabase.maybe_one("bot_definitions", filters={"id": runtime["bot_definition_id"]})
        if bot is None:
            runtime = self._update_runtime(runtime, {"status": "failed", "updated_at": now})
            self._engine.append_execution_event(
                None,
                runtime=runtime,
                event_type="runtime.failed",
                decision_summary="bot definition missing",
                request_payload={"bot_definition_id": runtime["bot_definition_id"]},
                result_payload={},
                status="error",
                error_reason="Bot definition not found",
            )
            return

        credentials = self._auth.get_trading_credentials(None, runtime["wallet_address"])
        if credentials is None:
            runtime = self._update_runtime(runtime, {"status": "paused", "updated_at": now})
            self._engine.append_execution_event(
                None,
                runtime=runtime,
                event_type="runtime.paused",
                decision_summary="delegated authorization missing",
                request_payload={},
                result_payload={"status": "paused"},
                status="error",
                error_reason="Delegated authorization is required",
            )
            await broadcaster.publish(
                channel=f"user:{runtime['user_id']}",
                event="bot.runtime.authorization_required",
                payload={"runtime_id": runtime["id"], "bot_id": bot["id"]},
            )
            return

        markets, positions = await asyncio.gather(
            self._safe_load(self._pacifica.get_markets, []),
            self._safe_load(lambda: self._pacifica.get_positions(runtime["wallet_address"]), []),
        )
        market_lookup = self._build_market_lookup(markets)
        position_lookup = self._build_position_lookup(positions)
        rules_json = bot["rules_json"] if isinstance(bot.get("rules_json"), dict) else {}
        candle_lookup = await self._indicator_context.load_candle_lookup(rules_json)

        runtime_policy = self._risk.normalize_policy(runtime.get("risk_policy_json") if isinstance(runtime.get("risk_policy_json"), dict) else {})
        runtime_state = runtime_policy.get("_runtime_state") if isinstance(runtime_policy.get("_runtime_state"), dict) else {}
        evaluation = self._rules.evaluate(
            rules_json=rules_json,
            context={
                "runtime": {"id": runtime["id"], "state": runtime_state},
                "market_lookup": market_lookup,
                "candle_lookup": candle_lookup,
                "position_lookup": position_lookup,
            },
        )
        if not evaluation.get("triggered"):
            self._update_runtime(runtime, {"updated_at": now})
            return

        runtime_touched = False
        coordination = self._coordination if getattr(self._coordination, "_supabase", None) is self._supabase else WorkerCoordinationService(self._supabase)
        for action in evaluation.get("actions") or []:
            idempotency_key = self._build_idempotency_key(runtime_id=runtime["id"], action=action)
            if not coordination.try_claim_action(runtime_id=runtime["id"], idempotency_key=idempotency_key):
                continue

            issues = self._risk.assess_action(policy=runtime_policy, action=action, runtime_state=runtime_state)
            if issues:
                event = self._engine.append_execution_event(
                    None,
                    runtime=runtime,
                    event_type="action.skipped",
                    decision_summary=idempotency_key,
                    request_payload=action,
                    result_payload={"issues": issues},
                    status="skipped",
                )
                await broadcaster.publish(
                    channel=f"user:{runtime['user_id']}",
                    event="bot.execution.skipped",
                    payload=self._serialize_event_payload(event),
                )
                continue

            try:
                response = await self._execute_action(
                    action=action,
                    credentials=credentials,
                    market_lookup=market_lookup,
                    position_lookup=position_lookup,
                )
                runtime_policy = self._risk.mark_execution(policy=runtime_policy, success=True)
                runtime_state = runtime_policy.get("_runtime_state") if isinstance(runtime_policy.get("_runtime_state"), dict) else {}
                runtime = self._update_runtime(
                    runtime,
                    {"risk_policy_json": runtime_policy, "updated_at": datetime.now(tz=UTC)},
                )
                runtime_touched = True
                event = self._engine.append_execution_event(
                    None,
                    runtime=runtime,
                    event_type="action.executed",
                    decision_summary=idempotency_key,
                    request_payload=action,
                    result_payload=response,
                    status="success",
                )
                await broadcaster.publish(
                    channel=f"user:{runtime['user_id']}",
                    event="bot.execution.success",
                    payload=self._serialize_event_payload(event),
                )
            except (PacificaClientError, ValueError) as exc:
                runtime_policy = self._risk.mark_execution(policy=runtime_policy, success=False)
                runtime_state = runtime_policy.get("_runtime_state") if isinstance(runtime_policy.get("_runtime_state"), dict) else {}
                runtime = self._update_runtime(
                    runtime,
                    {"risk_policy_json": runtime_policy, "updated_at": datetime.now(tz=UTC)},
                )
                runtime_touched = True
                event = self._engine.append_execution_event(
                    None,
                    runtime=runtime,
                    event_type="action.failed",
                    decision_summary=idempotency_key,
                    request_payload=action,
                    result_payload={},
                    status="error",
                    error_reason=str(exc),
                )
                await broadcaster.publish(
                    channel=f"user:{runtime['user_id']}",
                    event="bot.execution.failed",
                    payload=self._serialize_event_payload(event),
                )

        if not runtime_touched:
            self._update_runtime(runtime, {"updated_at": datetime.now(tz=UTC)})

    async def _execute_action(
        self,
        *,
        action: dict[str, Any],
        credentials: dict[str, str],
        market_lookup: dict[str, dict[str, Any]],
        position_lookup: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        action_type = str(action.get("type") or "")
        symbol = self._normalize_symbol(action.get("symbol"))
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
            side = "long" if action_type == "open_long" else "short" if action_type == "open_short" else str(action.get("side") or "").lower().strip()
            if side not in {"long", "short"}:
                raise ValueError("Market orders require side to be long or short")
            leverage = max(1, int(float(action.get("leverage") or 1)))
            reduce_only = self._to_bool(action.get("reduce_only"), False)
            amount = self._resolve_order_quantity(action=action, market_lookup=market_lookup, symbol=symbol, reference_price=None)
            if not reduce_only:
                await self._pacifica.place_order({"type": "update_leverage", **payload, "leverage": leverage})
            return await self._pacifica.place_order(
                {
                    "type": "create_market_order",
                    **payload,
                    "side": self._to_pacifica_side(side),
                    "amount": amount,
                    "reduce_only": reduce_only,
                    "slippage_percent": float(action.get("slippage_percent") or 0.5),
                }
            )

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
            amount = self._resolve_order_quantity(action=action, market_lookup=market_lookup, symbol=symbol, reference_price=price)
            if not reduce_only:
                await self._pacifica.place_order({"type": "update_leverage", **payload, "leverage": leverage})
            return await self._pacifica.place_order(
                {
                    "type": "create_order",
                    **payload,
                    "side": self._to_pacifica_side(side),
                    "amount": amount,
                    "price": price,
                    "tif": str(action.get("tif") or "GTC"),
                    "reduce_only": reduce_only,
                    "client_order_id": action.get("client_order_id"),
                }
            )

        if action_type == "place_twap_order":
            if not symbol:
                raise ValueError("TWAP orders require a symbol")
            side = str(action.get("side") or "").lower().strip()
            if side not in {"long", "short"}:
                raise ValueError("TWAP orders require side to be long or short")
            duration_seconds = max(1, int(float(action.get("duration_seconds") or 0)))
            leverage = max(1, int(float(action.get("leverage") or 1)))
            reduce_only = self._to_bool(action.get("reduce_only"), False)
            amount = self._resolve_order_quantity(action=action, market_lookup=market_lookup, symbol=symbol, reference_price=None)
            if not reduce_only:
                await self._pacifica.place_order({"type": "update_leverage", **payload, "leverage": leverage})
            return await self._pacifica.place_order(
                {
                    "type": "create_twap_order",
                    **payload,
                    "side": self._to_pacifica_side(side),
                    "amount": amount,
                    "reduce_only": reduce_only,
                    "duration_in_seconds": duration_seconds,
                    "slippage_percent": float(action.get("slippage_percent") or 0.5),
                    "client_order_id": action.get("client_order_id"),
                }
            )

        if action_type == "close_position":
            if not symbol:
                raise ValueError("Close position requires a symbol")
            position = position_lookup.get(symbol)
            if not isinstance(position, dict):
                raise ValueError(f"No open position to close for {symbol}")
            amount = abs(float(position.get("amount") or 0))
            if amount <= 0:
                raise ValueError(f"No open position to close for {symbol}")
            side = str(position.get("side") or "").lower()
            close_side = "ask" if side in {"bid", "long"} else "bid"
            return await self._pacifica.place_order(
                {"type": "create_market_order", **payload, "side": close_side, "amount": amount, "reduce_only": True}
            )

        if action_type == "set_tpsl":
            position = position_lookup.get(symbol)
            if not isinstance(position, dict):
                raise ValueError(f"No open position available for TP/SL on {symbol}")
            amount = abs(float(position.get("amount") or 0))
            market = self._resolve_market(market_lookup, symbol)
            mark_price = float(position.get("mark_price") or market.get("mark_price") or 0)
            if amount <= 0 or mark_price <= 0:
                raise ValueError(f"Cannot set TP/SL without valid position price for {symbol}")
            tp_pct = float(action.get("take_profit_pct") or 0)
            sl_pct = float(action.get("stop_loss_pct") or 0)
            side = str(position.get("side") or "").lower()
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
            return await self._pacifica.place_order({"type": "cancel_order", **payload, **self._extract_order_identifier(action)})

        if action_type == "cancel_twap_order":
            if not symbol:
                raise ValueError("Cancel TWAP order requires a symbol")
            return await self._pacifica.place_order({"type": "cancel_twap_order", **payload, **self._extract_order_identifier(action)})

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

        raise ValueError(f"Unsupported action type: {action_type}")

    async def _safe_load(self, loader: Any, fallback: Any) -> Any:
        try:
            return await loader()
        except PacificaClientError:
            return fallback

    @staticmethod
    def _build_idempotency_key(*, runtime_id: str, action: dict[str, Any]) -> str:
        bucket = int(datetime.now(tz=UTC).timestamp() // 30)
        payload = json.dumps(action, sort_keys=True, default=str)
        digest = hashlib.sha256(f"{runtime_id}:{bucket}:{payload}".encode()).hexdigest()[:24]
        return f"idem:{runtime_id}:{bucket}:{digest}"

    def _update_runtime(self, runtime: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
        serialized_updates = {key: value.isoformat() if isinstance(value, datetime) else value for key, value in updates.items()}
        return self._supabase.update("bot_runtimes", serialized_updates, filters={"id": runtime["id"]})[0]

    @staticmethod
    def _normalize_symbol(value: Any) -> str:
        return str(value or "").upper().replace("-PERP", "").strip()

    @staticmethod
    def _to_pacifica_side(side: str) -> str:
        normalized = side.lower().strip()
        if normalized == "long":
            return "bid"
        if normalized == "short":
            return "ask"
        raise ValueError("Order side must be either 'long' or 'short'.")

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

    def _build_market_lookup(self, markets: list[Any]) -> dict[str, dict[str, Any]]:
        lookup: dict[str, dict[str, Any]] = {}
        for item in markets:
            if not isinstance(item, dict):
                continue
            symbol = self._normalize_symbol(item.get("symbol") or item.get("display_symbol"))
            if symbol:
                lookup[symbol] = item
        return lookup

    def _build_position_lookup(self, positions: list[Any]) -> dict[str, dict[str, Any]]:
        lookup: dict[str, dict[str, Any]] = {}
        for item in positions:
            if not isinstance(item, dict):
                continue
            symbol = self._normalize_symbol(item.get("symbol"))
            if symbol:
                lookup[symbol] = item
        return lookup

    @staticmethod
    def _resolve_market(market_lookup: dict[str, dict[str, Any]], symbol: str) -> dict[str, Any]:
        market = market_lookup.get(symbol)
        if isinstance(market, dict):
            return market
        raise ValueError(f"Market price unavailable for {symbol}")

    def _resolve_order_quantity(
        self,
        *,
        action: dict[str, Any],
        market_lookup: dict[str, dict[str, Any]],
        symbol: str,
        reference_price: float | None,
    ) -> float:
        raw_quantity = float(action.get("quantity") or 0)
        market = self._resolve_market(market_lookup, symbol)
        if raw_quantity > 0:
            return self._normalize_order_quantity(
                raw_quantity,
                lot_size=float(market.get("lot_size") or 0),
                min_order_size=float(market.get("min_order_size") or 0),
                symbol=symbol,
            )
        resolved_price = reference_price if reference_price is not None else float(market.get("mark_price") or 0)
        if resolved_price <= 0:
            raise ValueError(f"Market price unavailable for {symbol}")
        size_usd = float(action.get("size_usd") or 0)
        if size_usd <= 0:
            raise ValueError("Action requires size_usd or quantity greater than zero")
        leverage = max(1, int(float(action.get("leverage") or 1)))
        return self._normalize_order_quantity(
            (size_usd * leverage) / resolved_price,
            lot_size=float(market.get("lot_size") or 0),
            min_order_size=float(market.get("min_order_size") or 0),
            symbol=symbol,
        )

    @staticmethod
    def _extract_order_identifier(action: dict[str, Any]) -> dict[str, Any]:
        order_id = action.get("order_id")
        client_order_id = str(action.get("client_order_id") or "").strip()
        if order_id not in (None, ""):
            if isinstance(order_id, str) and order_id.isdigit():
                return {"order_id": int(order_id)}
            return {"order_id": order_id}
        if client_order_id:
            return {"client_order_id": client_order_id}
        raise ValueError("Action requires order_id or client_order_id")

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
            raise ValueError(f"Order size for {symbol} must be at least {min_order_size:g}. Adjust the USD size or leverage.")
        return normalized_float

    @staticmethod
    def _serialize_event_payload(event: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": event.get("id"),
            "runtime_id": event.get("runtime_id"),
            "event_type": event.get("event_type"),
            "status": event.get("status"),
            "error_reason": event.get("error_reason"),
            "created_at": event.get("created_at"),
            "request_payload": event.get("request_payload") or {},
            "result_payload": event.get("result_payload") or {},
        }

    @property
    def is_running(self) -> bool:
        return bool(self._task and not self._task.done())
