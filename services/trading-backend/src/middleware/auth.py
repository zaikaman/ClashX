from collections.abc import Awaitable, Callable

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from src.api.auth import authenticate_bearer_token


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable],
    ):
        public_routes = {
            ("GET", "/healthz"),
            ("POST", "/api/auth/privy/verify"),
            ("POST", "/api/bots/validate"),
            ("GET", "/docs"),
            ("GET", "/openapi.json"),
        }
        public_prefixes = (
            "/api/builder",
            "/api/stream",
            "/api/bot-copy",
            "/api/marketplace",
            "/api/pacifica",
        )
        public_trading_paths = {"/api/trading/markets", "/api/trading/chart"}
        route_key = (request.method.upper(), request.url.path)
        if route_key in public_routes or request.url.path.startswith(public_prefixes):
            return await call_next(request)
        if request.url.path in public_trading_paths and request.method == "GET":
            return await call_next(request)

        if request.method == "OPTIONS":
            return await call_next(request)

        bearer = request.headers.get("Authorization", "")
        token = bearer.replace("Bearer", "").strip() if bearer.startswith("Bearer") else ""

        try:
            request.state.user = authenticate_bearer_token(token).model_dump(mode="json")
        except Exception:
            return JSONResponse(status_code=401, content={"detail": "Unauthorized"})
        return await call_next(request)
