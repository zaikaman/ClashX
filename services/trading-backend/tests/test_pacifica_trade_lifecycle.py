from __future__ import annotations

import asyncio
from copy import deepcopy
from typing import Any

from src.services.trading_service import TradingService
from src.workers.bot_runtime_worker import BotRuntimeWorker


class FakeSupabaseRestClient:
    def __init__(self) -> None:
        self.tables: dict[str, list[dict[str, Any]]] = {
            "users": [],
            "audit_events": [],
        }

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

    def maybe_one(
        self,
        table: str,
        *,
        columns: str = "*",
        filters: dict[str, Any] | None = None,
        order: str | None = None,
    ) -> dict[str, Any] | None:
        rows = self.select(table, columns=columns, filters=filters, order=order, limit=1)
        return rows[0] if rows else None

    def insert(
        self,
        table: str,
        payload: dict[str, Any] | list[dict[str, Any]],
        *,
        upsert: bool = False,
        on_conflict: str | None = None,
    ) -> list[dict[str, Any]]:
        del upsert, on_conflict
        items = payload if isinstance(payload, list) else [payload]
        stored = [deepcopy(item) for item in items]
        self.tables.setdefault(table, []).extend(stored)
        return [deepcopy(item) for item in stored]

    @staticmethod
    def _matches(row: dict[str, Any], filters: dict[str, Any] | None) -> bool:
        if not filters:
            return True
        return all(row.get(key) == expected for key, expected in filters.items())


class FakeAuthService:
    def get_authorization_by_wallet(self, db: Any, wallet_address: str) -> dict[str, str] | None:
        del db
        if wallet_address != "wallet-1":
            return None
        return {
            "agent_wallet_address": "agent-1",
            "status": "active",
        }

    def get_trading_credentials(self, db: Any, wallet_address: str) -> dict[str, str] | None:
        del db
        if wallet_address != "wallet-1":
            return None
        return {
            "account_address": wallet_address,
            "agent_wallet_address": "agent-1",
            "agent_private_key": "secret",
        }


