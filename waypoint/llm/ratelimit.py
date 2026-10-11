"""Client-side request pacing, one limiter per model (free-tier quotas are per model)."""
from __future__ import annotations

import time
from collections.abc import Callable


class RateLimiter:
    """Spaces request starts at least 60/rpm seconds apart; `slow_down` halves rpm."""

    def __init__(self, rpm: float, *, min_rpm: float = 1.0,
                 clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep) -> None:
        if rpm <= 0:
            raise ValueError("rpm must be positive")
        self.rpm, self.min_rpm = rpm, min(min_rpm, rpm)
        self._clock, self._sleep = clock, sleep
        self._last: float | None = None

    def wait(self) -> float | None:
        """Block until the next request may start; return seconds idle since the
        previous start (None for the first request of this process)."""
        if self._last is not None:
            gap = self._clock() - self._last
            if gap < 60.0 / self.rpm:
                self._sleep(60.0 / self.rpm - gap)
        now = self._clock()
        idle = None if self._last is None else now - self._last
        self._last = now
        return idle

    def slow_down(self) -> None:
        self.rpm = max(self.min_rpm, self.rpm / 2)
