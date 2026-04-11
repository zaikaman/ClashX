from __future__ import annotations

import asyncio
from copy import deepcopy
from typing import Any

import pytest

from src.services.portfolio_allocator_service import PortfolioAllocatorService
from tests.helpers.runtime_fakes import FakeAuthService


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

    def delete(self, table: str, *, filters: dict[str, Any]) -> list[dict[str, Any]]:
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
        for key, expected in filters.items():
            value = row.get(key)
            if isinstance(expected, tuple):
                operator, operand = expected
                if operator == "in":
                    if value not in operand:
                        return False
                    continue
                if operator != "eq" or value != operand:
                    return False
                continue
            if value != expected:
                return False
        return True


def test_create_portfolio_rejects_self_owned_runtime_before_persist() -> None:
    service = PortfolioAllocatorService()
    service.supabase = FakeSupabaseRestClient(
        {
            "bot_runtimes": [
                {
                    "id": "runtime-self",
                    "bot_definition_id": "bot-self",
                    "wallet_address": "wallet-1",
                    "risk_policy_json": {"allocated_capital_usd": 1_000},
                }
            ],
            "bot_definitions": [
                {
                    "id": "bot-self",
                    "visibility": "public",
                }
            ],
            "portfolio_baskets": [],
            "portfolio_risk_policies": [],
            "portfolio_allocation_members": [],
            "portfolio_rebalance_events": [],
        }
    )
    service.auth_service = FakeAuthService(active_wallets={"wallet-1"})

    with pytest.raises(ValueError, match="You cannot add your own runtime to a portfolio basket"):
        asyncio.run(
            service.create_portfolio(
                owner_user_id="user-1",
                wallet_address="wallet-1",
                name="Self Basket",
                description="",
                rebalance_mode="drift",
                rebalance_interval_minutes=60,
                drift_threshold_pct=6,
                target_notional_usd=1_000,
                members=[
                    {
                        "source_runtime_id": "runtime-self",
                        "target_weight_pct": 100,
                        "max_scale_bps": 20_000,
                    }
                ],
                risk_policy=None,
                activate_on_create=True,
            )
        )

    assert service.supabase.tables["portfolio_baskets"] == []
    assert service.supabase.tables["portfolio_risk_policies"] == []
    assert service.supabase.tables["portfolio_allocation_members"] == []
    assert service.supabase.tables["portfolio_rebalance_events"] == []
