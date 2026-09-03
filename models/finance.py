"""Finance, Payment, Cashbox, Bank, Check, Expense models"""
from datetime import datetime
from extensions import db


class Payment(db.Model):
    """پرداخت‌ها"""
    __tablename__ = 'payments'
    
    id = db.Column(db.Integer, primary_key=True)
    receipt_no = db.Column(db.String(20), unique=True, nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    registration_id = db.Column(db.Integer, db.ForeignKey('registrations.id'))
    installment_id = db.Column(db.Integer, db.ForeignKey('installments.id'))
    
    amount = db.Column(db.Float, nullable=False)
    payment_method = db.Column(db.String(20), nullable=False)  # cash, card, online, check, combined
    payment_date = db.Column(db.Date, default=datetime.utcnow)
    
    # Card payment
    card_number = db.Column(db.String(20))
    tracking_number = db.Column(db.String(50))
    bank_name = db.Column(db.String(50))
    
    # Online
    transaction_id = db.Column(db.String(100))
    
    # Check
    check_id = db.Column(db.Integer, db.ForeignKey('checks.id'))
    
    # Combined details
    cash_amount = db.Column(db.Float, default=0)
    card_amount = db.Column(db.Float, default=0)
    check_amount = db.Column(db.Float, default=0)
    
    cashbox_id = db.Column(db.Integer, db.ForeignKey('cashboxes.id'))
    description = db.Column(db.Text)
    status = db.Column(db.String(20), default='confirmed')  # confirmed, pending, cancelled
    
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    cancelled_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    cancelled_at = db.Column(db.DateTime)
    
    # Relationships
    installment = db.relationship('Installment', backref='payments')
    cashbox = db.relationship('Cashbox', backref='payments')
    branch = db.relationship('Branch', backref='payments')
    
    def __repr__(self):
        return f'<Payment {self.receipt_no}: {self.amount}>'


class DiscountCode(db.Model):
    """کدهای تخفیف"""
    __tablename__ = 'discount_codes'
    
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(30), unique=True, nullable=False)
    discount_type = db.Column(db.String(20), nullable=False)  # percentage, fixed
    discount_value = db.Column(db.Float, nullable=False)
    max_uses = db.Column(db.Integer)
    used_count = db.Column(db.Integer, default=0)
    valid_from = db.Column(db.Date)
    valid_until = db.Column(db.Date)
    course_id = db.Column(db.Integer, db.ForeignKey('courses.id'))
    is_active = db.Column(db.Boolean, default=True)
    description = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    course = db.relationship('Course', backref='discount_codes')


class Cashbox(db.Model):
    """صندوق"""
    __tablename__ = 'cashboxes'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    code = db.Column(db.String(20), unique=True)
    balance = db.Column(db.Float, default=0)
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'))
    is_active = db.Column(db.Boolean, default=True)
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    branch = db.relationship('Branch', backref='cashboxes')
    transactions = db.relationship('CashboxTransaction', backref='cashbox', lazy='dynamic')


def get_or_create_main_cashbox():
    """صندوق فعال پیش‌فرض؛ در نصب خالی ساخته می‌شود."""
    box = Cashbox.query.filter_by(is_active=True).first() or Cashbox.query.first()
    if box is None:
        box = Cashbox(name='صندوق اصلی', code='CASH-001', balance=0, is_active=True)
        db.session.add(box)
        db.session.flush()
    return box


class CashboxTransaction(db.Model):
    """تراکنش صندوق"""
    __tablename__ = 'cashbox_transactions'
    
    id = db.Column(db.Integer, primary_key=True)
    cashbox_id = db.Column(db.Integer, db.ForeignKey('cashboxes.id'), nullable=False)
    trans_type = db.Column(db.String(10), nullable=False)  # in, out
    amount = db.Column(db.Float, nullable=False)
    description = db.Column(db.Text)
    reference_type = db.Column(db.String(30))  # payment, expense, transfer, salary
    reference_id = db.Column(db.Integer)
    balance_after = db.Column(db.Float)
    transaction_date = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))


class BankAccount(db.Model):
    """حساب بانکی"""
    __tablename__ = 'bank_accounts'
    
    id = db.Column(db.Integer, primary_key=True)
    bank_name = db.Column(db.String(50), nullable=False)
    account_number = db.Column(db.String(30))
    card_number = db.Column(db.String(20))
    sheba = db.Column(db.String(30))
    branch_name = db.Column(db.String(100))  # نام شعبه بانک
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'))  # شعبه سازمانی
    balance = db.Column(db.Float, default=0)
    is_active = db.Column(db.Boolean, default=True)
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    branch = db.relationship('Branch', backref='bank_accounts')
    transactions = db.relationship('BankTransaction', backref='bank_account', lazy='dynamic')


