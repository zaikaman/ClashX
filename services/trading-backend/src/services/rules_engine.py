from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from src.services.indicator_context_service import (
    DEFAULT_INDICATOR_TIMEFRAME,
    normalize_symbol,
    normalize_timeframe,
)


@dataclass(frozen=True)
class _GraphNode:
    id: str
    kind: str
    config: dict[str, Any]
    position_x: float
    position_y: float


@dataclass(frozen=True)
class _GraphEdge:
    id: str
    source: str
    target: str


@dataclass(frozen=True)
class _GraphInspection:
    entry: str
    nodes: dict[str, _GraphNode]
    outgoing: dict[str, list[_GraphEdge]]
    issues: list[str]
    reachable_conditions: int
    reachable_actions: int


class RulesEngine:
    APPROVED_CONDITIONS = {
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
    }
    APPROVED_ACTIONS = {
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
    }

    def validation_issues(self, *, rules_json: dict[str, Any]) -> list[str]:
        if not isinstance(rules_json, dict):
            return ["rules_json must be an object"]

        if "graph" in rules_json:
            return self._inspect_graph(rules_json.get("graph")).issues

        conditions = rules_json.get("conditions")
        actions = rules_json.get("actions")
        issues = []
        if not isinstance(conditions, list) or len(conditions) == 0:
            issues.append("visual bots require at least one condition block")
        if not isinstance(actions, list) or len(actions) == 0:
            issues.append("visual bots require at least one action block")

        if isinstance(conditions, list):
            for condition in conditions:
                if not isinstance(condition, dict):
                    issues.append("conditions must be objects")
                    continue
                condition_type = str(condition.get("type") or "").strip()
                if condition_type not in self.APPROVED_CONDITIONS:
                    issues.append(f"unsupported condition: {condition_type or 'unknown'}")

        if isinstance(actions, list):
            for action in actions:
                if not isinstance(action, dict):
                    issues.append("actions must be objects")
                    continue
                action_type = str(action.get("type") or "").strip()
                if action_type not in self.APPROVED_ACTIONS:
                    issues.append(f"unsupported action: {action_type or 'unknown'}")

        return issues

    def evaluate(self, *, rules_json: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(rules_json, dict):
            return {
                "triggered": False,
                "reasons": ["rules_json must be an object"],
                "actions": [],
                "evaluated_conditions": 0,
            }

        if "graph" in rules_json:
            inspection = self._inspect_graph(rules_json.get("graph"))
            if inspection.issues:
                return {
                    "triggered": False,
                    "reasons": inspection.issues.copy(),
                    "actions": [],
                    "evaluated_conditions": 0,
                }
            return self._evaluate_graph(inspection=inspection, context=context)

        conditions = rules_json.get("conditions") if isinstance(rules_json.get("conditions"), list) else []
        actions = rules_json.get("actions") if isinstance(rules_json.get("actions"), list) else []
        if not conditions:
            return {
                "triggered": False,
                "reasons": ["missing conditions"],
                "actions": [],
                "evaluated_conditions": 0,
            }
        if not actions:
            return {
                "triggered": False,
                "reasons": ["missing actions"],
                "actions": [],
                "evaluated_conditions": 0,
            }

        reasons: list[str] = []
        for condition in conditions:
            passed, reason = self._evaluate_condition(condition, context)
            reasons.append(reason)
            if not passed:
                return {
                    "triggered": False,
                    "reasons": reasons,
                    "actions": [],
                    "evaluated_conditions": len(reasons),
                }

        normalized_actions = [action for action in (self._normalize_action(item) for item in actions) if action is not None]
        return {
            "triggered": len(normalized_actions) > 0,
            "reasons": reasons,
            "actions": normalized_actions,
            "evaluated_conditions": len(conditions),
        }

    def _evaluate_graph(self, *, inspection: _GraphInspection, context: dict[str, Any]) -> dict[str, Any]:
        actions, reasons, evaluated_conditions = self._visit_graph_node(
            inspection=inspection,
            node_id=inspection.entry,
            context=context,
            trail=(),
        )
        return {
            "triggered": len(actions) > 0,
            "reasons": reasons,
            "actions": actions,
            "evaluated_conditions": evaluated_conditions,
        }

    def _visit_graph_node(
        self,
        *,
        inspection: _GraphInspection,
        node_id: str,
        context: dict[str, Any],
        trail: tuple[str, ...],
    ) -> tuple[list[dict[str, Any]], list[str], int]:
        if node_id in trail:
            return [], [f"graph contains a cycle involving {node_id}"], 0

        node = inspection.nodes.get(node_id)
        if node is None:
            return [], [f"graph node missing: {node_id}"], 0

        next_trail = (*trail, node_id)
        if node.kind == "entry":
            return self._visit_graph_children(
                inspection=inspection,
                source_id=node.id,
                context=context,
                trail=next_trail,
            )

        if node.kind == "condition":
            passed, reason = self._evaluate_condition(node.config, context)
            prefixed_reason = f"{node.id}: {reason}"
            if not passed:
                return [], [prefixed_reason], 1
            actions, reasons, evaluated_conditions = self._visit_graph_children(
                inspection=inspection,
                source_id=node.id,
                context=context,
                trail=next_trail,
            )
            return actions, [prefixed_reason, *reasons], evaluated_conditions + 1

        normalized_action = self._normalize_action(node.config)
        action_reasons: list[str] = []
        action_results: list[dict[str, Any]] = []
        if normalized_action is None:
            action_reasons.append(f"{node.id}: unsupported action: {node.config.get('type') or 'unknown'}")
        else:
            action_results.append(normalized_action)

        child_actions, child_reasons, evaluated_conditions = self._visit_graph_children(
            inspection=inspection,
            source_id=node.id,
            context=context,
            trail=next_trail,
        )
        return [*action_results, *child_actions], [*action_reasons, *child_reasons], evaluated_conditions

    def _visit_graph_children(
        self,
        *,
        inspection: _GraphInspection,
        source_id: str,
        context: dict[str, Any],
        trail: tuple[str, ...],
    ) -> tuple[list[dict[str, Any]], list[str], int]:
        actions: list[dict[str, Any]] = []
        reasons: list[str] = []
        evaluated_conditions = 0
        for edge in inspection.outgoing.get(source_id, []):
            branch_actions, branch_reasons, branch_condition_count = self._visit_graph_node(
                inspection=inspection,
                node_id=edge.target,
                context=context,
                trail=trail,
            )
            actions.extend(branch_actions)
            reasons.extend(branch_reasons)
            evaluated_conditions += branch_condition_count
        return actions, reasons, evaluated_conditions

    def _inspect_graph(self, graph_payload: Any) -> _GraphInspection:
        issues: list[str] = []
        if not isinstance(graph_payload, dict):
            return _GraphInspection(
                entry="",
                nodes={},
                outgoing={},
                issues=["graph must be an object"],
                reachable_conditions=0,
                reachable_actions=0,
            )

        entry = str(graph_payload.get("entry") or "").strip()
        raw_nodes = graph_payload.get("nodes")
        raw_edges = graph_payload.get("edges")
        if not entry:
            issues.append("graph requires an entry node")
        if not isinstance(raw_nodes, list):
            issues.append("graph nodes must be an array")
            raw_nodes = []
        if not isinstance(raw_edges, list):
            issues.append("graph edges must be an array")
            raw_edges = []

        nodes: dict[str, _GraphNode] = {}
        entry_nodes: list[str] = []
        for index, raw_node in enumerate(raw_nodes):
            if not isinstance(raw_node, dict):
                issues.append("graph nodes must be objects")
                continue

            node_id = str(raw_node.get("id") or "").strip()
            kind = str(raw_node.get("kind") or "").strip()
            if not node_id:
                issues.append(f"graph node at index {index} is missing an id")
                continue
            if node_id in nodes:
                issues.append(f"duplicate graph node id: {node_id}")
                continue
            if kind not in {"entry", "condition", "action"}:
                issues.append(f"unsupported graph node kind: {kind or 'unknown'}")
                continue

            if kind == "entry":
                entry_nodes.append(node_id)
                config: dict[str, Any] = {}
            else:
                raw_config = raw_node.get("config")
                if not isinstance(raw_config, dict):
                    issues.append(f"graph node {node_id} requires a config object")
                    raw_config = {}
                config = dict(raw_config)
                node_type = str(config.get("type") or "").strip()
                approved_types = self.APPROVED_CONDITIONS if kind == "condition" else self.APPROVED_ACTIONS
                noun = "condition" if kind == "condition" else "action"
                if node_type not in approved_types:
                    issues.append(f"unsupported {noun}: {node_type or 'unknown'}")

            position = raw_node.get("position")
            position_x = self._position_value(position, "x")
            position_y = self._position_value(position, "y")
            nodes[node_id] = _GraphNode(
                id=node_id,
                kind=kind,
                config=config,
                position_x=position_x,
                position_y=position_y,
            )

        if len(entry_nodes) != 1:
            issues.append("graph must contain exactly one entry node")
        if entry and entry not in nodes:
            issues.append("graph entry node is missing")
        elif entry and nodes.get(entry) is not None and nodes[entry].kind != "entry":
            issues.append("graph entry must reference an entry node")

        outgoing_lookup: defaultdict[str, list[_GraphEdge]] = defaultdict(list)
        incoming_counts: defaultdict[str, int] = defaultdict(int)
        for index, raw_edge in enumerate(raw_edges):
            if not isinstance(raw_edge, dict):
                issues.append("graph edges must be objects")
                continue

            edge_id = str(raw_edge.get("id") or f"edge-{index + 1}").strip() or f"edge-{index + 1}"
            source = str(raw_edge.get("source") or "").strip()
            target = str(raw_edge.get("target") or "").strip()
            if not source or not target:
                issues.append(f"graph edge {edge_id} must include source and target")
                continue
            if source == target:
                issues.append(f"graph edge {edge_id} cannot connect a node to itself")
                continue
            if source not in nodes or target not in nodes:
                issues.append(f"graph edge {edge_id} references an unknown node")
                continue
            if nodes[target].kind == "entry":
                issues.append(f"graph edge {edge_id} cannot target the entry node")
                continue

            outgoing_lookup[source].append(_GraphEdge(id=edge_id, source=source, target=target))
            incoming_counts[target] += 1

        for node_id, incoming_count in incoming_counts.items():
            node = nodes.get(node_id)
            if node is not None and node.kind != "entry" and incoming_count > 1:
                issues.append(f"graph node {node_id} cannot have more than one incoming edge")

        outgoing: dict[str, list[_GraphEdge]] = {}
        for source_id, edges in outgoing_lookup.items():
            outgoing[source_id] = sorted(
                edges,
                key=lambda edge: (
                    nodes[edge.target].position_x,
                    nodes[edge.target].position_y,
                    edge.id,
                ),
            )

        reachable_conditions = 0
        reachable_actions = 0
        if entry in nodes:
            cycle_nodes: set[str] = set()
            state: dict[str, int] = {}

            def walk(node_id: str) -> None:
                nonlocal reachable_conditions, reachable_actions
                state[node_id] = 1
                node = nodes[node_id]
                if node.kind == "condition":
                    reachable_conditions += 1
                elif node.kind == "action":
                    reachable_actions += 1

                for edge in outgoing.get(node_id, []):
                    target_state = state.get(edge.target, 0)
                    if target_state == 0:
                        walk(edge.target)
                    elif target_state == 1:
                        cycle_nodes.add(edge.target)

                state[node_id] = 2

            walk(entry)
            for node_id in sorted(cycle_nodes):
                issues.append(f"graph contains a cycle involving {node_id}")

        if reachable_conditions == 0:
            issues.append("visual bots require at least one reachable condition block")
        if reachable_actions == 0:
            issues.append("visual bots require at least one reachable action block")

        return _GraphInspection(
            entry=entry,
            nodes=nodes,
            outgoing=outgoing,
            issues=issues,
            reachable_conditions=reachable_conditions,
            reachable_actions=reachable_actions,
        )

    def _evaluate_condition(self, condition: Any, context: dict[str, Any]) -> tuple[bool, str]:
        if not isinstance(condition, dict):
            return False, "invalid condition"
        condition_type = str(condition.get("type") or "").strip()
        if condition_type not in self.APPROVED_CONDITIONS:
            return False, f"unsupported condition: {condition_type or 'unknown'}"

        runtime_state = ((context.get("runtime") or {}).get("state") or {}) if isinstance(context.get("runtime"), dict) else {}
        market_lookup = context.get("market_lookup") if isinstance(context.get("market_lookup"), dict) else {}
        position_lookup = context.get("position_lookup") if isinstance(context.get("position_lookup"), dict) else {}
        candle_lookup = context.get("candle_lookup") if isinstance(context.get("candle_lookup"), dict) else {}

        if condition_type in {"price_above", "price_below"}:
            symbol = normalize_symbol(condition.get("symbol"))
            value = self._to_float(condition.get("value"), 0.0)
            mark_price = self._to_float((market_lookup.get(symbol) or {}).get("mark_price"), 0.0)
            if mark_price <= 0:
                return False, f"market price unavailable for {symbol}"
            if condition_type == "price_above":
                return mark_price > value, f"{symbol} mark {mark_price:.4f} > {value:.4f}"
            return mark_price < value, f"{symbol} mark {mark_price:.4f} < {value:.4f}"

        if condition_type in {"funding_rate_above", "funding_rate_below"}:
            symbol = normalize_symbol(condition.get("symbol"))
            threshold = self._to_float(condition.get("value"), 0.0)
            funding_rate = self._to_float((market_lookup.get(symbol) or {}).get("funding_rate"), 0.0)
            if condition_type == "funding_rate_above":
                return funding_rate > threshold, f"{symbol} funding {funding_rate:.6f} > {threshold:.6f}"
            return funding_rate < threshold, f"{symbol} funding {funding_rate:.6f} < {threshold:.6f}"

        if condition_type in {"volume_above", "volume_below"}:
            symbol = normalize_symbol(condition.get("symbol"))
            threshold = self._to_float(condition.get("value"), 0.0)
            volume_24h = self._to_float((market_lookup.get(symbol) or {}).get("volume_24h"), 0.0)
            if condition_type == "volume_above":
                return volume_24h > threshold, f"{symbol} volume {volume_24h:.2f} > {threshold:.2f}"
            return volume_24h < threshold, f"{symbol} volume {volume_24h:.2f} < {threshold:.2f}"

        if condition_type == "has_position":
            symbol = normalize_symbol(condition.get("symbol"))
            position = position_lookup.get(symbol)
            has_position = position is not None and self._to_float(position.get("amount"), 0.0) > 0
            return has_position, f"position exists for {symbol}: {has_position}"

        if condition_type == "position_side_is":
            symbol = normalize_symbol(condition.get("symbol"))
            expected_side = str(condition.get("side") or "").lower().strip()
            position = position_lookup.get(symbol) or {}
            current_side = str(position.get("side") or "").lower().strip()
            mapped_side = "long" if current_side in {"bid", "long"} else "short"
            return mapped_side == expected_side, f"{symbol} side {mapped_side} == {expected_side}"

        if condition_type == "cooldown_elapsed":
            cooldown_seconds = int(condition.get("seconds") or 0)
            if cooldown_seconds <= 0:
                cooldown_seconds = int(condition.get("minutes") or 0) * 60
            last_executed_at = runtime_state.get("last_executed_at")
            if not isinstance(last_executed_at, str):
                return True, "no last execution, cooldown satisfied"
            try:
                last_dt = datetime.fromisoformat(last_executed_at.replace("Z", "+00:00"))
            except ValueError:
                return True, "invalid cooldown timestamp ignored"
            elapsed = (datetime.now(tz=UTC) - last_dt).total_seconds()
            return elapsed >= cooldown_seconds, f"cooldown elapsed {int(elapsed)}s / {cooldown_seconds}s"

        if condition_type in {"rsi_above", "rsi_below"}:
            return self._evaluate_rsi_condition(condition, candle_lookup)

        if condition_type in {"sma_above", "sma_below"}:
            return self._evaluate_sma_condition(condition, candle_lookup)

        if condition_type in {"price_change_pct_above", "price_change_pct_below"}:
            return self._evaluate_price_change_condition(condition, candle_lookup)

        if condition_type in {"volatility_above", "volatility_below"}:
            return self._evaluate_volatility_condition(condition, candle_lookup)

        if condition_type in {"bollinger_above_upper", "bollinger_below_lower"}:
            return self._evaluate_bollinger_condition(condition, candle_lookup)

        if condition_type in {"breakout_above_recent_high", "breakout_below_recent_low"}:
            return self._evaluate_breakout_condition(condition, candle_lookup)

        if condition_type in {"atr_above", "atr_below"}:
            return self._evaluate_atr_condition(condition, candle_lookup)

        if condition_type in {"vwap_above", "vwap_below"}:
            return self._evaluate_vwap_condition(condition, candle_lookup)

        if condition_type in {"higher_timeframe_sma_above", "higher_timeframe_sma_below"}:
            return self._evaluate_higher_timeframe_sma_condition(condition, candle_lookup)

        if condition_type in {"ema_crosses_above", "ema_crosses_below"}:
            return self._evaluate_ema_cross_condition(condition, candle_lookup)

        if condition_type in {"macd_crosses_above_signal", "macd_crosses_below_signal"}:
            return self._evaluate_macd_cross_condition(condition, candle_lookup)

        if condition_type in {"position_pnl_above", "position_pnl_below"}:
            return self._evaluate_position_pnl_condition(condition, position_lookup)

        if condition_type in {"position_pnl_pct_above", "position_pnl_pct_below"}:
            return self._evaluate_position_pnl_pct_condition(condition, position_lookup)

        if condition_type in {"position_in_profit", "position_in_loss"}:
            return self._evaluate_position_state_condition(condition, position_lookup)

        return False, f"unsupported condition: {condition_type}"

    def _normalize_action(self, action: Any) -> dict[str, Any] | None:
        if not isinstance(action, dict):
            return None
        action_type = str(action.get("type") or "").strip()
        if action_type not in self.APPROVED_ACTIONS:
            return None
        normalized: dict[str, Any] = {"type": action_type}

        symbol = action.get("symbol")
        if symbol is not None:
            normalized["symbol"] = self._normalize_symbol(symbol)

        for key in (
            "size_usd",
            "quantity",
            "leverage",
            "take_profit_pct",
            "stop_loss_pct",
            "price",
            "duration_seconds",
            "slippage_percent",
        ):
            if key in action:
                normalized[key] = self._to_float(action.get(key), 0.0)

        for key in ("side", "tif", "client_order_id"):
            if key in action and action.get(key) not in (None, ""):
                normalized[key] = str(action.get(key))

        if "order_id" in action and action.get("order_id") not in (None, ""):
            normalized["order_id"] = action.get("order_id")

        for key in ("reduce_only", "all_symbols", "exclude_reduce_only"):
            if key in action:
                normalized[key] = self._to_bool(action.get(key))

        for key in ("entrypoint", "artifact_uri", "metadata"):
            if key in action:
                normalized[key] = action[key]

        return normalized

    @staticmethod
    def _candles_for_symbol_timeframe(
        symbol: str,
        timeframe: str,
        candle_lookup: dict[str, Any],
    ) -> list[dict[str, Any]]:
        raw_candles = ((candle_lookup.get(symbol) or {}).get(timeframe) or []) if isinstance(candle_lookup, dict) else []
        return [item for item in raw_candles if isinstance(item, dict) and float(item.get("close") or 0.0) > 0]

    @classmethod
    def _candles_for_condition(cls, condition: dict[str, Any], candle_lookup: dict[str, Any]) -> tuple[str, str, list[dict[str, Any]]]:
        symbol = normalize_symbol(condition.get("symbol"))
        timeframe = normalize_timeframe(condition.get("timeframe"))
        candles = cls._candles_for_symbol_timeframe(symbol, timeframe, candle_lookup)
        return symbol, timeframe or DEFAULT_INDICATOR_TIMEFRAME, candles

    @classmethod
    def _closes_for_condition(cls, condition: dict[str, Any], candle_lookup: dict[str, Any]) -> tuple[str, str, list[float]]:
        symbol, timeframe, candles = cls._candles_for_condition(condition, candle_lookup)
        closes = [float(item.get("close") or 0.0) for item in candles]
        return symbol, timeframe, closes

    def _evaluate_rsi_condition(self, condition: dict[str, Any], candle_lookup: dict[str, Any]) -> tuple[bool, str]:
        symbol, timeframe, closes = self._closes_for_condition(condition, candle_lookup)
        period = max(2, int(self._to_float(condition.get("period"), 14)))
        threshold = self._to_float(condition.get("value"), 70.0 if str(condition.get("type")) == "rsi_above" else 30.0)
        rsi_value = self._latest_rsi(closes, period)
        if rsi_value is None:
            return False, f"indicator data unavailable for {symbol} {timeframe} RSI({period})"
        if str(condition.get("type")) == "rsi_above":
            return rsi_value > threshold, f"{symbol} {timeframe} RSI({period}) {rsi_value:.2f} > {threshold:.2f}"
        return rsi_value < threshold, f"{symbol} {timeframe} RSI({period}) {rsi_value:.2f} < {threshold:.2f}"

    def _evaluate_sma_condition(self, condition: dict[str, Any], candle_lookup: dict[str, Any]) -> tuple[bool, str]:
        symbol, timeframe, closes = self._closes_for_condition(condition, candle_lookup)
        period = max(2, int(self._to_float(condition.get("period"), 20)))
        if len(closes) < period:
            return False, f"indicator data unavailable for {symbol} {timeframe} SMA({period})"
        latest_close = closes[-1]
        sma_value = sum(closes[-period:]) / period
        if str(condition.get("type")) == "sma_above":
            return latest_close > sma_value, f"{symbol} {timeframe} close {latest_close:.4f} > SMA({period}) {sma_value:.4f}"
        return latest_close < sma_value, f"{symbol} {timeframe} close {latest_close:.4f} < SMA({period}) {sma_value:.4f}"

    def _evaluate_price_change_condition(self, condition: dict[str, Any], candle_lookup: dict[str, Any]) -> tuple[bool, str]:
        symbol, timeframe, closes = self._closes_for_condition(condition, candle_lookup)
        period = max(1, int(self._to_float(condition.get("period"), 5)))
        threshold = self._to_float(condition.get("value"), 1.0)
        if len(closes) <= period:
            return False, f"indicator data unavailable for {symbol} {timeframe} price change({period})"
        baseline = closes[-(period + 1)]
        latest_close = closes[-1]
        if baseline <= 0:
            return False, f"invalid baseline price for {symbol} {timeframe} change({period})"
        change_pct = ((latest_close - baseline) / baseline) * 100.0
        if str(condition.get("type")) == "price_change_pct_above":
            return change_pct > threshold, f"{symbol} {timeframe} change {change_pct:.2f}% > {threshold:.2f}% over {period} bars"
        return change_pct < threshold, f"{symbol} {timeframe} change {change_pct:.2f}% < {threshold:.2f}% over {period} bars"

    def _evaluate_volatility_condition(self, condition: dict[str, Any], candle_lookup: dict[str, Any]) -> tuple[bool, str]:
        symbol, timeframe, closes = self._closes_for_condition(condition, candle_lookup)
        period = max(2, int(self._to_float(condition.get("period"), 20)))
        threshold = self._to_float(condition.get("value"), 1.5)
        if len(closes) <= period:
            return False, f"indicator data unavailable for {symbol} {timeframe} volatility({period})"
        returns: list[float] = []
        for previous, current in zip(closes[-(period + 1):], closes[-period:], strict=True):
            if previous <= 0:
                continue
            returns.append(((current - previous) / previous) * 100.0)
        if len(returns) < period:
            return False, f"indicator data unavailable for {symbol} {timeframe} volatility({period})"
        mean = sum(returns) / len(returns)
        variance = sum((item - mean) ** 2 for item in returns) / len(returns)
        volatility = variance ** 0.5
        if str(condition.get("type")) == "volatility_above":
            return volatility > threshold, f"{symbol} {timeframe} volatility {volatility:.2f}% > {threshold:.2f}%"
        return volatility < threshold, f"{symbol} {timeframe} volatility {volatility:.2f}% < {threshold:.2f}%"

    def _evaluate_bollinger_condition(self, condition: dict[str, Any], candle_lookup: dict[str, Any]) -> tuple[bool, str]:
        symbol, timeframe, closes = self._closes_for_condition(condition, candle_lookup)
        period = max(2, int(self._to_float(condition.get("period"), 20)))
        deviation_multiplier = self._to_float(condition.get("value"), 2.0)
        if len(closes) < period:
            return False, f"indicator data unavailable for {symbol} {timeframe} Bollinger({period})"
        window = closes[-period:]
        basis = sum(window) / period
        variance = sum((item - basis) ** 2 for item in window) / period
        deviation = variance ** 0.5
        latest_close = closes[-1]
        upper_band = basis + (deviation * deviation_multiplier)
        lower_band = basis - (deviation * deviation_multiplier)
        if str(condition.get("type")) == "bollinger_above_upper":
            return latest_close > upper_band, f"{symbol} {timeframe} close {latest_close:.4f} > upper band {upper_band:.4f}"
        return latest_close < lower_band, f"{symbol} {timeframe} close {latest_close:.4f} < lower band {lower_band:.4f}"

    def _evaluate_breakout_condition(self, condition: dict[str, Any], candle_lookup: dict[str, Any]) -> tuple[bool, str]:
        symbol, timeframe, candles = self._candles_for_condition(condition, candle_lookup)
        period = max(2, int(self._to_float(condition.get("period"), 20)))
        if len(candles) <= period:
            return False, f"indicator data unavailable for {symbol} {timeframe} breakout({period})"
        latest_close = self._to_float(candles[-1].get("close"), 0.0)
        reference_window = candles[-(period + 1):-1]
        if str(condition.get("type")) == "breakout_above_recent_high":
            highest_high = max(self._to_float(item.get("high"), 0.0) for item in reference_window)
            return latest_close > highest_high, f"{symbol} {timeframe} close {latest_close:.4f} > recent high {highest_high:.4f}"
        lowest_low = min(self._to_float(item.get("low"), 0.0) for item in reference_window)
        return latest_close < lowest_low, f"{symbol} {timeframe} close {latest_close:.4f} < recent low {lowest_low:.4f}"

    def _evaluate_atr_condition(self, condition: dict[str, Any], candle_lookup: dict[str, Any]) -> tuple[bool, str]:
        symbol, timeframe, candles = self._candles_for_condition(condition, candle_lookup)
        period = max(2, int(self._to_float(condition.get("period"), 14)))
        threshold = self._to_float(condition.get("value"), 1.0)
        if len(candles) <= period:
            return False, f"indicator data unavailable for {symbol} {timeframe} ATR({period})"
        true_ranges: list[float] = []
        recent_candles = candles[-(period + 1):]
        for previous, current in zip(recent_candles, recent_candles[1:], strict=True):
            high = self._to_float(current.get("high"), 0.0)
            low = self._to_float(current.get("low"), 0.0)
            previous_close = self._to_float(previous.get("close"), 0.0)
            true_ranges.append(max(high - low, abs(high - previous_close), abs(low - previous_close)))
        if len(true_ranges) < period:
            return False, f"indicator data unavailable for {symbol} {timeframe} ATR({period})"
        atr = sum(true_ranges[-period:]) / period
        latest_close = self._to_float(candles[-1].get("close"), 0.0)
        if latest_close <= 0:
            return False, f"invalid close price for {symbol} {timeframe} ATR({period})"
        atr_pct = (atr / latest_close) * 100.0
        if str(condition.get("type")) == "atr_above":
            return atr_pct > threshold, f"{symbol} {timeframe} ATR {atr_pct:.2f}% > {threshold:.2f}%"
        return atr_pct < threshold, f"{symbol} {timeframe} ATR {atr_pct:.2f}% < {threshold:.2f}%"

    def _evaluate_vwap_condition(self, condition: dict[str, Any], candle_lookup: dict[str, Any]) -> tuple[bool, str]:
        symbol, timeframe, candles = self._candles_for_condition(condition, candle_lookup)
        period = max(2, int(self._to_float(condition.get("period"), 24)))
        if len(candles) < period:
            return False, f"indicator data unavailable for {symbol} {timeframe} VWAP({period})"
        window = candles[-period:]
        total_volume = 0.0
        weighted_value = 0.0
        for candle in window:
            high = self._to_float(candle.get("high"), 0.0)
            low = self._to_float(candle.get("low"), 0.0)
            close = self._to_float(candle.get("close"), 0.0)
            volume = self._to_float(candle.get("volume"), 0.0)
            typical_price = (high + low + close) / 3.0
            weighted_value += typical_price * volume
            total_volume += volume
        if total_volume <= 0:
            return False, f"indicator data unavailable for {symbol} {timeframe} VWAP({period})"
        vwap = weighted_value / total_volume
        latest_close = self._to_float(window[-1].get("close"), 0.0)
        if str(condition.get("type")) == "vwap_above":
            return latest_close > vwap, f"{symbol} {timeframe} close {latest_close:.4f} > VWAP {vwap:.4f}"
        return latest_close < vwap, f"{symbol} {timeframe} close {latest_close:.4f} < VWAP {vwap:.4f}"

    def _evaluate_higher_timeframe_sma_condition(self, condition: dict[str, Any], candle_lookup: dict[str, Any]) -> tuple[bool, str]:
        symbol = normalize_symbol(condition.get("symbol"))
        timeframe = normalize_timeframe(condition.get("timeframe"))
        secondary_timeframe = normalize_timeframe(condition.get("secondary_timeframe"))
        primary_candles = self._candles_for_symbol_timeframe(symbol, timeframe, candle_lookup)
        secondary_candles = self._candles_for_symbol_timeframe(symbol, secondary_timeframe, candle_lookup)
        period = max(2, int(self._to_float(condition.get("period"), 20)))
        if not primary_candles or len(secondary_candles) < period:
            return False, f"indicator data unavailable for {symbol} {timeframe}/{secondary_timeframe} MTF SMA({period})"
        latest_close = self._to_float(primary_candles[-1].get("close"), 0.0)
        htf_closes = [self._to_float(item.get("close"), 0.0) for item in secondary_candles[-period:]]
        htf_sma = sum(htf_closes) / period
        if str(condition.get("type")) == "higher_timeframe_sma_above":
            return latest_close > htf_sma, f"{symbol} {timeframe} close {latest_close:.4f} > {secondary_timeframe} SMA({period}) {htf_sma:.4f}"
        return latest_close < htf_sma, f"{symbol} {timeframe} close {latest_close:.4f} < {secondary_timeframe} SMA({period}) {htf_sma:.4f}"

    def _evaluate_ema_cross_condition(self, condition: dict[str, Any], candle_lookup: dict[str, Any]) -> tuple[bool, str]:
        symbol, timeframe, closes = self._closes_for_condition(condition, candle_lookup)
        fast_period = max(2, int(self._to_float(condition.get("fast_period"), 9)))
        slow_period = max(fast_period + 1, int(self._to_float(condition.get("slow_period"), 21)))
        fast_pair = self._latest_indicator_pair(self._ema_series(closes, fast_period))
        slow_pair = self._latest_indicator_pair(self._ema_series(closes, slow_period))
        if fast_pair is None or slow_pair is None:
            return False, f"indicator data unavailable for {symbol} {timeframe} EMA({fast_period}/{slow_period})"

        fast_previous, fast_current = fast_pair
        slow_previous, slow_current = slow_pair
        if str(condition.get("type")) == "ema_crosses_above":
            passed = fast_previous <= slow_previous and fast_current > slow_current
            return passed, (
                f"{symbol} {timeframe} EMA({fast_period}) {fast_previous:.2f}->{fast_current:.2f} crossed above "
                f"EMA({slow_period}) {slow_previous:.2f}->{slow_current:.2f}"
            )

        passed = fast_previous >= slow_previous and fast_current < slow_current
        return passed, (
            f"{symbol} {timeframe} EMA({fast_period}) {fast_previous:.2f}->{fast_current:.2f} crossed below "
            f"EMA({slow_period}) {slow_previous:.2f}->{slow_current:.2f}"
        )

    def _evaluate_macd_cross_condition(self, condition: dict[str, Any], candle_lookup: dict[str, Any]) -> tuple[bool, str]:
        symbol, timeframe, closes = self._closes_for_condition(condition, candle_lookup)
        fast_period = max(2, int(self._to_float(condition.get("fast_period"), 12)))
        slow_period = max(fast_period + 1, int(self._to_float(condition.get("slow_period"), 26)))
        signal_period = max(2, int(self._to_float(condition.get("signal_period"), 9)))
        macd_pair = self._latest_macd_pair(closes, fast_period, slow_period, signal_period)
        if macd_pair is None:
            return False, f"indicator data unavailable for {symbol} {timeframe} MACD({fast_period},{slow_period},{signal_period})"

        macd_previous, signal_previous, macd_current, signal_current = macd_pair
        if str(condition.get("type")) == "macd_crosses_above_signal":
            passed = macd_previous <= signal_previous and macd_current > signal_current
            return passed, (
                f"{symbol} {timeframe} MACD {macd_previous:.4f}->{macd_current:.4f} crossed above signal "
                f"{signal_previous:.4f}->{signal_current:.4f}"
            )

        passed = macd_previous >= signal_previous and macd_current < signal_current
        return passed, (
            f"{symbol} {timeframe} MACD {macd_previous:.4f}->{macd_current:.4f} crossed below signal "
            f"{signal_previous:.4f}->{signal_current:.4f}"
        )

    def _evaluate_position_pnl_condition(
        self,
        condition: dict[str, Any],
        position_lookup: dict[str, Any],
    ) -> tuple[bool, str]:
        symbol, unrealized_pnl, _ = self._position_snapshot(condition, position_lookup)
        if unrealized_pnl is None:
            return False, f"position unavailable for {symbol}"
        threshold = self._to_float(condition.get("value"), 0.0)
        if str(condition.get("type")) == "position_pnl_above":
            return unrealized_pnl > threshold, f"{symbol} unrealized PnL {unrealized_pnl:.2f} > {threshold:.2f}"
        return unrealized_pnl < threshold, f"{symbol} unrealized PnL {unrealized_pnl:.2f} < {threshold:.2f}"

    def _evaluate_position_pnl_pct_condition(
        self,
        condition: dict[str, Any],
        position_lookup: dict[str, Any],
    ) -> tuple[bool, str]:
        symbol, _, unrealized_pnl_pct = self._position_snapshot(condition, position_lookup)
        if unrealized_pnl_pct is None:
            return False, f"position unavailable for {symbol}"
        threshold = self._to_float(condition.get("value"), 0.0)
        if str(condition.get("type")) == "position_pnl_pct_above":
            return unrealized_pnl_pct > threshold, f"{symbol} unrealized PnL {unrealized_pnl_pct:.2f}% > {threshold:.2f}%"
        return unrealized_pnl_pct < threshold, f"{symbol} unrealized PnL {unrealized_pnl_pct:.2f}% < {threshold:.2f}%"

    def _evaluate_position_state_condition(
        self,
        condition: dict[str, Any],
        position_lookup: dict[str, Any],
    ) -> tuple[bool, str]:
        symbol, unrealized_pnl, _ = self._position_snapshot(condition, position_lookup)
        if unrealized_pnl is None:
            return False, f"position unavailable for {symbol}"
        if str(condition.get("type")) == "position_in_profit":
            return unrealized_pnl > 0, f"{symbol} unrealized PnL {unrealized_pnl:.2f} > 0"
        return unrealized_pnl < 0, f"{symbol} unrealized PnL {unrealized_pnl:.2f} < 0"

    def _position_snapshot(
        self,
        condition: dict[str, Any],
        position_lookup: dict[str, Any],
    ) -> tuple[str, float | None, float | None]:
        symbol = normalize_symbol(condition.get("symbol"))
        position = position_lookup.get(symbol) if isinstance(position_lookup, dict) else None
        if not isinstance(position, dict):
            return symbol, None, None
        if "unrealized_pnl" in position:
            unrealized_pnl = self._to_float(position.get("unrealized_pnl"), 0.0)
            pnl_pct = self._to_float(position.get("unrealized_pnl_pct"), 0.0)
            return symbol, unrealized_pnl, pnl_pct
        amount = abs(self._to_float(position.get("amount", position.get("quantity")), 0.0))
        entry_price = self._to_float(position.get("entry_price"), 0.0)
        mark_price = self._to_float(position.get("mark_price"), 0.0)
        margin = abs(self._to_float(position.get("margin"), 0.0))
        raw_side = str(position.get("side") or "").lower().strip()
        direction = 1.0 if raw_side in {"bid", "long"} else -1.0
        if amount <= 0 or entry_price <= 0 or mark_price <= 0:
            return symbol, None, None
        unrealized_pnl = (mark_price - entry_price) * amount * direction
        pnl_pct = (unrealized_pnl / margin * 100.0) if margin > 0 else 0.0
        return symbol, unrealized_pnl, pnl_pct

    @staticmethod
    def _latest_indicator_pair(values: list[float]) -> tuple[float, float] | None:
        if len(values) < 2:
            return None
        return values[-2], values[-1]

    def _latest_macd_pair(
        self,
        closes: list[float],
        fast_period: int,
        slow_period: int,
        signal_period: int,
    ) -> tuple[float, float, float, float] | None:
        fast_values = self._ema_series(closes, fast_period)
        slow_values = self._ema_series(closes, slow_period)
        if len(fast_values) != len(closes) or len(slow_values) != len(closes) or len(closes) < 2:
            return None
        macd_series = [fast - slow for fast, slow in zip(fast_values, slow_values, strict=True)]
        signal_series = self._ema_series(macd_series, signal_period)
        if len(signal_series) < 2:
            return None
        return macd_series[-2], signal_series[-2], macd_series[-1], signal_series[-1]

    @staticmethod
    def _ema_series(values: list[float], period: int) -> list[float]:
        if len(values) < period or period <= 1:
            return []
        alpha = 2.0 / (period + 1)
        ema_values: list[float] = []
        ema = values[0]
        for value in values:
            ema = (value * alpha) + (ema * (1.0 - alpha))
            ema_values.append(ema)
        return ema_values

    @staticmethod
    def _latest_rsi(values: list[float], period: int) -> float | None:
        if len(values) <= period:
            return None

        gains: list[float] = []
        losses: list[float] = []
        for previous, current in zip(values, values[1:]):
            change = current - previous
            gains.append(max(change, 0.0))
            losses.append(max(-change, 0.0))

        average_gain = sum(gains[:period]) / period
        average_loss = sum(losses[:period]) / period

        for gain, loss in zip(gains[period:], losses[period:]):
            average_gain = ((average_gain * (period - 1)) + gain) / period
            average_loss = ((average_loss * (period - 1)) + loss) / period

        if average_loss == 0:
            return 100.0
        relative_strength = average_gain / average_loss
        return 100.0 - (100.0 / (1.0 + relative_strength))

    @staticmethod
    def _normalize_symbol(value: Any) -> str:
        return normalize_symbol(value)

    @staticmethod
    def _to_float(value: Any, default: float) -> float:
        try:
            if value is None or value == "":
                return default
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _to_bool(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "y"}
        return bool(value)

    @classmethod
    def _position_value(cls, position: Any, axis: str) -> float:
        if not isinstance(position, dict):
            return 1_000_000_000.0
        return cls._to_float(position.get(axis), 1_000_000_000.0)
