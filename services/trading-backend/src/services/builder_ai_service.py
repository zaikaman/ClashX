from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

import httpx

from src.core.settings import get_settings
from src.services.ai_response_json import extract_first_json_object

CONDITION_OPTIONS = [
    "price_above",
    "price_below",
    "price_change_pct_above",
    "price_change_pct_below",
    "has_position",
    "position_side_is",
    "cooldown_elapsed",
    "funding_rate_above",
    "funding_rate_below",
    "volume_above",
    "volume_below",
    "rsi_above",
    "rsi_below",
    "sma_above",
    "sma_below",
    "volatility_above",
    "volatility_below",
    "bollinger_above_upper",
    "bollinger_below_lower",
    "breakout_above_recent_high",
    "breakout_below_recent_low",
    "atr_above",
    "atr_below",
    "vwap_above",
    "vwap_below",
    "higher_timeframe_sma_above",
    "higher_timeframe_sma_below",
    "ema_crosses_above",
    "ema_crosses_below",
    "macd_crosses_above_signal",
    "macd_crosses_below_signal",
    "position_pnl_above",
    "position_pnl_below",
    "position_pnl_pct_above",
    "position_pnl_pct_below",
    "position_in_profit",
    "position_in_loss",
]

ACTION_OPTIONS = [
    "open_long",
    "open_short",
    "place_market_order",
    "place_limit_order",
    "place_twap_order",
    "close_position",
    "set_tpsl",
    "update_leverage",
    "cancel_order",
    "cancel_twap_order",
    "cancel_all_orders",
]

logger = logging.getLogger(__name__)

BUILDER_AI_TOTAL_TIMEOUT_SECONDS = 300.0
BUILDER_AI_CONNECT_TIMEOUT_SECONDS = 10.0


@dataclass(frozen=True)
class _ProviderAttempt:
    name: str
    request_coro: Any
    extract_text: Any


