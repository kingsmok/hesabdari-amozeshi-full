"""
سیستم حقوق و دستمزد پیشرفته
- حقوق ثابت، ساعتی، درصدی، جلسه‌ای
- ورکشاپ و بوتکمپ (ساعتی + درصدی)
- محاسبه مالیات
- مدیریت هزینه‌های پیشرفته
"""
from datetime import datetime, date, timedelta
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from license_client import license_required, licensed_section
from extensions import db
from utils.form_helpers import get_jalali_date

payroll_bp = Blueprint('payroll', __name__)


# ═══════════════════════════════════════════
#  داشبورد حقوق و دستمزد
# ═══════════════════════════════════════════
@payroll_bp.route('/payroll')
@license_required
@login_required
@licensed_section('payroll')
def dashboard():
    from models.teacher import Teacher
    from models.finance import Payslip, SalaryContract
    
    teachers = Teacher.query.filter_by(is_active=True).all()
    contracts = SalaryContract.query.filter_by(is_active=True).all()
    recent_payslips = Payslip.query.order_by(Payslip.created_at.desc()).limit(20).all()
    
    # آمار
    total_paid = db.session.query(db.func.sum(Payslip.net_amount)).filter(
        Payslip.status == 'paid'
    ).scalar() or 0
    
    total_pending = db.session.query(db.func.sum(Payslip.net_amount)).filter(
        Payslip.status.in_(['draft', 'approved'])
    ).scalar() or 0
    
    return render_template('payroll/dashboard.html',
                         teachers=teachers, contracts=contracts,
                         recent_payslips=recent_payslips,
                         total_paid=total_paid, total_pending=total_pending)


# ═══════════════════════════════════════════
#  قرارداد حقوقی
# ═══════════════════════════════════════════
@payroll_bp.route('/payroll/contracts')
@login_required
def contracts():
    from models.finance import SalaryContract
    contracts = SalaryContract.query.order_by(SalaryContract.created_at.desc()).all()
    return render_template('payroll/contracts.html', contracts=contracts)


@payroll_bp.route('/payroll/contracts/add', methods=['GET', 'POST'])
@login_required
def add_contract():
    from models.finance import SalaryContract
    from models.teacher import Teacher
    
    if request.method == 'POST':
        contract = SalaryContract(
            person_type=request.form['person_type'],
            person_id=int(request.form['person_id']),
            contract_type=request.form['contract_type'],
            base_salary=float(request.form.get('base_salary', 0) or 0),
            hourly_rate=float(request.form.get('hourly_rate', 0) or 0),
            session_rate=float(request.form.get('session_rate', 0) or 0),
            percentage_rate=float(request.form.get('percentage_rate', 0) or 0),
            commission_rate=float(request.form.get('commission_rate', 0) or 0),
            insurance_amount=float(request.form.get('insurance_amount', 0) or 0),
            tax_amount=float(request.form.get('tax_amount', 0) or 0),
            start_date=get_jalali_date(request.form, 'start_date') if request.form.get('start_date') else None,
            end_date=get_jalali_date(request.form, 'end_date') if request.form.get('end_date') else None,
            is_active=True,
            notes=request.form.get('notes')
        )
        db.session.add(contract)
        db.session.commit()
        flash('قرارداد حقوقی ثبت شد', 'success')
        return redirect(url_for('payroll.contracts'))
    
    teachers = Teacher.query.filter_by(is_active=True).all()
    return render_template('payroll/add_contract.html', teachers=teachers)


