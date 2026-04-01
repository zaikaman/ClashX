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
    background_workers_enabled: bool
    worker_instance_id: str
    supabase_url: str
    supabase_anon_key: str
    supabase_service_role_key: str
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
    pacifica_global_requests_per_second: int
    pacifica_public_requests_per_second: int
    pacifica_private_requests_per_second: int
    pacifica_write_requests_per_second: int
    pacifica_market_cache_ttl_seconds: int
    pacifica_price_cache_ttl_seconds: int
    pacifica_snapshot_cache_ttl_seconds: int
    pacifica_fast_evaluation_seconds: int
    pacifica_active_wallet_poll_seconds: int
    pacifica_warm_wallet_poll_seconds: int
    pacifica_idle_wallet_poll_seconds: int
    pacifica_recent_activity_window_seconds: int
    pacifica_performance_refresh_seconds: int
    privy_app_id: str
    privy_verification_key: str
    gemini_api_key: str
    gemini_base_url: str
    gemini_model: str
    openai_api_key: str
    openai_base_url: str
    openai_model: str


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    supabase_url = os.getenv("SUPABASE_URL", "").strip()
    supabase_service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    pacifica_network = os.getenv("PACIFICA_NETWORK", "Pacifica").strip() or "Pacifica"
    if not supabase_url or not supabase_service_role_key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required")
    workers_enabled = os.getenv("BACKGROUND_WORKERS_ENABLED", "true").strip().lower() in {"1", "true", "yes", "y"}
    worker_instance_id = os.getenv("WORKER_INSTANCE_ID", "").strip() or f"{os.getpid()}"
    return Settings(
        app_name=os.getenv("APP_NAME", "ClashX Trading Backend"),
        app_env=os.getenv("APP_ENV", "development"),
        background_workers_enabled=workers_enabled,
        worker_instance_id=worker_instance_id,
        supabase_url=supabase_url,
        supabase_anon_key=os.getenv("SUPABASE_ANON_KEY", ""),
        supabase_service_role_key=supabase_service_role_key,
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
        pacifica_global_requests_per_second=max(int(os.getenv("PACIFICA_GLOBAL_REQUESTS_PER_SECOND", "12")), 1),
        pacifica_public_requests_per_second=max(int(os.getenv("PACIFICA_PUBLIC_REQUESTS_PER_SECOND", "8")), 1),
        pacifica_private_requests_per_second=max(int(os.getenv("PACIFICA_PRIVATE_REQUESTS_PER_SECOND", "8")), 1),
        pacifica_write_requests_per_second=max(int(os.getenv("PACIFICA_WRITE_REQUESTS_PER_SECOND", "4")), 1),
        pacifica_market_cache_ttl_seconds=max(int(os.getenv("PACIFICA_MARKET_CACHE_TTL_SECONDS", "15")), 1),
        pacifica_price_cache_ttl_seconds=max(int(os.getenv("PACIFICA_PRICE_CACHE_TTL_SECONDS", "5")), 1),
        pacifica_snapshot_cache_ttl_seconds=max(int(os.getenv("PACIFICA_SNAPSHOT_CACHE_TTL_SECONDS", "8")), 1),
        pacifica_fast_evaluation_seconds=max(int(os.getenv("PACIFICA_FAST_EVALUATION_SECONDS", "5")), 1),
        pacifica_active_wallet_poll_seconds=max(int(os.getenv("PACIFICA_ACTIVE_WALLET_POLL_SECONDS", "4")), 1),
        pacifica_warm_wallet_poll_seconds=max(int(os.getenv("PACIFICA_WARM_WALLET_POLL_SECONDS", "15")), 1),
        pacifica_idle_wallet_poll_seconds=max(int(os.getenv("PACIFICA_IDLE_WALLET_POLL_SECONDS", "45")), 1),
        pacifica_recent_activity_window_seconds=max(int(os.getenv("PACIFICA_RECENT_ACTIVITY_WINDOW_SECONDS", "90")), 1),
        pacifica_performance_refresh_seconds=max(int(os.getenv("PACIFICA_PERFORMANCE_REFRESH_SECONDS", "60")), 5),
        privy_app_id=os.getenv("PRIVY_APP_ID", ""),
        privy_verification_key=os.getenv("PRIVY_VERIFICATION_KEY", ""),
        gemini_api_key=os.getenv("GEMINI_API_KEY", "").strip(),
        gemini_base_url=os.getenv("GEMINI_BASE_URL", "").strip(),
        gemini_model=os.getenv("GEMINI_MODEL", "").strip(),
        openai_api_key=os.getenv("OPENAI_API_KEY", "").strip(),
        openai_base_url=os.getenv("OPENAI_BASE_URL", "").strip(),
        openai_model=os.getenv("OPENAI_MODEL", "").strip(),
    )
