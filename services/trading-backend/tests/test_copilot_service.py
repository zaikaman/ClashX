from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import httpx

from src.api.auth import AuthenticatedUser
from src.services.copilot_service import CopilotService


@dataclass
class _FakeSettings:
    gemini_api_key: str = ""
    gemini_base_url: str = ""
    gemini_model: str = ""
    openai_api_key: str = ""
    openai_base_url: str = ""
    openai_model: str = ""


class _FakeResponse:
    def __init__(self, status_code: int, payload: Any) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> Any:
        return self._payload


class _FakeHttpClient:
    def __init__(self, responses: list[_FakeResponse]) -> None:
        self._responses = responses
        self.calls: list[dict[str, Any]] = []

    async def post(self, url: str, *, headers: dict[str, str], json: dict[str, Any]) -> _FakeResponse:
        self.calls.append({"url": url, "headers": headers, "json": json})
        if not self._responses:
            raise AssertionError("No fake responses remaining")
        return self._responses.pop(0)


class _TimeoutHttpClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def post(self, url: str, *, headers: dict[str, str], json: dict[str, Any]) -> _FakeResponse:
        self.calls.append({"url": url, "headers": headers, "json": json})
        raise httpx.ReadTimeout("timed out")


def _user() -> AuthenticatedUser:
    return AuthenticatedUser(user_id="user-123", wallet_addresses=["wallet-abc"])


def _service_with(
    *,
    settings: _FakeSettings,
    responses: list[_FakeResponse],
) -> tuple[CopilotService, _FakeHttpClient]:
    service = CopilotService()
    service.settings = settings
    service._http = _FakeHttpClient(responses)
    return service, service._http


def _gemini_text_payload(text: str) -> dict[str, Any]:
    return {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {
                            "text": text,
                        }
                    ]
                }
            }
        ]
    }


def test_copilot_executes_plain_text_tool_calls_and_returns_final_answer() -> None:
    service, http_client = _service_with(
        settings=_FakeSettings(
            gemini_api_key="gem-key",
            gemini_base_url="https://example.test/v1beta",
            gemini_model="gemini-3-flash-preview",
        ),
        responses=[
            _FakeResponse(200, _gemini_text_payload('{"type":"tool_call","tool":"list_bots","arguments":{"wallet_address":"wallet-abc"}}')),
            _FakeResponse(200, _gemini_text_payload('{"type":"final","reply":"You have 2 bots and 1 active runtime.","followUps":["Show the most recent bot events"]}')),
        ],
    )

    async def fake_execute_tool_call(*, tool_name: str, arguments: dict[str, Any], **_: Any) -> dict[str, Any]:
        assert tool_name == "list_bots"
        assert arguments["wallet_address"] == "wallet-abc"
        return {
            "ok": True,
            "data": {
                "wallet_address": "wallet-abc",
                "bots": [
                    {"id": "bot-1", "name": "Momentum"},
                    {"id": "bot-2", "name": "Mean Revert"},
                ],
            },
        }

    service._execute_tool_call = fake_execute_tool_call  # type: ignore[method-assign]

    result = asyncio.run(
        service.chat(
            messages=[{"role": "user", "content": "Summarize my bots"}],
            user=_user(),
            wallet_address=None,
        )
    )

    assert result["provider"] == "Gemini"
    assert result["reply"] == "You have 2 bots and 1 active runtime."
    assert result["followUps"] == ["Show the most recent bot events"]
    assert len(result["toolCalls"]) == 1
    assert result["toolCalls"][0]["tool"] == "list_bots"
    assert "TOOL_RESULT" in http_client.calls[1]["json"]["contents"][-1]["parts"][0]["text"]


def test_copilot_accepts_function_wrapper_and_falls_back_to_openai() -> None:
    service, http_client = _service_with(
        settings=_FakeSettings(
            gemini_api_key="gem-key",
            gemini_base_url="https://example.test/v1beta",
            gemini_model="gemini-3-flash-preview",
            openai_api_key="open-key",
            openai_base_url="https://example.openai.test/v1",
            openai_model="gpt-5-mini",
        ),
        responses=[
            _FakeResponse(500, {"error": {"message": "Gemini unavailable"}}),
            _FakeResponse(
                200,
                {
                    "output_text": (
                        '{"function":{"name":"final_response","arguments":"'
                        '{\\"reply\\":\\"Pacifica authorization is inactive.\\",'
                        '\\"followUps\\":[\\"Check readiness for my wallet\\"]}"}}'
                    ),
                },
            ),
        ],
    )

    result = asyncio.run(
        service.chat(
            messages=[{"role": "user", "content": "Can I trade right now?"}],
            user=_user(),
            wallet_address="wallet-abc",
        )
    )

    assert result["provider"] == "OpenAI"
    assert result["reply"] == "Pacifica authorization is inactive."
    assert result["followUps"] == ["Check readiness for my wallet"]
    assert [call["url"] for call in http_client.calls] == [
        "https://example.test/v1beta/models/gemini-3-flash-preview:generateContent",
        "https://example.openai.test/v1/responses",
    ]


