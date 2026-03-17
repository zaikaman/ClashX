import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv


def _find_workspace_env() -> Path | None:
    current = Path(__file__).resolve()
    for parent in current.parents:
        candidate = parent / ".env"
        if candidate.exists():
            return candidate
    return None


WORKSPACE_ENV = _find_workspace_env()
if WORKSPACE_ENV is not None:
    load_dotenv(WORKSPACE_ENV, override=True)


def _default_pacifica_rest_url(network: str) -> str:
    if network.lower().startswith("test"):
        return "https://test-api.pacifica.fi/api/v1"
    return "https://api.pacifica.fi/api/v1"


def _default_pacifica_ws_url(network: str) -> str:
    if network.lower().startswith("test"):
        return "wss://test-ws.pacifica.fi/ws"
    return "wss://ws.pacifica.fi/ws"


@dataclass(frozen=True)
class Settings:
    app_name: str
    app_env: str
    database_url: str
    supabase_url: str
    supabase_anon_key: str
    supabase_service_role_key: str
    use_supabase_api: bool
    pacifica_network: str
    pacifica_rest_url: str
    pacifica_ws_url: str
    pacifica_solana_rpc_url: str
    pacifica_account_address: str
    pacifica_private_key: str
    pacifica_agent_wallet_public_key: str
    pacifica_agent_private_key: str
    pacifica_agent_encryption_key: str
    pacifica_positions_api_url: str
    pacifica_expiry_window_ms: int
    pacifica_auth_expiry_window_ms: int
    pacifica_builder_max_fee_rate: str
    pacifica_api_key: str
    pacifica_api_secret: str
    pacifica_builder_code: str
    privy_app_id: str
    privy_verification_key: str


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    database_url = os.getenv("DATABASE_URL", "").strip()
    supabase_url = os.getenv("SUPABASE_URL", "").strip()
    supabase_service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    pacifica_network = os.getenv("PACIFICA_NETWORK", "Pacifica").strip() or "Pacifica"
    if not supabase_url or not supabase_service_role_key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required")
    return Settings(
        app_name=os.getenv("APP_NAME", "ClashX Trading Backend"),
        app_env=os.getenv("APP_ENV", "development"),
        database_url=database_url,
        supabase_url=supabase_url,
        supabase_anon_key=os.getenv("SUPABASE_ANON_KEY", ""),
        supabase_service_role_key=supabase_service_role_key,
        use_supabase_api=True,
        pacifica_network=pacifica_network,
        pacifica_rest_url=os.getenv("PACIFICA_REST_URL", "").strip() or _default_pacifica_rest_url(pacifica_network),
        pacifica_ws_url=os.getenv("PACIFICA_WS_URL", "").strip() or _default_pacifica_ws_url(pacifica_network),
        pacifica_solana_rpc_url=os.getenv("PACIFICA_SOLANA_RPC_URL", "").strip() or "https://api.devnet.solana.com",
        pacifica_account_address=os.getenv("PACIFICA_ACCOUNT_ADDRESS", "").strip(),
        pacifica_private_key=os.getenv("PACIFICA_PRIVATE_KEY", "").strip(),
        pacifica_agent_wallet_public_key=os.getenv("PACIFICA_AGENT_WALLET_PUBLIC_KEY", "").strip(),
        pacifica_agent_private_key=os.getenv("PACIFICA_AGENT_PRIVATE_KEY", "").strip(),
        pacifica_agent_encryption_key=os.getenv("PACIFICA_AGENT_ENCRYPTION_KEY", "").strip(),
        pacifica_positions_api_url=os.getenv("PACIFICA_POSITIONS_API_URL", "").strip(),
        pacifica_expiry_window_ms=max(int(os.getenv("PACIFICA_EXPIRY_WINDOW_MS", "120000")), 1000),
        pacifica_auth_expiry_window_ms=max(int(os.getenv("PACIFICA_AUTH_EXPIRY_WINDOW_MS", "120000")), 5000),
        pacifica_builder_max_fee_rate=os.getenv("PACIFICA_BUILDER_MAX_FEE_RATE", "0.001").strip() or "0.001",
        pacifica_api_key=os.getenv("PACIFICA_API_KEY", ""),
        pacifica_api_secret=os.getenv("PACIFICA_API_SECRET", ""),
        pacifica_builder_code=os.getenv("PACIFICA_BUILDER_CODE", ""),
        privy_app_id=os.getenv("PRIVY_APP_ID", ""),
        privy_verification_key=os.getenv("PRIVY_VERIFICATION_KEY", ""),
    )
