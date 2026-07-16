"""Finance routes - Payments, Cashbox, Bank, Checks, Expenses, Salary"""
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from extensions import db
from utils.form_helpers import get_jalali_date, safe_float, safe_int
from models.finance import (
    Payment, Cashbox, CashboxTransaction, BankAccount, BankTransaction,
    Check, Expense, ExpenseCategory, DiscountCode, SalaryContract, Payslip
)
from models.registration import Registration, Installment
from models.student import Student
from models.user import ActivityLog
from datetime import datetime

finance_bp = Blueprint('finance', __name__)


# ===== Payments =====
@finance_bp.route('/payments')
@login_required
def payments():
    page = request.args.get('page', 1, type=int)
    method = request.args.get('method', '')
    search = request.args.get('search', '')
    
    query = Payment.query
    if method:
        query = query.filter_by(payment_method=method)
    if search:
        query = query.join(Student).filter(
            db.or_(Student.first_name.contains(search), Payment.receipt_no.contains(search))
        )
    
    payments = query.order_by(Payment.created_at.desc()).paginate(page=page, per_page=20)
    return render_template('finance/payments.html', payments=payments, method=method, search=search)


@finance_bp.route('/payments/add', methods=['GET', 'POST'])
@login_required
def add_payment():
    if request.method == 'POST':
        last = Payment.query.order_by(Payment.id.desc()).first()
        import uuid; receipt_num = f'PAY-{datetime.now().strftime("%Y%m%d%H%M%S")}-{uuid.uuid4().hex[:4].upper()}'
        
        payment = Payment(
            receipt_no=receipt_num,
            student_id=request.form['student_id'],
            registration_id=request.form.get('registration_id') or None,
            amount=safe_float(request.form.get('amount')),
            payment_method=request.form['payment_method'],
            payment_date=get_jalali_date(request.form, 'payment_date') if request.form.get('payment_date') else datetime.utcnow().date(),
            card_number=request.form.get('card_number'),
            tracking_number=request.form.get('tracking_number'),
            bank_name=request.form.get('bank_name'),
            description=request.form.get('description'),
            branch_id=request.form.get('branch_id', 1),
            created_by=current_user.id
        )
        
        # Update registration
        if payment.registration_id:
            reg = Registration.query.get(payment.registration_id)
            if reg:
                reg.paid_amount = (reg.paid_amount or 0) + payment.amount
                reg.remaining_amount = reg.total_fee - reg.paid_amount
        
        # Update installment
        installment_id = request.form.get('installment_id')
        if installment_id:
            inst = Installment.query.get(installment_id)
            if inst:
                inst.paid_amount = (inst.paid_amount or 0) + payment.amount
                inst.paid_date = payment.payment_date
                inst.status = 'paid' if inst.paid_amount >= inst.amount else 'partial'
                payment.installment_id = installment_id
        
        # Update cashbox
        if payment.payment_method == 'cash':
            cashbox = Cashbox.query.first()
            if cashbox:
                cashbox.balance = (cashbox.balance or 0) + payment.amount
                tx = CashboxTransaction(
                    cashbox_id=cashbox.id,
                    trans_type='in',
                    amount=payment.amount,
                    description=f'دریافت شهریه {receipt_num}',
                    reference_type='payment',
                    balance_after=cashbox.balance,
                    created_by=current_user.id
                )
                db.session.add(tx)
        
        db.session.add(payment)
        db.session.commit()
        
        flash(f'پرداخت {receipt_num} ثبت شد', 'success')
        return redirect(url_for('finance.view_payment', id=payment.id))
    
    students = Student.query.filter_by(status='active').all()
    return render_template('finance/add_payment.html', students=students)


@finance_bp.route('/payments/<int:id>')
@login_required
def view_payment(id):
    payment = Payment.query.get_or_404(id)
    return render_template('finance/view_payment.html', payment=payment)


# ===== Cashbox =====
@finance_bp.route('/cashbox')
@login_required
def cashbox():
    cashboxes = Cashbox.query.all()
    today_tx = CashboxTransaction.query.filter(
        db.func.date(CashboxTransaction.transaction_date) == datetime.utcnow().date()
    ).order_by(CashboxTransaction.transaction_date.desc()).all()
    
    return render_template('finance/cashbox.html', cashboxes=cashboxes, today_tx=today_tx)


@finance_bp.route('/cashbox/<int:id>/transaction', methods=['POST'])
@login_required
def cashbox_transaction(id):
    cashbox = Cashbox.query.get_or_404(id)
    trans_type = request.form['trans_type']  # in or out
    amount = safe_float(request.form.get('amount'))
    
    if trans_type == 'in':
        cashbox.balance = (cashbox.balance or 0) + amount
    else:
        cashbox.balance = (cashbox.balance or 0) - amount
    
    tx = CashboxTransaction(
        cashbox_id=id,
        trans_type=trans_type,
        amount=amount,
        description=request.form.get('description'),
        reference_type=request.form.get('reference_type', 'manual'),
        balance_after=cashbox.balance,
        created_by=current_user.id
    )
    db.session.add(tx)
    db.session.commit()
    
    flash('تراکنش ثبت شد', 'success')
    return redirect(url_for('finance.cashbox'))


