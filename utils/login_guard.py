"""
محدودسازی تلاش‌های ناموفق ورود (A3 از بازبینی امنیت/داده)
════════════════════════════════════════════════════════════
پیش از این، `POST /login` هیچ محدودیتی نداشت و فقط `ActivityLog(action='failed_login')`
ثبت می‌شد ⇒ روی میزبانی عمومی (این پروژه برای cPanel هم بسته‌بندی می‌شود)
brute force کاملاً آزاد بود.

قاعده: برای هر زوج «نام کاربری + IP» بیش از `MAX_ATTEMPTS` تلاش ناموفق در
`WINDOW_SECONDS` ⇒ `LOCK_SECONDS` قفل.

چرا در حافظه پروسه؟ برای نصب تک‌پروسی (حالت رایج این برنامه و نسخه دسکتاپ)
کافی و بی‌هزینه است و هیچ جدول/مهاجرتی لازم ندارد. در میزبانی چند-ورکر
هر ورکر شمارش خودش را دارد (ضعف مستندشده در بازبینی)؛ در آن حالت می‌توان
`STATE_BACKEND` را به یک جدول DB یا Redis وصل کرد — تنها نقطه‌ای که باید عوض
شود همین فایل است.
"""
from __future__ import annotations

import threading
import time
from collections import deque

MAX_ATTEMPTS = 5          # چند تلاش ناموفق مجاز است
WINDOW_SECONDS = 15 * 60  # در بازه ۱۵ دقیقه‌ای
LOCK_SECONDS = 10 * 60    # و سپس ۱۰ دقیقه قفل

_lock = threading.Lock()
#: (username, ip) → صف زمان تلاش‌های ناموفق
_failures: dict[tuple[str, str], deque] = {}
#: (username, ip) → زمان آزادسازی قفل (unix)
_locked_until: dict[tuple[str, str], float] = {}


def _key(username, ip) -> tuple[str, str]:
    return (str(username or '').strip().lower()[:64], str(ip or '')[:64])


def failures_of(username, ip) -> int:
    """تعداد تلاش‌های ناموفقِ شمرده‌شده (برای پیام به کاربر)."""
    with _lock:
        stamps = _failures.get(_key(username, ip))
        return len(stamps) if stamps else 0


def lock_remaining(username, ip, now=None) -> int:
    """چند ثانیه تا رفع قفل باقی است (۰ یعنی آزاد)."""
    now = time.time() if now is None else now
    with _lock:
        until = _locked_until.get(_key(username, ip))
        if not until:
            return 0
        return max(0, int(until - now))


def is_locked(username, ip, now=None) -> bool:
    return lock_remaining(username, ip, now) > 0


def register_failure(username, ip, now=None) -> int:
    """ثبت یک تلاش ناموفق؛ تعداد فعلی را برمی‌گرداند و در صورت عبور، قفل می‌کند."""
    now = time.time() if now is None else now
    key = _key(username, ip)
    with _lock:
        stamps = _failures.setdefault(key, deque())
        # تنها تلاش‌های داخل پنجره زمانی شمرده می‌شوند
        cutoff = now - WINDOW_SECONDS
        while stamps and stamps[0] < cutoff:
            stamps.popleft()
        stamps.append(now)
        if len(stamps) >= MAX_ATTEMPTS:
            _locked_until[key] = now + LOCK_SECONDS
            stamps.clear()
            return MAX_ATTEMPTS
        return len(stamps)


def reset(username, ip) -> None:
    """پس از ورود موفق (یا رفع دستی قفل توسط مدیر)."""
    key = _key(username, ip)
    with _lock:
        _failures.pop(key, None)
        _locked_until.pop(key, None)


def lock_message(seconds_left: int) -> str:
    """پیام فارسی قفل — دقیقه‌گرد می‌کند تا «۵۹۹ ثانیه» به کاربر ندهیم."""
    minutes = max(1, int((seconds_left + 59) // 60))
    return (f'به دلیل تلاش‌های ناموفق پیاپی، این حساب برای {minutes:,} دقیقه '
            'موقتاً قفل شده است.')


def clear_all() -> None:
    """فقط برای آزمون‌ها."""
    with _lock:
        _failures.clear()
        _locked_until.clear()