class BuilderAiService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._http = httpx.AsyncClient(
            timeout=httpx.Timeout(
                BUILDER_AI_TOTAL_TIMEOUT_SECONDS,
                connect=BUILDER_AI_CONNECT_TIMEOUT_SECONDS,
            )
        )

    async def generate_draft(
        self,
        messages: list[dict[str, str]],
        available_markets: list[str],
        current_draft: dict[str, Any] | None,
    ) -> dict[str, Any]:
        attempts = self._build_provider_attempts(
            messages=messages,
            available_markets=available_markets,
            current_draft=current_draft,
        )
        if not attempts:
            raise RuntimeError(
                "Missing TrollLLM and OpenAI configuration. Set TROLLLLM_API_KEY, TROLLLLM_BASE_URL, and TROLLLLM_MODEL "
                "or OPENAI_API_KEY, OPENAI_BASE_URL, and OPENAI_MODEL."
            )

        errors: list[str] = []
        for attempt in attempts:
            try:
                payload = await attempt.request_coro()
                raw_text = attempt.extract_text(payload)
                parsed = self._normalize_tool_payload(self._extract_json(raw_text))
                return self._sanitize_draft(parsed, available_markets)
            except RuntimeError as exc:
                logger.warning("Builder AI provider attempt failed: %s", exc)
                errors.append(f"{attempt.name}: {exc}")
        raise RuntimeError("; ".join(errors))

    def _build_provider_attempts(
        self,
        messages: list[dict[str, str]],
        available_markets: list[str],
        current_draft: dict[str, Any] | None,
    ) -> list[_ProviderAttempt]:
        system_prompt = self._build_system_prompt(available_markets, current_draft)
        attempts: list[_ProviderAttempt] = []
        if self._has_trollllm_config():
            attempts.append(
                _ProviderAttempt(
                    name="TrollLLM",
                    request_coro=lambda: self._request_trollllm(messages, system_prompt),
                    extract_text=self._extract_openai_text,
                )
            )
        if self._has_openai_config():
            attempts.append(
                _ProviderAttempt(
                    name="OpenAI",
                    request_coro=lambda: self._request_openai(messages, system_prompt),
                    extract_text=self._extract_openai_text,
                )
            )
        return attempts

    def _has_trollllm_config(self) -> bool:
        return bool(
            self.settings.trollllm_api_key
            and self.settings.trollllm_base_url
            and self.settings.trollllm_model
        )

    def _has_openai_config(self) -> bool:
        return bool(
            self.settings.openai_api_key
            and self.settings.openai_base_url
            and self.settings.openai_model
        )

    async def _request_trollllm(
        self,
        messages: list[dict[str, str]],
        system_prompt: str,
    ) -> Any:
        try:
            return await self._request_chat_completions_compatible(
                provider_name="TrollLLM",
                base_url=self.settings.trollllm_base_url,
                api_key=self.settings.trollllm_api_key,
                model=self.settings.trollllm_model,
                messages=messages,
                system_prompt=system_prompt,
            )
        except RuntimeError as exc:
            if "non-json" not in str(exc).lower():
                raise
            logger.warning("TrollLLM chat/completions returned non-JSON; retrying with /responses endpoint.")
            return await self._request_openai_compatible(
                provider_name="TrollLLM",
                base_url=self.settings.trollllm_base_url,
                api_key=self.settings.trollllm_api_key,
                model=self.settings.trollllm_model,
                messages=messages,
                system_prompt=system_prompt,
            )

    async def _request_openai(
        self,
        messages: list[dict[str, str]],
        system_prompt: str,
    ) -> Any:
        return await self._request_openai_compatible(
            provider_name="OpenAI",
            base_url=self.settings.openai_base_url,
            api_key=self.settings.openai_api_key,
            model=self.settings.openai_model,
            messages=messages,
            system_prompt=system_prompt,
        )

    async def _request_openai_compatible(
        self,
        *,
        provider_name: str,
        base_url: str,
        api_key: str,
        model: str,
        messages: list[dict[str, str]],
        system_prompt: str,
    ) -> Any:
        try:
            response = await self._http.post(
                self._build_responses_url(base_url),
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "input": [
                        {
                            "role": "system",
                            "content": system_prompt,
                        },
                        *messages,
                    ],
                },
            )
        except httpx.TimeoutException as exc:
            raise RuntimeError(f"{provider_name} request timed out.") from exc
        except httpx.HTTPError as exc:
            raise RuntimeError(f"{provider_name} request failed: {exc}") from exc
        return self._parse_response_payload(response)

    async def _request_chat_completions_compatible(
        self,
        *,
        provider_name: str,
        base_url: str,
        api_key: str,
        model: str,
        messages: list[dict[str, str]],
        system_prompt: str,
    ) -> Any:
        try:
            response = await self._http.post(
                self._build_chat_completions_url(base_url),
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": [
                        {
                            "role": "system",
                            "content": system_prompt,
                        },
                        *messages,
                    ],
                },
            )
        except httpx.TimeoutException as exc:
            raise RuntimeError(f"{provider_name} request timed out.") from exc
        except httpx.HTTPError as exc:
            raise RuntimeError(f"{provider_name} request failed: {exc}") from exc
        return self._parse_response_payload(response)

    def _build_responses_url(self, base_url: str) -> str:
        normalized = base_url.strip().rstrip("/")
        if normalized.endswith("/responses"):
            return normalized
        if normalized.endswith("/v1"):
            return f"{normalized}/responses"
        return f"{normalized}/v1/responses"

    def _build_chat_completions_url(self, base_url: str) -> str:
        normalized = base_url.strip().rstrip("/")
        if normalized.endswith("/chat/completions"):
            return normalized
        if normalized.endswith("/v1"):
            return f"{normalized}/chat/completions"
        return f"{normalized}/v1/chat/completions"

    def _build_system_prompt(
        self,
        available_markets: list[str],
        current_draft: dict[str, Any] | None,
    ) -> str:
        current_draft_summary = json.dumps(current_draft or {}, ensure_ascii=True)
        return "\n".join(
            [
                "You are an AI trading bot planner for the ClashX builder.",
                "You must reply with one JSON object only. No markdown. No prose outside JSON.",
                "Interpret the user's latest request as either a new draft or a modification of the current draft.",
                "Keep strategies realistic and concise for a rules-based Pacifica bot.",
                f"Allowed condition types: {', '.join(CONDITION_OPTIONS)}.",
                f"Allowed action types: {', '.join(ACTION_OPTIONS)}.",
                f"Available markets right now: {', '.join(available_markets) if available_markets else 'BTC, ETH, SOL'}.",
                "Use marketSelection = \"all\" only if the user explicitly wants the bot to trade many markets.",
                "Prefer 1-4 conditions and 1-3 actions unless the user asks for more complexity.",
                "Use uppercase market symbols like BTC, ETH, SOL.",
                "Plan the draft by first extracting the user's explicit strategy intents.",
                "An intent is a trigger plus the behavior that should happen when that trigger is true.",
                "Each distinct intent should become its own route unless the user clearly wants the same action chain to happen after a shared trigger path.",
                "A route is an ordered path of conditions followed by actions.",
                "If the strategy includes alternative triggers, opposite-side entries, or multiple if/then statements, represent them as separate routes rather than one linear list.",
                "Do not merge distinct triggers into one route if that would change the meaning of the strategy.",
                "Do not omit any explicit trigger, direction, market, TP, SL, timeframe, or threshold the user asked for.",
                "A single route must not contain contradictory entry directions unless the user explicitly asked for a sequential multi-action flow.",
                "If the user gives entry risk instructions such as TP or SL percentages, attach the protection to every affected entry route with a downstream set_tpsl action.",
                "When editing an existing draft, preserve unchanged routes, markets, and risk intent unless the user asks to replace them.",
                "If the current draft includes routes or graph data, use that structure as the source of truth for the existing logic.",
                "Always include top-level conditions and actions. If you return routes, make the top-level conditions/actions match the primary route.",
                "Before you answer, silently verify that the draft fully covers every explicit user intent and that the number of routes matches the number of distinct trigger/action paths implied by the request.",
                f"Current draft context: {current_draft_summary}",
                "Return exactly this shape:",
                '{"reply":"short natural language summary","name":"string","description":"string","marketSelection":"selected|all","markets":["BTC"],"conditions":[{"type":"ema_crosses_above","symbol":"BTC","timeframe":"15m","fast_period":9,"slow_period":21}],"actions":[{"type":"open_long","symbol":"BTC","size_usd":150,"leverage":3}],"routes":[{"name":"optional-route-name","conditions":[{"type":"rsi_above","symbol":"BTC","timeframe":"15m","period":14,"value":70}],"actions":[{"type":"open_short","symbol":"BTC","size_usd":150,"leverage":3},{"type":"set_tpsl","symbol":"BTC","take_profit_pct":2,"stop_loss_pct":1}]},{"name":"optional-second-route","conditions":[{"type":"rsi_below","symbol":"BTC","timeframe":"15m","period":14,"value":30}],"actions":[{"type":"open_long","symbol":"BTC","size_usd":150,"leverage":3},{"type":"set_tpsl","symbol":"BTC","take_profit_pct":2,"stop_loss_pct":1}]}]}',
            ]
        )

    def _parse_response_payload(self, response: Any) -> Any:
        status_code = int(getattr(response, "status_code", 500) or 500)
        try:
            payload = response.json()
        except ValueError as exc:
            raw_text = str(getattr(response, "text", "") or "").strip()
            if raw_text and status_code < 400:
                try:
                    extract_first_json_object(raw_text)
                except RuntimeError:
                    pass
                else:
                    return {
                        "choices": [
                            {
                                "message": {
                                    "content": raw_text,
                                }
                            }
                        ]
                    }
            if status_code >= 400:
                reason = str(getattr(response, "reason_phrase", "") or "").strip()
                status_summary = f"AI request failed with status {status_code}"
                if reason:
                    status_summary = f"{status_summary} ({reason})"
                raise RuntimeError(f"{status_summary}.") from exc
            raise RuntimeError("AI provider returned a non-JSON response.") from exc
        if status_code >= 400:
            error = payload.get("error", {}) if isinstance(payload, dict) else {}
            detail = error.get("message") if isinstance(error, dict) else None
            raise RuntimeError(str(detail or "AI request failed."))
        return payload

    def _extract_openai_text(self, payload: Any) -> str:
        if not isinstance(payload, dict):
            return ""
        choices = payload.get("choices")
        if isinstance(choices, list):
            chunks: list[str] = []
            for choice in choices:
                if not isinstance(choice, dict):
                    continue
                message = choice.get("message")
                if not isinstance(message, dict):
                    continue
                tool_calls = message.get("tool_calls")
                if isinstance(tool_calls, list):
                    for tool_call in tool_calls:
                        if not isinstance(tool_call, dict):
                            continue
                        function = tool_call.get("function")
                        if isinstance(function, dict) and function.get("name") and function.get("arguments") is not None:
                            return json.dumps(
                                {
                                    "function": {
                                        "name": function.get("name"),
                                        "arguments": function.get("arguments"),
                                    }
                                }
                            )
                function_call = message.get("function_call")
                if isinstance(function_call, dict) and function_call.get("name") and function_call.get("arguments") is not None:
                    return json.dumps(
                        {
                            "function": {
                                "name": function_call.get("name"),
                                "arguments": function_call.get("arguments"),
                            }
                        }
                    )
                content = message.get("content")
                if isinstance(content, str) and content.strip():
                    chunks.append(content)
                    continue
                if isinstance(content, list):
                    for part in content:
                        if isinstance(part, dict) and isinstance(part.get("text"), str):
                            chunks.append(part["text"])
            if chunks:
                return "\n".join(chunks).strip()
        output_text = payload.get("output_text")
        if isinstance(output_text, str) and output_text.strip():
            return output_text
        output = payload.get("output")
        if isinstance(output, list):
            chunks: list[str] = []
            for item in output:
                if not isinstance(item, dict):
                    continue
                if item.get("type") == "function_call" and item.get("name") and item.get("arguments") is not None:
                    return json.dumps(
                        {
                            "function": {
                                "name": item.get("name"),
                                "arguments": item.get("arguments"),
                            }
                        }
                    )
                content = item.get("content")
                if not isinstance(content, list):
                    continue
                for part in content:
                    if (
                        isinstance(part, dict)
                        and part.get("type") == "function_call"
                        and part.get("name")
                        and part.get("arguments") is not None
                    ):
                        return json.dumps(
                            {
                                "function": {
                                    "name": part.get("name"),
                                    "arguments": part.get("arguments"),
                                }
                            }
                        )
                    if isinstance(part, dict) and isinstance(part.get("text"), str):
                        chunks.append(part["text"])
            if chunks:
                return "\n".join(chunks).strip()
        if self._looks_like_builder_payload(payload):
            return json.dumps(payload)
        return ""

    def _looks_like_builder_payload(self, payload: dict[str, Any]) -> bool:
        return any(
            key in payload
            for key in (
                "reply",
                "name",
                "description",
                "marketSelection",
                "markets",
                "conditions",
                "actions",
                "routes",
            )
        )

    def _extract_json(self, value: str) -> dict[str, Any]:
        return extract_first_json_object(value)

    def _normalize_tool_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        nested_function = payload.get("function")
        if isinstance(nested_function, dict) and "arguments" in nested_function:
            return self._coerce_tool_arguments(nested_function["arguments"])

        if "arguments" in payload and any(key in payload for key in ("name", "tool", "type", "call")):
            return self._coerce_tool_arguments(payload["arguments"])

        return payload

    def _coerce_tool_arguments(self, value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            return self._extract_json(value)
        raise RuntimeError("AI function-call arguments must be a JSON object")

    def _normalize_markets(self, value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        markets: list[str] = []
        for item in value:
            if isinstance(item, str):
                market = item.strip().upper()
                if market:
                    markets.append(market)
        return markets

    def _sanitize_condition_list(self, value: Any) -> list[dict[str, Any]]:
        conditions: list[dict[str, Any]] = []
        if not isinstance(value, list):
            return conditions

        for item in value:
            if not isinstance(item, dict) or item.get("type") not in CONDITION_OPTIONS:
                continue
            conditions.append(
                {
                    **item,
                    "symbol": item.get("symbol", "").strip().upper()
                    if isinstance(item.get("symbol"), str)
                    else None,
                }
            )
        return conditions

    def _sanitize_action_list(self, value: Any) -> list[dict[str, Any]]:
        actions: list[dict[str, Any]] = []
        if not isinstance(value, list):
            return actions

        for item in value:
            if not isinstance(item, dict) or item.get("type") not in ACTION_OPTIONS:
                continue
            actions.append(
                {
                    **item,
                    "symbol": item.get("symbol", "").strip().upper()
                    if isinstance(item.get("symbol"), str)
                    else None,
                }
            )
        return actions

    def _sanitize_routes(self, value: Any) -> list[dict[str, Any]]:
        routes: list[dict[str, Any]] = []
        if not isinstance(value, list):
            return routes

        for item in value:
            if not isinstance(item, dict):
                continue
            conditions = self._sanitize_condition_list(item.get("conditions"))
            actions = self._sanitize_action_list(item.get("actions"))
            if not conditions or not actions:
                continue

            route: dict[str, Any] = {
                "conditions": conditions,
                "actions": actions,
            }
            if isinstance(item.get("name"), str) and item["name"].strip():
                route["name"] = item["name"].strip()
            routes.append(route)
        return routes

    def _sanitize_draft(self, payload: dict[str, Any], available_markets: list[str]) -> dict[str, Any]:
        allowed_markets = {market.strip().upper() for market in available_markets if market.strip()}
        requested_markets = self._normalize_markets(payload.get("markets"))
        markets = [
            market for market in requested_markets if not allowed_markets or market in allowed_markets
        ]

        routes = self._sanitize_routes(payload.get("routes"))
        conditions = self._sanitize_condition_list(payload.get("conditions"))
        actions = self._sanitize_action_list(payload.get("actions"))

        if routes:
            if not conditions:
                conditions = list(routes[0]["conditions"])
            if not actions:
                actions = list(routes[0]["actions"])

        if not conditions:
            raise RuntimeError("AI draft must include at least one valid condition")
        if not actions:
            raise RuntimeError("AI draft must include at least one valid action")

        return {
            "reply": payload.get("reply", "I rebuilt the draft from your instructions."),
            "draft": {
                "name": str(payload.get("name") or "AI Strategy Draft").strip(),
                "description": str(payload.get("description") or "Generated from AI chat.").strip(),
                "marketSelection": "all" if payload.get("marketSelection") == "all" else "selected",
                "markets": markets,
                "conditions": conditions,
                "actions": actions,
                "routes": routes,
            },
        }
