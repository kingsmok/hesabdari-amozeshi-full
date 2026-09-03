"""Persistent models for the unified reporting centre.

The core reports are calculated from the operational tables.  These models only
store user preferences, automation, snapshots and reconciliation/budget inputs;
they never duplicate the accounting source of truth.
"""
from __future__ import annotations

from extensions import db
from utils.local_time import local_now_naive


class ReportPreset(db.Model):
    """A named report filter/column layout owned by one user."""

    __tablename__ = 'report_presets'
    __table_args__ = (
        db.UniqueConstraint('user_id', 'report_key', 'name', name='uq_report_preset_name'),
        db.Index('ix_report_preset_user_key', 'user_id', 'report_key'),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    report_key = db.Column(db.String(80), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    filters_json = db.Column(db.Text, default='{}', nullable=False)
    columns_json = db.Column(db.Text, default='[]', nullable=False)
    is_favorite = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=local_now_naive, nullable=False)
    updated_at = db.Column(
        db.DateTime, default=local_now_naive, onupdate=local_now_naive, nullable=False
    )

    user = db.relationship('User', backref=db.backref('report_presets', lazy='dynamic'))


class ReportFavorite(db.Model):
    """A report pinned to the reporting dashboard."""

    __tablename__ = 'report_favorites'
    __table_args__ = (
        db.UniqueConstraint('user_id', 'report_key', name='uq_report_favorite'),
        db.Index('ix_report_favorite_user', 'user_id'),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    report_key = db.Column(db.String(80), nullable=False)
    created_at = db.Column(db.DateTime, default=local_now_naive, nullable=False)

    user = db.relationship('User', backref=db.backref('report_favorites', lazy='dynamic'))


class ReportSchedule(db.Model):
    """Recurring generation/delivery definition for a report."""

    __tablename__ = 'report_schedules'
    __table_args__ = (
        db.Index('ix_report_schedule_due', 'is_active', 'next_run_at'),
        db.Index('ix_report_schedule_user', 'user_id'),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    report_key = db.Column(db.String(80), nullable=False)
    filters_json = db.Column(db.Text, default='{}', nullable=False)
    export_format = db.Column(db.String(10), default='xlsx', nullable=False)
    frequency = db.Column(db.String(20), default='monthly', nullable=False)
    schedule_day = db.Column(db.Integer)  # روز ماه شمسی برای جلوگیری از جابه‌جایی اجرا
    delivery_method = db.Column(db.String(20), default='internal', nullable=False)
    recipient = db.Column(db.String(250))
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    next_run_at = db.Column(db.DateTime, nullable=False)
    last_run_at = db.Column(db.DateTime)
    last_status = db.Column(db.String(20), default='pending')
    last_error = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=local_now_naive, nullable=False)
    updated_at = db.Column(
        db.DateTime, default=local_now_naive, onupdate=local_now_naive, nullable=False
    )

    user = db.relationship('User', backref=db.backref('report_schedules', lazy='dynamic'))


class ReportSnapshot(db.Model):
    """Immutable KPI snapshot, useful for later period comparisons."""

    __tablename__ = 'report_snapshots'
    __table_args__ = (
        db.Index('ix_report_snapshot_user_key', 'user_id', 'report_key'),
        db.Index('ix_report_snapshot_created', 'created_at'),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    report_key = db.Column(db.String(80), nullable=False)
    title = db.Column(db.String(180), nullable=False)
    filters_json = db.Column(db.Text, default='{}', nullable=False)
    metrics_json = db.Column(db.Text, default='[]', nullable=False)
    row_count = db.Column(db.Integer, default=0, nullable=False)
    created_at = db.Column(db.DateTime, default=local_now_naive, nullable=False)

    user = db.relationship('User', backref=db.backref('report_snapshots', lazy='dynamic'))


class ReportExportLog(db.Model):
    """Audit trail for manual and scheduled report exports."""

    __tablename__ = 'report_export_logs'
    __table_args__ = (
        db.Index('ix_report_export_user_created', 'user_id', 'created_at'),
        db.Index('ix_report_export_key', 'report_key'),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    report_key = db.Column(db.String(80), nullable=False)
    export_format = db.Column(db.String(10), nullable=False)
    row_count = db.Column(db.Integer, default=0, nullable=False)
    status = db.Column(db.String(20), default='completed', nullable=False)
    file_name = db.Column(db.String(250))
    error_message = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=local_now_naive, nullable=False)

    user = db.relationship('User', backref=db.backref('report_exports', lazy='dynamic'))


class ReportBudget(db.Model):
    """Budget line used by the budget-vs-actual report."""

    __tablename__ = 'report_budgets'
    __table_args__ = (
        db.Index('ix_report_budget_year_branch', 'fiscal_year', 'branch_id'),
        db.Index('ix_report_budget_period', 'fiscal_year', 'period', 'period_no'),
    )

    id = db.Column(db.Integer, primary_key=True)
    fiscal_year = db.Column(db.String(10), nullable=False)
    period = db.Column(db.String(10), default='year', nullable=False)
    period_no = db.Column(db.Integer)  # ماه ۱..۱۲ یا فصل ۱..۴
    title = db.Column(db.String(160), nullable=False)
    budget_type = db.Column(db.String(20), default='expense', nullable=False)
    amount = db.Column(db.Numeric(18, 2), default=0, nullable=False)
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'))
    account_id = db.Column(db.Integer, db.ForeignKey('accounts.id'))
    expense_category_id = db.Column(db.Integer, db.ForeignKey('expense_categories.id'))
    notes = db.Column(db.Text)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=local_now_naive, nullable=False)
    updated_at = db.Column(
        db.DateTime, default=local_now_naive, onupdate=local_now_naive, nullable=False
    )

    branch = db.relationship('Branch', backref='report_budgets')
    account = db.relationship('Account', backref='report_budgets')
    expense_category = db.relationship('ExpenseCategory', backref='report_budgets')
    creator = db.relationship('User', foreign_keys=[created_by])


class AccountReconciliation(db.Model):
    """A cashbox/bank reconciliation statement and its resolution status."""

    __tablename__ = 'account_reconciliations'
    __table_args__ = (
        db.Index('ix_reconciliation_date_kind', 'reconciliation_date', 'account_kind'),
    )

    id = db.Column(db.Integer, primary_key=True)
    account_kind = db.Column(db.String(20), nullable=False)  # cashbox / bank
    cashbox_id = db.Column(db.Integer, db.ForeignKey('cashboxes.id'))
    bank_account_id = db.Column(db.Integer, db.ForeignKey('bank_accounts.id'))
    reconciliation_date = db.Column(db.Date, nullable=False)
    system_balance = db.Column(db.Numeric(18, 2), default=0, nullable=False)
    statement_balance = db.Column(db.Numeric(18, 2), default=0, nullable=False)
    difference = db.Column(db.Numeric(18, 2), default=0, nullable=False)
    status = db.Column(db.String(20), default='open', nullable=False)
    notes = db.Column(db.Text)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    resolved_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    resolved_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=local_now_naive, nullable=False)

    cashbox = db.relationship('Cashbox', backref='reconciliations')
    bank_account = db.relationship('BankAccount', backref='reconciliations')
    creator = db.relationship('User', foreign_keys=[created_by])
    resolver = db.relationship('User', foreign_keys=[resolved_by])
