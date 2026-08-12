"""In-process token-bucket rate limiter for `/api/v1/ask`.

No Redis — this is a single-user, single-process app (same deferral
reasoning as ADR-006), so a module-level in-memory bucket is sufficient and
resets on process restart, which is acceptable for a personal tool. Exists
to bound Anthropic API spend against a runaway client, not to defend
against multi-tenant abuse.
"""

import time
from threading import Lock


class TokenBucketRateLimiter:
    def __init__(self, capacity: int, refill_per_second: float) -> None:
        self._capacity = float(capacity)
        self._tokens = float(capacity)
        self._refill_per_second = refill_per_second
        self._last_refill = time.monotonic()
        self._lock = Lock()

    def try_acquire(self) -> bool:
        """Returns True and consumes one token if available, else False."""
        with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_refill
            self._tokens = min(self._capacity, self._tokens + elapsed * self._refill_per_second)
            self._last_refill = now
            if self._tokens >= 1:
                self._tokens -= 1
                return True
            return False

    def reset(self) -> None:
        """Refills to full capacity — for tests only. A production
        caller has no legitimate reason to reset its own rate limit;
        this exists because `login_rate_limiter` is a module-level
        singleton shared by the whole pytest process, and the
        `client` fixture logs in once per test (Revision Prompt 16)."""
        with self._lock:
            self._tokens = self._capacity
            self._last_refill = time.monotonic()


# 5-request burst, steady-state refill of 1 request per 12 seconds (5/min) —
# generous for interactive single-user use, tight enough to stop a buggy
# client loop from burning through Anthropic spend unattended.
ask_rate_limiter = TokenBucketRateLimiter(capacity=5, refill_per_second=1 / 12)

# Tighter than ask_rate_limiter: each request can trigger several real web
# searches (up to `MAX_SEARCH_USES` in services/earnings_research.py), so a
# single call costs meaningfully more than a /ask round trip. 3-request
# burst, 1 per 20 seconds steady state.
earnings_research_rate_limiter = TokenBucketRateLimiter(capacity=3, refill_per_second=1 / 20)
