"""Rolling-average duration and queue ETA math (§5).

`avg_duration` is the mean of the last `N` completed jobs, falling back to a configured default
until the first sample arrives. ETA values are *estimates*: callers return them as `null` until
`is_ready()` (≥3 completed jobs) is true.
"""

from __future__ import annotations


class EtaEstimator:
    def __init__(self, *, sample_size: int = 20, default_seconds: float = 90.0):
        self._sample_size = sample_size
        self._default_seconds = default_seconds
        self._durations: list[float] = []

    def record(self, duration_seconds: float) -> None:
        self._durations.append(duration_seconds)
        if len(self._durations) > self._sample_size:
            self._durations.pop(0)

    def sample_count(self) -> int:
        return len(self._durations)

    def is_ready(self) -> bool:
        return len(self._durations) >= 3

    def avg_duration(self) -> float:
        if not self._durations:
            return self._default_seconds
        return sum(self._durations) / len(self._durations)

    def start_eta(self, position: int, total_slots: int) -> float:
        """Estimated wait before a queued job at 0-based `position` starts."""
        if total_slots <= 0:
            return 0.0
        return (position // total_slots) * self.avg_duration()

    def finish_eta(self, position: int, total_slots: int) -> float:
        return self.start_eta(position, total_slots) + self.avg_duration()

    def running_remaining(self, elapsed_seconds: float) -> float:
        return max(0.0, self.avg_duration() - elapsed_seconds)
