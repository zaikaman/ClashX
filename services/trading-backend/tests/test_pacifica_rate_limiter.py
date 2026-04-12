from __future__ import annotations

from collections import deque

import pytest

from src.services.pacifica_rate_limiter import PacificaRateLimiter


@pytest.mark.anyio
async def test_acquire_token_records_local_bucket_event() -> None:
    limiter = PacificaRateLimiter()

    await limiter._acquire_token("public", 2)

    assert "public" in limiter._bucket_events
    assert len(limiter._bucket_events["public"]) == 1


@pytest.mark.anyio
async def test_acquire_token_waits_when_local_bucket_is_full(monkeypatch: pytest.MonkeyPatch) -> None:
    limiter = PacificaRateLimiter()
    limiter._bucket_events["public"] = deque([10.0])

    monotonic_values = [10.2, 10.2, 11.25, 11.25]
    sleep_calls: list[float] = []

    def _fake_monotonic() -> float:
        if monotonic_values:
            return monotonic_values.pop(0)
        return 11.25

    monkeypatch.setattr("src.services.pacifica_rate_limiter.time.monotonic", _fake_monotonic)

    async def _fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    monkeypatch.setattr("src.services.pacifica_rate_limiter.asyncio.sleep", _fake_sleep)

    await limiter._acquire_token("public", 1)

    assert sleep_calls
    assert sleep_calls[0] == pytest.approx(0.8, abs=0.01)
    assert len(limiter._bucket_events["public"]) == 1
    assert limiter._bucket_events["public"][0] == 11.25
