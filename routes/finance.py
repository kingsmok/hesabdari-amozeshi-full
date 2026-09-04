"""Finance routes - Payments, Cashbox, Bank, Checks, Expenses, Salary"""
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from license_client import license_required, licensed_section
from extensions import db
from utils.form_helpers import get_jalali_date, safe_float, safe_int
from models.finance import (
    Payment, Cashbox, CashboxTransaction, BankAccount, BankTransaction,
    Check, Expense, ExpenseCategory, DiscountCode, SalaryContract, Payslip,
    get_or_create_main_cashbox,
)
from models.registration import Registration, Installment
from models.student import Student
from utils.document_numbers import next_document_number
from utils.payments import (apply_payment_to_targets, build_receipt_no, cash_portion,
                            settle_cashbox)
from datetime import datetime


def _log_payment_action(action, payment, description):
    """ردپای تغییرات مالی — نقطهٔ مشترک در utils/activity_log (DRY)."""
    from utils.activity_log import log_activity
    log_activity(action, description, module='finance', entity_type='payment',
                 entity_id=payment.id if payment else None)

finance_bp = Blueprint('finance', __name__)


# ===== Payments =====
@finance_bp.route('/payments')
@license_required
@login_required
@licensed_section('finance')
def payments():
    page = request.args.get('page', 1, type=int)
    method = request.args.get('method', '')
    search = request.args.get('search', '')
    status = request.args.get('status', '')
    
    query = Payment.query
    if method:
        query = query.filter_by(payment_method=method)
    if status:
        query = query.filter_by(status=status)
    if search:
        query = query.join(Student).filter(
            db.or_(Student.first_name.contains(search), Payment.receipt_no.contains(search))
        )
    
    payments = query.order_by(Payment.created_at.desc()).paginate(page=page, per_page=20)
    return render_template('finance/payments.html', payments=payments, method=method,
                           search=search, status=status)


