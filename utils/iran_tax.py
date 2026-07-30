"""
ابزارهای پایه مالیاتی ایران

شامل:
- الگوریتم Verhoeff (رقم کنترلی شماره منحصر به فرد مالیاتی)
- اعتبارسنجی کد ملی، شناسه ملی اشخاص حقوقی، کد اقتصادی و کد فراگیر اتباع
- تولید «شماره منحصر به فرد مالیاتی» ۲۲ کاراکتری مطابق سند
  «قالب شناسه یکتای حافظه مالیاتی و شماره منحصر به فرد مالیاتی»
- الگوهای صورتحساب الکترونیکی سامانه مودیان

مرجع ساختار شماره مالیاتی (۲۲ کاراکتر):
    [۶ کاراکتر شناسه یکتای حافظه مالیاتی]
    [۵ کاراکتر Hex تاریخ ثبت صورتحساب (تعداد روز از 1970/01/01)]
    [۱۰ کاراکتر Hex سریال داخلی صورتحساب]
    [۱ رقم کنترلی Verhoeff]
"""
from __future__ import annotations

from datetime import date, datetime

# ═══════════════════════════════════════════════════════════════
#  الگوریتم Verhoeff
# ═══════════════════════════════════════════════════════════════
_VERHOEFF_D = (
    (0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
    (1, 2, 3, 4, 0, 6, 7, 8, 9, 5),
    (2, 3, 4, 0, 1, 7, 8, 9, 5, 6),
    (3, 4, 0, 1, 2, 8, 9, 5, 6, 7),
    (4, 0, 1, 2, 3, 9, 5, 6, 7, 8),
    (5, 9, 8, 7, 6, 0, 4, 3, 2, 1),
    (6, 5, 9, 8, 7, 1, 0, 4, 3, 2),
    (7, 6, 5, 9, 8, 2, 1, 0, 4, 3),
    (8, 7, 6, 5, 9, 3, 2, 1, 0, 4),
    (9, 8, 7, 6, 5, 4, 3, 2, 1, 0),
)

_VERHOEFF_P = (
    (0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
    (1, 5, 7, 6, 2, 8, 3, 0, 9, 4),
    (5, 8, 0, 3, 7, 9, 6, 1, 4, 2),
    (8, 9, 1, 6, 0, 4, 3, 5, 2, 7),
    (9, 4, 5, 3, 1, 2, 6, 8, 7, 0),
    (4, 2, 8, 6, 5, 7, 3, 9, 0, 1),
    (2, 7, 9, 3, 8, 0, 6, 4, 1, 5),
    (7, 0, 4, 6, 9, 1, 3, 2, 5, 8),
)

_VERHOEFF_INV = (0, 4, 3, 2, 1, 5, 6, 7, 8, 9)


def verhoeff_check_digit(number: str) -> int:
    """رقم کنترلی Verhoeff را برای یک رشته عددی تولید می‌کند."""
    digits = [int(ch) for ch in reversed(str(number)) if ch.isdigit()]
    checksum = 0
    for index, digit in enumerate(digits):
        checksum = _VERHOEFF_D[checksum][_VERHOEFF_P[(index + 1) % 8][digit]]
    return _VERHOEFF_INV[checksum]


def verhoeff_validate(number: str) -> bool:
    """صحت رشته‌ای که رقم کنترلی Verhoeff در انتهای آن قرار دارد."""
    digits = [int(ch) for ch in reversed(str(number)) if ch.isdigit()]
    checksum = 0
    for index, digit in enumerate(digits):
        checksum = _VERHOEFF_D[checksum][_VERHOEFF_P[index % 8][digit]]
    return checksum == 0


# ═══════════════════════════════════════════════════════════════
#  نرمال‌سازی ارقام فارسی/عربی
# ═══════════════════════════════════════════════════════════════
_DIGIT_MAP = str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789')


def normalize_digits(value) -> str:
    """ارقام فارسی/عربی را به لاتین تبدیل و فاصله و خط تیره را حذف می‌کند."""
    if value is None:
        return ''
    text = str(value).translate(_DIGIT_MAP)
    for ch in (' ', '\u200c', '-', '_', '/'):
        text = text.replace(ch, '')
    return text.strip()


# ═══════════════════════════════════════════════════════════════
#  اعتبارسنجی شناسه‌های هویتی
# ═══════════════════════════════════════════════════════════════
def validate_national_code(code) -> bool:
    """اعتبارسنجی الگوریتمی کد ملی ۱۰ رقمی اشخاص حقیقی."""
    code = normalize_digits(code)
    if len(code) != 10 or not code.isdigit():
        return False
    if code == code[0] * 10:  # کدهای تکراری مثل 1111111111 نامعتبرند
        return False
    total = sum(int(code[i]) * (10 - i) for i in range(9))
    remainder = total % 11
    control = int(code[9])
    if remainder < 2:
        return control == remainder
    return control == 11 - remainder


def validate_legal_id(code) -> bool:
    """اعتبارسنجی شناسه ملی ۱۱ رقمی اشخاص حقوقی."""
    code = normalize_digits(code)
    if len(code) != 11 or not code.isdigit():
        return False
    if len(set(code)) == 1:
        return False
    control = int(code[10])
    decimal = int(code[9]) + 2
    weights = (29, 27, 23, 19, 17, 29, 27, 23, 19, 17)
    total = sum((int(code[i]) + decimal) * weights[i] for i in range(10))
    remainder = total % 11
    if remainder == 10:
        remainder = 0
    return remainder == control


def validate_foreigner_id(code) -> bool:
    """کد فراگیر اتباع خارجی ۱۲ رقمی (فقط کنترل ساختاری)."""
    code = normalize_digits(code)
    return len(code) == 12 and code.isdigit()


def validate_economic_code(code) -> bool:
    """کد اقتصادی ۱۲ یا ۱۴ رقمی (کنترل ساختاری طبق فرمت سازمان)."""
    code = normalize_digits(code)
    return code.isdigit() and len(code) in (12, 14)


def detect_party_id_type(code) -> str:
    """نوع شناسه را از روی طول و صحت الگوریتمی تشخیص می‌دهد."""
    code = normalize_digits(code)
    if validate_national_code(code):
        return 'national'      # شخص حقیقی
    if validate_legal_id(code):
        return 'legal'         # شخص حقوقی
    if validate_foreigner_id(code):
        return 'foreigner'     # اتباع خارجی
    return 'unknown'


def validate_party_id(code, party_type: str | None = None) -> tuple[bool, str]:
    """اعتبارسنجی شناسه طرف حساب و برگرداندن پیام فارسی.

    party_type: real (حقیقی) | legal (حقوقی) | foreigner (اتباع) | None (خودکار)
    """
    code = normalize_digits(code)
    if not code:
        return False, 'شناسه وارد نشده است'

    if party_type == 'real':
        return (True, 'کد ملی معتبر است') if validate_national_code(code) \
            else (False, 'کد ملی نامعتبر است (الگوریتم کنترل رقم)')
    if party_type == 'legal':
        return (True, 'شناسه ملی معتبر است') if validate_legal_id(code) \
            else (False, 'شناسه ملی اشخاص حقوقی نامعتبر است')
    if party_type == 'foreigner':
        return (True, 'کد فراگیر پذیرفته شد') if validate_foreigner_id(code) \
            else (False, 'کد فراگیر اتباع باید ۱۲ رقم باشد')

    kind = detect_party_id_type(code)
    messages = {
        'national': 'کد ملی معتبر است',
        'legal': 'شناسه ملی اشخاص حقوقی معتبر است',
        'foreigner': 'کد فراگیر اتباع خارجی',
    }
    if kind == 'unknown':
        return False, 'شناسه با هیچ‌کدام از الگوهای کد ملی/شناسه ملی/کد فراگیر مطابقت ندارد'
    return True, messages[kind]


# ═══════════════════════════════════════════════════════════════
#  شناسه یکتای حافظه مالیاتی و شماره منحصر به فرد مالیاتی
# ═══════════════════════════════════════════════════════════════
# طبق سند سازمان، کاراکترهای I، J، L، Q، V در شناسه حافظه ممنوع هستند.
FORBIDDEN_MEMORY_CHARS = set('IJLQV')
MEMORY_ID_LENGTH = 6
TAX_NUMBER_LENGTH = 22
EPOCH = date(1970, 1, 1)


def validate_memory_id(memory_id) -> tuple[bool, str]:
    """اعتبارسنجی شناسه یکتای حافظه مالیاتی (۶ کاراکتر، بدون I J L Q V)."""
    if not memory_id:
        return False, 'شناسه یکتای حافظه مالیاتی وارد نشده است'
    value = str(memory_id).strip().upper()
    if len(value) != MEMORY_ID_LENGTH:
        return False, 'شناسه یکتای حافظه مالیاتی باید دقیقاً ۶ کاراکتر باشد'
    if not value.isalnum() or not value.isascii():
        return False, 'شناسه حافظه فقط شامل حروف و اعداد انگلیسی است'
    invalid = FORBIDDEN_MEMORY_CHARS & set(value)
    if invalid:
        return False, f"کاراکترهای ممنوعه در شناسه حافظه: {'، '.join(sorted(invalid))}"
    return True, 'شناسه حافظه معتبر است'


def _memory_id_to_decimal(memory_id: str) -> str:
    """هر کاراکتر شناسه حافظه را به معادل ده‌دهی UTF-8 تبدیل می‌کند.

    ارقام به همان مقدار عددی و حروف به کد UTF-8 (مثلاً D→68) تبدیل می‌شوند.
    """
    parts = []
    for ch in str(memory_id).strip().upper():
        parts.append(ch if ch.isdigit() else str(ord(ch)))
    return ''.join(parts)


def date_to_hex(invoice_date: date | datetime | None = None) -> str:
    """تاریخ ثبت صورتحساب → تعداد روز از 1970/01/01 → Hex پنج کاراکتری."""
    if invoice_date is None:
        invoice_date = date.today()
    if isinstance(invoice_date, datetime):
        invoice_date = invoice_date.date()
    days = (invoice_date - EPOCH).days
    if days < 0:
        raise ValueError('تاریخ صورتحساب نمی‌تواند قبل از 1970/01/01 باشد')
    return format(days, 'X').zfill(5)[-5:]


def hex_to_date(hex_value: str) -> date:
    """تبدیل معکوس بخش تاریخ شماره مالیاتی به تاریخ میلادی."""
    from datetime import timedelta
    return EPOCH + timedelta(days=int(hex_value, 16))


def serial_to_hex(serial: int) -> str:
    """سریال داخلی صورتحساب → Hex ده کاراکتری."""
    if serial < 0:
        raise ValueError('سریال داخلی نمی‌تواند منفی باشد')
    value = format(int(serial), 'X').zfill(10)
    if len(value) > 10:
        raise ValueError('سریال داخلی از ظرفیت ۱۰ کاراکتر Hex عبور کرده است')
    return value


def generate_tax_number(memory_id: str, invoice_date: date, serial: int) -> str:
    """تولید شماره منحصر به فرد مالیاتی ۲۲ کاراکتری.

    مثال سند سازمان:
        memory_id=DEF5GH ، تاریخ 1399/04/30 ، سریال 12
        → DEF5GH0481F000000000C2
    """
    ok, message = validate_memory_id(memory_id)
    if not ok:
        raise ValueError(message)

    memory_id = str(memory_id).strip().upper()
    date_hex = date_to_hex(invoice_date)
    serial_hex = serial_to_hex(serial)

    control_source = (
        _memory_id_to_decimal(memory_id)
        + str(int(date_hex, 16)).zfill(6)
        + str(int(serial_hex, 16)).zfill(12)
    )
    check_digit = verhoeff_check_digit(control_source)
    return f'{memory_id}{date_hex}{serial_hex}{check_digit}'


def validate_tax_number(tax_number: str) -> tuple[bool, str]:
    """صحت ساختاری و رقم کنترلی یک شماره منحصر به فرد مالیاتی."""
    if not tax_number:
        return False, 'شماره مالیاتی خالی است'
    value = str(tax_number).strip().upper()
    if len(value) != TAX_NUMBER_LENGTH:
        return False, 'طول شماره مالیاتی باید دقیقاً ۲۲ کاراکتر باشد'
    if not value.isalnum() or not value.isascii():
        return False, 'شماره مالیاتی فقط شامل حروف و اعداد انگلیسی است'

    memory_id, date_hex, serial_hex, check_digit = (
        value[:6], value[6:11], value[11:21], value[21]
    )
    ok, message = validate_memory_id(memory_id)
    if not ok:
        return False, message
    try:
        int(date_hex, 16)
        int(serial_hex, 16)
    except ValueError:
        return False, 'بخش تاریخ یا سریال شماره مالیاتی Hex معتبر نیست'
    if not check_digit.isdigit():
        return False, 'رقم کنترلی باید عدد باشد'

    expected = generate_tax_number(memory_id, hex_to_date(date_hex), int(serial_hex, 16))
    if expected != value:
        return False, 'رقم کنترلی Verhoeff با اجزای شماره مالیاتی مطابقت ندارد'
    return True, 'شماره مالیاتی معتبر است'


def parse_tax_number(tax_number: str) -> dict:
    """تجزیه شماره مالیاتی به مولفه‌های تشکیل‌دهنده برای نمایش در UI."""
    value = str(tax_number or '').strip().upper()
    if len(value) != TAX_NUMBER_LENGTH:
        return {}
    date_hex, serial_hex = value[6:11], value[11:21]
    try:
        issued = hex_to_date(date_hex)
        serial = int(serial_hex, 16)
    except ValueError:
        return {}
    return {
        'memory_id': value[:6],
        'date_hex': date_hex,
        'date': issued,
        'serial_hex': serial_hex,
        'serial': serial,
        'check_digit': value[21],
    }


# ═══════════════════════════════════════════════════════════════
#  الگوهای صورتحساب الکترونیکی
# ═══════════════════════════════════════════════════════════════
# کلید = کد الگو در سامانه مودیان (فیلد ins در هدر صورتحساب)
INVOICE_PATTERNS = {
    '1': {'code': '1', 'name': 'فروش کالا و خدمات', 'requires_buyer': True,  'export': False},
    '2': {'code': '2', 'name': 'فروش ارز',           'requires_buyer': True,  'export': False},
    '3': {'code': '3', 'name': 'طلا، جواهر و پلاتین', 'requires_buyer': True, 'export': False},
    '4': {'code': '4', 'name': 'قرارداد پیمانکاری',  'requires_buyer': True,  'export': False},
    '5': {'code': '5', 'name': 'قبوض خدماتی',        'requires_buyer': True,  'export': False},
    '6': {'code': '6', 'name': 'بلیط هواپیما',       'requires_buyer': True,  'export': False},
    '7': {'code': '7', 'name': 'صادرات',             'requires_buyer': False, 'export': True},
}

# نوع صورتحساب (inty): ۱ اطلاعات کامل خریدار، ۲ مصرف‌کننده نهایی، ۳ رسید کارتخوان
INVOICE_TYPES = {
    '1': 'نوع اول — با اطلاعات کامل خریدار (B2B)',
    '2': 'نوع دوم — مصرف‌کننده نهایی (B2C)',
    '3': 'نوع سوم — رسید پرداخت کارتخوان',
}

# موضوع صورتحساب (inp): ۱ اصلی، ۲ اصلاحی، ۳ ابطالی، ۴ برگشت از فروش
INVOICE_SUBJECTS = {
    '1': 'اصلی',
    '2': 'اصلاحی',
    '3': 'ابطالی',
    '4': 'برگشت از فروش',
}


def pattern_name(code) -> str:
    pattern = INVOICE_PATTERNS.get(str(code or ''))
    return pattern['name'] if pattern else '-'
