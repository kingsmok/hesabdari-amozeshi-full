"""
مسیرهای حسابداری دوبل (دفتر روزنامه، کدینگ، دوره مالی و گزارش‌ها)

اصلاحات انجام‌شده در این نسخه:
  • سند ترازنبود نه ثبت می‌شود (هشدار) و نه قابل تأیید/تصویب است
  • هر سند به دوره مالی تاریخش وصل می‌شود و در دوره بسته، قفل است
  • تراز آزمایشی و سود و زیان از جمع ستون‌های اسناد (journal_items) به‌دست
    می‌آید؛ پیش‌تر از `Account.balance` خوانده می‌شد که هیچ‌جا به‌روز نمی‌شود
    و گزارش همیشه صفر بود
  • شماره سند از شمارنده پایدار، مبلغ‌ها با تجزیه مقاوم (ارقام فارسی) و
    هر عملیات در تاریخچه فعالیت ثبت می‌شود
  • کدینگ حساب در نصب خالی با یک دکمه ساخته می‌شود
"""
from datetime import datetime

from flask import (Blueprint, abort, flash, jsonify, redirect, render_template, request,
                   url_for)
from flask_login import login_required, current_user
from license_client import license_required, licensed_section
from extensions import db
from utils.access_policy import require_role
from utils.document_numbers import next_document_number
from utils.form_helpers import get_jalali_date, safe_float, safe_int
from models.accounting import (
    AccountGroup, Account, SubAccount, DetailAccount,
    FiscalPeriod, JournalEntry, JournalItem
)

accounting_bp = Blueprint('accounting', __name__)

#: وضعیت‌هایی که در گزارش‌های رسمی محاسبه می‌شوند
POSTED_STATUSES = ('confirmed', 'approved')
_TOLERANCE = 1.0          # تلورانس گرد کردن، در تومان


def _log(action, description, entity_type='journal_entry', entity_id=None):
    """ردپای فعالیت — پیاده‌سازی مشترک در utils/activity_log (DRY)."""
    from utils.activity_log import log_activity
    log_activity(action, description, module='accounting',
                 entity_type=entity_type, entity_id=entity_id)


def _period_lock_error(entry_date):
    """اگر تاریخ سند در دوره بسته باشد، پیام خطا برمی‌گردد وگرنه None."""
    period = FiscalPeriod.for_date(entry_date)
    if period and period.is_closed:
        return (f'دوره مالی «{period.name}» بسته شده است؛ ثبت یا تغییر سند در آن مجاز نیست. '
                'برای ویرایش، ابتدا دوره را باز کنید.')
    return None


def _parse_items(form):
    """ردیف‌های فرم سند → (rows, errors). rows: [{'account_id','debit','credit','description'}]."""
    accounts = form.getlist('item_account[]') or form.getlist('item_account')
    debits = form.getlist('item_debit[]') or form.getlist('item_debit')
    credits = form.getlist('item_credit[]') or form.getlist('item_credit')
    descs = form.getlist('item_desc[]') or form.getlist('item_desc')

    rows, errors = [], []
    valid_account_ids = {row[0] for row in db.session.query(Account.id).all()}
    for index, account_id in enumerate(accounts):
        account_pk = safe_int(account_id, 0)
        debit = safe_float(debits[index]) if index < len(debits) else 0.0
        credit = safe_float(credits[index]) if index < len(credits) else 0.0
        if not account_id:
            continue                                  # ردیف خالی نادیده گرفته می‌شود
        if account_pk not in valid_account_ids:
            errors.append(f'حساب کل ردیف {index + 1} در کدینگ وجود ندارد')
            continue
        if debit < 0 or credit < 0:
            errors.append(f'مبلغ بدهکار/بستانکار ردیف {index + 1} نمی‌تواند منفی باشد')
            continue
        if debit == 0 and credit == 0:
            errors.append(f'ردیف {index + 1} هیچ مبلغی ندارد')
            continue
        if debit and credit:
            errors.append(f'ردیف {index + 1} نباید همزمان بدهکار و بستانکار باشد')
            continue
        rows.append({'account_id': account_pk, 'debit': debit, 'credit': credit,
                     'description': (descs[index] if index < len(descs) else '') or None})

    if len(rows) < 2:
        errors.append('سند باید حداقل دو ردیف (بدهکار و بستانکار) داشته باشد')
    return rows, errors


def _totals(rows):
    return (sum(row['debit'] for row in rows), sum(row['credit'] for row in rows))


# ===== Chart of Accounts =====
@accounting_bp.route('/')
@license_required
@login_required
@licensed_section('accounting')
def index():
    return redirect(url_for('accounting.journal'))