@finance_bp.route('/payments/add', methods=['GET', 'POST'])
@login_required
def add_payment():
    if request.method == 'POST':
        student_id = request.form.get('student_id', type=int)
        registration_id = request.form.get('registration_id', type=int)
        installment_id = request.form.get('installment_id', type=int)
        amount = safe_float(request.form.get('amount'))
        student = Student.query.get(student_id) if student_id else None
        registration = Registration.query.get(registration_id) if registration_id else None
        installment = Installment.query.get(installment_id) if installment_id else None
        if registration is None and installment is not None:
            # قسط حتماً به یک ثبت‌نام وابسته است؛ بدون این خط، مانده آن ثبت‌نام
            # به‌روز نمی‌شد و هنرجو بدهکار می‌ماند
            registration = installment.registration

        if not student or amount <= 0:
            flash('هنرجو یا مبلغ پرداخت معتبر نیست', 'danger')
            return redirect(url_for('finance.add_payment'))
        if registration and registration.student_id != student.id:
            flash('ثبت‌نام انتخاب‌شده متعلق به این هنرجو نیست', 'danger')
            return redirect(url_for('finance.add_payment'))
        if installment and (not registration or installment.registration_id != registration.id):
            flash('قسط انتخاب‌شده با ثبت‌نام مطابقت ندارد', 'danger')
            return redirect(url_for('finance.add_payment'))
        if registration and amount > max(0, registration.remaining_amount or 0):
            flash('مبلغ پرداخت بیشتر از مانده ثبت‌نام است', 'danger')
            return redirect(url_for('finance.add_payment'))
        if installment and amount > max(0, installment.remaining):
            flash('مبلغ پرداخت بیشتر از مانده قسط است', 'danger')
            return redirect(url_for('finance.add_payment'))

        # ── اجزای پرداخت ترکیبی ────────────────────────────────────────────
        # ستون‌های cash_amount/card_amount/check_amount در مدل بود ولی هیچ‌وقت
        # پر نمی‌شد؛ نتیجه: سهم نقدی به صندوق اضافه نمی‌شد، رسید بدون ریز بود
        # و ابطال/مرجوعی نمی‌دانست چقدر نقد بیرون بیاید.
        # اعتبارسنجی مرکزی روش پرداخت (utils/validators)
        from utils.validators import normalize_payment_method
        method = normalize_payment_method(request.form.get('payment_method'), 'cash')
        cash_part = card_part = check_part = 0.0
        if method == 'combined':
            cash_part = safe_float(request.form.get('cash_amount'))
            card_part = safe_float(request.form.get('card_amount'))
            check_part = safe_float(request.form.get('check_amount'))
            if min(cash_part, card_part, check_part) < 0:
                flash('مبلغ بخش‌های پرداخت نمی‌تواند منفی باشد', 'danger')
                return redirect(url_for('finance.add_payment'))
            parts_total = cash_part + card_part + check_part
            if abs(parts_total - amount) > 1:
                flash(f'جمع بخش‌ها ({parts_total:,.0f}) با کل مبلغ ({amount:,.0f}) نمی‌خواند؛ '
                      'اختلاف نباید بیشتر از ۱ تومان باشد', 'danger')
                return redirect(url_for('finance.add_payment'))

        receipt_num = build_receipt_no()

        payment = Payment(
            receipt_no=receipt_num,
            student_id=student.id,
            registration_id=registration.id if registration else None,
            # قسط باید از ابتدا وصل باشد: اگر بعداً چسبانده شود،
            # apply_payment_to_targets آن را نمی‌بیند و وضعیت قسط دست‌نخورده
            # می‌ماند (بدهکاری هنرجو در صفحه اقساط باقی می‌ماند)
            installment_id=installment.id if installment else None,
            amount=amount,
            payment_method=method,
            payment_date=get_jalali_date(request.form, 'payment_date') if request.form.get('payment_date') else datetime.utcnow().date(),
            card_number=request.form.get('card_number'),
            tracking_number=request.form.get('tracking_number'),
            bank_name=request.form.get('bank_name'),
            transaction_id=request.form.get('transaction_id'),
            cash_amount=cash_part,
            card_amount=card_part,
            check_amount=check_part,
            description=request.form.get('description'),
            branch_id=request.form.get('branch_id', 1),
            created_by=current_user.id
        )
        
        db.session.add(payment)
        db.session.flush()          # تا payment.id برای تراکنش صندوق آماده شود

        # ثبت‌نام/قسط و صندوق از یک راه مشترک اعمال می‌شود. قبلاً این‌جا دستی بود:
        # سهم نقدیِ پرداخت «ترکیبی» به صندوق اضافه نمی‌شد و cashbox_id ثبت
        # نمی‌شد، پس بعداً معلوم نبود پول کدام صندوق رفته است.
        apply_payment_to_targets(payment, sign=1, date_hint=payment.payment_date)
        ok, message = settle_cashbox(
            payment, cash_portion(payment), f'دریافت شهریه {receipt_num}',
            user_id=current_user.id, direction='in')
        if not ok:
            db.session.rollback()
            flash(message, 'danger')
            return redirect(url_for('finance.add_payment'))

        db.session.commit()
        _log_payment_action('payment-create', payment, f'ثبت پرداخت {receipt_num}')
        
        flash(f'پرداخت {receipt_num} ثبت شد', 'success')
        return redirect(url_for('finance.view_payment', id=payment.id))
    
    students = Student.query.filter_by(status='active').all()
    # این فرم هیچ‌وقت فیلد ثبت‌نام/قسط نداشت ⇒ پرداخت ثبت می‌شد ولی مانده
    # هنرجو کم نمی‌شد و در صفحه اقساط هم بدهکاری سر جایش می‌ماند.
    open_registrations = (Registration.query
                          .filter(Registration.status == 'active',
                                  db.func.coalesce(Registration.remaining_amount, 0) > 0)
                          .order_by(Registration.remaining_amount.desc()).limit(400).all())
    open_installments = (Installment.query.join(Registration, Installment.registration_id == Registration.id)
                         .filter(Registration.status == 'active',
                                 Installment.status.in_(('pending', 'partial')),
                                 db.func.coalesce(Installment.paid_amount, 0) < Installment.amount
                                 + db.func.coalesce(Installment.late_fee, 0))
                         .order_by(Installment.due_date.asc()).limit(400).all())
    return render_template('finance/add_payment.html', students=students,
                           open_registrations=open_registrations, open_installments=open_installments)