class BankTransaction(db.Model):
    """تراکنش بانکی"""
    __tablename__ = 'bank_transactions'
    
    id = db.Column(db.Integer, primary_key=True)
    bank_account_id = db.Column(db.Integer, db.ForeignKey('bank_accounts.id'), nullable=False)
    trans_type = db.Column(db.String(10), nullable=False)  # deposit, withdrawal, transfer
    amount = db.Column(db.Float, nullable=False)
    description = db.Column(db.Text)
    reference_type = db.Column(db.String(30))
    reference_id = db.Column(db.Integer)
    balance_after = db.Column(db.Float)
    transaction_date = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))


class Check(db.Model):
    """چک"""
    __tablename__ = 'checks'
    
    id = db.Column(db.Integer, primary_key=True)
    check_number = db.Column(db.String(20), nullable=False)
    bank_name = db.Column(db.String(50), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    issue_date = db.Column(db.Date, nullable=False)
    due_date = db.Column(db.Date, nullable=False)
    issuer_name = db.Column(db.String(100))
    check_type = db.Column(db.String(10))  # received, issued
    status = db.Column(db.String(20), default='received')  # received, cashed, bounced, spent
    bounced_reason = db.Column(db.String(200))
    bounced_date = db.Column(db.Date)
    tracking_notes = db.Column(db.Text)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'))
    description = db.Column(db.Text)
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    
    student = db.relationship('Student', backref='checks')
    branch = db.relationship('Branch', backref='checks')


class Expense(db.Model):
    """هزینه‌ها"""
    __tablename__ = 'expenses'
    
    id = db.Column(db.Integer, primary_key=True)
    expense_number = db.Column(db.String(20), unique=True, nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('expense_categories.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    description = db.Column(db.Text)
    expense_date = db.Column(db.Date, default=datetime.utcnow)
    payment_method = db.Column(db.String(20))  # cash, card, check, transfer
    paid_to = db.Column(db.String(100))
    approved_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    cashbox_id = db.Column(db.Integer, db.ForeignKey('cashboxes.id'))
    bank_account_id = db.Column(db.Integer, db.ForeignKey('bank_accounts.id'))
    attachment = db.Column(db.String(300))
    status = db.Column(db.String(20), default='confirmed')  # confirmed, pending, cancelled
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    
    category = db.relationship('ExpenseCategory', backref='expenses')
    cashbox = db.relationship('Cashbox', backref='expenses')
    bank_account = db.relationship('BankAccount', backref='expenses')
    branch = db.relationship('Branch', backref='expenses')


class ExpenseCategory(db.Model):
    """دسته‌بندی هزینه‌ها"""
    __tablename__ = 'expense_categories'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    code = db.Column(db.String(20))
    parent_id = db.Column(db.Integer, db.ForeignKey('expense_categories.id'))
    description = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True)
    
    children = db.relationship('ExpenseCategory', backref=db.backref('parent', remote_side=[id]))


class SalaryContract(db.Model):
    """قرارداد حقوقی"""
    __tablename__ = 'salary_contracts'
    
    id = db.Column(db.Integer, primary_key=True)
    person_type = db.Column(db.String(20), nullable=False)  # teacher, employee, manager
    person_id = db.Column(db.Integer, nullable=False)
    contract_type = db.Column(db.String(20))  # fixed, hourly, percentage, session, combined
    base_salary = db.Column(db.Float, default=0)
    hourly_rate = db.Column(db.Float, default=0)
    session_rate = db.Column(db.Float, default=0)
    percentage_rate = db.Column(db.Float, default=0)
    commission_rate = db.Column(db.Float, default=0)
    insurance_amount = db.Column(db.Float, default=0)
    tax_amount = db.Column(db.Float, default=0)
    start_date = db.Column(db.Date)
    end_date = db.Column(db.Date)
    is_active = db.Column(db.Boolean, default=True)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Payslip(db.Model):
    """فیش حقوقی"""
    __tablename__ = 'payslips'
    
    id = db.Column(db.Integer, primary_key=True)
    payslip_number = db.Column(db.String(20), unique=True, nullable=False)
    person_type = db.Column(db.String(20), nullable=False)
    person_id = db.Column(db.Integer, nullable=False)
    period = db.Column(db.String(10))  # e.g., 1405/01
    
    base_amount = db.Column(db.Float, default=0)
    teaching_hours = db.Column(db.Float, default=0)
    teaching_amount = db.Column(db.Float, default=0)
    sessions_count = db.Column(db.Integer, default=0)
    session_amount = db.Column(db.Float, default=0)
    commission_amount = db.Column(db.Float, default=0)
    bonus = db.Column(db.Float, default=0)
    overtime = db.Column(db.Float, default=0)
    gross_amount = db.Column(db.Float, default=0)
    
    deductions = db.Column(db.Float, default=0)  # مساعده
    insurance = db.Column(db.Float, default=0)
    tax = db.Column(db.Float, default=0)
    penalty = db.Column(db.Float, default=0)
    total_deductions = db.Column(db.Float, default=0)
    
    net_amount = db.Column(db.Float, default=0)
    status = db.Column(db.String(20), default='draft')  # draft, approved, paid
    paid_date = db.Column(db.Date)
    notes = db.Column(db.Text)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    approved_by = db.Column(db.Integer, db.ForeignKey('users.id'))
