"""
محاسبه استهلاک دارایی‌های ثابت

روش‌های استاندارد جدول استهلاکات موضوع ماده ۱۴۹ قانون مالیات‌های مستقیم:
- خط مستقیم (Straight Line): (بهای تمام شده − ارزش اسقاط) ÷ عمر مفید
- نزولی (Declining Balance): ارزش دفتری ابتدای دوره × نرخ نزولی

جدول پیش‌فرض گروه‌های پرکاربرد یک آموزشگاه ارائه شده و در فرم قابل تغییر است.
"""
from __future__ import annotations

# گروه‌های متداول دارایی در آموزشگاه بر مبنای جدول ماده ۱۴۹
ASSET_CATEGORIES = [
    {'name': 'ساختمان آموزشی', 'method': 'straight', 'life': 20, 'rate': 7},
    {'name': 'تاسیسات ساختمان (سرمایش/گرمایش)', 'method': 'straight', 'life': 10, 'rate': 15},
    {'name': 'اثاثه و منصوبات اداری و آموزشی', 'method': 'straight', 'life': 10, 'rate': 20},
    {'name': 'رایانه و تجهیزات جانبی', 'method': 'straight', 'life': 3, 'rate': 30},
    {'name': 'تجهیزات صوتی و تصویری کلاس', 'method': 'straight', 'life': 5, 'rate': 25},
    {'name': 'تجهیزات آزمایشگاهی و کارگاهی', 'method': 'declining', 'life': 8, 'rate': 25},
    {'name': 'وسایل نقلیه', 'method': 'declining', 'life': 8, 'rate': 25},
    {'name': 'نرم‌افزار و دارایی نامشهود', 'method': 'straight', 'life': 5, 'rate': 20},
]

CATEGORY_NAMES = [category['name'] for category in ASSET_CATEGORIES]


def category_defaults(name: str) -> dict | None:
    for category in ASSET_CATEGORIES:
        if category['name'] == name:
            return category
    return None


def annual_depreciation(asset, opening_value: float | None = None) -> float:
    """استهلاک یک دوره سالانه را برای دارایی محاسبه می‌کند."""
    cost = float(asset.cost or 0)
    salvage = float(asset.salvage_value or 0)
    accumulated = float(asset.accumulated_depreciation or 0)
    book_value = cost - accumulated if opening_value is None else float(opening_value)

    if book_value <= salvage or cost <= 0:
        return 0.0

    if asset.method == 'declining':
        rate = float(asset.declining_rate or 0) / 100.0
        amount = book_value * rate
    else:
        life = float(asset.useful_life_years or 0)
        if life <= 0:
            return 0.0
        amount = (cost - salvage) / life

    # استهلاک نباید ارزش دفتری را زیر ارزش اسقاط ببرد
    amount = min(amount, book_value - salvage)
    return round(max(amount, 0.0), 2)


def depreciation_schedule(asset, periods: int | None = None) -> list[dict]:
    """جدول کامل استهلاک از ابتدای عمر دارایی (برای پیش‌بینی و گزارش)."""
    cost = float(asset.cost or 0)
    salvage = float(asset.salvage_value or 0)
    if periods is None:
        periods = int(float(asset.useful_life_years or 5)) if asset.method == 'straight' else 15
        periods = max(periods, 1)

    rows = []
    book_value = cost
    accumulated = 0.0
    for index in range(1, periods + 1):
        if book_value - salvage <= 0.5:
            break
        if asset.method == 'declining':
            amount = book_value * float(asset.declining_rate or 0) / 100.0
        else:
            life = float(asset.useful_life_years or 0)
            amount = (cost - salvage) / life if life > 0 else 0
        amount = round(min(amount, book_value - salvage), 2)
        if amount <= 0:
            break
        accumulated += amount
        opening = book_value
        book_value = round(book_value - amount, 2)
        rows.append({
            'period': index,
            'opening_value': round(opening, 2),
            'depreciation': amount,
            'accumulated': round(accumulated, 2),
            'closing_value': book_value,
        })
    return rows
