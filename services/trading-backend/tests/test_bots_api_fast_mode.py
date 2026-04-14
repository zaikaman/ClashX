from __future__ import annotations

import asyncio
from datetime import datetime, UTC
from typing import Any

from fastapi import Response

from src.api.auth import AuthenticatedUser
import src.api.bots as bots_api


class _FakeBuilderService:
    def __init__(self, definitions: list[dict[str, Any]]) -> None:
        self._definitions = definitions

    def list_bots(self, _db: Any, *, wallet_address: str) -> list[dict[str, Any]]:
        return [row for row in self._definitions if row["wallet_address"] == wallet_address]


class _FakeRuntimeEngine:
    def __init__(self, runtimes: list[dict[str, Any]]) -> None:
        self._runtimes = runtimes

    def list_runtimes_for_wallet(self, _db: Any, *, wallet_address: str, user_id: str) -> list[dict[str, Any]]:
        del user_id
        return [row for row in self._runtimes if row["wallet_address"] == wallet_address]


class _FakeSnapshotService:
    def __init__(self, snapshots_by_bot: dict[str, dict[str, Any]]) -> None:
        self._snapshots_by_bot = snapshots_by_bot

    def list_snapshots_for_wallet(self, _wallet_address: str) -> dict[str, dict[str, Any]]:
        return self._snapshots_by_bot


class _FakePerformanceService:
    def __init__(self, performance_by_runtime: dict[str, dict[str, Any]]) -> None:
        self._performance_by_runtime = performance_by_runtime

    async def get_cached_runtimes_performance_map(self, _runtimes: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        return self._performance_by_runtime



def test_list_bots_fast_mode_prefers_fresh_live_runtime_performance(monkeypatch: Any) -> None:
    wallet = "wallet-1"
    now = datetime.now(tz=UTC)

    definitions = [
        {
            "id": "bot-mmts",
            "user_id": "user-1",
            "wallet_address": wallet,
            "name": "Multi-Market Trend Scalper",
            "description": "",
            "visibility": "private",
            "market_scope": "Pacifica perpetuals",
            "strategy_type": "rules",
            "authoring_mode": "visual",
            "rules_version": 1,
            "rules_json": {},
            "created_at": now,
            "updated_at": now,
        },
        {
            "id": "bot-rsi",
            "user_id": "user-1",
            "wallet_address": wallet,
            "name": "RSI Long/Short on BTC ETH SOL",
            "description": "",
            "visibility": "private",
            "market_scope": "Pacifica perpetuals",
            "strategy_type": "rules",
            "authoring_mode": "visual",
            "rules_version": 1,
            "rules_json": {},
            "created_at": now,
            "updated_at": now,
        },
    ]

    runtimes = [
        {
            "id": "runtime-mmts",
            "bot_definition_id": "bot-mmts",
            "user_id": "user-1",
            "wallet_address": wallet,
            "status": "active",
            "mode": "live",
            "risk_policy_json": {},
            "deployed_at": now,
            "stopped_at": None,
            "updated_at": now,
        },
        {
            "id": "runtime-rsi",
            "bot_definition_id": "bot-rsi",
            "user_id": "user-1",
            "wallet_address": wallet,
            "status": "active",
            "mode": "live",
            "risk_policy_json": {},
            "deployed_at": now,
            "stopped_at": None,
            "updated_at": now,
        },
    ]

    stale_snapshot_by_bot = {
        "bot-mmts": {
            "performance_json": {
                "pnl_total": 2.0,
                "pnl_total_pct": 0.5,
                "pnl_realized": 0.0,
                "pnl_unrealized": 2.0,
                "win_streak": 1,
                "positions": [
                    {
                        "symbol": "BTC",
                        "side": "long",
                        "amount": 0.008,
                        "entry_price": 74207.45113,
                        "mark_price": 74531.62,
                        "unrealized_pnl": 2.61,
                    }
                ],
            }
        },
        "bot-rsi": {
            "performance_json": {
                "pnl_total": 18.0,
                "pnl_total_pct": 4.5,
                "pnl_realized": 18.7,
                "pnl_unrealized": -0.1,
                "win_streak": 0,
                "positions": [],
            }
        },
    }

    fresh_performance_by_runtime = {
        "runtime-mmts": {
            "pnl_total": 2.0,
            "pnl_total_pct": 0.5,
            "pnl_realized": 0.0,
            "pnl_unrealized": 0.0,
            "win_streak": 1,
            "positions": [],
        },
        "runtime-rsi": {
            "pnl_total": 18.0,
            "pnl_total_pct": 4.5,
            "pnl_realized": 18.7,
            "pnl_unrealized": -0.1,
            "win_streak": 0,
            "positions": [
                {
                    "symbol": "BTC",
                    "side": "long",
                    "amount": 0.008,
                    "entry_price": 74519.0,
                    "mark_price": 74531.62,
                    "unrealized_pnl": 0.1,
                }
            ],
        },
    }

    monkeypatch.setattr(bots_api, "bot_builder_service", _FakeBuilderService(definitions))
    monkeypatch.setattr(bots_api, "bot_runtime_engine", _FakeRuntimeEngine(runtimes))
    monkeypatch.setattr(bots_api, "bot_runtime_snapshot_service", _FakeSnapshotService(stale_snapshot_by_bot))
    monkeypatch.setattr(bots_api, "bot_performance_service", _FakePerformanceService(fresh_performance_by_runtime))

    user = AuthenticatedUser(
        user_id="user-auth",
        wallet_addresses=[wallet],
        wallet_user_ids={wallet: "user-1"},
    )

    payload = asyncio.run(
        bots_api.list_bots(
            response=Response(),
            wallet_address=wallet,
            include_performance=True,
            performance_mode="fast",
            db=None,
            user=user,
        )
    )

    by_id = {item.id: item for item in payload}
    assert by_id["bot-mmts"].performance is not None
    assert by_id["bot-rsi"].performance is not None
    assert by_id["bot-mmts"].performance.positions == []
    assert len(by_id["bot-rsi"].performance.positions) == 1
    assert by_id["bot-rsi"].performance.positions[0].symbol == "BTC"
    assert by_id["bot-rsi"].performance.positions[0].entry_price == 74519.0
