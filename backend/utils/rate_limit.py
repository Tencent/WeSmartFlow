"""进程内限流 / 失败锁定。

用于保护登录类接口（admin 登录、邮箱验证码），防止暴力猜测与邮件轰炸。
状态保存在进程内存中：多 worker / 多实例部署时每个进程各自计数，
上限相当于乘以进程数；需要全局精确限流时应在反向代理层再加一道。
"""

from __future__ import annotations

import threading
import time
from collections import deque

from fastapi import HTTPException, Request, status

# 防止恶意构造海量 key 撑爆内存。
_MAX_TRACKED_KEYS = 10_000


def client_ip(request: Request) -> str:
    """取直连对端地址。

    经反向代理部署时，请让 uvicorn 以 ``--proxy-headers --forwarded-allow-ips``
    只信任自己的代理，这样 ``request.client.host`` 才是真实客户端；
    这里不直接读取 ``X-Forwarded-For``，避免被客户端伪造绕过限流。
    """
    return request.client.host if request.client else "unknown"


def _too_many(retry_after: int, detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail=detail,
        headers={"Retry-After": str(max(1, retry_after))},
    )


class SlidingWindowLimiter:
    """滑动窗口：``window_seconds`` 内同一 key 最多 ``max_events`` 次。"""

    def __init__(self, max_events: int, window_seconds: int, *, detail: str):
        self.max_events = max_events
        self.window = window_seconds
        self.detail = detail
        self._events: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def hit(self, key: str) -> None:
        """记录一次请求；超限抛 429。"""
        now = time.monotonic()
        with self._lock:
            self._evict(now)
            events = self._events.setdefault(key, deque())
            while events and now - events[0] > self.window:
                events.popleft()
            if len(events) >= self.max_events:
                raise _too_many(int(self.window - (now - events[0])) + 1, self.detail)
            events.append(now)

    def _evict(self, now: float) -> None:
        if len(self._events) < _MAX_TRACKED_KEYS:
            return
        for key in [
            k for k, v in self._events.items() if not v or now - v[-1] > self.window
        ]:
            del self._events[key]
        if len(self._events) >= _MAX_TRACKED_KEYS:
            self._events.clear()

    def reset(self) -> None:
        with self._lock:
            self._events.clear()


class FailureLockout:
    """连续失败锁定：``window_seconds`` 内失败 ``max_failures`` 次后锁定 ``lockout_seconds``。"""

    def __init__(
        self,
        max_failures: int,
        window_seconds: int,
        lockout_seconds: int,
        *,
        detail: str,
    ):
        self.max_failures = max_failures
        self.window = window_seconds
        self.lockout = lockout_seconds
        self.detail = detail
        self._failures: dict[str, deque[float]] = {}
        self._locked_until: dict[str, float] = {}
        self._lock = threading.Lock()

    def check(self, key: str) -> None:
        """处理请求前调用；处于锁定期则抛 429。"""
        now = time.monotonic()
        with self._lock:
            until = self._locked_until.get(key)
            if until is None:
                return
            if now >= until:
                del self._locked_until[key]
                self._failures.pop(key, None)
                return
            raise _too_many(int(until - now) + 1, self.detail)

    def record_failure(self, key: str) -> None:
        now = time.monotonic()
        with self._lock:
            if len(self._failures) >= _MAX_TRACKED_KEYS:
                self._failures.clear()
                self._locked_until.clear()
            failures = self._failures.setdefault(key, deque())
            while failures and now - failures[0] > self.window:
                failures.popleft()
            failures.append(now)
            if len(failures) >= self.max_failures:
                self._locked_until[key] = now + self.lockout

    def record_success(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)
            self._locked_until.pop(key, None)

    def reset(self) -> None:
        with self._lock:
            self._failures.clear()
            self._locked_until.clear()