# ===== Bank =====
@finance_bp.route('/bank')
@login_required
def bank():
    accounts = BankAccount.query.filter_by(is_active=True).all()
    return render_template('finance/bank.html', accounts=accounts)


@finance_bp.route('/bank/add', methods=['GET', 'POST'])
@login_required
def add_bank_account():
    if request.method == 'POST':
        account = BankAccount(
            bank_name=request.form['bank_name'],
            account_number=request.form.get('account_number'),
            card_number=request.form.get('card_number'),
            sheba=request.form.get('sheba'),
            branch_name=request.form.get('branch_name'),
            balance=safe_float(request.form.get('balance')),
            description=request.form.get('description')
        )
        db.session.add(account)
        db.session.commit()
        flash('حساب بانکی اضافه شد', 'success')
        return redirect(url_for('finance.bank'))
    
    return render_template('finance/add_bank.html')


@finance_bp.route('/bank/<int:id>/transaction', methods=['POST'])
@login_required
def bank_transaction(id):
    account = BankAccount.query.get_or_404(id)
    trans_type = request.form['trans_type']
    amount = safe_float(request.form.get('amount'))
    
    if trans_type == 'deposit':
        account.balance = (account.balance or 0) + amount
    else:
        account.balance = (account.balance or 0) - amount
    
    tx = BankTransaction(
        bank_account_id=id,
        trans_type=trans_type,
        amount=amount,
        description=request.form.get('description'),
        balance_after=account.balance,
        created_by=current_user.id
    )
    db.session.add(tx)
    db.session.commit()
    
    flash('تراکنش بانکی ثبت شد', 'success')
    return redirect(url_for('finance.bank'))


# ===== Checks =====
@finance_bp.route('/checks')
@login_required
def checks():
    status = request.args.get('status', '')
    query = Check.query
    if status:
        query = query.filter_by(status=status)
    checks = query.order_by(Check.due_date).all()
    return render_template('finance/checks.html', checks=checks, status=status)


@finance_bp.route('/checks/add', methods=['GET', 'POST'])
@login_required
def add_check():
    if request.method == 'POST':
        check = Check(
            check_number=request.form['check_number'],
            bank_name=request.form['bank_name'],
            amount=safe_float(request.form.get('amount')),
            issue_date=get_jalali_date(request.form, 'issue_date'),
            due_date=get_jalali_date(request.form, 'due_date'),
            issuer_name=request.form.get('issuer_name'),
            check_type=request.form.get('check_type', 'received'),
            student_id=request.form.get('student_id') or None,
            description=request.form.get('description'),
            branch_id=request.form.get('branch_id', 1),
            created_by=current_user.id
        )
        db.session.add(check)
        db.session.commit()
        flash('چک ثبت شد', 'success')
        return redirect(url_for('finance.checks'))
    
    students = Student.query.filter_by(status='active').all()
    return render_template('finance/add_check.html', students=students)


@finance_bp.route('/checks/<int:id>/status', methods=['POST'])
@login_required
def check_status(id):
    check = Check.query.get_or_404(id)
    new_status = request.form['status']
    check.status = new_status
    if new_status == 'bounced':
        check.bounced_reason = request.form.get('reason')
        check.bounced_date = datetime.utcnow().date()
    db.session.commit()
    flash('وضعیت چک بروزرسانی شد', 'success')
    return redirect(url_for('finance.checks'))


# ===== Expenses =====
@finance_bp.route('/expenses')
@login_required
def expenses():
    page = request.args.get('page', 1, type=int)
    expenses = Expense.query.order_by(Expense.expense_date.desc()).paginate(page=page, per_page=20)
    return render_template('finance/expenses.html', expenses=expenses)


@finance_bp.route('/expenses/add', methods=['GET', 'POST'])
@login_required
def add_expense():
    if request.method == 'POST':
        last = Expense.query.order_by(Expense.id.desc()).first()
        exp_num = f'EXP-1405-{(last.id + 1) if last else 1:05d}'
        
        expense = Expense(
            expense_number=exp_num,
            category_id=request.form['category_id'],
            amount=safe_float(request.form.get('amount')),
            description=request.form.get('description'),
            expense_date=get_jalali_date(request.form, 'expense_date') if request.form.get('expense_date') else datetime.utcnow().date(),
            payment_method=request.form.get('payment_method'),
            paid_to=request.form.get('paid_to'),
            approved_by=request.form.get('approved_by'),
            branch_id=request.form.get('branch_id', 1),
            created_by=current_user.id
        )
        db.session.add(expense)
        db.session.commit()
        flash(f'هزینه {exp_num} ثبت شد', 'success')
        return redirect(url_for('finance.expenses'))
    
    categories = ExpenseCategory.query.filter_by(is_active=True).all()
    return render_template('finance/add_expense.html', categories=categories)


