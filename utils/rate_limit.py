"""
محدودسازی نرخ درخواست‌ها (Rate Limiting) — API های عمومی/پرتنش
════════════════════════════════════════════
ورود از قبل قفل دارد (`login_guard`)، اما مسیرهای `/api/*` (جستجو، dark-mode،
دستگاه حضور و غیاب) هیچ محدودیتی نداشتند؛ یک اسکریپت ساده می‌توانست با
هزاران درخواست ثانیه‌ای، دیتابیس SQLite را قفل کند (SRE: حفاظت از سرویس).

پیاده‌سازی: سطل لغزان در حافظهٔ پروسه (مثل login_guard — بدون جدول/مهاجرت).
ریسک‌های میزبانی چند-ورکری همان مستندات login_guard را دارد؛ در آن حالت فقط
همین ماژول باید به Redis/DB وصل شود.

محدودیت‌ها از env خوانده می‌شوند تا در هاست‌های شلوغ بدون ویرایش کد تنظیم شوند.
"""
from __future__ import annotations

import os
import threading
import time
from collections import defaultdict, deque

#: پیش‌فرض‌ها: ۱۲۰ درخواست در دقیقه به ازای هر (IP + مسیر)
DEFAULT_LIMIT = 120
DEFAULT_PERIOD = 60.0

_lock = threading.Lock()
_buckets: dict[tuple[str, str], deque] = defaultdict(deque)


def _limit() -> int:
    try:
        return int(os.environ.get('ACADEMY_RATE_LIMIT', DEFAULT_LIMIT))
    except ValueError:
        return DEFAULT_LIMIT


def _period() -> float:
    try:
        return float(os.environ.get('ACADEMY_RATE_PERIOD', DEFAULT_PERIOD))
    except ValueError:
        return DEFAULT_PERIOD


def _key() -> tuple[str, str]:
    from flask import request
    ip = (request.remote_addr or 'unknown')[:64]
    path = request.path[:128]
    return (ip, path)


def hit() -> bool:
    """ثبت یک درخواست؛ False یعنی از سقف گذشت و باید 429 بدهیم."""
    now = time.time()
    key = _key()
    limit, period = _limit(), _period()
    with _lock:
        stamps = _buckets[key]
        cutoff = now - period
        while stamps and stamps[0] < cutoff:
            stamps.popleft()
        if len(stamps) >= limit:
            return False
        stamps.append(now)
        return True


def remaining() -> int:
    """چند درخواست هنوز مجاز است (برای هدر X-RateLimit-Remaining)."""
    now = time.time()
    limit, period = _limit(), _period()
    key = _key()
    with _lock:
        stamps = _buckets[key]
        while stamps and stamps[0] < now - period:
            stamps.popleft()
        return max(0, limit - len(stamps))


def clear() -> None:
    """فقط برای آزمون‌ها."""
    with _lock:
        _buckets.clear()