@finance_bp.route('/payments/<int:id>')
@login_required
def view_payment(id):
    payment = Payment.query.get_or_404(id)
    creator_name = None
    if payment.created_by:
        from models.user import User
        author = db.session.get(User, payment.created_by)
        creator_name = author.full_name if author else None
    return render_template('finance/view_payment.html', payment=payment,
                           creator_name=creator_name,
                           cash_in_part=cash_portion(payment))


@finance_bp.route('/payments/<int:id>/cancel', methods=['POST'])
@license_required
@login_required
@licensed_section('finance')
def cancel_payment(id):
    """ابطال پرداخت با بازمحاسبه مانده (و در صورت درخواست، مرجوعی صندوق).

    تا پیش از این هیچ مسیر ابطال/مرجوعی برای `Payment` نبود، هرچند مدل
    `status='cancelled'` + `cancelled_by/cancelled_at` را داشت؛ یعنی تنها راه
    اصلاح یک اشتباه، ویرایش دستی دیتابیس بود و مانده هنرجو هم بازمحاسبه
    نمی‌شد. ابطال «حذف» نیست: ردیف می‌ماند، دلیل و کی/کِی ثبت می‌شود.
    """
    payment = Payment.query.get_or_404(id)
    if payment.status == 'cancelled':
        flash('این پرداخت پیش‌تر باطل شده است', 'warning')
        return redirect(url_for('finance.view_payment', id=payment.id))

    reason = (request.form.get('reason') or '').strip()
    if len(reason) < 3:
        flash('برای ابطال، دلیل را بنویسید (در حسابداری، حذف بی‌دلیل نداریم)', 'danger')
        return redirect(url_for('finance.view_payment', id=payment.id))

    want_refund = request.form.get('refund') == 'on'
    refund_amount = cash_portion(payment) if want_refund else 0.0

    # قفل اتمیک وضعیت: دو درخواست هم‌زمان/کلیک دوباره فقط یک‌بار ابطال می‌کند
    from utils.money_guard import atomic_transition
    transitioned = atomic_transition(
        Payment, payment.id, ('confirmed', 'pending'), 'cancelled',
        {'cancelled_by': current_user.id,
         'cancelled_at': datetime.utcnow(),
         'cancel_reason': reason,
         'refunded_amount': refund_amount})
    if not transitioned:
        flash('این پرداخت هم‌زمان توسط درخواست دیگری باطل شده است؛ عملیات تکرار نشد.',
              'warning')
        return redirect(url_for('finance.view_payment', id=payment.id))

    # اول مرجوعی صندوق؛ اگر موجودی کافی نبود کل عملیات ول می‌شود
    ok, message = settle_cashbox(
        payment, refund_amount, f'مرجوعی ابطال پرداخت {payment.receipt_no}',
        user_id=current_user.id, direction='out')
    if not ok:
        db.session.rollback()
        flash(message + ' — می‌توانید ابطال را بدون مرجوعی نقدی ثبت کنید', 'danger')
        return redirect(url_for('finance.view_payment', id=payment.id))

    apply_payment_to_targets(payment, sign=-1)
    _log_payment_action('payment-cancel', payment,
                        f'ابطال {payment.receipt_no}: {reason}')
    db.session.commit()

    flash(f'پرداخت {payment.receipt_no} باطل شد'
          + (f' و {refund_amount:,.0f} تومان به صندوق برگشت' if refund_amount else ''),
          'success')
    return redirect(url_for('finance.view_payment', id=payment.id))


