"""
تبدیل تاریخ شمسی ↔ میلادی — با jdatetime (کتابخانه استاندارد)
"""
import jdatetime
from datetime import date, datetime


def jalali_to_gregorian(jy, jm, jd):
    """تبدیل شمسی به میلادی"""
    try:
        return jdatetime.date(jy, jm, jd).togregorian()
    except:
        return None


def gregorian_to_jalali(g_date):
    """تبدیل میلادی به شمسی → رشته YYYY/MM/DD"""
    if g_date is None:
        return ''
    try:
        if isinstance(g_date, datetime):
            g_date = g_date.date()
        j = jdatetime.date.fromgregorian(date=g_date)
        return f'{j.year}/{j.month:02d}/{j.day:02d}'
    except:
        return str(g_date)


def gregorian_to_jalali_obj(g_date):
    """تبدیل میلادی به شمسی → شیء jdatetime"""
    if g_date is None:
        return None
    try:
        if isinstance(g_date, datetime):
            g_date = g_date.date()
        return jdatetime.date.fromgregorian(date=g_date)
    except:
        return None


def parse_jalali_date(date_str):
    """پردازش تاریخ فرم به میلادی.

    فرمت شمسی 1405/01/16 و فرمت استاندارد میلادی 2026-04-05 پذیرفته می‌شود
    تا فرم حتی در صورت غیرفعال بودن JavaScript نیز اطلاعات را از دست ندهد.
    """
    if not date_str or not str(date_str).strip():
        return None

    normalized = str(date_str).strip().translate(
        str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789')
    ).replace('-', '/')

    try:
        parts = normalized.split('/')
        if len(parts) != 3:
            return None
        year, month, day = map(int, parts)

        if 1300 <= year <= 1500:
            return jalali_to_gregorian(year, month, day)
        if 1700 <= year <= 2500:
            return date(year, month, day)
    except (ValueError, TypeError):
        return None
    return None


def today_jalali():
    """تاریخ امروز به شمسی"""
    return jdatetime.date.today().strftime('%Y/%m/%d')


def current_jalali_year():
    """سال جاری شمسی برای شماره‌گذاری پویا."""
    return str(jdatetime.date.today().year)


def jalali_month_name(month_num):
    """نام ماه شمسی"""
    months = {
        1: 'فروردین', 2: 'اردیبهشت', 3: 'خرداد',
        4: 'تیر', 5: 'مرداد', 6: 'شهریور',
        7: 'مهر', 8: 'آبان', 9: 'آذر',
        10: 'دی', 11: 'بهمن', 12: 'اسفند'
    }
    return months.get(month_num, '')


def jalali_weekday_name(weekday):
    """نام روز هفته شمسی (شنبه=0)"""
    days = ['شنبه', 'یکشنبه', 'دوشنبه', 'سه‌شنبه', 'چهارشنبه', 'پنجشنبه', 'جمعه']
    return days[weekday] if 0 <= weekday < 7 else ''


# ══════════════════════════════════════════════════════════════
#  دوره‌های شمسی (ماه/سال) — برای حقوق، مالیات و گزارش‌های ماهانه
# ══════════════════════════════════════════════════════════════

_PERIOD_RE = None


