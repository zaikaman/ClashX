from __future__ import annotations

import asyncio
import contextlib
import hashlib
import inspect
import json
import logging
import uuid
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from decimal import ROUND_DOWN, ROUND_UP, Decimal
from time import monotonic
from time import perf_counter
from typing import Any

from src.core.performance_metrics import get_performance_metrics_store
from src.core.settings import get_settings
from src.services.bot_risk_service import BotRiskService
from src.services.bot_runtime_engine import BotRuntimeEngine
from src.services.bot_performance_service import BotPerformanceService
from src.services.event_broadcaster import broadcaster
from src.services.indicator_context_service import IndicatorContextService, TIMEFRAME_TO_MS, extract_candle_requests
from src.services.pacifica_auth_service import PacificaAuthService
from src.services.pacifica_client import PacificaClient, PacificaClientError, get_pacifica_client
from src.services.pacifica_market_data_service import get_pacifica_market_data_service
from src.services.rules_engine import RulesEngine
from src.services.supabase_rest import SupabaseRestClient, SupabaseRestError
from src.services.worker_coordination_service import WorkerCoordinationService


logger = logging.getLogger(__name__)
PENDING_ENTRY_TTL_SECONDS = 120
RUNTIME_HEARTBEAT_INTERVAL_SECONDS = 120
SKIP_EVENT_DEDUP_SECONDS = 300
SKIP_EVENT_CACHE_TTL_SECONDS = SKIP_EVENT_DEDUP_SECONDS
IDLE_RUNTIME_DISCOVERY_SECONDS = 5.0
RUNTIME_SET_REFRESH_SECONDS = 15.0
MIN_WORKER_SLEEP_SECONDS = 1.0
RUNTIME_COORDINATION_LEASE_SECONDS = 300
VOLATILE_RUNTIME_STATE_KEYS = frozenset(
    {
        "wallet_synced_at",
        "performance_synced_at",
        "last_rule_evaluated_at",
        "evaluation_slots",
        "observed_open_orders",
        "observed_positions",
    }
)
ENTRY_ACTION_TYPES = {
    "open_long",
    "open_short",
    "place_market_order",
    "place_limit_order",
    "place_twap_order",
}