@finance_bp.route('/payments/<int:id>/restore', methods=['POST'])
@license_required
@login_required
@licensed_section('finance')
def restore_payment(id):
    """بازگردانی پرداخت باطل‌شده (فقط مدیر/حسابدار؛ دقیقاً برعکس ابطال).

    اگر هنگام ابطال پولی به هنرجو برگشت داده شده بود، همان مقدار دوباره به
    صندوق برمی‌گردد — نه کل مبلغ، چون ممکن است فقط بخش نقد مرجوع شده باشد.
    """
    payment = Payment.query.get_or_404(id)
    if payment.status != 'cancelled':
        flash('فقط پرداخت باطل‌شده قابل بازگردانی است', 'warning')
        return redirect(url_for('finance.view_payment', id=payment.id))

    # مبلغ مرجوع‌شده را قبل از transition بخوان؛ transition آن را صفر می‌کند
    repay = float(payment.refunded_amount or 0)

    # قفل اتمیک: بازگردانی دوباره (کلیک دوباره) فقط یک‌بار اعمال می‌شود
    from utils.money_guard import atomic_transition
    transitioned = atomic_transition(
        Payment, payment.id, ('cancelled',), 'confirmed',
        {'cancelled_by': None, 'cancelled_at': None,
         'cancel_reason': None, 'refunded_amount': 0})
    if not transitioned:
        flash('این پرداخت هم‌زمان توسط درخواست دیگری بازگردانی شده است؛ عملیات تکرار نشد.',
              'warning')
        return redirect(url_for('finance.view_payment', id=payment.id))

    if repay > 0:
        ok, message = settle_cashbox(
            payment, repay, f'بازگشت مرجوعی پرداخت {payment.receipt_no}',
            user_id=current_user.id, direction='in')
        if not ok:
            db.session.rollback()
            flash(message, 'danger')
            return redirect(url_for('finance.view_payment', id=payment.id))

    apply_payment_to_targets(payment, sign=+1, date_hint=payment.payment_date)
    _log_payment_action('payment-restore', payment,
                        f'بازگردانی پرداخت {payment.receipt_no}')
    db.session.commit()
    flash(f'پرداخت {payment.receipt_no} به وضعیت تأییدشده برگشت', 'success')
    return redirect(url_for('finance.view_payment', id=payment.id))


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
    trans_type = request.form.get('trans_type')
    amount = safe_float(request.form.get('amount'))
    if trans_type not in ('in', 'out') or amount <= 0:
        flash('نوع تراکنش یا مبلغ معتبر نیست', 'danger')
        return redirect(url_for('finance.cashbox'))
    
    if trans_type == 'in':
        cashbox.balance = (cashbox.balance or 0) + amount
    else:
        if amount > (cashbox.balance or 0):
            flash('موجودی صندوق برای این برداشت کافی نیست', 'danger')
            return redirect(url_for('finance.cashbox'))
        cashbox.balance = (cashbox.balance or 0) - amount
    
    # نوع مرجع فقط از مقادیر شناخته‌شده — اعتبارسنجی مرکزی (DRY)
    from utils.validators import normalize_ref_type
    reference_type = normalize_ref_type(request.form.get('reference_type'), 'manual')

    tx = CashboxTransaction(
        cashbox_id=id,
        trans_type=trans_type,
        amount=amount,
        description=request.form.get('description'),
        reference_type=reference_type,
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
    trans_type = request.form.get('trans_type')
    amount = safe_float(request.form.get('amount'))
    if trans_type not in ('deposit', 'withdrawal') or amount <= 0:
        flash('نوع تراکنش یا مبلغ معتبر نیست', 'danger')
        return redirect(url_for('finance.bank'))
    
    if trans_type == 'deposit':
        account.balance = (account.balance or 0) + amount
    else:
        if amount > (account.balance or 0):
            flash('موجودی حساب برای این برداشت کافی نیست', 'danger')
            return redirect(url_for('finance.bank'))
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
    new_status = request.form.get('status')
    if new_status not in ('received', 'cashed', 'bounced', 'spent', 'cancelled'):
        flash('وضعیت چک معتبر نیست', 'danger')
        return redirect(url_for('finance.checks'))
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


@finance_bp.route('/expenses/pdf')
@login_required
def expenses_pdf():
    """خروجی چاپی هزینه‌ها فقط با فرمت PDF."""
    from utils.jalali import gregorian_to_jalali
    from utils.pdf_helpers import build_table_pdf

    expense_rows = Expense.query.order_by(Expense.expense_date.desc(), Expense.id.desc()).all()
    rows = [
        (
            expense.expense_number,
            expense.category.name if expense.category else '-',
            f'{expense.amount:,.0f}',
            expense.description or '-',
            gregorian_to_jalali(expense.expense_date),
            expense.paid_to or '-'
        )
        for expense in expense_rows
    ]
    return build_table_pdf(
        'گزارش هزینه‌های آموزشگاه',
        ['شماره', 'دسته‌بندی', 'مبلغ (تومان)', 'توضیحات', 'تاریخ', 'پرداخت‌شونده'],
        rows,
        'expenses-report.pdf',
        subtitle=f'تعداد رکورد: {len(rows)}',
        landscape_mode=True,
        download=request.args.get('download') == '1'
    )


@finance_bp.route('/expenses/add', methods=['GET', 'POST'])
@login_required
def add_expense():
    categories = ExpenseCategory.query.filter_by(is_active=True).order_by(ExpenseCategory.name).all()

    if request.method == 'POST':
        category_id = request.form.get('category_id', type=int)
        category = ExpenseCategory.query.filter_by(id=category_id, is_active=True).first() if category_id else None
        amount = safe_float(request.form.get('amount'))

        if not category:
            flash('لطفاً یک دسته‌بندی هزینه فعال انتخاب کنید', 'danger')
            return render_template('finance/add_expense.html', categories=categories), 400
        if amount <= 0:
            flash('مبلغ هزینه باید بیشتر از صفر باشد', 'danger')
            return render_template('finance/add_expense.html', categories=categories), 400

        exp_num = next_document_number('expense')
        
        expense = Expense(
            expense_number=exp_num,
            category_id=category.id,
            amount=amount,
            description=(request.form.get('description') or '').strip() or None,
            expense_date=get_jalali_date(request.form, 'expense_date') if request.form.get('expense_date') else datetime.utcnow().date(),
            payment_method=request.form.get('payment_method'),
            paid_to=(request.form.get('paid_to') or '').strip() or None,
            approved_by=request.form.get('approved_by') or None,
            branch_id=request.form.get('branch_id', 1),
            created_by=current_user.id
        )
        db.session.add(expense)
        db.session.commit()
        flash(f'هزینه {exp_num} در دسته‌بندی «{category.name}» ثبت شد', 'success')
        return redirect(url_for('finance.expenses'))
    
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
        # این فرم قدیمی (نسخه موازی `/payroll/calculate`) دو ایراد داشت:
        # ۱) شماره فیش از MAX(id)+1 ساخته می‌شد ⇒ تصادم هم‌زمان/۵۰۰
        # ۲) برای یک نفر و یک دوره، فیش دوم هم صادر می‌شد ⇒ پرداخت تکراری
        from utils.document_numbers import next_document_number
        from utils.jalali import current_jalali_period, normalize_jalali_period
        period = normalize_jalali_period(request.form.get('period')) or current_jalali_period()
        person_type = request.form.get('person_type', 'teacher')
        person_id = safe_int(request.form.get('person_id'))
        if not person_id:
            flash('شخص (مدرس یا کارمند) را انتخاب کنید', 'danger')
            return redirect(url_for('finance.create_payslip'))
        clash = Payslip.query.filter_by(person_type=person_type, person_id=person_id,
                                        period=period).first()
        if clash is not None:
            flash(f'برای این نفر در دوره {period} فیش {clash.payslip_number} '
                  f'(وضعیت {clash.status}) ثبت شده است؛ از بخش حقوق و دستمزد همان فیش را '
                  'ویرایش یا لغو کنید', 'danger')
            return redirect(url_for('payroll.payslips', period=period))

        ps_num = next_document_number('payslip')
        
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
            person_type=person_type,
            person_id=person_id,
            period=period,
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
    # پنجره شمسی (میلادی ⇒ ۲۰ روز اول ماه، آمار ماه قبل را می‌شمارد)
    from utils.jalali import jalali_month_bounds
    month_start, month_end = jalali_month_bounds()
    
    month_income = db.session.query(db.func.sum(Payment.amount)).filter(
        Payment.payment_date >= month_start, Payment.payment_date <= month_end,
        Payment.status == 'confirmed'
    ).scalar() or 0
    
    month_expenses = db.session.query(db.func.sum(Expense.amount)).filter(
        Expense.expense_date >= month_start, Expense.expense_date <= month_end,
        Expense.status == 'confirmed'
    ).scalar() or 0
    
    cashbox = get_or_create_main_cashbox()
    
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
