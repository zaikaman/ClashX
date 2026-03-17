from __future__ import annotations

import asyncio
from typing import Any

from src.services.pacifica_readiness_service import PacificaReadinessService


class FakePacificaClient:
    async def get_portfolio_history(self, wallet_address: str, *, limit: int = 30, offset: int = 0) -> list[dict[str, Any]]:
        del wallet_address, limit, offset
        return [{"timestamp": "2026-03-17T00:00:00Z", "equity": 125.0}]

    async def get_account_info(self, wallet_address: str) -> dict[str, Any]:
        del wallet_address
        return {"balance": 125.0, "fee_level": 0}


class FakeAuthService:
    def get_authorization_by_wallet(self, db: Any, wallet_address: str) -> dict[str, Any]:
        del db, wallet_address
        return {"status": "active", "agent_wallet_address": "agent-1", "builder_code": "builder-x"}


def test_readiness_marks_wallet_ready_when_all_checks_pass() -> None:
    service = PacificaReadinessService()
    service.pacifica = FakePacificaClient()
    service.auth = FakeAuthService()

    async def fake_sol_balance(wallet_address: str) -> float:
        del wallet_address
        return 0.2

    async def fake_account_access(wallet_address: str) -> bool:
        del wallet_address
        return True

    service._get_sol_balance = fake_sol_balance  # type: ignore[method-assign]
    service._verify_account_access = fake_account_access  # type: ignore[method-assign]

    readiness = asyncio.run(service.get_readiness(None, "wallet-1"))

    assert readiness["ready"] is True
    assert readiness["metrics"]["sol_balance"] == 0.2
    assert readiness["metrics"]["equity_usd"] == 125.0
    assert all(step["verified"] for step in readiness["steps"])


def test_readiness_returns_specific_blockers_when_checks_fail() -> None:
    service = PacificaReadinessService()
    service.pacifica = FakePacificaClient()
    service.auth = type("InactiveAuth", (), {"get_authorization_by_wallet": lambda self, db, wallet_address: None})()

    async def fake_sol_balance(wallet_address: str) -> float:
        del wallet_address
        return 0.05

    async def fake_account_state(wallet_address: str) -> tuple[bool, float]:
        del wallet_address
        return False, 80.0

    service._get_sol_balance = fake_sol_balance  # type: ignore[method-assign]
    service._get_account_access_and_equity = fake_account_state  # type: ignore[method-assign]

    readiness = asyncio.run(service.get_readiness(None, "wallet-1"))

    assert readiness["ready"] is False
    assert "Wallet needs at least 0.1 SOL on devnet." in readiness["blockers"]
    assert "Pacifica equity must be at least $100." in readiness["blockers"]
    assert "Pacifica account access is not verified yet." in readiness["blockers"]
    assert "Authorize the ClashX agent wallet before deploying." in readiness["blockers"]


def test_readiness_uses_account_equity_when_portfolio_history_is_unavailable() -> None:
    service = PacificaReadinessService()

    class AccountOnlyPacificaClient:
        async def get_portfolio_history(self, wallet_address: str, *, limit: int = 30, offset: int = 0) -> list[dict[str, Any]]:
            del wallet_address, limit, offset
            return []

        async def get_account_info(self, wallet_address: str) -> dict[str, Any]:
            del wallet_address
            return {"balance": 0.0, "equity": 990.67, "fee_level": 0}

    service.pacifica = AccountOnlyPacificaClient()
    service.auth = FakeAuthService()

    async def fake_sol_balance(wallet_address: str) -> float:
        del wallet_address
        return 0.2

    async def fake_account_access(wallet_address: str) -> bool:
        del wallet_address
        return True

    service._get_sol_balance = fake_sol_balance  # type: ignore[method-assign]
    service._verify_account_access = fake_account_access  # type: ignore[method-assign]

    readiness = asyncio.run(service.get_readiness(None, "wallet-1"))

    assert readiness["ready"] is True
    assert readiness["metrics"]["equity_usd"] == 990.67


def test_readiness_prefers_account_equity_before_portfolio_history() -> None:
    service = PacificaReadinessService()

    class AccountEquityFirstPacificaClient:
        async def get_account_info(self, wallet_address: str) -> dict[str, Any]:
            del wallet_address
            return {"balance": 0.0, "equity": 990.67, "fee_level": 0}

        async def get_portfolio_history(self, wallet_address: str, *, limit: int = 30, offset: int = 0) -> list[dict[str, Any]]:
            del wallet_address, limit, offset
            raise AssertionError("Portfolio history should not be queried when account equity is already available")

    service.pacifica = AccountEquityFirstPacificaClient()
    service.auth = FakeAuthService()

    async def fake_sol_balance(wallet_address: str) -> float:
        del wallet_address
        return 0.2

    service._get_sol_balance = fake_sol_balance  # type: ignore[method-assign]

    readiness = asyncio.run(service.get_readiness(None, "wallet-1"))

    assert readiness["ready"] is True
    assert readiness["metrics"]["equity_usd"] == 990.67
    assert readiness["steps"][1]["verified"] is True
