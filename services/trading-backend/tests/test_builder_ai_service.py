from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

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
