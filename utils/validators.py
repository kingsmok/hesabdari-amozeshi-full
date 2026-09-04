"""
اعتبارسنجی مرکزی ورودی‌ها — یک منبع واحد برای قواعد فرم‌ها (DRY)
════════════════════════════════════════════
مقادیری که قبلاً در هر route جدا هاردکد می‌شدند (روش پرداخت، دورهٔ شمسی،
نوع مرجع صندوق) اینجا یک‌جا بررسی می‌شوند تا کل پروژه یک رفتار داشته باشد.
"""
from __future__ import annotations

from utils.constants import CASHBOX_REF_TYPES, MAX_MONEY, PAYMENT_METHODS


def normalize_payment_method(value, default: str = 'cash') -> str:
    """روش پرداخت را به مقدار مجاز تبدیل می‌کند؛ ورودی ناشناس → default."""
    value = (value or '').strip().lower()
    return value if value in PAYMENT_METHODS else default


def normalize_ref_type(value, default: str = 'manual') -> str:
    """نوع مرجع تراکنش صندوق؛ ورودی دلخواه کاربر پذیرفته نمی‌شود."""
    value = (value or '').strip().lower()
    return value if value in CASHBOX_REF_TYPES else default


def validate_period(value):
    """بررسی دورهٔ شمسی (مثل «۱۴۰۵/۰۶» یا «1405-06»).

    Returns:
        (normalized, gregorian_start, gregorian_end) یا (None, None, None)
    """
    from utils.jalali import jalali_period_bounds, normalize_jalali_period

    normalized = normalize_jalali_period((value or '').strip())
    if not normalized:
        return None, None, None
    bounds = jalali_period_bounds(normalized)
    if not bounds:
        return None, None, None
    return normalized, bounds[0], bounds[1]


def money_in_range(amount, minimum: float = 0, maximum: float = MAX_MONEY) -> bool:
    """آیا مبلغ در بازهٔ منطقی است؟ (منفی/صفر/انفجاری float رد می‌شود)"""
    try:
        amount = float(amount)
    except (TypeError, ValueError):
        return False
    return minimum <= amount <= maximum
