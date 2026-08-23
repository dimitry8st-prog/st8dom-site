"""Простой лимит запросов к виджету. Без внешних сервисов."""

from __future__ import annotations

import time
from collections import defaultdict, deque

WINDOW_SEC = 300
MAX_HITS = 20


class SlidingWindowLimiter:
    def __init__(self, max_hits: int = MAX_HITS, window_sec: int = WINDOW_SEC) -> None:
        self.max_hits = max_hits
        self.window_sec = window_sec
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        bucket = self._hits[key]
        cutoff = now - self.window_sec
        while bucket and bucket[0] < cutoff:
            bucket.popleft()
        if len(bucket) >= self.max_hits:
            return False
        bucket.append(now)
        return True

    def reset(self) -> None:
        self._hits.clear()


limiter = SlidingWindowLimiter()
