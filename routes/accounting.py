"""Accounting routes"""
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from license_client import license_required, licensed_section
from extensions import db
from utils.form_helpers import get_jalali_date
from models.accounting import (
    AccountGroup, Account, SubAccount, DetailAccount,
    FiscalPeriod, JournalEntry, JournalItem
)
from models.user import ActivityLog
from datetime import datetime

accounting_bp = Blueprint('accounting', __name__)


@accounting_bp.route('/')
@license_required
@login_required
@licensed_section('accounting')
def index():
    return redirect(url_for('accounting.journal'))


# ===== Chart of Accounts =====
@accounting_bp.route('/chart')
@login_required
def chart():
    groups = AccountGroup.query.order_by(AccountGroup.code).all()
    accounts = Account.query.order_by(Account.code).all()
    return render_template('accounting/chart.html', groups=groups, accounts=accounts)


@accounting_bp.route('/chart/add-group', methods=['POST'])
@login_required
def add_group():
    group = AccountGroup(
        code=request.form['code'],
        name=request.form['name'],
        account_type=request.form['account_type'],
        description=request.form.get('description')
    )
    db.session.add(group)
    db.session.commit()
    flash('گروه حساب اضافه شد', 'success')
    return redirect(url_for('accounting.chart'))


@accounting_bp.route('/chart/add-account', methods=['POST'])
@login_required
def add_account():
    account = Account(
        code=request.form['code'],
        name=request.form['name'],
        group_id=request.form['group_id'],
        account_type=request.form.get('account_type'),
        nature=request.form.get('nature', 'debit'),
        description=request.form.get('description')
    )
    db.session.add(account)
    db.session.commit()
    flash('حساب کل اضافه شد', 'success')
    return redirect(url_for('accounting.chart'))


@accounting_bp.route('/chart/add-sub', methods=['POST'])
@login_required
def add_sub():
    sub = SubAccount(
        code=request.form['code'],
        name=request.form['name'],
        account_id=request.form['account_id'],
        description=request.form.get('description')
    )
    db.session.add(sub)
    db.session.commit()
    flash('حساب معین اضافه شد', 'success')
    return redirect(url_for('accounting.chart'))


# ===== Journal =====
@accounting_bp.route('/journal')
@login_required
def journal():
    page = request.args.get('page', 1, type=int)
    status = request.args.get('status', '')
    
    query = JournalEntry.query
    if status:
        query = query.filter_by(status=status)
    
    entries = query.order_by(JournalEntry.entry_date.desc(), JournalEntry.entry_number.desc()).paginate(page=page, per_page=20)
    return render_template('accounting/journal.html', entries=entries, status=status)


@accounting_bp.route('/journal/add', methods=['GET', 'POST'])
@login_required
def add_entry():
    if request.method == 'POST':
        last = JournalEntry.query.order_by(JournalEntry.id.desc()).first()
        entry_num = f'SND-{(last.id + 1) if last else 1:05d}'
        
        entry = JournalEntry(
            entry_number=entry_num,
            entry_date=get_jalali_date(request.form, 'entry_date') if request.form.get('entry_date') else datetime.utcnow().date(),
            entry_type=request.form.get('entry_type', 'income'),
            description=request.form.get('description'),
            status='draft',
            branch_id=request.form.get('branch_id', 1),
            created_by=current_user.id
        )
        db.session.add(entry)
        db.session.flush()
        
        # Add items
        accounts = request.form.getlist('item_account[]')
        debits = request.form.getlist('item_debit[]')
        credits = request.form.getlist('item_credit[]')
        descs = request.form.getlist('item_desc[]')
        
        for i, acc_id in enumerate(accounts):
            if acc_id:
                item = JournalItem(
                    entry_id=entry.id,
                    account_id=int(acc_id),
                    debit=float(debits[i]) if i < len(debits) and debits[i] else 0,
                    credit=float(credits[i]) if i < len(credits) and credits[i] else 0,
                    description=descs[i] if i < len(descs) else '',
                    row_number=i + 1
                )
                db.session.add(item)
        
        entry.calculate_totals()
        db.session.commit()
        
        flash(f'سند {entry_num} ثبت شد', 'success')
        return redirect(url_for('accounting.view_entry', id=entry.id))
    
    accounts = Account.query.filter_by(is_active=True).order_by(Account.code).all()
    return render_template('accounting/add_entry.html', accounts=accounts)


