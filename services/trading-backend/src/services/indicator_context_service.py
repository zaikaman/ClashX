from __future__ import annotations

import json
from typing import Any

from src.services.pacifica_client import PacificaClient, get_pacifica_client
from src.services.pacifica_market_data_service import PacificaMarketDataService, get_pacifica_market_data_service

TIMEFRAME_TO_MS: dict[str, int] = {
    "1m": 60_000,
    "5m": 300_000,
    "15m": 900_000,
    "30m": 1_800_000,
    "1h": 3_600_000,
    "4h": 14_400_000,
    "1d": 86_400_000,
}

DEFAULT_INDICATOR_TIMEFRAME = "15m"
INDICATOR_CONDITION_TYPES = {
    "price_change_pct_above",
    "price_change_pct_below",
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
}


def normalize_symbol(value: Any) -> str:
    return str(value or "").upper().replace("-PERP", "").strip()


def normalize_timeframe(value: Any) -> str:
    candidate = str(value or "").strip().lower()
    return candidate if candidate in TIMEFRAME_TO_MS else DEFAULT_INDICATOR_TIMEFRAME


def _iter_condition_configs(rules_json: dict[str, Any]) -> list[dict[str, Any]]:
    conditions: list[dict[str, Any]] = []

    flat_conditions = rules_json.get("conditions")
    if isinstance(flat_conditions, list):
        for item in flat_conditions:
            if isinstance(item, dict):
                conditions.append(item)

    graph = rules_json.get("graph")
    if isinstance(graph, dict):
        nodes = graph.get("nodes")
        if isinstance(nodes, list):
            for node in nodes:
                if not isinstance(node, dict) or str(node.get("kind") or "").strip() != "condition":
                    continue
                config = node.get("config")
                if isinstance(config, dict):
                    conditions.append(config)

    return conditions


def _required_lookback(condition: dict[str, Any]) -> int:
    condition_type = str(condition.get("type") or "").strip()
    if condition_type == "rsi_above" or condition_type == "rsi_below":
        period = max(2, int(float(condition.get("period") or 14)))
        return period + 8
    if condition_type == "sma_above" or condition_type == "sma_below":
        period = max(2, int(float(condition.get("period") or 20)))
        return period + 4
    if condition_type == "price_change_pct_above" or condition_type == "price_change_pct_below":
        period = max(1, int(float(condition.get("period") or 5)))
        return period + 4
    if condition_type == "volatility_above" or condition_type == "volatility_below":
        period = max(2, int(float(condition.get("period") or 20)))
        return period + 4
    if condition_type == "bollinger_above_upper" or condition_type == "bollinger_below_lower":
        period = max(2, int(float(condition.get("period") or 20)))
        return period + 4
    if condition_type == "breakout_above_recent_high" or condition_type == "breakout_below_recent_low":
        period = max(2, int(float(condition.get("period") or 20)))
        return period + 3
    if condition_type == "atr_above" or condition_type == "atr_below":
        period = max(2, int(float(condition.get("period") or 14)))
        return period + 4
    if condition_type == "vwap_above" or condition_type == "vwap_below":
        period = max(2, int(float(condition.get("period") or 24)))
        return period + 2
    if condition_type == "higher_timeframe_sma_above" or condition_type == "higher_timeframe_sma_below":
        period = max(2, int(float(condition.get("period") or 20)))
        return period + 4
    if condition_type == "ema_crosses_above" or condition_type == "ema_crosses_below":
        fast_period = max(2, int(float(condition.get("fast_period") or 9)))
        slow_period = max(fast_period + 1, int(float(condition.get("slow_period") or 21)))
        return slow_period + 8
    if condition_type == "macd_crosses_above_signal" or condition_type == "macd_crosses_below_signal":
        fast_period = max(2, int(float(condition.get("fast_period") or 12)))
        slow_period = max(fast_period + 1, int(float(condition.get("slow_period") or 26)))
        signal_period = max(2, int(float(condition.get("signal_period") or 9)))
        return slow_period + signal_period + 12
    return 0


def extract_candle_requests(rules_json: dict[str, Any]) -> list[dict[str, Any]]:
    requests: dict[tuple[str, str], int] = {}

    for condition in _iter_condition_configs(rules_json):
        condition_type = str(condition.get("type") or "").strip()
        if condition_type not in INDICATOR_CONDITION_TYPES:
            continue
        symbol = normalize_symbol(condition.get("symbol"))
        if not symbol:
            continue
        timeframe = normalize_timeframe(condition.get("timeframe"))
        lookback = _required_lookback(condition)
        key = (symbol, timeframe)
        requests[key] = max(requests.get(key, 0), lookback)
        if condition_type in {"higher_timeframe_sma_above", "higher_timeframe_sma_below"}:
            secondary_timeframe = normalize_timeframe(condition.get("secondary_timeframe"))
            secondary_key = (symbol, secondary_timeframe)
            requests[secondary_key] = max(requests.get(secondary_key, 0), lookback)

    return [
        {"symbol": symbol, "timeframe": timeframe, "lookback": lookback}
        for (symbol, timeframe), lookback in sorted(requests.items())
        if lookback > 0
    ]


def extract_indicator_conditions(rules_json: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        dict(condition)
        for condition in _iter_condition_configs(rules_json)
        if str(condition.get("type") or "").strip() in INDICATOR_CONDITION_TYPES
    ]


def indicator_condition_key(condition: dict[str, Any]) -> str:
    normalized = {
        key: value
        for key, value in condition.items()
        if key
    }
    if "symbol" in normalized:
        normalized["symbol"] = normalize_symbol(normalized.get("symbol"))
    if "timeframe" in normalized:
        normalized["timeframe"] = normalize_timeframe(normalized.get("timeframe"))
    if "secondary_timeframe" in normalized:
        normalized["secondary_timeframe"] = normalize_timeframe(normalized.get("secondary_timeframe"))
    return json.dumps(normalized, sort_keys=True, separators=(",", ":"), default=str)


class IndicatorContextService:
    def __init__(self, pacifica_client: PacificaClient | None = None) -> None:
        self.pacifica_client = pacifica_client or get_pacifica_client()
        if pacifica_client is None:
            self.market_data = get_pacifica_market_data_service()
        else:
            self.market_data = PacificaMarketDataService(self.pacifica_client)

    async def load_candle_lookup(self, rules_json: dict[str, Any]) -> dict[str, dict[str, list[dict[str, Any]]]]:
        requests = extract_candle_requests(rules_json)
        if not requests:
            return {}
        return await self.market_data.load_candle_lookup(requests)
