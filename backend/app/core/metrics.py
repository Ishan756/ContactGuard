import time
from collections import Counter
from dataclasses import dataclass, field
from threading import Lock
from typing import Any


@dataclass
class RouteMetrics:
    count: int = 0
    errors: int = 0
    total_duration_ms: float = 0.0
    max_duration_ms: float = 0.0


@dataclass
class MetricsRegistry:
    """Small in-process metrics registry for logs and the health endpoint.

    Multi-worker deployments should scrape structured logs or use a shared metrics
    backend; these counters are intentionally per-process.
    """

    started_at: float = field(default_factory=time.time)
    counters: Counter[str] = field(default_factory=Counter)
    routes: dict[str, RouteMetrics] = field(default_factory=dict)
    _lock: Lock = field(default_factory=Lock, repr=False)

    def record_request(
        self,
        method: str,
        route: str,
        status_code: int,
        duration_ms: float,
    ) -> None:
        key = f"{method.upper()} {route}"
        with self._lock:
            self.counters["requests_total"] += 1
            if status_code >= 500:
                self.counters["requests_5xx_total"] += 1
            elif status_code >= 400:
                self.counters["requests_4xx_total"] += 1
            if status_code == 429:
                self.counters["rate_limited_total"] += 1
            metrics = self.routes.setdefault(key, RouteMetrics())
            metrics.count += 1
            metrics.errors += int(status_code >= 500)
            metrics.total_duration_ms += duration_ms
            metrics.max_duration_ms = max(metrics.max_duration_ms, duration_ms)

    def increment(self, name: str, amount: int = 1) -> None:
        with self._lock:
            self.counters[name] += amount

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            routes = {
                key: {
                    "count": value.count,
                    "errors": value.errors,
                    "avg_duration_ms": round(
                        value.total_duration_ms / value.count, 2
                    )
                    if value.count
                    else 0.0,
                    "max_duration_ms": round(value.max_duration_ms, 2),
                }
                for key, value in sorted(self.routes.items())
            }
            return {
                "uptime_seconds": round(time.time() - self.started_at, 2),
                "counters": dict(self.counters),
                "routes": routes,
            }


metrics = MetricsRegistry()
