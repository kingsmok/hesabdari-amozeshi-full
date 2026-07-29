"""
انطباق مالیاتی — ارزش افزوده، معاملات فصلی، مالیات تکلیفی،
استهلاک دارایی‌ها و صورت‌های مالی قانونی.
"""
from datetime import date, datetime

import jdatetime
from flask import (Blueprint, flash, redirect, render_template, request,
                   url_for)
from flask_login import current_user, login_required

from extensions import db
from models.tax import (DepreciationRecord, FixedAsset, SalaryTaxBracket,
                        TaxInvoice, TaxParty, TaxSettings, WithholdingTax)
from utils.depreciation import (ASSET_CATEGORIES, CATEGORY_NAMES,
                                annual_depreciation, depreciation_schedule)
from utils.form_helpers import form_float, form_int, form_str, get_jalali_date
from utils.iran_tax import normalize_digits, validate_party_id
from utils.jalali import gregorian_to_jalali
from utils.tax_reports import (QUARTER_NAMES, TTMS_SALE_HEADERS,
                               build_salary_tax_txt, csv_response,
                               excel_response, quarter_date_range,
                               text_response)

compliance_bp = Blueprint('compliance', __name__)


def _settings():
    return TaxSettings.get()


def _current_jalali_year():
    return jdatetime.date.today().year


# ═══════════════════════════════════════════
#  ارزش افزوده
# ═══════════════════════════════════════════
def _vat_summary(start, end):
    """جمع ارزش افزوده فروش و خرید در یک بازه."""
    sales = TaxInvoice.query.filter(
        TaxInvoice.direction == 'sale',
        TaxInvoice.invoice_date >= start,
        TaxInvoice.invoice_date <= end,
        TaxInvoice.status != 'cancelled',
    ).order_by(TaxInvoice.invoice_date).all()
    purchases = TaxInvoice.query.filter(
        TaxInvoice.direction == 'purchase',
        TaxInvoice.invoice_date >= start,
        TaxInvoice.invoice_date <= end,
        TaxInvoice.status != 'cancelled',
    ).order_by(TaxInvoice.invoice_date).all()

    def _totals(rows):
        return {
            'count': len(rows),
            'taxable': sum(r.total_taxable or 0 for r in rows),
            'exempt': sum(r.total_exempt or 0 for r in rows),
            'vat': sum(r.total_vat or 0 for r in rows),
            'total': sum(r.total_amount or 0 for r in rows),
        }

    sale_totals = _totals(sales)
    purchase_totals = _totals(purchases)
    return {
        'sales': sales,
        'purchases': purchases,
        'sale_totals': sale_totals,
        'purchase_totals': purchase_totals,
        'payable': round(sale_totals['vat'] - purchase_totals['vat'], 2),
    }


