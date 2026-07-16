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
    """پردازش رشته تاریخ شمسی → تاریخ میلادی
    
    فرمت: 1405/01/16 یا 1405-01-16
    """
    if not date_str or not date_str.strip():
        return None
    
    date_str = date_str.strip().replace('-', '/')
    
    try:
        parts = date_str.split('/')
        if len(parts) == 3:
            jy = int(parts[0])
            jm = int(parts[1])
            jd = int(parts[2])
            
            if 1300 <= jy <= 1500 and 1 <= jm <= 12 and 1 <= jd <= 31:
                return jalali_to_gregorian(jy, jm, jd)
    except:
        pass
    
    return None


def today_jalali():
    """تاریخ امروز به شمسی"""
    return jdatetime.date.today().strftime('%Y/%m/%d')


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
