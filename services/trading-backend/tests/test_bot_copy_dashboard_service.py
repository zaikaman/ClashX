from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from typing import Any

from src.services.bot_copy_dashboard_service import BotCopyDashboardService


class FakeSupabaseRestClient:
    def __init__(self, tables: dict[str, list[dict[str, Any]]]) -> None:
        self.tables = {name: [deepcopy(row) for row in rows] for name, rows in tables.items()}

    def select(
        self,
        table: str,
        *,
        columns: str = "*",
        filters: dict[str, Any] | None = None,
        order: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        del columns
        rows = [deepcopy(row) for row in self.tables.get(table, []) if self._matches(row, filters)]
        if order:
            field, _, direction = order.partition(".")
            rows.sort(key=lambda row: row.get(field), reverse=direction.lower() == "desc")
        if limit is not None:
            rows = rows[:limit]
        return rows

    @staticmethod
    def _matches(row: dict[str, Any], filters: dict[str, Any] | None) -> bool:
        if not filters:
            return True
        for key, expected in filters.items():
            value = row.get(key)
            if isinstance(expected, tuple):
                operator, operand = expected
                if operator == "in":
                    if value not in operand:
                        return False
                    continue
                if operator == "eq":
                    if value != operand:
                        return False
                    continue
                return False
            if value != expected:
                return False
        return True


class FakeCopyEngine:
    def __init__(self, relationships: list[dict[str, Any]]) -> None:
        self._relationships = relationships

    def list_relationships(self, _db: Any, *, follower_wallet_address: str) -> list[dict[str, Any]]:
        return [deepcopy(item) for item in self._relationships if item["follower_wallet_address"] == follower_wallet_address]


class FakePortfolioService:
    def __init__(self, portfolios: list[dict[str, Any]]) -> None:
        self._portfolios = portfolios

    def list_portfolios(self, *, wallet_address: str) -> list[dict[str, Any]]:
        return [deepcopy(item) for item in self._portfolios if item["wallet_address"] == wallet_address]


class FakeTradingService:
    def __init__(self, snapshot: dict[str, Any]) -> None:
        self._snapshot = snapshot

    async def get_account_snapshot(self, _db: Any, wallet_address: str) -> dict[str, Any]:
        assert wallet_address == self._snapshot["wallet_address"]
        return deepcopy(self._snapshot)


class FakeReadinessService:
    def __init__(self, readiness: dict[str, Any]) -> None:
        self._readiness = readiness

    async def get_readiness(self, _db: Any, wallet_address: str) -> dict[str, Any]:
        assert wallet_address == self._readiness["wallet_address"]
        return deepcopy(self._readiness)


class FakeMarketplaceService:
    def __init__(self, discover_rows: list[dict[str, Any]]) -> None:
        self._discover_rows = discover_rows

    async def discover_public_bots(self, *, limit: int = 6) -> list[dict[str, Any]]:
        return [deepcopy(item) for item in self._discover_rows[:limit]]

    async def get_runtime_profile(self, *, runtime_id: str) -> dict[str, Any]:
        raise ValueError(runtime_id)


def test_dashboard_uses_copy_only_positions_and_flags_unattributed_exposure() -> None:
    service = BotCopyDashboardService()
    service.supabase = FakeSupabaseRestClient(
        {
            "marketplace_runtime_snapshots": [
                {
                    "runtime_id": "runtime-1",
                    "detail_json": {
                        "runtime_id": "runtime-1",
                        "rank": 3,
                        "drawdown": 8.5,
                        "trust": {"trust_score": 88, "risk_grade": "A", "health": "healthy"},
                        "drift": {"status": "aligned"},
                        "creator": {"display_name": "Atlas", "creator_id": "creator-1"},
                    },
                    "row_json": {},
                }
            ],
            "bot_copy_execution_events": [
                {
                    "id": "exec-open",
                    "relationship_id": "rel-1",
                    "source_runtime_id": "runtime-1",
                    "source_event_id": "event-open",
                    "follower_wallet_address": "wallet-1",
                    "symbol": "BTC",
                    "position_side": "long",
                    "action_type": "open_long",
                    "reduce_only": False,
                    "copied_quantity": 1.0,
                    "reference_price": 100.0,
                    "notional_estimate_usd": 100.0,
                    "status": "mirrored",
                    "error_reason": None,
                    "created_at": "2026-04-12T09:00:00+00:00",
                    "updated_at": "2026-04-12T09:00:00+00:00",
                }
            ],
        }
    )
    service.copy_engine = FakeCopyEngine(
        [
            {
                "id": "rel-1",
                "source_runtime_id": "runtime-1",
                "source_bot_definition_id": "bot-1",
                "source_bot_name": "Momentum Atlas",
                "follower_user_id": "user-1",
                "follower_wallet_address": "wallet-1",
                "mode": "mirror",
                "scale_bps": 10_000,
                "status": "active",
                "risk_ack_version": "v1",
                "confirmed_at": "2026-04-11T08:00:00+00:00",
                "updated_at": "2026-04-12T09:00:00+00:00",
                "follower_display_name": "Trader",
                "max_notional_usd": None,
            }
        ]
    )
    service.portfolio_service = FakePortfolioService([])
    service.trading_service = FakeTradingService(
        {
            "wallet_address": "wallet-1",
            "positions_loaded": True,
            "positions": [
                {
                    "symbol": "BTC",
                    "side": "long",
                    "quantity": 1.0,
                    "mark_price": 120.0,
                },
                {
                    "symbol": "ETH",
                    "side": "long",
                    "quantity": 2.0,
                    "mark_price": 50.0,
                },
            ],
            "markets": [
                {"symbol": "BTC", "mark_price": 120.0},
                {"symbol": "ETH", "mark_price": 50.0},
            ],
        }
    )
    service.readiness_service = FakeReadinessService(
        {
            "wallet_address": "wallet-1",
            "ready": True,
            "blockers": [],
            "metrics": {"authorization_status": "active"},
        }
    )
    service.marketplace_service = FakeMarketplaceService(
        [
            {
                "runtime_id": "runtime-2",
                "bot_definition_id": "bot-2",
                "bot_name": "Beta Trend",
                "strategy_type": "trend",
                "rank": 7,
                "drawdown": 12.0,
                "trust": {"trust_score": 71},
                "creator": {"display_name": "Nova", "creator_id": "creator-2"},
            }
        ]
    )

    dashboard = asyncio.run(service.get_dashboard(wallet_address="wallet-1"))

    assert dashboard["summary"]["open_positions"] == 1
    assert dashboard["summary"]["copied_open_notional_usd"] == 120.0
    assert dashboard["summary"]["copied_unrealized_pnl_usd"] == 20.0
    assert dashboard["positions"][0]["symbol"] == "BTC"
    assert dashboard["follows"][0]["copied_position_count"] == 1
    assert any(alert["kind"] == "unattributed_exposure" for alert in dashboard["alerts"])
    assert dashboard["discover"][0]["bot_name"] == "Beta Trend"


def test_dashboard_tracks_realized_copy_pnl_from_mirrored_closes() -> None:
    now = datetime.now(tz=UTC)
    opened_at = (now - timedelta(days=2)).isoformat()
    closed_at = (now - timedelta(hours=6)).isoformat()
    service = BotCopyDashboardService()
    service.supabase = FakeSupabaseRestClient(
        {
            "marketplace_runtime_snapshots": [],
            "bot_copy_execution_events": [
                {
                    "id": "exec-open",
                    "relationship_id": "rel-1",
                    "source_runtime_id": "runtime-1",
                    "source_event_id": "event-open",
                    "follower_wallet_address": "wallet-1",
                    "symbol": "BTC",
                    "position_side": "long",
                    "action_type": "open_long",
                    "reduce_only": False,
                    "copied_quantity": 1.0,
                    "reference_price": 100.0,
                    "notional_estimate_usd": 100.0,
                    "status": "mirrored",
                    "error_reason": None,
                    "created_at": opened_at,
                    "updated_at": opened_at,
                },
                {
                    "id": "exec-close",
                    "relationship_id": "rel-1",
                    "source_runtime_id": "runtime-1",
                    "source_event_id": "event-close",
                    "follower_wallet_address": "wallet-1",
                    "symbol": "BTC",
                    "position_side": "long",
                    "action_type": "close_position",
                    "reduce_only": True,
                    "copied_quantity": 1.0,
                    "reference_price": 130.0,
                    "notional_estimate_usd": 130.0,
                    "status": "mirrored",
                    "error_reason": None,
                    "created_at": closed_at,
                    "updated_at": closed_at,
                },
            ],
        }
    )
    service.copy_engine = FakeCopyEngine(
        [
            {
                "id": "rel-1",
                "source_runtime_id": "runtime-1",
                "source_bot_definition_id": "bot-1",
                "source_bot_name": "Momentum Atlas",
                "follower_user_id": "user-1",
                "follower_wallet_address": "wallet-1",
                "mode": "mirror",
                "scale_bps": 10_000,
                "status": "active",
                "risk_ack_version": "v1",
                "confirmed_at": "2026-04-11T08:00:00+00:00",
                "updated_at": "2026-04-12T09:00:00+00:00",
                "follower_display_name": "Trader",
                "max_notional_usd": None,
            }
        ]
    )
    service.portfolio_service = FakePortfolioService([])
    service.trading_service = FakeTradingService(
        {
            "wallet_address": "wallet-1",
            "positions_loaded": True,
            "positions": [],
            "markets": [],
        }
    )
    service.readiness_service = FakeReadinessService(
        {
            "wallet_address": "wallet-1",
            "ready": True,
            "blockers": [],
            "metrics": {"authorization_status": "active"},
        }
    )
    service.marketplace_service = FakeMarketplaceService([])

    dashboard = asyncio.run(service.get_dashboard(wallet_address="wallet-1"))

    assert dashboard["summary"]["open_positions"] == 0
    assert dashboard["summary"]["copied_realized_pnl_usd_24h"] == 30.0
    assert dashboard["summary"]["copied_realized_pnl_usd_7d"] == 30.0


def test_dashboard_hides_stale_copy_positions_when_pacifica_reports_none_open() -> None:
    service = BotCopyDashboardService()
    service.supabase = FakeSupabaseRestClient(
        {
            "marketplace_runtime_snapshots": [],
            "bot_copy_execution_events": [
                {
                    "id": "exec-open",
                    "relationship_id": "rel-1",
                    "source_runtime_id": "runtime-1",
                    "source_event_id": "event-open",
                    "follower_wallet_address": "wallet-1",
                    "symbol": "BTC",
                    "position_side": "long",
                    "action_type": "open_long",
                    "reduce_only": False,
                    "copied_quantity": 1.0,
                    "reference_price": 100.0,
                    "notional_estimate_usd": 100.0,
                    "status": "mirrored",
                    "error_reason": None,
                    "created_at": "2026-04-12T09:00:00+00:00",
                    "updated_at": "2026-04-12T09:00:00+00:00",
                }
            ],
        }
    )
    service.copy_engine = FakeCopyEngine(
        [
            {
                "id": "rel-1",
                "source_runtime_id": "runtime-1",
                "source_bot_definition_id": "bot-1",
                "source_bot_name": "Momentum Atlas",
                "follower_user_id": "user-1",
                "follower_wallet_address": "wallet-1",
                "mode": "mirror",
                "scale_bps": 10_000,
                "status": "active",
                "risk_ack_version": "v1",
                "confirmed_at": "2026-04-11T08:00:00+00:00",
                "updated_at": "2026-04-12T09:00:00+00:00",
                "follower_display_name": "Trader",
                "max_notional_usd": None,
            }
        ]
    )
    service.portfolio_service = FakePortfolioService([])
    service.trading_service = FakeTradingService(
        {
            "wallet_address": "wallet-1",
            "positions_loaded": True,
            "positions": [],
            "markets": [{"symbol": "BTC", "mark_price": 125.0}],
        }
    )
    service.readiness_service = FakeReadinessService(
        {
            "wallet_address": "wallet-1",
            "ready": True,
            "blockers": [],
            "metrics": {"authorization_status": "active"},
        }
    )
    service.marketplace_service = FakeMarketplaceService([])

    dashboard = asyncio.run(service.get_dashboard(wallet_address="wallet-1"))

    assert dashboard["summary"]["open_positions"] == 0
    assert dashboard["summary"]["copied_open_notional_usd"] == 0.0
    assert dashboard["positions"] == []
    assert dashboard["follows"][0]["copied_position_count"] == 0
