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


class _FakeTradingTools:
    async def list_positions(self, db: Any, wallet_address: str) -> list[dict[str, Any]]:
        assert db is None
        assert wallet_address == "wallet-abc"
        return [
            {"symbol": "BTC", "side": "long", "amount": 0.25},
            {"symbol": "ETH", "side": "short", "amount": 1.5},
        ]

    async def list_orders(self, db: Any, wallet_address: str) -> list[dict[str, Any]]:
        assert db is None
        assert wallet_address == "wallet-abc"
        return [
            {"order_id": "ord-1", "symbol": "BTC", "side": "bid"},
            {"order_id": "ord-2", "symbol": "ETH", "side": "ask"},
        ]

    async def get_account_snapshot(self, db: Any, wallet_address: str) -> dict[str, Any]:
        assert db is None
        assert wallet_address == "wallet-abc"
        return {
            "wallet_address": wallet_address,
            "positions_loaded": True,
            "fills": [
                {"symbol": "BTC", "pnl": 12.5, "event_type": "close_long"},
                {"symbol": "ETH", "pnl": -3.0, "event_type": "close_short"},
            ],
        }


class _FakeRuntimeHealthTools:
    def get_health(self, db: Any, *, bot_id: str, wallet_address: str, user_id: str) -> dict[str, Any]:
        assert db is None
        assert bot_id == "bot-1"
        assert wallet_address == "wallet-abc"
        assert user_id == "user-123"
        return {"health": "healthy", "status": "running", "reasons": ["Heartbeat is fresh"]}


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


def test_copilot_retries_when_final_reply_after_tool_call_is_only_a_placeholder() -> None:
    service, http_client = _service_with(
        settings=_FakeSettings(
            gemini_api_key="gem-key",
            gemini_base_url="https://example.test/v1beta",
            gemini_model="gemini-3-flash-preview",
        ),
        responses=[
            _FakeResponse(200, _gemini_text_payload('{"type":"tool_call","tool":"list_bots","arguments":{"wallet_address":"wallet-abc"}}')),
            _FakeResponse(
                200,
                _gemini_text_payload(
                    '{"type":"final","reply":"Tool call issued for live trading account health check. Waiting for results to summarize health status and any action items.","followUps":["Would you like me to also fetch bot status and portfolio health in the same check?"]}'
                ),
            ),
            _FakeResponse(
                200,
                _gemini_text_payload(
                    '{"type":"final","reply":"You have 2 bots. Momentum is active, Mean Revert is idle, and no critical runtime issues are visible from the current bot snapshot.","followUps":["Show the latest bot events"]}'
                ),
            ),
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
                    {"id": "bot-1", "name": "Momentum", "runtime_overview": {"status": "active"}},
                    {"id": "bot-2", "name": "Mean Revert", "runtime_overview": {"status": "idle"}},
                ],
            },
        }

    service._execute_tool_call = fake_execute_tool_call  # type: ignore[method-assign]

    result = asyncio.run(
        service.chat(
            messages=[{"role": "user", "content": "What are my active bots doing right now?"}],
            user=_user(),
            wallet_address="wallet-abc",
        )
    )

    assert result["reply"] == (
        "You have 2 bots. Momentum is active, Mean Revert is idle, and no critical runtime issues are visible "
        "from the current bot snapshot."
    )
    assert result["followUps"] == ["Show the latest bot events"]
    assert len(result["toolCalls"]) == 1
    assert result["toolCalls"][0]["tool"] == "list_bots"
    assert "SYSTEM_RETRY" in http_client.calls[2]["json"]["contents"][-1]["parts"][0]["text"]


def test_copilot_executes_new_trading_tools() -> None:
    service = CopilotService()
    service._trading = _FakeTradingTools()  # type: ignore[assignment]

    positions = asyncio.run(
        service._execute_tool_call(
            tool_name="get_positions",
            arguments={"wallet_address": "wallet-abc", "limit": 1},
            user=_user(),
            default_wallet_address=None,
            scope_cache={},
        )
    )
    orders = asyncio.run(
        service._execute_tool_call(
            tool_name="get_open_orders",
            arguments={"wallet_address": "wallet-abc", "limit": 5},
            user=_user(),
            default_wallet_address=None,
            scope_cache={},
        )
    )
    trades = asyncio.run(
        service._execute_tool_call(
            tool_name="get_recent_trades",
            arguments={"wallet_address": "wallet-abc", "limit": 1},
            user=_user(),
            default_wallet_address=None,
            scope_cache={},
        )
    )

    assert positions["ok"] is True
    assert positions["data"]["count"] == 2
    assert positions["data"]["positions"] == [{"symbol": "BTC", "side": "long", "amount": 0.25}]
    assert orders["ok"] is True
    assert orders["data"]["count"] == 2
    assert orders["data"]["orders"][0]["order_id"] == "ord-1"
    assert trades["ok"] is True
    assert trades["data"]["count"] == 2
    assert trades["data"]["positions_loaded"] is True
    assert trades["data"]["trades"] == [{"symbol": "BTC", "pnl": 12.5, "event_type": "close_long"}]


def test_copilot_executes_runtime_health_tool() -> None:
    service = CopilotService()
    service._runtime_health = _FakeRuntimeHealthTools()  # type: ignore[assignment]

    result = asyncio.run(
        service._execute_tool_call(
            tool_name="get_runtime_health",
            arguments={"wallet_address": "wallet-abc", "bot_id": "bot-1"},
            user=_user(),
            default_wallet_address=None,
            scope_cache={},
        )
    )

    assert result == {
        "ok": True,
        "data": {
            "wallet_address": "wallet-abc",
            "bot_id": "bot-1",
            "health": {"health": "healthy", "status": "running", "reasons": ["Heartbeat is fresh"]},
        },
    }


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
