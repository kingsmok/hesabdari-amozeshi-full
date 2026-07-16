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
    closed_at = db.Column(db.DateTime)
    closed_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


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
    approved_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    cancelled_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    cancelled_at = db.Column(db.DateTime)
    cancel_reason = db.Column(db.Text)
    
    # Relationships
    items = db.relationship('JournalItem', backref='entry', lazy='dynamic', cascade='all, delete-orphan')
    fiscal_period = db.relationship('FiscalPeriod', backref='entries')
    branch = db.relationship('Branch', backref='journal_entries')
    
    def calculate_totals(self):
        items = self.items.all()
        self.total_debit = sum(item.debit for item in items)
        self.total_credit = sum(item.credit for item in items)
        return self.total_debit == self.total_credit
    
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
