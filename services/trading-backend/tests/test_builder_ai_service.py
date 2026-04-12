from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import httpx

from src.services.builder_ai_service import BuilderAiService


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


def _service_with(
    *,
    settings: _FakeSettings,
    responses: list[_FakeResponse],
) -> tuple[BuilderAiService, _FakeHttpClient]:
    service = BuilderAiService()
    service.settings = settings
    service._http = _FakeHttpClient(responses)
    return service, service._http


def _draft_payload(*, symbol: str = "BTC") -> dict[str, Any]:
    return {
        "reply": f"Built a {symbol} breakout draft.",
        "name": f"{symbol} Breakout",
        "description": "Ride upside momentum after confirmation.",
        "marketSelection": "selected",
        "markets": [symbol],
        "conditions": [
            {
                "type": "ema_crosses_above",
                "symbol": symbol,
                "timeframe": "15m",
                "fast_period": 9,
                "slow_period": 21,
            }
        ],
        "actions": [
            {
                "type": "open_long",
                "symbol": symbol,
                "size_usd": 150,
                "leverage": 3,
            }
        ],
    }


def test_generate_draft_prefers_gemini_and_uses_generate_content_endpoint() -> None:
    gemini_payload = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {
                            "text": str(_draft_payload()).replace("'", '"'),
                        }
                    ]
                }
            }
        ]
    }
    service, http_client = _service_with(
        settings=_FakeSettings(
            gemini_api_key="gem-key",
            gemini_base_url="https://v98store.com/v1beta",
            gemini_model="gemini-3-flash-preview",
            openai_api_key="open-key",
            openai_base_url="https://example.openai.azure.com/openai/v1",
            openai_model="gpt-5-nano",
        ),
        responses=[_FakeResponse(200, gemini_payload)],
    )

    result = asyncio.run(
        service.generate_draft(
            messages=[{"role": "user", "content": "Build a BTC momentum bot"}],
            available_markets=["BTC", "ETH"],
            current_draft=None,
        )
    )

    assert result["draft"]["name"] == "BTC Breakout"
    assert len(http_client.calls) == 1
    assert http_client.calls[0]["url"] == "https://v98store.com/v1beta/models/gemini-3-flash-preview:generateContent"
    assert http_client.calls[0]["json"]["contents"][0]["role"] == "user"


def test_generate_draft_falls_back_to_openai_when_gemini_fails() -> None:
    openai_payload = {
        "output_text": str(_draft_payload(symbol="ETH")).replace("'", '"'),
    }
    service, http_client = _service_with(
        settings=_FakeSettings(
            gemini_api_key="gem-key",
            gemini_base_url="https://v98store.com/v1beta",
            gemini_model="gemini-3-flash-preview",
            openai_api_key="open-key",
            openai_base_url="https://example.openai.azure.com/openai/v1",
            openai_model="gpt-5-nano",
        ),
        responses=[
            _FakeResponse(500, {"error": {"message": "Gemini unavailable"}}),
            _FakeResponse(200, openai_payload),
        ],
    )

    result = asyncio.run(
        service.generate_draft(
            messages=[{"role": "user", "content": "Build an ETH trend bot"}],
            available_markets=["BTC", "ETH"],
            current_draft=None,
        )
    )

    assert result["draft"]["markets"] == ["ETH"]
    assert [call["url"] for call in http_client.calls] == [
        "https://v98store.com/v1beta/models/gemini-3-flash-preview:generateContent",
        "https://example.openai.azure.com/openai/v1/responses",
    ]


