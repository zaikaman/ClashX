from __future__ import annotations

import json
import re
from typing import Any

import httpx

from src.core.settings import get_settings

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


class BuilderAiService:
    def __init__(self) -> None:
        self.settings = get_settings()

    async def generate_draft(
        self,
        messages: list[dict[str, str]],
        available_markets: list[str],
        current_draft: dict[str, Any] | None,
    ) -> dict[str, Any]:
        if (
            not self.settings.openai_api_key
            or not self.settings.openai_base_url
            or not self.settings.openai_model
        ):
            raise RuntimeError("Missing OPENAI_API_KEY, OPENAI_BASE_URL, or OPENAI_MODEL.")

        async with httpx.AsyncClient(timeout=45.0) as client:
            response = await client.post(
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
                            "content": self._build_system_prompt(available_markets, current_draft),
                        },
                        *messages,
                    ],
                },
            )
            payload = response.json()

        if response.status_code >= 400:
            error = payload.get("error", {}) if isinstance(payload, dict) else {}
            detail = error.get("message") if isinstance(error, dict) else None
            raise RuntimeError(str(detail or "AI request failed."))

        raw_text = self._extract_text(payload)
        parsed = self._extract_json(raw_text)
        return self._sanitize_draft(parsed, available_markets)

    def _build_responses_url(self, base_url: str) -> str:
        normalized = base_url.strip().rstrip("/")
        if normalized.endswith("/responses"):
            return normalized
        if normalized.endswith("/v1"):
            return f"{normalized}/responses"
        return f"{normalized}/v1/responses"

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
                f"Current draft context: {current_draft_summary}",
                "Return exactly this shape:",
                '{"reply":"short natural language summary","name":"string","description":"string","marketSelection":"selected|all","markets":["BTC"],"conditions":[{"type":"ema_crosses_above","symbol":"BTC","timeframe":"15m","fast_period":9,"slow_period":21}],"actions":[{"type":"open_long","symbol":"BTC","size_usd":150,"leverage":3}]}',
            ]
        )

    def _extract_text(self, payload: Any) -> str:
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
                content = item.get("content")
                if not isinstance(content, list):
                    continue
                for part in content:
                    if isinstance(part, dict) and isinstance(part.get("text"), str):
                        chunks.append(part["text"])
            if chunks:
                return "\n".join(chunks).strip()
        return ""

    def _extract_json(self, value: str) -> dict[str, Any]:
        trimmed = value.strip()
        if not trimmed:
            raise RuntimeError("Empty AI response")
        fenced = re.search(r"```(?:json)?\s*([\s\S]*?)```", trimmed, re.IGNORECASE)
        candidate = fenced.group(1).strip() if fenced else trimmed
        first_brace = candidate.find("{")
        last_brace = candidate.rfind("}")
        if first_brace == -1 or last_brace == -1 or last_brace < first_brace:
            raise RuntimeError("AI response did not contain JSON")
        parsed = json.loads(candidate[first_brace : last_brace + 1])
        if not isinstance(parsed, dict):
            raise RuntimeError("AI response JSON must be an object")
        return parsed

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

    def _sanitize_draft(self, payload: dict[str, Any], available_markets: list[str]) -> dict[str, Any]:
        allowed_markets = {market.strip().upper() for market in available_markets if market.strip()}
        requested_markets = self._normalize_markets(payload.get("markets"))
        markets = [
            market for market in requested_markets if not allowed_markets or market in allowed_markets
        ]

        raw_conditions = payload.get("conditions")
        conditions: list[dict[str, Any]] = []
        if isinstance(raw_conditions, list):
            for item in raw_conditions:
                if isinstance(item, dict) and item.get("type") in CONDITION_OPTIONS:
                    conditions.append(
                        {
                            **item,
                            "symbol": item.get("symbol", "").strip().upper()
                            if isinstance(item.get("symbol"), str)
                            else None,
                        }
                    )

        raw_actions = payload.get("actions")
        actions: list[dict[str, Any]] = []
        if isinstance(raw_actions, list):
            for item in raw_actions:
                if isinstance(item, dict) and item.get("type") in ACTION_OPTIONS:
                    actions.append(
                        {
                            **item,
                            "symbol": item.get("symbol", "").strip().upper()
                            if isinstance(item.get("symbol"), str)
                            else None,
                        }
                    )

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
            },
        }
