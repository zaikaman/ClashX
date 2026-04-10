from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

import src.main as main


class _FakeMetricsStore:
    def record(self, key: str, value: float) -> None:
        del key, value

    def snapshot(self) -> dict[str, object]:
        return {}


class _FakeMarketDataService:
    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None


class _FakeWorker:
    def __init__(self) -> None:
        self.is_running = False
        self.last_iteration_at = None
        self.last_error = None

    def start(self) -> None:
        self.is_running = True

    async def stop(self) -> None:
        self.is_running = False


def _build_settings() -> SimpleNamespace:
    return SimpleNamespace(
        app_name="Test App",
        cors_allowed_origins=("https://clash-x.vercel.app",),
        pacifica_network="testnet",
        background_workers_enabled=False,
    )


def test_copilot_timeout_returns_504_with_cors_header(monkeypatch) -> None:
    monkeypatch.setattr(main, "get_settings", _build_settings)
    monkeypatch.setattr(main, "get_performance_metrics_store", lambda: _FakeMetricsStore())
    monkeypatch.setattr(main, "get_pacifica_market_data_service", lambda: _FakeMarketDataService())
    monkeypatch.setattr(main, "BotRuntimeWorker", _FakeWorker)
    monkeypatch.setattr(main, "BotCopyWorker", _FakeWorker)
    monkeypatch.setattr(main, "PortfolioAllocatorWorker", _FakeWorker)

    app = main.create_app()

    import src.api.copilot as copilot_module
    import src.middleware.auth as auth_module

    async def fake_send_message(*, user, content, conversation_id=None, wallet_address=None):
        del user, content, conversation_id, wallet_address
        raise RuntimeError("OpenAI request timed out.")

    monkeypatch.setattr(copilot_module.conversation_service, "send_message", fake_send_message)
    monkeypatch.setattr(
        auth_module,
        "authenticate_bearer_token",
        lambda token: SimpleNamespace(model_dump=lambda mode="json": {"user_id": "user-123", "wallet_addresses": ["wallet-abc"]}),
    )

    client = TestClient(app)
    response = client.post(
        "/api/copilot/chat",
        headers={
            "Origin": "https://clash-x.vercel.app",
            "Authorization": "Bearer token",
        },
        json={"content": "hello"},
    )

    assert response.status_code == 504
    assert response.headers.get("access-control-allow-origin") == "https://clash-x.vercel.app"
    assert response.json() == {"detail": "OpenAI request timed out."}