@accounting_bp.route('/chart')
@login_required
def chart():
    from utils.chart_of_accounts import chart_is_empty
    groups = AccountGroup.query.order_by(AccountGroup.code).all()
    accounts = Account.query.order_by(Account.code).all()
    balances = _account_totals()
    entry_counts = dict((row[0], row[1]) for row in db.session.query(
        JournalItem.account_id, db.func.count(db.distinct(JournalItem.entry_id)))
        .group_by(JournalItem.account_id).all())

    rows = []
    for account in accounts:
        debit, credit = balances.get(account.id, (0.0, 0.0))
        net = debit - credit if (account.nature or 'debit') == 'debit' else credit - debit
        rows.append({'account': account, 'debit': debit, 'credit': credit,
                     'balance': net, 'entries': entry_counts.get(account.id, 0)})

    return render_template('accounting/chart.html', groups=groups, accounts=accounts, rows=rows,
                           sub_accounts=SubAccount.query.order_by(SubAccount.code).all(),
                           can_edit=current_user.is_admin or current_user.has_permission('accounting', 'edit'),
                           is_empty=chart_is_empty())


@accounting_bp.route('/chart/seed-default', methods=['POST'])
@login_required
@require_role('accounting', 'edit')
def seed_chart():
    """ساخت کدینگ استاندارد در نصب خالی (بدون دست‌زدن به حساب‌های موجود)."""
    from utils.chart_of_accounts import seed_default_chart
    result = seed_default_chart()
    _log('create', f'ساخت کدینگ پیش‌فرض: {result["groups"]} گروه و {result["accounts"]} حساب',
         'account', None)
    db.session.commit()
    flash(f'کدینگ حسابداری ساخته شد ({result["accounts"]} حساب کل)', 'success')
    return redirect(url_for('accounting.chart'))


@accounting_bp.route('/chart/add-group', methods=['POST'])
@login_required
@require_role('accounting', 'create')
def add_group():
    code = (request.form.get('code') or '').strip()
    name = (request.form.get('name') or '').strip()
    account_type = (request.form.get('account_type') or '').strip()
    if not code or not name:
        flash('کد و نام گروه الزامی است', 'danger')
        return redirect(url_for('accounting.chart'))
    if account_type not in ('asset', 'liability', 'equity', 'revenue', 'expense'):
        flash('نوع گروه نامعتبر است', 'danger')
        return redirect(url_for('accounting.chart'))
    if AccountGroup.query.filter(db.func.lower(AccountGroup.code) == code.lower()).first():
        flash('کد این گروه تکراری است', 'danger')
        return redirect(url_for('accounting.chart'))

    group = AccountGroup(code=code, name=name, account_type=account_type,
                         description=(request.form.get('description') or '').strip() or None)
    db.session.add(group)
    _log('create', f'افزودن گروه حساب {code} — {name}', 'account_group')
    db.session.commit()
    flash('گروه حساب اضافه شد', 'success')
    return redirect(url_for('accounting.chart'))


@accounting_bp.route('/chart/add-account', methods=['POST'])
@login_required
@require_role('accounting', 'create')
def add_account():
    code = (request.form.get('code') or '').strip()
    name = (request.form.get('name') or '').strip()
    group_id = safe_int(request.form.get('group_id'), 0)
    group = AccountGroup.query.get(group_id) if group_id else None
    if not code or not name:
        flash('کد و نام حساب الزامی است', 'danger')
        return redirect(url_for('accounting.chart'))
    if group is None:
        flash('گروه حساب انتخاب‌شده معتبر نیست', 'danger')
        return redirect(url_for('accounting.chart'))
    if Account.query.filter(db.func.lower(Account.code) == code.lower()).first():
        flash('کد این حساب کل تکراری است', 'danger')
        return redirect(url_for('accounting.chart'))

    account_type = (request.form.get('account_type') or group.account_type).strip()
    nature = (request.form.get('nature') or '').strip()
    if nature not in ('debit', 'credit'):
        # ماهیت از نوع حساب: دارایی و هزینه بدهکار، بقیه بستانکار
        nature = 'debit' if account_type in ('asset', 'expense') else 'credit'
    account = Account(
        code=code, name=name, group_id=group.id,
        account_type=account_type, nature=nature,
        description=(request.form.get('description') or '').strip() or None,
        is_active=True, balance=0,
    )
    db.session.add(account)
    _log('create', f'افزودن حساب کل {code} — {name}', 'account')
    db.session.commit()
    flash('حساب کل اضافه شد', 'success')
    return redirect(url_for('accounting.chart'))


