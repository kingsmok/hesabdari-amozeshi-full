"""
موتور قواعد مالیات حقوق و بیمه (قابل تنظیم به تفکیک سال)

چرا این فایل اضافه شد؟
    در نسخه قبلی، جدول «براکت‌های مالیاتی ۱۴۰۵» به‌صورت ثابت در `routes/tax.py`
    نوشته شده بود، اما اعداد آن مربوط به سال ۱۴۰۴ بود و به‌صورت «سالانه» اعمال
    می‌شد؛ در نتیجه مالیات همه تقریباً صفر محاسبه می‌شد. طبق ماده ۱ قانون بودجه
    ۱۴۰۵، سقف معافیت سالانه ۴۸۰۰ میلیون ریال (۴۰ میلیون تومان در ماه) است و
    مازاد آن پلکانی محاسبه می‌شود.

ساختار:
    - مقادیر پیش‌فرض داخل کد (DEFAULT_RULES) — فقط سال ۱۴۰۵.
    - در صورت وجود جدول `tax_rules`، ردیف فعال همان سال از دیتابیس خوانده می‌شود؛
      پس تصویب بخشنامه سال بعد نیازمند ویرایش کد نیست.
"""
from __future__ import annotations

import json

# ═══════════════════════════════════════════
#  پیش‌فرض‌ها
# ═══════════════════════════════════════════
#: پلکان‌های ماهانه حقوق ۱۴۰۵ (تومان). مازاد بر هر پله با نرخ همان پله.
DEFAULT_RULES: dict[str, dict] = {
    '1405': {
        'monthly_exemption': 40_000_000,
        'brackets': [
            {'from': 40_000_000, 'to': 80_000_000, 'rate': 0.10},
            {'from': 80_000_000, 'to': 100_000_000, 'rate': 0.15},
            {'from': 100_000_000, 'to': 120_000_000, 'rate': 0.20},
            {'from': 120_000_000, 'to': 140_000_000, 'rate': 0.25},
            {'from': 140_000_000, 'to': None, 'rate': 0.30},
        ],
        'insurance_employee_rate': 0.07,
        'insurance_employer_rate': 0.23,
        'note': 'ماده ۱ قانون بودجه ۱۴۰۵ — معافیت ماهانه ۴۰ میلیون تومان، '
                'سقف پلکان آخر ۳۰٪؛ حق بیمه ۷٪ سهم بیمه‌شده و ۲۳٪ سهم کارفرما.',
    },
}

BRACKET_LABELS = {0.10: '۱۰٪', 0.15: '۱۵٪', 0.20: '۲۰٪', 0.25: '۲۵٪', 0.30: '۳۰٪',
                  0.35: '۳۵٪', 0.0: 'معاف'}

_CACHE: dict[str, dict] = {}


def invalidate_rule_cache() -> None:
    """پس از ذخیره قواعد در «تنظیمات مالیاتی» فراخوانی می‌شود."""
    _CACHE.clear()


def current_year() -> str:
    from utils.jalali import current_jalali_period
    return current_jalali_period().split('/')[0]


def get_rule(year: str | None = None) -> dict:
    """قاعده یک سال: ابتدا جدول tax_rules، سپس پیش‌فرض کد، در نهایت آخرین سال موجود."""
    from utils.jalali import normalize_jalali_period

    if year:
        normalized = normalize_jalali_period(year)
        year = normalized.split('/')[0] if normalized else str(year).strip()[:4]
    else:
        year = current_year()

    if year in _CACHE:
        return _CACHE[year]

    rule = None
    try:
        from models.system import TaxRule
        row = TaxRule.query.filter_by(year=year, is_active=True).first() \
            or TaxRule.query.filter_by(year=year).first()
        if row is not None:
            brackets = None
            if row.brackets:
                try:
                    brackets = json.loads(row.brackets)
                except Exception:
                    brackets = None
            rule = {
                'year': year,
                'monthly_exemption': row.monthly_exemption or 0,
                'brackets': normalize_brackets(brackets or []),
                'insurance_employee_rate': row.insurance_employee_rate
                if row.insurance_employee_rate is not None else 0.07,
                'insurance_employer_rate': row.insurance_employer_rate
                if row.insurance_employer_rate is not None else 0.23,
                'note': row.note or '',
                'source': 'database',
            }
    except Exception:
        rule = None                      # جدول هنوز ساخته نشده (نصب قدیمی)

    if rule is None:
        default = DEFAULT_RULES.get(year) or DEFAULT_RULES[max(DEFAULT_RULES)]
        rule = {
            'year': year,
            'monthly_exemption': default['monthly_exemption'],
            'brackets': [dict(item) for item in default['brackets']],
            'insurance_employee_rate': default['insurance_employee_rate'],
            'insurance_employer_rate': default['insurance_employer_rate'],
            'note': default['note'],
            'source': 'code-default',
        }
    rule.setdefault('year', year)
    _CACHE[year] = rule
    return rule


