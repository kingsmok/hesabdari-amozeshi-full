"""
سیستم مالیاتی کامل
- محاسبه مالیات بر اساس براکت‌های ایران
- صدور فیش مالیاتی
- گزارش سالانه مالیات
- ارسال لیست مالیات به اداره دارایی
"""
from datetime import datetime, date
from flask import Blueprint, render_template, request, redirect, url_for, flash, make_response
from flask_login import login_required, current_user
from license_client import license_required, licensed_section
from extensions import db
import io

tax_bp = Blueprint('tax', __name__)


# ═══════════════════════════════════════════
#  براکت‌های مالیاتی ایران ۱۴۰۵
# ═══════════════════════════════════════════
TAX_BRACKETS_1405 = [
    {'min': 0, 'max': 120000000, 'rate': 0.00, 'label': 'معاف'},
    {'min': 120000000, 'max': 200000000, 'rate': 0.10, 'label': '۱۰٪'},
    {'min': 200000000, 'max': 400000000, 'rate': 0.15, 'label': '۱۵٪'},
    {'min': 400000000, 'max': 600000000, 'rate': 0.20, 'label': '۲۰٪'},
    {'min': 600000000, 'max': 800000000, 'rate': 0.25, 'label': '۲۵٪'},
    {'min': 800000000, 'max': 1000000000, 'rate': 0.30, 'label': '۳۰٪'},
    {'min': 1000000000, 'max': None, 'rate': 0.35, 'label': '۳۵٪'},
]


def calculate_tax(annual_income):
    """محاسبه مالیات بر اساس درآمد سالانه — براکت‌بندی تصاعدی"""
    if annual_income <= 0:
        return 0, []
    
    total_tax = 0
    breakdown = []
    
    for bracket in TAX_BRACKETS_1405:
        if annual_income <= bracket['min']:
            break
        
        if bracket['max'] is None:
            taxable = annual_income - bracket['min']
        else:
            taxable = min(annual_income, bracket['max']) - bracket['min']
        
        if taxable > 0:
            tax = taxable * bracket['rate']
            total_tax += tax
            breakdown.append({
                'label': bracket['label'],
                'from': bracket['min'],
                'to': bracket['max'] or annual_income,
                'taxable': taxable,
                'rate': bracket['rate'],
                'tax': tax
            })
    
    return total_tax, breakdown


def calculate_monthly_tax(monthly_income):
    """محاسبه مالیات ماهانه"""
    annual = monthly_income * 12
    annual_tax, _ = calculate_tax(annual)
    return annual_tax / 12


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
    
    year = request.args.get('year', '1405')
    
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
    
    # نام افراد
    persons = []
    for (ptype, pid), data in person_tax.items():
        name = '-'
        if ptype == 'teacher':
            t = Teacher.query.get(pid)
            if t:
                name = t.full_name
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
    
    if request.method == 'POST':
        income_type = request.form.get('income_type', 'monthly')
        amount = float(request.form.get('amount', 0))
        insurance = float(request.form.get('insurance', 0))
        
        if income_type == 'monthly':
            annual = (amount - insurance) * 12
        else:
            annual = amount - (insurance * 12)
        
        total_tax, breakdown = calculate_tax(annual)
        monthly_tax = total_tax / 12
        
        result = {
            'gross_monthly': amount,
            'insurance': insurance,
            'taxable_annual': annual,
            'annual_tax': total_tax,
            'monthly_tax': monthly_tax,
            'net_monthly': amount - insurance - monthly_tax,
        }
    
    return render_template('tax/calculator.html', result=result, breakdown=breakdown, brackets=TAX_BRACKETS_1405)


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
    
    year = request.args.get('year', '1405')
    
    payslips = Payslip.query.filter(
        Payslip.period.like(f'{year}%')
    ).all()
    
    # تجمید سالانه هر شخص
    annual = {}
    for p in payslips:
        key = p.person_id
        if key not in annual:
            annual[key] = {
                'person_type': p.person_type,
                'gross': 0, 'insurance': 0, 'tax': 0, 'net': 0, 'months': 0
            }
        annual[key]['gross'] += p.gross_amount or 0
        annual[key]['insurance'] += p.insurance or 0
        annual[key]['tax'] += p.tax or 0
        annual[key]['net'] += p.net_amount or 0
        annual[key]['months'] += 1
    
    # تکمیل اطلاعات
    report = []
    for pid, data in annual.items():
        name = '-'
        if data['person_type'] == 'teacher':
            t = Teacher.query.get(pid)
            if t:
                name = t.full_name
        
        # محاسبه مالیات واقعی بر اساس براکت
        real_tax, _ = calculate_tax(data['gross'])
        
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
    
    period = request.form.get('period', '')
    if not period:
        flash('دوره را وارد کنید', 'error')
        return redirect(url_for('tax.dashboard'))
    
    payslips = Payslip.query.filter_by(period=period).all()
    
    count = 0
    for p in payslips:
        insurance = p.insurance or 0
        annual_income = ((p.gross_amount or 0) - insurance) * 12
        annual_tax, _ = calculate_tax(annual_income)
        monthly_tax = round(annual_tax / 12)
        
        p.tax = monthly_tax
        p.total_deductions = (p.deductions or 0) + insurance + monthly_tax + (p.penalty or 0)
        p.net_amount = (p.gross_amount or 0) - p.total_deductions
        count += 1
    
    db.session.commit()
    flash(f'مالیات {count} فیش محاسبه شد', 'success')
    return redirect(url_for('tax.dashboard'))
