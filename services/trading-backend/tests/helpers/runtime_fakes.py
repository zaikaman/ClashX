from __future__ import annotations

from copy import deepcopy
from typing import Any


class FakeSupabaseRestClient:
    def __init__(self, tables: dict[str, list[dict[str, Any]]] | None = None) -> None:
        self.tables: dict[str, list[dict[str, Any]]] = {
            "users": [],
            "audit_events": [],
            **({name: [deepcopy(row) for row in rows] for name, rows in (tables or {}).items()}),
        }

    def select(
        self,
        table: str,
        *,
        columns: str = "*",
        filters: dict[str, Any] | None = None,
        order: str | None = None,
        limit: int | None = None,
        cache_ttl_seconds: float | None = None,
    ) -> list[dict[str, Any]]:
        del columns, cache_ttl_seconds
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
        cache_ttl_seconds: float | None = None,
    ) -> dict[str, Any] | None:
        rows = self.select(
            table,
            columns=columns,
            filters=filters,
            order=order,
            limit=1,
            cache_ttl_seconds=cache_ttl_seconds,
        )
        return rows[0] if rows else None

    def insert(
        self,
        table: str,
        payload: dict[str, Any] | list[dict[str, Any]],
        *,
        upsert: bool = False,
        on_conflict: str | None = None,
        returning: str = "representation",
    ) -> list[dict[str, Any]]:
        del upsert, on_conflict, returning
        items = payload if isinstance(payload, list) else [payload]
        stored = [deepcopy(item) for item in items]
        self.tables.setdefault(table, []).extend(stored)
        return [deepcopy(item) for item in stored]

    def update(
        self,
        table: str,
        values: dict[str, Any],
        *,
        filters: dict[str, Any],
    ) -> list[dict[str, Any]]:
        rows = self.tables.get(table, [])
        updated: list[dict[str, Any]] = []
        for row in rows:
            if self._matches(row, filters):
                row.update(deepcopy(values))
                updated.append(deepcopy(row))
        return updated

    def delete(
        self,
        table: str,
        *,
        filters: dict[str, Any],
    ) -> list[dict[str, Any]]:
        rows = self.tables.get(table, [])
        kept: list[dict[str, Any]] = []
        deleted: list[dict[str, Any]] = []
        for row in rows:
            if self._matches(row, filters):
                deleted.append(deepcopy(row))
            else:
                kept.append(row)
        self.tables[table] = kept
        return deleted

    @staticmethod
    def _matches(row: dict[str, Any], filters: dict[str, Any] | None) -> bool:
        if not filters:
            return True
        return all(row.get(key) == expected for key, expected in filters.items())


class FakeAuthService:
    def __init__(self, active_wallets: set[str] | None = None) -> None:
        self.active_wallets = active_wallets or {"wallet-1"}

    def get_authorization_by_wallet(self, db: Any, wallet_address: str) -> dict[str, str] | None:
        del db
        if wallet_address not in self.active_wallets:
            return None
        return {
            "agent_wallet_address": "agent-1",
            "status": "active",
        }

    def get_trading_credentials(self, db: Any, wallet_address: str) -> dict[str, str] | None:
        del db
        if wallet_address not in self.active_wallets:
            return None
        return {
            "account_address": wallet_address,
            "agent_wallet_address": "agent-1",
            "agent_private_key": "secret",
        }


