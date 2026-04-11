from datetime import UTC, datetime, timedelta
from functools import lru_cache
import uuid
from typing import Any

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, status
from privy import AuthenticationError, PrivyAPI, PrivyAPIError
from pydantic import BaseModel, Field

from src.core.settings import get_settings
from src.services.supabase_rest import SupabaseRestClient

router = APIRouter(prefix="/api/auth", tags=["auth"])
PRIVY_JWT_LEEWAY_SECONDS = 60


class PrivyVerifyRequest(BaseModel):
    wallet_address: str | None = None
    access_token: str | None = None
    session_token: str | None = None
    telegram_user_id: str | None = None


class AuthenticatedUser(BaseModel):
    user_id: str
    session_id: str | None = None
    wallet_addresses: list[str] = Field(default_factory=list)
    wallet_user_ids: dict[str, str] = Field(default_factory=dict)
    expires_at: datetime | None = None


class PrivyVerifyResponse(AuthenticatedUser):
    verified: bool = True


def _extract_bearer_token(authorization_header: str) -> str:
    if not authorization_header.startswith("Bearer "):
        return ""
    return authorization_header.removeprefix("Bearer ").strip()


def _is_likely_verification_key(value: str) -> bool:
    return value.startswith("-----BEGIN") or value.startswith("{")


