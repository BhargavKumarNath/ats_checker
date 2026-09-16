"""Per-client sliding-window rate limit for the free scoring endpoint.

Why in-process: the Fly proxy can also limit, but that lives outside this repo. A limiter
here is visible in the import graph, tested, and works identically in local dev and in
production. State is per process, which is fine for one always-on web machine; with several
machines the effective limit is multiplied by their count, which is still bounded.

Why a middleware and not a dependency in routes.py: the boundary between "request arrives" and
"scoring work starts" should be one obvious place. Nothing here touches models or scoring.
"""

from __future__ import annotations

import math
import time
from collections import deque
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from starlette.requests import Request
from starlette.types import ASGIApp, Receive, Scope, Send

from atsc.web.routes import too_many_requests

LIMITED = frozenset({("POST", "/score")})
PRUNE_EVERY = 256  # checks between sweeps of idle keys


@dataclass(frozen=True)
class Verdict:
    allowed: bool
    retry_after: int  # whole seconds until the oldest counted hit leaves the window; 0 if allowed


class SlidingWindowLimiter:
    """At most `limit` hits per key in any `window_seconds`-long interval."""

    def __init__(
        self, *, limit: int, window_seconds: float, clock: Callable[[], float] = time.monotonic
    ) -> None:
        if limit < 1:
            raise ValueError("limit must be >= 1; disable the limiter instead of setting 0")
        self.limit = limit
        self.window = float(window_seconds)
        self._clock = clock
        self._hits: dict[str, deque[float]] = {}
        self._checks = 0

    @property
    def tracked_keys(self) -> int:
        return len(self._hits)

    def check(self, key: str) -> Verdict:
        now = self._clock()
        self._checks += 1
        if self._checks % PRUNE_EVERY == 0:
            self.prune()
        hits = self._hits.setdefault(key, deque())
        cutoff = now - self.window
        while hits and hits[0] <= cutoff:
            hits.popleft()
        if len(hits) >= self.limit:
            return Verdict(False, max(1, math.ceil(hits[0] + self.window - now)))
        hits.append(now)
        return Verdict(True, 0)

    def prune(self) -> None:
        """Forget keys with no hits inside the window so memory is bounded by active clients."""
        cutoff = self._clock() - self.window
        for key in [k for k, h in self._hits.items() if not h or h[-1] <= cutoff]:
            del self._hits[key]


class RateLimitMiddleware:
    """Pure ASGI middleware: 429 with Retry-After when a client exceeds the limit.

    The client key is the socket peer address unless `client_ip_header` names a header set by
    a trusted reverse proxy (on Fly: `Fly-Client-IP`). An unconfigured header is ignored, so a
    client cannot buy fresh buckets by inventing forwarding headers.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        limiter: SlidingWindowLimiter,
        client_ip_header: str = "",
        limited: Iterable[tuple[str, str]] = LIMITED,
    ) -> None:
        self.app = app
        self.limiter = limiter
        self.header = client_ip_header.lower().encode() if client_ip_header else b""
        self.limited = frozenset(limited)

    def client_key(self, scope: Scope) -> str:
        if self.header:
            for name, value in scope.get("headers", []):
                if name == self.header:
                    return str(value.decode("latin-1").split(",")[0].strip())
        client = scope.get("client")
        return str(client[0]) if client else "unknown"

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or (scope["method"], scope["path"]) not in self.limited:
            await self.app(scope, receive, send)
            return
        verdict = self.limiter.check(self.client_key(scope))
        if verdict.allowed:
            await self.app(scope, receive, send)
            return
        response = too_many_requests(Request(scope), retry_after=verdict.retry_after)
        await response(scope, receive, send)