def normalize_brackets(raw) -> list[dict]:
    """پاک‌سازی پلکان‌های ورودی: حذف نامعتبر، مرتب‌سازی و نرخ صحیح روی آخرین پله."""
    cleaned = []
    for item in raw or []:
        try:
            rate = float(item.get('rate', 0) or 0)
        except (TypeError, ValueError):
            continue
        if rate <= 0 or rate >= 1:
            continue
        start = item.get('from', item.get('min'))
        end = item.get('to', item.get('max'))
        try:
            start = float(start) if start not in (None, '') else 0.0
        except (TypeError, ValueError):
            continue
        try:
            end = float(end) if end not in (None, '', 0) else None
        except (TypeError, ValueError):
            end = None
        cleaned.append({'from': start, 'to': end, 'rate': rate})

    cleaned.sort(key=lambda item: item['from'])
    for index, item in enumerate(cleaned):
        if index == len(cleaned) - 1:
            item['to'] = None
        elif item['to'] is None:
            item['to'] = cleaned[index + 1]['from']
        item['label'] = BRACKET_LABELS.get(item['rate'], f"{item['rate'] * 100:g}٪")
    return cleaned


# ═══════════════════════════════════════════
#  محاسبه
# ═══════════════════════════════════════════
def _progressive(amount: float, exemption: float, brackets: list[dict], scale: float = 1.0):
    """محاسبه پلکانی.

    `scale` فقط آستانه‌ها را مقیاس می‌کند: برای محاسبه سالانه، پلکان ماهانه × ۱۲
    و مبلغ همان رقم سالیانه است (پیش‌تر مبلغ هم ضرب می‌شد و مالیات سالانه
    چند برابر خروجی می‌شد).
    """
    taxable = float(amount or 0)
    exempt = float(exemption or 0) * scale
    if taxable <= exempt:
        return 0.0, [{'label': 'معاف', 'from': 0, 'to': exempt, 'taxable': taxable,
                      'rate': 0.0, 'tax': 0.0}]

    total = 0.0
    breakdown = [{'label': 'معاف', 'from': 0, 'to': exempt, 'taxable': min(taxable, exempt),
                  'rate': 0.0, 'tax': 0.0}]
    for bracket in brackets:
        low = float(bracket['from']) * scale
        high = (float(bracket['to']) * scale) if bracket.get('to') is not None else None
        if taxable <= low:
            break
        upper = taxable if high is None else min(taxable, high)
        slice_amount = upper - low
        if slice_amount <= 0:
            continue
        tax = slice_amount * bracket['rate']
        total += tax
        breakdown.append({'label': bracket.get('label') or BRACKET_LABELS.get(bracket['rate'], ''),
                          'from': low, 'to': high if high is not None else taxable,
                          'taxable': slice_amount, 'rate': bracket['rate'], 'tax': tax})
    return round(total), breakdown


def calculate_salary_tax_monthly(monthly_salary: float, year: str | None = None):
    """مالیات یک ماه حقوق → (amount, breakdown). مبنای قانونی: پلکان ماهانه."""
    rule = get_rule(year)
    return _progressive(monthly_salary, rule['monthly_exemption'], rule['brackets'])


def calculate_salary_tax_annual(annual_salary: float, year: str | None = None):
    """مالیات جمع سالیانه (برای گزارش ماده ۸۵) — همان پلکان‌ها × ۱۲."""
    rule = get_rule(year)
    return _progressive(annual_salary, rule['monthly_exemption'], rule['brackets'], scale=12.0)


def annual_brackets_display(year: str | None = None) -> list[dict]:
    """نمایش سالانه پلکان‌ها برای صفحه محاسبه‌گر (مقادیر × ۱۲ تومان)."""
    rule = get_rule(year)
    rows = [{'min': 0, 'max': rule['monthly_exemption'] * 12, 'rate': 0.0, 'label': 'معاف'}]
    for bracket in rule['brackets']:
        rows.append({'min': bracket['from'] * 12,
                     'max': (bracket['to'] * 12) if bracket['to'] is not None else None,
                     'rate': bracket['rate'], 'label': bracket.get('label', '')})
    return rows


def suggested_insurance(monthly_base: float, year: str | None = None,
                        employer_share: bool = False) -> float:
    """حق بیمه پیشنهادی؛ سهم کارمند پیش‌فرض ۷٪ و سهم کارفرما ۲۳٪."""
    rule = get_rule(year)
    rate = rule['insurance_employer_rate'] if employer_share else rule['insurance_employee_rate']
    return round(float(monthly_base or 0) * (rate or 0))
