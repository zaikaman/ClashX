from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from src.workers.backtest_job_worker import BacktestJobWorker


@dataclass
class _FakeJobService:
    queued_jobs: list[dict[str, Any]] = field(default_factory=list)
    stale_running_jobs: list[dict[str, Any]] = field(default_factory=list)
    failed_jobs: list[tuple[str, str]] = field(default_factory=list)
    list_calls: list[dict[str, Any]] = field(default_factory=list)

    def list_jobs(self, **kwargs) -> list[dict[str, Any]]:
        self.list_calls.append(dict(kwargs))
        statuses = kwargs.get("statuses") or []
        if statuses == ["queued"]:
            return [dict(job) for job in self.queued_jobs]
        if statuses == ["running"]:
            return [dict(job) for job in self.stale_running_jobs]
        return []

    def mark_failed(self, *, job_id: str, error_detail: str) -> dict[str, Any]:
        self.failed_jobs.append((job_id, error_detail))
        return {"id": job_id, "status": "failed"}


@dataclass
class _FakeRunner:
    calls: list[dict[str, Any]] = field(default_factory=list)

    async def _run_backtest_run_job(self, **kwargs) -> None:
        self.calls.append(dict(kwargs))
        heartbeat = kwargs.get("heartbeat")
        if heartbeat is not None:
            heartbeat()


@dataclass
class _FakeCoordination:
    claimed: list[tuple[str, int]] = field(default_factory=list)
    released: list[str] = field(default_factory=list)

    def try_claim_lease(self, lease_key: str, *, ttl_seconds: int) -> bool:
        self.claimed.append((lease_key, ttl_seconds))
        return True

    def release_lease(self, lease_key: str) -> None:
        self.released.append(lease_key)


def test_backtest_job_worker_loads_queued_and_stale_running_jobs() -> None:
    jobs = _FakeJobService(
        queued_jobs=[{"id": "job-1"}],
        stale_running_jobs=[{"id": "job-2"}, {"id": "job-1"}],
    )
    worker = BacktestJobWorker(supabase=object(), job_service=jobs, runner=_FakeRunner(), coordination=_FakeCoordination())

    candidates = worker._load_candidate_jobs()

    assert [job["id"] for job in candidates] == ["job-1", "job-2"]
    assert jobs.list_calls[0]["statuses"] == ["queued"]
    assert jobs.list_calls[1]["statuses"] == ["running"]


def test_backtest_job_worker_processes_job_payload_and_releases_lease() -> None:
    jobs = _FakeJobService()
    runner = _FakeRunner()
    coordination = _FakeCoordination()
    worker = BacktestJobWorker(supabase=object(), job_service=jobs, runner=runner, coordination=coordination)
    lease_key = worker._lease_key("job-7")
    worker._held_leases[lease_key] = 999999.0

    asyncio.run(
        worker._process_job(
            {
                "id": "job-7",
                "request_payload_json": {
                    "bot_id": "bot-1",
                    "wallet_address": "wallet-abc",
                    "user_id": "user-1",
                    "interval": "1m",
                    "start_time": 1,
                    "end_time": 2,
                    "initial_capital_usd": 10_000,
                    "assumptions": {"fee_bps": 4},
                },
            }
        )
    )

    assert runner.calls[0]["job_id"] == "job-7"
    assert runner.calls[0]["bot_id"] == "bot-1"
    assert runner.calls[0]["interval"] == "1m"
    assert callable(runner.calls[0]["heartbeat"])
    assert coordination.released == [lease_key]
    assert lease_key not in worker._held_leases


def test_backtest_job_worker_marks_invalid_payload_failed() -> None:
    jobs = _FakeJobService()
    worker = BacktestJobWorker(supabase=object(), job_service=jobs, runner=_FakeRunner(), coordination=_FakeCoordination())
    lease_key = worker._lease_key("job-9")
    worker._held_leases[lease_key] = 999999.0

    asyncio.run(worker._process_job({"id": "job-9", "request_payload_json": {"bot_id": ""}}))

    assert jobs.failed_jobs == [("job-9", "Backtest job payload is missing bot or wallet identity fields.")]
