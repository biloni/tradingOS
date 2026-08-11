"""In-process request metrics (Revision Prompt 16: "job dashboard +
metrics"). Stdlib-only, matching this project's established pattern of
avoiding a new dependency (`prometheus_client`, etc.) for a capability
nothing external scrapes yet — a single-process personal app doesn't
need a metrics *pipeline*, just an honest in-memory summary exposed
over HTTP (`routers/ops.py::get_metrics`). Resets on process restart;
that's an accepted limitation for the same reason
`core/rate_limit.py`'s in-memory buckets are (see that module's
docstring).
"""

from __future__ import annotations

import time
from collections import deque
from threading import Lock
from typing import TypedDict


class LatencyStats(TypedDict):
    avg_ms: float | None
    p50_ms: float | None
    p95_ms: float | None
    sample_size: int


class MetricsSnapshot(TypedDict):
    uptime_seconds: float
    total_requests: int
    status_class_counts: dict[str, int]
    latency: LatencyStats


class RequestMetrics:
    """A bounded `deque` of recent latencies (not every latency ever
    seen) keeps memory flat for a long-running process — the p50/p95
    over the most recent `max_samples` requests is what an operator
    actually wants to know ("is it slow right now"), not a lifetime
    average that a single incident from days ago still skews."""

    def __init__(self, max_samples: int = 2000) -> None:
        self._lock = Lock()
        self._started_at = time.monotonic()
        self._total = 0
        self._status_class_counts: dict[str, int] = {}
        self._durations_ms: deque[float] = deque(maxlen=max_samples)

    def record(self, *, status_code: int, duration_ms: float) -> None:
        status_class = f"{status_code // 100}xx"
        with self._lock:
            self._total += 1
            self._status_class_counts[status_class] = (
                self._status_class_counts.get(status_class, 0) + 1
            )
            self._durations_ms.append(duration_ms)

    def snapshot(self) -> MetricsSnapshot:
        with self._lock:
            durations = sorted(self._durations_ms)
            status_class_counts = dict(self._status_class_counts)
            total = self._total
            uptime_seconds = round(time.monotonic() - self._started_at, 1)

        count = len(durations)
        latency: LatencyStats = {
            "avg_ms": round(sum(durations) / count, 2) if count else None,
            "p50_ms": durations[count // 2] if count else None,
            "p95_ms": durations[min(int(count * 0.95), count - 1)] if count else None,
            "sample_size": count,
        }
        return {
            "uptime_seconds": uptime_seconds,
            "total_requests": total,
            "status_class_counts": status_class_counts,
            "latency": latency,
        }

    def reset(self) -> None:
        """Tests only — a fresh process would never call this."""
        with self._lock:
            self._started_at = time.monotonic()
            self._total = 0
            self._status_class_counts = {}
            self._durations_ms.clear()


request_metrics = RequestMetrics()

__all__ = ["LatencyStats", "MetricsSnapshot", "RequestMetrics", "request_metrics"]
