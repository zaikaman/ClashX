from __future__ import annotations

import asyncio
from typing import Any

from src.services.bot_builder_service import BotBuilderService
from src.services.builder_catalog_service import BuilderCatalogService
from src.services.rules_engine import RulesEngine


class _FakePacificaClient:
    async def get_markets(self) -> list[dict[str, Any]]:
        return [
            {
                "symbol": "ETH-PERP",
                "display_symbol": "ETH",
                "mark_price": 4200,
                "funding_rate": 0.0001,
                "volume_24h": 1200000,
                "updated_at": "2026-03-13T12:00:00Z",
            }
        ]

    async def get_kline(
        self,
        symbol: str,
        *,
        interval: str = "15m",
        start_time: int,
        end_time: int | None = None,
    ) -> list[dict[str, Any]]:
        closes = [100, 97, 94, 91, 88, 91, 91, 94, 91, 91, 95]
        return [
            {
                "symbol": symbol,
                "interval": interval,
                "open_time": index,
                "close_time": index + 1,
                "open": close,
                "high": close,
                "low": close,
                "close": close,
                "volume": 1,
                "trade_count": 1,
            }
            for index, close in enumerate(closes)
        ]

    async def get_mark_kline(
        self,
        symbol: str,
        *,
        interval: str = "15m",
        start_time: int,
        end_time: int | None = None,
    ) -> list[dict[str, Any]]:
        return await self.get_kline(
            symbol,
            interval=interval,
            start_time=start_time,
            end_time=end_time,
        )


def _graph_rules(symbol: str = "ETH") -> dict[str, Any]:
    return {
        "graph": {
            "version": 1,
            "entry": "builder-entry",
            "nodes": [
                {"id": "builder-entry", "kind": "entry", "position": {"x": 0, "y": 0}},
                {
                    "id": "condition-price",
                    "kind": "condition",
                    "position": {"x": 180, "y": 100},
                    "config": {"type": "price_above", "symbol": symbol, "value": 4000},
                },
                {
                    "id": "action-open",
                    "kind": "action",
                    "position": {"x": 380, "y": 100},
                    "config": {"type": "open_long", "symbol": symbol, "size_usd": 250, "leverage": 3},
                },
            ],
            "edges": [
                {"id": "edge-entry-condition", "source": "builder-entry", "target": "condition-price"},
                {"id": "edge-condition-action", "source": "condition-price", "target": "action-open"},
            ],
        }
    }


def test_visual_validation_accepts_graph_without_flat_arrays() -> None:
    service = BotBuilderService(rules_engine=RulesEngine())

    issues = service.validate_definition(
        authoring_mode="visual",
        visibility="private",
        rules_version=1,
        rules_json=_graph_rules(),
    )

    assert issues == []


def test_visual_validation_rejects_graph_without_reachable_action() -> None:
    service = BotBuilderService(rules_engine=RulesEngine())
    rules_json = _graph_rules()
    rules_json["graph"]["nodes"] = rules_json["graph"]["nodes"][:-1]
    rules_json["graph"]["edges"] = rules_json["graph"]["edges"][:-1]

    issues = service.validate_definition(
        authoring_mode="visual",
        visibility="private",
        rules_version=1,
        rules_json=rules_json,
    )

    assert "visual bots require at least one reachable action block" in issues


def test_simulate_uses_graph_symbols_and_condition_count() -> None:
    service = BuilderCatalogService(
        pacifica_client=_FakePacificaClient(),
        rules_engine=RulesEngine(),
    )

    result = asyncio.run(service.simulate(_graph_rules()))

    assert result["valid"] is True
    assert result["triggered"] is True
    assert result["evaluated_conditions"] == 1
    assert result["planned_actions"] == 1
    assert result["market_context"]["selected_symbols"] == ["ETH"]


def test_simulate_supports_indicator_conditions_with_loaded_candles() -> None:
    service = BuilderCatalogService(
        pacifica_client=_FakePacificaClient(),
        rules_engine=RulesEngine(),
    )

    indicator_rules = {
        "graph": {
            "version": 1,
            "entry": "builder-entry",
            "nodes": [
                {"id": "builder-entry", "kind": "entry", "position": {"x": 0, "y": 0}},
                {
                    "id": "condition-rsi",
                    "kind": "condition",
                    "position": {"x": 180, "y": 100},
                    "config": {"type": "rsi_above", "symbol": "ETH", "timeframe": "15m", "period": 5, "value": 50},
                },
                {
                    "id": "action-open",
                    "kind": "action",
                    "position": {"x": 380, "y": 100},
                    "config": {"type": "open_long", "symbol": "ETH", "size_usd": 250, "leverage": 3},
                },
            ],
            "edges": [
                {"id": "edge-entry-condition", "source": "builder-entry", "target": "condition-rsi"},
                {"id": "edge-condition-action", "source": "condition-rsi", "target": "action-open"},
            ],
        }
    }

    result = asyncio.run(service.simulate(indicator_rules))

    assert result["valid"] is True
    assert result["triggered"] is True
    assert result["evaluated_conditions"] == 1
    assert result["planned_actions"] == 1
    assert "ETH" in result["market_context"]["candle_lookup"]
