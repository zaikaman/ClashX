from __future__ import annotations

from src.services.rules_engine import RulesEngine


def _build_graph_rules() -> dict:
    return {
        "graph": {
            "version": 1,
            "entry": "builder-entry",
            "nodes": [
                {"id": "builder-entry", "kind": "entry", "position": {"x": 0, "y": 0}},
                {
                    "id": "condition-breakout",
                    "kind": "condition",
                    "position": {"x": 200, "y": 80},
                    "config": {"type": "price_above", "symbol": "BTC", "value": 100000},
                },
                {
                    "id": "action-open-long",
                    "kind": "action",
                    "position": {"x": 420, "y": 80},
                    "config": {"type": "open_long", "symbol": "BTC", "size_usd": 150, "leverage": 3},
                },
                {
                    "id": "condition-cooldown",
                    "kind": "condition",
                    "position": {"x": 200, "y": 260},
                    "config": {"type": "cooldown_elapsed", "symbol": "BTC", "seconds": 60},
                },
                {
                    "id": "action-leverage",
                    "kind": "action",
                    "position": {"x": 420, "y": 260},
                    "config": {"type": "update_leverage", "symbol": "BTC", "leverage": 5},
                },
            ],
            "edges": [
                {"id": "edge-entry-breakout", "source": "builder-entry", "target": "condition-breakout"},
                {"id": "edge-breakout-action", "source": "condition-breakout", "target": "action-open-long"},
                {"id": "edge-entry-cooldown", "source": "builder-entry", "target": "condition-cooldown"},
                {"id": "edge-cooldown-action", "source": "condition-cooldown", "target": "action-leverage"},
            ],
        }
    }


def test_graph_execution_takes_precedence_over_flat_primary_route() -> None:
    engine = RulesEngine()
    rules_json = {
        "conditions": [{"type": "price_above", "symbol": "BTC", "value": 100000}],
        "actions": [{"type": "open_long", "symbol": "BTC", "size_usd": 150, "leverage": 3}],
        **_build_graph_rules(),
    }

    result = engine.evaluate(
        rules_json=rules_json,
        context={
            "market_lookup": {"BTC": {"mark_price": 105000}},
            "position_lookup": {},
            "runtime": {"state": {}},
        },
    )

    assert result["triggered"] is True
    assert result["evaluated_conditions"] == 2
    assert [action["type"] for action in result["actions"]] == ["open_long", "update_leverage"]
    assert any("condition-breakout" in reason for reason in result["reasons"])
    assert any("condition-cooldown" in reason for reason in result["reasons"])


def test_graph_execution_skips_failed_branch_and_keeps_passing_branch() -> None:
    engine = RulesEngine()
    rules_json = {
        "graph": {
            "version": 1,
            "entry": "builder-entry",
            "nodes": [
                {"id": "builder-entry", "kind": "entry", "position": {"x": 0, "y": 0}},
                {
                    "id": "condition-breakout",
                    "kind": "condition",
                    "position": {"x": 160, "y": 60},
                    "config": {"type": "price_above", "symbol": "BTC", "value": 100000},
                },
                {
                    "id": "action-open-long",
                    "kind": "action",
                    "position": {"x": 360, "y": 60},
                    "config": {"type": "open_long", "symbol": "BTC", "size_usd": 150, "leverage": 3},
                },
                {
                    "id": "condition-position",
                    "kind": "condition",
                    "position": {"x": 160, "y": 240},
                    "config": {"type": "has_position", "symbol": "ETH"},
                },
                {
                    "id": "action-close",
                    "kind": "action",
                    "position": {"x": 360, "y": 240},
                    "config": {"type": "close_position", "symbol": "ETH"},
                },
            ],
            "edges": [
                {"id": "edge-entry-breakout", "source": "builder-entry", "target": "condition-breakout"},
                {"id": "edge-breakout-action", "source": "condition-breakout", "target": "action-open-long"},
                {"id": "edge-entry-position", "source": "builder-entry", "target": "condition-position"},
                {"id": "edge-position-action", "source": "condition-position", "target": "action-close"},
            ],
        }
    }

    result = engine.evaluate(
        rules_json=rules_json,
        context={
            "market_lookup": {"BTC": {"mark_price": 105000}},
            "position_lookup": {},
            "runtime": {"state": {}},
        },
    )

    assert result["triggered"] is True
    assert result["evaluated_conditions"] == 2
    assert [action["type"] for action in result["actions"]] == ["open_long"]
    assert any("condition-position" in reason and "False" in reason for reason in result["reasons"])


def test_indicator_conditions_use_candle_context_for_rsi_and_ema_cross() -> None:
    engine = RulesEngine()
    rules_json = {
        "graph": {
            "version": 1,
            "entry": "builder-entry",
            "nodes": [
                {"id": "builder-entry", "kind": "entry", "position": {"x": 0, "y": 0}},
                {
                    "id": "condition-rsi",
                    "kind": "condition",
                    "position": {"x": 160, "y": 60},
                    "config": {"type": "rsi_above", "symbol": "BTC", "timeframe": "15m", "period": 5, "value": 50},
                },
                {
                    "id": "condition-ema",
                    "kind": "condition",
                    "position": {"x": 360, "y": 60},
                    "config": {"type": "ema_crosses_above", "symbol": "BTC", "timeframe": "15m", "fast_period": 3, "slow_period": 5},
                },
                {
                    "id": "action-open-long",
                    "kind": "action",
                    "position": {"x": 560, "y": 60},
                    "config": {"type": "open_long", "symbol": "BTC", "size_usd": 150, "leverage": 3},
                },
            ],
            "edges": [
                {"id": "edge-entry-rsi", "source": "builder-entry", "target": "condition-rsi"},
                {"id": "edge-rsi-ema", "source": "condition-rsi", "target": "condition-ema"},
                {"id": "edge-ema-action", "source": "condition-ema", "target": "action-open-long"},
            ],
        }
    }

    closes = [100, 97, 94, 91, 88, 91, 91, 94, 91, 91, 95]
    candle_lookup = {
        "BTC": {
            "15m": [
                {"close": close, "open_time": index, "close_time": index + 1}
                for index, close in enumerate(closes)
            ]
        }
    }

    result = engine.evaluate(
        rules_json=rules_json,
        context={
            "market_lookup": {"BTC": {"mark_price": 101}},
            "candle_lookup": candle_lookup,
            "position_lookup": {},
            "runtime": {"state": {}},
        },
    )

    assert result["triggered"] is True
    assert result["evaluated_conditions"] == 2
    assert [action["type"] for action in result["actions"]] == ["open_long"]
    assert any("RSI" in reason for reason in result["reasons"])
    assert any("crossed above" in reason for reason in result["reasons"])
