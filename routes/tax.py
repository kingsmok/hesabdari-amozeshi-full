"""
سیستم مالیاتی کامل
- محاسبه مالیات بر اساس براکت‌های ایران
- صدور فیش مالیاتی
- گزارش سالانه مالیات
- ارسال لیست مالیات به اداره دارایی
"""
from datetime import datetime, date
from flask import Blueprint, abort, render_template, request, redirect, url_for, flash, make_response
from flask_login import login_required, current_user
from license_client import license_required, licensed_section
from extensions import db
from utils.access_policy import require_role
from utils.form_helpers import safe_float, safe_int
from utils.tax_rules import (annual_brackets_display, calculate_salary_tax_annual,
                             calculate_salary_tax_monthly, get_rule, invalidate_rule_cache,
                             suggested_insurance)
import io

tax_bp = Blueprint('tax', __name__)


def _log_tax(action, description, entity_type=None, entity_id=None):
    """ثبت رویدادهای مالیاتی — نقطهٔ مشترک در utils/activity_log (DRY)."""
    from utils.activity_log import log_activity
    log_activity(action, description, module='tax',
                 entity_type=entity_type, entity_id=entity_id)


# ═══════════════════════════════════════════
#  جدول مالیات حقوق
# ═══════════════════════════════════════════
# اعداد پلکانی دیگر در کد هاردکد نیستند؛ از جدول tax_rules (صفحه «تنظیمات
# مالیاتی») و در نبودش از پیش‌فرض ماده ۱ قانون بودجه ۱۴۰۵ خوانده می‌شوند:
# معافیت ماهانه ۴۰٬۰۰۰٬۰۰۰ تومان و پلکان‌های ۱۰/۱۵/۲۰/۲۵/۳۰ درصد.
# نام TAX_BRACKETS_1405 برای سازگاری با کدها و قالب‌های قبلی نگه داشته شده و
# به‌صورت تابع محاسبه می‌شود (annual brackets = پلکان ماهانه × ۱۲).
def TAX_BRACKETS_FOR(year=None):
    return annual_brackets_display(year)


class _BracketsProxy(list):
    """نمایش سالانه پلکان‌ها برای قالب‌های قدیمی (indexable مثل list)."""


def _brackets_for_current_year():
    return annual_brackets_display()


TAX_BRACKETS_1405 = _brackets_for_current_year()


def brackets_for_year(year=None):
    return annual_brackets_display(year)


def calculate_tax(annual_income, year=None):
    """مالیات از روی درآمد سالیانه — پلکان‌بندی تصاعدی (ماده ۸۵)."""
    return calculate_salary_tax_annual(annual_income, year)


def calculate_monthly_tax(monthly_income, year=None):
    """مالیات یک ماه حقوق — مبنای واقعی قانون، نه تقسیم سالانه."""
    tax, _ = calculate_salary_tax_monthly(monthly_income, year)
    return tax


# ═══════════════════════════════════════════
#  داشبورد مالیاتی
# ═══════════════════════════════════════════
@tax_bp.route('/tax')
@license_required
@login_required
@licensed_section('tax')
def dashboard():
    from models.finance import Payslip
    from models.teacher import Teacher
    from utils.jalali import current_jalali_period

    # سال پیش‌فرض دیگر هاردکد «۱۴۰۵» نیست؛ از تقویم جاری می‌آید
    year = request.args.get('year', '') or current_jalali_period().split('/')[0]

    # آمار مالیاتی سال
    payslips = Payslip.query.filter(
        Payslip.period.like(f'{year}%')
    ).all()
    
    total_gross = sum(p.gross_amount or 0 for p in payslips)
    total_tax = sum(p.tax or 0 for p in payslips)
    total_insurance = sum(p.insurance or 0 for p in payslips)
    total_net = sum(p.net_amount or 0 for p in payslips)
    
    # تفکیک هر شخص
    person_tax = {}
    for p in payslips:
        key = (p.person_type, p.person_id)
        if key not in person_tax:
            person_tax[key] = {'gross': 0, 'tax': 0, 'insurance': 0, 'net': 0, 'count': 0}
        person_tax[key]['gross'] += p.gross_amount or 0
        person_tax[key]['tax'] += p.tax or 0
        person_tax[key]['insurance'] += p.insurance or 0
        person_tax[key]['net'] += p.net_amount or 0
        person_tax[key]['count'] += 1
    
    # بهینه‌سازی N+1: نام مدرس‌ها یک‌جا load می‌شود
    # (full_name پراپرتی است؛ first/last جدا انتخاب و ترکیب می‌شوند)
    teacher_names = {
        row[0]: f'{row[1]} {row[2]}'
        for row in db.session.query(Teacher.id, Teacher.first_name, Teacher.last_name).all()
    }
    persons = []
    for (ptype, pid), data in person_tax.items():
        name = teacher_names.get(pid, '-') if ptype == 'teacher' else '-'
        persons.append({'type': ptype, 'id': pid, 'name': name, **data})
    
    persons.sort(key=lambda x: x['tax'], reverse=True)
    
    return render_template('tax/dashboard.html',
                         year=year, total_gross=total_gross,
                         total_tax=total_tax, total_insurance=total_insurance,
                         total_net=total_net, persons=persons)


