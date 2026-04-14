from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
import re
from typing import Any

import anyio

from src.services.bot_risk_service import BotRiskService
from src.services.event_broadcaster import broadcaster
from src.services.pacifica_auth_service import PacificaAuthService
from src.services.pacifica_readiness_service import PacificaReadinessService
from src.services.rules_engine import RulesEngine
from src.services.supabase_rest import SupabaseRestClient

MARKET_UNIVERSE_SYMBOL = "__BOT_MARKET_UNIVERSE__"
_SYMBOL_TOKEN_RE = re.compile(r"^[A-Z0-9]+$")


class BotRuntimeEngine:
    def __init__(self) -> None:
        self._supabase = SupabaseRestClient()
        self._auth = PacificaAuthService()
        self._readiness = PacificaReadinessService()
        self._risk = BotRiskService()
        self._rules = RulesEngine()

    def deploy_runtime(
        self,
        db: Any,
        *,
        bot_id: str,
        wallet_address: str,
        user_id: str,
        risk_policy_json: dict[str, Any] | None,
    ) -> dict[str, Any]:
        del db
        bot = self._resolve_bot(bot_id=bot_id, wallet_address=wallet_address, user_id=user_id)
        runtime = self._resolve_runtime(bot_definition_id=bot["id"], wallet_address=wallet_address)
        self._require_runtime_readiness(wallet_address)

        now = datetime.now(tz=UTC).isoformat()
        normalized_policy = self._risk.normalize_policy(risk_policy_json)
        normalized_policy = self._apply_default_allowed_symbols(
            bot=bot,
            normalized_policy=normalized_policy,
            requested_policy=risk_policy_json,
        )
        self._validate_runtime_policy(bot=bot, risk_policy_json=normalized_policy)
        if runtime is None:
            runtime = self._supabase.insert(
                "bot_runtimes",
                {
                    "id": str(uuid.uuid4()),
                    "bot_definition_id": bot["id"],
                    "user_id": bot["user_id"],
                    "wallet_address": wallet_address,
                    "status": "active",
                    "mode": "live",
                    "risk_policy_json": normalized_policy,
                    "deployed_at": now,
                    "stopped_at": None,
                    "updated_at": now,
                },
            )[0]
        else:
            merged_policy = dict(runtime.get("risk_policy_json") or {})
            if isinstance(risk_policy_json, dict):
                merged_policy.update(risk_policy_json)
            normalized_merged_policy = self._risk.normalize_policy(merged_policy)
            normalized_merged_policy = self._apply_default_allowed_symbols(
                bot=bot,
                normalized_policy=normalized_merged_policy,
                requested_policy=risk_policy_json,
            )
            runtime = self._supabase.update(
                "bot_runtimes",
                {
                    "status": "active",
                    "mode": "live",
                    "risk_policy_json": normalized_merged_policy,
                    "deployed_at": runtime.get("deployed_at") or now,
                    "stopped_at": None,
                    "updated_at": now,
                },
                filters={"id": runtime["id"]},
            )[0]

        self._supabase.insert(
            "bot_execution_events",
            {
                "id": str(uuid.uuid4()),
                "runtime_id": runtime["id"],
                "event_type": "runtime.deployed",
                "decision_summary": "runtime transitioned to active",
                "request_payload": {"bot_id": bot["id"]},
                "result_payload": {"status": runtime["status"]},
                "status": "success",
                "created_at": now,
            },
        )
        self._publish_event(user_id=runtime["user_id"], event="bot.runtime.deployed", payload=self.serialize_runtime(runtime))
        return self.serialize_runtime(runtime)

    def pause_runtime(self, db: Any, *, bot_id: str, wallet_address: str, user_id: str) -> dict[str, Any]:
        del db
        runtime = self._require_runtime(bot_id=bot_id, wallet_address=wallet_address, user_id=user_id)
        if runtime["status"] == "stopped":
            raise ValueError("Stopped runtime cannot be paused")
        now = datetime.now(tz=UTC).isoformat()
        runtime = self._supabase.update("bot_runtimes", {"status": "paused", "updated_at": now}, filters={"id": runtime["id"]})[0]
        self._append_runtime_transition(runtime=runtime, event_type="runtime.paused")
        self._publish_event(user_id=runtime["user_id"], event="bot.runtime.paused", payload=self.serialize_runtime(runtime))
        return self.serialize_runtime(runtime)

    def resume_runtime(self, db: Any, *, bot_id: str, wallet_address: str, user_id: str) -> dict[str, Any]:
        del db
        runtime = self._require_runtime(bot_id=bot_id, wallet_address=wallet_address, user_id=user_id)
        if runtime["status"] == "stopped":
            raise ValueError("Stopped runtime cannot be resumed")
        if self._auth.get_trading_credentials(None, wallet_address) is None:
            raise ValueError("Authorize a delegated Pacifica agent wallet before resuming this bot.")
        now = datetime.now(tz=UTC).isoformat()
        runtime = self._supabase.update("bot_runtimes", {"status": "active", "updated_at": now}, filters={"id": runtime["id"]})[0]
        self._append_runtime_transition(runtime=runtime, event_type="runtime.resumed")
        self._publish_event(user_id=runtime["user_id"], event="bot.runtime.resumed", payload=self.serialize_runtime(runtime))
        return self.serialize_runtime(runtime)

    def stop_runtime(self, db: Any, *, bot_id: str, wallet_address: str, user_id: str) -> dict[str, Any]:
        del db
        runtime = self._require_runtime(bot_id=bot_id, wallet_address=wallet_address, user_id=user_id)
        now = datetime.now(tz=UTC).isoformat()
        runtime = self._supabase.update(
            "bot_runtimes",
            {"status": "stopped", "stopped_at": now, "updated_at": now},
            filters={"id": runtime["id"]},
        )[0]
        self._append_runtime_transition(runtime=runtime, event_type="runtime.stopped")
        self._publish_event(user_id=runtime["user_id"], event="bot.runtime.stopped", payload=self.serialize_runtime(runtime))
        return self.serialize_runtime(runtime)

    def list_runtime_events(self, db: Any, *, bot_id: str, wallet_address: str, user_id: str, limit: int) -> list[dict[str, Any]]:
        del db
        bot = self._resolve_bot(bot_id=bot_id, wallet_address=wallet_address, user_id=user_id)
        runtime = self._resolve_runtime(bot_definition_id=bot["id"], wallet_address=wallet_address)
        if runtime is None:
            return []
        rows = self._supabase.select(
            "bot_execution_events",
            columns="id,runtime_id,event_type,decision_summary,request_payload,result_payload,status,error_reason,created_at",
            filters={"runtime_id": runtime["id"]},
            order="created_at.desc",
            limit=limit,
        )
        return [self.serialize_event_summary(row) for row in rows]

    def list_runtimes_for_wallet(self, db: Any, *, wallet_address: str, user_id: str) -> list[dict[str, Any]]:
        del db, user_id
        rows = self._supabase.select(
            "bot_runtimes",
            columns="id,bot_definition_id,user_id,wallet_address,status,mode,risk_policy_json,deployed_at,stopped_at,updated_at",
            filters={"wallet_address": wallet_address},
            order="updated_at.desc",
            cache_ttl_seconds=15,
        )
        return [self.serialize_runtime(row) for row in rows]

    def get_runtime(self, db: Any, *, bot_id: str, wallet_address: str, user_id: str) -> dict[str, Any] | None:
        del db
        bot = self._resolve_bot(bot_id=bot_id, wallet_address=wallet_address, user_id=user_id)
        runtime = self._resolve_runtime(bot_definition_id=bot["id"], wallet_address=wallet_address)
        return self.serialize_runtime(runtime) if runtime is not None else None

    def get_active_runtimes(self, db: Any) -> list[dict[str, Any]]:
        del db
        return self._supabase.select(
            "bot_runtimes",
            columns="id,bot_definition_id,user_id,wallet_address,status,mode,risk_policy_json,deployed_at,stopped_at,updated_at",
            filters={"status": "active"},
        )

    def append_execution_event(
        self,
        db: Any,
        *,
        runtime: dict[str, Any],
        event_type: str,
        decision_summary: str,
        request_payload: dict[str, Any],
        result_payload: dict[str, Any],
        status: str,
        error_reason: str | None = None,
    ) -> dict[str, Any]:
        del db
        return self._supabase.insert(
            "bot_execution_events",
            {
                "id": str(uuid.uuid4()),
                "runtime_id": runtime["id"],
                "event_type": event_type,
                "decision_summary": decision_summary,
                "request_payload": request_payload,
                "result_payload": result_payload,
                "status": status,
                "error_reason": error_reason,
                "created_at": datetime.now(tz=UTC).isoformat(),
            },
        )[0]

    @staticmethod
    def serialize_runtime(runtime: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": runtime["id"],
            "bot_definition_id": runtime["bot_definition_id"],
            "user_id": runtime["user_id"],
            "wallet_address": runtime["wallet_address"],
            "status": runtime["status"],
            "mode": runtime["mode"],
            "risk_policy_json": runtime["risk_policy_json"],
            "deployed_at": runtime.get("deployed_at"),
            "stopped_at": runtime.get("stopped_at"),
            "updated_at": runtime["updated_at"],
        }

    @staticmethod
    def serialize_event(event: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": event["id"],
            "runtime_id": event["runtime_id"],
            "event_type": event["event_type"],
            "decision_summary": event["decision_summary"],
            "request_payload": event["request_payload"],
            "result_payload": event["result_payload"],
            "status": event["status"],
            "error_reason": event.get("error_reason"),
            "created_at": event["created_at"],
        }

    @classmethod
    def serialize_event_summary(cls, event: dict[str, Any]) -> dict[str, Any]:
        request_payload = event["request_payload"] if isinstance(event.get("request_payload"), dict) else {}
        result_payload = event["result_payload"] if isinstance(event.get("result_payload"), dict) else {}
        return {
            "id": event["id"],
            "runtime_id": event["runtime_id"],
            "event_type": event["event_type"],
            "decision_summary": cls._build_event_decision_summary(event, request_payload=request_payload),
            "action_type": cls._read_text(request_payload.get("type")),
            "symbol": cls._read_text(request_payload.get("symbol")),
            "leverage": cls._read_number(request_payload.get("leverage")),
            "size_usd": cls._read_number(request_payload.get("size_usd")),
            "status": event["status"],
            "error_reason": event.get("error_reason"),
            "outcome_summary": cls._build_event_outcome_summary(event, result_payload=result_payload),
            "created_at": event["created_at"],
        }

    def _require_runtime(self, *, bot_id: str, wallet_address: str, user_id: str) -> dict[str, Any]:
        bot = self._resolve_bot(bot_id=bot_id, wallet_address=wallet_address, user_id=user_id)
        runtime = self._resolve_runtime(bot_definition_id=bot["id"], wallet_address=wallet_address)
        if runtime is None:
            raise ValueError("Bot runtime not found")
        return runtime

    def _resolve_bot(self, *, bot_id: str, wallet_address: str, user_id: str) -> dict[str, Any]:
        del user_id
        bot = self._supabase.maybe_one(
            "bot_definitions",
            filters={"id": bot_id, "wallet_address": wallet_address},
            cache_ttl_seconds=15,
        )
        if bot is None:
            raise ValueError("Bot not found")
        return bot

    def _resolve_runtime(self, *, bot_definition_id: str, wallet_address: str) -> dict[str, Any] | None:
        return self._supabase.maybe_one(
            "bot_runtimes",
            filters={"bot_definition_id": bot_definition_id, "wallet_address": wallet_address},
            cache_ttl_seconds=15,
        )

    def _append_runtime_transition(self, *, runtime: dict[str, Any], event_type: str) -> None:
        self._supabase.insert(
            "bot_execution_events",
            {
                "id": str(uuid.uuid4()),
                "runtime_id": runtime["id"],
                "event_type": event_type,
                "decision_summary": f"runtime transitioned to {runtime['status']}",
                "request_payload": {},
                "result_payload": {"status": runtime["status"]},
                "status": "success",
                "created_at": datetime.now(tz=UTC).isoformat(),
            },
            returning="minimal",
        )

    def _validate_runtime_policy(self, *, bot: dict[str, Any], risk_policy_json: dict[str, Any]) -> None:
        if str(risk_policy_json.get("sizing_mode") or "fixed_usd") != "risk_adjusted":
            return
        rules_json = bot.get("rules_json") if isinstance(bot.get("rules_json"), dict) else {}
        issues = self._rules.risk_adjusted_sizing_issues(rules_json=rules_json)
        if issues:
            raise ValueError("Risk-adjusted sizing is not available for this bot: " + "; ".join(issues))

    def _apply_default_allowed_symbols(
        self,
        *,
        bot: dict[str, Any],
        normalized_policy: dict[str, Any],
        requested_policy: dict[str, Any] | None,
    ) -> dict[str, Any]:
        if self._requested_policy_includes_allowed_symbols(requested_policy):
            return normalized_policy
        derived_symbols = self._derive_allowed_symbols_from_bot(bot)
        if not derived_symbols:
            return normalized_policy
        next_policy = dict(normalized_policy)
        next_policy["allowed_symbols"] = derived_symbols
        return self._risk.normalize_policy(next_policy)

    @staticmethod
    def _requested_policy_includes_allowed_symbols(requested_policy: dict[str, Any] | None) -> bool:
        if not isinstance(requested_policy, dict):
            return False
        allowed_symbols = requested_policy.get("allowed_symbols")
        return isinstance(allowed_symbols, list) and any(str(symbol).strip() for symbol in allowed_symbols)

    @classmethod
    def _derive_allowed_symbols_from_bot(cls, bot: dict[str, Any]) -> list[str]:
        rules_json = bot.get("rules_json") if isinstance(bot.get("rules_json"), dict) else {}
        selected_symbols = rules_json.get("selected_market_symbols")
        explicit_symbols = cls._extract_rule_symbols(rules_json)
        normalized_selected = cls._normalize_symbols(selected_symbols) if isinstance(selected_symbols, list) else []
        uses_market_universe = cls._rules_use_market_universe_symbol(rules_json)

        if uses_market_universe:
            merged_symbols = cls._normalize_symbols([*explicit_symbols, *normalized_selected])
            if merged_symbols:
                return merged_symbols
        elif explicit_symbols:
            return explicit_symbols

        if normalized_selected:
            return normalized_selected

        return cls._market_scope_symbols(str(bot.get("market_scope") or ""))

    @classmethod
    def _rules_use_market_universe_symbol(cls, rules_json: dict[str, Any]) -> bool:
        for group in ("conditions", "actions"):
            rows = rules_json.get(group)
            if not isinstance(rows, list):
                continue
            for row in rows:
                if not isinstance(row, dict):
                    continue
                symbol = cls._normalize_symbol(row.get("symbol"))
                if symbol == MARKET_UNIVERSE_SYMBOL:
                    return True

        graph = rules_json.get("graph")
        if isinstance(graph, dict):
            nodes = graph.get("nodes")
            if isinstance(nodes, list):
                for node in nodes:
                    if not isinstance(node, dict):
                        continue
                    config = node.get("config")
                    if not isinstance(config, dict):
                        continue
                    symbol = cls._normalize_symbol(config.get("symbol"))
                    if symbol == MARKET_UNIVERSE_SYMBOL:
                        return True

        return False

    @classmethod
    def _extract_rule_symbols(cls, rules_json: dict[str, Any]) -> list[str]:
        symbols: list[str] = []
        seen: set[str] = set()
        for group in ("conditions", "actions"):
            rows = rules_json.get(group)
            if not isinstance(rows, list):
                continue
            for row in rows:
                if not isinstance(row, dict):
                    continue
                symbol = cls._normalize_symbol(row.get("symbol"))
                if not symbol or symbol == MARKET_UNIVERSE_SYMBOL or symbol in seen:
                    continue
                seen.add(symbol)
                symbols.append(symbol)

        graph = rules_json.get("graph")
        if isinstance(graph, dict):
            nodes = graph.get("nodes")
            if isinstance(nodes, list):
                for node in nodes:
                    if not isinstance(node, dict):
                        continue
                    config = node.get("config")
                    if not isinstance(config, dict):
                        continue
                    symbol = cls._normalize_symbol(config.get("symbol"))
                    if not symbol or symbol == MARKET_UNIVERSE_SYMBOL or symbol in seen:
                        continue
                    seen.add(symbol)
                    symbols.append(symbol)

        return symbols

    @classmethod
    def _market_scope_symbols(cls, scope: str) -> list[str]:
        normalized = scope.strip()
        if not normalized or "all pacifica" in normalized.lower():
            return []
        tail = normalized.split("/")[-1]
        candidate_symbols = cls._normalize_symbols(tail.split(","))
        return [symbol for symbol in candidate_symbols if cls._looks_like_market_symbol(symbol)]

    @staticmethod
    def _looks_like_market_symbol(symbol: str) -> bool:
        if not symbol:
            return False
        if not _SYMBOL_TOKEN_RE.match(symbol):
            return False
        return any(character.isalpha() for character in symbol)

    @classmethod
    def _normalize_symbols(cls, values: list[Any]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for value in values:
            symbol = cls._normalize_symbol(value)
            if not symbol or symbol in seen:
                continue
            seen.add(symbol)
            normalized.append(symbol)
        return normalized

    @staticmethod
    def _normalize_symbol(value: Any) -> str:
        return str(value or "").upper().replace("-PERP", "").strip()

    def _require_runtime_readiness(self, wallet_address: str) -> dict[str, Any]:
        try:
            return anyio.from_thread.run(self._readiness.require_ready, None, wallet_address)
        except RuntimeError:
            # Fall back for direct synchronous calls outside FastAPI's worker thread bridge.
            return asyncio.run(self._readiness.require_ready(None, wallet_address))

    @staticmethod
    def _publish_event(*, user_id: str, event: str, payload: dict[str, Any]) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        loop.create_task(broadcaster.publish(channel=f"user:{user_id}", event=event, payload=payload))

    @staticmethod
    def _build_event_outcome_summary(event: dict[str, Any], *, result_payload: dict[str, Any] | None = None) -> str:
        error_reason = BotRuntimeEngine._read_text(event.get("error_reason"))
        if error_reason:
            return error_reason

        event_type = BotRuntimeEngine._read_text(event.get("event_type")) or "event"
        status = BotRuntimeEngine._read_text(event.get("status")) or "pending"
        payload = result_payload if isinstance(result_payload, dict) else {}
        skip_summary = BotRuntimeEngine._build_skip_outcome_summary(payload)
        if status == "skipped" and skip_summary:
            return skip_summary

        if event_type.startswith("runtime."):
            return BotRuntimeEngine._build_runtime_outcome_summary(event_type)
        if status == "success":
            return "Action executed successfully."
        if status == "skipped":
            return "Action was skipped after runtime checks."
        if status == "error":
            return "Action failed during runtime execution."
        return "Event recorded."

    @staticmethod
    def _build_event_decision_summary(event: dict[str, Any], *, request_payload: dict[str, Any]) -> str:
        event_type = BotRuntimeEngine._read_text(event.get("event_type")) or "event"
        if event_type.startswith("runtime."):
            status = event_type.split(".", 1)[1].replace("_", " ").strip() or "updated"
            return f"Runtime transitioned to {status}."

        action_type = BotRuntimeEngine._read_text(request_payload.get("type"))
        symbol = BotRuntimeEngine._read_text(request_payload.get("symbol"))
        leverage = BotRuntimeEngine._read_number(request_payload.get("leverage"))
        size_usd = BotRuntimeEngine._read_number(request_payload.get("size_usd"))
        if action_type:
            return BotRuntimeEngine._describe_action_attempt(
                action_type=action_type,
                symbol=symbol,
                leverage=leverage,
                size_usd=size_usd,
            )

        stored_summary = BotRuntimeEngine._read_text(event.get("decision_summary"))
        return stored_summary or "Runtime recorded a decision."

    @staticmethod
    def _describe_action_attempt(
        *,
        action_type: str,
        symbol: str | None,
        leverage: float | None,
        size_usd: float | None,
    ) -> str:
        market = f" on {symbol.upper().replace('-PERP', '')}" if symbol else ""
        leverage_text = f" with {leverage:g}x leverage" if leverage is not None else ""
        size_text = f" and about ${size_usd:,.0f} notional" if size_usd is not None else ""

        if action_type == "open_long":
            return f"Runtime attempted to open a long position{market}{leverage_text}{size_text}."
        if action_type == "open_short":
            return f"Runtime attempted to open a short position{market}{leverage_text}{size_text}."
        if action_type == "set_tpsl":
            return f"Runtime attempted to place take-profit and stop-loss protection{market}."
        if action_type == "close_position":
            return f"Runtime attempted to close the managed position{market}."
        if action_type == "update_leverage":
            target = f" on {symbol.upper().replace('-PERP', '')}" if symbol else ""
            leverage_only = f" to {leverage:g}x" if leverage is not None else ""
            return f"Runtime attempted to update leverage{target}{leverage_only}."
        if action_type == "place_market_order":
            return f"Runtime attempted to place a market order{market}{leverage_text}{size_text}."
        if action_type == "place_limit_order":
            return f"Runtime attempted to place a limit order{market}{leverage_text}{size_text}."
        if action_type == "place_twap_order":
            return f"Runtime attempted to place a TWAP order{market}{leverage_text}{size_text}."
        return f"Runtime attempted to run {action_type.replace('_', ' ')}{market}."

    @staticmethod
    def _build_runtime_outcome_summary(event_type: str) -> str:
        if event_type == "runtime.active":
            return "Runtime is active and ready to evaluate new market signals."
        if event_type == "runtime.paused":
            return "Runtime is paused and will not place new trades."
        if event_type == "runtime.stopped":
            return "Runtime has been stopped and will not evaluate new actions."
        return "Runtime state updated successfully."

    @staticmethod
    def _build_skip_outcome_summary(result_payload: dict[str, Any]) -> str | None:
        issues = result_payload.get("issues")
        if not isinstance(issues, list):
            return None

        friendly_issues = [
            BotRuntimeEngine._humanize_issue(str(issue).strip())
            for issue in issues
            if BotRuntimeEngine._read_text(issue)
        ]
        if not friendly_issues:
            return None
        return " ".join(friendly_issues)

    @staticmethod
    def _humanize_issue(issue: str) -> str:
        cleaned = issue.strip()
        if not cleaned:
            return "Runtime checks blocked this action."

        if cleaned.startswith("symbol ") and cleaned.endswith(" is not in allowed_symbols policy"):
            symbol = cleaned[len("symbol ") : -len(" is not in allowed_symbols policy")].strip().upper()
            return f"{symbol} is outside this runtime's allowed market list."
        if cleaned.startswith("requested leverage ") and " exceeds max_leverage " in cleaned:
            requested, maximum = cleaned[len("requested leverage ") :].split(" exceeds max_leverage ", 1)
            return f"Requested {requested.strip()}x leverage, above the runtime cap of {maximum.strip()}x."
        if cleaned.startswith("requested leverage ") and " market max_leverage " in cleaned:
            requested_part, market_part = cleaned[len("requested leverage ") :].split(" exceeds ", 1)
            market_name, market_max = market_part.split(" market max_leverage ", 1)
            return (
                f"Requested {requested_part.strip()}x leverage, above {market_name.strip().upper()}'s market maximum "
                f"of {market_max.strip()}x."
            )
        if cleaned.startswith("requested order value ") and " exceeds max_order_size_usd " in cleaned:
            requested, maximum = cleaned[len("requested order value ") :].split(" exceeds max_order_size_usd ", 1)
            requested_amount = BotRuntimeEngine._read_number(requested)
            maximum_amount = BotRuntimeEngine._read_number(maximum)
            if requested_amount is not None and maximum_amount is not None:
                return (
                    f"Requested order size is about ${requested_amount:,.0f}, above the runtime cap of "
                    f"${maximum_amount:,.0f}."
                )
        if cleaned.startswith("bot does not manage an open position on "):
            symbol = cleaned[len("bot does not manage an open position on ") :].strip().upper()
            return f"No tracked open position exists on {symbol}, so this action cannot run."
        if cleaned.startswith("max_open_positions ") and cleaned.endswith(" reached"):
            limit = cleaned[len("max_open_positions ") : -len(" reached")].strip()
            return f"The runtime is already at its limit of {limit} open position{'s' if limit != '1' else ''}."
        if cleaned.startswith("bot already manages an open position on "):
            symbol = cleaned[len("bot already manages an open position on ") :].strip().upper()
            return f"The runtime already has an open position on {symbol}."
        if cleaned.startswith("existing bot entry order on ") and cleaned.endswith(" is still open"):
            symbol = cleaned[len("existing bot entry order on ") : -len(" is still open")].strip().upper()
            return f"An existing entry order on {symbol} is still open."
        if cleaned.startswith("pending entry on ") and cleaned.endswith(" is still syncing"):
            symbol = cleaned[len("pending entry on ") : -len(" is still syncing")].strip().upper()
            return f"A new entry on {symbol} is still syncing from Pacifica, so another order was blocked."
        if cleaned.startswith("awaiting position sync on ") and cleaned.endswith(" before TP/SL"):
            symbol = cleaned[len("awaiting position sync on ") : -len(" before TP/SL")].strip().upper()
            return f"{symbol} has not synced into the runtime yet, so TP/SL could not be placed."
        if cleaned.startswith("existing protective order on ") and cleaned.endswith(" already covers this position"):
            symbol = cleaned[len("existing protective order on ") : -len(" already covers this position")].strip().upper()
            return f"Existing protective orders already cover the current position on {symbol}."
        if cleaned.startswith("runtime drawdown "):
            return cleaned[0].upper() + cleaned[1:] + ("" if cleaned.endswith(".") else ".")
        if cleaned.startswith("cooldown active for ") and cleaned.endswith(" more seconds"):
            remaining = cleaned[len("cooldown active for ") : -len(" more seconds")].strip()
            return f"Cooldown is still active for {remaining} more seconds."
        return cleaned[0].upper() + cleaned[1:] + ("" if cleaned.endswith(".") else ".")

    @staticmethod
    def _read_text(value: Any) -> str | None:
        if not isinstance(value, str):
            return None
        cleaned = value.strip()
        return cleaned or None

    @staticmethod
    def _read_number(value: Any) -> float | None:
        if isinstance(value, bool) or value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value)
            except ValueError:
                return None
        return None
