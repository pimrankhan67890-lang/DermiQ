from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass
from threading import Lock
from typing import Deque, Dict


@dataclass(frozen=True)
class RateLimit:
    max_requests: int
    window_seconds: int


class InMemoryRateLimiter:
    """
    Simple in-memory rate limiter (per key, fixed window sliding timestamps).

    Notes:
    - Suitable for single-instance deployments.
    - For multi-instance production, use a shared store (Redis) at the edge.
    """

    def __init__(self) -> None:
        self._lock = Lock()
        self._hits: Dict[str, Deque[float]] = {}

    def allow(self, key: str, limit: RateLimit) -> bool:
        if not key:
            return True

        now = time.time()
        cutoff = now - float(limit.window_seconds)

        with self._lock:
            q = self._hits.get(key)
            if q is None:
                q = deque()
                self._hits[key] = q

            while q and q[0] < cutoff:
                q.popleft()

            if len(q) >= int(limit.max_requests):
                return False

            q.append(now)
            return True