def test_copilot_ignores_extra_json_after_first_object() -> None:
    service, _ = _service_with(
        settings=_FakeSettings(
            gemini_api_key="gem-key",
            gemini_base_url="https://example.test/v1beta",
            gemini_model="gemini-3-flash-preview",
        ),
        responses=[
            _FakeResponse(
                200,
                _gemini_text_payload(
                    '{"type":"final","reply":"Here is the summary.","followUps":["Show recent activity"]}'
                    '\n{"debug":"ignore me"}'
                ),
            ),
        ],
    )

    result = asyncio.run(
        service.chat(
            messages=[{"role": "user", "content": "Summarize my account"}],
            user=_user(),
            wallet_address=None,
        )
    )

    assert result["reply"] == "Here is the summary."
    assert result["followUps"] == ["Show recent activity"]


def test_copilot_retries_when_final_reply_claims_fetching_without_tool_call() -> None:
    service, http_client = _service_with(
        settings=_FakeSettings(
            gemini_api_key="gem-key",
            gemini_base_url="https://example.test/v1beta",
            gemini_model="gemini-3-flash-preview",
        ),
        responses=[
            _FakeResponse(
                200,
                _gemini_text_payload(
                    '{"type":"final","reply":"I\\u2019m pulling your recent runtime events. Fetching your bots and their latest events now.","followUps":["Would you like me to summarize only the most recent event per bot, or provide a full list of the last 20 events per bot?"]}'
                ),
            ),
            _FakeResponse(200, _gemini_text_payload('{"type":"tool_call","tool":"list_bots","arguments":{"wallet_address":"wallet-abc"}}')),
            _FakeResponse(200, _gemini_text_payload('{"type":"final","reply":"You have 2 bots. The newest runtime event was a rebalance on Momentum.","followUps":["Show the full event timeline"]}')),
        ],
    )

    async def fake_execute_tool_call(*, tool_name: str, arguments: dict[str, Any], **_: Any) -> dict[str, Any]:
        assert tool_name == "list_bots"
        assert arguments["wallet_address"] == "wallet-abc"
        return {
            "ok": True,
            "data": {
                "wallet_address": "wallet-abc",
                "bots": [
                    {"id": "bot-1", "name": "Momentum"},
                    {"id": "bot-2", "name": "Mean Revert"},
                ],
            },
        }

    service._execute_tool_call = fake_execute_tool_call  # type: ignore[method-assign]

    result = asyncio.run(
        service.chat(
            messages=[{"role": "user", "content": "What happened in my recent runtime events?"}],
            user=_user(),
            wallet_address="wallet-abc",
        )
    )

    assert result["reply"] == "You have 2 bots. The newest runtime event was a rebalance on Momentum."
    assert result["followUps"] == ["Show the full event timeline"]
    assert len(result["toolCalls"]) == 1
    assert result["toolCalls"][0]["tool"] == "list_bots"
    assert "SYSTEM_RETRY" in http_client.calls[1]["json"]["contents"][-1]["parts"][0]["text"]


def test_copilot_converts_openai_timeouts_to_runtime_errors() -> None:
    service = CopilotService()
    service.settings = _FakeSettings(
        openai_api_key="open-key",
        openai_base_url="https://example.openai.test/v1",
        openai_model="gpt-5-mini",
    )
    service._http = _TimeoutHttpClient()

    try:
        asyncio.run(
            service.chat(
                messages=[{"role": "user", "content": "Can I trade right now?"}],
                user=_user(),
                wallet_address="wallet-abc",
            )
        )
    except RuntimeError as exc:
        assert str(exc) == "OpenAI: OpenAI request timed out."
    else:
        raise AssertionError("Expected RuntimeError")