@accounting_bp.route('/chart/<int:id>/toggle', methods=['POST'])
@login_required
@require_role('accounting', 'edit')
def toggle_account(id):
    """غیرفعال کردن حساب به‌جای حذف؛ حسابی که سند دارد حذف نمی‌شود."""
    account = Account.query.get_or_404(id)
    if not account.is_active:
        account.is_active = True
        message = f'حساب {account.code} فعال شد'
    else:
        used = db.session.query(JournalItem.id).filter(JournalItem.account_id == account.id).first()
        if used:
            flash('این حساب در اسناد استفاده شده است؛ برای جلوگیری از به‌هم‌ریختن '
                  'گزارش‌ها آن را غیرفعال کنید نه حذف', 'warning')
        account.is_active = False
        message = f'حساب {account.code} غیرفعال شد'
    _log('edit', message, 'account', account.id)
    db.session.commit()
    flash(message, 'success')
    return redirect(url_for('accounting.chart'))


@accounting_bp.route('/chart/add-sub', methods=['POST'])
@login_required
@require_role('accounting', 'create')
def add_sub():
    code = (request.form.get('code') or '').strip()
    name = (request.form.get('name') or '').strip()
    account_id = safe_int(request.form.get('account_id'), 0)
    if not code or not name or not account_id:
        flash('کد، نام و حساب کل الزامی است', 'danger')
        return redirect(url_for('accounting.chart'))
    if SubAccount.query.filter(db.func.lower(SubAccount.code) == code.lower()).first():
        flash('کد این حساب معین تکراری است', 'danger')
        return redirect(url_for('accounting.chart'))
    if Account.query.get(account_id) is None:
        flash('حساب کل انتخاب‌شده معتبر نیست', 'danger')
        return redirect(url_for('accounting.chart'))

    sub = SubAccount(code=code, name=name, account_id=account_id,
                     description=(request.form.get('description') or '').strip() or None)
    db.session.add(sub)
    _log('create', f'افزودن حساب معین {code} — {name}', 'sub_account')
    db.session.commit()
    flash('حساب معین اضافه شد', 'success')
    return redirect(url_for('accounting.chart'))


@accounting_bp.route('/chart/add-detail', methods=['POST'])
@login_required
@require_role('accounting', 'create')
def add_detail():
    """حساب تفصیلی — قبلاً اصلاً مسیر ثبت نداشت و فقط مدل داشت."""
    code = (request.form.get('code') or '').strip()
    name = (request.form.get('name') or '').strip()
    sub_account_id = safe_int(request.form.get('sub_account_id'), 0)
    if not code or not name or not sub_account_id:
        flash('کد، نام و حساب معین الزامی است', 'danger')
        return redirect(url_for('accounting.chart'))
    if SubAccount.query.get(sub_account_id) is None:
        flash('حساب معین انتخاب‌شده معتبر نیست', 'danger')
        return redirect(url_for('accounting.chart'))
    if DetailAccount.query.filter(db.func.lower(DetailAccount.code) == code.lower()).first():
        flash('کد این حساب تفصیلی تکراری است', 'danger')
        return redirect(url_for('accounting.chart'))

    detail = DetailAccount(code=code, name=name, sub_account_id=sub_account_id,
                           description=(request.form.get('description') or '').strip() or None)
    db.session.add(detail)
    _log('create', f'افزودن حساب تفصیلی {code} — {name}', 'detail_account')
    db.session.commit()
    flash('حساب تفصیلی اضافه شد', 'success')
    return redirect(url_for('accounting.chart'))


# ===== Journal =====
@accounting_bp.route('/journal')
@login_required
def journal():
    page = request.args.get('page', 1, type=int)
    status = request.args.get('status', '')
    if status not in ('draft', 'confirmed', 'approved', 'cancelled'):
        status = ''

    query = JournalEntry.query
    if status:
        query = query.filter_by(status=status)
    date_from = get_jalali_date(request.args, 'date_from') if request.args.get('date_from') else None
    date_to = get_jalali_date(request.args, 'date_to') if request.args.get('date_to') else None
    if date_from:
        query = query.filter(JournalEntry.entry_date >= date_from)
    if date_to:
        query = query.filter(JournalEntry.entry_date <= date_to)
    search = (request.args.get('q') or '').strip()
    if search:
        like = f'%{search}%'
        query = query.filter(db.or_(JournalEntry.entry_number.ilike(like),
                                    JournalEntry.description.ilike(like)))

    entries = query.order_by(JournalEntry.entry_date.desc(), JournalEntry.id.desc()).paginate(
        page=page, per_page=20, error_out=False)
    unbalanced = [entry for entry in entries.items if not entry.is_balanced(_TOLERANCE)]

    return render_template('accounting/journal.html', entries=entries, status=status,
                           date_from=request.args.get('date_from', ''),
                           date_to=request.args.get('date_to', ''), q=search,
                           unbalanced_ids={entry.id for entry in unbalanced})