# ═══════════════════════════════════════════
#  محاسبه‌گر مالیات
# ═══════════════════════════════════════════
@tax_bp.route('/tax/calculator', methods=['GET', 'POST'])
@login_required
def calculator():
    result = None
    breakdown = []
    
    year = request.form.get('year') or request.args.get('year') or None

    if request.method == 'POST':
        income_type = request.form.get('income_type', 'monthly')
        amount = safe_float(request.form.get('amount'))
        insurance = safe_float(request.form.get('insurance'))

        if income_type == 'monthly':
            annual = (amount - insurance) * 12
        else:
            annual = amount - (insurance * 12)

        total_tax, breakdown = calculate_tax(annual, year)
        monthly_tax = total_tax / 12
        
        result = {
            'gross_monthly': amount,
            'insurance': insurance,
            'taxable_annual': annual,
            'annual_tax': total_tax,
            'monthly_tax': monthly_tax,
            'net_monthly': amount - insurance - monthly_tax,
        }
    
    return render_template('tax/calculator.html', result=result, breakdown=breakdown,
                           brackets=brackets_for_year(year), rule=get_rule(year), year=year or '')


# ═══════════════════════════════════════════
#  فیش مالیاتی
# ═══════════════════════════════════════════
@tax_bp.route('/tax/receipt/<int:payslip_id>')
@login_required
def tax_receipt(payslip_id):
    """صدور فیش مالیاتی برای یک فیش حقوقی"""
    from models.finance import Payslip
    from models.teacher import Teacher
    
    payslip = Payslip.query.get_or_404(payslip_id)
    
    person_name = '-'
    if payslip.person_type == 'teacher':
        t = Teacher.query.get(payslip.person_id)
        if t:
            person_name = t.full_name
    
    # محاسبه مالیات سالانه
    annual_income = (payslip.gross_amount or 0) * 12
    annual_tax, breakdown = calculate_tax(annual_income)
    
    return render_template('tax/receipt.html',
                         payslip=payslip, person_name=person_name,
                         annual_income=annual_income,
                         annual_tax=annual_tax, breakdown=breakdown)


