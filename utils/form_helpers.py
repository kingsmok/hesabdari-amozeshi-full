"""
کمک‌کننده فرم‌ها — تبدیل تاریخ شمسی و مقادیر عددی امن
"""
import re

from utils.jalali import parse_jalali_date

_DIGIT_TRANSLATION = str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789')
_NUMBER_CLEAN_RE = re.compile(r'[^0-9.,\-+eE]')


def parse_number(value, default=None):
    """تبدیل متن فرم به عدد، با تحمل نگارش واقعی کاربران.

    فارسی/عربی («۹٬۰۰۰٬۰۰۰»)، جداکننده هزارگان («9,000,000» یا «1.234.567»)،
    ممیز فارسی («۱۲٫۵»)، واحد («تومان»، «ریال»)، فاصله و نیم‌فاصله.
    اگر تبدیل ممکن نبود مقدار default برمی‌گردد (در safe_float/safe_int صفر).
    """
    if value is None:
        return default if default is not None else 0.0
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)

    fallback = default if default is not None else 0.0
    text = str(value).strip()
    if not text:
        return fallback

    text = text.translate(_DIGIT_TRANSLATION)
    text = text.replace('\u200c', ' ').replace('\u200e', '').replace('\u200f', '')
    text = text.replace('\u066b', '.').replace('\u066c', ',')   # ممیز/جداکننده فارسی
    # حذف واحد پول و متن اضافه
    text = re.sub(r'(\s*(ریال|تومان|ريال|Rial|Toman|IRR|RT)\s*)', ' ', text, flags=re.I)
    text = _NUMBER_CLEAN_RE.sub('', text)
    if not text or not any(ch.isdigit() for ch in text):
        return fallback

    sign = -1.0 if text.startswith('-') else 1.0
    text = text.lstrip('+-')
    if 'e' in text.lower():
        text = text.lower().replace('e', 'e')     # نمای علمی را دست نمی‌زنیم

    dot, comma = text.rfind('.'), text.rfind(',')
    last = max(dot, comma)
    if last == -1:
        number = float(text)
    else:
        tail = text[last + 1:]
        head = text[:last]
        # جداکننده آخر اگر ۱ یا ۲ رقم بعدش باشد ممیز است، وگرنه هزارگان
        is_decimal = 1 <= len(tail) <= 2 and (tail.isdigit() or tail == '')
        if is_decimal:
            cleaned_head = head.replace(',', '').replace('.', '')
            number = float(f'{cleaned_head or "0"}.{tail or 0}')
        else:
            number = float((head + tail).replace(',', '').replace('.', '') or 0)
    return sign * number


def rial_to_toman(value):
    """ریال → تومان (دیتابیس ریال نگه می‌دارد؛ فرم‌ها تومان می‌گیرند)."""
    return (parse_number(value, 0.0) or 0.0) / 10


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
    """تبدیل امن به float — رشته خالی، ارقام فارسی و جداکننده هزارگان."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return default
    try:
        return parse_number(value, default)
    except Exception:
        return default


def safe_int(value, default=0):
    """تبدیل امن به int — همان تحمل نگارش safe_float و گرد کردن به پایین."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return default
    try:
        result = parse_number(value, default)
        return default if result is None else int(result)
    except (TypeError, ValueError):
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