@accounting_bp.route('/journal/<int:id>')
@login_required
def view_entry(id):
    entry = JournalEntry.query.get_or_404(id)
    return render_template('accounting/view_entry.html', entry=entry)


@accounting_bp.route('/journal/<int:id>/confirm', methods=['POST'])
@login_required
def confirm_entry(id):
    entry = JournalEntry.query.get_or_404(id)
    entry.status = 'confirmed'
    entry.confirmed_by = current_user.id
    db.session.commit()
    flash('سند تایید شد', 'success')
    return redirect(url_for('accounting.view_entry', id=id))


@accounting_bp.route('/journal/<int:id>/approve', methods=['POST'])
@login_required
def approve_entry(id):
    entry = JournalEntry.query.get_or_404(id)
    entry.status = 'approved'
    entry.approved_by = current_user.id
    db.session.commit()
    flash('سند تصویب شد', 'success')
    return redirect(url_for('accounting.view_entry', id=id))


@accounting_bp.route('/journal/<int:id>/cancel', methods=['POST'])
@login_required
def cancel_entry(id):
    entry = JournalEntry.query.get_or_404(id)
    entry.status = 'cancelled'
    entry.cancelled_by = current_user.id
    entry.cancelled_at = datetime.utcnow()
    entry.cancel_reason = request.form.get('reason')
    db.session.commit()
    flash('سند ابطال شد', 'warning')
    return redirect(url_for('accounting.view_entry', id=id))


# ===== Ledgers =====
@accounting_bp.route('/ledger')
@login_required
def ledger():
    accounts = Account.query.filter_by(is_active=True).order_by(Account.code).all()
    return render_template('accounting/ledger.html', accounts=accounts)


@accounting_bp.route('/ledger/<int:account_id>')
@login_required
def account_ledger(account_id):
    account = Account.query.get_or_404(account_id)
    items = JournalItem.query.filter_by(account_id=account_id).join(JournalEntry).filter(
        JournalEntry.status.in_(['confirmed', 'approved'])
    ).order_by(JournalItem.id).all()
    
    return render_template('accounting/account_ledger.html', account=account, items=items)


# ===== Fiscal Period =====
@accounting_bp.route('/fiscal')
@login_required
def fiscal():
    periods = FiscalPeriod.query.order_by(FiscalPeriod.start_date.desc()).all()
    return render_template('accounting/fiscal.html', periods=periods)


@accounting_bp.route('/fiscal/close/<int:id>', methods=['POST'])
@login_required
def close_fiscal(id):
    period = FiscalPeriod.query.get_or_404(id)
    period.is_closed = True
    period.closed_at = datetime.utcnow()
    period.closed_by = current_user.id
    db.session.commit()
    flash('دوره مالی بسته شد', 'success')
    return redirect(url_for('accounting.fiscal'))


# ===== Reports =====
@accounting_bp.route('/trial-balance')
@login_required
def trial_balance():
    accounts = Account.query.filter_by(is_active=True).order_by(Account.code).all()
    return render_template('accounting/trial_balance.html', accounts=accounts)


@accounting_bp.route('/profit-loss')
@login_required
def profit_loss():
    revenue_accounts = Account.query.filter_by(account_type='revenue', is_active=True).all()
    expense_accounts = Account.query.filter_by(account_type='expense', is_active=True).all()
    return render_template('accounting/profit_loss.html', 
                         revenue_accounts=revenue_accounts, 
                         expense_accounts=expense_accounts)
