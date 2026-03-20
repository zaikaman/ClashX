from __future__ import annotations

from typing import Any

from src.services.indicator_context_service import IndicatorContextService
from src.services.pacifica_client import PacificaClient, PacificaClientError
from src.services.rules_engine import RulesEngine


class BuilderCatalogService:
    _TEMPLATES = [
        {
            "id": "momentum-breakout-v1",
            "name": "Momentum Breakout",
            "description": "Enters on trend confirmation and exits via TP/SL guards.",
            "authoring_mode": "visual",
            "risk_profile": "moderate",
        },
        {
            "id": "mean-revert-v1",
            "name": "Mean Reversion",
            "description": "Trades deviations from anchor bands with strict cooldown.",
            "authoring_mode": "visual",
            "risk_profile": "moderate",
        },
    ]
    _CONDITION_LABELS = {
        "price_above": "Price Above Level",
        "price_below": "Price Below Level",
        "price_change_pct_above": "Price Change Above %",
        "price_change_pct_below": "Price Change Below %",
        "has_position": "Position Exists",
        "position_side_is": "Position Side Matches",
        "cooldown_elapsed": "Cooldown Elapsed",
        "funding_rate_above": "Funding Above Threshold",
        "funding_rate_below": "Funding Below Threshold",
        "volume_above": "Volume Above Threshold",
        "volume_below": "Volume Below Threshold",
        "rsi_above": "RSI Above Threshold",
        "rsi_below": "RSI Below Threshold",
        "sma_above": "Price Above SMA",
        "sma_below": "Price Below SMA",
        "volatility_above": "Volatility Above Threshold",
        "volatility_below": "Volatility Below Threshold",
        "bollinger_above_upper": "Bollinger Above Upper Band",
        "bollinger_below_lower": "Bollinger Below Lower Band",
        "breakout_above_recent_high": "Breakout Above Recent High",
        "breakout_below_recent_low": "Breakout Below Recent Low",
        "atr_above": "ATR Above Threshold",
        "atr_below": "ATR Below Threshold",
        "vwap_above": "Price Above VWAP",
        "vwap_below": "Price Below VWAP",
        "higher_timeframe_sma_above": "Higher Timeframe SMA Long Bias",
        "higher_timeframe_sma_below": "Higher Timeframe SMA Short Bias",
        "ema_crosses_above": "EMA Crosses Above",
        "ema_crosses_below": "EMA Crosses Below",
        "macd_crosses_above_signal": "MACD Crosses Above Signal",
        "macd_crosses_below_signal": "MACD Crosses Below Signal",
        "position_pnl_above": "Position PnL Above Threshold",
        "position_pnl_below": "Position PnL Below Threshold",
        "position_pnl_pct_above": "Position PnL % Above Threshold",
        "position_pnl_pct_below": "Position PnL % Below Threshold",
        "position_in_profit": "Position In Profit",
        "position_in_loss": "Position In Loss",
    }
    _ACTION_LABELS = {
        "open_long": "Open Long",
        "open_short": "Open Short",
        "place_market_order": "Place Market Order",
        "place_limit_order": "Place Limit Order",
        "place_twap_order": "Place TWAP Order",
        "close_position": "Close Position",
        "set_tpsl": "Set Take Profit / Stop Loss",
        "update_leverage": "Update Leverage",
        "cancel_order": "Cancel Order",
        "cancel_twap_order": "Cancel TWAP Order",
        "cancel_all_orders": "Cancel All Orders",
    }

    def __init__(
        self,
        pacifica_client: PacificaClient | None = None,
        rules_engine: RulesEngine | None = None,
    ) -> None:
        self.pacifica_client = pacifica_client or PacificaClient()
        self.rules_engine = rules_engine or RulesEngine()
        self.indicator_context = IndicatorContextService(self.pacifica_client)

    def templates(self) -> list[dict]:
        return [template.copy() for template in self._TEMPLATES]

    def blocks(self) -> list[dict]:
        blocks: list[dict[str, str]] = []
        for key in sorted(self.rules_engine.APPROVED_CONDITIONS):
            blocks.append(
                {
                    "type": "condition",
                    "key": key,
                    "label": self._CONDITION_LABELS.get(key, key.replace("_", " ").title()),
                }
            )
        for key in sorted(self.rules_engine.APPROVED_ACTIONS):
            blocks.append(
                {
                    "type": "action",
                    "key": key,
                    "label": self._ACTION_LABELS.get(key, key.replace("_", " ").title()),
                }
            )
        return blocks

    async def markets(self) -> list[dict]:
        try:
            markets = await self.pacifica_client.get_markets()
        except PacificaClientError:
            return []

        return [
            {
                "symbol": market["display_symbol"],
                "status": "active" if float(market.get("mark_price", 0) or 0) > 0 else "stale",
                "mark_price": market.get("mark_price", 0),
                "funding_rate": market.get("funding_rate", 0),
                "volume_24h": market.get("volume_24h", 0),
                "max_leverage": market.get("max_leverage", 0),
            }
            for market in markets
        ]

    async def simulate(self, rules_json: dict, market_context: dict | None = None) -> dict:
        normalized_rules = rules_json if isinstance(rules_json, dict) else {}
        issues = self._validation_issues(normalized_rules)
        context = await self._build_context(normalized_rules, market_context)
        evaluation = self.rules_engine.evaluate(rules_json=normalized_rules, context=context)
        planned_actions = evaluation.get("actions") if isinstance(evaluation.get("actions"), list) else []
        evaluated_conditions = evaluation.get("evaluated_conditions")

        return {
            "valid": len(issues) == 0,
            "triggered": bool(evaluation.get("triggered")) and len(issues) == 0,
            "evaluated_conditions": int(evaluated_conditions) if isinstance(evaluated_conditions, int | float) else 0,
            "planned_actions": len(planned_actions),
            "market_context": {
                "selected_symbols": sorted(context.get("market_lookup", {}).keys()),
                "market_lookup": context.get("market_lookup", {}),
                "position_lookup": context.get("position_lookup", {}),
                "candle_lookup": context.get("candle_lookup", {}),
                "runtime": context.get("runtime", {}),
                "issues": issues,
                "reasons": evaluation.get("reasons", []),
            },
        }

    def _validation_issues(self, rules_json: dict[str, Any]) -> list[str]:
        return self.rules_engine.validation_issues(rules_json=rules_json)

    async def _build_context(self, rules_json: dict[str, Any], market_context: dict | None) -> dict[str, Any]:
        context = market_context.copy() if isinstance(market_context, dict) else {}
        market_lookup = self._normalize_market_lookup(context.get("market_lookup"))
        if not market_lookup:
            market_lookup = await self._load_market_lookup(self._extract_symbols(rules_json))

        candle_lookup = await self.indicator_context.load_candle_lookup(rules_json)
        position_lookup = context.get("position_lookup")
        runtime = context.get("runtime")
        return {
            "market_lookup": market_lookup,
            "candle_lookup": candle_lookup,
            "position_lookup": position_lookup if isinstance(position_lookup, dict) else {},
            "runtime": runtime if isinstance(runtime, dict) else {},
        }

    async def _load_market_lookup(self, symbols: set[str]) -> dict[str, dict[str, Any]]:
        try:
            markets = await self.pacifica_client.get_markets()
        except PacificaClientError:
            return {}

        lookup: dict[str, dict[str, Any]] = {}
        for market in markets:
            symbol = str(market.get("symbol") or "").upper().replace("-PERP", "").strip()
            if not symbol or (symbols and symbol not in symbols):
                continue
            lookup[symbol] = {
                "mark_price": float(market.get("mark_price", 0) or 0),
                "funding_rate": float(market.get("funding_rate", 0) or 0),
                "volume_24h": float(market.get("volume_24h", 0) or 0),
                "updated_at": market.get("updated_at"),
            }
        return lookup

    def _normalize_market_lookup(self, value: Any) -> dict[str, dict[str, Any]]:
        if not isinstance(value, dict):
            return {}

        lookup: dict[str, dict[str, Any]] = {}
        for symbol, payload in value.items():
            if not isinstance(payload, dict):
                continue
            normalized_symbol = str(symbol).upper().replace("-PERP", "").strip()
            if not normalized_symbol:
                continue
            lookup[normalized_symbol] = dict(payload)
        return lookup

    def _extract_symbols(self, rules_json: dict[str, Any]) -> set[str]:
        symbols: set[str] = set()
        for group in ("conditions", "actions"):
            rows = rules_json.get(group)
            if not isinstance(rows, list):
                continue
            for row in rows:
                if not isinstance(row, dict):
                    continue
                symbol = str(row.get("symbol") or "").upper().replace("-PERP", "").strip()
                if symbol:
                    symbols.add(symbol)

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
                    symbol = str(config.get("symbol") or "").upper().replace("-PERP", "").strip()
                    if symbol:
                        symbols.add(symbol)
        return symbols
