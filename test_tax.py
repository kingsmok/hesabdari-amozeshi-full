"""بررسی فنی ماژول‌های مالیاتی (سامانه مودیان، ارزش افزوده، استهلاک).

اجرا:
    python test_tax.py

این اسکریپت هیچ درخواستی به سرور سازمان امور مالیاتی ارسال نمی‌کند و
داده‌ای از دیتابیس حذف نمی‌کند.
"""
from datetime import date
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

failures = []


def check(title, condition, detail=''):
    icon = '✅' if condition else '❌'
    print(f' {icon} {title}' + (f' — {detail}' if detail else ''))
    if not condition:
        failures.append(title)


def test_tax_number():
    from utils.iran_tax import (generate_tax_number, parse_tax_number,
                                validate_memory_id, validate_tax_number,
                                verhoeff_check_digit, verhoeff_validate)

    print('\n[شماره منحصر به فرد مالیاتی]')
    # مثال‌های رسمی سند «قالب شناسه یکتای حافظه مالیاتی»
    sample_date = date(2020, 7, 20)  # 1399/04/30
    check('نمونه ۱ سند سازمان (سریال 0xC)',
          generate_tax_number('DEF5GH', sample_date, 0xC) == 'DEF5GH0481F000000000C2',
          generate_tax_number('DEF5GH', sample_date, 0xC))
    check('نمونه ۲ سند سازمان (سریال 0x1FED)',
          generate_tax_number('DEF5GH', sample_date, 0x1FED).startswith('DEF5GH0481F0000001FED'),
          generate_tax_number('DEF5GH', sample_date, 0x1FED))

    number = generate_tax_number('A1B2C3', date(2026, 3, 21), 4096)
    check('طول شماره تولیدی ۲۲ کاراکتر است', len(number) == 22, number)
    check('اعتبارسنجی شماره تولیدی موفق است', validate_tax_number(number)[0])
    check('دستکاری رقم کنترلی شناسایی می‌شود',
          not validate_tax_number(number[:-1] + ('0' if number[-1] != '0' else '1'))[0])

    parsed = parse_tax_number(number)
    check('تجزیه شماره، تاریخ صحیح برمی‌گرداند', parsed['date'] == date(2026, 3, 21))
    check('تجزیه شماره، سریال صحیح برمی‌گرداند', parsed['serial'] == 4096)

    check('کاراکتر ممنوعه I در شناسه حافظه رد می‌شود', not validate_memory_id('AIB2C3')[0])
    check('شناسه حافظه کوتاه رد می‌شود', not validate_memory_id('AB12')[0])
    check('Verhoeff روی رشته با رقم کنترلی معتبر است',
          verhoeff_validate('236' + str(verhoeff_check_digit('236'))))


def test_identity_validation():
    from utils.iran_tax import (detect_party_id_type, normalize_digits,
                                validate_economic_code, validate_legal_id,
                                validate_national_code, validate_party_id)

    print('\n[اعتبارسنجی کد ملی و شناسه ملی]')
    check('کد ملی معتبر پذیرفته می‌شود', validate_national_code('0499370899'))
    check('کد ملی با رقم کنترلی غلط رد می‌شود', not validate_national_code('0499370898'))
    check('کد ملی تکراری (۱۱۱۱۱۱۱۱۱۱) رد می‌شود', not validate_national_code('1111111111'))
    check('ارقام فارسی نرمال‌سازی می‌شوند', validate_national_code('۰۴۹۹۳۷۰۸۹۹'))
    check('شناسه ملی حقوقی معتبر پذیرفته می‌شود', validate_legal_id('10380284790'))
    check('شناسه ملی با رقم کنترلی غلط رد می‌شود', not validate_legal_id('10380284791'))
    check('کد اقتصادی ۱۲ رقمی پذیرفته می‌شود', validate_economic_code('411111111111'))
    check('کد اقتصادی ۱۰ رقمی رد می‌شود', not validate_economic_code('4111111111'))
    check('تشخیص خودکار نوع شناسه حقیقی', detect_party_id_type('0499370899') == 'national')
    check('تشخیص خودکار نوع شناسه حقوقی', detect_party_id_type('10380284790') == 'legal')
    check('پیام فارسی برای شناسه نامعتبر بازگردانده می‌شود',
          validate_party_id('123', 'real')[0] is False)
    check('نرمال‌سازی خط تیره و فاصله', normalize_digits(' 049-937 0899 ') == '0499370899')


