"""Accounting models - Double entry bookkeeping"""
from datetime import datetime
from extensions import db


class AccountGroup(db.Model):
    """گروه حساب"""
    __tablename__ = 'account_groups'
    
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(10), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    account_type = db.Column(db.String(20), nullable=False)  # asset, liability, equity, revenue, expense
    description = db.Column(db.Text)
    
    accounts = db.relationship('Account', backref='group', lazy='dynamic')


class Account(db.Model):
    """حساب کل"""
    __tablename__ = 'accounts'
    
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), unique=True, nullable=False)
    name = db.Column(db.String(150), nullable=False)
    group_id = db.Column(db.Integer, db.ForeignKey('account_groups.id'), nullable=False)
    account_type = db.Column(db.String(20))  # asset, liability, equity, revenue, expense
    nature = db.Column(db.String(10))  # debit, credit
    balance = db.Column(db.Float, default=0)
    description = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True)
    
    sub_accounts = db.relationship('SubAccount', backref='account', lazy='dynamic')
    journal_items = db.relationship('JournalItem', backref='account', lazy='dynamic')


class SubAccount(db.Model):
    """حساب معین"""
    __tablename__ = 'sub_accounts'
    
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(30), unique=True, nullable=False)
    name = db.Column(db.String(150), nullable=False)
    account_id = db.Column(db.Integer, db.ForeignKey('accounts.id'), nullable=False)
    balance = db.Column(db.Float, default=0)
    description = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True)
    
    details = db.relationship('DetailAccount', backref='sub_account', lazy='dynamic')


class DetailAccount(db.Model):
    """حساب تفصیلی"""
    __tablename__ = 'detail_accounts'
    
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(40), unique=True, nullable=False)
    name = db.Column(db.String(150), nullable=False)
    sub_account_id = db.Column(db.Integer, db.ForeignKey('sub_accounts.id'), nullable=False)
    balance = db.Column(db.Float, default=0)
    description = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True)


class FiscalPeriod(db.Model):
    """دوره مالی"""
    __tablename__ = 'fiscal_periods'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    is_closed = db.Column(db.Boolean, default=False)
    closed_by_user = db.Column(db.Boolean, default=False)   # بسته شدن با تأیید مدیر کل
    closed_at = db.Column(db.DateTime)
    closed_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def contains(self, day):
        return day is not None and self.start_date <= day <= self.end_date

    @classmethod
    def for_date(cls, day):
        """دوره مالی شامل یک تاریخ (برای قفل شدن اسناد دوره بسته)."""
        if day is None:
            return None
        return cls.query.filter(cls.start_date <= day, cls.end_date >= day).first()

    @classmethod
    def is_date_locked(cls, day):
        period = cls.for_date(day)
        return bool(period and period.is_closed)


class JournalEntry(db.Model):
    """سند حسابداری"""
    __tablename__ = 'journal_entries'
    
    id = db.Column(db.Integer, primary_key=True)
    entry_number = db.Column(db.String(20), unique=True, nullable=False, index=True)
    entry_date = db.Column(db.Date, nullable=False, default=datetime.utcnow)
    entry_type = db.Column(db.String(20))  # income, expense, adjustment, transfer
    description = db.Column(db.Text)
    total_debit = db.Column(db.Float, default=0)
    total_credit = db.Column(db.Float, default=0)
    
    fiscal_period_id = db.Column(db.Integer, db.ForeignKey('fiscal_periods.id'))
    status = db.Column(db.String(20), default='draft')  # draft, confirmed, approved, cancelled
    is_adjusted = db.Column(db.Boolean, default=False)
    adjustment_reason = db.Column(db.Text)
    
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    confirmed_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    confirmed_at = db.Column(db.DateTime)
    approved_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    approved_at = db.Column(db.DateTime)
    cancelled_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    cancelled_at = db.Column(db.DateTime)
    cancel_reason = db.Column(db.Text)
    
    # Relationships
    items = db.relationship('JournalItem', backref='entry', lazy='dynamic', cascade='all, delete-orphan')
    fiscal_period = db.relationship('FiscalPeriod', backref='entries')
    branch = db.relationship('Branch', backref='journal_entries')

    #: حساب‌های کاربری سند — صراحتاً با foreign_keys تا SQLAlchemy بین
    #: چهار کلید خارجیِ users.selectable سردرگم نشود
    created_by_user = db.relationship('User', foreign_keys=[created_by])
    confirmed_by_user = db.relationship('User', foreign_keys=[confirmed_by])
    approved_by_user = db.relationship('User', foreign_keys=[approved_by])
    cancelled_by_user = db.relationship('User', foreign_keys=[cancelled_by])
    
    def calculate_totals(self):
        items = self.items.all()
        self.total_debit = sum(item.debit or 0 for item in items)
        self.total_credit = sum(item.credit or 0 for item in items)
        return self.is_balanced()

    def is_balanced(self, tolerance=1.0):
        """تراز بودن سند — تلورانس یک تومانی برای گرد کردن مبالغ.

        سند ترازنبود نباید تأیید یا تصویب شود؛ در حالت قبلی هر سندی
        بدون بررسی تأیید می‌شد و تراز آزمایشی بی‌معنا می‌گشت.
        """
        return abs((self.total_debit or 0) - (self.total_credit or 0)) <= tolerance

    @property
    def is_editable(self):
        """فقط سند پیش‌نویسِ دوره باز قابل ویرایش است."""
        return self.status in ('draft',) and not FiscalPeriod.is_date_locked(self.entry_date)
    
    def __repr__(self):
        return f'<JournalEntry {self.entry_number}>'


class JournalItem(db.Model):
    """آیتم سند حسابداری"""
    __tablename__ = 'journal_items'
    
    id = db.Column(db.Integer, primary_key=True)
    entry_id = db.Column(db.Integer, db.ForeignKey('journal_entries.id'), nullable=False)
    account_id = db.Column(db.Integer, db.ForeignKey('accounts.id'), nullable=False)
    sub_account_id = db.Column(db.Integer, db.ForeignKey('sub_accounts.id'))
    detail_account_id = db.Column(db.Integer, db.ForeignKey('detail_accounts.id'))
    
    debit = db.Column(db.Float, default=0)
    credit = db.Column(db.Float, default=0)
    description = db.Column(db.Text)
    row_number = db.Column(db.Integer)
    
    sub_account = db.relationship('SubAccount', backref='journal_items')
    detail_account = db.relationship('DetailAccount', backref='journal_items')
