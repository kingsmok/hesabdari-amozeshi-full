"""
ثابت‌های مرکزی برنامه — یک منبع واحد برای مقادیر تکرارشونده (DRY)
════════════════════════════════════════════
قبلاً «روش‌های پرداخت مجاز» در ۳ فایل هاردکد بودند، «نوع قرارداد/شخص» فقط در
payroll و نام برنامه در چند جا — هر بار تغییر = جستجو در کل پروژه.
"""
from __future__ import annotations

import os

APP_NAME = 'آکادمی منیجر پرو'
APP_DESCRIPTION = 'نرم‌افزار حسابداری و مدیریت آموزشگاه'

#: نسخهٔ برنامه از فایل VERSION (آمادهٔ ارتقا بدون ویرایش کد)
def _read_version() -> str:
    try:
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            'VERSION')
        with open(path, encoding='utf-8') as handle:
            return handle.read().strip() or '1.0.0'
    except OSError:
        return '1.0.0'


APP_VERSION = _read_version()

#: روش‌های پرداخت پشتیبانی‌شده (پول نقد/کارت/آنلاین/چک/ترکیبی)
PAYMENT_METHODS = frozenset({'cash', 'card', 'online', 'check', 'combined'})

#: نوع مرجع تراکنش صندوق — بعد از این، ورودیِ آزاد کاربر پذیرفته نمی‌شود
CASHBOX_REF_TYPES = frozenset({'manual', 'payment', 'expense', 'salary', 'transfer'})

#: سقف مبلغ مالی (جلوگیری از ورودی فوق‌بزرگ/بی‌منطق float)
MAX_MONEY = 10 ** 12

#: نوع قرارداد حقوقی (کلید → برچسب فارسی)
CONTRACT_TYPES = {
    'fixed': 'ثابت ماهانه',
    'hourly': 'ساعتی',
    'session': 'جلسه‌ای',
    'percentage': 'درصدی از شهریه',
    'combined': 'ترکیبی (ساعتی + درصدی)',
}

#: نوع شخصِ حقوق‌بگیر (کلید → برچسب فارسی)
PERSON_TYPES = {'teacher': 'مدرس', 'employee': 'کارمند', 'manager': 'مدیر'}

# ══════════════════════════════════════════════════════════════
#  حساب پیش‌فرض نصب تازه
# ══════════════════════════════════════════════════════════════
# در نصب تازه (هیچ کاربری وجود ندارد) این حساب مدیر خودکار ساخته می‌شود تا
# کاربر بدون ویزارد هم بتواند وارد شود. با متغیر محیطی قابل بازتعریف است:
#   ACADEMY_ADMIN_USER / ACADEMY_ADMIN_PASSWORD
# اگر نصب‌کننده (config.ini) مدیر خودش را داشته باشد، آن مدیر ساخته می‌شود و
# این پیش‌فرض نادیده گرفته می‌شود (bootstrap/defaults.py).
#: نام کاربری پیش‌فرض
FALLBACK_ADMIN_USERNAME = 'admin'
#: رمز پیش‌فرض — ۸ نویسه (حداقل سیاست رمز سیستم)؛ پس از ورود عوض شود
FALLBACK_ADMIN_PASSWORD = 'admin123'


def default_admin_username() -> str:
    """نام کاربری پیش‌فرض مدیر (قابل بازتعریف با ACADEMY_ADMIN_USER)."""
    return (os.environ.get('ACADEMY_ADMIN_USER') or FALLBACK_ADMIN_USERNAME).strip() \
        or FALLBACK_ADMIN_USERNAME


def default_admin_password() -> str:
    """رمز پیش‌فرض مدیر (قابل بازتعریف با ACADEMY_ADMIN_PASSWORD)."""
    return os.environ.get('ACADEMY_ADMIN_PASSWORD') or FALLBACK_ADMIN_PASSWORD


def is_default_admin_password(username: str, password: str) -> bool:
    """آیا این مشخصات همان پیش‌فرض کارخانه است؟ (برای هشدار امنیتی پس از ورود)."""
    try:
        return (username or '') == default_admin_username() \
            and (password or '') == default_admin_password()
    except Exception:
        return False