# ═══════════════════════════════════════════
#  محاسبه حقوق
# ═══════════════════════════════════════════
@payroll_bp.route('/payroll/calculate', methods=['GET', 'POST'])
@login_required
def calculate():
    """محاسبه خودکار حقوق بر اساس نوع قرارداد"""
    from models.teacher import Teacher
    from models.finance import SalaryContract, Payslip
    from models.attendance import TeacherAttendance
    from models.classes import ClassGroup
    from models.registration import Registration
    
    if request.method == 'POST':
        period = request.form['period']  # مثال: 1405/04
        teacher_ids = request.form.getlist('teacher_ids')
        
        count = 0
        for tid in teacher_ids:
            teacher = Teacher.query.get(int(tid))
            if not teacher:
                continue
            
            contract = SalaryContract.query.filter_by(
                person_type='teacher', person_id=int(tid), is_active=True
            ).first()
            
            if not contract:
                continue
            
            # محاسبه بر اساس نوع قرارداد
            base = contract.base_salary or 0
            teaching_hours = 0
            teaching_amount = 0
            sessions_count = 0
            session_amount = 0
            commission_amount = 0
            
            if contract.contract_type == 'hourly':
                # ساعتی: تعداد ساعات تدریس × نرخ ساعتی
                attendances = TeacherAttendance.query.filter_by(teacher_id=int(tid)).all()
                teaching_hours = sum(a.teaching_hours or 0 for a in attendances)
                teaching_amount = teaching_hours * (contract.hourly_rate or 0)
            
            elif contract.contract_type == 'session':
                # جلسه‌ای: تعداد جلسات × نرخ جلسه
                classes = ClassGroup.query.filter_by(teacher_id=int(tid), status='active').all()
                for cls in classes:
                    sessions_count += cls.completed_sessions_count or 0
                session_amount = sessions_count * (contract.session_rate or 0)
            
            elif contract.contract_type == 'percentage':
                # درصدی: درصد از شهریه هنرجویان
                classes = ClassGroup.query.filter_by(teacher_id=int(tid), status='active').all()
                total_fee = 0
                for cls in classes:
                    regs = Registration.query.filter_by(class_id=cls.id, status='active').all()
                    for r in regs:
                        total_fee += r.paid_amount or 0
                commission_amount = total_fee * (contract.percentage_rate / 100)
            
            elif contract.contract_type == 'combined':
                # ترکیبی: ساعتی + درصدی
                attendances = TeacherAttendance.query.filter_by(teacher_id=int(tid)).all()
                teaching_hours = sum(a.teaching_hours or 0 for a in attendances)
                teaching_amount = teaching_hours * (contract.hourly_rate or 0)
                
                classes = ClassGroup.query.filter_by(teacher_id=int(tid), status='active').all()
                total_fee = 0
                for cls in classes:
                    regs = Registration.query.filter_by(class_id=cls.id, status='active').all()
                    for r in regs:
                        total_fee += r.paid_amount or 0
                commission_amount = total_fee * (contract.percentage_rate / 100)
            
            # محاسبه ناخالص
            gross = base + teaching_amount + session_amount + commission_amount
            
            # کسورات
            insurance = contract.insurance_amount or 0
            tax = contract.tax_amount or 0
            total_deductions = insurance + tax
            
            # خالص
            net = gross - total_deductions
            
            # صدور فیش
            last = Payslip.query.order_by(Payslip.id.desc()).first()
            ps_num = f'PS-{(last.id + 1) if last else 1:06d}'
            
            payslip = Payslip(
                payslip_number=ps_num,
                person_type='teacher',
                person_id=int(tid),
                period=period,
                base_amount=base,
                teaching_hours=teaching_hours,
                teaching_amount=teaching_amount,
                sessions_count=sessions_count,
                session_amount=session_amount,
                commission_amount=commission_amount,
                gross_amount=gross,
                insurance=insurance,
                tax=tax,
                total_deductions=total_deductions,
                net_amount=net,
                status='draft',
                created_by=current_user.id
            )
            db.session.add(payslip)
            count += 1
        
        db.session.commit()
        flash(f'{count} فیش حقوقی صدور شد', 'success')
        return redirect(url_for('payroll.dashboard'))
    
    teachers = Teacher.query.filter_by(is_active=True).all()
    return render_template('payroll/calculate.html', teachers=teachers)


# ═══════════════════════════════════════════
#  مشاهده فیش حقوقی
# ═══════════════════════════════════════════
@payroll_bp.route('/payroll/payslip/<int:id>')
@login_required
def view_payslip(id):
    from models.finance import Payslip
    payslip = Payslip.query.get_or_404(id)
    return render_template('payroll/view_payslip.html', payslip=payslip)


@payroll_bp.route('/payroll/payslip/<int:id>/approve', methods=['POST'])
@login_required
def approve_payslip(id):
    from models.finance import Payslip
    payslip = Payslip.query.get_or_404(id)
    payslip.status = 'approved'
    payslip.approved_by = current_user.id
    db.session.commit()
    flash('فیش حقوقی تأیید شد', 'success')
    return redirect(url_for('payroll.view_payslip', id=id))


