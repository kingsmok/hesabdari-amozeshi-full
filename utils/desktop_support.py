"""
کمکی‌های پوسته دسکتاپ (بدون وابستگی به Qt)
══════════════════════════════════════════════════════════════════════════
این تابع‌ها در `app_desktop.py` استفاده می‌شوند اما جدا از Qt نگه داشته شده‌اند
تا بشود آن‌ها را در CI آزمود (محیط تست PyQt6 ندارد). سه باگ واقعی نسخه دسکتاپ
از همین‌جا رفع می‌شود: پورت اشغال‌شده، «سرور آماده» پیش از bind، و مسیر لوگو.
"""
from __future__ import annotations

import os
import socket
import time
from datetime import date

#: پورت پیش‌فرض سرور داخلی
DEFAULT_PORT = 5000

#: چند پورت بعدی را امتحان کنیم؟
PORT_SCAN_LIMIT = 40


def get_local_ip() -> str:
    """IP این سیستم در شبکه محلی (برای نمایش آدرس LAN)؛ در صورت شکست 127.0.0.1."""
    probe = None
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        probe.settimeout(0.5)
        probe.connect(("8.8.8.8", 80))
        return probe.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        if probe is not None:
            try:
                probe.close()
            except Exception:
                pass


def is_port_free(port: int, host: str = '') -> bool:
    """آیا می‌توان روی این پورت bind کرد؟

    host خالی یعنی «همه اینترفیس‌ها»؛ وقتی برنامه فقط روی loopback می‌نشیند
    هم همین آزمون کافی است، چون bind روی '' هر پورت اشغال‌شده‌ای را رد می‌کند.
    """
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        probe.bind((host, int(port)))
        return True
    except OSError:
        return False
    finally:
        try:
            probe.close()
        except Exception:
            pass


def pick_port(start: int = DEFAULT_PORT, limit: int = PORT_SCAN_LIMIT) -> int | None:
    """اولین پورت آزاد از `start`؛ `None` اگر همه اشغال بودند.

    قبلاً `PORT = 5000` ثابت بود و اگر همسایه‌ای همان پورت را گرفته بود،
    سرور bind نمی‌کرد ولی پیام «✓ سرور آماده است!» چاپ می‌شد.
    """
    for offset in range(limit + 1):
        candidate = int(start) + offset
        if is_port_free(candidate):
            return candidate
    return None


def wait_until_serving(port: int, *, timeout: float = 25.0,
                       error: Exception | None = None,
                       path: str = '/login') -> bool:
    """تا سرور واقعاً پاسخ HTTP بدهد صبر می‌کند (bind ≠ پاسخ‌گو).

    پاسخ‌های ۴۰۱/۳۰۲ هم «سروش بالاست» حساب می‌شوند؛ فقط نبودِ اتصال یا
    خطای bind شکست است.
    """
    import urllib.error
    import urllib.request

    url = f'http://127.0.0.1:{int(port)}{path}'
    deadline = time.time() + timeout
    while time.time() < deadline:
        if error is not None:
            return False
        try:
            urllib.request.urlopen(url, timeout=1.0)
            return True
        except urllib.error.HTTPError:
            return True
        except Exception:
            time.sleep(0.25)
    return False


def desktop_log_path(base_dir: str, today: date | None = None) -> str:
    """مسیر فایل لاگ روزانه پوسته دسکتاپ."""
    day = (today or date.today()).isoformat()
    return os.path.join(base_dir, 'logs', f'desktop-{day}.log')


def resolve_logo_path(logo: str | None, base_dir: str) -> str | None:
    """لوگوی ذخیره‌شده در تنظیمات → فایل روی دیسک (یا None).

    `SystemSettings.logo` ممکن است نام فایل، مسیر نسبی `static/uploads/...` یا
    با اسلش ابتدایی ثبت شده باشد؛ هر سه حالت پذیرفته می‌شود و مسیر بیرونی
    (خارج از base_dir) رد می‌شود.
    """
    if not logo:
        return None
    text = str(logo).strip()
    if not text or text.startswith(('http://', 'https://', 'data:')):
        return None
    tail = text.lstrip('/\\')
    if '..' in tail.replace('\\', '/').split('/'):
        return None
    for candidate in (os.path.join(base_dir, tail),
                      os.path.join(base_dir, 'static', tail),
                      os.path.join(base_dir, 'static', 'uploads', tail)):
        candidate = os.path.normpath(candidate)
        if os.path.isfile(candidate):
            return candidate
    return None


def unique_path(directory: str, filename: str) -> str:
    """مسیر یکتای `directory/filename` — اگر وجود داشت «(۱)»، «(۲)» و… می‌گیرد.

    برای ذخیره بی‌سؤالِ فایل‌های پرتکرار (رسید/فیش) لازم است تا فایل قبلی
    بازنویسی نشود.
    """
    safe = os.path.basename((filename or 'download').strip()) or 'download'
    stem, extension = os.path.splitext(safe)
    candidate = os.path.join(directory, safe)
    index = 1
    while os.path.exists(candidate):
        candidate = os.path.join(directory, f'{stem} ({index}){extension}')
        index += 1
        if index > 999:
            return os.path.join(directory, f'{stem}-{int(time.time())}{extension}')
    return candidate


def server_error_text(exc: BaseException | None, port: int) -> str:
    """پیام فارسی قابل‌فهم برای شکست شروع سرور (به‌جای استک‌تریس)."""
    detail = str(exc).strip() if exc is not None else 'سرور پاسخ نداد'
    if '10048' in detail or 'Address already in use' in detail or 'already in use' in detail:
        return (f'پورت {port} توسط برنامه دیگری اشغال است. '
                f'برنامه را با «--port {port + 1}» اجرا کنید.')
    if 'Permission' in detail:
        return f'اجازه bind روی پورت {port} نیست (پورت‌های زیر ۱۰۲۴ ریشه‌ای‌اند).'
    return f'سرور داخلی بالا نیامد (پورت {port}): {detail}'
