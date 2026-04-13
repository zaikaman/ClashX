import asyncio
from types import SimpleNamespace

import src.main as main


class _FakeMetricsStore:
    def record(self, key: str, value: float) -> None:
        del key, value

    def snapshot(self) -> dict[str, object]:
        return {}


class _FakeMarketDataService:
    def __init__(self) -> None:
        self.start_calls = 0
        self.stop_calls = 0

    async def start(self) -> None:
        self.start_calls += 1

    async def stop(self) -> None:
        self.stop_calls += 1


class _FakeWorker:
    def __init__(self) -> None:
        self.start_calls = 0
        self.stop_calls = 0
        self.is_running = False
        self.last_iteration_at = None
        self.last_error = None

    def start(self) -> None:
        self.start_calls += 1
        self.is_running = True

    async def stop(self) -> None:
        self.stop_calls += 1
        self.is_running = False


class _FakeMarketplaceService:
    def __init__(self) -> None:
        self.start_calls = 0
        self.stop_calls = 0

    async def start_background_warmup(self) -> None:
        self.start_calls += 1

    async def stop_background_warmup(self) -> None:
        self.stop_calls += 1


class _FakeTelegramService:
    def __init__(self) -> None:
        self.configure_calls = 0

    async def configure_bot(self, *, settings) -> None:
        del settings
        self.configure_calls += 1


def _build_settings(*, background_workers_enabled: bool) -> SimpleNamespace:
    return SimpleNamespace(
        app_name="Test App",
        cors_allowed_origins=("http://localhost:3000",),
        pacifica_network="testnet",
        background_workers_enabled=background_workers_enabled,
    )


def test_web_startup_skips_pacifica_ws(monkeypatch) -> None:
    market_data_service = _FakeMarketDataService()
    marketplace = _FakeMarketplaceService()
    telegram = _FakeTelegramService()

    monkeypatch.setattr(main, "get_settings", lambda: _build_settings(background_workers_enabled=False))
    monkeypatch.setattr(main, "get_performance_metrics_store", lambda: _FakeMetricsStore())
    monkeypatch.setattr(main, "get_pacifica_market_data_service", lambda: market_data_service)
    monkeypatch.setattr(main, "marketplace_service", marketplace)
    monkeypatch.setattr(main, "telegram_service", telegram)
    monkeypatch.setattr(main, "BotRuntimeWorker", _FakeWorker)
    monkeypatch.setattr(main, "BotCopyWorker", _FakeWorker)
    monkeypatch.setattr(main, "BotRuntimeSnapshotWorker", _FakeWorker)
    monkeypatch.setattr(main, "PortfolioAllocatorWorker", _FakeWorker)
    monkeypatch.setattr(main, "BacktestJobWorker", _FakeWorker)

    app = main.create_app()

    asyncio.run(app.router.startup())
    asyncio.run(app.router.shutdown())

    assert market_data_service.start_calls == 0
    assert market_data_service.stop_calls == 1
    assert marketplace.start_calls == 0
    assert marketplace.stop_calls == 1
    assert telegram.configure_calls == 1


def test_worker_enabled_startup_starts_pacifica_ws(monkeypatch) -> None:
    market_data_service = _FakeMarketDataService()
    marketplace = _FakeMarketplaceService()
    telegram = _FakeTelegramService()

    monkeypatch.setattr(main, "get_settings", lambda: _build_settings(background_workers_enabled=True))
    monkeypatch.setattr(main, "get_performance_metrics_store", lambda: _FakeMetricsStore())
    monkeypatch.setattr(main, "get_pacifica_market_data_service", lambda: market_data_service)
    monkeypatch.setattr(main, "marketplace_service", marketplace)
    monkeypatch.setattr(main, "telegram_service", telegram)
    monkeypatch.setattr(main, "BotRuntimeWorker", _FakeWorker)
    monkeypatch.setattr(main, "BotCopyWorker", _FakeWorker)
    monkeypatch.setattr(main, "BotRuntimeSnapshotWorker", _FakeWorker)
    monkeypatch.setattr(main, "PortfolioAllocatorWorker", _FakeWorker)
    monkeypatch.setattr(main, "BacktestJobWorker", _FakeWorker)

    app = main.create_app()

    asyncio.run(app.router.startup())
    asyncio.run(app.router.shutdown())

    assert market_data_service.start_calls == 1
    assert market_data_service.stop_calls == 1
    assert marketplace.start_calls == 1
    assert marketplace.stop_calls == 1
    assert telegram.configure_calls == 1
