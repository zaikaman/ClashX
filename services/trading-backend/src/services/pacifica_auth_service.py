from __future__ import annotations

import uuid
from datetime import UTC, datetime
from time import time
from typing import Any

import httpx
from cryptography.fernet import Fernet
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.settings import get_settings
from src.models.pacifica_authorization import PacificaAuthorization
from src.models.user import User
from src.services.pacifica_signing import prepare_message
from src.services.supabase_rest import SupabaseRestClient

try:
    import base58
    from solders.keypair import Keypair
    from solders.pubkey import Pubkey
    from solders.signature import Signature
except ImportError:  # pragma: no cover - surfaced when the service is used
    base58 = None
    Keypair = None
    Pubkey = None
    Signature = None


class PacificaAuthService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.supabase = SupabaseRestClient() if self.settings.use_supabase_api else None

    def get_authorization_by_wallet(self, db: Session, wallet_address: str) -> dict[str, Any] | None:
        if self.settings.use_supabase_api:
            user = self.supabase.maybe_one("users", filters={"wallet_address": wallet_address})
            if user is None:
                return None
            record = self.supabase.maybe_one("pacifica_authorizations", filters={"user_id": user["id"]})
            return self._serialize(record) if record else None

        user = db.scalar(select(User).where(User.wallet_address == wallet_address).limit(1))
        if user is None:
            return None
        record = db.scalar(select(PacificaAuthorization).where(PacificaAuthorization.user_id == user.id).limit(1))
        return self._serialize(record) if record else None

    def require_active_authorization(self, db: Session, wallet_address: str) -> dict[str, Any]:
        authorization = self.get_authorization_by_wallet(db, wallet_address)
        if authorization is None or authorization["status"] != "active":
            raise ValueError("Authorize a delegated Pacifica agent wallet in the Agent Desk before trading.")
        return authorization

    def get_trading_credentials(self, db: Session, wallet_address: str) -> dict[str, str] | None:
        if self.settings.use_supabase_api:
            user = self.supabase.maybe_one("users", filters={"wallet_address": wallet_address})
            if user is None:
                return None
            record = self.supabase.maybe_one("pacifica_authorizations", filters={"user_id": user["id"]})
            if record is None or record["status"] != "active":
                return None
            return {
                "account_address": record["account_address"],
                "agent_wallet_address": record["agent_wallet_address"],
                "agent_private_key": self._decrypt_private_key(record["encrypted_agent_private_key"]),
            }

        user = db.scalar(select(User).where(User.wallet_address == wallet_address).limit(1))
        if user is None:
            return None
        record = db.scalar(select(PacificaAuthorization).where(PacificaAuthorization.user_id == user.id).limit(1))
        if record is None or record.status != "active":
            return None
        return {
            "account_address": record.account_address,
            "agent_wallet_address": record.agent_wallet_address,
            "agent_private_key": self._decrypt_private_key(record.encrypted_agent_private_key),
        }

    def start_authorization(
        self,
        db: Session,
        *,
        wallet_address: str,
        display_name: str | None,
        force_reissue: bool = False,
    ) -> dict[str, Any]:
        self._ensure_crypto_runtime()
        user = self._upsert_user(db, wallet_address=wallet_address, display_name=display_name)
        existing = self._get_record_by_user_id(db, user_id=user["id"] if isinstance(user, dict) else user.id)
        if existing is not None and self._status(existing) == "active" and not force_reissue:
            return self._serialize(existing)

        agent_keypair = Keypair()
        agent_private_key = base58.b58encode(bytes(agent_keypair)).decode("ascii")
        agent_wallet_address = str(agent_keypair.pubkey())
        builder_draft = self._create_draft(
            "approve_builder_code",
            {
                "builder_code": self.settings.pacifica_builder_code,
                "max_fee_rate": self.settings.pacifica_builder_max_fee_rate,
            },
        ) if self.settings.pacifica_builder_code else None
        bind_draft = self._create_draft("bind_agent_wallet", {"agent_wallet": agent_wallet_address})
        now_iso = datetime.now(tz=UTC).isoformat()

        values = {
            "id": existing["id"] if isinstance(existing, dict) else existing.id if existing is not None else str(uuid.uuid4()),
            "user_id": user["id"] if isinstance(user, dict) else user.id,
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
            "created_at": existing.get("created_at", now_iso) if isinstance(existing, dict) and existing is not None else existing.created_at if existing is not None else now_iso,
            "updated_at": now_iso,
        }
        record = self._save_record(db, values)
        return self._serialize(record, include_drafts=True)

    def activate_authorization(
        self,
        db: Session,
        *,
        authorization_id: str,
        bind_agent_signature: str,
        builder_approval_signature: str | None = None,
    ) -> dict[str, Any]:
        record = self._get_record_by_id(db, authorization_id)
        if record is None:
            raise ValueError("Pacifica authorization record not found")
        if self._status(record) == "active":
            return self._serialize(record)

        current = self._as_dict(record)
        if current["builder_code"] and not current.get("builder_approved_at"):
            if not builder_approval_signature:
                raise ValueError("Builder approval signature is required")
            self._verify_wallet_signature(
                account_address=current["account_address"],
                message=current.get("builder_approval_message"),
                signature=builder_approval_signature,
            )
            approval_request = {
                "user": current["account_address"],
                "account": current["account_address"],
                "agent_wallet": None,
                "signature": builder_approval_signature,
                "timestamp": current["builder_approval_timestamp"],
                "expiry_window": current["builder_approval_expiry_window"],
                "builder_code": current["builder_code"],
                "max_fee_rate": current["max_fee_rate"],
            }
            self._post_to_pacifica("/account/builder_codes/approve", approval_request)
            current["builder_approval_signature"] = builder_approval_signature
            current["builder_approved_at"] = datetime.now(tz=UTC).isoformat()

        bind_request = {
            "account": current["account_address"],
            "signature": bind_agent_signature,
            "timestamp": current["bind_agent_timestamp"],
            "expiry_window": current["bind_agent_expiry_window"],
            "agent_wallet": current["agent_wallet_address"],
        }
        self._verify_wallet_signature(
            account_address=current["account_address"],
            message=current.get("bind_agent_message"),
            signature=bind_agent_signature,
        )
        try:
            self._post_to_pacifica("/agent/bind", bind_request)
        except ValueError as exc:
            current["status"] = "error"
            current["last_error"] = str(exc)
            current["updated_at"] = datetime.now(tz=UTC).isoformat()
            self._save_record(db, current)
            raise

        current["bind_agent_signature"] = bind_agent_signature
        current["agent_bound_at"] = datetime.now(tz=UTC).isoformat()
        current["status"] = "active"
        current["last_error"] = None
        current["updated_at"] = datetime.now(tz=UTC).isoformat()
        saved = self._save_record(db, current)
        return self._serialize(saved)

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
        return {
            "type": request_type,
            "timestamp": timestamp,
            "expiry_window": expiry_window,
            "payload": payload,
            "message": message,
        }

    def _upsert_user(self, db: Session, *, wallet_address: str, display_name: str | None) -> User | dict[str, Any]:
        if self.settings.use_supabase_api:
            user = self.supabase.maybe_one("users", filters={"wallet_address": wallet_address})
            if user is None:
                user = {
                    "id": str(uuid.uuid4()),
                    "wallet_address": wallet_address,
                    "display_name": display_name or wallet_address[:8],
                    "auth_provider": "privy",
                    "created_at": datetime.now(tz=UTC).isoformat(),
                }
                self.supabase.insert("users", user)
                return user
            if display_name and user.get("display_name") != display_name:
                return self.supabase.update("users", {"display_name": display_name}, filters={"id": user["id"]})[0]
            return user

        user = db.scalar(select(User).where(User.wallet_address == wallet_address).limit(1))
        if user is None:
            user = User(wallet_address=wallet_address, display_name=display_name or wallet_address[:8])
            db.add(user)
            db.flush()
            return user
        if display_name:
            user.display_name = display_name
            db.flush()
        return user

    def _get_record_by_user_id(self, db: Session, user_id: str) -> PacificaAuthorization | dict[str, Any] | None:
        if self.settings.use_supabase_api:
            return self.supabase.maybe_one("pacifica_authorizations", filters={"user_id": user_id})
        return db.scalar(select(PacificaAuthorization).where(PacificaAuthorization.user_id == user_id).limit(1))

    def _get_record_by_id(self, db: Session, authorization_id: str) -> PacificaAuthorization | dict[str, Any] | None:
        if self.settings.use_supabase_api:
            return self.supabase.maybe_one("pacifica_authorizations", filters={"id": authorization_id})
        return db.get(PacificaAuthorization, authorization_id)

    def _save_record(self, db: Session, values: dict[str, Any]) -> PacificaAuthorization | dict[str, Any]:
        if self.settings.use_supabase_api:
            return self.supabase.insert(
                "pacifica_authorizations",
                values,
                upsert=True,
                on_conflict="user_id",
            )[0]

        record = db.get(PacificaAuthorization, values["id"])
        if record is None:
            record = PacificaAuthorization(id=values["id"], user_id=values["user_id"], account_address=values["account_address"], agent_wallet_address=values["agent_wallet_address"], encrypted_agent_private_key=values["encrypted_agent_private_key"], bind_agent_message=values["bind_agent_message"], bind_agent_timestamp=values["bind_agent_timestamp"], bind_agent_expiry_window=values["bind_agent_expiry_window"])
            db.add(record)
        for key, value in values.items():
            if key in {"created_at", "updated_at", "builder_approved_at", "agent_bound_at"} and isinstance(value, str):
                setattr(record, key, datetime.fromisoformat(value.replace("Z", "+00:00")))
            elif hasattr(record, key):
                setattr(record, key, value)
        db.commit()
        db.refresh(record)
        return record

    def _serialize(self, record: PacificaAuthorization | dict[str, Any] | None, *, include_drafts: bool = False) -> dict[str, Any] | None:
        if record is None:
            return None
        item = self._as_dict(record)
        payload = {
            "id": item["id"],
            "user_id": item["user_id"],
            "wallet_address": item["account_address"],
            "account_address": item["account_address"],
            "agent_wallet_address": item["agent_wallet_address"],
            "status": item["status"],
            "builder_code": item.get("builder_code"),
            "max_fee_rate": item.get("max_fee_rate"),
            "builder_approval_required": bool(item.get("builder_code")),
            "builder_approved_at": item.get("builder_approved_at"),
            "agent_bound_at": item.get("agent_bound_at"),
            "last_error": item.get("last_error"),
            "created_at": item.get("created_at"),
            "updated_at": item.get("updated_at"),
        }
        if include_drafts and item["status"] != "active":
            payload["builder_approval_draft"] = {
                "type": "approve_builder_code",
                "message": item.get("builder_approval_message"),
                "request_payload": {
                    "account": item["account_address"],
                    "agent_wallet": None,
                    "timestamp": item.get("builder_approval_timestamp"),
                    "expiry_window": item.get("builder_approval_expiry_window"),
                    "builder_code": item.get("builder_code"),
                    "max_fee_rate": item.get("max_fee_rate"),
                },
            } if item.get("builder_approval_message") else None
            payload["bind_agent_draft"] = {
                "type": "bind_agent_wallet",
                "message": item["bind_agent_message"],
                "request_payload": {
                    "account": item["account_address"],
                    "agent_wallet": item["agent_wallet_address"],
                    "timestamp": item["bind_agent_timestamp"],
                    "expiry_window": item["bind_agent_expiry_window"],
                },
            }
        else:
            payload["builder_approval_draft"] = None
            payload["bind_agent_draft"] = None
        return payload

    def _status(self, record: PacificaAuthorization | dict[str, Any]) -> str:
        return record["status"] if isinstance(record, dict) else record.status

    def _as_dict(self, record: PacificaAuthorization | dict[str, Any]) -> dict[str, Any]:
        if isinstance(record, dict):
            return record
        return {
            "id": record.id,
            "user_id": record.user_id,
            "account_address": record.account_address,
            "agent_wallet_address": record.agent_wallet_address,
            "encrypted_agent_private_key": record.encrypted_agent_private_key,
            "builder_code": record.builder_code,
            "max_fee_rate": record.max_fee_rate,
            "status": record.status,
            "builder_approval_message": record.builder_approval_message,
            "builder_approval_timestamp": record.builder_approval_timestamp,
            "builder_approval_expiry_window": record.builder_approval_expiry_window,
            "builder_approval_signature": record.builder_approval_signature,
            "builder_approved_at": record.builder_approved_at,
            "bind_agent_message": record.bind_agent_message,
            "bind_agent_timestamp": record.bind_agent_timestamp,
            "bind_agent_expiry_window": record.bind_agent_expiry_window,
            "bind_agent_signature": record.bind_agent_signature,
            "agent_bound_at": record.agent_bound_at,
            "last_error": record.last_error,
            "created_at": record.created_at,
            "updated_at": record.updated_at,
        }

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