def normalize_jalali_period(value):
    """هر شکل نوشتاری دوره را به `YYYY/MM` شمسی تبدیل می‌کند.

    ورودی‌های پذیرفته: 1405/06، 1405-6، 1405.06، ۱۴۰۵/۰۶، '1405'.
    اگر سال میلادی داده شود (۱۷۰۰..۲۵۰۰) به شمسی تبدیل می‌شود.
    خروجی None یعنی ورودی قابل فهمیدن نیست.
    """
    import re
    global _PERIOD_RE
    if _PERIOD_RE is None:
        _PERIOD_RE = re.compile(r'^\s*(\d{4})\s*[/\-.]\s*(\d{1,2})\s*$')
    if value is None:
        return None
    text = str(value).strip().translate(
        str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789'))
    if not text:
        return None

    match = _PERIOD_RE.match(text)
    if match:
        year, month = int(match.group(1)), int(match.group(2))
    elif re.match(r'^\d{6}$', text):          # 140506
        year, month = int(text[:4]), int(text[4:])
    elif re.match(r'^\d{4}$', text):          # فقط سال → ۱۲ ماه همان سال
        year, month = int(text), 1
    else:
        return None

    if not (1 <= month <= 12):
        return None
    if 1700 <= year <= 2600:                  # میلادی داده شده؛ به دوره شمسی متناظر تبدیل کن
        try:
            j = jdatetime.date.fromgregorian(year=year, month=month, day=1)
            year, month = j.year, j.month
        except Exception:
            return None
    if not (1300 <= year <= 1700) or not (1 <= month <= 12):
        return None
    return f'{year}/{month:02d}'


def jalali_month_bounds(today=None):
    """ابتدا و انتهای ماه شمسی جاری (تاریخ میلادی) → (start_date, end_date)."""
    return jalali_period_bounds(current_jalali_period(today))


def jalali_months_back(count=12):
    """`count` ماه شمسی اخیر → `[('1404/12', start, end), …]` از قدیم به جدید.

    برای نمودارهای ۱۲/۶‌ماهه؛ جای حلقه‌هایی مثل `today - timedelta(days=30*i)`
    که ماه را جابه‌جا می‌کردند و هر ماه را ۳۰ روز می‌شمردند (سبد ماه‌ها با
    تقویم شمسیِ کاربر یکی نیست).
    """
    out = []
    for period in reversed(recent_jalali_periods(count)):
        bounds = jalali_period_bounds(period)
        if bounds:
            out.append((period, bounds[0], bounds[1]))
    return out


def jalali_period_bounds(period):
    """بازه میلادیِ یک دوره شمسی → (start_date, end_date) شامل دو سر.

    برای محاسبه حقوق و گزارش‌های ماهانه ضروری است؛ پنجره‌های میلادی
    (`today.replace(day=1)`) با ماه شمسی هم‌خوانی ندارند.
    """
    from datetime import date
    normalized = normalize_jalali_period(period)
    if not normalized:
        return None
    year, month = (int(part) for part in normalized.split('/'))
    try:
        start = jdatetime.date(year, month, 1).togregorian()
    except Exception:
        return None
    if month == 12:
        end_j = jdatetime.date(year + 1, 1, 1)
    else:
        end_j = jdatetime.date(year, month + 1, 1)
    end = end_j.togregorian()
    return date(start.year, start.month, start.day), date(end.year, end.month, end.day) - _one_day()


def _one_day():
    from datetime import timedelta
    return timedelta(days=1)


def current_jalali_period(today=None):
    """دوره جاری به شکل `1405/06`.

    `today` (میلادی) برای آزمون و برای محاسبه «ماه» یک تاریخ مشخص به کار
    می‌آید. جایگزین درستِ `datetime.now().replace(day=1)` است: پنجره میلادی
    با ماه شمسی هم‌خوانی ندارد و ~۲۰ روز اول هر ماه، آمار ماه قبل را داخل
    «ماه جاری» می‌آورد.
    """
    if today is None:
        jdate = jdatetime.date.today()
    else:
        if hasattr(today, 'date'):
            today = today.date()
        jdate = jdatetime.date.fromgregorian(date=today)
    return f'{jdate.year:04d}/{jdate.month:02d}'


def jalali_period_label(period):
    """برچسب خوانا: `1405/06` → `شهریور ۱۴۰۵`."""
    normalized = normalize_jalali_period(period)
    if not normalized:
        return str(period or '')
    year, month = (int(part) for part in normalized.split('/'))
    return f'{jalali_month_name(month)} {year}'


def jalali_month_start(g_date=None):
    """اول ماه شمسیِ یک تاریخ میلادی (برای آمار «این ماه»)."""
    from datetime import date
    if g_date is None:
        g_date = date.today()
    elif hasattr(g_date, 'date'):
        g_date = g_date.date()
    j = jdatetime.date.fromgregorian(date=g_date)
    g = jdatetime.date(j.year, j.month, 1).togregorian()
    return date(g.year, g.month, g.day)


def recent_jalali_periods(count=18):
    """فهرست دوره‌های اخیر شمسی (از جاری به عقب) برای انتخاب‌گر فرم‌ها."""
    today = jdatetime.date.today()
    year, month = today.year, today.month
    periods = []
    for _ in range(max(1, int(count))):
        periods.append(f'{year}/{month:02d}')
        month -= 1
        if month == 0:
            month, year = 12, year - 1
    return periods
