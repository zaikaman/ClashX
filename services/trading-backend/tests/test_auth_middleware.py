import asyncio
from typing import Any

import pytest
from fastapi import Request
from fastapi.responses import JSONResponse

from src.api.auth import AuthenticatedUser
from src.middleware.auth import AuthMiddleware


def _build_request(path: str, method: str, headers: dict[str, str] | None = None) -> Request:
    encoded_headers = [
        (key.lower().encode("latin-1"), value.encode("latin-1"))
        for key, value in (headers or {}).items()
    ]
    scope: dict[str, Any] = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("ascii"),
        "query_string": b"",
        "root_path": "",
        "headers": encoded_headers,
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
    }
    return Request(scope)


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("POST", "/api/bots/validate"),
        ("GET", "/api/builder/templates"),
        ("GET", "/api/builder/markets"),
    ],
)
def test_public_routes_bypass_auth(
    monkeypatch: pytest.MonkeyPatch,
    method: str,
    path: str,
) -> None:
    middleware = AuthMiddleware(app=lambda *_args, **_kwargs: None)

    def _unexpected_auth_call(_token: str) -> AuthenticatedUser:
        raise AssertionError("public routes should not trigger bearer auth")

    async def call_next(_request: Request) -> JSONResponse:
        return JSONResponse({"ok": True})

    monkeypatch.setattr("src.middleware.auth.authenticate_bearer_token", _unexpected_auth_call)

    response = asyncio.run(middleware.dispatch(_build_request(path, method), call_next))

    assert response.status_code == 200


def test_protected_route_requires_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    middleware = AuthMiddleware(app=lambda *_args, **_kwargs: None)
    auth_tokens: list[str] = []

    def _failing_auth(token: str) -> AuthenticatedUser:
        auth_tokens.append(token)
        raise ValueError("missing token")

    async def call_next(_request: Request) -> JSONResponse:
        return JSONResponse({"ok": True})

    monkeypatch.setattr("src.middleware.auth.authenticate_bearer_token", _failing_auth)

    response = asyncio.run(middleware.dispatch(_build_request("/api/bots", "GET"), call_next))

    assert response.status_code == 401
    assert auth_tokens == [""]


def test_protected_route_accepts_valid_bearer_token(monkeypatch: pytest.MonkeyPatch) -> None:
    middleware = AuthMiddleware(app=lambda *_args, **_kwargs: None)
    captured_users: list[dict[str, Any]] = []

    def _successful_auth(_token: str) -> AuthenticatedUser:
        return AuthenticatedUser(user_id="user_123", wallet_addresses=["wallet_abc"])

    async def call_next(request: Request) -> JSONResponse:
        captured_users.append(request.state.user)
        return JSONResponse({"ok": True})

    monkeypatch.setattr("src.middleware.auth.authenticate_bearer_token", _successful_auth)

    response = asyncio.run(
        middleware.dispatch(
            _build_request("/api/bots", "GET", headers={"Authorization": "Bearer test-token"}),
            call_next,
        )
    )

    assert response.status_code == 200
    assert captured_users == [
        {
            "user_id": "user_123",
            "session_id": None,
            "wallet_addresses": ["wallet_abc"],
            "expires_at": None,
        }
    ]