def test_generate_draft_accepts_plain_text_function_call_arguments() -> None:
    function_payload = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {
                            "text": (
                                '{"name":"apply_builder_draft","arguments":'
                                '"{\\"reply\\":\\"Updated BTC draft.\\",\\"name\\":\\"BTC Scalper\\",'
                                '\\"description\\":\\"Short-term BTC momentum.\\",'
                                '\\"marketSelection\\":\\"selected\\",\\"markets\\":[\\"BTC\\"],'
                                '\\"conditions\\":[{\\"type\\":\\"price_above\\",\\"symbol\\":\\"BTC\\",\\"value\\":65000}],'
                                '\\"actions\\":[{\\"type\\":\\"open_long\\",\\"symbol\\":\\"BTC\\",\\"size_usd\\":200,\\"leverage\\":2}]}"'
                                "}"
                            ),
                        }
                    ]
                }
            }
        ]
    }
    service, _ = _service_with(
        settings=_FakeSettings(
            gemini_api_key="gem-key",
            gemini_base_url="https://v98store.com/v1beta",
            gemini_model="gemini-3-flash-preview",
        ),
        responses=[_FakeResponse(200, function_payload)],
    )

    result = asyncio.run(
        service.generate_draft(
            messages=[{"role": "user", "content": "Make BTC react when price breaks higher"}],
            available_markets=["BTC", "ETH"],
            current_draft=None,
        )
    )

    assert result["reply"] == "Updated BTC draft."
    assert result["draft"]["name"] == "BTC Scalper"
    assert result["draft"]["conditions"][0]["type"] == "price_above"


def test_generate_draft_ignores_extra_json_after_first_object() -> None:
    service, _ = _service_with(
        settings=_FakeSettings(
            openai_api_key="open-key",
            openai_base_url="https://example.openai.azure.com/openai/v1",
            openai_model="gpt-5-nano",
        ),
        responses=[
            _FakeResponse(
                200,
                {
                    "output_text": str(_draft_payload(symbol="BTC")).replace("'", '"') + '\n{"debug":"ignore me"}',
                },
            ),
        ],
    )

    result = asyncio.run(
        service.generate_draft(
            messages=[{"role": "user", "content": "Build a BTC momentum bot"}],
            available_markets=["BTC", "ETH"],
            current_draft=None,
        )
    )

    assert result["draft"]["name"] == "BTC Breakout"
    assert result["draft"]["markets"] == ["BTC"]


def test_system_prompt_describes_route_semantics_for_branching_strategies() -> None:
    service, _ = _service_with(
        settings=_FakeSettings(),
        responses=[],
    )

    prompt = service._build_system_prompt(
        available_markets=["BTC", "ETH", "SOL"],
        current_draft={"name": "Existing bot"},
    )

    assert "A route is an ordered path of conditions followed by actions." in prompt
    assert "Each distinct intent should become its own route" in prompt
    assert "Do not omit any explicit trigger, direction, market, TP, SL, timeframe, or threshold" in prompt
    assert "the number of routes matches the number of distinct trigger/action paths implied by the request" in prompt
    assert '"routes":' in prompt


def test_generate_draft_accepts_explicit_routes_for_multi_branch_strategies() -> None:
    routed_payload = {
        "output_text": (
            "{"
            '"reply":"Built a two-route RSI mean reversion draft.",'
            '"name":"ETH RSI Mean Reversion",'
            '"description":"Trades overbought and oversold RSI extremes with separate branches.",'
            '"marketSelection":"selected",'
            '"markets":["ETH"],'
            '"routes":['
            "{"
            '"name":"short-overbought",'
            '"conditions":[{"type":"rsi_above","symbol":"ETH","timeframe":"15m","period":14,"value":70}],'
            '"actions":['
            '{"type":"open_short","symbol":"ETH","size_usd":150,"leverage":3},'
            '{"type":"set_tpsl","symbol":"ETH","take_profit_pct":2,"stop_loss_pct":1}'
            "]"
            "},"
            "{"
            '"name":"long-oversold",'
            '"conditions":[{"type":"rsi_below","symbol":"ETH","timeframe":"15m","period":14,"value":30}],'
            '"actions":['
            '{"type":"open_long","symbol":"ETH","size_usd":150,"leverage":3},'
            '{"type":"set_tpsl","symbol":"ETH","take_profit_pct":2,"stop_loss_pct":1}'
            "]"
            "}"
            "]"
            "}"
        ),
    }
    service, _ = _service_with(
        settings=_FakeSettings(
            openai_api_key="open-key",
            openai_base_url="https://example.openai.azure.com/openai/v1",
            openai_model="gpt-5-nano",
        ),
        responses=[_FakeResponse(200, routed_payload)],
    )

    result = asyncio.run(
        service.generate_draft(
            messages=[{"role": "user", "content": "Short ETH when RSI is above 70 and long when it is below 30."}],
            available_markets=["BTC", "ETH"],
            current_draft=None,
        )
    )

    assert result["draft"]["markets"] == ["ETH"]
    assert len(result["draft"]["routes"]) == 2
    assert result["draft"]["routes"][0]["actions"][0]["type"] == "open_short"
    assert result["draft"]["routes"][1]["actions"][0]["type"] == "open_long"
    assert result["draft"]["conditions"][0]["type"] == "rsi_above"
    assert result["draft"]["actions"][0]["type"] == "open_short"


