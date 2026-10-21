"""Bounded per-process public request budgets; no document or question text stored."""
from collections import OrderedDict, deque
from contextlib import contextmanager
from threading import Lock
import time
from fastapi import HTTPException, Request
from app.core.config import get_settings
from app.core.access import authenticated

_buckets = OrderedDict()
_active = 0
_lock = Lock()


def _rate(request: Request, purpose: str):
    now = time.monotonic()
    key = (purpose, request.client.host if request.client else 'unknown')
    with _lock:
        timestamps = _buckets.pop(key, deque())
        while timestamps and timestamps[0] <= now - 60:
            timestamps.popleft()
        _buckets[key] = timestamps
        while len(_buckets) > 4096:
            _buckets.popitem(last=False)
        if len(timestamps) >= get_settings().public_chat_rate_limit:
            raise HTTPException(429, 'Có quá nhiều yêu cầu. Vui lòng chờ rồi thử lại.', headers={'Retry-After':'60'})
        timestamps.append(now)


@contextmanager
def public_chat_slot(request: Request):
    global _active
    if authenticated(request):
        yield
        return
    _rate(request, 'chat')
    with _lock:
        if _active >= get_settings().public_chat_max_concurrent:
            raise HTTPException(429, 'Hệ thống đang xử lý nhiều câu hỏi. Vui lòng thử lại sau.', headers={'Retry-After':'10'})
        _active += 1
    try:
        yield
    finally:
        with _lock:
            _active -= 1
