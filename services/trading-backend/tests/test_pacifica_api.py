import pytest
from fastapi import HTTPException

from src.api.auth import AuthenticatedUser
from src.api.pacifica import ActivateAuthorizationRequest, activate_authorization, pacifica_auth_service


def test_activate_authorization_uses_requested_id_across_multiple_owned_wallets(monkeypatch: pytest.MonkeyPatch) -> None:
    records = {
        "auth-wallet-a": {
            "id": "auth-wallet-a",
            "wallet_address": "wallet-A",
            "account_address": "wallet-A",
        },
        "auth-wallet-b": {
            "id": "auth-wallet-b",
            "wallet_address": "wallet-B",
            "account_address": "wallet-B",
        },
    }

    def fake_get_authorization_by_wallet(_db, wallet_address: str):
        if wallet_address == "wallet-A":
            return records["auth-wallet-a"]
        if wallet_address == "wallet-B":
            return records["auth-wallet-b"]
        return None

    activated: list[str] = []

    def fake_activate_authorization(_db, *, authorization_id: str, bind_agent_signature: str, builder_approval_signature: str | None = None):
        del bind_agent_signature, builder_approval_signature
        activated.append(authorization_id)
        return {
            "id": authorization_id,
            "user_id": "user-1",
            "wallet_address": "wallet-B",
            "account_address": "wallet-B",
            "agent_wallet_address": "agent-1",
            "status": "active",
            "builder_code": None,
            "max_fee_rate": None,
            "builder_approval_required": False,
            "builder_approved_at": None,
            "agent_bound_at": "2026-03-17T00:00:00+00:00",
            "last_error": None,
            "created_at": "2026-03-17T00:00:00+00:00",
            "updated_at": "2026-03-17T00:00:00+00:00",
            "builder_approval_draft": None,
            "bind_agent_draft": None,
        }

    monkeypatch.setattr(pacifica_auth_service, "get_authorization_by_wallet", fake_get_authorization_by_wallet)
    monkeypatch.setattr(pacifica_auth_service, "activate_authorization", fake_activate_authorization)

    response = activate_authorization(
        "auth-wallet-b",
        ActivateAuthorizationRequest(bind_agent_signature="x" * 16),
        db=None,
        user=AuthenticatedUser(user_id="user-1", wallet_addresses=["wallet-A", "wallet-B"]),
    )

    assert activated == ["auth-wallet-b"]
    assert response.id == "auth-wallet-b"
    assert response.wallet_address == "wallet-B"


def test_activate_authorization_rejects_unowned_authorization_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        pacifica_auth_service,
        "get_authorization_by_wallet",
        lambda _db, wallet_address: {"id": "auth-wallet-a", "wallet_address": wallet_address, "account_address": wallet_address}
        if wallet_address == "wallet-A"
        else None,
    )

    with pytest.raises(HTTPException) as exc_info:
        activate_authorization(
            "auth-wallet-b",
            ActivateAuthorizationRequest(bind_agent_signature="x" * 16),
            db=None,
            user=AuthenticatedUser(user_id="user-1", wallet_addresses=["wallet-A"]),
        )

    assert exc_info.value.status_code == 403
