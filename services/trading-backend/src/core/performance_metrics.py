from __future__ import annotations

from collections import defaultdict, deque
from functools import lru_cache
from threading import Lock
from typing import Deque


class PerformanceMetricsStore:
    def __init__(self, *, max_samples_per_key: int = 512) -> None:
        self._max_samples_per_key = max(32, max_samples_per_key)
        self._samples: dict[str, Deque[float]] = defaultdict(lambda: deque(maxlen=self._max_samples_per_key))
        self._lock = Lock()

    def record(self, key: str, duration_ms: float) -> None:
        if not key:
            return
        bounded = max(0.0, float(duration_ms))
        with self._lock:
            self._samples[key].append(bounded)

    def snapshot(self) -> dict[str, dict[str, float | int]]:
        with self._lock:
            serialized = {key: list(values) for key, values in self._samples.items() if values}

        metrics: dict[str, dict[str, float | int]] = {}
        for key, values in serialized.items():
            values.sort()
            count = len(values)
            metrics[key] = {
                "count": count,
                "avg_ms": round(sum(values) / count, 3),
                "p50_ms": round(self._percentile(values, 50), 3),
                "p95_ms": round(self._percentile(values, 95), 3),
                "p99_ms": round(self._percentile(values, 99), 3),
                "max_ms": round(values[-1], 3),
            }
        return metrics

    @staticmethod
    def _percentile(sorted_values: list[float], percentile: int) -> float:
        if not sorted_values:
            return 0.0
        if len(sorted_values) == 1:
            return sorted_values[0]
        position = (len(sorted_values) - 1) * (percentile / 100)
        lower = int(position)
        upper = min(lower + 1, len(sorted_values) - 1)
        weight = position - lower
        return sorted_values[lower] + (sorted_values[upper] - sorted_values[lower]) * weight


@lru_cache(maxsize=1)
def get_performance_metrics_store() -> PerformanceMetricsStore:
    return PerformanceMetricsStore()
