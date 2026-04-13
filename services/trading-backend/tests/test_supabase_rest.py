from __future__ import annotations

import httpx
import pytest

from src.services.supabase_rest import SupabaseRestClient, SupabaseRestError


def _build_client(handler: httpx.MockTransport) -> SupabaseRestClient:
    client = SupabaseRestClient.__new__(SupabaseRestClient)
    client._base_url = "https://example.supabase.co/rest/v1"  # noqa: SLF001
    client._client = httpx.Client(  # noqa: SLF001
        transport=handler,
        base_url=client._base_url,
    )
    client._read_cache = SupabaseRestClient._shared_read_cache  # noqa: SLF001
    return client


def test_request_summarizes_html_gateway_error() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            502,
            headers={"content-type": "text/html; charset=UTF-8"},
            text="""
<!DOCTYPE html>
<html lang="en-US">
<head><title> | 502: Bad gateway</title></head>
<body><h1>Bad gateway</h1></body>
</html>
""",
            request=request,
        )
    )
    client = _build_client(transport)
    try:
        with pytest.raises(SupabaseRestError) as exc_info:
            client._request("GET", "/worker_leases")  # noqa: SLF001
    finally:
        client.close()

    assert str(exc_info.value) == "Supabase request failed with status 502: upstream returned an HTML error page (502: Bad gateway)"
    assert exc_info.value.is_retryable is True


def test_request_wraps_transport_error_as_retryable_supabase_error() -> None:
    def _raise(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("socket closed", request=request)

    client = _build_client(httpx.MockTransport(_raise))
    try:
        with pytest.raises(SupabaseRestError) as exc_info:
            client._request("PATCH", "/worker_leases")  # noqa: SLF001
    finally:
        client.close()

    assert exc_info.value.status_code == 503
    assert exc_info.value.is_retryable is True
    assert "before a response was received" in str(exc_info.value)


def test_build_filters_quotes_string_values_for_in_operator() -> None:
    client = SupabaseRestClient.__new__(SupabaseRestClient)

    params = client._build_filters(  # noqa: SLF001
        {
            "lease_key": ("in", ["bot-runtime:abc-123", 'portfolio:"quoted"']),
        }
    )

    assert params == {
        "lease_key": 'in.("bot-runtime:abc-123","portfolio:\\"quoted\\"")',
    }


def test_select_reuses_shared_read_cache_across_instances() -> None:
    call_count = 0

    def _handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(200, json=[{"id": "row-1"}], request=request)

    SupabaseRestClient._shared_read_cache.clear()
    first = _build_client(httpx.MockTransport(_handler))
    second = _build_client(httpx.MockTransport(_handler))
    try:
        assert first.select("worker_leases", cache_ttl_seconds=15) == [{"id": "row-1"}]
        assert second.select("worker_leases", cache_ttl_seconds=15) == [{"id": "row-1"}]
    finally:
        first.close()
        second.close()
        SupabaseRestClient._shared_read_cache.clear()

    assert call_count == 1
