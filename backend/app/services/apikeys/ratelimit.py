"""60 requests per minute per key (API-4), counted in memory.

Render runs one uvicorn worker, so this is exact in production; it resets on restart and would
not be shared across several workers (known gap in PHASE_LOG)."""

import math
from collections import deque
from datetime import datetime

LIMIT = 60
WINDOW_SECONDS = 60.0

_hits: dict[str, deque[float]] = {}


def check(key_id: str, now: datetime) -> int | None:
    """Record a request. Returns None if allowed, else seconds until the next one is allowed."""
    t = now.timestamp()
    hits = _hits.setdefault(key_id, deque())
    while hits and hits[0] <= t - WINDOW_SECONDS:
        hits.popleft()
    if len(hits) >= LIMIT:
        return max(1, math.ceil(hits[0] + WINDOW_SECONDS - t))
    hits.append(t)
    return None