@compliance_bp.route('/tax/vat')
@login_required
def vat_report():
    """گزارش دوره‌ای (فصلی) ارزش افزوده برای اظهارنامه."""
    year = request.args.get('year', type=int) or _current_jalali_year()
    quarter = request.args.get('quarter', type=int) or ((jdatetime.date.today().month - 1) // 3 + 1)
    start, end = quarter_date_range(year, quarter)
    data = _vat_summary(start, end)

    return render_template('tax/vat_report.html', settings=_settings(),
                           year=year, quarter=quarter,
                           quarter_name=QUARTER_NAMES[quarter],
                           start=start, end=end, **data)


@compliance_bp.route('/tax/vat/export')
@login_required
def vat_export():
    year = request.args.get('year', type=int) or _current_jalali_year()
    quarter = request.args.get('quarter', type=int) or 1
    start, end = quarter_date_range(year, quarter)
    data = _vat_summary(start, end)

    def _rows(invoices):
        return [[
            invoice.invoice_number,
            gregorian_to_jalali(invoice.invoice_date),
            invoice.party_name_snapshot or '-',
            invoice.party.national_id if invoice.party else '-',
            round(invoice.total_taxable or 0),
            round(invoice.total_exempt or 0),
            round(invoice.total_vat or 0),
            round(invoice.total_amount or 0),
            invoice.tax_number or '-',
        ] for invoice in invoices]

    headers = ['شماره صورتحساب', 'تاریخ', 'طرف حساب', 'شناسه', 'مشمول',
               'معاف', 'ارزش افزوده', 'جمع کل', 'شماره مالیاتی']
    summary_rows = [
        ['جمع فروش', data['sale_totals']['taxable'], data['sale_totals']['exempt'],
         data['sale_totals']['vat'], data['sale_totals']['total']],
        ['جمع خرید', data['purchase_totals']['taxable'], data['purchase_totals']['exempt'],
         data['purchase_totals']['vat'], data['purchase_totals']['total']],
        ['مابه‌التفاوت قابل پرداخت', '', '', data['payable'], ''],
    ]

    return excel_response(
        f'vat_{year}_Q{quarter}.xlsx',
        {
            'خلاصه': {'headers': ['شرح', 'مشمول', 'معاف', 'ارزش افزوده', 'جمع'],
                      'rows': summary_rows, 'widths': [28, 18, 18, 18, 18]},
            'فروش': {'headers': headers, 'rows': _rows(data['sales']),
                     'widths': [18, 14, 26, 18, 16, 16, 16, 18, 26]},
            'خرید': {'headers': headers, 'rows': _rows(data['purchases']),
                     'widths': [18, 14, 26, 18, 16, 16, 16, 18, 26]},
        },
    )


# ═══════════════════════════════════════════
#  معاملات فصلی — ماده ۱۶۹ (TTMS)
# ═══════════════════════════════════════════
@compliance_bp.route('/tax/seasonal')
@login_required
def seasonal_report():
    year = request.args.get('year', type=int) or _current_jalali_year()
    quarter = request.args.get('quarter', type=int) or ((jdatetime.date.today().month - 1) // 3 + 1)
    start, end = quarter_date_range(year, quarter)
    data = _vat_summary(start, end)

    # طرف‌حساب‌های فاقد شناسه معتبر مانع پذیرش گزارش در TTMS می‌شوند
    problem_parties = []
    for invoice in data['sales'] + data['purchases']:
        party = invoice.party
        if party is None:
            continue
        if not party.is_verified and party.party_type != 'consumer':
            problem_parties.append(party)
    problem_parties = list({p.id: p for p in problem_parties}.values())

    return render_template('tax/seasonal_report.html', year=year, quarter=quarter,
                           quarter_name=QUARTER_NAMES[quarter], start=start, end=end,
                           problem_parties=problem_parties, **data)


def _ttms_rows(invoices, deal_type):
    rows = []
    for invoice in invoices:
        party = invoice.party
        rows.append([
            deal_type,
            invoice.invoice_number,
            gregorian_to_jalali(invoice.invoice_date),
            party.type_label if party else 'مصرف‌کننده نهایی',
            invoice.party_name_snapshot or (party.name if party else '-'),
            party.national_id if party else '',
            party.economic_code if party else '',
            party.postal_code if party else '',
            (party.address if party else '') or '',
            (invoice.description or 'خدمات آموزشی'),
            round(invoice.total_before_discount or 0),
            round(invoice.total_discount or 0),
            round(invoice.total_taxable or 0),
            round(invoice.total_exempt or 0),
            round(invoice.total_vat or 0),
            round(invoice.total_amount or 0),
            invoice.tax_number or '',
        ])
    return rows


@compliance_bp.route('/tax/seasonal/export')
@login_required
def seasonal_export():
    """خروجی استاندارد TTMS — اکسل (دو شیت فروش/خرید) یا CSV."""
    year = request.args.get('year', type=int) or _current_jalali_year()
    quarter = request.args.get('quarter', type=int) or 1
    fmt = request.args.get('format', 'excel')
    start, end = quarter_date_range(year, quarter)
    data = _vat_summary(start, end)

    sale_rows = _ttms_rows(data['sales'], 'فروش')
    purchase_rows = _ttms_rows(data['purchases'], 'خرید')

    if fmt == 'csv':
        return csv_response(f'ttms_{year}_Q{quarter}.csv',
                            TTMS_SALE_HEADERS, sale_rows + purchase_rows)

    widths = [10, 16, 12, 14, 26, 16, 16, 12, 30, 26, 16, 12, 16, 14, 14, 16, 24]
    return excel_response(
        f'ttms_{year}_Q{quarter}.xlsx',
        {
            'فروش': {'headers': TTMS_SALE_HEADERS, 'rows': sale_rows, 'widths': widths},
            'خرید': {'headers': TTMS_SALE_HEADERS, 'rows': purchase_rows, 'widths': widths},
        },
    )


# ═══════════════════════════════════════════
#  مالیات حقوق — پله‌ها و خروجی سامانه
# ═══════════════════════════════════════════
DEFAULT_BRACKETS = [
    # پله‌های ماهانه پیش‌فرض (قابل ویرایش برای هر سال)
    {'title': 'معاف', 'from_amount': 0, 'to_amount': 120000000, 'rate': 0},
    {'title': '۱۰٪', 'from_amount': 120000000, 'to_amount': 165000000, 'rate': 10},
    {'title': '۱۵٪', 'from_amount': 165000000, 'to_amount': 270000000, 'rate': 15},
    {'title': '۲۰٪', 'from_amount': 270000000, 'to_amount': 400000000, 'rate': 20},
    {'title': '۳۰٪', 'from_amount': 400000000, 'to_amount': None, 'rate': 30},
]


def get_brackets(year: str):
    """پله‌های مالیاتی سال؛ در نبود رکورد، مقدار پیش‌فرض ساخته می‌شود."""
    brackets = SalaryTaxBracket.query.filter_by(year=str(year), is_active=True) \
        .order_by(SalaryTaxBracket.order_index, SalaryTaxBracket.from_amount).all()
    if brackets:
        return brackets
    for index, item in enumerate(DEFAULT_BRACKETS):
        db.session.add(SalaryTaxBracket(year=str(year), order_index=index, **item))
    db.session.commit()
    return SalaryTaxBracket.query.filter_by(year=str(year), is_active=True) \
        .order_by(SalaryTaxBracket.order_index, SalaryTaxBracket.from_amount).all()


def calculate_salary_tax(monthly_taxable: float, year: str):
    """مالیات ماهانه حقوق را بر مبنای پله‌های تعریف‌شده محاسبه می‌کند."""
    amount = float(monthly_taxable or 0)
    total = 0.0
    breakdown = []
    for bracket in get_brackets(year):
        lower = float(bracket.from_amount or 0)
        upper = bracket.to_amount
        if amount <= lower:
            continue
        top = amount if upper is None else min(amount, float(upper))
        slice_amount = top - lower
        if slice_amount <= 0:
            continue
        tax = slice_amount * float(bracket.rate or 0) / 100.0
        total += tax
        breakdown.append({
            'title': bracket.title or f'{bracket.rate}٪',
            'from': lower, 'to': upper, 'rate': bracket.rate,
            'amount': slice_amount, 'tax': round(tax),
        })
    return round(total), breakdown


@compliance_bp.route('/tax/salary-brackets', methods=['GET', 'POST'])
@login_required
def salary_brackets():
    year = request.args.get('year') or str(_current_jalali_year())

    if request.method == 'POST':
        year = form_str(request.form, 'year') or year
        SalaryTaxBracket.query.filter_by(year=year).delete()
        titles = request.form.getlist('bracket_title[]')
        froms = request.form.getlist('bracket_from[]')
        tos = request.form.getlist('bracket_to[]')
        rates = request.form.getlist('bracket_rate[]')

        for index, title in enumerate(titles):
            from_value = (froms[index] if index < len(froms) else '').strip()
            to_value = (tos[index] if index < len(tos) else '').strip()
            rate_value = (rates[index] if index < len(rates) else '0').strip()
            if not from_value and not rate_value:
                continue
            db.session.add(SalaryTaxBracket(
                year=year,
                title=title.strip() or f'{rate_value}٪',
                from_amount=float(from_value or 0),
                to_amount=float(to_value) if to_value else None,
                rate=float(rate_value or 0),
                order_index=index,
                is_active=True,
            ))
        db.session.commit()
        flash(f'پله‌های مالیاتی سال {year} ذخیره شد', 'success')
        return redirect(url_for('compliance.salary_brackets', year=year))

    brackets = get_brackets(year)
    years = [row[0] for row in db.session.query(SalaryTaxBracket.year).distinct().all()]
    settings = _settings()
    sample_tax, sample_breakdown = calculate_salary_tax(
        request.args.get('sample', type=float) or 200000000, year)
    return render_template('tax/salary_brackets.html', brackets=brackets, year=year,
                           years=sorted(set(years)), settings=settings,
                           sample_tax=sample_tax, sample_breakdown=sample_breakdown)


def _payslip_rows(period):
    """ردیف‌های لیست مالیات حقوق یک دوره."""
    from models.finance import Payslip
    from models.teacher import Teacher

    settings = _settings()
    year = (period or '').split('/')[0] or settings.salary_year
    exemption = float(settings.salary_monthly_exemption or 0)

    rows = []
    for payslip in Payslip.query.filter_by(period=period).all():
        teacher = Teacher.query.get(payslip.person_id) if payslip.person_type == 'teacher' else None
        full_name = (teacher.full_name if teacher else f'{payslip.person_type} #{payslip.person_id}')
        parts = full_name.split(' ', 1)
        gross = float(payslip.gross_amount or 0)
        insurance = float(payslip.insurance or 0)
        taxable = max(gross - insurance - exemption, 0)
        computed_tax, _ = calculate_salary_tax(gross - insurance, year)
        rows.append({
            'payslip': payslip,
            'first_name': parts[0],
            'last_name': parts[1] if len(parts) > 1 else '',
            'national_code': getattr(teacher, 'national_code', '') or '',
            'insurance_number': getattr(teacher, 'insurance_number', '') or '',
            'job_title': 'مدرس' if teacher else payslip.person_type,
            'base': float(payslip.base_amount or 0),
            'continuous': float(payslip.teaching_amount or 0) + float(payslip.session_amount or 0),
            'non_continuous': float(payslip.bonus or 0) + float(payslip.overtime or 0),
            'gross': gross,
            'exemption': exemption,
            'insurance': insurance,
            'taxable': taxable,
            'tax': float(payslip.tax or 0),
            'computed_tax': computed_tax,
            'net': float(payslip.net_amount or 0),
        })
    return rows


@compliance_bp.route('/tax/salary-list')
@login_required
def salary_tax_list():
    """لیست مالیات حقوق یک دوره برای بارگذاری در salary.tax.gov.ir."""
    from models.finance import Payslip

    period = request.args.get('period', '')
    periods = [row[0] for row in db.session.query(Payslip.period).distinct().all() if row[0]]
    periods.sort(reverse=True)
    if not period and periods:
        period = periods[0]

    rows = _payslip_rows(period) if period else []
    totals = {
        'gross': sum(r['gross'] for r in rows),
        'insurance': sum(r['insurance'] for r in rows),
        'taxable': sum(r['taxable'] for r in rows),
        'tax': sum(r['tax'] for r in rows),
        'computed_tax': sum(r['computed_tax'] for r in rows),
        'net': sum(r['net'] for r in rows),
    }
    missing_codes = [r for r in rows if not r['national_code']]
    return render_template('tax/salary_list.html', rows=rows, totals=totals,
                           period=period, periods=periods, settings=_settings(),
                           missing_codes=missing_codes)


@compliance_bp.route('/tax/salary-list/export')
@login_required
def salary_tax_export():
    period = request.args.get('period', '')
    fmt = request.args.get('format', 'excel')
    rows = _payslip_rows(period)
    settings = _settings()

    if fmt == 'txt':
        content = build_salary_tax_txt(rows, period, settings.employer_tax_file_code or '')
        return text_response(f'salary_tax_{period.replace("/", "_")}.txt', content)

    headers = ['ردیف', 'نام', 'نام خانوادگی', 'کد ملی', 'شماره بیمه', 'شغل',
               'حقوق پایه', 'مزایای مستمر', 'مزایای غیرمستمر', 'ناخالص',
               'معافیت', 'بیمه', 'درآمد مشمول', 'مالیات', 'خالص پرداختی']
    data_rows = [[
        index, r['first_name'], r['last_name'], r['national_code'], r['insurance_number'],
        r['job_title'], round(r['base']), round(r['continuous']), round(r['non_continuous']),
        round(r['gross']), round(r['exemption']), round(r['insurance']),
        round(r['taxable']), round(r['tax']), round(r['net']),
    ] for index, r in enumerate(rows, start=1)]

    return excel_response(
        f'salary_tax_{period.replace("/", "_")}.xlsx',
        {'لیست مالیات حقوق': {'headers': headers, 'rows': data_rows,
                              'widths': [8, 16, 20, 16, 16, 14] + [16] * 9}},
    )


@compliance_bp.route('/tax/salary-list/recalculate', methods=['POST'])
@login_required
def salary_recalculate():
    """محاسبه مجدد مالیات فیش‌های یک دوره بر اساس پله‌های تعریف‌شده."""
    from models.finance import Payslip

    period = form_str(request.form, 'period')
    if not period:
        flash('دوره را انتخاب کنید', 'error')
        return redirect(url_for('compliance.salary_tax_list'))

    year = period.split('/')[0]
    count = 0
    for payslip in Payslip.query.filter_by(period=period).all():
        gross = float(payslip.gross_amount or 0)
        insurance = float(payslip.insurance or 0)
        tax, _ = calculate_salary_tax(gross - insurance, year)
        payslip.tax = tax
        payslip.total_deductions = (payslip.deductions or 0) + insurance + tax + (payslip.penalty or 0)
        payslip.net_amount = gross - payslip.total_deductions
        count += 1
    db.session.commit()
    flash(f'مالیات {count} فیش بر اساس پله‌های سال {year} بازمحاسبه شد', 'success')
    return redirect(url_for('compliance.salary_tax_list', period=period))


# ═══════════════════════════════════════════
#  مالیات‌های تکلیفی
# ═══════════════════════════════════════════
@compliance_bp.route('/tax/withholding')
@login_required
def withholding_list():
    tax_type = request.args.get('type', '')
    period = request.args.get('period', '')
    query = WithholdingTax.query
    if tax_type:
        query = query.filter_by(tax_type=tax_type)
    if period:
        query = query.filter_by(period=period)
    items = query.order_by(WithholdingTax.doc_date.desc()).all()

    totals = {
        'gross': sum(i.gross_amount or 0 for i in items),
        'tax': sum(i.tax_amount or 0 for i in items),
        'net': sum(i.net_amount or 0 for i in items),
        'unpaid': sum(i.tax_amount or 0 for i in items if not i.is_paid),
    }
    return render_template('tax/withholding.html', items=items, totals=totals,
                           tax_type=tax_type, period=period, settings=_settings(),
                           type_labels=WithholdingTax.TYPE_LABELS)


@compliance_bp.route('/tax/withholding/add', methods=['GET', 'POST'])
@compliance_bp.route('/tax/withholding/<int:item_id>/edit', methods=['GET', 'POST'])
@login_required
def withholding_form(item_id=None):
    from models.teacher import Teacher

    item = WithholdingTax.query.get_or_404(item_id) if item_id else None
    settings = _settings()

    if request.method == 'POST':
        national_id = normalize_digits(request.form.get('payee_national_id'))
        payee_type = form_str(request.form, 'payee_type') or 'real'
        if national_id:
            ok, message = validate_party_id(national_id, payee_type)
            if not ok and not request.form.get('force_save'):
                flash(f'شناسه دریافت‌کننده: {message}', 'error')
                return render_template('tax/withholding_form.html', item=item,
                                       teachers=Teacher.query.all(), settings=settings)

        if item is None:
            # شماره سند پیش از افزودن رکورد ساخته می‌شود تا autoflush رکورد ناقص را ذخیره نکند
            last = WithholdingTax.query.order_by(WithholdingTax.id.desc()).first()
            item = WithholdingTax(doc_number=f'WHT-{((last.id if last else 0) + 1):05d}')
            db.session.add(item)

        item.tax_type = form_str(request.form, 'tax_type') or 'rent'
        item.period = form_str(request.form, 'period')
        item.payee_name = form_str(request.form, 'payee_name')
        item.payee_national_id = national_id
        item.payee_type = payee_type
        item.gross_amount = form_float(request.form, 'gross_amount')
        item.rate = form_float(request.form, 'rate', settings.rent_withholding_rate or 10)
        item.doc_date = get_jalali_date(request.form, 'doc_date') or date.today()
        item.teacher_id = form_int(request.form, 'teacher_id') or None
        item.description = form_str(request.form, 'description')
        item.is_paid = bool(request.form.get('is_paid'))
        item.paid_date = get_jalali_date(request.form, 'paid_date')
        item.payment_reference = form_str(request.form, 'payment_reference')
        item.created_by = current_user.id
        item.recalculate()

        db.session.commit()
        flash('سند مالیات تکلیفی ذخیره شد', 'success')
        return redirect(url_for('compliance.withholding_list'))

    return render_template('tax/withholding_form.html', item=item,
                           teachers=Teacher.query.filter_by(is_active=True).all(),
                           settings=settings)


@compliance_bp.route('/tax/withholding/<int:item_id>/delete', methods=['POST'])
@login_required
def withholding_delete(item_id):
    item = WithholdingTax.query.get_or_404(item_id)
    db.session.delete(item)
    db.session.commit()
    flash('سند حذف شد', 'warning')
    return redirect(url_for('compliance.withholding_list'))


@compliance_bp.route('/tax/withholding/export')
@login_required
def withholding_export():
    items = WithholdingTax.query.order_by(WithholdingTax.doc_date).all()
    rows = [[
        item.doc_number, item.type_label, item.period or '',
        gregorian_to_jalali(item.doc_date), item.payee_name,
        item.payee_national_id or '', round(item.gross_amount or 0),
        item.rate, round(item.tax_amount or 0), round(item.net_amount or 0),
        'واریز شده' if item.is_paid else 'واریز نشده',
        item.payment_reference or '',
    ] for item in items]
    return excel_response('withholding_taxes.xlsx', {
        'مالیات تکلیفی': {
            'headers': ['شماره سند', 'نوع', 'دوره', 'تاریخ', 'دریافت‌کننده', 'شناسه',
                        'مبلغ ناخالص', 'نرخ (٪)', 'مالیات کسر شده', 'خالص پرداختی',
                        'وضعیت واریز', 'مرجع پرداخت'],
            'rows': rows,
            'widths': [14, 20, 12, 14, 26, 16, 18, 10, 18, 18, 14, 18],
        }
    })


# ═══════════════════════════════════════════
#  دارایی ثابت و استهلاک (ماده ۱۴۹)
# ═══════════════════════════════════════════
@compliance_bp.route('/tax/assets')
@login_required
def assets():
    items = FixedAsset.query.order_by(FixedAsset.acquisition_date.desc()).all()
    totals = {
        'cost': sum(a.cost or 0 for a in items),
        'accumulated': sum(a.accumulated_depreciation or 0 for a in items),
        'book': sum(a.book_value for a in items),
        'annual': sum(annual_depreciation(a) for a in items if not a.is_disposed),
    }
    return render_template('tax/assets.html', assets=items, totals=totals,
                           categories=ASSET_CATEGORIES)


@compliance_bp.route('/tax/assets/add', methods=['GET', 'POST'])
@compliance_bp.route('/tax/assets/<int:asset_id>/edit', methods=['GET', 'POST'])
@login_required
def asset_form(asset_id=None):
    asset = FixedAsset.query.get_or_404(asset_id) if asset_id else None

    if request.method == 'POST':
        if asset is None:
            last = FixedAsset.query.order_by(FixedAsset.id.desc()).first()
            asset = FixedAsset(name=form_str(request.form, 'name'),
                               asset_code=f'AST-{((last.id if last else 0) + 1):05d}')
            db.session.add(asset)

        asset.name = form_str(request.form, 'name')
        asset.category = form_str(request.form, 'category')
        asset.acquisition_date = get_jalali_date(request.form, 'acquisition_date') or date.today()
        asset.cost = form_float(request.form, 'cost')
        asset.salvage_value = form_float(request.form, 'salvage_value')
        asset.method = form_str(request.form, 'method') or 'straight'
        asset.useful_life_years = form_float(request.form, 'useful_life_years', 5)
        asset.declining_rate = form_float(request.form, 'declining_rate', 25)
        asset.location = form_str(request.form, 'location')
        asset.notes = form_str(request.form, 'notes')

        db.session.commit()
        flash('دارایی ذخیره شد', 'success')
        return redirect(url_for('compliance.asset_detail', asset_id=asset.id))

    return render_template('tax/asset_form.html', asset=asset,
                           categories=ASSET_CATEGORIES, category_names=CATEGORY_NAMES)


@compliance_bp.route('/tax/assets/<int:asset_id>')
@login_required
def asset_detail(asset_id):
    asset = FixedAsset.query.get_or_404(asset_id)
    schedule = depreciation_schedule(asset)
    records = asset.depreciations.order_by(DepreciationRecord.period_index).all()
    return render_template('tax/asset_detail.html', asset=asset,
                           schedule=schedule, records=records,
                           next_amount=annual_depreciation(asset))


@compliance_bp.route('/tax/assets/<int:asset_id>/depreciate', methods=['POST'])
@login_required
def asset_depreciate(asset_id):
    """ثبت استهلاک یک دوره برای دارایی."""
    asset = FixedAsset.query.get_or_404(asset_id)
    year = form_str(request.form, 'year') or str(_current_jalali_year())

    if asset.depreciations.filter_by(year=year).first():
        flash(f'استهلاک سال {year} برای این دارایی قبلاً ثبت شده است', 'warning')
        return redirect(url_for('compliance.asset_detail', asset_id=asset.id))

    amount = annual_depreciation(asset)
    if amount <= 0:
        flash('دارایی کاملاً مستهلک شده است', 'warning')
        return redirect(url_for('compliance.asset_detail', asset_id=asset.id))

    opening = asset.book_value
    asset.accumulated_depreciation = (asset.accumulated_depreciation or 0) + amount
    db.session.add(DepreciationRecord(
        asset_id=asset.id, year=year,
        period_index=asset.depreciations.count() + 1,
        opening_value=opening, depreciation=amount,
        accumulated=asset.accumulated_depreciation,
        closing_value=asset.book_value,
    ))
    db.session.commit()
    flash(f'استهلاک سال {year} به مبلغ {amount:,.0f} ثبت شد', 'success')
    return redirect(url_for('compliance.asset_detail', asset_id=asset.id))


@compliance_bp.route('/tax/assets/depreciate-all', methods=['POST'])
@login_required
def depreciate_all():
    """ثبت گروهی استهلاک سالانه همه دارایی‌های فعال."""
    year = form_str(request.form, 'year') or str(_current_jalali_year())
    count = 0
    total = 0.0
    for asset in FixedAsset.query.filter_by(is_disposed=False).all():
        if asset.depreciations.filter_by(year=year).first():
            continue
        amount = annual_depreciation(asset)
        if amount <= 0:
            continue
        opening = asset.book_value
        asset.accumulated_depreciation = (asset.accumulated_depreciation or 0) + amount
        db.session.add(DepreciationRecord(
            asset_id=asset.id, year=year,
            period_index=asset.depreciations.count() + 1,
            opening_value=opening, depreciation=amount,
            accumulated=asset.accumulated_depreciation,
            closing_value=asset.book_value,
        ))
        count += 1
        total += amount
    db.session.commit()
    flash(f'استهلاک سال {year} برای {count} دارایی به مبلغ کل {total:,.0f} ثبت شد', 'success')
    return redirect(url_for('compliance.assets'))


@compliance_bp.route('/tax/assets/export')
@login_required
def assets_export():
    items = FixedAsset.query.order_by(FixedAsset.asset_code).all()
    rows = [[
        asset.asset_code, asset.name, asset.category or '-',
        gregorian_to_jalali(asset.acquisition_date), round(asset.cost or 0),
        round(asset.salvage_value or 0), asset.method_label,
        asset.useful_life_years if asset.method == 'straight' else f'{asset.declining_rate}٪',
        round(annual_depreciation(asset)), round(asset.accumulated_depreciation or 0),
        round(asset.book_value),
    ] for asset in items]
    return excel_response('fixed_assets.xlsx', {
        'دارایی ثابت': {
            'headers': ['کد', 'نام دارایی', 'گروه (ماده ۱۴۹)', 'تاریخ تحصیل', 'بهای تمام شده',
                        'ارزش اسقاط', 'روش', 'عمر مفید/نرخ', 'استهلاک دوره',
                        'استهلاک انباشته', 'ارزش دفتری'],
            'rows': rows,
            'widths': [12, 30, 26, 14, 18, 16, 14, 14, 18, 18, 18],
        }
    })


# ═══════════════════════════════════════════
#  صورت‌های مالی و دفاتر قانونی
# ═══════════════════════════════════════════
def _account_balances(start=None, end=None):
    """مانده حساب‌ها از روی اسناد تایید شده."""
    from models.accounting import Account, JournalEntry, JournalItem

    query = db.session.query(
        Account.id, Account.code, Account.name, Account.account_type, Account.nature,
        db.func.coalesce(db.func.sum(JournalItem.debit), 0).label('debit'),
        db.func.coalesce(db.func.sum(JournalItem.credit), 0).label('credit'),
    ).outerjoin(JournalItem, JournalItem.account_id == Account.id) \
     .outerjoin(JournalEntry, db.and_(
         JournalEntry.id == JournalItem.entry_id,
         JournalEntry.status.in_(['confirmed', 'approved']),
     ))

    if start:
        query = query.filter(db.or_(JournalEntry.id.is_(None), JournalEntry.entry_date >= start))
    if end:
        query = query.filter(db.or_(JournalEntry.id.is_(None), JournalEntry.entry_date <= end))

    rows = query.filter(Account.is_active.is_(True)) \
                .group_by(Account.id).order_by(Account.code).all()

    result = []
    for row in rows:
        debit, credit = float(row.debit or 0), float(row.credit or 0)
        balance = debit - credit if (row.nature or 'debit') == 'debit' else credit - debit
        result.append({
            'id': row.id, 'code': row.code, 'name': row.name,
            'type': row.account_type, 'nature': row.nature,
            'debit': debit, 'credit': credit, 'balance': balance,
        })
    return result


@compliance_bp.route('/tax/balance-sheet')
@login_required
def balance_sheet():
    """ترازنامه پایان دوره مالی."""
    year = request.args.get('year', type=int) or _current_jalali_year()
    start = jdatetime.date(year, 1, 1).togregorian()
    end = jdatetime.date(year + 1, 1, 1).togregorian()

    accounts = _account_balances(start, end)
    groups = {'asset': [], 'liability': [], 'equity': [], 'revenue': [], 'expense': []}
    for account in accounts:
        groups.get(account['type'], groups['asset']).append(account)

    def _sum(key):
        return sum(a['balance'] for a in groups[key])

    revenue, expense = _sum('revenue'), _sum('expense')
    net_income = revenue - expense
    assets_total = _sum('asset')
    liabilities_total = _sum('liability')
    equity_total = _sum('equity') + net_income

    return render_template('tax/balance_sheet.html', year=year, groups=groups,
                           assets_total=assets_total, liabilities_total=liabilities_total,
                           equity_total=equity_total, net_income=net_income,
                           difference=round(assets_total - (liabilities_total + equity_total), 2))


@compliance_bp.route('/tax/income-statement')
@login_required
def income_statement():
    """صورت سود و زیان دوره."""
    year = request.args.get('year', type=int) or _current_jalali_year()
    start = jdatetime.date(year, 1, 1).togregorian()
    end = jdatetime.date(year + 1, 1, 1).togregorian()

    accounts = _account_balances(start, end)
    revenues = [a for a in accounts if a['type'] == 'revenue']
    expenses = [a for a in accounts if a['type'] == 'expense']

    total_revenue = sum(a['balance'] for a in revenues)
    total_expense = sum(a['balance'] for a in expenses)

    depreciation = db.session.query(
        db.func.coalesce(db.func.sum(DepreciationRecord.depreciation), 0)
    ).filter(DepreciationRecord.year == str(year)).scalar() or 0

    return render_template('tax/income_statement.html', year=year,
                           revenues=revenues, expenses=expenses,
                           total_revenue=total_revenue, total_expense=total_expense,
                           depreciation=float(depreciation),
                           net_income=total_revenue - total_expense - float(depreciation))


@compliance_bp.route('/tax/legal-books')
@login_required
def legal_books():
    """دفتر روزنامه و کل برای تحریر دفاتر پلمپ."""
    from models.accounting import JournalEntry, JournalItem

    year = request.args.get('year', type=int) or _current_jalali_year()
    book = request.args.get('book', 'journal')
    start = jdatetime.date(year, 1, 1).togregorian()
    end = jdatetime.date(year + 1, 1, 1).togregorian()

    entries = JournalEntry.query.filter(
        JournalEntry.entry_date >= start,
        JournalEntry.entry_date < end,
        JournalEntry.status.in_(['confirmed', 'approved']),
    ).order_by(JournalEntry.entry_date, JournalEntry.entry_number).all()

    ledger = _account_balances(start, end) if book == 'ledger' else []
    totals = {
        'debit': sum(e.total_debit or 0 for e in entries),
        'credit': sum(e.total_credit or 0 for e in entries),
    }
    unbalanced = [e for e in entries if round((e.total_debit or 0) - (e.total_credit or 0), 2) != 0]

    return render_template('tax/legal_books.html', entries=entries, ledger=ledger,
                           year=year, book=book, totals=totals, unbalanced=unbalanced)


@compliance_bp.route('/tax/legal-books/export')
@login_required
def legal_books_export():
    from models.accounting import Account, JournalEntry, JournalItem

    year = request.args.get('year', type=int) or _current_jalali_year()
    start = jdatetime.date(year, 1, 1).togregorian()
    end = jdatetime.date(year + 1, 1, 1).togregorian()

    entries = JournalEntry.query.filter(
        JournalEntry.entry_date >= start,
        JournalEntry.entry_date < end,
        JournalEntry.status.in_(['confirmed', 'approved']),
    ).order_by(JournalEntry.entry_date, JournalEntry.entry_number).all()

    journal_rows = []
    for entry in entries:
        for item in entry.items.order_by(JournalItem.row_number).all():
            account = Account.query.get(item.account_id)
            journal_rows.append([
                entry.entry_number, gregorian_to_jalali(entry.entry_date),
                account.code if account else '', account.name if account else '',
                item.description or entry.description or '',
                round(item.debit or 0), round(item.credit or 0),
            ])

    ledger_rows = [[
        row['code'], row['name'], row['type'] or '',
        round(row['debit']), round(row['credit']), round(row['balance']),
    ] for row in _account_balances(start, end)]

    return excel_response(f'legal_books_{year}.xlsx', {
        'دفتر روزنامه': {
            'headers': ['شماره سند', 'تاریخ', 'کد حساب', 'نام حساب', 'شرح', 'بدهکار', 'بستانکار'],
            'rows': journal_rows, 'widths': [14, 14, 14, 28, 36, 18, 18],
        },
        'دفتر کل': {
            'headers': ['کد حساب', 'نام حساب', 'نوع', 'جمع بدهکار', 'جمع بستانکار', 'مانده'],
            'rows': ledger_rows, 'widths': [14, 30, 14, 18, 18, 18],
        },
    })