def test_vat_and_invoice(app):
    from extensions import db
    from models.tax import TaxInvoice, TaxInvoiceItem, TaxSettings
    from utils.moadian import MoadianClient, build_invoice_payload

    print('\n[ارزش افزوده و صورتحساب]')
    with app.app_context():
        settings = TaxSettings.get()
        settings.memory_id = settings.memory_id or 'A1B2C3'
        settings.client_id = settings.client_id or settings.memory_id
        settings.seller_tin = settings.seller_tin or '10380284790'
        settings.sandbox_mode = True
        settings.vat_rate = 10
        db.session.commit()

        invoice = TaxInvoice(invoice_number='TEST-VAT-CHECK', direction='sale',
                             invoice_date=date.today(), pattern='1', invoice_type='2')
        db.session.add(invoice)
        db.session.flush()
        db.session.add(TaxInvoiceItem(invoice_id=invoice.id, row_number=1, title='دوره مشمول',
                                      quantity=2, unit_price=1_000_000, discount=200_000,
                                      vat_exempt=False, vat_rate=10))
        db.session.add(TaxInvoiceItem(invoice_id=invoice.id, row_number=2, title='دوره معاف',
                                      quantity=1, unit_price=500_000, vat_exempt=True))
        db.session.flush()
        invoice.recalculate(10)

        check('مبلغ مشمول پس از تخفیف درست است', invoice.total_taxable == 1_800_000, invoice.total_taxable)
        check('مبلغ معاف جدا محاسبه می‌شود', invoice.total_exempt == 500_000, invoice.total_exempt)
        check('ارزش افزوده فقط روی ردیف مشمول اعمال می‌شود',
              invoice.total_vat == 180_000, invoice.total_vat)
        check('جمع کل = مشمول + معاف + ارزش افزوده',
              invoice.total_amount == 2_480_000, invoice.total_amount)

        payload = build_invoice_payload(invoice, settings)
        check('ساختار payload شامل header/body/payments است',
              set(payload) == {'header', 'body', 'payments'})
        check('تعداد ردیف‌های body صحیح است', len(payload['body']) == 2)
        check('مجموع صورتحساب در هدر درج شده', payload['header']['tbill'] == 2_480_000)

        result = MoadianClient(settings).send_invoice(invoice)
        check('ارسال در حالت آزمایشی بدون تماس شبکه موفق است', result['success'])
        check('حالت آزمایشی علامت‌گذاری شده', result.get('sandbox') is True)

        db.session.rollback()


def test_depreciation():
    from types import SimpleNamespace

    from utils.depreciation import annual_depreciation, depreciation_schedule

    print('\n[استهلاک دارایی — ماده ۱۴۹]')
    straight = SimpleNamespace(cost=300_000_000, salvage_value=0, accumulated_depreciation=0,
                               method='straight', useful_life_years=3, declining_rate=0)
    check('خط مستقیم: استهلاک سالانه = بهای تمام شده ÷ عمر مفید',
          annual_depreciation(straight) == 100_000_000, annual_depreciation(straight))
    schedule = depreciation_schedule(straight)
    check('جدول خط مستقیم ۳ دوره دارد', len(schedule) == 3, len(schedule))
    check('ارزش دفتری پایان دوره آخر صفر است', schedule[-1]['closing_value'] == 0)

    declining = SimpleNamespace(cost=100_000_000, salvage_value=0, accumulated_depreciation=0,
                                method='declining', useful_life_years=0, declining_rate=25)
    check('نزولی: دوره اول ۲۵٪ ارزش دفتری',
          annual_depreciation(declining) == 25_000_000, annual_depreciation(declining))
    declining.accumulated_depreciation = 25_000_000
    check('نزولی: دوره دوم روی ارزش دفتری جدید محاسبه می‌شود',
          annual_depreciation(declining) == 18_750_000, annual_depreciation(declining))

    salvaged = SimpleNamespace(cost=100_000_000, salvage_value=90_000_000,
                               accumulated_depreciation=0, method='straight',
                               useful_life_years=1, declining_rate=0)
    check('استهلاک از ارزش اسقاط عبور نمی‌کند',
          annual_depreciation(salvaged) == 10_000_000, annual_depreciation(salvaged))