# ===== Discount Codes =====
@finance_bp.route('/discounts')
@login_required
def discounts():
    codes = DiscountCode.query.order_by(DiscountCode.created_at.desc()).all()
    return render_template('finance/discounts.html', codes=codes)


@finance_bp.route('/discounts/add', methods=['GET', 'POST'])
@login_required
def add_discount():
    if request.method == 'POST':
        dc = DiscountCode(
            code=request.form['code'],
            discount_type=request.form['discount_type'],
            discount_value=safe_float(request.form.get('discount_value')),
            max_uses=safe_int(request.form.get('max_uses')) or None,
            valid_from=get_jalali_date(request.form, 'valid_from') if request.form.get('valid_from') else None,
            valid_until=get_jalali_date(request.form, 'valid_until') if request.form.get('valid_until') else None,
            description=request.form.get('description'),
            is_active=True
        )
        db.session.add(dc)
        db.session.commit()
        flash('کد تخفیف ایجاد شد', 'success')
        return redirect(url_for('finance.discounts'))
    
    return render_template('finance/add_discount.html')


# ===== Salary =====
@finance_bp.route('/salary')
@login_required
def salary():
    payslips = Payslip.query.order_by(Payslip.created_at.desc()).limit(50).all()
    contracts = SalaryContract.query.filter_by(is_active=True).all()
    return render_template('finance/salary.html', payslips=payslips, contracts=contracts)


@finance_bp.route('/salary/create-payslip', methods=['GET', 'POST'])
@login_required
def create_payslip():
    if request.method == 'POST':
        last = Payslip.query.order_by(Payslip.id.desc()).first()
        ps_num = f'PS-1405-{(last.id + 1) if last else 1:05d}'
        
        base = safe_float(request.form.get('base_amount'))
        teaching = safe_float(request.form.get('teaching_amount'))
        commission = safe_float(request.form.get('commission_amount'))
        bonus = safe_float(request.form.get('bonus'))
        overtime = safe_float(request.form.get('overtime'))
        gross = base + teaching + commission + bonus + overtime
        
        deductions = safe_float(request.form.get('deductions'))
        insurance = safe_float(request.form.get('insurance'))
        tax = safe_float(request.form.get('tax'))
        penalty = safe_float(request.form.get('penalty'))
        total_deductions = deductions + insurance + tax + penalty
        
        net = gross - total_deductions
        
        payslip = Payslip(
            payslip_number=ps_num,
            person_type=request.form['person_type'],
            person_id=safe_int(request.form.get('person_id')),
            period=request.form['period'],
            base_amount=base,
            teaching_hours=safe_float(request.form.get('teaching_hours')),
            teaching_amount=teaching,
            sessions_count=safe_int(request.form.get('sessions_count')),
            session_amount=safe_float(request.form.get('session_amount')),
            commission_amount=commission,
            bonus=bonus,
            overtime=overtime,
            gross_amount=gross,
            deductions=deductions,
            insurance=insurance,
            tax=tax,
            penalty=penalty,
            total_deductions=total_deductions,
            net_amount=net,
            status='draft',
            created_by=current_user.id
        )
        db.session.add(payslip)
        db.session.commit()
        
        flash(f'فیش حقوقی {ps_num} صادر شد', 'success')
        return redirect(url_for('finance.salary'))
    
    from models.teacher import Teacher
    teachers = Teacher.query.filter_by(is_active=True).all()
    return render_template('finance/create_payslip.html', teachers=teachers)


# ===== Dashboard =====
@finance_bp.route('/dashboard')
@login_required
def financial_dashboard():
    today = datetime.utcnow()
    month_start = today.replace(day=1)
    
    month_income = db.session.query(db.func.sum(Payment.amount)).filter(
        Payment.payment_date >= month_start.date(),
        Payment.status == 'confirmed'
    ).scalar() or 0
    
    month_expenses = db.session.query(db.func.sum(Expense.amount)).filter(
        Expense.expense_date >= month_start.date(),
        Expense.status == 'confirmed'
    ).scalar() or 0
    
    cashbox = Cashbox.query.first()
    
    # Debtors
    debtors = Registration.query.filter(
        Registration.remaining_amount > 0,
        Registration.status == 'active'
    ).order_by(Registration.remaining_amount.desc()).limit(20).all()
    
    # Overdue installments
    overdue = Installment.query.filter(
        Installment.due_date < today.date(),
        Installment.status.in_(['pending', 'partial'])
    ).order_by(Installment.due_date).limit(20).all()
    
    return render_template('finance/dashboard.html',
                         month_income=month_income,
                         month_expenses=month_expenses,
                         cashbox=cashbox,
                         debtors=debtors,
                         overdue=overdue)
