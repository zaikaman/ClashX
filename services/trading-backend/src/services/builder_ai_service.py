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


@dataclass(frozen=True)
class _ProviderAttempt:
    name: str
    request_coro: Any
    extract_text: Any


class BuilderAiService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._http = httpx.AsyncClient(timeout=45.0)

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
                "Missing Gemini and OpenAI configuration. Set GEMINI_API_KEY, GEMINI_BASE_URL, and GEMINI_MODEL "
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
        if self._has_gemini_config():
            attempts.append(
                _ProviderAttempt(
                    name="Gemini",
                    request_coro=lambda: self._request_gemini(messages, system_prompt),
                    extract_text=self._extract_gemini_text,
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

    def _has_gemini_config(self) -> bool:
        return bool(
            self.settings.gemini_api_key
            and self.settings.gemini_base_url
            and self.settings.gemini_model
        )

    def _has_openai_config(self) -> bool:
        return bool(
            self.settings.openai_api_key
            and self.settings.openai_base_url
            and self.settings.openai_model
        )

    async def _request_gemini(
        self,
        messages: list[dict[str, str]],
        system_prompt: str,
    ) -> Any:
        response = await self._http.post(
            self._build_gemini_url(self.settings.gemini_base_url, self.settings.gemini_model),
            headers={
                "Authorization": f"Bearer {self.settings.gemini_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "systemInstruction": {
                    "parts": [
                        {
                            "text": system_prompt,
                        }
                    ]
                },
                "contents": self._build_gemini_contents(messages),
                "generationConfig": {
                    "temperature": 1,
                    "topP": 1,
                    "thinkingConfig": {
                        "includeThoughts": True,
                        "thinkingBudget": 26240,
                    },
                },
            },
        )
        return self._parse_response_payload(response)

    async def _request_openai(
        self,
        messages: list[dict[str, str]],
        system_prompt: str,
    ) -> Any:
        response = await self._http.post(
            self._build_responses_url(self.settings.openai_base_url),
            headers={
                "Authorization": f"Bearer {self.settings.openai_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.settings.openai_model,
                "input": [
                    {
                        "role": "system",
                        "content": system_prompt,
                    },
                    *messages,
                ],
            },
        )
        return self._parse_response_payload(response)

    def _build_responses_url(self, base_url: str) -> str:
        normalized = base_url.strip().rstrip("/")
        if normalized.endswith("/responses"):
            return normalized
        if normalized.endswith("/v1"):
            return f"{normalized}/responses"
        return f"{normalized}/v1/responses"

    def _build_gemini_url(self, base_url: str, model: str) -> str:
        normalized = base_url.strip().rstrip("/")
        if normalized.endswith(":generateContent"):
            return normalized
        model_path = f"/models/{model}"
        if model_path in normalized:
            return normalized if normalized.endswith(":generateContent") else f"{normalized}:generateContent"
        if normalized.endswith("/models"):
            return f"{normalized}/{model}:generateContent"
        return f"{normalized}/models/{model}:generateContent"

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
                "A route is an ordered path of conditions followed by actions.",
                "If the strategy has alternative triggers, opposite-side entries, or multiple if/then branches, use routes.",
                "Do not combine opposite-side entries into one linear condition/action list unless the user explicitly wants both actions to happen after the same trigger path.",
                "If the user says long when X and short when Y, return two routes.",
                "When editing an existing draft, preserve unchanged routes, markets, and risk intent unless the user asks to replace them.",
                "If the current draft includes routes or graph data, use that structure as the source of truth for the existing logic.",
                "Always include top-level conditions and actions. If you return routes, make the top-level conditions/actions match the primary route.",
                f"Current draft context: {current_draft_summary}",
                "Return exactly this shape:",
                '{"reply":"short natural language summary","name":"string","description":"string","marketSelection":"selected|all","markets":["BTC"],"conditions":[{"type":"ema_crosses_above","symbol":"BTC","timeframe":"15m","fast_period":9,"slow_period":21}],"actions":[{"type":"open_long","symbol":"BTC","size_usd":150,"leverage":3}],"routes":[{"name":"optional-route-name","conditions":[{"type":"rsi_above","symbol":"BTC","timeframe":"15m","period":14,"value":70}],"actions":[{"type":"open_short","symbol":"BTC","size_usd":150,"leverage":3},{"type":"set_tpsl","symbol":"BTC","take_profit_pct":2,"stop_loss_pct":1}]},{"name":"optional-second-route","conditions":[{"type":"rsi_below","symbol":"BTC","timeframe":"15m","period":14,"value":30}],"actions":[{"type":"open_long","symbol":"BTC","size_usd":150,"leverage":3},{"type":"set_tpsl","symbol":"BTC","take_profit_pct":2,"stop_loss_pct":1}]}]}',
            ]
        )

    def _build_gemini_contents(self, messages: list[dict[str, str]]) -> list[dict[str, Any]]:
        contents: list[dict[str, Any]] = []
        for message in messages:
            content = message.get("content", "").strip()
            if not content:
                continue
            contents.append(
                {
                    "role": "model" if message.get("role") == "assistant" else "user",
                    "parts": [{"text": content}],
                }
            )
        return contents

    def _parse_response_payload(self, response: Any) -> Any:
        try:
            payload = response.json()
        except ValueError as exc:
            raise RuntimeError("AI provider returned a non-JSON response.") from exc
        if getattr(response, "status_code", 500) >= 400:
            error = payload.get("error", {}) if isinstance(payload, dict) else {}
            detail = error.get("message") if isinstance(error, dict) else None
            raise RuntimeError(str(detail or "AI request failed."))
        return payload

    def _extract_openai_text(self, payload: Any) -> str:
        if not isinstance(payload, dict):
            return ""
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
        return ""

    def _extract_gemini_text(self, payload: Any) -> str:
        if not isinstance(payload, dict):
            return ""
        candidates = payload.get("candidates")
        if not isinstance(candidates, list):
            return ""
        chunks: list[str] = []
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            content = candidate.get("content")
            if not isinstance(content, dict):
                continue
            parts = content.get("parts")
            if not isinstance(parts, list):
                continue
            for part in parts:
                if isinstance(part, dict) and isinstance(part.get("functionCall"), dict):
                    function_call = part["functionCall"]
                    if function_call.get("name"):
                        return json.dumps(
                            {
                                "function": {
                                    "name": function_call.get("name"),
                                    "arguments": function_call.get("args", {}),
                                }
                            }
                        )
                if isinstance(part, dict) and isinstance(part.get("text"), str):
                    chunks.append(part["text"])
        return "\n".join(chunks).strip()

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
