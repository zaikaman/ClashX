import asyncio
import contextlib
import logging
import signal

from src.core.settings import get_settings
from src.services.pacifica_market_data_service import get_pacifica_market_data_service
from src.workers.backtest_job_worker import BacktestJobWorker
from src.workers.bot_copy_worker import BotCopyWorker
from src.workers.bot_runtime_worker import BotRuntimeWorker
from src.workers.bot_runtime_snapshot_worker import BotRuntimeSnapshotWorker
from src.workers.portfolio_allocator_worker import PortfolioAllocatorWorker


logger = logging.getLogger(__name__)


async def run_worker() -> None:
    settings = get_settings()
    if not settings.background_workers_enabled:
        raise RuntimeError("BACKGROUND_WORKERS_ENABLED must be true for the worker process")

    market_data_service = get_pacifica_market_data_service()
    workers = [
        BotRuntimeWorker(),
        BotCopyWorker(),
        BotRuntimeSnapshotWorker(),
        PortfolioAllocatorWorker(),
        BacktestJobWorker(),
    ]
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop_event.set)

    await market_data_service.start()
    for worker in workers:
        worker.start()

    logger.info("Background worker process started with %s worker loops", len(workers))

    try:
        await stop_event.wait()
    finally:
        for worker in reversed(workers):
            with contextlib.suppress(asyncio.CancelledError):
                await worker.stop()
        await market_data_service.stop()


if __name__ == "__main__":
    asyncio.run(run_worker())
