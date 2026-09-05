"""
پروفایل منابع اجرا — هاست ضعیف / RAM کم / Passenger
════════════════════════════════════════════════════════════════
نسخهٔ وب روی هاست اشتراکی یا سیستم کند اگر مثل دسکتاپ رفتار کند
(چند ورکر، اسکن کامل جداول در بوت، تایم‌اوت ۱۰ثانیهٔ لایسنس با ۳ تلاش)
به ۵۰۰ و timeout می‌رسد؛ این ماژول یک پرچم واحد می‌دهد.
"""
from __future__ import annotations

import os


def is_low_resource() -> bool:
    """آیا باید با کمترین مصرف RAM/CPU بالا بیاییم؟"""
    flag = os.environ.get('ACADEMY_LOW_RESOURCE', '').strip().lower()
    if flag in ('1', 'true', 'yes', 'on'):
        return True
    if flag in ('0', 'false', 'no', 'off'):
        return False
    # Passenger روی هاست اشتراکی تقریباً همیشه RAM محدود دارد
    if os.environ.get('PASSENGER_APP_ENV'):
        return True
    mem = available_ram_mb()
    return mem is not None and mem < 400


def available_ram_mb() -> int | None:
    """RAM در دسترس (مگابایت) — None اگر قابل تشخیص نباشد."""
    try:
        with open('/proc/meminfo', encoding='utf-8') as handle:
            for line in handle:
                if line.startswith('MemAvailable:'):
                    return int(line.split()[1]) // 1024
                if line.startswith('MemFree:'):
                    # fallback قدیمی‌تر
                    free = int(line.split()[1]) // 1024
                    return free
    except (OSError, ValueError):
        pass
    return None


def sqlite_cache_kib() -> int:
    """اندازهٔ کش صفحهٔ SQLite (کیلو‌بایت منفی = کیلوبایت)."""
    if is_low_resource():
        return -2000   # ۲ مگ
    return -8000       # ۸ مگ