class FakePacificaClient:
    def __init__(self) -> None:
        self.order_calls: list[dict[str, Any]] = []
        self.batch_order_calls: list[list[dict[str, Any]]] = []
        self._position: dict[str, Any] | None = None
        self._fills: list[dict[str, Any]] = []
        self._margin_settings: list[dict[str, Any]] = []
        self._open_orders: list[dict[str, Any]] = []
        self._positions_visible = True
        self._markets: list[dict[str, Any]] = [
            {
                "symbol": "BTC-PERP",
                "display_symbol": "BTC-PERP",
                "mark_price": 105_000.0,
                "lot_size": 0.001,
                "min_order_size": 0.001,
                "tick_size": 0.5,
                "max_leverage": 5,
            }
        ]

    async def get_account_info(self, wallet_address: str) -> dict[str, Any]:
        del wallet_address
        return {"balance": 2_000.0, "fee_level": 0}

    async def get_account_settings(self, wallet_address: str) -> list[dict[str, Any]]:
        del wallet_address
        return [deepcopy(item) for item in self._margin_settings]

    async def get_markets(self) -> list[dict[str, Any]]:
        return [deepcopy(item) for item in self._markets]

    async def get_positions(
        self,
        wallet_address: str,
        *,
        price_lookup: dict[str, float] | None = None,
    ) -> list[dict[str, Any]]:
        del wallet_address, price_lookup
        if self._position is None or not self._positions_visible:
            return []
        return [deepcopy(self._position)]

    async def get_open_orders(self, wallet_address: str) -> list[dict[str, Any]]:
        del wallet_address
        return [deepcopy(item) for item in self._open_orders]

    async def get_position_history(
        self,
        wallet_address: str,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        del wallet_address, limit, offset
        return [deepcopy(item) for item in self._fills]

    async def get_portfolio_history(
        self,
        wallet_address: str,
        *,
        limit: int = 90,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        del wallet_address, limit, offset
        return []

    async def place_order(self, payload: dict[str, Any]) -> dict[str, Any]:
        call = deepcopy(payload)
        self.order_calls.append(call)

        request_type = str(payload.get("type") or "create_market_order")
        symbol = str(payload.get("symbol") or "")
        if request_type == "create_market_order":
            amount = float(payload.get("amount") or 0)
            side = str(payload.get("side") or "")
            if payload.get("reduce_only"):
                self._open_orders = [
                    item
                    for item in self._open_orders
                    if str(item.get("symbol") or "") != symbol
                ]
                if self._position and str(self._position.get("symbol") or "") == symbol:
                    remaining = max(0.0, float(self._position.get("amount") or 0.0) - amount)
                    if remaining > 0:
                        self._position["amount"] = remaining
                        self._position["updated_at"] = "2026-03-16T00:01:00Z"
                    else:
                        self._position = None
            else:
                if self._position and str(self._position.get("symbol") or "") == symbol and str(self._position.get("side") or "") == side:
                    self._position["amount"] = float(self._position.get("amount") or 0.0) + amount
                    self._position["updated_at"] = "2026-03-16T00:01:00Z"
                else:
                    self._position = {
                        "symbol": symbol,
                        "side": side,
                        "amount": amount,
                        "entry_price": 105_000.0,
                        "mark_price": 105_000.0,
                        "margin": 105.0,
                        "isolated": True,
                        "created_at": "2026-03-16T00:00:00Z",
                        "updated_at": "2026-03-16T00:00:00Z",
                    }

        if request_type == "create_order":
            order_record = {
                "symbol": symbol,
                "order_id": len(self._open_orders) + 100,
                "client_order_id": payload.get("client_order_id"),
                "side": payload.get("side"),
                "price": payload.get("price"),
                "tick_level": payload.get("tick_level"),
                "reduce_only": bool(payload.get("reduce_only")),
                "order_type": "limit",
                "initial_amount": payload.get("amount"),
                "filled_amount": 0,
                "remaining_amount": payload.get("amount"),
            }
            self._open_orders.append(order_record)

        if request_type == "cancel_order":
            order_id = payload.get("order_id")
            client_order_id = payload.get("client_order_id")
            self._open_orders = [
                item
                for item in self._open_orders
                if not (
                    str(item.get("symbol") or "") == symbol
                    and (
                        (order_id is not None and item.get("order_id") == order_id)
                        or (
                            client_order_id is not None
                            and str(item.get("client_order_id") or "") == str(client_order_id)
                        )
                    )
                )
            ]

        if request_type == "cancel_all_orders":
            all_symbols = bool(payload.get("all_symbols", True))
            exclude_reduce_only = bool(payload.get("exclude_reduce_only", False))
            if all_symbols:
                self._open_orders = [
                    item for item in self._open_orders if exclude_reduce_only and bool(item.get("reduce_only"))
                ]
            else:
                self._open_orders = [
                    item
                    for item in self._open_orders
                    if str(item.get("symbol") or "") != symbol
                    or (exclude_reduce_only and bool(item.get("reduce_only")))
                ]

        if request_type == "set_position_tpsl":
            self._open_orders = [
                item
                for item in self._open_orders
                if str(item.get("symbol") or "") != symbol or not bool(item.get("reduce_only"))
            ]
            self._open_orders.extend(
                [
                    {
                        "symbol": symbol,
                        "reduce_only": True,
                        "kind": "take_profit",
                        "order_type": "take_profit_market",
                        "stop_price": payload.get("take_profit", {}).get("stop_price"),
                        "client_order_id": payload.get("take_profit", {}).get("client_order_id"),
                    },
                    {
                        "symbol": symbol,
                        "reduce_only": True,
                        "kind": "stop_loss",
                        "order_type": "stop_loss_market",
                        "stop_price": payload.get("stop_loss", {}).get("stop_price"),
                        "client_order_id": payload.get("stop_loss", {}).get("client_order_id"),
                    },
                ]
            )

        return {
            "status": "submitted",
            "request_id": f"req-{len(self.order_calls)}",
            "network": "testnet",
            "payload": {},
        }

    async def place_batch_orders(self, payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
        self.batch_order_calls.append([deepcopy(item) for item in payloads])
        responses: list[dict[str, Any]] = []
        for payload in payloads:
            responses.append(await self.place_order(payload))
        return responses


class FakeIndicatorContextService:
    async def load_candle_lookup(self, rules_json: dict[str, Any]) -> dict[str, Any]:
        del rules_json
        return {}


class FakeCoordinationService:
    def try_claim_action(self, *, runtime_id: str, idempotency_key: str) -> bool:
        del runtime_id, idempotency_key
        return True

    def try_claim_lease(self, lease_key: str, ttl_seconds: int) -> bool:
        del lease_key, ttl_seconds
        return True

    def release_lease(self, lease_key: str) -> None:
        del lease_key


async def noop_publish(*, channel: str, event: str, payload: dict[str, Any]) -> None:
    del channel, event, payload