@accounting_bp.route('/journal/add', methods=['GET', 'POST'])
@login_required
@require_role('accounting', 'create')
def add_entry():
    if request.method == 'POST':
        entry_date = (get_jalali_date(request.form, 'entry_date')
                      if request.form.get('entry_date') else datetime.utcnow().date())
        lock_message = _period_lock_error(entry_date)
        if lock_message:
            flash(lock_message, 'danger')
            return redirect(url_for('accounting.fiscal'))

        rows, errors = _parse_items(request.form)
        total_debit, total_credit = _totals(rows)
        difference = round(total_debit - total_credit, 2)
        unbalanced = abs(difference) > _TOLERANCE
        want_confirm = request.form.get('confirm_now') == '1'
        if unbalanced and want_confirm:
            errors.append(f'سند تراز نیست؛ اختلاف بدهکار و بستانکار {abs(difference):,.0f} تومان است '
                          '— برای تأیید، ابتدا اختلاف را برطرف کنید')
        if errors:
            for message in errors:
                flash(message, 'danger')
            accounts = Account.query.filter_by(is_active=True).order_by(Account.code).all()
            return render_template('accounting/add_entry.html', accounts=accounts,
                                   form=request.form, kept_rows=rows,
                                   totals={'debit': total_debit, 'credit': total_credit,
                                           'diff': difference}), 400

        entry_number = next_document_number('voucher')
        # دوره مالی فقط یک‌بار کوئری می‌شود (قبلاً دو بار)
        period_for_date = FiscalPeriod.for_date(entry_date)
        entry = JournalEntry(
            entry_number=entry_number,
            entry_date=entry_date,
            entry_type=request.form.get('entry_type', 'manual'),
            description=(request.form.get('description') or '').strip() or None,
            status='draft',
            fiscal_period_id=period_for_date.id if period_for_date else None,
            branch_id=safe_int(request.form.get('branch_id'), 1) or 1,
            created_by=current_user.id,
        )
        db.session.add(entry)
        db.session.flush()

        for index, row in enumerate(rows):
            db.session.add(JournalItem(entry_id=entry.id, account_id=row['account_id'],
                                       debit=row['debit'], credit=row['credit'],
                                       description=row['description'], row_number=index + 1))
        entry.total_debit = total_debit
        entry.total_credit = total_credit
        _log('create', f'ثبت سند {entry_number} مبلغ {total_debit:,.0f} تومان '
                       f'({len(rows)} ردیف)', 'journal_entry', entry.id)
        db.session.commit()

        if want_confirm and not unbalanced:
            entry.status = 'confirmed'
            entry.confirmed_by = current_user.id
            entry.confirmed_at = datetime.utcnow()
            _log('confirm', f'تأیید سند {entry_number}', 'journal_entry', entry.id)
            db.session.commit()

        if unbalanced:
            flash(f'سند {entry_number} در وضعیت پیش‌نویس ذخیره شد — اختلاف {abs(difference):,.0f} '
                  'تومان دارد و تا تراز شدن قابل تأیید نیست', 'warning')
        else:
            flash(f'سند {entry_number} ثبت شد', 'success')
        return redirect(url_for('accounting.view_entry', id=entry.id))

    accounts = Account.query.filter_by(is_active=True).order_by(Account.code).all()
    return render_template('accounting/add_entry.html', accounts=accounts, form={},
                           kept_rows=[], totals={'debit': 0, 'credit': 0, 'diff': 0},
                           today=datetime.utcnow().date())