# ═══════════════════════════════════════════
#  گزارش سالانه مالیات
# ═══════════════════════════════════════════
@tax_bp.route('/tax/annual-report')
@login_required
def annual_report():
    """گزارش سالانه مالیات برای اداره دارایی"""
    from models.finance import Payslip
    from models.teacher import Teacher
    
    from utils.jalali import current_jalali_period, normalize_jalali_period
    requested = (request.args.get('year') or '').strip()
    normalized = normalize_jalali_period(requested) or normalize_jalali_period(f'{requested}/01')
    year = (normalized or current_jalali_period()).split('/')[0]

    payslips = Payslip.query.filter(
        Payslip.period.like(f'{year}%')
    ).all()

    # تجمع سالانه هر شخص
    annual = {}
    for p in payslips:
        key = p.person_id
        if key not in annual:
            annual[key] = {
                'person_type': p.person_type,
                'gross': 0, 'insurance': 0, 'tax': 0, 'net': 0, 'months': 0, 'real_tax': 0
            }
        annual[key]['gross'] += p.gross_amount or 0
        annual[key]['insurance'] += p.insurance or 0
        annual[key]['tax'] += p.tax or 0
        annual[key]['net'] += p.net_amount or 0
        annual[key]['months'] += 1
        month_tax, _ = calculate_salary_tax_monthly((p.gross_amount or 0) - (p.insurance or 0), year)
        annual[key]['real_tax'] += month_tax
    
    # بهینه‌سازی N+1: نام مدرس‌ها یک‌جا load می‌شود
    teacher_names = {
        row[0]: f'{row[1]} {row[2]}'
        for row in db.session.query(Teacher.id, Teacher.first_name, Teacher.last_name).all()
    }

    # تکمیل اطلاعات
    report = []
    for pid, data in annual.items():
        name = '-'
        if data['person_type'] == 'teacher':
            name = teacher_names.get(pid, '-')
        
        # مالیات واقعی = جمع مالیات پلکانی ماه‌های همان شخص
        # (یک‌بار محاسبه روی جمع سال، ماه‌های معاف را هم مشمول پلکان‌های بالا می‌کرد)
        real_tax = data['real_tax']

        report.append({
            'person_id': pid,
            'name': name,
            'type': data['person_type'],
            'gross': data['gross'],
            'insurance': data['insurance'],
            'tax_calculated': data['tax'],
            'tax_real': real_tax,
            'net': data['net'],
            'months': data['months']
        })
    
    report.sort(key=lambda x: x['gross'], reverse=True)
    
    total_gross = sum(r['gross'] for r in report)
    total_tax = sum(r['tax_calculated'] for r in report)
    total_insurance = sum(r['insurance'] for r in report)
    
    return render_template('tax/annual_report.html',
                         year=year, report=report,
                         total_gross=total_gross, total_tax=total_tax,
                         total_insurance=total_insurance)


# ═══════════════════════════════════════════
#  لیست مالیات ماهانه (برای اداره دارایی)
# ═══════════════════════════════════════════
@tax_bp.route('/tax/monthly-list')
@login_required
def monthly_list():
    """لیست مالیات ماهانه"""
    from models.finance import Payslip
    from models.teacher import Teacher
    
    period = request.args.get('period', '')
    
    query = Payslip.query
    if period:
        query = query.filter_by(period=period)
    
    payslips = query.order_by(Payslip.created_at.desc()).all()
    
    return render_template('tax/monthly_list.html', payslips=payslips, period=period)


# ═══════════════════════════════════════════
#  محاسبه خودکار مالیات فیش‌ها
# ═══════════════════════════════════════════
@tax_bp.route('/tax/auto-calculate', methods=['POST'])
@login_required
def auto_calculate():
    """محاسبه خودکار مالیات برای تمام فیش‌های دوره"""
    from models.finance import Payslip
    
    from utils.jalali import normalize_jalali_period

    period = normalize_jalali_period(request.form.get('period'))
    if not period:
        flash('دوره را به شکل ۱۴۰۵/۰۶ وارد کنید', 'danger')
        return redirect(url_for('tax.dashboard'))

    payslips = Payslip.query.filter_by(period=period).all()

    count = 0
    skipped = 0
    for p in payslips:
        if p.status == 'paid':
            skipped += 1                      # فیش پرداخت‌شده نباید تغییر کند
            continue
        insurance = p.insurance or 0
        taxable_month = (p.gross_amount or 0) - insurance
        monthly_tax = calculate_monthly_tax(taxable_month, period.split('/')[0])

        p.tax = monthly_tax
        p.total_deductions = (p.deductions or 0) + insurance + monthly_tax + (p.penalty or 0)
        p.net_amount = (p.gross_amount or 0) - p.total_deductions
        count += 1

    _log_tax('edit', f'محاسبه خودکار مالیات دوره {period} برای {count} فیش')
    db.session.commit()
    message = f'مالیات {count} فیش برای دوره {period} محاسبه شد'
    if skipped:
        message += f' — {skipped} فیش پرداخت‌شده دست نخورد'
    flash(message, 'success' if count else 'warning')
    return redirect(url_for('tax.dashboard', period=period))