@payroll_bp.route('/payroll/payslip/<int:id>/pay', methods=['POST'])
@login_required
def pay_payslip(id):
    from models.finance import Payslip, Cashbox, CashboxTransaction
    payslip = Payslip.query.get_or_404(id)
    payslip.status = 'paid'
    payslip.paid_date = date.today()
    
    # کسر از صندوق
    cashbox = Cashbox.query.first()
    if cashbox:
        cashbox.balance = (cashbox.balance or 0) - payslip.net_amount
        tx = CashboxTransaction(
            cashbox_id=cashbox.id, trans_type='out',
            amount=payslip.net_amount,
            description=f'پرداخت حقوق {payslip.payslip_number}',
            reference_type='salary',
            balance_after=cashbox.balance,
            created_by=current_user.id
        )
        db.session.add(tx)
    
    db.session.commit()
    flash('حقوق پرداخت شد', 'success')
    return redirect(url_for('payroll.view_payslip', id=id))


# ═══════════════════════════════════════════
#  مالیات
# ═══════════════════════════════════════════
@payroll_bp.route('/payroll/tax')
@login_required
def tax_report():
    """گزارش مالیاتی"""
    from models.finance import Payslip
    
    period = request.args.get('period', '')
    
    query = Payslip.query
    if period:
        query = query.filter_by(period=period)
    
    payslips = query.order_by(Payslip.created_at.desc()).all()
    
    total_gross = sum(p.gross_amount or 0 for p in payslips)
    total_tax = sum(p.tax or 0 for p in payslips)
    total_insurance = sum(p.insurance or 0 for p in payslips)
    total_net = sum(p.net_amount or 0 for p in payslips)
    
    return render_template('payroll/tax_report.html',
                         payslips=payslips, period=period,
                         total_gross=total_gross, total_tax=total_tax,
                         total_insurance=total_insurance, total_net=total_net)


# ═══════════════════════════════════════════
#  هزینه‌های پیشرفته
# ═══════════════════════════════════════════
@payroll_bp.route('/expenses/advanced')
@login_required
def advanced_expenses():
    """مدیریت پیشرفته هزینه‌ها"""
    from models.finance import Expense, ExpenseCategory
    
    # فیلتر
    category_id = request.args.get('category_id', '')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    
    query = Expense.query
    if category_id:
        selected_category_id = request.args.get('category_id', type=int)
        if selected_category_id:
            query = query.filter_by(category_id=selected_category_id)
    if date_from:
        parsed_from = get_jalali_date(request.args, 'date_from')
        if parsed_from:
            query = query.filter(Expense.expense_date >= parsed_from)
    if date_to:
        parsed_to = get_jalali_date(request.args, 'date_to')
        if parsed_to:
            query = query.filter(Expense.expense_date <= parsed_to)
    
    expenses = query.order_by(Expense.expense_date.desc()).all()
    categories = ExpenseCategory.query.filter_by(is_active=True).order_by(ExpenseCategory.name).all()
    
    # آمار
    total = sum(e.amount for e in expenses)
    by_category = {}
    for e in expenses:
        cat_name = e.category.name if e.category else 'سایر'
        by_category[cat_name] = by_category.get(cat_name, 0) + e.amount
    
    return render_template('payroll/advanced_expenses.html',
                         expenses=expenses, categories=categories,
                         total=total, by_category=by_category,
                         category_id=category_id, date_from=date_from, date_to=date_to)