@accounting_bp.route('/journal/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@require_role('accounting', 'edit')
def edit_entry(id):
    """ویرایش سند فقط در وضعیت پیش‌نویس و در دوره باز."""
    entry = JournalEntry.query.get_or_404(id)
    if entry.status != 'draft':
        flash('سند تأیید/تصویب‌شده قابل ویرایش نیست؛ ابتدا آن را ابطال و سند جدید بزنید', 'warning')
        return redirect(url_for('accounting.view_entry', id=id))
    if not entry.is_editable:      # دوره مالی آن بسته شده
        flash(_period_lock_error(entry.entry_date) or 'دوره مالی این سند بسته است', 'danger')
        return redirect(url_for('accounting.fiscal'))

    if request.method == 'POST':
        entry_date = (get_jalali_date(request.form, 'entry_date')
                      if request.form.get('entry_date') else entry.entry_date)
        lock_message = _period_lock_error(entry_date)
        if lock_message:
            flash(lock_message, 'danger')
            return redirect(url_for('accounting.fiscal'))

        rows, errors = _parse_items(request.form)
        total_debit, total_credit = _totals(rows)
        difference = round(total_debit - total_credit, 2)
        if len(rows) >= 2 and abs(difference) > _TOLERANCE:
            flash(f'سند تراز نیست (اختلاف {abs(difference):,.0f} تومان)؛ در وضعیت پیش‌نویس '
                  'می‌ماند و تا تراز شدن قابل تأیید نیست', 'warning')
        if errors:
            for message in errors:
                flash(message, 'danger')
            accounts = Account.query.filter_by(is_active=True).order_by(Account.code).all()
            return render_template('accounting/add_entry.html', accounts=accounts,
                                   form=request.form, entry=entry, kept_rows=rows,
                                   totals={'debit': total_debit, 'credit': total_credit,
                                           'diff': total_debit - total_credit}), 400

        JournalItem.query.filter_by(entry_id=entry.id).delete(synchronize_session=False)
        for index, row in enumerate(rows):
            db.session.add(JournalItem(entry_id=entry.id, account_id=row['account_id'],
                                       debit=row['debit'], credit=row['credit'],
                                       description=row['description'], row_number=index + 1))
        period_for_date = FiscalPeriod.for_date(entry_date)
        entry.entry_date = entry_date
        entry.entry_type = request.form.get('entry_type') or entry.entry_type
        entry.description = (request.form.get('description') or '').strip() or None
        entry.total_debit = total_debit
        entry.total_credit = total_credit
        entry.fiscal_period_id = period_for_date.id if period_for_date else None
        _log('edit', f'ویرایش سند {entry.entry_number}', 'journal_entry', entry.id)
        db.session.commit()
        flash('سند به‌روزرسانی شد', 'success')
        return redirect(url_for('accounting.view_entry', id=id))

    accounts = Account.query.filter_by(is_active=True).order_by(Account.code).all()
    rows = [{'account_id': item.account_id, 'debit': item.debit or 0, 'credit': item.credit or 0,
             'description': item.description, 'sub_account_id': item.sub_account_id}
            for item in entry.items.order_by(JournalItem.row_number).all()]
    return render_template('accounting/add_entry.html', accounts=accounts, entry=entry,
                           form={}, kept_rows=rows,
                           totals={'debit': entry.total_debit or 0, 'credit': entry.total_credit or 0,
                                   'diff': (entry.total_debit or 0) - (entry.total_credit or 0)})


@accounting_bp.route('/journal/<int:id>')
@login_required
def view_entry(id):
    entry = JournalEntry.query.get_or_404(id)
    items = entry.items.order_by(JournalItem.row_number).all()
    return render_template('accounting/view_entry.html', entry=entry, items=items,
                           can_edit=current_user.is_admin or current_user.has_permission('accounting', 'edit'))


@accounting_bp.route('/journal/<int:id>/confirm', methods=['POST'])
@login_required
@require_role('accounting', 'edit')
def confirm_entry(id):
    entry = JournalEntry.query.get_or_404(id)
    if not entry.is_balanced(_TOLERANCE):
        flash(f'سند تراز نیست (بدهکار {entry.total_debit:,.0f} — بستانکار {entry.total_credit:,.0f})؛ '
              'ابتدا اختلاف را برطرف کنید', 'danger')
        return redirect(url_for('accounting.view_entry', id=id))
    lock_message = _period_lock_error(entry.entry_date)
    if lock_message:
        flash(lock_message, 'danger')
        return redirect(url_for('accounting.fiscal'))
    if entry.status not in ('draft',):
        flash('فقط سند پیش‌نویس قابل تأیید است', 'warning')
        return redirect(url_for('accounting.view_entry', id=id))

    entry.status = 'confirmed'
    entry.confirmed_by = current_user.id
    entry.confirmed_at = datetime.utcnow()
    if entry.fiscal_period_id is None:
        period = FiscalPeriod.for_date(entry.entry_date)
        entry.fiscal_period_id = period.id if period else None
    _log('confirm', f'تأیید سند {entry.entry_number}', 'journal_entry', entry.id)
    db.session.commit()
    flash('سند تأیید شد', 'success')
    return redirect(url_for('accounting.view_entry', id=id))


@accounting_bp.route('/journal/<int:id>/approve', methods=['POST'])
@login_required
@require_role('accounting', 'edit')
def approve_entry(id):
    entry = JournalEntry.query.get_or_404(id)
    if not entry.is_balanced(_TOLERANCE):
        flash('سند ترازنبود قابل تصویب نیست', 'danger')
        return redirect(url_for('accounting.view_entry', id=id))
    if _period_lock_error(entry.entry_date):
        flash('دوره مالی این سند بسته است؛ تصویب مجاز نیست', 'danger')
        return redirect(url_for('accounting.fiscal'))
    if entry.status not in ('draft', 'confirmed'):
        flash('این سند در وضعیت فعلی قابل تصویب نیست', 'warning')
        return redirect(url_for('accounting.view_entry', id=id))

    entry.status = 'approved'
    entry.approved_by = current_user.id
    entry.approved_at = datetime.utcnow()
    _log('approve', f'تصویب سند {entry.entry_number}', 'journal_entry', entry.id)
    db.session.commit()
    flash('سند تصویب شد', 'success')
    return redirect(url_for('accounting.view_entry', id=id))


@accounting_bp.route('/journal/<int:id>/cancel', methods=['POST'])
@login_required
@require_role('accounting', 'edit')
def cancel_entry(id):
    entry = JournalEntry.query.get_or_404(id)
    if entry.status == 'cancelled':
        flash('این سند قبلاً ابطال شده است', 'warning')
        return redirect(url_for('accounting.view_entry', id=id))
    reason = (request.form.get('reason') or '').strip()
    if not reason:
        flash('برای ابطال سند، نوشتن دلیل الزامی است', 'danger')
        return redirect(url_for('accounting.view_entry', id=id))
    if _period_lock_error(entry.entry_date) and not current_user.is_admin:
        flash('دوره مالی این سند بسته است؛ ابطال آن فقط با حساب مدیر کل ممکن است', 'danger')
        return redirect(url_for('accounting.fiscal'))

    entry.status = 'cancelled'
    entry.cancelled_by = current_user.id
    entry.cancelled_at = datetime.utcnow()
    entry.cancel_reason = reason
    _log('delete', f'ابطال سند {entry.entry_number} — {reason}', 'journal_entry', entry.id)
    db.session.commit()
    flash('سند ابطال شد', 'warning')
    return redirect(url_for('accounting.view_entry', id=id))


# ===== Ledgers =====
@accounting_bp.route('/ledger')
@login_required
def ledger():
    accounts = Account.query.filter_by(is_active=True).order_by(Account.code).all()
    balances = _account_totals()
    rows = [{'account': account,
             'debit': balances.get(account.id, (0, 0))[0],
             'credit': balances.get(account.id, (0, 0))[1]} for account in accounts]
    return render_template('accounting/ledger.html', accounts=rows)


@accounting_bp.route('/ledger/<int:account_id>')
@login_required
def account_ledger(account_id):
    account = Account.query.get_or_404(account_id)
    date_from = get_jalali_date(request.args, 'date_from') if request.args.get('date_from') else None
    date_to = get_jalali_date(request.args, 'date_to') if request.args.get('date_to') else None

    # بهینه‌سازی N+1: account و entry هر آیتم یک‌جا load می‌شوند؛ قبلاً برای
    # هر ردیف دفتر (حتی ده‌ها هزار) دو کوئری جداگانه زده می‌شد.
    from sqlalchemy.orm import contains_eager, joinedload
    query = (db.session.query(JournalItem)
             .join(JournalEntry, JournalItem.entry_id == JournalEntry.id)
             .options(joinedload(JournalItem.account),
                      contains_eager(JournalItem.entry))
             .filter(JournalItem.account_id == account_id,
                     JournalEntry.status.in_(POSTED_STATUSES)))
    if date_from:
        query = query.filter(JournalEntry.entry_date >= date_from)
    if date_to:
        query = query.filter(JournalEntry.entry_date <= date_to)
    items = query.order_by(JournalEntry.entry_date.asc(), JournalItem.row_number.asc()).all()

    rows, running = [], 0.0
    for item in items:
        debit, credit = item.debit or 0, item.credit or 0
        running += debit - credit if (item.account.nature or 'debit') == 'debit' else credit - debit
        rows.append({'item': item, 'entry': item.entry, 'running': running})

    total_debit = sum((item.debit or 0) for item in items)
    total_credit = sum((item.credit or 0) for item in items)
    return render_template('accounting/account_ledger.html', account=account, items=rows,
                           total_debit=total_debit, total_credit=total_credit,
                           balance=running,
                           date_from=request.args.get('date_from', ''),
                           date_to=request.args.get('date_to', ''))


# ===== Fiscal Period =====
@accounting_bp.route('/fiscal')
@login_required
def fiscal():
    from datetime import date as _date
    periods = FiscalPeriod.query.order_by(FiscalPeriod.start_date.desc()).all()
    counts = dict((row[0], row[1]) for row in db.session.query(
        JournalEntry.fiscal_period_id, db.func.count(JournalEntry.id))
        .group_by(JournalEntry.fiscal_period_id).all())
    draft_counts = dict((row[0], row[1]) for row in db.session.query(
        JournalEntry.fiscal_period_id, db.func.count(JournalEntry.id))
        .filter(JournalEntry.status == 'draft').group_by(JournalEntry.fiscal_period_id).all())
    for period in periods:
        period.entry_count = counts.get(period.id, 0)
        period.draft_count = draft_counts.get(period.id, 0)
    return render_template('accounting/fiscal.html', periods=periods, today=_date.today(),
                           can_edit=current_user.is_admin or current_user.has_permission('accounting', 'edit'))


@accounting_bp.route('/fiscal/add', methods=['POST'])
@login_required
@require_role('accounting', 'create')
def add_fiscal():
    start = get_jalali_date(request.form, 'start_date')
    end = get_jalali_date(request.form, 'end_date')
    name = (request.form.get('name') or '').strip()
    if not start or not end or not name:
        flash('نام و تاریخ شروع/پایان (شمسی) الزامی است', 'danger')
        return redirect(url_for('accounting.fiscal'))
    if end < start:
        flash('تاریخ پایان نمی‌تواند قبل از شروع باشد', 'danger')
        return redirect(url_for('accounting.fiscal'))
    overlap = FiscalPeriod.query.filter(FiscalPeriod.start_date <= end,
                                        FiscalPeriod.end_date >= start).first()
    if overlap:
        flash(f'این بازه با دوره «{overlap.name}» هم‌پوشانی دارد', 'danger')
        return redirect(url_for('accounting.fiscal'))

    period = FiscalPeriod(name=name, start_date=start, end_date=end,
                          notes=(request.form.get('notes') or '').strip() or None)
    db.session.add(period)
    _log('create', f'ایجاد دوره مالی {name}', 'fiscal_period')
    db.session.commit()
    flash('دوره مالی ساخته شد و اسناد تاریخ‌های آن به آن وصل می‌شوند', 'success')
    return redirect(url_for('accounting.fiscal'))


@accounting_bp.route('/fiscal/close/<int:id>', methods=['POST'])
@login_required
@require_role('accounting', 'edit')
def close_fiscal(id):
    """بستن دوره: اسناد دوره قفل می‌شوند؛ ابتدا باید سند پیش‌نویس نماند."""
    period = FiscalPeriod.query.get_or_404(id)
    drafts = JournalEntry.query.filter_by(fiscal_period_id=period.id, status='draft').count()
    unassigned = (JournalEntry.query
                  .filter(JournalEntry.fiscal_period_id.is_(None),
                          JournalEntry.entry_date >= period.start_date,
                          JournalEntry.entry_date <= period.end_date,
                          JournalEntry.status == 'draft').count())
    if drafts or unassigned:
        flash(f'برای بستن دوره «{period.name}» ابتدا {drafts + unassigned} سند پیش‌نویس '
              'این دوره را تأیید یا ابطال کنید', 'danger')
        return redirect(url_for('accounting.fiscal'))

    # اتصال اسناد بی‌دورهٔ این بازه به دوره، تا قفل واقعاً شامل همه شود
    loose = (JournalEntry.query
             .filter(JournalEntry.fiscal_period_id.is_(None),
                     JournalEntry.entry_date >= period.start_date,
                     JournalEntry.entry_date <= period.end_date).all())
    for entry in loose:
        entry.fiscal_period_id = period.id

    period.is_closed = True
    period.closed_by_user = True
    period.closed_at = datetime.utcnow()
    period.closed_by = current_user.id
    _log('edit', f'بستن دوره مالی {period.name} ({len(loose)} سند بی‌دوره وصل شد)',
         'fiscal_period', period.id)
    db.session.commit()
    flash(f'دوره «{period.name}» بسته شد؛ از این پس ثبت و تغییر سند در آن مجاز نیست', 'success')
    return redirect(url_for('accounting.fiscal'))


@accounting_bp.route('/fiscal/reopen/<int:id>', methods=['POST'])
@login_required
@require_role('accounting', 'edit')
def reopen_fiscal(id):
    """باز کردن دوره — برای اصلاح اشتباه؛ در تاریخچه ثبت می‌شود."""
    period = FiscalPeriod.query.get_or_404(id)
    if not period.is_closed:
        flash('این دوره بسته نشده است', 'warning')
        return redirect(url_for('accounting.fiscal'))
    period.is_closed = False
    period.closed_by_user = False
    period.closed_at = None
    period.closed_by = None
    _log('edit', f'باز کردن دوره مالی {period.name}', 'fiscal_period', period.id)
    db.session.commit()
    flash(f'دوره «{period.name}» باز شد؛ فراموش نکنید دوباره آن را ببندید', 'warning')
    return redirect(url_for('accounting.fiscal'))


# ===== Reports =====
def _account_totals(date_from=None, date_to=None, statuses=POSTED_STATUSES):
    """جمع بدهکار/بستانکار هر حساب کل از روی اقلام سند (منبع واقعی)."""
    query = (db.session.query(JournalItem.account_id,
                              db.func.coalesce(db.func.sum(JournalItem.debit), 0),
                              db.func.coalesce(db.func.sum(JournalItem.credit), 0))
             .join(JournalEntry, JournalItem.entry_id == JournalEntry.id)
             .filter(JournalEntry.status.in_(statuses)))
    if date_from:
        query = query.filter(JournalEntry.entry_date >= date_from)
    if date_to:
        query = query.filter(JournalEntry.entry_date <= date_to)
    return {row[0]: (float(row[1] or 0), float(row[2] or 0)) for row in query.group_by(
        JournalItem.account_id).all()}


@accounting_bp.route('/trial-balance')
@login_required
def trial_balance():
    from utils.jalali import jalali_period_bounds, normalize_jalali_period

    period = normalize_jalali_period(request.args.get('period'))
    if period:
        bounds = jalali_period_bounds(period)
        date_from, date_to = bounds if bounds else (None, None)
    else:
        date_from = get_jalali_date(request.args, 'date_from') if request.args.get('date_from') else None
        date_to = get_jalali_date(request.args, 'date_to') if request.args.get('date_to') else None

    include_draft = request.args.get('include_draft') == '1'
    statuses = POSTED_STATUSES + (('draft',) if include_draft else ())

    accounts = Account.query.filter_by(is_active=True).order_by(Account.code).all()
    balances = _account_totals(date_from, date_to, statuses)

    rows = []
    total_debit = total_credit = 0.0
    for account in accounts:
        debit, credit = balances.get(account.id, (0.0, 0.0))
        if not debit and not credit:
            continue                      # حساب بی‌حرکت در گزارش نمایش داده نمی‌شود
        net = debit - credit
        row_debit = net if net > 0 else 0.0
        row_credit = -net if net < 0 else 0.0
        total_debit += row_debit
        total_credit += row_credit
        rows.append({'account': account, 'total_debit': debit, 'total_credit': credit,
                     'debit': row_debit, 'credit': row_credit})

    return render_template('accounting/trial_balance.html', rows=rows, accounts=rows,
                           total_debit=total_debit, total_credit=total_credit,
                           balanced=abs(total_debit - total_credit) <= _TOLERANCE,
                           period=period or '', date_from=request.args.get('date_from', ''),
                           date_to=request.args.get('date_to', ''), include_draft=include_draft,
                           count_with_activity=len(rows), count_total=len(accounts))


@accounting_bp.route('/profit-loss')
@login_required
def profit_loss():
    from utils.jalali import jalali_period_bounds, normalize_jalali_period

    period = normalize_jalali_period(request.args.get('period'))
    if period:
        bounds = jalali_period_bounds(period)
        date_from, date_to = bounds if bounds else (None, None)
    else:
        date_from = get_jalali_date(request.args, 'date_from') if request.args.get('date_from') else None
        date_to = get_jalali_date(request.args, 'date_to') if request.args.get('date_to') else None

    balances = _account_totals(date_from, date_to)

    def _collect(kind):
        accounts = Account.query.filter_by(account_type=kind, is_active=True).order_by(Account.code).all()
        rows = []
        total = 0.0
        for account in accounts:
            debit, credit = balances.get(account.id, (0.0, 0.0))
            amount = (credit - debit) if kind == 'revenue' else (debit - credit)
            if not amount and not (debit or credit):
                continue
            total += amount
            rows.append({'account': account, 'amount': amount})
        return rows, total

    revenue_rows, total_revenue = _collect('revenue')
    expense_rows, total_expense = _collect('expense')

    return render_template('accounting/profit_loss.html',
                           revenue_accounts=revenue_rows, expense_accounts=expense_rows,
                           total_revenue=total_revenue, total_expense=total_expense,
                           profit=total_revenue - total_expense,
                           period=period or '', date_from=request.args.get('date_from', ''),
                           date_to=request.args.get('date_to', ''))


@accounting_bp.route('/api/balances')
@login_required
def api_balances():
    """تراز حساب‌ها برای فرم سند (JSON) — جای محاسبه دستی در قالب."""
    balances = _account_totals()
    payload = [{'id': account.id, 'code': account.code, 'name': account.name,
                'nature': account.nature, 'debit': balances.get(account.id, (0, 0))[0],
                'credit': balances.get(account.id, (0, 0))[1]}
               for account in Account.query.filter_by(is_active=True).order_by(Account.code).all()]
    return jsonify({'ok': True, 'accounts': payload})
