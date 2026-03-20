import asyncio
import contextlib
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.auth import router as auth_router
from src.api.backtests import router as backtests_router
from src.api.bot_copy import router as bot_copy_router
from src.api.bots import router as bots_router
from src.api.builder import router as builder_router
from src.api.pacifica import router as pacifica_router
from src.api.stream import router as stream_router
from src.api.stream import websocket_fallback
from src.api.trading import router as trading_router
from src.core.settings import get_settings
from src.middleware.auth import AuthMiddleware
from src.services.pacifica_market_data_service import get_pacifica_market_data_service
from src.workers.bot_copy_worker import BotCopyWorker
from src.workers.bot_runtime_worker import BotRuntimeWorker


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        force=True,
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


_configure_logging()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name)
    bot_copy_worker = BotCopyWorker()
    bot_runtime_worker = BotRuntimeWorker()
    market_data_service = get_pacifica_market_data_service()

    app.add_middleware(AuthMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(auth_router)
    app.include_router(backtests_router)
    app.include_router(bot_copy_router)
    app.include_router(bots_router)
    app.include_router(builder_router)
    app.include_router(pacifica_router)
    app.include_router(stream_router)
    app.include_router(trading_router)

    display_network = "Devnet" if settings.pacifica_network.lower().startswith("test") else settings.pacifica_network

    @app.on_event("startup")
    async def startup() -> None:
        await market_data_service.start()
        if not settings.background_workers_enabled:
            return
        app.state.bot_runtime_worker = bot_runtime_worker
        app.state.bot_copy_worker = bot_copy_worker
        bot_runtime_worker.start()
        bot_copy_worker.start()

    @app.on_event("shutdown")
    async def shutdown() -> None:
        running_bot_copy_worker: BotCopyWorker | None = getattr(app.state, "bot_copy_worker", None)
        running_bot_runtime_worker: BotRuntimeWorker | None = getattr(app.state, "bot_runtime_worker", None)
        if running_bot_copy_worker is not None:
            with contextlib.suppress(asyncio.CancelledError):
                await running_bot_copy_worker.stop()
        if running_bot_runtime_worker is not None:
            with contextlib.suppress(asyncio.CancelledError):
                await running_bot_runtime_worker.stop()
        await market_data_service.stop()

    @app.get("/healthz", tags=["ops"])
    async def healthz() -> dict[str, object]:
        workers: dict[str, object] = {}
        for key in ("bot_runtime_worker", "bot_copy_worker"):
            worker_ref = getattr(app.state, key, None)
            if worker_ref is None:
                workers[key] = {"enabled": False}
                continue
            workers[key] = {
                "enabled": True,
                "running": worker_ref.is_running,
                "last_iteration_at": worker_ref.last_iteration_at,
                "last_error": worker_ref.last_error,
            }
        return {"status": "ok", "network": display_network, "workers": workers}

    app.websocket("/ws")(websocket_fallback)
    return app


app = create_app()
