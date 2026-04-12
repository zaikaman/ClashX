from __future__ import annotations

import pytest

from src.services.pacifica_rate_limiter import PacificaRateLimiter


class _FakeCoordination:
    def __init__(self, *, claim_results: list[bool] | None = None) -> None:
        self.claim_results = list(claim_results or [True])
        self.calls: list[tuple[str, float]] = []

    def try_claim_lease(self, lease_key: str, *, ttl_seconds: int) -> bool:
        self.calls.append((lease_key, float(ttl_seconds)))
        if self.claim_results:
            return self.claim_results.pop(0)
        return False


def test_rate_limiter_uses_stable_slot_lease_keys() -> None:
    assert PacificaRateLimiter._lease_key(bucket="public", slot=3) == "rate-budget:public:3"
    assert PacificaRateLimiter._lease_key(bucket="global", slot=11) == "rate-budget:global:11"


def test_rate_limiter_scopes_ttl_to_current_second_boundary() -> None:
    ttl = PacificaRateLimiter._lease_ttl_seconds(now=100.95)
    assert 0.05 <= ttl <= 0.11

    ttl = PacificaRateLimiter._lease_ttl_seconds(now=100.25)
    assert 0.79 <= ttl <= 0.81


@pytest.mark.anyio
async def test_acquire_token_reuses_stable_slot_keys() -> None:
    coordination = _FakeCoordination(claim_results=[False, True])
    limiter = PacificaRateLimiter(coordination=coordination)

    async def _next_slot(limit: int) -> int:
        assert limit == 4
        return 0

    limiter._next_slot = _next_slot  # type: ignore[method-assign]

    await limiter._acquire_token("public", 4)

    assert [call[0] for call in coordination.calls] == [
        "rate-budget:public:0",
        "rate-budget:public:1",
    ]
