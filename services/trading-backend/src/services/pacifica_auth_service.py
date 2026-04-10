from __future__ import annotations

import uuid
from datetime import UTC, datetime
from time import time
from typing import Any

import httpx
from cryptography.fernet import Fernet

from src.core.settings import get_settings
from src.services.pacifica_signing import prepare_message
from src.services.supabase_rest import SupabaseRestClient

try:
    import base58
    from solders.keypair import Keypair
    from solders.pubkey import Pubkey
    from solders.signature import Signature
except ImportError:  # pragma: no cover
    base58 = None
    Keypair = None
    Pubkey = None
    Signature = None


class PacificaAuthService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.supabase = SupabaseRestClient()

    def get_authorization_by_wallet(self, db: Any, wallet_address: str) -> dict[str, Any] | None:
        del db
        user = self.supabase.maybe_one(
            "users",
            columns="id",
            filters={"wallet_address": wallet_address},
            cache_ttl_seconds=60,
        )
        if user is None:
            return None
        record = self.supabase.maybe_one("pacifica_authorizations", filters={"user_id": user["id"]}, cache_ttl_seconds=5)
        return self._serialize(record) if record else None

    def require_active_authorization(self, db: Any, wallet_address: str) -> dict[str, Any]:
        authorization = self.get_authorization_by_wallet(db, wallet_address)
        if authorization is None or authorization["status"] != "active":
            raise ValueError("Authorize a delegated Pacifica agent wallet in the Agent Desk before trading.")
        return authorization

    def get_trading_credentials(self, db: Any, wallet_address: str) -> dict[str, str] | None:
        del db
        user = self.supabase.maybe_one(
            "users",
            columns="id",
            filters={"wallet_address": wallet_address},
            cache_ttl_seconds=60,
        )
        if user is None:
            return None
        record = self.supabase.maybe_one("pacifica_authorizations", filters={"user_id": user["id"]}, cache_ttl_seconds=5)
        if record is None or record["status"] != "active":
            return None
        return {
            "account_address": record["account_address"],
            "agent_wallet_address": record["agent_wallet_address"],
            "agent_private_key": self._decrypt_private_key(record["encrypted_agent_private_key"]),
        }

    def start_authorization(self, db: Any, *, wallet_address: str, display_name: str | None, force_reissue: bool = False) -> dict[str, Any]:
        del db
        self._ensure_crypto_runtime()
        user = self._upsert_user(wallet_address=wallet_address, display_name=display_name)
        existing = self.supabase.maybe_one("pacifica_authorizations", filters={"user_id": user["id"]})
        if existing is not None and existing["status"] == "active" and not force_reissue:
            return self._serialize(existing)
        agent_keypair = Keypair()
        agent_private_key = base58.b58encode(bytes(agent_keypair)).decode("ascii")
        agent_wallet_address = str(agent_keypair.pubkey())
        builder_draft = self._create_draft(
            "approve_builder_code",
            {"builder_code": self.settings.pacifica_builder_code, "max_fee_rate": self.settings.pacifica_builder_max_fee_rate},
        ) if self.settings.pacifica_builder_code else None
        bind_draft = self._create_draft("bind_agent_wallet", {"agent_wallet": agent_wallet_address})
        now_iso = datetime.now(tz=UTC).isoformat()
        record = self.supabase.insert(
            "pacifica_authorizations",
            {
                "id": existing["id"] if existing else str(uuid.uuid4()),
                "user_id": user["id"],
                "account_address": wallet_address,
                "agent_wallet_address": agent_wallet_address,
                "encrypted_agent_private_key": self._encrypt_private_key(agent_private_key),
                "builder_code": self.settings.pacifica_builder_code or None,
                "max_fee_rate": self.settings.pacifica_builder_max_fee_rate,
                "status": "draft",
                "builder_approval_message": builder_draft["message"] if builder_draft else None,
                "builder_approval_timestamp": builder_draft["timestamp"] if builder_draft else None,
                "builder_approval_expiry_window": builder_draft["expiry_window"] if builder_draft else None,
                "builder_approval_signature": None,
                "builder_approved_at": None,
                "bind_agent_message": bind_draft["message"],
                "bind_agent_timestamp": bind_draft["timestamp"],
                "bind_agent_expiry_window": bind_draft["expiry_window"],
                "bind_agent_signature": None,
                "agent_bound_at": None,
                "last_error": None,
                "created_at": existing.get("created_at", now_iso) if existing else now_iso,
                "updated_at": now_iso,
            },
            upsert=True,
            on_conflict="user_id",
        )[0]
        return self._serialize(record, include_drafts=True)

    def activate_authorization(
        self,
        db: Any,
        *,
        authorization_id: str,
        bind_agent_signature: str,
        builder_approval_signature: str | None = None,
    ) -> dict[str, Any]:
        del db
        record = self.supabase.maybe_one("pacifica_authorizations", filters={"id": authorization_id})
        if record is None:
            raise ValueError("Pacifica authorization record not found")
        if record["status"] == "active":
            return self._serialize(record)
        current = dict(record)
        if current["builder_code"] and not current.get("builder_approved_at"):
            if not builder_approval_signature:
                raise ValueError("Builder approval signature is required")
            self._verify_wallet_signature(
                account_address=current["account_address"],
                message=current.get("builder_approval_message"),
                signature=builder_approval_signature,
            )
            self._post_to_pacifica(
                "/account/builder_codes/approve",
                {
                    "user": current["account_address"],
                    "account": current["account_address"],
                    "agent_wallet": None,
                    "signature": builder_approval_signature,
                    "timestamp": current["builder_approval_timestamp"],
                    "expiry_window": current["builder_approval_expiry_window"],
                    "builder_code": current["builder_code"],
                    "max_fee_rate": current["max_fee_rate"],
                },
            )
            current["builder_approval_signature"] = builder_approval_signature
            current["builder_approved_at"] = datetime.now(tz=UTC).isoformat()
        self._verify_wallet_signature(
            account_address=current["account_address"],
            message=current.get("bind_agent_message"),
            signature=bind_agent_signature,
        )
        try:
            self._post_to_pacifica(
                "/agent/bind",
                {
                    "account": current["account_address"],
                    "signature": bind_agent_signature,
                    "timestamp": current["bind_agent_timestamp"],
                    "expiry_window": current["bind_agent_expiry_window"],
                    "agent_wallet": current["agent_wallet_address"],
                },
            )
        except ValueError as exc:
            current["status"] = "error"
            current["last_error"] = str(exc)
            current["updated_at"] = datetime.now(tz=UTC).isoformat()
            self.supabase.update("pacifica_authorizations", current, filters={"id": current["id"]})
            raise
        current["bind_agent_signature"] = bind_agent_signature
        current["agent_bound_at"] = datetime.now(tz=UTC).isoformat()
        current["status"] = "active"
        current["last_error"] = None
        current["updated_at"] = datetime.now(tz=UTC).isoformat()
        saved = self.supabase.update("pacifica_authorizations", current, filters={"id": current["id"]})[0]
        return self._serialize(saved)

    def _upsert_user(self, *, wallet_address: str, display_name: str | None) -> dict[str, Any]:
        user = self.supabase.maybe_one(
            "users",
            filters={"wallet_address": wallet_address},
            cache_ttl_seconds=60,
        )
        if user is None:
            return self.supabase.insert(
                "users",
                {
                    "id": str(uuid.uuid4()),
                    "wallet_address": wallet_address,
                    "display_name": display_name or wallet_address[:8],
                    "auth_provider": "privy",
                    "created_at": datetime.now(tz=UTC).isoformat(),
                },
            )[0]
        if display_name and user.get("display_name") != display_name:
            return self.supabase.update("users", {"display_name": display_name}, filters={"id": user["id"]})[0]
        return user

    def _post_to_pacifica(self, path: str, payload: dict[str, Any]) -> None:
        response = httpx.post(
            f"{self.settings.pacifica_rest_url}{path}",
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=20,
        )
        try:
            body = response.json()
        except ValueError:
            body = {"detail": response.text}
        if response.is_error or body.get("success") is False:
            detail = body.get("message") or body.get("error") or body.get("detail") or response.text
            raise ValueError(f"Pacifica authorization request failed ({response.status_code}): {detail}")

    def _create_draft(self, request_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        timestamp = int(time() * 1_000)
        expiry_window = self.settings.pacifica_auth_expiry_window_ms
        header = {"timestamp": timestamp, "expiry_window": expiry_window, "type": request_type}
        message = prepare_message(header, payload)
        return {"type": request_type, "timestamp": timestamp, "expiry_window": expiry_window, "payload": payload, "message": message}

    def _serialize(self, record: dict[str, Any] | None, *, include_drafts: bool = False) -> dict[str, Any] | None:
        if record is None:
            return None
        payload = {
            "id": record["id"],
            "user_id": record["user_id"],
            "wallet_address": record["account_address"],
            "account_address": record["account_address"],
            "agent_wallet_address": record["agent_wallet_address"],
            "status": record["status"],
            "builder_code": record.get("builder_code"),
            "max_fee_rate": record.get("max_fee_rate"),
            "builder_approval_required": bool(record.get("builder_code")),
            "builder_approved_at": record.get("builder_approved_at"),
            "agent_bound_at": record.get("agent_bound_at"),
            "last_error": record.get("last_error"),
            "created_at": record.get("created_at"),
            "updated_at": record.get("updated_at"),
        }
        if include_drafts and record["status"] != "active":
            payload["builder_approval_draft"] = {
                "type": "approve_builder_code",
                "message": record.get("builder_approval_message"),
                "request_payload": {
                    "account": record["account_address"],
                    "agent_wallet": None,
                    "timestamp": record.get("builder_approval_timestamp"),
                    "expiry_window": record.get("builder_approval_expiry_window"),
                    "builder_code": record.get("builder_code"),
                    "max_fee_rate": record.get("max_fee_rate"),
                },
            } if record.get("builder_approval_message") else None
            payload["bind_agent_draft"] = {
                "type": "bind_agent_wallet",
                "message": record["bind_agent_message"],
                "request_payload": {
                    "account": record["account_address"],
                    "agent_wallet": record["agent_wallet_address"],
                    "timestamp": record["bind_agent_timestamp"],
                    "expiry_window": record["bind_agent_expiry_window"],
                },
            }
        else:
            payload["builder_approval_draft"] = None
            payload["bind_agent_draft"] = None
        return payload

    def _encrypt_private_key(self, private_key: str) -> str:
        return self._fernet().encrypt(private_key.encode("utf-8")).decode("utf-8")

    def _decrypt_private_key(self, encrypted_private_key: str) -> str:
        return self._fernet().decrypt(encrypted_private_key.encode("utf-8")).decode("utf-8")

    def _fernet(self) -> Fernet:
        configured = self.settings.pacifica_agent_encryption_key.strip()
        if not configured:
            raise ValueError("PACIFICA_AGENT_ENCRYPTION_KEY must be configured")
        return Fernet(configured.encode("utf-8"))

    def _verify_wallet_signature(self, *, account_address: str, message: str | None, signature: str) -> None:
        self._ensure_crypto_runtime()
        if Pubkey is None or Signature is None:
            raise ValueError("Pacifica signing dependencies are missing. Reinstall backend dependencies.")
        if not message:
            raise ValueError("Missing authorization message draft")
        try:
            pubkey = Pubkey.from_string(account_address)
            parsed_signature = Signature.from_string(signature)
        except Exception as exc:
            raise ValueError("Authorization signature is malformed") from exc
        if not parsed_signature.verify(pubkey, message.encode("utf-8")):
            raise ValueError("Authorization signature does not match the connected wallet")

    @staticmethod
    def _ensure_crypto_runtime() -> None:
        if base58 is None or Keypair is None:
            raise ValueError("Pacifica signing dependencies are missing. Reinstall backend dependencies.")