# ═══════════════════════════════════════════
#  تنظیمات مالیاتی (قواعد سالانه حقوق و بیمه)
# ═══════════════════════════════════════════
@tax_bp.route('/tax/rules')
@login_required
def tax_rules():
    """مدیریت پلکان معافیت/نرخ مالیات حقوق و حق بیمه به تفکیک سال.

    تا پیش از این این اعداد داخل کد هاردکد بود؛ با تصویب بودجه سال بعد باید
    کد تغییر می‌کرد (و در عمل اعداد ۱۴۰۴ روی ۱۴۰۵ مانده بود).
    """
    import json

    from models.system import TaxRule
    from utils.tax_rules import DEFAULT_RULES

    rules = TaxRule.query.order_by(TaxRule.year.desc()).all()
    effective = get_rule()

    # نمونه محاسبه با قواعد جاری، تا کاربر از صحت اعداد مطمئن شود
    preview = []
    for step in range(7):
        monthly = step * 20_000_000
        tax, _ = calculate_salary_tax_monthly(monthly, effective['year'])
        insurance = suggested_insurance(monthly, effective['year'])
        preview.append({'monthly': monthly, 'tax': tax, 'insurance': insurance,
                        'net': monthly - tax - insurance})

    return render_template('tax/tax_rules.html', rules=rules, effective=effective,
                           defaults=DEFAULT_RULES, preview=preview,
                           json=json)


@tax_bp.route('/tax/rules/save', methods=['POST'])
@login_required
@require_role('tax', 'edit')
def save_tax_rules():
    """ثبت/ویرایش قواعد یک سال (upsert روی شماره سال)."""
    import json

    from models.system import TaxRule
    from utils.jalali import normalize_jalali_period
    from utils.tax_rules import normalize_brackets

    raw_year = (request.form.get('year') or '').strip()
    year = raw_year[:4]
    if not (year.isdigit() and 1300 <= int(year) <= 1700):
        normalized = normalize_jalali_period(raw_year)
        year = normalized.split('/')[0] if normalized else ''
    if not year:
        flash('سال باید چهار رقم شمسی باشد (نمونه: ۱۴۰۵)', 'danger')
        return redirect(url_for('tax.tax_rules'))

    exemption = safe_float(request.form.get('monthly_exemption'))
    if exemption < 0:
        flash('سقف معافیت ماهانه نمی‌تواند منفی باشد', 'danger')
        return redirect(url_for('tax.tax_rules'))

    starts = request.form.getlist('bracket_from')
    ends = request.form.getlist('bracket_to')
    rates = request.form.getlist('bracket_rate')
    brackets = []
    for index, rate_value in enumerate(rates):
        rate = safe_float(rate_value)
        if rate <= 0:
            continue                      # پلکان خالی نادیده گرفته می‌شود
        brackets.append({'from': safe_float(starts[index]) if index < len(starts) else 0,
                         'to': safe_float(ends[index]) if index < len(ends) else None,
                         'rate': rate / 100.0 if rate > 1 else rate})
    brackets = normalize_brackets(brackets)
    if not brackets:
        flash('حداقل یک پلکان با نرخ معتبر وارد کنید', 'danger')
        return redirect(url_for('tax.tax_rules'))

    rule = TaxRule.query.filter_by(year=year).first()
    if rule is None:
        rule = TaxRule(year=year)
        db.session.add(rule)
    rule.monthly_exemption = exemption
    rule.brackets = json.dumps(brackets, ensure_ascii=False)
    rule.insurance_employee_rate = safe_float(request.form.get('insurance_employee_rate'), 7) / 100.0
    rule.insurance_employer_rate = safe_float(request.form.get('insurance_employer_rate'), 23) / 100.0
    rule.note = (request.form.get('note') or '').strip() or None
    rule.is_active = request.form.get('is_active') == 'on' or rule.is_active is None
    rule.updated_by = current_user.id
    invalidate_rule_cache()

    _log_tax('edit', f'به‌روزرسانی قواعد مالیات حقوق سال {year}', 'tax_rule', rule.id)
    db.session.commit()
    flash(f'قواعد مالیاتی سال {year} ذخیره شد', 'success')
    return redirect(url_for('tax.tax_rules'))


@tax_bp.route('/tax/rules/<int:id>/delete', methods=['POST'])
@login_required
@require_role('tax', 'delete')
def delete_tax_rule(id):
    """حذف قواعد یک سال → بازگشت به پیش‌فرض داخل کد."""
    from models.system import TaxRule

    rule = TaxRule.query.get_or_404(id)
    year = rule.year
    db.session.delete(rule)
    invalidate_rule_cache()
    _log_tax('delete', f'حذف قواعد مالیاتی سال {year}', 'tax_rule', id)
    db.session.commit()
    flash(f'قواعد سال {year} حذف شد؛ از این پس پیش‌فرض کد اعمال می‌شود', 'warning')
    return redirect(url_for('tax.tax_rules'))
