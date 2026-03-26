from __future__ import annotations

from typing import Any

import httpx

from src.core.settings import get_settings
from src.services.pacifica_auth_service import PacificaAuthService
from src.services.pacifica_client import PacificaClientError, get_pacifica_client


MIN_SOL_BALANCE = 0.1
MIN_EQUITY_USD = 100.0


class PacificaReadinessService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.pacifica = get_pacifica_client()
        self.auth = PacificaAuthService()
        self._rpc_http = httpx.AsyncClient(timeout=10.0)

    async def get_readiness(self, db: Any, wallet_address: str) -> dict[str, Any]:
        sol_balance = await self._get_sol_balance(wallet_address)
        account_access, equity_usd, verification_issue = await self._get_account_access_and_equity(wallet_address)
        authorization = self.auth.get_authorization_by_wallet(db, wallet_address)
        authorization_verified = authorization is not None and authorization.get("status") == "active"
        funding_verified = sol_balance >= MIN_SOL_BALANCE and equity_usd is not None and equity_usd >= MIN_EQUITY_USD
        steps = [
            {
                "id": "funding",
                "title": "Fund the devnet wallet",
                "verified": funding_verified,
                "detail": f"Needs at least {MIN_SOL_BALANCE:g} SOL on devnet and ${MIN_EQUITY_USD:,.0f} in Pacifica equity.",
            },
            {
                "id": "app_access",
                "title": "Unlock Pacifica test app",
                "verified": account_access is True,
                "detail": "Verified through Pacifica account API access.",
            },
            {"id": "agent_authorization", "title": "Authorize ClashX agent", "verified": authorization_verified, "detail": "Verified from the active delegated agent wallet record."},
        ]
        blockers: list[str] = []
        if sol_balance < MIN_SOL_BALANCE:
            blockers.append(f"Wallet needs at least {MIN_SOL_BALANCE:g} SOL on devnet.")
        if verification_issue is not None:
            blockers.append(verification_issue)
        elif equity_usd is not None and equity_usd < MIN_EQUITY_USD:
            blockers.append(f"Pacifica equity must be at least ${MIN_EQUITY_USD:,.0f}.")
        if verification_issue is None and account_access is False:
            blockers.append("Pacifica account access is not verified yet.")
        if not authorization_verified:
            blockers.append("Authorize the ClashX agent wallet before deploying.")
        return {
            "wallet_address": wallet_address,
            "ready": len(blockers) == 0,
            "blockers": blockers,
            "metrics": {
                "sol_balance": sol_balance,
                "min_sol_balance": MIN_SOL_BALANCE,
                "equity_usd": equity_usd,
                "min_equity_usd": MIN_EQUITY_USD,
                "agent_wallet_address": authorization.get("agent_wallet_address") if authorization else None,
                "authorization_status": authorization.get("status") if authorization else "inactive",
                "builder_code": authorization.get("builder_code") if authorization else None,
            },
            "steps": steps,
        }

    async def require_ready(self, db: Any, wallet_address: str) -> dict[str, Any]:
        readiness = await self.get_readiness(db, wallet_address)
        if not readiness["ready"]:
            raise ValueError("; ".join(readiness["blockers"]))
        return readiness

    async def _get_sol_balance(self, wallet_address: str) -> float:
        payload = {"jsonrpc": "2.0", "id": 1, "method": "getBalance", "params": [wallet_address, {"commitment": "confirmed"}]}
        response = await self._rpc_http.post(self.settings.pacifica_solana_rpc_url, json=payload)
        response.raise_for_status()
        result = response.json().get("result", {})
        lamports = int(result.get("value", 0) or 0)
        return lamports / 1_000_000_000

    async def _verify_account_access(self, wallet_address: str) -> bool:
        try:
            response = await self.pacifica._http.get(  # noqa: SLF001
                f"{self.settings.pacifica_rest_url}/account",
                params={"account": wallet_address},
                headers={"Accept": "*/*"},
            )
            if response.status_code in {401, 403, 404}:
                return False
            response.raise_for_status()
            payload = self.pacifica._extract_response_payload(response.json())  # noqa: SLF001
            return isinstance(payload, dict)
        except (httpx.HTTPError, PacificaClientError, ValueError):
            return False

    async def _get_account_access_and_equity(self, wallet_address: str) -> tuple[bool | None, float | None, str | None]:
        try:
            account_info = await self.pacifica.get_account_info(wallet_address)
        except PacificaClientError as exc:
            if exc.status_code in {401, 403, 404}:
                return False, 0.0, None
            return None, None, self._verification_issue_message(exc)

        equity = float(account_info.get("equity", account_info.get("balance", 0)) or 0)
        if equity > 0:
            return True, equity, None
        resolved_equity, verification_issue = await self._get_equity_usd(wallet_address)
        return True, resolved_equity, verification_issue

    async def _get_equity_usd(self, wallet_address: str) -> tuple[float | None, str | None]:
        try:
            portfolio = await self.pacifica.get_portfolio_history(wallet_address, limit=30, offset=0)
        except PacificaClientError as exc:
            if exc.status_code not in {401, 403, 404}:
                return None, self._verification_issue_message(exc)
            portfolio = []
        if portfolio:
            latest = portfolio[-1]
            return float(latest.get("equity", 0) or 0), None
        try:
            account_info = await self.pacifica.get_account_info(wallet_address)
        except PacificaClientError as exc:
            if exc.status_code in {401, 403, 404}:
                return 0.0, None
            return None, self._verification_issue_message(exc)
        return float(account_info.get("equity", account_info.get("balance", 0)) or 0), None

    @staticmethod
    def _verification_issue_message(exc: PacificaClientError) -> str:
        if exc.status_code == 429:
            return "Pacifica readiness could not be verified right now because the Pacifica API is rate-limiting requests."
        if exc.status_code is not None and exc.status_code >= 500:
            return "Pacifica readiness could not be verified right now because the Pacifica API is unavailable."
        return "Pacifica readiness could not be verified right now."