class BotRuntimeWorker:
    def __init__(self, poll_interval_seconds: float = 4.0) -> None:
        self._settings = get_settings()
        self.poll_interval_seconds = poll_interval_seconds
        self._task: asyncio.Task | None = None
        self._running = False
        self._engine = BotRuntimeEngine()
        self._rules = RulesEngine()
        self._risk = BotRiskService()
        self._auth = PacificaAuthService()
        self._pacifica = get_pacifica_client()
        self._indicator_context = IndicatorContextService(self._pacifica)
        self._market_data = get_pacifica_market_data_service()
        self._supabase = SupabaseRestClient()
        self._coordination = WorkerCoordinationService(self._supabase)
        self._metrics = get_performance_metrics_store()
        self._held_leases: dict[str, float] = {}
        self._recent_skip_events: dict[str, float] = {}
        self._runtime_state_cache: dict[str, dict[str, Any]] = {}
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
        self._release_held_leases()
        logger.info("Stopped bot runtime worker")

    async def run_forever(self) -> None:
        while self._running:
            iteration_started = perf_counter()
            next_sleep_seconds = IDLE_RUNTIME_DISCOVERY_SECONDS
            try:
                runtimes = await asyncio.to_thread(lambda: list(self._engine.get_active_runtimes(None)))
                runtimes = [self._merge_cached_runtime_state(runtime) for runtime in runtimes]
                bot_lookup = await self._load_runtime_bot_lookup(runtimes)
                runtime_specs: list[dict[str, Any]] = []
                shared_candle_requests: list[dict[str, Any]] = []
                need_shared_markets = False
                for runtime in runtimes:
                    bot = bot_lookup.get(str(runtime["bot_definition_id"]))
                    runtime_policy = self._risk.normalize_policy(
                        runtime.get("risk_policy_json") if isinstance(runtime.get("risk_policy_json"), dict) else {}
                    )
                    runtime_state = runtime_policy.get("_runtime_state") if isinstance(runtime_policy.get("_runtime_state"), dict) else {}
                    rules_json = bot["rules_json"] if isinstance(bot, dict) and isinstance(bot.get("rules_json"), dict) else {}
                    evaluation_due = self._should_evaluate_rules(rules_json=rules_json, runtime_state=runtime_state)
                    wallet_due = evaluation_due or self._should_refresh_wallet(runtime_state=runtime_state)
                    if evaluation_due:
                        shared_candle_requests.extend(extract_candle_requests(rules_json))
                        need_shared_markets = True
                    if wallet_due:
                        need_shared_markets = True
                    runtime_specs.append(
                        {
                            "runtime": runtime,
                            "bot": bot,
                            "evaluation_due": evaluation_due,
                            "wallet_due": wallet_due,
                            "next_due_seconds": self._next_runtime_check_seconds(
                                runtime_state=runtime_state,
                                rules_json=rules_json,
                            ),
                        }
                    )
                market_lookup: dict[str, dict[str, Any]] = {}
                price_lookup: dict[str, float] = {}
                candle_lookup: dict[str, dict[str, list[dict[str, Any]]]] = {}
                if need_shared_markets:
                    markets = await self._market_data.get_markets()
                    market_lookup = self._build_market_lookup(markets)
                    price_lookup = {
                        str(item.get("symbol") or ""): float(item.get("mark_price") or 0.0)
                        for item in markets
                        if str(item.get("symbol") or "")
                    }
                if shared_candle_requests:
                    candle_lookup = await self._market_data.load_candle_lookup(shared_candle_requests)
                for runtime_spec in runtime_specs:
                    runtime = runtime_spec["runtime"]
                    lease_key = f"bot-runtime:{runtime['id']}"
                    if not self._claim_local_runtime_lease(
                        lease_key,
                        ttl_seconds=RUNTIME_COORDINATION_LEASE_SECONDS,
                    ):
                        continue
                    updated_runtime = await self._process_runtime(
                        None,
                        runtime,
                        bot=runtime_spec.get("bot"),
                        bot_loaded=True,
                        market_lookup=market_lookup,
                        candle_lookup=candle_lookup,
                        price_lookup=price_lookup,
                        wallet_due=bool(runtime_spec.get("wallet_due")),
                        evaluation_due=bool(runtime_spec.get("evaluation_due")),
                    )
                    if not isinstance(updated_runtime, dict):
                        updated_runtime = runtime
                    updated_bot = runtime_spec.get("bot")
                    updated_rules_json = (
                        updated_bot["rules_json"]
                        if isinstance(updated_bot, dict) and isinstance(updated_bot.get("rules_json"), dict)
                        else {}
                    )
                    updated_policy = self._risk.normalize_policy(
                        updated_runtime.get("risk_policy_json")
                        if isinstance(updated_runtime.get("risk_policy_json"), dict)
                        else {}
                    )
                    updated_runtime_state = (
                        updated_policy.get("_runtime_state")
                        if isinstance(updated_policy.get("_runtime_state"), dict)
                        else {}
                    )
                    if str(updated_runtime.get("status") or "") == "active":
                        runtime_spec["next_due_seconds"] = self._next_runtime_check_seconds(
                            runtime_state=updated_runtime_state,
                            rules_json=updated_rules_json,
                        )
                    else:
                        runtime_spec["next_due_seconds"] = RUNTIME_SET_REFRESH_SECONDS
                if runtime_specs:
                    next_sleep_seconds = min(
                        RUNTIME_SET_REFRESH_SECONDS,
                        max(
                            MIN_WORKER_SLEEP_SECONDS,
                            min(float(spec.get("next_due_seconds") or 0.0) for spec in runtime_specs),
                        ),
                    )
                self.last_iteration_at = datetime.now(tz=UTC).isoformat()
                self.last_error = None
            except SupabaseRestError as exc:
                self.last_error = str(exc)
                if exc.is_retryable:
                    logger.warning("Bot runtime worker iteration deferred because Supabase is temporarily unavailable: %s", exc)
                else:
                    logger.exception("Bot runtime worker iteration failed")
            except Exception as exc:
                self.last_error = str(exc)
                logger.exception("Bot runtime worker iteration failed")
            finally:
                self._metrics.record("worker:bot_runtime:iteration", (perf_counter() - iteration_started) * 1000.0)
            await asyncio.sleep(max(MIN_WORKER_SLEEP_SECONDS, next_sleep_seconds))

    async def _process_runtime(
        self,
        db: Any,
        runtime: dict[str, Any],
        *,
        bot: dict[str, Any] | None = None,
        bot_loaded: bool = False,
        market_lookup: dict[str, dict[str, Any]] | None = None,
        candle_lookup: dict[str, dict[str, list[dict[str, Any]]]] | None = None,
        price_lookup: dict[str, float] | None = None,
        wallet_due: bool = True,
        evaluation_due: bool = True,
    ) -> dict[str, Any]:
        del db
        now = datetime.now(tz=UTC)
        if not bot_loaded:
            bot = bot or await asyncio.to_thread(
                self._supabase.maybe_one,
                "bot_definitions",
                columns="id,rules_json",
                filters={"id": runtime["bot_definition_id"]},
                cache_ttl_seconds=10,
            )
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
            return runtime

        rules_json = bot["rules_json"] if isinstance(bot.get("rules_json"), dict) else {}
        runtime_policy = self._risk.normalize_policy(runtime.get("risk_policy_json") if isinstance(runtime.get("risk_policy_json"), dict) else {})
        runtime_state = runtime_policy.get("_runtime_state") if isinstance(runtime_policy.get("_runtime_state"), dict) else {}
        if not wallet_due and not evaluation_due:
            return self._maybe_refresh_runtime_heartbeat(runtime, now=now)

        resolved_price_lookup = dict(price_lookup or {})
        positions: list[dict[str, Any]] = []
        open_orders: list[dict[str, Any]] = []
        if wallet_due:
            positions, open_orders = await asyncio.gather(
                self._safe_load(
                    lambda: self._pacifica.get_positions(runtime["wallet_address"], price_lookup=resolved_price_lookup),
                    [],
                ),
                self._safe_load(lambda: self._pacifica.get_open_orders(runtime["wallet_address"]), []),
            )
        position_lookup = self._build_position_lookup(positions)
        open_order_lookup = self._build_open_order_lookup(open_orders)
        runtime_state = {
            **runtime_state,
            "wallet_synced_at": now.isoformat(),
            "observed_open_orders": sum(len(items) for items in open_order_lookup.values()),
            "observed_positions": sum(
                1
                for item in position_lookup.values()
                if abs(float(item.get("amount") or 0.0)) > 0
            ),
        }
        if self._should_refresh_performance(runtime_state=runtime_state):
            history_loader = getattr(self._pacifica, "get_position_history", None)
            manual_close_history = (
                await self._safe_load(
                    lambda: history_loader(runtime["wallet_address"], limit=200, offset=0),
                    [],
                )
                if callable(history_loader)
                else []
            )
            performance = await self._load_runtime_performance(
                runtime,
                market_lookup=market_lookup or {},
                position_lookup=position_lookup,
                manual_close_history=manual_close_history,
            )
            runtime_policy = self._risk.sync_performance(
                policy=runtime_policy,
                pnl_total=float(performance.get("pnl_total") or 0.0),
                pnl_realized=float(performance.get("pnl_realized") or 0.0),
                pnl_unrealized=float(performance.get("pnl_unrealized") or 0.0),
            )
            runtime_state = runtime_policy.get("_runtime_state") if isinstance(runtime_policy.get("_runtime_state"), dict) else {}
            runtime_state["performance_synced_at"] = now.isoformat()
        runtime_state = self._reconcile_runtime_state(
            runtime_state=runtime_state,
            position_lookup=position_lookup,
            open_order_lookup=open_order_lookup,
        )
        runtime_policy["_runtime_state"] = runtime_state
        runtime = self._persist_runtime_policy(runtime, runtime_policy, now=now)
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
            return runtime

        if not evaluation_due:
            return self._maybe_refresh_runtime_heartbeat(runtime, now=now)

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
            return runtime

        if self._should_suspend_entry_evaluation(
            rules_json=rules_json,
            runtime_policy=runtime_policy,
            runtime_state=runtime_state,
        ):
            logger.debug(
                "Runtime %s skipped rule evaluation because entry capacity is full and no exit actions are declared",
                runtime["id"],
            )
            return self._maybe_refresh_runtime_heartbeat(runtime, now=now)

        resolved_market_lookup = market_lookup or self._build_market_lookup(await self._load_markets())
        resolved_candle_lookup = candle_lookup or await self._indicator_context.load_candle_lookup(rules_json)
        cycle_runtime_state = self._mark_rule_evaluation(
            runtime_state=dict(runtime_state),
            rules_json=rules_json,
            now=now,
        )
        runtime_policy["_runtime_state"] = cycle_runtime_state
        runtime = self._persist_runtime_policy(runtime, runtime_policy, now=now)
        evaluation = self._rules.evaluate(
            rules_json=rules_json,
            context={
                "runtime": {"id": runtime["id"], "state": cycle_runtime_state},
                "market_lookup": resolved_market_lookup,
                "candle_lookup": resolved_candle_lookup,
                "position_lookup": position_lookup,
            },
        )
        if not evaluation.get("triggered"):
            return self._maybe_refresh_runtime_heartbeat(runtime, now=now)

        actions = evaluation.get("actions") or []
        actions = self._prune_triggered_actions(
            actions=actions,
            runtime_policy=runtime_policy,
            runtime_state=cycle_runtime_state,
        )
        if not actions:
            return self._maybe_refresh_runtime_heartbeat(runtime, now=now)
        logger.debug(
            "Runtime %s triggered for bot %s on wallet %s with %d action(s)",
            runtime["id"],
            bot["id"],
            runtime["wallet_address"],
            len(actions),
        )

        runtime_touched = False
        coordination = self._coordination if getattr(self._coordination, "_supabase", None) is self._supabase else WorkerCoordinationService(self._supabase)
        batch_result = await self._maybe_execute_batch_actions(
            runtime=runtime,
            runtime_policy=runtime_policy,
            cycle_runtime_state=cycle_runtime_state,
            actions=actions,
            credentials=credentials,
            market_lookup=resolved_market_lookup,
            position_lookup=position_lookup,
            open_order_lookup=open_order_lookup,
            coordination=coordination,
            price_lookup=resolved_price_lookup,
        )
        if batch_result is not None:
            runtime_touched = batch_result
            return self._maybe_refresh_runtime_heartbeat(runtime, now=now)
        for action_index, raw_action in enumerate(actions):
            action = self._apply_runtime_sizing_policy(
                action=raw_action,
                runtime_policy=runtime_policy,
                route_actions=actions,
                action_index=action_index,
            )
            issues = self._risk.assess_action(
                policy=runtime_policy,
                action=action,
                runtime_state=cycle_runtime_state,
                position_lookup=position_lookup,
                open_order_lookup=open_order_lookup,
                market_lookup=resolved_market_lookup,
            )
            if issues:
                skipped_key = self._build_idempotency_key(
                    runtime_id=runtime["id"],
                    action=action,
                    runtime_state=runtime_state,
                    position_lookup=position_lookup,
                )
                skip_result = {"issues": issues}
                if await self._should_record_skip_event_async(
                    runtime_id=runtime["id"],
                    decision_summary=skipped_key,
                    request_payload=action,
                    result_payload=skip_result,
                ):
                    event = self._engine.append_execution_event(
                        None,
                        runtime=runtime,
                        event_type="action.skipped",
                        decision_summary=skipped_key,
                        request_payload=action,
                        result_payload=skip_result,
                        status="skipped",
                    )
                    await broadcaster.publish(
                        channel=f"user:{runtime['user_id']}",
                        event="bot.execution.skipped",
                        payload=self._serialize_event_payload(event),
                    )
                    self._remember_skip_event(runtime_id=runtime["id"], decision_summary=skipped_key)
                    logger.debug(
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
                    runtime=runtime,
                    runtime_state=cycle_runtime_state,
                    action=action,
                    credentials=credentials,
                    market_lookup=resolved_market_lookup,
                    position_lookup=position_lookup,
                    open_order_lookup=open_order_lookup,
                )
                execution_meta = response.get("execution_meta") if isinstance(response.get("execution_meta"), dict) else {}
                action_for_state = {**action, "_execution_meta": execution_meta}
                if "take_profit_client_order_id" in execution_meta:
                    action_for_state["_take_profit_client_order_id"] = execution_meta.get("take_profit_client_order_id")
                if "stop_loss_client_order_id" in execution_meta:
                    action_for_state["_stop_loss_client_order_id"] = execution_meta.get("stop_loss_client_order_id")
                runtime_policy = self._risk.mark_execution(policy=runtime_policy, success=True)
                persisted_runtime_state = (
                    runtime_policy.get("_runtime_state") if isinstance(runtime_policy.get("_runtime_state"), dict) else {}
                )
                cycle_runtime_state = self._update_runtime_state_for_action(
                    runtime_state=cycle_runtime_state,
                    action=action_for_state,
                    position_lookup=position_lookup,
                    open_order_lookup=open_order_lookup,
                    success=True,
                )
                runtime_policy["_runtime_state"] = {**persisted_runtime_state, **cycle_runtime_state}
                position_lookup = await self._refresh_position_lookup(
                    credentials["account_address"],
                    price_lookup=resolved_price_lookup,
                )
                open_order_lookup = await self._refresh_open_order_lookup(credentials["account_address"])
                cycle_runtime_state = self._reconcile_runtime_state(
                    runtime_state=cycle_runtime_state,
                    position_lookup=position_lookup,
                    open_order_lookup=open_order_lookup,
                )
                runtime_policy["_runtime_state"] = {**persisted_runtime_state, **cycle_runtime_state}
                runtime = self._persist_runtime_policy(runtime, runtime_policy)
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
                runtime = self._persist_runtime_policy(runtime, runtime_policy)
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
        return self._maybe_refresh_runtime_heartbeat(runtime, now=now)

    async def _maybe_execute_batch_actions(
        self,
        *,
        runtime: dict[str, Any],
        runtime_policy: dict[str, Any],
        cycle_runtime_state: dict[str, Any],
        actions: list[dict[str, Any]],
        credentials: dict[str, str],
        market_lookup: dict[str, dict[str, Any]],
        position_lookup: dict[str, dict[str, Any]],
        open_order_lookup: dict[str, list[dict[str, Any]]],
        coordination: WorkerCoordinationService,
        price_lookup: dict[str, float],
    ) -> bool | None:
        batchable_types = {"place_limit_order", "cancel_order"}
        if len(actions) < 2 or any(str(action.get("type") or "") not in batchable_types for action in actions):
            return None

        for action_index, raw_action in enumerate(actions):
            action = self._apply_runtime_sizing_policy(
                action=raw_action,
                runtime_policy=runtime_policy,
                route_actions=actions,
                action_index=action_index,
            )
            issues = self._risk.assess_action(
                policy=runtime_policy,
                action=action,
                runtime_state=cycle_runtime_state,
                position_lookup=position_lookup,
                open_order_lookup=open_order_lookup,
                market_lookup=market_lookup,
            )
            if issues:
                return None

        batch_items: list[dict[str, Any]] = []
        for action_index, raw_action in enumerate(actions):
            action = self._apply_runtime_sizing_policy(
                action=raw_action,
                runtime_policy=runtime_policy,
                route_actions=actions,
                action_index=action_index,
            )
            idempotency_key = self._build_idempotency_key(
                runtime_id=runtime["id"],
                action=action,
                runtime_state=cycle_runtime_state,
                position_lookup=position_lookup,
            )
            if not coordination.try_claim_action(runtime_id=runtime["id"], idempotency_key=idempotency_key):
                continue
            payload, execution_meta = await self._build_batch_order_request(
                runtime=runtime,
                action=action,
                credentials=credentials,
                market_lookup=market_lookup,
                open_order_lookup=open_order_lookup,
            )
            batch_items.append(
                {
                    "action": action,
                    "idempotency_key": idempotency_key,
                    "payload": payload,
                    "execution_meta": execution_meta,
                }
            )

        if not batch_items:
            return False

        try:
            if len(batch_items) == 1:
                responses = [await self._pacifica.place_order(batch_items[0]["payload"])]
            else:
                responses = await self._pacifica.place_batch_orders([item["payload"] for item in batch_items])
        except (PacificaClientError, ValueError) as exc:
            for item in batch_items:
                runtime_policy = self._risk.mark_execution(policy=runtime_policy, success=False)
                runtime_state = runtime_policy.get("_runtime_state") if isinstance(runtime_policy.get("_runtime_state"), dict) else {}
                runtime_policy["_runtime_state"] = {**runtime_state, **cycle_runtime_state}
            runtime = self._persist_runtime_policy(runtime, runtime_policy)
            for item in batch_items:
                event = self._engine.append_execution_event(
                    None,
                    runtime=runtime,
                    event_type="action.failed",
                    decision_summary=item["idempotency_key"],
                    request_payload=item["action"],
                    result_payload={},
                    status="error",
                    error_reason=str(exc),
                )
                await broadcaster.publish(
                    channel=f"user:{runtime['user_id']}",
                    event="bot.execution.failed",
                    payload=self._serialize_event_payload(event),
                )
            return True

        for item, response in zip(batch_items, responses, strict=False):
            action = item["action"]
            action_type = str(action.get("type") or "")
            execution_meta = dict(item["execution_meta"])
            if action_type == "place_limit_order":
                response_payload = response.get("payload") if isinstance(response.get("payload"), dict) else {}
                execution_meta["client_order_id"] = str(
                    response_payload.get("client_order_id") or execution_meta.get("client_order_id") or ""
                ).strip()
            response["execution_meta"] = execution_meta
            action_for_state = {**action, "_execution_meta": execution_meta}
            runtime_policy = self._risk.mark_execution(policy=runtime_policy, success=True)
            persisted_runtime_state = (
                runtime_policy.get("_runtime_state") if isinstance(runtime_policy.get("_runtime_state"), dict) else {}
            )
            cycle_runtime_state = self._update_runtime_state_for_action(
                runtime_state=cycle_runtime_state,
                action=action_for_state,
                position_lookup=position_lookup,
                open_order_lookup=open_order_lookup,
                success=True,
            )
            runtime_policy["_runtime_state"] = {**persisted_runtime_state, **cycle_runtime_state}
            event = self._engine.append_execution_event(
                None,
                runtime=runtime,
                event_type="action.executed",
                decision_summary=item["idempotency_key"],
                request_payload=action,
                result_payload=response,
                status="success",
            )
            await broadcaster.publish(
                channel=f"user:{runtime['user_id']}",
                event="bot.execution.success",
                payload=self._serialize_event_payload(event),
            )

        position_lookup = await self._refresh_position_lookup(
            credentials["account_address"],
            price_lookup=price_lookup,
        )
        open_order_lookup = await self._refresh_open_order_lookup(credentials["account_address"])
        persisted_runtime_state = (
            runtime_policy.get("_runtime_state") if isinstance(runtime_policy.get("_runtime_state"), dict) else {}
        )
        cycle_runtime_state = self._reconcile_runtime_state(
            runtime_state=cycle_runtime_state,
            position_lookup=position_lookup,
            open_order_lookup=open_order_lookup,
        )
        runtime_policy["_runtime_state"] = {**persisted_runtime_state, **cycle_runtime_state}
        runtime = self._persist_runtime_policy(runtime, runtime_policy)
        return True

    async def _execute_action(
        self,
        *,
        runtime: dict[str, Any] | None = None,
        runtime_state: dict[str, Any] | None = None,
        action: dict[str, Any],
        credentials: dict[str, str],
        market_lookup: dict[str, dict[str, Any]],
        position_lookup: dict[str, dict[str, Any]],
        open_order_lookup: dict[str, list[dict[str, Any]]] | None = None,
    ) -> dict[str, Any]:
        action_type = str(action.get("type") or "")
        symbol = self._normalize_symbol(action.get("symbol"))
        runtime_state = runtime_state if isinstance(runtime_state, dict) else {}
        runtime_id = str(runtime.get("id")) if isinstance(runtime, dict) else "runtime"
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
            self._validate_market_leverage(market_lookup=market_lookup, symbol=symbol, leverage=leverage)
            reduce_only = self._to_bool(action.get("reduce_only"), False)
            reference_price = float((market_lookup.get(symbol) or {}).get("mark_price") or 0)
            amount = self._resolve_order_quantity(action=action, market_lookup=market_lookup, symbol=symbol, reference_price=None)
            client_order_id = None if reduce_only else self._build_entry_client_order_id(runtime_id=runtime_id, symbol=symbol)
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
                    "client_order_id": client_order_id,
                }
            )
            response_payload = response.get("payload") if isinstance(response.get("payload"), dict) else {}
            normalized_client_order_id = str(response_payload.get("client_order_id") or client_order_id or "").strip()
            response["execution_meta"] = {
                "symbol": symbol,
                "side": self._to_pacifica_side(side),
                "amount": amount,
                "reduce_only": reduce_only,
                "reference_price": reference_price,
                "client_order_id": normalized_client_order_id,
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
            amount = self._resolve_order_quantity(action=action, market_lookup=market_lookup, symbol=symbol, reference_price=price)
            client_order_id = str(action.get("client_order_id") or "").strip() or (
                None if reduce_only else self._build_entry_client_order_id(runtime_id=runtime_id, symbol=symbol)
            )
            limit_order_fields = self._build_limit_order_price_fields(
                symbol=symbol,
                side=side,
                price=price,
                market_lookup=market_lookup,
            )
            normalized_price = float(limit_order_fields.get("price") or price)
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
                    "tif": str(action.get("tif") or "GTC"),
                    "reduce_only": reduce_only,
                    "client_order_id": client_order_id,
                    "price": normalized_price,
                }
            )
            response_payload = response.get("payload") if isinstance(response.get("payload"), dict) else {}
            normalized_client_order_id = str(response_payload.get("client_order_id") or client_order_id or "").strip()
            response["execution_meta"] = {
                "symbol": symbol,
                "side": self._to_pacifica_side(side),
                "amount": amount,
                "reduce_only": reduce_only,
                "reference_price": normalized_price,
                "client_order_id": normalized_client_order_id,
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
            reference_price = float((market_lookup.get(symbol) or {}).get("mark_price") or 0)
            amount = self._resolve_order_quantity(action=action, market_lookup=market_lookup, symbol=symbol, reference_price=None)
            client_order_id = str(action.get("client_order_id") or "").strip() or (
                None if reduce_only else self._build_entry_client_order_id(runtime_id=runtime_id, symbol=symbol)
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
                    "side": self._to_pacifica_side(side),
                    "amount": amount,
                    "reduce_only": reduce_only,
                    "duration_in_seconds": duration_seconds,
                    "slippage_percent": float(action.get("slippage_percent") or 0.5),
                    "client_order_id": client_order_id,
                }
            )
            response_payload = response.get("payload") if isinstance(response.get("payload"), dict) else {}
            normalized_client_order_id = str(response_payload.get("client_order_id") or client_order_id or "").strip()
            response["execution_meta"] = {
                "symbol": symbol,
                "side": self._to_pacifica_side(side),
                "amount": amount,
                "reduce_only": reduce_only,
                "reference_price": reference_price,
                "client_order_id": normalized_client_order_id,
            }
            return response

        if action_type == "close_position":
            if not symbol:
                raise ValueError("Close position requires a symbol")
            managed_position = self._maybe_get_managed_position(runtime_state=runtime_state, symbol=symbol) or {}
            position = position_lookup.get(symbol)
            if not isinstance(position, dict):
                raise ValueError(f"No open position to close for {symbol}")
            amount = self._resolve_position_amount(
                managed_position=managed_position,
                wallet_position=position,
            )
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
            managed_position = self._maybe_get_managed_position(runtime_state=runtime_state, symbol=symbol) or {}
            position = position_lookup.get(symbol)
            if not isinstance(position, dict):
                raise ValueError(f"No open position available for TP/SL on {symbol}")
            amount = self._resolve_position_amount(
                managed_position=managed_position,
                wallet_position=position,
            )
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
            take_profit_client_order_id, stop_loss_client_order_id = self._build_tpsl_client_order_ids(
                runtime_id=runtime_id,
                symbol=symbol,
                managed_position=managed_position,
            )
            response = await self._pacifica.place_order(
                {
                    "type": "set_position_tpsl",
                    **payload,
                    "side": close_side,
                    "take_profit": {
                        "stop_price": take_profit_price,
                        "amount": amount,
                        "client_order_id": take_profit_client_order_id,
                    },
                    "stop_loss": {
                        "stop_price": stop_loss_price,
                        "amount": amount,
                        "client_order_id": stop_loss_client_order_id,
                    },
                }
            )
            response_payload = response.get("payload") if isinstance(response.get("payload"), dict) else {}
            take_profit_payload = response_payload.get("take_profit") if isinstance(response_payload.get("take_profit"), dict) else {}
            stop_loss_payload = response_payload.get("stop_loss") if isinstance(response_payload.get("stop_loss"), dict) else {}
            response["execution_meta"] = {
                "symbol": symbol,
                "side": close_side,
                "amount": amount,
                "take_profit_client_order_id": str(
                    take_profit_payload.get("client_order_id") or take_profit_client_order_id
                ).strip(),
                "stop_loss_client_order_id": str(
                    stop_loss_payload.get("client_order_id") or stop_loss_client_order_id
                ).strip(),
            }
            return response

        if action_type == "update_leverage":
            if not symbol:
                raise ValueError("Leverage updates require a symbol")
            leverage = max(1, int(float(action.get("leverage") or 1)))
            self._validate_market_leverage(market_lookup=market_lookup, symbol=symbol, leverage=leverage)
            return await self._pacifica.place_order({"type": "update_leverage", **payload, "leverage": leverage})

        if action_type == "cancel_order":
            if not symbol:
                raise ValueError("Cancel order requires a symbol")
            return await self._pacifica.place_order(
                {
                    "type": "cancel_order",
                    **payload,
                    **self._build_cancel_order_request_fields(
                        action=action,
                        market_lookup=market_lookup,
                        open_order_lookup=open_order_lookup,
                    ),
                }
            )

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

    async def _build_batch_order_request(
        self,
        *,
        runtime: dict[str, Any],
        action: dict[str, Any],
        credentials: dict[str, str],
        market_lookup: dict[str, dict[str, Any]],
        open_order_lookup: dict[str, list[dict[str, Any]]] | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        action_type = str(action.get("type") or "")
        symbol = self._normalize_symbol(action.get("symbol"))
        payload: dict[str, Any] = {
            "account": credentials["account_address"],
            "agent_wallet": credentials["agent_wallet_address"],
            "__agent_private_key": credentials["agent_private_key"],
        }
        if symbol:
            payload["symbol"] = symbol

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
            amount = self._resolve_order_quantity(
                action=action,
                market_lookup=market_lookup,
                symbol=symbol,
                reference_price=price,
            )
            client_order_id = str(action.get("client_order_id") or "").strip() or (
                None if reduce_only else self._build_entry_client_order_id(runtime_id=str(runtime.get("id") or "runtime"), symbol=symbol)
            )
            limit_order_fields = self._build_limit_order_price_fields(
                symbol=symbol,
                side=side,
                price=price,
                market_lookup=market_lookup,
            )
            normalized_price = float(limit_order_fields.get("price") or price)
            if not reduce_only:
                await self._ensure_leverage(
                    wallet_address=credentials["account_address"],
                    credentials=credentials,
                    symbol=symbol,
                    leverage=leverage,
                )
            return (
                {
                    "type": "create_order",
                    **payload,
                    "side": self._to_pacifica_side(side),
                    "amount": amount,
                    "tif": str(action.get("tif") or "GTC"),
                    "reduce_only": reduce_only,
                    "client_order_id": client_order_id,
                    "price": normalized_price,
                },
                {
                    "symbol": symbol,
                    "side": self._to_pacifica_side(side),
                    "amount": amount,
                    "reduce_only": reduce_only,
                    "reference_price": normalized_price,
                    "client_order_id": client_order_id,
                },
            )

        if action_type == "cancel_order":
            if not symbol:
                raise ValueError("Cancel order requires a symbol")
            return (
                {
                    "type": "cancel_order",
                    **payload,
                    **self._build_cancel_order_request_fields(
                        action=action,
                        market_lookup=market_lookup,
                        open_order_lookup=open_order_lookup,
                    ),
                },
                {},
            )

        raise ValueError(f"Unsupported batch action type: {action_type}")

    async def _refresh_position_lookup(
        self,
        wallet_address: str,
        *,
        price_lookup: dict[str, float] | None = None,
    ) -> dict[str, dict[str, Any]]:
        positions = await self._safe_load(
            lambda: self._pacifica.get_positions(wallet_address, price_lookup=price_lookup),
            [],
        )
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

    async def _calculate_runtime_performance(
        self,
        runtime: dict[str, Any],
        *,
        market_lookup: dict[str, dict[str, Any]],
        position_lookup: dict[str, dict[str, Any]],
        manual_close_history: list[dict[str, Any]],
    ) -> dict[str, Any]:
        service = BotPerformanceService(pacifica_client=self._pacifica, supabase=self._supabase)
        return await service.calculate_runtime_performance_with_context(
            runtime,
            market_lookup=market_lookup,
            live_position_lookup=position_lookup,
            manual_close_history=manual_close_history,
        )

    async def _load_runtime_performance(
        self,
        runtime: dict[str, Any],
        *,
        market_lookup: dict[str, dict[str, Any]],
        position_lookup: dict[str, dict[str, Any]],
        manual_close_history: list[dict[str, Any]],
    ) -> dict[str, Any]:
        parameters = inspect.signature(self._calculate_runtime_performance).parameters
        if "market_lookup" in parameters:
            return await self._calculate_runtime_performance(
                runtime,
                market_lookup=market_lookup,
                position_lookup=position_lookup,
                manual_close_history=manual_close_history,
            )
        return await self._calculate_runtime_performance(runtime)  # type: ignore[misc]

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
        symbol = BotRuntimeWorker._normalize_symbol(action.get("symbol"))
        entry_retry_generation = BotRuntimeWorker._entry_retry_generation(
            runtime_state=runtime_state,
            symbol=symbol,
        )
        if action_type == "set_tpsl":
            digest_source = f"{runtime_id}:{action_type}:{position_fingerprint}:{payload}"
            digest = hashlib.sha256(digest_source.encode()).hexdigest()[:24]
            return f"idem:{runtime_id}:tpsl:{digest}"
        if action_type in ENTRY_ACTION_TYPES:
            digest = hashlib.sha256(
                (
                    f"{runtime_id}:{execution_cursor}:{failure_cursor}:{last_executed_at}:"
                    f"{entry_retry_generation}:{position_fingerprint}:{payload}"
                ).encode()
            ).hexdigest()[:24]
            return f"idem:{runtime_id}:{execution_cursor}:{failure_cursor}:{entry_retry_generation}:{digest}"
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
        updated = self._supabase.update("bot_runtimes", serialized_updates, filters={"id": runtime["id"]})[0]
        return self._merge_cached_runtime_state(updated)

    def _maybe_refresh_runtime_heartbeat(
        self,
        runtime: dict[str, Any],
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        if str(runtime.get("status") or "") != "active":
            return runtime
        resolved_now = now or datetime.now(tz=UTC)
        last_updated = self._parse_runtime_state_timestamp(str(runtime.get("updated_at") or ""))
        if last_updated is not None and (resolved_now - last_updated).total_seconds() < RUNTIME_HEARTBEAT_INTERVAL_SECONDS:
            return runtime
        return self._update_runtime(runtime, {"updated_at": resolved_now})

    def _merge_cached_runtime_state(self, runtime: dict[str, Any]) -> dict[str, Any]:
        next_runtime = dict(runtime)
        runtime_id = str(next_runtime.get("id") or "").strip()
        if not runtime_id:
            return next_runtime
        cached_state = self._runtime_state_cache.get(runtime_id)
        if not isinstance(cached_state, dict) or not cached_state:
            return next_runtime
        runtime_policy = self._risk.normalize_policy(
            next_runtime.get("risk_policy_json") if isinstance(next_runtime.get("risk_policy_json"), dict) else {}
        )
        persisted_state = self._extract_runtime_state(runtime_policy)
        runtime_policy["_runtime_state"] = {**persisted_state, **deepcopy(cached_state)}
        next_runtime["risk_policy_json"] = runtime_policy
        return next_runtime

    @staticmethod
    def _with_runtime_policy(runtime: dict[str, Any], runtime_policy: dict[str, Any]) -> dict[str, Any]:
        next_runtime = dict(runtime)
        next_runtime["risk_policy_json"] = deepcopy(runtime_policy)
        return next_runtime

    def _storage_ready_runtime_policy(self, runtime_policy: dict[str, Any]) -> dict[str, Any]:
        normalized_policy = self._risk.normalize_policy(runtime_policy)
        runtime_state = self._extract_runtime_state(normalized_policy)
        stored_state = {
            key: deepcopy(value)
            for key, value in runtime_state.items()
            if key not in VOLATILE_RUNTIME_STATE_KEYS
        }
        next_policy = {key: deepcopy(value) for key, value in normalized_policy.items() if key != "_runtime_state"}
        next_policy["_runtime_state"] = stored_state
        return next_policy

    @staticmethod
    def _extract_runtime_state(runtime_policy: dict[str, Any]) -> dict[str, Any]:
        runtime_state = runtime_policy.get("_runtime_state")
        if not isinstance(runtime_state, dict):
            return {}
        return deepcopy(runtime_state)

    async def _load_runtime_bot_lookup(self, runtimes: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        definition_ids = sorted(
            {
                str(runtime.get("bot_definition_id") or "").strip()
                for runtime in runtimes
                if str(runtime.get("bot_definition_id") or "").strip()
            }
        )
        if not definition_ids:
            return {}
        rows = await asyncio.to_thread(
            self._supabase.select,
            "bot_definitions",
            columns="id,rules_json",
            filters={"id": ("in", definition_ids)},
        )
        return {
            str(row["id"]): row
            for row in rows
            if isinstance(row, dict) and str(row.get("id") or "").strip()
        }

    def _claim_local_runtime_lease(self, lease_key: str, *, ttl_seconds: int) -> bool:
        if self._lease_refresh_not_due(lease_key):
            return True
        claimed = self._coordination.try_claim_lease(lease_key, ttl_seconds=ttl_seconds)
        if not claimed:
            self._held_leases.pop(lease_key, None)
            return False
        self._held_leases[lease_key] = monotonic() + max(1.0, ttl_seconds * 0.85)
        return True

    def _lease_refresh_not_due(self, lease_key: str) -> bool:
        refresh_at = self._held_leases.get(lease_key)
        return refresh_at is not None and monotonic() < refresh_at

    def _release_held_leases(self) -> None:
        for lease_key in list(self._held_leases):
            self._coordination.release_lease(lease_key)
        self._held_leases.clear()

    def _should_refresh_wallet(self, *, runtime_state: dict[str, Any]) -> bool:
        last_sync_at = self._parse_runtime_state_timestamp(str(runtime_state.get("wallet_synced_at") or ""))
        if last_sync_at is None:
            return True
        elapsed = (datetime.now(tz=UTC) - last_sync_at).total_seconds()
        return elapsed >= self._wallet_poll_interval_seconds(runtime_state=runtime_state)

    def _wallet_poll_interval_seconds(self, *, runtime_state: dict[str, Any]) -> int:
        pending_entries = runtime_state.get("pending_entry_symbols")
        pending_count = len(pending_entries) if isinstance(pending_entries, dict) else 0
        observed_open_orders = int(runtime_state.get("observed_open_orders") or 0)
        recent_activity = self._recent_runtime_activity(runtime_state=runtime_state)
        observed_positions = int(runtime_state.get("observed_positions") or 0)
        if pending_count > 0 or observed_open_orders > 0 or recent_activity:
            return self._settings.pacifica_active_wallet_poll_seconds
        if observed_positions > 0:
            return self._settings.pacifica_warm_wallet_poll_seconds
        return self._settings.pacifica_idle_wallet_poll_seconds

    def _should_refresh_performance(self, *, runtime_state: dict[str, Any]) -> bool:
        last_sync_at = self._parse_runtime_state_timestamp(str(runtime_state.get("performance_synced_at") or ""))
        if last_sync_at is None:
            return True
        elapsed = (datetime.now(tz=UTC) - last_sync_at).total_seconds()
        if elapsed >= self._settings.pacifica_performance_refresh_seconds:
            return True
        return self._recent_runtime_activity(runtime_state=runtime_state)

    def _should_evaluate_rules(self, *, rules_json: dict[str, Any], runtime_state: dict[str, Any]) -> bool:
        current_slots = self._evaluation_slots(rules_json=rules_json)
        previous_slots = runtime_state.get("evaluation_slots")
        if not isinstance(previous_slots, dict):
            return True
        return any(previous_slots.get(key) != value for key, value in current_slots.items())

    def _mark_rule_evaluation(
        self,
        *,
        runtime_state: dict[str, Any],
        rules_json: dict[str, Any],
        now: datetime,
    ) -> dict[str, Any]:
        next_state = dict(runtime_state)
        next_state["evaluation_slots"] = self._evaluation_slots(rules_json=rules_json)
        next_state["last_rule_evaluated_at"] = now.isoformat()
        return next_state

    def _evaluation_slots(self, *, rules_json: dict[str, Any]) -> dict[str, int]:
        requests = extract_candle_requests(rules_json)
        if not requests:
            return {
                "fast": int(
                    datetime.now(tz=UTC).timestamp() // self._settings.pacifica_fast_evaluation_seconds
                )
            }
        now_ms = int(datetime.now(tz=UTC).timestamp() * 1_000)
        slots: dict[str, int] = {}
        for timeframe in sorted({str(item.get("timeframe") or "") for item in requests}):
            timeframe_ms = TIMEFRAME_TO_MS.get(timeframe)
            if timeframe_ms is None:
                continue
            slots[timeframe] = now_ms // timeframe_ms
        return slots or {
            "fast": int(
                datetime.now(tz=UTC).timestamp() // self._settings.pacifica_fast_evaluation_seconds
            )
        }

    def _recent_runtime_activity(self, *, runtime_state: dict[str, Any]) -> bool:
        last_executed_at = self._parse_runtime_state_timestamp(str(runtime_state.get("last_executed_at") or ""))
        if last_executed_at is None:
            return False
        return (
            datetime.now(tz=UTC) - last_executed_at
        ).total_seconds() < self._settings.pacifica_recent_activity_window_seconds

    def _next_runtime_check_seconds(
        self,
        *,
        runtime_state: dict[str, Any],
        rules_json: dict[str, Any],
    ) -> float:
        return min(
            self._seconds_until_rule_evaluation(rules_json=rules_json),
            self._seconds_until_wallet_refresh(runtime_state=runtime_state),
        )

    def _seconds_until_wallet_refresh(self, *, runtime_state: dict[str, Any]) -> float:
        last_sync_at = self._parse_runtime_state_timestamp(str(runtime_state.get("wallet_synced_at") or ""))
        if last_sync_at is None:
            return 0.0
        interval_seconds = float(self._wallet_poll_interval_seconds(runtime_state=runtime_state))
        due_at = last_sync_at + timedelta(seconds=interval_seconds)
        return max(0.0, (due_at - datetime.now(tz=UTC)).total_seconds())

    def _seconds_until_rule_evaluation(self, *, rules_json: dict[str, Any]) -> float:
        requests = extract_candle_requests(rules_json)
        if not requests:
            interval_seconds = float(self._settings.pacifica_fast_evaluation_seconds)
            now_seconds = datetime.now(tz=UTC).timestamp()
            next_due_seconds = (int(now_seconds // interval_seconds) + 1) * interval_seconds
            return max(0.0, next_due_seconds - now_seconds)

        now_ms = int(datetime.now(tz=UTC).timestamp() * 1_000)
        next_due_ms: int | None = None
        for timeframe in {str(item.get("timeframe") or "") for item in requests}:
            timeframe_ms = TIMEFRAME_TO_MS.get(timeframe)
            if timeframe_ms is None:
                continue
            candidate_due_ms = ((now_ms // timeframe_ms) + 1) * timeframe_ms
            if next_due_ms is None or candidate_due_ms < next_due_ms:
                next_due_ms = candidate_due_ms
        if next_due_ms is None:
            interval_seconds = float(self._settings.pacifica_fast_evaluation_seconds)
            now_seconds = datetime.now(tz=UTC).timestamp()
            next_due_seconds = (int(now_seconds // interval_seconds) + 1) * interval_seconds
            return max(0.0, next_due_seconds - now_seconds)
        return max(0.0, (next_due_ms - now_ms) / 1_000)

    def _persist_runtime_policy(
        self,
        runtime: dict[str, Any],
        runtime_policy: dict[str, Any],
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        resolved_now = now or datetime.now(tz=UTC)
        runtime_id = str(runtime.get("id") or "").strip()
        if runtime_id:
            self._runtime_state_cache[runtime_id] = self._extract_runtime_state(runtime_policy)

        stored_policy = self._storage_ready_runtime_policy(runtime_policy)
        current_policy = self._storage_ready_runtime_policy(
            runtime.get("risk_policy_json") if isinstance(runtime.get("risk_policy_json"), dict) else {}
        )
        if current_policy == stored_policy:
            return self._with_runtime_policy(runtime, runtime_policy)

        updated_runtime = self._update_runtime(
            runtime,
            {"risk_policy_json": stored_policy, "updated_at": resolved_now},
        )
        return self._with_runtime_policy(updated_runtime, runtime_policy)

    async def _should_record_skip_event_async(
        self,
        *,
        runtime_id: str,
        decision_summary: str,
        request_payload: dict[str, Any],
        result_payload: dict[str, Any],
    ) -> bool:
        if self._skip_event_recently_recorded(runtime_id=runtime_id, decision_summary=decision_summary):
            return False
        latest_events = await asyncio.to_thread(
            self._supabase.select,
            "bot_execution_events",
            filters={"runtime_id": runtime_id},
            order="created_at.desc",
            limit=12,
        )
        should_record = self._should_record_skip_event(
            runtime_id=runtime_id,
            decision_summary=decision_summary,
            request_payload=request_payload,
            result_payload=result_payload,
            latest_events=latest_events,
        )
        if not should_record:
            self._remember_skip_event(runtime_id=runtime_id, decision_summary=decision_summary)
        return should_record

    def _should_record_skip_event(
        self,
        *,
        runtime_id: str,
        decision_summary: str,
        request_payload: dict[str, Any],
        result_payload: dict[str, Any],
        latest_events: list[dict[str, Any]] | None = None,
    ) -> bool:
        resolved_latest_events = latest_events
        if resolved_latest_events is None:
            resolved_latest_events = self._supabase.select(
                "bot_execution_events",
                filters={"runtime_id": runtime_id},
                order="created_at.desc",
                limit=12,
            )
        if not resolved_latest_events:
            return True
        cutoff = datetime.now(tz=UTC) - timedelta(seconds=SKIP_EVENT_DEDUP_SECONDS)
        for event in resolved_latest_events:
            created_at = self._parse_runtime_state_timestamp(str(event.get("created_at") or ""))
            if created_at is None or created_at < cutoff:
                continue
            if (
                event.get("event_type") == "action.skipped"
                and event.get("status") == "skipped"
                and event.get("decision_summary") == decision_summary
                and event.get("request_payload") == request_payload
                and event.get("result_payload") == result_payload
            ):
                return False
        return True

    def _skip_event_recently_recorded(self, *, runtime_id: str, decision_summary: str) -> bool:
        cache_key = self._skip_event_cache_key(runtime_id=runtime_id, decision_summary=decision_summary)
        expires_at = self._recent_skip_events.get(cache_key)
        if expires_at is None:
            return False
        if monotonic() >= expires_at:
            self._recent_skip_events.pop(cache_key, None)
            return False
        return True

    def _remember_skip_event(self, *, runtime_id: str, decision_summary: str) -> None:
        self._recent_skip_events[
            self._skip_event_cache_key(runtime_id=runtime_id, decision_summary=decision_summary)
        ] = monotonic() + SKIP_EVENT_CACHE_TTL_SECONDS

    @staticmethod
    def _skip_event_cache_key(*, runtime_id: str, decision_summary: str) -> str:
        digest = hashlib.sha256(f"{runtime_id}:{decision_summary}".encode()).hexdigest()[:24]
        return f"skip:{runtime_id}:{digest}"

    def _should_suspend_entry_evaluation(
        self,
        *,
        rules_json: dict[str, Any],
        runtime_policy: dict[str, Any],
        runtime_state: dict[str, Any],
    ) -> bool:
        max_open_positions = max(1, int(runtime_policy.get("max_open_positions") or 1))
        reserved_symbols = self._reserved_runtime_symbols(runtime_state=runtime_state)
        if len(reserved_symbols) < max_open_positions:
            return False

        declared_actions = self._rules.declared_actions(rules_json=rules_json)
        if not declared_actions:
            return False

        has_entry_actions = False
        for action in declared_actions:
            if self._is_entry_action(action):
                has_entry_actions = True
                continue
            if self._action_targets_reserved_symbol(action=action, reserved_symbols=reserved_symbols):
                return False
        return has_entry_actions

    def _prune_triggered_actions(
        self,
        *,
        actions: list[dict[str, Any]],
        runtime_policy: dict[str, Any],
        runtime_state: dict[str, Any],
    ) -> list[dict[str, Any]]:
        max_open_positions = max(1, int(runtime_policy.get("max_open_positions") or 1))
        reserved_symbols = self._reserved_runtime_symbols(runtime_state=runtime_state)
        filtered_actions: list[dict[str, Any]] = []
        for action in actions:
            if not isinstance(action, dict):
                continue
            symbol = self._normalize_symbol(action.get("symbol"))
            if self._is_entry_action(action):
                if not symbol or symbol in reserved_symbols or len(reserved_symbols) >= max_open_positions:
                    continue
                reserved_symbols.add(symbol)
                filtered_actions.append(action)
                continue
            if self._is_position_management_action(action):
                if not symbol or symbol not in reserved_symbols:
                    continue
            filtered_actions.append(action)
        return filtered_actions

    @staticmethod
    def _reserved_runtime_symbols(*, runtime_state: dict[str, Any]) -> set[str]:
        managed_positions = runtime_state.get("managed_positions")
        if not isinstance(managed_positions, dict):
            managed_positions = {}
        pending_entries = runtime_state.get("pending_entry_symbols")
        if not isinstance(pending_entries, dict):
            pending_entries = {}

        reserved_symbols = {
            str(item.get("symbol") or symbol).strip().upper()
            for symbol, item in managed_positions.items()
            if isinstance(item, dict) and abs(float(item.get("amount") or 0.0)) > 0
        }
        reserved_symbols.update(str(symbol).strip().upper() for symbol in pending_entries if str(symbol).strip())
        return reserved_symbols

    @staticmethod
    def _is_position_management_action(action: dict[str, Any]) -> bool:
        action_type = str(action.get("type") or "")
        if action_type in {"set_tpsl", "close_position"}:
            return True
        return action_type in ENTRY_ACTION_TYPES and BotRuntimeWorker._to_bool(action.get("reduce_only"), False)

    def _action_targets_reserved_symbol(self, *, action: dict[str, Any], reserved_symbols: set[str]) -> bool:
        if not self._is_position_management_action(action):
            return False
        symbol = self._normalize_symbol(action.get("symbol"))
        if not symbol or symbol == "__BOT_MARKET_UNIVERSE__":
            return True
        return symbol in reserved_symbols

    @staticmethod
    def _is_entry_action(action: dict[str, Any]) -> bool:
        action_type = str(action.get("type") or "")
        if action_type not in ENTRY_ACTION_TYPES:
            return False
        return not BotRuntimeWorker._to_bool(action.get("reduce_only"), False)

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

    async def _load_markets(self) -> list[dict[str, Any]]:
        if isinstance(self._pacifica, PacificaClient):
            return await self._market_data.get_markets()
        return await self._pacifica.get_markets()

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
        del open_order_lookup
        next_state = dict(runtime_state)
        pending_entries = next_state.get("pending_entry_symbols")
        if not isinstance(pending_entries, dict):
            pending_entries = {}
        entry_retry_generations = next_state.get("entry_retry_generations")
        if not isinstance(entry_retry_generations, dict):
            entry_retry_generations = {}
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
                continue
            self._bump_entry_retry_generation(entry_retry_generations, symbol)
        if synced_pending:
            next_state["pending_entry_symbols"] = synced_pending
        else:
            next_state.pop("pending_entry_symbols", None)
        managed_positions = next_state.get("managed_positions")
        if not isinstance(managed_positions, dict):
            managed_positions = {}
        reconciled_positions: dict[str, dict[str, Any]] = {}
        for symbol, managed_position in managed_positions.items():
            if not isinstance(managed_position, dict):
                continue
            wallet_position = position_lookup.get(symbol) or {}
            wallet_amount = abs(float(wallet_position.get("amount") or 0.0))
            managed_amount = abs(float(managed_position.get("amount") or 0.0))
            if managed_amount <= 0:
                continue
            if wallet_amount <= 0:
                if symbol in synced_pending:
                    reconciled_positions[symbol] = dict(managed_position)
                else:
                    self._bump_entry_retry_generation(entry_retry_generations, symbol)
                continue
            side = str(wallet_position.get("side") or managed_position.get("side") or "").lower()
            reconciled_positions[symbol] = {
                **managed_position,
                "amount": self._resolve_position_amount(
                    managed_position=managed_position,
                    wallet_position=wallet_position,
                ),
                "side": side,
                "mark_price": wallet_position.get("mark_price"),
                "entry_price": managed_position.get("entry_price") or wallet_position.get("entry_price"),
                "updated_at": datetime.now(tz=UTC).isoformat(),
            }
        if reconciled_positions:
            next_state["managed_positions"] = reconciled_positions
        else:
            next_state.pop("managed_positions", None)
        if entry_retry_generations:
            next_state["entry_retry_generations"] = entry_retry_generations
        else:
            next_state.pop("entry_retry_generations", None)
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
                managed_positions = next_state.get("managed_positions")
                if not isinstance(managed_positions, dict):
                    managed_positions = {}
                amount = float(((action.get("_execution_meta") or {}).get("amount")) or 0.0)
                side = str(((action.get("_execution_meta") or {}).get("side")) or "").lower()
                entry_client_order_id = str(((action.get("_execution_meta") or {}).get("client_order_id")) or "").strip()
                if amount > 0 and entry_client_order_id:
                    managed_positions[symbol] = {
                        "symbol": symbol,
                        "amount": amount,
                        "side": side,
                        "entry_client_order_id": entry_client_order_id,
                        "entry_price": ((action.get("_execution_meta") or {}).get("reference_price")) or 0.0,
                        "opened_at": datetime.now(tz=UTC).isoformat(),
                        "updated_at": datetime.now(tz=UTC).isoformat(),
                    }
                    next_state["managed_positions"] = managed_positions
        if success and symbol and action_type == "close_position":
            pending_entries.pop(symbol, None)
            managed_positions = next_state.get("managed_positions")
            if isinstance(managed_positions, dict):
                managed_positions.pop(symbol, None)
                if managed_positions:
                    next_state["managed_positions"] = managed_positions
                else:
                    next_state.pop("managed_positions", None)
        if success and symbol and action_type == "set_tpsl":
            managed_positions = next_state.get("managed_positions")
            if not isinstance(managed_positions, dict):
                managed_positions = {}
            managed_position = managed_positions.get(symbol)
            if isinstance(managed_position, dict):
                managed_position = dict(managed_position)
                managed_position["take_profit_client_order_id"] = str(action.get("_take_profit_client_order_id") or "").strip()
                managed_position["stop_loss_client_order_id"] = str(action.get("_stop_loss_client_order_id") or "").strip()
                managed_position["tpsl_set_at"] = datetime.now(tz=UTC).isoformat()
                managed_position["updated_at"] = datetime.now(tz=UTC).isoformat()
                managed_positions[symbol] = managed_position
                next_state["managed_positions"] = managed_positions
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
    def _get_managed_position(*, runtime_state: dict[str, Any], symbol: str) -> dict[str, Any]:
        managed_positions = runtime_state.get("managed_positions")
        if not isinstance(managed_positions, dict):
            raise ValueError(f"No bot-managed position available for {symbol}")
        managed_position = managed_positions.get(symbol)
        if not isinstance(managed_position, dict):
            raise ValueError(f"No bot-managed position available for {symbol}")
        return managed_position

    @staticmethod
    def _maybe_get_managed_position(*, runtime_state: dict[str, Any], symbol: str) -> dict[str, Any] | None:
        managed_positions = runtime_state.get("managed_positions")
        if not isinstance(managed_positions, dict):
            return None
        managed_position = managed_positions.get(symbol)
        if not isinstance(managed_position, dict):
            return None
        return managed_position

    @staticmethod
    def _resolve_position_amount(*, managed_position: dict[str, Any], wallet_position: dict[str, Any]) -> float:
        managed_amount = abs(float(managed_position.get("amount") or 0.0)) if isinstance(managed_position, dict) else 0.0
        wallet_amount = abs(float(wallet_position.get("amount") or 0.0)) if isinstance(wallet_position, dict) else 0.0
        if managed_amount > 0 and wallet_amount > 0:
            return min(managed_amount, wallet_amount)
        if managed_amount > 0:
            return managed_amount
        return wallet_amount

    @staticmethod
    def _entry_retry_generation(*, runtime_state: dict[str, Any], symbol: str) -> int:
        if not symbol:
            return 0
        entry_retry_generations = runtime_state.get("entry_retry_generations")
        if not isinstance(entry_retry_generations, dict):
            return 0
        return int(entry_retry_generations.get(symbol) or 0)

    @staticmethod
    def _bump_entry_retry_generation(entry_retry_generations: dict[str, Any], symbol: str) -> None:
        normalized_symbol = BotRuntimeWorker._normalize_symbol(symbol)
        if not normalized_symbol:
            return
        entry_retry_generations[normalized_symbol] = int(entry_retry_generations.get(normalized_symbol) or 0) + 1

    @staticmethod
    def _build_entry_client_order_id(*, runtime_id: str, symbol: str) -> str:
        digest = hashlib.sha256(f"{runtime_id}:{symbol}:{uuid.uuid4().hex}".encode()).hexdigest()[:12]
        return f"bot-{runtime_id.replace('-', '')[:10]}-{symbol.lower()}-en-{digest}"

    @staticmethod
    def _build_tpsl_client_order_ids(*, runtime_id: str, symbol: str, managed_position: dict[str, Any]) -> tuple[str, str]:
        entry_client_order_id = str(managed_position.get("entry_client_order_id") or "").strip()
        base = entry_client_order_id or f"bot-{runtime_id.replace('-', '')[:10]}-{symbol.lower()}-px"
        digest = hashlib.sha256(f"{runtime_id}:{symbol}:{base}".encode()).hexdigest()[:8]
        return (
            f"{base[:32]}-tp-{digest}",
            f"{base[:32]}-sl-{digest}",
        )

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
        leverage = 1 if self._to_bool(action.get("reduce_only"), False) else max(1, int(float(action.get("leverage") or 1)))
        return self._normalize_order_quantity(
            (size_usd * leverage) / resolved_price,
            lot_size=float(market.get("lot_size") or 0),
            symbol=symbol,
        )

    def _apply_runtime_sizing_policy(
        self,
        *,
        action: dict[str, Any],
        runtime_policy: dict[str, Any],
        route_actions: list[dict[str, Any]],
        action_index: int,
    ) -> dict[str, Any]:
        action_type = str(action.get("type") or "")
        if action_type not in ENTRY_ACTION_TYPES or self._to_bool(action.get("reduce_only"), False):
            return dict(action)

        normalized_policy = self._risk.normalize_policy(runtime_policy)
        sizing_mode = str(normalized_policy.get("sizing_mode") or "fixed_usd")
        leverage = max(1, int(float(normalized_policy.get("max_leverage") or 1)))
        resolved_action = dict(action)
        resolved_action["leverage"] = leverage

        if sizing_mode == "fixed_usd":
            resolved_action.pop("quantity", None)
            resolved_action["size_usd"] = float(normalized_policy.get("fixed_usd_amount") or 0.0)
            resolved_action["_sizing_mode"] = "fixed_usd"
            return resolved_action

        if sizing_mode != "risk_adjusted":
            return resolved_action

        symbol = self._normalize_symbol(action.get("symbol"))
        stop_loss_pct = self._resolve_route_stop_loss_pct(
            symbol=symbol,
            route_actions=route_actions,
            action_index=action_index,
        )
        if stop_loss_pct is None or stop_loss_pct <= 0:
            raise ValueError(
                f"Risk-adjusted sizing requires a downstream Set TP/SL block with stop loss > 0 for {symbol}."
            )

        risk_per_trade_pct = float(normalized_policy.get("risk_per_trade_pct") or 0.0)
        allocated_capital_usd = float(normalized_policy.get("allocated_capital_usd") or 0.0)
        risk_budget_usd = allocated_capital_usd * (risk_per_trade_pct / 100.0)
        stop_fraction = stop_loss_pct / 100.0
        if stop_fraction <= 0:
            raise ValueError(f"Risk-adjusted sizing requires stop loss > 0 for {symbol}.")

        size_usd = risk_budget_usd / (stop_fraction * leverage)
        resolved_action.pop("quantity", None)
        resolved_action["size_usd"] = size_usd
        resolved_action["_sizing_mode"] = "risk_adjusted"
        resolved_action["_stop_loss_pct"] = stop_loss_pct
        resolved_action["_risk_budget_usd"] = round(risk_budget_usd, 8)
        return resolved_action

    def _resolve_route_stop_loss_pct(
        self,
        *,
        symbol: str,
        route_actions: list[dict[str, Any]],
        action_index: int,
    ) -> float | None:
        for next_action in route_actions[action_index + 1:]:
            action_type = str(next_action.get("type") or "")
            if action_type in ENTRY_ACTION_TYPES:
                return None
            if action_type != "set_tpsl":
                continue
            action_symbol = self._normalize_symbol(next_action.get("symbol"))
            if action_symbol != symbol:
                continue
            stop_loss_pct = float(next_action.get("stop_loss_pct") or 0.0)
            if stop_loss_pct > 0:
                return stop_loss_pct
        return None

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

    def _build_limit_order_price_fields(
        self,
        *,
        symbol: str,
        side: str,
        price: float,
        market_lookup: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        market = self._resolve_market(market_lookup, symbol)
        tick_size = float(market.get("tick_size") or 0)
        rounding = ROUND_DOWN if side == "long" else ROUND_UP
        normalized_price = self._normalize_price_to_tick(
            price,
            tick_size=tick_size,
            rounding=rounding,
        )
        fields: dict[str, Any] = {"price": normalized_price}
        tick_level = self._price_to_tick_level(normalized_price, tick_size=tick_size)
        if tick_level is not None:
            fields["tick_level"] = tick_level
        return fields

    def _build_cancel_order_request_fields(
        self,
        *,
        action: dict[str, Any],
        market_lookup: dict[str, dict[str, Any]],
        open_order_lookup: dict[str, list[dict[str, Any]]] | None = None,
    ) -> dict[str, Any]:
        identifier = self._extract_order_identifier(action)
        symbol = self._normalize_symbol(action.get("symbol"))
        matched_order = self._find_open_order(
            symbol=symbol,
            identifier=identifier,
            open_order_lookup=open_order_lookup,
        )
        if not isinstance(matched_order, dict):
            return identifier
        request_fields = dict(identifier)
        side = str(matched_order.get("side") or "").strip()
        if side:
            request_fields["side"] = side
        tick_level = matched_order.get("tick_level")
        if tick_level in (None, ""):
            market = market_lookup.get(symbol) if symbol else None
            tick_level = self._price_to_tick_level(
                matched_order.get("price"),
                tick_size=float(market.get("tick_size") or 0) if isinstance(market, dict) else 0.0,
            )
        else:
            tick_level = self._to_int(tick_level)
        if tick_level is not None:
            request_fields["tick_level"] = tick_level
        return request_fields

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

    def _find_open_order(
        self,
        *,
        symbol: str,
        identifier: dict[str, Any],
        open_order_lookup: dict[str, list[dict[str, Any]]] | None,
    ) -> dict[str, Any] | None:
        if not symbol or not isinstance(open_order_lookup, dict):
            return None
        orders = open_order_lookup.get(symbol)
        if not isinstance(orders, list):
            return None
        if "order_id" in identifier:
            expected = str(identifier.get("order_id"))
            for order in orders:
                if str(order.get("order_id") or "").strip() == expected:
                    return order
        if "client_order_id" in identifier:
            expected = str(identifier.get("client_order_id") or "").strip()
            for order in orders:
                if str(order.get("client_order_id") or "").strip() == expected:
                    return order
        return None

    @staticmethod
    def _price_to_tick_level(price: Any, *, tick_size: float) -> int | None:
        if tick_size <= 0:
            return None
        try:
            price_decimal = Decimal(str(price))
            tick_decimal = Decimal(str(tick_size))
            if tick_decimal <= 0:
                return None
            return int((price_decimal / tick_decimal).to_integral_value(rounding=ROUND_DOWN))
        except (ArithmeticError, ValueError, TypeError):
            return None

    @staticmethod
    def _to_int(value: Any) -> int | None:
        try:
            if value in (None, ""):
                return None
            return int(float(value))
        except (TypeError, ValueError):
            return None

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
