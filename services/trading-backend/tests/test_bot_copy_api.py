import asyncio

import pytest
from fastapi import HTTPException

from src.api.auth import AuthenticatedUser
from src.api.bot_copy import BotCopyRelationshipPatchRequest, bot_copy_engine, delete_bot_copy_relationship, patch_bot_copy_relationship


def test_patch_bot_copy_relationship_rejects_unowned_wallet(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        bot_copy_engine.supabase,
        "maybe_one",
        lambda table, filters=None, **_kwargs: {"id": "rel_123", "follower_wallet_address": "wallet_owner"} if table == "bot_copy_relationships" else None,
    )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            patch_bot_copy_relationship(
                "rel_123",
                BotCopyRelationshipPatchRequest(scale_bps=12_500),
                db=None,
                user=AuthenticatedUser(user_id="user_123", wallet_addresses=["wallet_other"]),
            )
        )

    assert exc_info.value.status_code == 403


def test_delete_bot_copy_relationship_requires_owned_wallet(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        bot_copy_engine.supabase,
        "maybe_one",
        lambda table, filters=None, **_kwargs: {"id": "rel_123", "follower_wallet_address": "wallet_owner"} if table == "bot_copy_relationships" else None,
    )

    called: list[str] = []

    async def _fake_stop_relationship(_db, *, relationship_id: str):
        called.append(relationship_id)
        return {
            "id": relationship_id,
            "source_runtime_id": "runtime_123",
            "source_bot_definition_id": "bot_123",
            "source_bot_name": "Source bot",
            "follower_user_id": "user_123",
            "follower_wallet_address": "wallet_owner",
            "mode": "mirror",
            "scale_bps": 10_000,
            "status": "stopped",
            "risk_ack_version": "v1",
            "confirmed_at": "2026-03-17T00:00:00+00:00",
            "updated_at": "2026-03-17T00:00:00+00:00",
            "follower_display_name": "Owner",
        }

    monkeypatch.setattr(bot_copy_engine, "stop_relationship", _fake_stop_relationship)

    payload = asyncio.run(
        delete_bot_copy_relationship(
            "rel_123",
            db=None,
            user=AuthenticatedUser(user_id="user_123", wallet_addresses=["wallet_owner"]),
        )
    )

    assert called == ["rel_123"]
    assert payload.status == "stopped"