def test_salary_tax(app):
    """روی یک سال آزمایشی مجزا اجرا می‌شود تا جدول واقعی کاربر دست‌نخورده بماند."""
    print('\n[مالیات حقوق]')
    test_year = '9999'
    with app.app_context():
        from extensions import db
        from models.tax import SalaryTaxBracket
        from routes.tax_compliance import calculate_salary_tax, get_brackets

        SalaryTaxBracket.query.filter_by(year=test_year).delete()
        db.session.commit()
        try:
            brackets = get_brackets(test_year)
            check('پله‌های پیش‌فرض سال ساخته می‌شوند', len(brackets) >= 4, len(brackets))
            zero_tax, _ = calculate_salary_tax(100_000_000, test_year)
            check('درآمد زیر سقف معافیت، مالیات ندارد', zero_tax == 0, zero_tax)
            tax, breakdown = calculate_salary_tax(150_000_000, test_year)
            check('پله ۱۰٪ روی مازاد معافیت اعمال می‌شود', tax == 3_000_000, tax)
            check('ریز محاسبه پله‌ها برگردانده می‌شود', len(breakdown) >= 1)
            big_tax, _ = calculate_salary_tax(500_000_000, test_year)
            check('محاسبه تصاعدی چندپله‌ای انجام می‌شود', big_tax > tax, big_tax)
        finally:
            SalaryTaxBracket.query.filter_by(year=test_year).delete()
            db.session.commit()


def test_reports(app):
    print('\n[گزارش‌های مالیاتی]')
    from utils.tax_reports import build_salary_tax_txt, quarter_date_range

    start, end = quarter_date_range(1404, 1)
    check('بازه فصل بهار ۱۴۰۴ درست محاسبه می‌شود',
          (start.isoformat(), end.isoformat()) == ('2025-03-21', '2025-06-21'),
          f'{start} تا {end}')
    start, end = quarter_date_range(1404, 4)
    check('فصل زمستان تا پایان اسفند ادامه دارد', end.isoformat() == '2026-03-20', end)

    content = build_salary_tax_txt(
        [{'first_name': 'علی', 'last_name': 'رضایی', 'national_code': '0499370899',
          'gross': 200_000_000, 'tax': 5_000_000, 'net': 195_000_000}],
        '1405/05', 'EMP-1')
    check('فایل متنی لیست حقوق هدر دوره دارد', '#PERIOD=1405/05' in content)
    check('فایل متنی ردیف کارمند را شامل می‌شود', '0499370899' in content)

    with app.app_context():
        from utils.tax_reports import excel_response
        with app.test_request_context():
            response = excel_response('t.xlsx', {'ش': {'headers': ['الف'], 'rows': [[1]]}})
            check('ساخت خروجی اکسل بدون خطا انجام می‌شود',
                  response.headers['Content-Type'].startswith('application/vnd'))


def test_routes(app):
    print('\n[مسیرهای ثبت‌شده]')
    required = {
        'moadian.dashboard', 'moadian.settings_page', 'moadian.new_invoice',
        'moadian.issue_invoice', 'moadian.send_invoice', 'moadian.inquiry_invoice',
        'moadian.tax_number_tool', 'moadian.validate_id_api', 'moadian.parties',
        'moadian.service_items', 'moadian.invoice_from_payment',
        'compliance.vat_report', 'compliance.vat_export',
        'compliance.seasonal_report', 'compliance.seasonal_export',
        'compliance.salary_brackets', 'compliance.salary_tax_list',
        'compliance.salary_tax_export', 'compliance.withholding_list',
        'compliance.assets', 'compliance.asset_depreciate',
        'compliance.balance_sheet', 'compliance.income_statement',
        'compliance.legal_books', 'compliance.legal_books_export',
    }
    endpoints = {rule.endpoint for rule in app.url_map.iter_rules()}
    missing = sorted(required - endpoints)
    check(f'{len(required)} مسیر مالیاتی ثبت شده‌اند', not missing, '، '.join(missing))


def main() -> int:
    from app import create_app

    app = create_app()
    print('=' * 70)
    print(' گزارش بررسی ماژول‌های انطباق مالیاتی')
    print('=' * 70)

    test_tax_number()
    test_identity_validation()
    test_depreciation()
    test_reports(app)
    test_vat_and_invoice(app)
    test_salary_tax(app)
    test_routes(app)

    print('\n' + '-' * 70)
    if failures:
        print(f'❌ {len(failures)} بررسی ناموفق: ' + '، '.join(failures))
        return 1
    print('✅ تمام بررسی‌های مالیاتی با موفقیت انجام شد.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