@lru_cache(maxsize=1)
def _get_privy_api() -> PrivyAPI:
    settings = get_settings()
    app_id = settings.privy_app_id.strip()
    secret_or_key = settings.privy_verification_key.strip()
    if not app_id or not secret_or_key:
        raise RuntimeError("Privy credentials are not configured")
    return PrivyAPI(app_id=app_id, app_secret=None if _is_likely_verification_key(secret_or_key) else secret_or_key)


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _as_dict(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        dumped = value.model_dump()
        if isinstance(dumped, dict):
            return dumped
    if isinstance(value, dict):
        return value
    return {}


def _extract_wallet_addresses(privy_user: Any) -> list[str]:
    payload = _as_dict(privy_user)
    linked_accounts = payload.get("linked_accounts") or payload.get("linkedAccounts") or []
    addresses: list[str] = []
    for linked_account in linked_accounts:
        account = _as_dict(linked_account)
        address = account.get("address")
        account_type = account.get("type")
        chain_type = account.get("chain_type") or account.get("chainType")
        if not isinstance(address, str) or not address:
            continue
        if account_type == "wallet" or isinstance(chain_type, str):
            addresses.append(address)

    unique_addresses: list[str] = []
    seen: set[str] = set()
    for address in addresses:
        if address in seen:
            continue
        seen.add(address)
        unique_addresses.append(address)
    return unique_addresses


def _resolve_wallet_user_ids(wallet_addresses: list[str]) -> dict[str, str]:
    normalized_wallets: list[str] = []
    seen_wallets: set[str] = set()
    for wallet_address in wallet_addresses:
        normalized = str(wallet_address or "").strip()
        if not normalized or normalized in seen_wallets:
            continue
        seen_wallets.add(normalized)
        normalized_wallets.append(normalized)
    if not normalized_wallets:
        return {}

    supabase = SupabaseRestClient()
    existing_rows = supabase.select(
        "users",
        columns="id,wallet_address",
        filters={"wallet_address": ("in", normalized_wallets)},
        cache_ttl_seconds=60,
    )
    wallet_user_ids = {
        str(row.get("wallet_address") or ""): str(row.get("id") or "")
        for row in existing_rows
        if str(row.get("wallet_address") or "") and str(row.get("id") or "")
    }
    missing_wallets = [wallet for wallet in normalized_wallets if wallet not in wallet_user_ids]
    for wallet_address in missing_wallets:
        created = supabase.insert(
            "users",
            {
                "id": str(uuid.uuid4()),
                "wallet_address": wallet_address,
                "display_name": wallet_address[:8],
                "auth_provider": "privy",
                "created_at": datetime.now(tz=UTC).isoformat(),
            },
            upsert=True,
            on_conflict="wallet_address",
        )[0]
        wallet_user_ids[wallet_address] = str(created["id"])
    return wallet_user_ids


def _verify_access_token_with_leeway(client: PrivyAPI, token: str, verification_key: str | None) -> dict[str, str]:
    try:
        return client.users.verify_access_token(auth_token=token, verification_key=verification_key)
    except jwt.ImmatureSignatureError:
        resolved_verification_key = verification_key
        if not resolved_verification_key:
            resolved_verification_key = client.users._get_verification_key()
        decoded = jwt.decode(
            token,
            resolved_verification_key,
            issuer="privy.io",
            audience=client.app_id,
            algorithms=["ES256"],
            leeway=PRIVY_JWT_LEEWAY_SECONDS,
        )
        return {
            "app_id": str(decoded["aud"]),
            "user_id": str(decoded["sub"]),
            "session_id": str(decoded.get("sid") or "") or None,
            "issuer": str(decoded["iss"]),
            "issued_at": str(decoded["iat"]),
            "expiration": str(decoded["exp"]),
        }


def authenticate_bearer_token(token: str) -> AuthenticatedUser:
    settings = get_settings()
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    if not settings.privy_app_id or not settings.privy_verification_key:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Privy credentials are not configured")

    try:
        client = _get_privy_api()
        verification_key = settings.privy_verification_key if _is_likely_verification_key(settings.privy_verification_key) else None
        claims = _verify_access_token_with_leeway(client, token, verification_key)
        privy_user = client.users.get(claims["user_id"])
    except (AuthenticationError, PrivyAPIError, ValueError, jwt.PyJWTError) as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Privy access token") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    wallet_addresses = _extract_wallet_addresses(privy_user)
    return AuthenticatedUser(
        user_id=claims["user_id"],
        session_id=claims.get("session_id"),
        wallet_addresses=wallet_addresses,
        wallet_user_ids=_resolve_wallet_user_ids(wallet_addresses),
        expires_at=_parse_datetime(claims.get("expiration")),
    )


def verify_privy_session_token(session_token: str) -> bool:
    try:
        authenticate_bearer_token(session_token)
    except HTTPException:
        return False
    return True


def require_authenticated_user(request: Request) -> AuthenticatedUser:
    existing = getattr(request.state, "user", None)
    if isinstance(existing, dict) and existing.get("user_id"):
        return AuthenticatedUser.model_validate(existing)

    token = _extract_bearer_token(request.headers.get("Authorization", ""))
    user = authenticate_bearer_token(token)
    request.state.user = user.model_dump(mode="json")
    return user


def ensure_wallet_owned(user: AuthenticatedUser, wallet_address: str) -> None:
    if wallet_address not in user.wallet_addresses:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Wallet is not linked to the authenticated Privy user")


def resolve_app_user_id(user: AuthenticatedUser, wallet_address: str) -> str:
    ensure_wallet_owned(user, wallet_address)
    resolved = str(user.wallet_user_ids.get(wallet_address) or "").strip()
    if resolved:
        return resolved
    if not user.wallet_user_ids and str(user.user_id or "").strip():
        return str(user.user_id).strip()

    wallet_user_ids = _resolve_wallet_user_ids([wallet_address])
    resolved = str(wallet_user_ids.get(wallet_address) or "").strip()
    if not resolved:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Unable to resolve authenticated wallet user")
    user.wallet_user_ids[wallet_address] = resolved
    return resolved


@router.get("/me", response_model=AuthenticatedUser)
def get_authenticated_me(user: AuthenticatedUser = Depends(require_authenticated_user)) -> AuthenticatedUser:
    return user


@router.post("/privy/verify", response_model=PrivyVerifyResponse)
async def verify_privy_session(payload: PrivyVerifyRequest) -> PrivyVerifyResponse:
    token = payload.access_token or payload.session_token or ""
    user = authenticate_bearer_token(token)
    if payload.wallet_address:
        ensure_wallet_owned(user, payload.wallet_address)

    return PrivyVerifyResponse(
        verified=True,
        user_id=user.user_id,
        session_id=user.session_id,
        wallet_addresses=user.wallet_addresses,
        wallet_user_ids=user.wallet_user_ids,
        expires_at=user.expires_at or (datetime.now(tz=UTC) + timedelta(hours=1)),
    )
