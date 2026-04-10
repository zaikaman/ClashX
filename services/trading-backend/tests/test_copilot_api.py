from __future__ import annotations

import asyncio
from types import SimpleNamespace

from fastapi.testclient import TestClient

import src.main as main
from src.api.auth import AuthenticatedUser
from src.api.copilot import CopilotChatRequest, create_copilot_chat_job, get_copilot_chat_job


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


def test_create_copilot_chat_job_returns_queued_job(monkeypatch) -> None:
    created: dict[str, object] = {}
    launched: dict[str, object] = {}

    monkeypatch.setattr(
        "src.api.copilot.ai_job_service.create_job",
        lambda **kwargs: created.setdefault("job", {"id": "job-1", **kwargs}) or created["job"],
    )
    monkeypatch.setattr(
        "src.api.copilot.ai_job_runner.start_copilot_chat_job",
        lambda **kwargs: launched.setdefault("payload", kwargs),
    )

    response = asyncio.run(
        create_copilot_chat_job(
            CopilotChatRequest(content="Summarize my bots", conversationId="conv-1", walletAddress="wallet-abc"),
            user=AuthenticatedUser(user_id="user-1", wallet_addresses=["wallet-abc"]),
        )
    )

    assert response.id == "job-1"
    assert response.status == "queued"
    assert response.conversationId == "conv-1"
    assert created["job"]["wallet_address"] == "wallet-abc"
    assert launched["payload"]["job_id"] == "job-1"


def test_get_copilot_chat_job_scopes_to_linked_wallets(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.api.copilot.ai_job_service.get_job_for_wallets",
        lambda **kwargs: {
            "id": kwargs["job_id"],
            "job_type": "copilot_chat",
            "status": "completed",
            "conversation_id": "conv-1",
            "result_payload_json": {
                "conversationId": "conv-1",
                "conversation": {
                    "id": "conv-1",
                    "title": "Summarize my bots",
                    "walletAddress": "wallet-abc",
                    "messageCount": 2,
                    "lastMessagePreview": "Done",
                    "createdAt": "2026-04-10T00:00:00+00:00",
                    "updatedAt": "2026-04-10T00:00:01+00:00",
                    "latestMessageAt": "2026-04-10T00:00:01+00:00",
                },
                "assistantMessage": {
                    "id": "assistant-1",
                    "role": "assistant",
                    "content": "Done",
                    "toolCalls": [],
                    "followUps": [],
                    "provider": "OpenAI",
                    "createdAt": "2026-04-10T00:00:01+00:00",
                },
                "reply": "Done",
                "followUps": [],
                "toolCalls": [],
                "provider": "OpenAI",
                "usedWalletAddress": "wallet-abc",
            },
            "error_detail": None,
            "created_at": "2026-04-10T00:00:00+00:00",
            "updated_at": "2026-04-10T00:00:01+00:00",
            "completed_at": "2026-04-10T00:00:01+00:00",
        },
    )

    response = asyncio.run(
        get_copilot_chat_job(
            "job-1",
            user=AuthenticatedUser(user_id="user-1", wallet_addresses=["wallet-abc"]),
        )
    )

    assert response.id == "job-1"
    assert response.status == "completed"
    assert response.result is not None
    assert response.result.reply == "Done"