@payroll_bp.route('/expenses/advanced/add', methods=['GET', 'POST'])
@login_required
def add_advanced_expense():
    """ثبت هزینه پیشرفته"""
    from models.finance import Expense, ExpenseCategory

    categories = ExpenseCategory.query.filter_by(is_active=True).order_by(ExpenseCategory.name).all()
    
    if request.method == 'POST':
        category_id = request.form.get('category_id', type=int)
        category = ExpenseCategory.query.filter_by(id=category_id, is_active=True).first() if category_id else None
        try:
            amount = float(request.form.get('amount') or 0)
        except (TypeError, ValueError):
            amount = 0

        if not category:
            flash('لطفاً یک دسته‌بندی هزینه فعال انتخاب کنید', 'danger')
            return render_template('payroll/add_expense.html', categories=categories), 400
        if amount <= 0:
            flash('مبلغ هزینه باید بیشتر از صفر باشد', 'danger')
            return render_template('payroll/add_expense.html', categories=categories), 400

        last = Expense.query.order_by(Expense.id.desc()).first()
        exp_num = f'EXP-{(last.id + 1) if last else 1:06d}'
        
        expense = Expense(
            expense_number=exp_num,
            category_id=category.id,
            amount=amount,
            description=(request.form.get('description') or '').strip() or None,
            expense_date=get_jalali_date(request.form, 'expense_date') if request.form.get('expense_date') else date.today(),
            payment_method=request.form.get('payment_method'),
            paid_to=(request.form.get('paid_to') or '').strip() or None,
            branch_id=request.form.get('branch_id', 1),
            created_by=current_user.id
        )
        
        # آپلود فاکتور
        if 'attachment' in request.files:
            file = request.files['attachment']
            if file.filename:
                import os, uuid
                ext = os.path.splitext(file.filename)[1]
                filename = f'{uuid.uuid4().hex}{ext}'
                filepath = os.path.join('static', 'uploads', 'expenses', filename)
                os.makedirs(os.path.dirname(filepath), exist_ok=True)
                file.save(filepath)
                expense.attachment = filepath
        
        db.session.add(expense)
        db.session.commit()
        flash(f'هزینه در دسته‌بندی «{category.name}» ثبت شد', 'success')
        return redirect(url_for('payroll.advanced_expenses'))
    
    return render_template('payroll/add_expense.html', categories=categories)


@payroll_bp.route('/expenses/categories')
@login_required
def expense_categories():
    """مسیر قدیمی؛ مدیریت دسته‌بندی‌ها اکنون از یک صفحه واحد انجام می‌شود."""
    return redirect(url_for('settings.expense_categories'))


@payroll_bp.route('/expenses/categories/add', methods=['POST'])
@login_required
def add_expense_category():
    """سازگاری با فرم نسخه‌های قدیمی برنامه."""
    from models.finance import ExpenseCategory

    name = (request.form.get('name') or '').strip()
    code = (request.form.get('code') or '').strip().upper() or None
    if not name:
        flash('نام دسته‌بندی هزینه الزامی است', 'danger')
        return redirect(url_for('settings.expense_categories'))

    duplicate = ExpenseCategory.query.filter(db.func.lower(ExpenseCategory.name) == name.lower()).first()
    duplicate_code = code and ExpenseCategory.query.filter(db.func.lower(ExpenseCategory.code) == code.lower()).first()
    if duplicate or duplicate_code:
        flash('نام یا کد دسته‌بندی تکراری است', 'danger')
        return redirect(url_for('settings.expense_categories'))

    cat = ExpenseCategory(
        name=name,
        code=code,
        description=(request.form.get('description') or '').strip() or None,
        is_active=True
    )
    db.session.add(cat)
    db.session.commit()
    flash(f'دسته‌بندی «{name}» اضافه شد', 'success')
    return redirect(url_for('settings.expense_categories'))


# ═══════════════════════════════════════════
#  گزارش مالی جامع
# ═══════════════════════════════════════════
@payroll_bp.route('/reports/comprehensive')
@login_required
def comprehensive_report():
    """گزارش مالی جامع"""
    from models.finance import Payment, Expense, Payslip
    from models.registration import Registration
    
    today = date.today()
    month_start = today.replace(day=1)
    
    # درآمد ماه
    income = db.session.query(db.func.sum(Payment.amount)).filter(
        Payment.payment_date >= month_start,
        Payment.status == 'confirmed'
    ).scalar() or 0
    
    # هزینه ماه
    expenses = db.session.query(db.func.sum(Expense.amount)).filter(
        Expense.expense_date >= month_start,
        Expense.status == 'confirmed'
    ).scalar() or 0
    
    # حقوق ماه
    salaries = db.session.query(db.func.sum(Payslip.net_amount)).filter(
        Payslip.period == f'{today.year}/{today.month:02d}'
    ).scalar() or 0
    
    # مالیات ماه
    taxes = db.session.query(db.func.sum(Payslip.tax)).filter(
        Payslip.period == f'{today.year}/{today.month:02d}'
    ).scalar() or 0
    
    # بدهکاران
    total_debt = db.session.query(db.func.sum(Registration.remaining_amount)).filter(
        Registration.remaining_amount > 0,
        Registration.status == 'active'
    ).scalar() or 0
    
    return render_template('payroll/comprehensive_report.html',
                         income=income, expenses=expenses,
                         salaries=salaries, taxes=taxes,
                         total_debt=total_debt,
                         profit=income - expenses - salaries)
