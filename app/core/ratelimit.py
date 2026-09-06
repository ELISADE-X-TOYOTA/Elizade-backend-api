"""Request rate limiting.

WHY THIS IS NOT A SCALING FEATURE
=================================
`/auth/otp/request` was unauthenticated, unthrottled, and sends a Postmark
email on every call. At 41 users that is already a live problem, not a
future one — it lets anyone burn the email budget, and lets anyone flood a
chosen person's inbox with codes, from a single laptop. Rate limiting is
therefore shipped ahead of everything else in the scaling work.

TWO KEYS, NOT ONE
=================
Limiting by IP alone misses the abuse that matters most here: one attacker,
one IP, a thousand different victim addresses — each getting a real email.
Limiting by email alone is trivially beaten with a script. So OTP costs a
budget on BOTH the recipient and the caller, and the stricter one wins.

THE STORAGE SEAM
================
Counters live in memory by default, which is exactly right for the single
worker running today and costs nothing to operate. It is also WRONG the moment
there are two replicas: each keeps its own counters, so the effective limit
silently doubles. `RateLimitStore` is the seam — point it at Redis and the
limit becomes global again, with nothing above it changing. That swap is a
prerequisite for horizontal scaling, alongside the realtime hub's.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Protocol

from fastapi import HTTPException, Request, status


@dataclass(frozen=True)
class Decision:
    allowed: bool
    #: Seconds until the window resets. Sent as `Retry-After`, so a client can
    #: back off precisely instead of guessing.
    retry_after: int
    remaining: int


class RateLimitStore(Protocol):
    def hit(self, key: str, *, limit: int, window: int) -> Decision: ...


class InMemoryRateLimitStore:
    """Fixed-window counters in process memory.

    Fixed window rather than sliding: it is a few lines, has no per-request
    allocation per hit, and its known weakness — up to 2x the limit across a
    window boundary — is irrelevant at the magnitudes here (5 emails vs 10).
    A sliding window would be the right call for billing or quota enforcement.

    Thread-safe because sync FastAPI endpoints run in a threadpool, so hits
    genuinely race.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        #: key -> (window_started_at, count)
        self._buckets: dict[str, tuple[float, int]] = {}
        self._last_swept = time.monotonic()

    def _sweep(self, now: float) -> None:
        """Drop windows that ended over an hour ago.

        Without this the dict grows once per distinct key forever — and the
        keys include attacker-chosen email addresses, so it is a slow memory
        leak that an attacker controls the rate of.
        """
        if now - self._last_swept < 300:
            return
        cutoff = now - 3600
        self._buckets = {k: v for k, v in self._buckets.items() if v[0] > cutoff}
        self._last_swept = now

    def hit(self, key: str, *, limit: int, window: int) -> Decision:
        now = time.monotonic()
        with self._lock:
            self._sweep(now)
            started, count = self._buckets.get(key, (now, 0))
            if now - started >= window:
                started, count = now, 0
            count += 1
            self._buckets[key] = (started, count)

        retry_after = max(1, int(window - (now - started)))
        if count > limit:
            return Decision(allowed=False, retry_after=retry_after, remaining=0)
        return Decision(allowed=True, retry_after=retry_after, remaining=limit - count)


#: Process-wide store. Replaced wholesale when Redis is configured.
_store: RateLimitStore = InMemoryRateLimitStore()


def set_store(store: RateLimitStore) -> None:
    """Swap the backend — see the module docstring on multi-replica."""
    global _store
    _store = store


def client_ip(request: Request) -> str:
    """Best-effort caller identity.

    `X-Forwarded-For` is caller-supplied and therefore spoofable. Railway
    appends the real peer as the LAST entry, so the rightmost hop is the one
    the platform vouches for — the leftmost, which is the usual convention, is
    exactly the part an attacker writes. Taking the rightmost means a spoofed
    header cannot fragment an attacker across unlimited synthetic buckets.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        hops = [h.strip() for h in forwarded.split(",") if h.strip()]
        if hops:
            return hops[-1]
    return request.client.host if request.client else "unknown"


def enforce(key: str, *, limit: int, window: int) -> None:
    """Charge one hit; raise 429 when the budget is spent."""
    decision = _store.hit(key, limit=limit, window=window)
    if not decision.allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many attempts. Please wait a moment and try again.",
            headers={"Retry-After": str(decision.retry_after)},
        )


# ── Budgets ──────────────────────────────────────────────────────────────
#
# Tuned to be invisible to a real person and expensive for a script. A customer
# who mistypes their address, retries, then asks for a resend uses three.
OTP_PER_EMAIL = (5, 600)     # 5 codes per address per 10 minutes
OTP_PER_IP = (30, 600)       # 30 sends per caller per 10 minutes
VERIFY_PER_IP = (40, 600)    # brute-force guard on the code itself
CHEAP_READ_PER_IP = (120, 60)  # side-effect-free endpoints, generous


def limit_otp_request(request: Request, email: str) -> None:
    """Both budgets, recipient first — see the module docstring."""
    normalised = (email or "").strip().lower()
    if normalised:
        enforce(f"otp:email:{normalised}", limit=OTP_PER_EMAIL[0], window=OTP_PER_EMAIL[1])
    enforce(f"otp:ip:{client_ip(request)}", limit=OTP_PER_IP[0], window=OTP_PER_IP[1])


def limit_otp_verify(request: Request) -> None:
    enforce(f"verify:ip:{client_ip(request)}", limit=VERIFY_PER_IP[0], window=VERIFY_PER_IP[1])


def limit_cheap_read(request: Request, scope: str) -> None:
    enforce(
        f"read:{scope}:{client_ip(request)}",
        limit=CHEAP_READ_PER_IP[0],
        window=CHEAP_READ_PER_IP[1],
    )
