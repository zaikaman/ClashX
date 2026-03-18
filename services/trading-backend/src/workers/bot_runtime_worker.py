from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import logging
from datetime import UTC, datetime
from decimal import ROUND_DOWN, ROUND_UP, Decimal
from typing import Any

from src.services.bot_risk_service import BotRiskService
from src.services.bot_runtime_engine import BotRuntimeEngine
from src.services.bot_performance_service import BotPerformanceService
from src.services.event_broadcaster import broadcaster
from src.services.indicator_context_service import IndicatorContextService
from src.services.pacifica_auth_service import PacificaAuthService
from src.services.pacifica_client import PacificaClient, PacificaClientError
from src.services.rules_engine import RulesEngine
from src.services.supabase_rest import SupabaseRestClient
from src.services.worker_coordination_service import WorkerCoordinationService


logger = logging.getLogger(__name__)
PENDING_ENTRY_TTL_SECONDS = 120


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
        logger.info("Starting bot runtime worker with poll interval %.1fs", self.poll_interval_seconds)
        self._task = asyncio.create_task(self.run_forever(), name="bot-runtime-worker")
        return self._task

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        logger.info("Stopped bot runtime worker")

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
            logger.error(
                "Runtime %s failed because bot definition %s was not found",
                runtime["id"],
                runtime["bot_definition_id"],
            )
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

        markets, positions, open_orders = await asyncio.gather(
            self._safe_load(self._pacifica.get_markets, []),
            self._safe_load(lambda: self._pacifica.get_positions(runtime["wallet_address"]), []),
            self._safe_load(lambda: self._pacifica.get_open_orders(runtime["wallet_address"]), []),
        )
        market_lookup = self._build_market_lookup(markets)
        position_lookup = self._build_position_lookup(positions)
        open_order_lookup = self._build_open_order_lookup(open_orders)
        rules_json = bot["rules_json"] if isinstance(bot.get("rules_json"), dict) else {}
        candle_lookup = await self._indicator_context.load_candle_lookup(rules_json)

        runtime_policy = self._risk.normalize_policy(runtime.get("risk_policy_json") if isinstance(runtime.get("risk_policy_json"), dict) else {})
        performance = await self._calculate_runtime_performance(runtime)
        runtime_policy = self._risk.sync_performance(
            policy=runtime_policy,
            pnl_total=float(performance.get("pnl_total") or 0.0),
            pnl_realized=float(performance.get("pnl_realized") or 0.0),
            pnl_unrealized=float(performance.get("pnl_unrealized") or 0.0),
        )
        runtime = self._update_runtime(
            runtime,
            {"risk_policy_json": runtime_policy, "updated_at": now},
        )
        runtime_state = runtime_policy.get("_runtime_state") if isinstance(runtime_policy.get("_runtime_state"), dict) else {}
        runtime_state = self._reconcile_runtime_state(
            runtime_state=runtime_state,
            position_lookup=position_lookup,
            open_order_lookup=open_order_lookup,
        )
        runtime_policy["_runtime_state"] = runtime_state
        drawdown_reason = self._risk.drawdown_breach_reason(policy=runtime_policy, runtime_state=runtime_state)
        if drawdown_reason is not None:
            logger.warning(
                "Runtime %s stopped by risk policy: %s",
                runtime["id"],
                drawdown_reason,
            )
            runtime = self._update_runtime(
                runtime,
                {
                    "status": "stopped",
                    "stopped_at": now,
                    "risk_policy_json": runtime_policy,
                    "updated_at": now,
                },
            )
            event = self._engine.append_execution_event(
                None,
                runtime=runtime,
                event_type="runtime.stopped",
                decision_summary="runtime stopped after exceeding allocated drawdown budget",
                request_payload={
                    "allocated_capital_usd": runtime_policy.get("allocated_capital_usd"),
                    "max_drawdown_pct": runtime_policy.get("max_drawdown_pct"),
                },
                result_payload={"runtime_state": runtime_state},
                status="success",
                error_reason=drawdown_reason,
            )
            await broadcaster.publish(
                channel=f"user:{runtime['user_id']}",
                event="bot.runtime.stopped",
                payload=self._serialize_event_payload(event),
            )
            return

        credentials = self._auth.get_trading_credentials(None, runtime["wallet_address"])
        if credentials is None:
            logger.warning(
                "Runtime %s paused because delegated Pacifica authorization is missing for wallet %s",
                runtime["id"],
                runtime["wallet_address"],
            )
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
            return

        actions = evaluation.get("actions") or []
        logger.info(
            "Runtime %s triggered for bot %s on wallet %s with %d action(s)",
            runtime["id"],
            bot["id"],
            runtime["wallet_address"],
            len(actions),
        )

        runtime_touched = False
        cycle_runtime_state = dict(runtime_state)
        coordination = self._coordination if getattr(self._coordination, "_supabase", None) is self._supabase else WorkerCoordinationService(self._supabase)
        for action in actions:
            issues = self._risk.assess_action(
                policy=runtime_policy,
                action=action,
                runtime_state=cycle_runtime_state,
                position_lookup=position_lookup,
                open_order_lookup=open_order_lookup,
            )
            if issues:
                skipped_key = self._build_idempotency_key(
                    runtime_id=runtime["id"],
                    action=action,
                    runtime_state=runtime_state,
                    position_lookup=position_lookup,
                )
                event = self._engine.append_execution_event(
                    None,
                    runtime=runtime,
                    event_type="action.skipped",
                    decision_summary=skipped_key,
                    request_payload=action,
                    result_payload={"issues": issues},
                    status="skipped",
                )
                await broadcaster.publish(
                    channel=f"user:{runtime['user_id']}",
                    event="bot.execution.skipped",
                    payload=self._serialize_event_payload(event),
                )
                logger.warning(
                    "Runtime %s skipped action %s for %s: %s",
                    runtime["id"],
                    action.get("type"),
                    action.get("symbol"),
                    "; ".join(issues),
                )
                continue

            idempotency_key = self._build_idempotency_key(
                runtime_id=runtime["id"],
                action=action,
                runtime_state=runtime_state,
                position_lookup=position_lookup,
            )
            if not coordination.try_claim_action(runtime_id=runtime["id"], idempotency_key=idempotency_key):
                continue

            try:
                response = await self._execute_action(
                    action=action,
                    credentials=credentials,
                    market_lookup=market_lookup,
                    position_lookup=position_lookup,
                )
                runtime_policy = self._risk.mark_execution(policy=runtime_policy, success=True)
                persisted_runtime_state = (
                    runtime_policy.get("_runtime_state") if isinstance(runtime_policy.get("_runtime_state"), dict) else {}
                )
                cycle_runtime_state = self._update_runtime_state_for_action(
                    runtime_state=cycle_runtime_state,
                    action=action,
                    position_lookup=position_lookup,
                    open_order_lookup=open_order_lookup,
                    success=True,
                )
                runtime_policy["_runtime_state"] = {**persisted_runtime_state, **cycle_runtime_state}
                runtime = self._update_runtime(
                    runtime,
                    {"risk_policy_json": runtime_policy, "updated_at": datetime.now(tz=UTC)},
                )
                position_lookup = await self._refresh_position_lookup(credentials["account_address"])
                open_order_lookup = await self._refresh_open_order_lookup(credentials["account_address"])
                cycle_runtime_state = self._reconcile_runtime_state(
                    runtime_state=cycle_runtime_state,
                    position_lookup=position_lookup,
                    open_order_lookup=open_order_lookup,
                )
                runtime_policy["_runtime_state"] = {**persisted_runtime_state, **cycle_runtime_state}
                runtime = self._update_runtime(
                    runtime,
                    {"risk_policy_json": runtime_policy, "updated_at": datetime.now(tz=UTC)},
                )
                runtime_state = runtime_policy["_runtime_state"]
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
                logger.info(
                    "Runtime %s executed action %s for %s successfully",
                    runtime["id"],
                    action.get("type"),
                    action.get("symbol"),
                )
            except (PacificaClientError, ValueError) as exc:
                runtime_policy = self._risk.mark_execution(policy=runtime_policy, success=False)
                runtime_state = runtime_policy.get("_runtime_state") if isinstance(runtime_policy.get("_runtime_state"), dict) else {}
                runtime_policy["_runtime_state"] = {**runtime_state, **cycle_runtime_state}
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
                logger.error(
                    "Runtime %s failed action %s for %s: %s",
                    runtime["id"],
                    action.get("type"),
                    action.get("symbol"),
                    exc,
                )
        if not runtime_touched:
            return

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
            reference_price = float((market_lookup.get(symbol) or {}).get("mark_price") or 0)
            amount = self._resolve_order_quantity(action=action, market_lookup=market_lookup, symbol=symbol, reference_price=None)
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
                    "side": self._to_pacifica_side(side),
                    "amount": amount,
                    "reduce_only": reduce_only,
                    "slippage_percent": float(action.get("slippage_percent") or 0.5),
                }
            )
            response["execution_meta"] = {
                "symbol": symbol,
                "side": self._to_pacifica_side(side),
                "amount": amount,
                "reduce_only": reduce_only,
                "reference_price": reference_price,
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
            amount = self._resolve_order_quantity(action=action, market_lookup=market_lookup, symbol=symbol, reference_price=price)
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
                    "side": self._to_pacifica_side(side),
                    "amount": amount,
                    "price": price,
                    "tif": str(action.get("tif") or "GTC"),
                    "reduce_only": reduce_only,
                    "client_order_id": action.get("client_order_id"),
                }
            )
            response["execution_meta"] = {
                "symbol": symbol,
                "side": self._to_pacifica_side(side),
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
            reference_price = float((market_lookup.get(symbol) or {}).get("mark_price") or 0)
            amount = self._resolve_order_quantity(action=action, market_lookup=market_lookup, symbol=symbol, reference_price=None)
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
                    "side": self._to_pacifica_side(side),
                    "amount": amount,
                    "reduce_only": reduce_only,
                    "duration_in_seconds": duration_seconds,
                    "slippage_percent": float(action.get("slippage_percent") or 0.5),
                    "client_order_id": action.get("client_order_id"),
                }
            )
            response["execution_meta"] = {
                "symbol": symbol,
                "side": self._to_pacifica_side(side),
                "amount": amount,
                "reduce_only": reduce_only,
                "reference_price": reference_price,
            }
            return response

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
            reference_price = float(position.get("mark_price") or (market_lookup.get(symbol) or {}).get("mark_price") or 0)
            response = await self._pacifica.place_order(
                {"type": "create_market_order", **payload, "side": close_side, "amount": amount, "reduce_only": True}
            )
            response["execution_meta"] = {
                "symbol": symbol,
                "side": close_side,
                "amount": amount,
                "reduce_only": True,
                "reference_price": reference_price,
            }
            return response

        if action_type == "set_tpsl":
            position = position_lookup.get(symbol)
            if not isinstance(position, dict):
                raise ValueError(f"No open position available for TP/SL on {symbol}")
            amount = abs(float(position.get("amount") or 0))
            market = self._resolve_market(market_lookup, symbol)
            mark_price = float(position.get("mark_price") or market.get("mark_price") or 0)
            tick_size = float(market.get("tick_size") or 0)
            if amount <= 0 or mark_price <= 0:
                raise ValueError(f"Cannot set TP/SL without valid position price for {symbol}")
            tp_pct = float(action.get("take_profit_pct") or 0)
            sl_pct = float(action.get("stop_loss_pct") or 0)
            side = str(position.get("side") or "").lower()
            close_side = "ask" if side in {"bid", "long"} else "bid"
            if side in {"bid", "long"}:
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
            return await self._pacifica.place_order(
                {
                    "type": "set_position_tpsl",
                    **payload,
                    "side": close_side,
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

    async def _refresh_position_lookup(self, wallet_address: str) -> dict[str, dict[str, Any]]:
        positions = await self._safe_load(lambda: self._pacifica.get_positions(wallet_address), [])
        return self._build_position_lookup(positions)

    async def _refresh_open_order_lookup(self, wallet_address: str) -> dict[str, list[dict[str, Any]]]:
        open_orders = await self._safe_load(lambda: self._pacifica.get_open_orders(wallet_address), [])
        return self._build_open_order_lookup(open_orders)

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

    async def _calculate_runtime_performance(self, runtime: dict[str, Any]) -> dict[str, Any]:
        service = BotPerformanceService(pacifica_client=self._pacifica, supabase=self._supabase)
        return await service.calculate_runtime_performance(runtime)

    @staticmethod
    def _build_idempotency_key(
        *,
        runtime_id: str,
        action: dict[str, Any],
        runtime_state: dict[str, Any],
        position_lookup: dict[str, dict[str, Any]],
    ) -> str:
        action_type = str(action.get("type") or "")
        payload = json.dumps(action, sort_keys=True, default=str)
        execution_cursor = int(runtime_state.get("executions_total") or 0)
        failure_cursor = int(runtime_state.get("failures_total") or 0)
        last_executed_at = str(runtime_state.get("last_executed_at") or "")
        position_fingerprint = BotRuntimeWorker._position_fingerprint(
            action=action,
            position_lookup=position_lookup,
        )
        if action_type == "set_tpsl":
            digest_source = f"{runtime_id}:{action_type}:{position_fingerprint}:{payload}"
            digest = hashlib.sha256(digest_source.encode()).hexdigest()[:24]
            return f"idem:{runtime_id}:tpsl:{digest}"
        digest = hashlib.sha256(
            f"{runtime_id}:{execution_cursor}:{failure_cursor}:{last_executed_at}:{position_fingerprint}:{payload}".encode()
        ).hexdigest()[:24]
        return f"idem:{runtime_id}:{execution_cursor}:{failure_cursor}:{digest}"

    @staticmethod
    def _position_fingerprint(*, action: dict[str, Any], position_lookup: dict[str, dict[str, Any]]) -> str:
        action_type = str(action.get("type") or "")
        symbol = BotRuntimeWorker._normalize_symbol(action.get("symbol"))
        if not symbol:
            return "nosymbol"
        position = position_lookup.get(symbol) or {}
        amount = float(position.get("amount") or 0.0) if isinstance(position, dict) else 0.0
        side = str(position.get("side") or "") if isinstance(position, dict) else ""
        has_position = amount > 0
        if action_type == "set_tpsl":
            entry_price = float(position.get("entry_price") or 0.0) if isinstance(position, dict) else 0.0
            created_at = str(position.get("created_at") or "") if isinstance(position, dict) else ""
            updated_at = str(position.get("updated_at") or "") if isinstance(position, dict) else ""
            return f"{symbol}:tpsl:{has_position}:{side}:{amount:.8f}:{entry_price:.8f}:{created_at}:{updated_at}"
        if action_type in {"open_long", "open_short", "place_market_order", "place_limit_order", "place_twap_order"}:
            return f"{symbol}:entry:{has_position}:{side}:{amount:.8f}"
        if action_type == "close_position":
            return f"{symbol}:close:{has_position}:{side}:{amount:.8f}"
        return f"{symbol}:generic:{has_position}:{side}:{amount:.8f}"

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

    def _build_open_order_lookup(self, open_orders: list[Any]) -> dict[str, list[dict[str, Any]]]:
        lookup: dict[str, list[dict[str, Any]]] = {}
        for item in open_orders:
            if not isinstance(item, dict):
                continue
            symbol = self._normalize_symbol(item.get("symbol"))
            if not symbol:
                continue
            lookup.setdefault(symbol, []).append(item)
        return lookup

    def _reconcile_runtime_state(
        self,
        *,
        runtime_state: dict[str, Any],
        position_lookup: dict[str, dict[str, Any]],
        open_order_lookup: dict[str, list[dict[str, Any]]],
    ) -> dict[str, Any]:
        next_state = dict(runtime_state)
        pending_entries = next_state.get("pending_entry_symbols")
        if not isinstance(pending_entries, dict):
            pending_entries = {}
        synced_pending: dict[str, str] = {}
        for symbol, started_at in pending_entries.items():
            position = position_lookup.get(symbol) or {}
            if abs(float(position.get("amount") or 0.0)) > 0:
                continue
            started_at_str = str(started_at)
            started_dt = self._parse_runtime_state_timestamp(started_at_str)
            if started_dt is None:
                synced_pending[symbol] = started_at_str
                continue
            age_seconds = (datetime.now(tz=UTC) - started_dt).total_seconds()
            if age_seconds < PENDING_ENTRY_TTL_SECONDS:
                synced_pending[symbol] = started_at_str
        if synced_pending:
            next_state["pending_entry_symbols"] = synced_pending
        else:
            next_state.pop("pending_entry_symbols", None)
        return next_state

    def _update_runtime_state_for_action(
        self,
        *,
        runtime_state: dict[str, Any],
        action: dict[str, Any],
        position_lookup: dict[str, dict[str, Any]],
        open_order_lookup: dict[str, list[dict[str, Any]]],
        success: bool,
    ) -> dict[str, Any]:
        next_state = dict(runtime_state)
        pending_entries = next_state.get("pending_entry_symbols")
        if not isinstance(pending_entries, dict):
            pending_entries = {}
        action_type = str(action.get("type") or "")
        symbol = self._normalize_symbol(action.get("symbol"))
        if success and symbol and action_type in {"open_long", "open_short", "place_market_order", "place_limit_order", "place_twap_order"}:
            if not self._to_bool(action.get("reduce_only"), False):
                pending_entries[symbol] = datetime.now(tz=UTC).isoformat()
        if success and symbol and action_type == "close_position":
            pending_entries.pop(symbol, None)
        if pending_entries:
            next_state["pending_entry_symbols"] = pending_entries
        else:
            next_state.pop("pending_entry_symbols", None)
        return self._reconcile_runtime_state(
            runtime_state=next_state,
            position_lookup=position_lookup,
            open_order_lookup=open_order_lookup,
        )

    @staticmethod
    def _parse_runtime_state_timestamp(value: str) -> datetime | None:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None

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
