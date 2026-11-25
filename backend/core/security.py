"""
Krishi Bazaar — CSRF protection and a small in-memory rate limiter.
"""
import hmac
import secrets
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

CSRF_SESSION_KEY = "csrf"
CSRF_FIELD = "csrfmiddlewaretoken"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}


def csrf_token(session) -> str:
    """Return this session's CSRF token (created on first use)."""
    token = session.get(CSRF_SESSION_KEY)
    if not token:
        token = secrets.token_urlsafe(32)
        session[CSRF_SESSION_KEY] = token
    return token


async def csrf_protect(request: Request):
    """Router dependency: every state-changing request must carry the session's token."""
    if request.method in SAFE_METHODS:
        return
    expected = request.session.get(CSRF_SESSION_KEY)
    sent = request.headers.get("x-csrf-token")
    if not sent:
        form = await request.form()
        sent = form.get(CSRF_FIELD)
    if not expected or not sent or not hmac.compare_digest(str(sent), str(expected)):
        raise HTTPException(403, "Your security token is missing or expired. Please go back, reload the page and try again.")


class RateLimiter:
    """Allow `limit` events per `window` seconds for each key. In-memory (per server process)."""

    def __init__(self):
        self._events = defaultdict(deque)

    def _trim(self, key, window):
        events, now = self._events[key], time.monotonic()
        while events and now - events[0] > window:
            events.popleft()
        return events

    def blocked(self, key: str, limit: int, window: int) -> bool:
        return len(self._trim(key, window)) >= limit

    def hit(self, key: str, window: int) -> None:
        self._trim(key, window).append(time.monotonic())

    def reset(self, key: str) -> None:
        self._events.pop(key, None)


limiter = RateLimiter()


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def enforce_limit(request: Request, name: str, limit: int, window: int, extra: str = "") -> str:
    """Raise 429 when the caller is over the limit; otherwise return the limiter key."""
    key = f"{name}:{client_ip(request)}:{extra.lower()}"
    if limiter.blocked(key, limit, window):
        raise HTTPException(429, "Too many attempts. Please wait a few minutes and try again.")
    return key