class FakePacificaClient:
    def __init__(self) -> None:
        self.order_calls: list[dict[str, Any]] = []
        self._position: dict[str, Any] | None = None
        self._fills: list[dict[str, Any]] = []

    async def get_account_info(self, wallet_address: str) -> dict[str, Any]:
        del wallet_address
        return {"balance": 2_000.0, "fee_level": 0}

    async def get_markets(self) -> list[dict[str, Any]]:
        return [
            {
                "symbol": "BTC-PERP",
                "display_symbol": "BTC-PERP",
                "mark_price": 105_000.0,
                "lot_size": 0.001,
                "min_order_size": 0.001,
            }
        ]

    async def get_positions(self, wallet_address: str) -> list[dict[str, Any]]:
        del wallet_address
        if self._position is None:
            return []
        return [deepcopy(self._position)]

    async def get_open_orders(self, wallet_address: str) -> list[dict[str, Any]]:
        del wallet_address
        return []

    async def get_position_history(self, wallet_address: str, *, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        del wallet_address, limit, offset
        return [deepcopy(item) for item in self._fills]

    async def get_portfolio_history(self, wallet_address: str, *, limit: int = 90, offset: int = 0) -> list[dict[str, Any]]:
        del wallet_address, limit, offset
        return []

    async def place_order(self, payload: dict[str, Any]) -> dict[str, Any]:
        call = deepcopy(payload)
        self.order_calls.append(call)

        request_type = str(payload.get("type") or "create_market_order")
        if request_type == "create_market_order":
            amount = float(payload.get("amount") or 0)
            side = str(payload.get("side") or "")
            if payload.get("reduce_only"):
                self._fills.append(
                    {
                        "history_id": len(self._fills) + 1,
                        "symbol": str(payload.get("symbol") or ""),
                        "amount": amount,
                        "price": 105_000.0,
                        "fee": 0.0,
                        "pnl": 0.0,
                        "event_type": "close_long",
                        "is_maker": False,
                        "created_at": "2026-03-16T00:00:00Z",
                    }
                )
                self._position = None
            else:
                self._position = {
                    "symbol": str(payload.get("symbol") or ""),
                    "side": side,
                    "amount": amount,
                    "entry_price": 105_000.0,
                    "mark_price": 105_000.0,
                    "margin": 105.0,
                    "isolated": True,
                    "created_at": "2026-03-16T00:00:00Z",
                    "updated_at": "2026-03-16T00:00:00Z",
                }

        return {
            "status": "submitted",
            "request_id": f"req-{len(self.order_calls)}",
            "network": "testnet",
        }


async def _noop_publish(*, channel: str, event: str, payload: dict[str, Any]) -> None:
    del channel, event, payload


def test_trading_service_places_entry_then_reduce_only_exit(monkeypatch: Any) -> None:
    monkeypatch.setattr("src.services.trading_service.broadcaster.publish", _noop_publish)

    pacifica = FakePacificaClient()
    service = TradingService()
    service.supabase = FakeSupabaseRestClient()
    service.auth_service = FakeAuthService()
    service.pacifica = pacifica

    open_result = asyncio.run(
        service.place_order(
            None,
            wallet_address="wallet-1",
            symbol="BTC",
            side="long",
            order_type="market",
            leverage=2,
            size_usd=105.0,
        )
    )

    close_result = asyncio.run(
        service.place_order(
            None,
            wallet_address="wallet-1",
            symbol="BTC",
            side="short",
            order_type="market",
            leverage=2,
            quantity=0.002,
            reduce_only=True,
        )
    )

    assert [call.get("type", "create_market_order") for call in pacifica.order_calls] == [
        "update_leverage",
        "create_market_order",
        "create_market_order",
    ]
    assert pacifica.order_calls[1]["side"] == "bid"
    assert pacifica.order_calls[1]["amount"] == 0.002
    assert pacifica.order_calls[1]["reduce_only"] is False
    assert pacifica.order_calls[2]["side"] == "ask"
    assert pacifica.order_calls[2]["amount"] == 0.002
    assert pacifica.order_calls[2]["reduce_only"] is True
    assert open_result["snapshot"]["positions"][0]["side"] == "long"
    assert close_result["snapshot"]["positions"] == []
    assert len(service.supabase.tables["audit_events"]) == 2


def test_bot_runtime_worker_translates_open_and_close_actions_to_pacifica_payloads() -> None:
    worker = BotRuntimeWorker()
    worker._pacifica = FakePacificaClient()

    credentials = {
        "account_address": "wallet-1",
        "agent_wallet_address": "agent-1",
        "agent_private_key": "secret",
    }
    market_lookup = {
        "BTC": {
            "symbol": "BTC-PERP",
            "mark_price": 105_000.0,
            "lot_size": 0.001,
            "min_order_size": 0.001,
        }
    }

    open_result = asyncio.run(
        worker._execute_action(
            action={"type": "open_long", "symbol": "BTC", "size_usd": 105.0, "leverage": 2},
            credentials=credentials,
            market_lookup=market_lookup,
            position_lookup={},
        )
    )

    close_result = asyncio.run(
        worker._execute_action(
            action={"type": "close_position", "symbol": "BTC"},
            credentials=credentials,
            market_lookup=market_lookup,
            position_lookup={"BTC": {"symbol": "BTC", "side": "bid", "amount": 0.002}},
        )
    )

    pacifica_calls = worker._pacifica.order_calls
    assert [call.get("type", "create_market_order") for call in pacifica_calls] == [
        "update_leverage",
        "create_market_order",
        "create_market_order",
    ]
    assert pacifica_calls[1]["side"] == "bid"
    assert pacifica_calls[1]["amount"] == 0.002
    assert pacifica_calls[1]["reduce_only"] is False
    assert pacifica_calls[2]["side"] == "ask"
    assert pacifica_calls[2]["amount"] == 0.002
    assert pacifica_calls[2]["reduce_only"] is True
    assert open_result["status"] == "submitted"
    assert close_result["status"] == "submitted"
