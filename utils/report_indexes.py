"""Idempotent database indexes used by reports and global search."""
from __future__ import annotations

from sqlalchemy import Index, inspect, text

from extensions import db


INDEX_SPECS = (
    ('payments', 'ix_reports_payments_date_status_branch', ('payment_date', 'status', 'branch_id')),
    ('payments', 'ix_search_payments_receipt_tracking', ('receipt_no', 'tracking_number')),
    ('expenses', 'ix_reports_expenses_date_status_branch', ('expense_date', 'status', 'branch_id')),
    ('checks', 'ix_reports_checks_due_status_branch', ('due_date', 'status', 'branch_id')),
    ('checks', 'ix_search_checks_number', ('check_number',)),
    ('registrations', 'ix_reports_reg_date_status_branch', ('registration_date', 'status', 'branch_id')),
    ('registrations', 'ix_reports_reg_course_class', ('course_id', 'class_id', 'teacher_id')),
    ('installments', 'ix_reports_installments_due_status', ('due_date', 'status')),
    ('journal_entries', 'ix_reports_journal_date_status_branch', ('entry_date', 'status', 'branch_id')),
    ('journal_items', 'ix_reports_items_account_entry', ('account_id', 'entry_id')),
    ('journal_items', 'ix_reports_items_sub_detail', ('sub_account_id', 'detail_account_id')),
    ('class_groups', 'ix_reports_class_status_branch_course', ('status', 'branch_id', 'course_id')),
    ('class_sessions', 'ix_reports_session_date_class', ('session_date', 'class_id')),
    ('exams', 'ix_reports_exam_date_course_class', ('exam_date', 'course_id', 'class_id')),
    ('certificates', 'ix_reports_certificate_date_status', ('issue_date', 'status')),
    ('report_budgets', 'ix_report_budget_period', ('fiscal_year', 'period', 'period_no')),
    ('account_reconciliations', 'ix_reports_recon_kind_status_date', ('account_kind', 'status', 'reconciliation_date')),
    ('cashbox_transactions', 'ix_reports_cashbox_tx_date', ('transaction_date', 'cashbox_id')),
    ('bank_accounts', 'ix_reports_bank_accounts_branch_active', ('branch_id', 'is_active')),
    ('bank_transactions', 'ix_reports_bank_tx_date', ('transaction_date', 'bank_account_id')),
)


def ensure_reporting_indexes() -> int:
    """Add backward-compatible scope columns and create missing report indexes."""
    created = 0
    inspector = inspect(db.engine)
    tables = set(inspector.get_table_names())
    # create_all cannot add columns to an existing installation. Old bank
    # accounts remain shared (NULL branch) and old annual budgets remain valid.
    migrations = (
        ('bank_accounts', 'branch_id', 'ALTER TABLE bank_accounts ADD COLUMN branch_id INTEGER'),
        ('report_budgets', 'period_no', 'ALTER TABLE report_budgets ADD COLUMN period_no INTEGER'),
        ('report_schedules', 'schedule_day', 'ALTER TABLE report_schedules ADD COLUMN schedule_day INTEGER'),
    )
    for table_name, column_name, statement in migrations:
        if table_name not in tables:
            continue
        columns = {item['name'] for item in inspect(db.engine).get_columns(table_name)}
        if column_name not in columns:
            try:
                db.session.execute(text(statement))
                db.session.commit()
                created += 1
            except Exception:
                db.session.rollback()
                # A concurrent process may have added the same nullable column.
                refreshed = {item['name'] for item in inspect(db.engine).get_columns(table_name)}
                if column_name not in refreshed:
                    raise
    if 'report_schedules' in tables:
        from models.reporting import ReportSchedule
        from utils.jalali import gregorian_to_jalali_obj
        changed = False
        for schedule in ReportSchedule.query.filter(ReportSchedule.schedule_day.is_(None)).all():
            jalali = gregorian_to_jalali_obj(schedule.next_run_at)
            if jalali:
                schedule.schedule_day = jalali.day
                changed = True
        if changed:
            db.session.commit()
    inspector = inspect(db.engine)
    for table_name, index_name, column_names in INDEX_SPECS:
        if table_name not in tables:
            continue
        table = db.metadata.tables.get(table_name)
        if table is None or any(name not in table.c for name in column_names):
            continue
        existing = {item['name'] for item in inspect(db.engine).get_indexes(table_name)}
        if index_name in existing:
            continue
        try:
            Index(index_name, *(table.c[name] for name in column_names)).create(
                bind=db.engine, checkfirst=True
            )
            created += 1
        except Exception:
            # Another worker may win the startup race between inspection and
            # CREATE INDEX.  Only suppress the expected duplicate outcome.
            refreshed = {item['name'] for item in inspect(db.engine).get_indexes(table_name)}
            if index_name not in refreshed:
                raise
    return created
