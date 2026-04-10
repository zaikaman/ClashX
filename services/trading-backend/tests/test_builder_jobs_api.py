from __future__ import annotations

import asyncio

from src.api.builder import (
    BuilderAiChatMessage,
    BuilderAiChatRequest,
    create_ai_chat_job,
    get_ai_chat_job,
)


def test_create_builder_ai_chat_job_returns_queued_job(monkeypatch) -> None:
    created: dict[str, object] = {}
    launched: dict[str, object] = {}

    monkeypatch.setattr(
        "src.api.builder.ai_job_service.create_job",
        lambda **kwargs: created.setdefault("job", {"id": "job-1", **kwargs}) or created["job"],
    )
    monkeypatch.setattr(
        "src.api.builder.ai_job_runner.start_builder_ai_chat_job",
        lambda **kwargs: launched.setdefault("payload", kwargs),
    )

    response = asyncio.run(
        create_ai_chat_job(
            BuilderAiChatRequest(
                messages=[BuilderAiChatMessage(role="user", content="Build BTC")],
                availableMarkets=["BTC"],
                currentDraft=None,
            )
        )
    )

    assert response.id == "job-1"
    assert response.status == "queued"
    assert created["job"]["job_type"] == "builder_ai_chat"
    assert launched["payload"]["job_id"] == "job-1"


def test_get_builder_ai_chat_job_returns_completed_payload(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.api.builder.ai_job_service.get_job",
        lambda **kwargs: {
            "id": kwargs["job_id"],
            "job_type": "builder_ai_chat",
            "status": "completed",
            "result_payload_json": {
                "reply": "Built draft",
                "draft": {
                    "name": "Draft",
                    "description": "Generated",
                    "marketSelection": "selected",
                    "markets": ["BTC"],
                    "conditions": [{"type": "price_above", "symbol": "BTC"}],
                    "actions": [{"type": "open_long", "symbol": "BTC"}],
                },
            },
            "error_detail": None,
            "created_at": "2026-04-10T00:00:00+00:00",
            "updated_at": "2026-04-10T00:00:01+00:00",
            "completed_at": "2026-04-10T00:00:01+00:00",
        },
    )

    response = asyncio.run(get_ai_chat_job("job-1"))

    assert response.id == "job-1"
    assert response.status == "completed"
    assert response.result is not None
    assert response.result.reply == "Built draft"
