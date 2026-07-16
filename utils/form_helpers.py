"""
کمک‌کننده فرم‌ها — تبدیل تاریخ شمسی و مقادیر عددی امن
"""
from utils.jalali import parse_jalali_date


def get_jalali_date(form, field_name):
    """دریافت تاریخ شمسی از فرم و تبدیل به میلادی"""
    value = form.get(field_name, '').strip()
    if value:
        return parse_jalali_date(value)
    return None


def get_jalali_date_or_default(form, field_name, default=None):
    """دریافت تاریخ شمسی با مقدار پیش‌فرض"""
    result = get_jalali_date(form, field_name)
    return result if result else default


def safe_float(value, default=0.0):
    """تبدیل امن به float — مقاوم در برابر رشته خالی و None"""
    if value is None or value == '':
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def safe_int(value, default=0):
    """تبدیل امن به int — مقاوم در برابر رشته خالی و None"""
    if value is None or value == '':
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def form_float(form, field_name, default=0.0):
    """دریافت مقدار اعشاری امن از فرم"""
    return safe_float(form.get(field_name), default)


def form_int(form, field_name, default=0):
    """دریافت مقدار عددی امن از فرم"""
    return safe_int(form.get(field_name), default)


def form_str(form, field_name, default=''):
    """دریافت رشته از فرم"""
    return form.get(field_name, default).strip()
