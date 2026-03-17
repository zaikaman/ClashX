import asyncio
import contextlib

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.admin import router as admin_router
from src.api.auth import router as auth_router
from src.api.bot_copy import router as bot_copy_router
from src.api.bots import router as bots_router
from src.api.builder import router as builder_router
from src.api.copy import router as copy_router
from src.api.leagues import router as leagues_router
from src.api.pacifica import router as pacifica_router
from src.api.stream import router as stream_router
from src.api.stream import websocket_fallback
from src.api.trading import router as trading_router
from src.core.settings import get_settings
from src.db.session import engine
from src.middleware.auth import AuthMiddleware
from src.workers.bot_copy_worker import BotCopyWorker
from src.workers.bot_runtime_worker import BotRuntimeWorker
from src.workers.copy_worker import CopyWorker
from src.workers.leaderboard_worker import LeaderboardWorker


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name)
    worker = LeaderboardWorker()
    copy_worker = CopyWorker()
    bot_copy_worker = BotCopyWorker()
    bot_runtime_worker = BotRuntimeWorker()

    app.add_middleware(AuthMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(auth_router)
    app.include_router(admin_router)
    app.include_router(bot_copy_router)
    app.include_router(bots_router)
    app.include_router(builder_router)
    app.include_router(copy_router)
    app.include_router(leagues_router)
    app.include_router(pacifica_router)
    app.include_router(stream_router)
    app.include_router(trading_router)

    display_network = "Devnet" if settings.pacifica_network.lower().startswith("test") else settings.pacifica_network

    @app.on_event("startup")
    async def startup() -> None:
        app.state.bot_runtime_worker = bot_runtime_worker
        bot_runtime_worker.start()
        if engine is not None:
            app.state.leaderboard_worker = worker
            app.state.copy_worker = copy_worker
            app.state.bot_copy_worker = bot_copy_worker
            worker.start()
            copy_worker.start()
            bot_copy_worker.start()

    @app.on_event("shutdown")
    async def shutdown() -> None:
        running_worker: LeaderboardWorker | None = getattr(app.state, "leaderboard_worker", None)
        running_copy_worker: CopyWorker | None = getattr(app.state, "copy_worker", None)
        running_bot_copy_worker: BotCopyWorker | None = getattr(app.state, "bot_copy_worker", None)
        running_bot_runtime_worker: BotRuntimeWorker | None = getattr(app.state, "bot_runtime_worker", None)
        if running_worker is not None:
            await running_worker.stop()
        if running_copy_worker is not None:
            with contextlib.suppress(asyncio.CancelledError):
                await running_copy_worker.stop()
        if running_bot_copy_worker is not None:
            with contextlib.suppress(asyncio.CancelledError):
                await running_bot_copy_worker.stop()
        if running_bot_runtime_worker is not None:
            with contextlib.suppress(asyncio.CancelledError):
                await running_bot_runtime_worker.stop()

    @app.get("/healthz", tags=["ops"])
    async def healthz() -> dict[str, str]:
        return {"status": "ok", "network": display_network}

    app.websocket("/ws")(websocket_fallback)
    return app


app = create_app()