def test_generate_draft_accepts_openai_function_call_output_items() -> None:
    function_call_payload = {
        "output": [
            {
                "type": "function_call",
                "name": "apply_builder_draft",
                "arguments": (
                    "{"
                    '"reply":"Built ETH RSI routes.",'
                    '"name":"ETH RSI Draft",'
                    '"description":"RSI threshold branches.",'
                    '"marketSelection":"selected",'
                    '"markets":["ETH"],'
                    '"routes":['
                    "{"
                    '"conditions":[{"type":"rsi_above","symbol":"ETH","timeframe":"15m","period":14,"value":70}],'
                    '"actions":[{"type":"open_short","symbol":"ETH","size_usd":150,"leverage":3}]'
                    "},"
                    "{"
                    '"conditions":[{"type":"rsi_below","symbol":"ETH","timeframe":"15m","period":14,"value":30}],'
                    '"actions":[{"type":"open_long","symbol":"ETH","size_usd":150,"leverage":3}]'
                    "}"
                    "]"
                    "}"
                ),
            }
        ]
    }
    service, _ = _service_with(
        settings=_FakeSettings(
            openai_api_key="open-key",
            openai_base_url="https://example.openai.azure.com/openai/v1",
            openai_model="gpt-5-nano",
        ),
        responses=[_FakeResponse(200, function_call_payload)],
    )

    result = asyncio.run(
        service.generate_draft(
            messages=[{"role": "user", "content": "Build the ETH RSI strategy."}],
            available_markets=["BTC", "ETH"],
            current_draft=None,
        )
    )

    assert result["draft"]["markets"] == ["ETH"]
    assert len(result["draft"]["routes"]) == 2
    assert result["draft"]["actions"][0]["type"] == "open_short"


def test_generate_draft_accepts_gemini_function_call_parts() -> None:
    gemini_payload = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {
                            "functionCall": {
                                "name": "apply_builder_draft",
                                "args": {
                                    "reply": "Built BTC route draft.",
                                    "name": "BTC Routed Draft",
                                    "description": "Structured route draft.",
                                    "marketSelection": "selected",
                                    "markets": ["BTC"],
                                    "routes": [
                                        {
                                            "conditions": [{"type": "rsi_below", "symbol": "BTC", "timeframe": "15m", "period": 14, "value": 30}],
                                            "actions": [{"type": "open_long", "symbol": "BTC", "size_usd": 150, "leverage": 3}],
                                        }
                                    ],
                                },
                            }
                        }
                    ]
                }
            }
        ]
    }
    service, _ = _service_with(
        settings=_FakeSettings(
            gemini_api_key="gem-key",
            gemini_base_url="https://v98store.com/v1beta",
            gemini_model="gemini-3-flash-preview",
        ),
        responses=[_FakeResponse(200, gemini_payload)],
    )

    result = asyncio.run(
        service.generate_draft(
            messages=[{"role": "user", "content": "Build the BTC RSI strategy."}],
            available_markets=["BTC", "ETH"],
            current_draft=None,
        )
    )

    assert result["draft"]["markets"] == ["BTC"]
    assert len(result["draft"]["routes"]) == 1
    assert result["draft"]["conditions"][0]["type"] == "rsi_below"


def test_generate_draft_converts_openai_timeouts_to_runtime_errors() -> None:
    service = BuilderAiService()
    service.settings = _FakeSettings(
        openai_api_key="open-key",
        openai_base_url="https://example.openai.test/v1",
        openai_model="gpt-5-mini",
    )
    service._http = _TimeoutHttpClient()

    try:
        asyncio.run(
            service.generate_draft(
                messages=[{"role": "user", "content": "Build a BTC momentum bot"}],
                available_markets=["BTC"],
                current_draft=None,
            )
        )
    except RuntimeError as exc:
        assert str(exc) == "OpenAI: OpenAI request timed out."
    else:
        raise AssertionError("Expected RuntimeError")
