import asyncio
import contextlib
import logging
import os
import signal
import threading

from src.core.settings import get_settings
from src.services.pacifica_market_data_service import get_pacifica_market_data_service
from src.workers.backtest_job_worker import BacktestJobWorker
from src.workers.bot_copy_worker import BotCopyWorker
from src.workers.bot_runtime_worker import BotRuntimeWorker
from src.workers.bot_runtime_snapshot_worker import BotRuntimeSnapshotWorker
from src.workers.portfolio_allocator_worker import PortfolioAllocatorWorker


logger = logging.getLogger(__name__)
HEROKU_SHUTDOWN_GRACE_SECONDS = 25.0
WORKER_STOP_TIMEOUT_SECONDS = 20.0


def _force_exit_after_grace() -> threading.Timer:
    timer = threading.Timer(HEROKU_SHUTDOWN_GRACE_SECONDS, _force_exit)
    timer.daemon = True
    timer.start()
    return timer


def _force_exit() -> None:
    logger.warning("Worker shutdown exceeded %.1fs; exiting before Heroku SIGKILL", HEROKU_SHUTDOWN_GRACE_SECONDS)
    os._exit(0)


async def run_worker() -> None:
    settings = get_settings()
    if not settings.background_workers_enabled:
        raise RuntimeError("BACKGROUND_WORKERS_ENABLED must be true for the worker process")

    market_data_service = get_pacifica_market_data_service()
    bot_copy_worker = BotCopyWorker()
    bot_runtime_worker = BotRuntimeWorker()
    bot_runtime_worker.copy_worker = bot_copy_worker
    workers = [
        bot_copy_worker,
        bot_runtime_worker,
        BotRuntimeSnapshotWorker(),
        PortfolioAllocatorWorker(),
        BacktestJobWorker(),
    ]
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    shutdown_timer: threading.Timer | None = None

    def request_stop() -> None:
        nonlocal shutdown_timer
        if shutdown_timer is None:
            shutdown_timer = _force_exit_after_grace()
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, request_stop)

    await market_data_service.start()
    for worker in workers:
        worker.start()

    logger.info("Background worker process started with %s worker loops", len(workers))

    try:
        await stop_event.wait()
    finally:
        logger.info("Background worker shutdown requested")
        stop_tasks = [asyncio.create_task(worker.stop()) for worker in reversed(workers)]
        stop_tasks.append(asyncio.create_task(market_data_service.stop()))
        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(asyncio.gather(*stop_tasks, return_exceptions=True), timeout=WORKER_STOP_TIMEOUT_SECONDS)
        for task in stop_tasks:
            if not task.done():
                task.cancel()
        if shutdown_timer is not None:
            shutdown_timer.cancel()
        logger.info("Background worker shutdown complete")


if __name__ == "__main__":
    asyncio.run(run_worker())
