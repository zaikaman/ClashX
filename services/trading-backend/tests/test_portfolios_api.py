from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

from src.api.auth import AuthenticatedUser
from src.api.portfolios import PortfolioCreateRequest, create_portfolio, delete_portfolio


def test_create_portfolio_uses_wallet_scoped_app_user_id(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, str] = {}

    async def fake_create_portfolio(**kwargs):
        captured["owner_user_id"] = kwargs["owner_user_id"]
        raise ValueError("stop after capture")

    monkeypatch.setattr("src.api.portfolios.portfolio_allocator_service.create_portfolio", fake_create_portfolio)

    payload = PortfolioCreateRequest(
        wallet_address="wallet-abc",
        name="Core Portfolio",
        target_notional_usd=1000,
        members=[{"source_runtime_id": "runtime-1", "target_weight_pct": 100}],
    )
    user = AuthenticatedUser(
        user_id="did:privy:abc123",
        wallet_addresses=["wallet-abc"],
        wallet_user_ids={"wallet-abc": "app-user-uuid"},
    )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(create_portfolio(payload, db=None, user=user))

    assert exc_info.value.status_code == 400
    assert captured["owner_user_id"] == "app-user-uuid"


def test_delete_portfolio_uses_wallet_scope(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, str] = {}

    async def fake_delete_portfolio(**kwargs):
        captured["portfolio_id"] = kwargs["portfolio_id"]
        captured["wallet_address"] = kwargs["wallet_address"]
        raise ValueError("stop after capture")

    monkeypatch.setattr("src.api.portfolios.portfolio_allocator_service.delete_portfolio", fake_delete_portfolio)

    user = AuthenticatedUser(
        user_id="user_123",
        wallet_addresses=["wallet-abc"],
    )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(delete_portfolio("portfolio-1", wallet_address="wallet-abc", db=None, user=user))

    assert exc_info.value.status_code == 400
    assert captured == {"portfolio_id": "portfolio-1", "wallet_address": "wallet-abc"}
