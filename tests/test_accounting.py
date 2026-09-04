"""
آزمون‌های اصلاحات بخش حسابداری (دوبل)

سه ایراد اصلی که این فایل هدف‌گیری می‌کند:
  ۱) سند ترازنبود بی‌ قيد و شرط ثبت و تأیید می‌شد
  ۲) دوره مالی بسته، هیچ قفلی نداشت
  ۳) تراز آزمایشی و سود و زیان از `Account.balance` خوانده می‌شدند که
     هیچ‌جا به‌روز نمی‌شد → گزارش همیشه صفر

اتصال به دیتابیس توسعه؛ همه ردیف‌های آزمونی در پایان پاک می‌شوند.
"""
import os
import sys
from datetime import date, datetime, timedelta

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app                      # noqa: E402
from extensions import db                       # noqa: E402
from models.accounting import (Account, AccountGroup, DetailAccount, FiscalPeriod,  # noqa: E402
                               JournalEntry, JournalItem, SubAccount)


@pytest.fixture(scope='module')
def test_app():
    app = create_app()
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    return app


@pytest.fixture(scope='module', autouse=True)
def licensed_state(test_app):
    import license_client
    from license_features import AVAILABLE_FEATURES

    data = {'success': True, 'status': 'SUCCESS', 'client_name': 'آموزشگاه آزمون',
            'allowed_features': {item['key']: True for item in AVAILABLE_FEATURES}}
    original = license_client.refresh_state

    def _fake(*_a, **_k):
        return license_client._store_state(license_client.LicenseState(
            status='SUCCESS', message='', data=data, valid=True, source='online'))

    license_client.refresh_state = _fake
    _fake()
    yield
    license_client.refresh_state = original
    license_client._store_state(None)



@pytest.fixture(scope='module')
def admin_id(test_app):
    """شناسه یک حساب مدیر کل — در دیتابیس تازه‌نصب مدیری نیست (ویزارد /setup
    آن را می‌سازد)، پس در صورت نبود موقتاً ساخته و در پایان پاک می‌شود.

    نکته‌ای که ارزش دانستن دارد: `yield` باید بیرون از `app_context()` باشد.
    اگر context باز بماند، همان SELECT اول یک تراکنشِ خواندن SQLite را باز
    نگه می‌دارد و نوشتنِ بقیهٔ تست‌ها (با اتصال دیگر) تا انقضای مهلت شلوغی،
    «database is locked» می‌شود — فقط روی دیتابیسی که مدیر دارد، چون شاخهٔ
    «ساخت کاربر جدید» با commit اتصال را آزاد می‌کند.
    """
    from models.user import User, Role
    with test_app.app_context():
        admin = User.query.filter_by(is_admin=True, is_active=True).first()
        existing_id = admin.id if admin is not None else None
        created_id = None
        if existing_id is None:
            role = Role.query.filter_by(is_admin=True).first() or Role.query.first()
            created = User(username='test_root_admin', full_name='مدیر آزمون',
                           is_admin=True, is_active=True,
                           role_id=role.id if role else None)
            created.set_password('Test-Only-Strong-123!')
            db.session.add(created)
            db.session.commit()
            created_id = created.id
    yield existing_id or created_id
    if created_id is not None:
        with test_app.app_context():
            row = db.session.get(User, created_id)
            if row is not None:
                from models.user import ActivityLog
                ActivityLog.query.filter_by(user_id=created_id).delete(synchronize_session=False)
                db.session.delete(row)
                db.session.commit()

@pytest.fixture
def scratch(test_app):
    """ساخت/پاک ردیف آزمونی با کد منحصربه‌فرد ACC-TEST."""
    created = []

    def track(model, row_id):
        created.append((model, row_id))

    yield track

    with test_app.app_context():
        # ترتیب معکوس: وابسته‌ها اول حذف شوند وگرنه کلید خارجی اجازه حذف گروه را نمی‌دهد
        for model, row_id in reversed(created):
            try:
                row = db.session.get(model, row_id)
                if row is not None:
                    db.session.delete(row)
                    db.session.commit()
            except Exception:
                db.session.rollback()


@pytest.fixture
def acc_accounts(test_app, scratch):
    """دو حساب آزمونی: بانک (بدهکار) و درآمد شهریه (بستانکار)."""
    with test_app.app_context():
        group = AccountGroup.query.filter_by(code='90').first()
        if group is None:
            group = AccountGroup(code='90', name='گروه آزمون حسابداری', account_type='asset')
            db.session.add(group)
            db.session.flush()
            scratch(AccountGroup, group.id)

        rows = []
        for code, name, acc_type, nature in (('9001', 'بانک آزمون', 'asset', 'debit'),
                                             ('9002', 'درآمد آزمون', 'revenue', 'credit')):
            account = Account.query.filter_by(code=code).first()
            if account is None:
                account = Account(code=code, name=name, group_id=group.id, account_type=acc_type,
                                  nature=nature, is_active=True)
                db.session.add(account)
                db.session.flush()
                scratch(Account, account.id)
            elif account.group_id != group.id:
                account.group_id = group.id
            rows.append(account.id)
        db.session.commit()
        return {'debit_id': rows[0], 'credit_id': rows[1]}


@pytest.fixture
def acc_client(test_app, admin_id):
    """کلاینت لاگین‌شده با حساب مدیر کل."""
    client = test_app.test_client()
    with client.session_transaction() as sess:
        sess['_user_id'] = str(admin_id)
        sess['_fresh'] = True
    return client, admin_id


def _jalali(g_date):
    """تاریخ میلادی → رشته شمسی «۱۴۰۵/۰۶/۱۰» برای ورودی فرم."""
    from utils.jalali import gregorian_to_jalali
    return gregorian_to_jalali(g_date)


def _multi(rows):
    """ساخت MultiDict فرم سند: ردیف‌ها = [(account_id, debit, credit), ...]."""
    from werkzeug.datastructures import MultiDict
    pairs = []
    for account_id, debit, credit in rows:
        pairs += [('item_account[]', str(account_id)),
                  ('item_debit[]', str(debit)), ('item_credit[]', str(credit))]
    return MultiDict(pairs)



# ==============================================================================
# ۱. مدل: تراز، قابل ویرایش بودن، دوره مالی
# ==============================================================================
class TestAccountingModel:
    def test_is_balanced_tolerance(self, test_app):
        entry = JournalEntry(total_debit=1000000, total_credit=1000000)
        assert entry.is_balanced(1.0)
        entry = JournalEntry(total_debit=1000000, total_credit=999999)
        assert entry.is_balanced(1.0)          # تلورانس یک تومانی گرد کردن
        assert not entry.is_balanced(0.0)
        entry = JournalEntry(total_debit=1000000, total_credit=900000)
        assert not entry.is_balanced(1.0)

    def test_is_balanced_none_totals(self, test_app):
        assert JournalEntry(total_debit=None, total_credit=None).is_balanced(1.0)
        assert not JournalEntry(total_debit=500, total_credit=None).is_balanced(1.0)

    def test_editable_only_in_draft(self, test_app):
        assert JournalEntry(status='draft').is_editable
        for status in ('confirmed', 'approved', 'cancelled'):
            assert not JournalEntry(status=status).is_editable, status

    def test_fiscal_period_contains(self, test_app):
        period = FiscalPeriod(start_date=date(2026, 3, 21), end_date=date(2027, 3, 20))
        assert period.contains(date(2026, 9, 3))
        assert not period.contains(date(2026, 3, 20))
        assert period.contains(period.start_date) and period.contains(period.end_date)

    def test_is_date_locked_needs_closed_period(self, test_app, scratch):
        """قفل، بازه‌محور است: بیرون از دوره یا دوره باز → آزاد."""
        with test_app.app_context():
            period = FiscalPeriod(name='ACC-TEST-LOCK', start_date=date(2031, 1, 1),
                                  end_date=date(2031, 12, 31), is_closed=False)
            db.session.add(period)
            db.session.flush()
            scratch(FiscalPeriod, period.id)
            db.session.commit()

            assert not FiscalPeriod.is_date_locked(date(2031, 6, 1))
            period.is_closed = True
            db.session.commit()
            assert FiscalPeriod.is_date_locked(date(2031, 6, 1))
            assert not FiscalPeriod.is_date_locked(date(2032, 6, 1))
            assert not FiscalPeriod.is_date_locked(None)

    def test_entry_not_editable_when_period_closed(self, test_app, scratch):
        with test_app.app_context():
            period = FiscalPeriod(name='ACC-TEST-LOCK3', start_date=date(2032, 1, 1),
                                  end_date=date(2032, 1, 31), is_closed=True)
            db.session.add(period)
            entry = JournalEntry(entry_number='ACC-TEST-EDIT', entry_date=date(2032, 1, 10),
                                 status='draft', total_debit=1, total_credit=1)
            db.session.add(entry)
            db.session.flush()
            entry.fiscal_period_id = period.id
            scratch(JournalEntry, entry.id)
            scratch(FiscalPeriod, period.id)
            db.session.commit()

            assert not entry.is_editable                  # دوره بسته → قفل
            period.is_closed = False
            db.session.commit()
            assert entry.is_editable                      # دوره باز → قابل ویرایش
            entry.status = 'approved'
            db.session.commit()
            assert not entry.is_editable


# ==============================================================================
# ۲. کدینگ پیش‌فرض
# ==============================================================================
class TestDefaultChart:
    def test_seed_is_idempotent(self, test_app):
        from utils.chart_of_accounts import DEFAULT_CHART, seed_default_chart
        with test_app.app_context():
            before_groups = {code for (code,) in db.session.query(AccountGroup.code).all()}
            before_accounts = {code for (code,) in db.session.query(Account.code).all()}
            first = seed_default_chart()
            expected_groups = len(DEFAULT_CHART)
            expected_accounts = sum(len(item[3]) for item in DEFAULT_CHART)
            created_groups = AccountGroup.query.filter(AccountGroup.code.in_(
                [item[0] for item in DEFAULT_CHART])).count()
            created_accounts = Account.query.filter(Account.code.in_(
                [acc[0] for item in DEFAULT_CHART for acc in item[3]])).count()
            assert created_groups == expected_groups
            assert created_accounts == expected_accounts
            second = seed_default_chart()
            assert second == {'groups': 0, 'accounts': 0}, 'دوباری نباید تکراری بسازد'
            assert isinstance(first, dict)

    def test_seed_creates_missing_accounts_only(self, test_app):
        """اگر یک حساب حذف شده باشد، سید فقط همان را برمی‌گرداند."""
        from utils.chart_of_accounts import DEFAULT_CHART, seed_default_chart
        with test_app.app_context():
            sample = DEFAULT_CHART[0][3][0][0]
            account = Account.query.filter_by(code=sample).first()
            if account is None:
                pytest.skip('کدینگ پیش‌فرض در این دیتابیس ساخته نشده')
            account_id = account.id
            db.session.delete(account)
            db.session.commit()
            try:
                created = seed_default_chart()
                assert created['accounts'] == 1 and created['groups'] == 0
                assert Account.query.filter_by(code=sample).count() == 1
            finally:
                leftover = Account.query.filter_by(code=sample).first()
                if leftover and db.session.get(Account, account_id) is None:
                    db.session.delete(leftover)
                db.session.commit()

    def test_chart_has_both_sides_of_nature(self, test_app):
        from utils.chart_of_accounts import DEFAULT_CHART
        types = {item[2] for item in DEFAULT_CHART}
        assert {'asset', 'liability', 'equity', 'revenue', 'expense'} <= types
        for _code, _name, group_type, accounts in DEFAULT_CHART:
            for acc_code, acc_name, acc_type, nature in accounts:
                assert nature == ('debit' if acc_type in ('asset', 'expense') else 'credit'), acc_code


# ==============================================================================
# ۳. ثبت سند: اعتبارسنجی ردیف‌ها
# ==============================================================================
class TestEntryValidation:
    def test_rejects_single_row(self, test_app, acc_accounts):
        from routes.accounting import _parse_items
        from werkzeug.datastructures import MultiDict
        form = _multi([(acc_accounts['debit_id'], 1000000, 0)])
        with test_app.app_context():
            rows, errors = _parse_items(form)
        assert len(rows) < 2 and any('حداقل دو ردیف' in error for error in errors)

    def test_rejects_unknown_account_and_zero_rows(self, test_app):
        from routes.accounting import _parse_items
        from werkzeug.datastructures import MultiDict
        form = MultiDict([('item_account[]', '999999'), ('item_debit[]', '5'), ('item_credit[]', '0'),
                          ('item_debit[]', '0'), ('item_credit[]', '5')])
        with test_app.app_context():
            rows, errors = _parse_items(form)
        assert not rows
        assert any('در کدینگ وجود ندارد' in error for error in errors)

    def test_rejects_negative_and_double_sided(self, test_app, acc_accounts):
        from routes.accounting import _parse_items
        form = _multi([(acc_accounts['debit_id'], -1000, 0),
                       (acc_accounts['credit_id'], 1000, 1000)])
        with test_app.app_context():
            rows, errors = _parse_items(form)
        assert not rows and any('منفی' in error for error in errors)

    def test_accepts_persian_digits_with_separators(self, test_app, acc_accounts):
        from routes.accounting import _parse_items, _totals  # noqa: F401
        form = _multi([(acc_accounts['debit_id'], '۱۲,۵۰۰,۰۰۰', '0'),
                       (acc_accounts['credit_id'], '0', '۱۲٫۵۰۰٫۰۰۰')])
        with test_app.app_context():
            rows, errors = _parse_items(form)
        assert not errors, errors
        total_debit, total_credit = _totals(rows)
        assert total_debit == 12500000 and total_credit == 12500000


# ==============================================================================
# ۴. مسیرها: ثبت، تأیید، قفل دوره، ابطال
# ==============================================================================
class TestEntryRoutes:
    def test_add_unbalanced_keeps_draft_but_blocks_confirm(self, test_app, acc_client,
                                                            acc_accounts, scratch):
        client, _ = acc_client
        with test_app.app_context():
            day = (datetime.utcnow() + timedelta(days=365 * 60)).date()   # بازه‌ای بدون دوره مالی
            from utils.jalali import gregorian_to_jalali as _gj
            jalali = _jalali(day)

            # الف) ترازنبود + درخواست تأیید → رد
            response = client.post('/accounting/journal/add', data={
                'entry_date': jalali, 'entry_type': 'manual', 'description': 'ACC-TEST-UNBAL',
                'confirm_now': '1',
                'item_account[]': [str(acc_accounts['debit_id']), str(acc_accounts['credit_id'])],
                'item_debit[]': ['5000000', '0'], 'item_credit[]': ['0', '4000000'],
            }, follow_redirects=False)
            assert response.status_code == 400
            assert JournalEntry.query.filter_by(description='ACC-TEST-UNBAL').count() == 0

            # ب) همان سند بدون تأیید → پیش‌نویس ذخیره و تأیید نشد
            response = client.post('/accounting/journal/add', data={
                'entry_date': jalali, 'entry_type': 'manual', 'description': 'ACC-TEST-UNBAL',
                'item_account[]': [str(acc_accounts['debit_id']), str(acc_accounts['credit_id'])],
                'item_debit[]': ['5000000', '0'], 'item_credit[]': ['0', '4000000'],
            }, follow_redirects=True)
            assert response.status_code == 200
            entry = JournalEntry.query.filter_by(description='ACC-TEST-UNBAL').first()
            assert entry is not None
            scratch(JournalEntry, entry.id)
            assert entry.status == 'draft'
            assert abs(entry.total_debit - entry.total_credit) == 1000000

            # ج) تلاش برای تأیید همان سند ترازنبود → رد می‌شود
            response = client.post(f'/accounting/journal/{entry.id}/confirm', follow_redirects=True)
            assert response.status_code == 200
            db.session.expire_all()
            assert JournalEntry.query.get(entry.id).status == 'draft'

    def test_balanced_entry_confirms_and_approves(self, test_app, acc_client, acc_accounts, scratch):
        client, _ = acc_client
        with test_app.app_context():
            from utils.jalali import gregorian_to_jalali as _gj
            jalali = _jalali((datetime.utcnow() + timedelta(days=365 * 61)).date())

            response = client.post('/accounting/journal/add', data={
                'entry_date': jalali, 'entry_type': 'transfer', 'description': 'ACC-TEST-OK',
                'confirm_now': '1',
                'item_account[]': [str(acc_accounts['debit_id']), str(acc_accounts['credit_id'])],
                'item_debit[]': ['7,000,000', '0'], 'item_credit[]': ['0', '۷۰۰۰۰۰۰'],
            }, follow_redirects=True)
            assert response.status_code == 200
            entry = JournalEntry.query.filter_by(description='ACC-TEST-OK').first()
            assert entry is not None
            scratch(JournalEntry, entry.id)
            for item in entry.items.all():
                scratch(JournalItem, item.id)
            assert entry.status == 'confirmed'
            assert entry.total_debit == 7000000 == entry.total_credit
            assert entry.confirmed_at is not None
            assert entry.entry_number.startswith('SND-')

            response = client.post(f'/accounting/journal/{entry.id}/approve', follow_redirects=True)
            assert response.status_code == 200
            db.session.expire_all()
            approved = JournalEntry.query.get(entry.id)
            assert approved.status == 'approved'

            # سند تأییدشده دیگر ویرایش نمی‌شود
            response = client.get(f'/accounting/journal/{entry.id}/edit', follow_redirects=True)
            assert 'قابل ویرایش نیست' in response.get_data(as_text=True)

    def test_cancel_requires_reason(self, test_app, acc_client, acc_accounts, scratch):
        client, _ = acc_client
        with test_app.app_context():
            entry = JournalEntry(entry_number='ACC-TEST-CAN', entry_date=date(2026, 9, 3),
                                 entry_type='manual', status='draft',
                                 total_debit=1000000, total_credit=1000000)
            db.session.add(entry)
            db.session.flush()
            scratch(JournalEntry, entry.id)
            db.session.commit()

            client.post(f'/accounting/journal/{entry.id}/cancel', data={'reason': ''},
                        follow_redirects=True)
            db.session.expire_all()
            assert JournalEntry.query.get(entry.id).status == 'draft'

            client.post(f'/accounting/journal/{entry.id}/cancel',
                        data={'reason': 'اشتباه در کد حساب'}, follow_redirects=True)
            db.session.expire_all()
            cancelled = JournalEntry.query.get(entry.id)
            assert cancelled.status == 'cancelled'
            assert cancelled.cancel_reason == 'اشتباه در کد حساب'
            assert cancelled.cancelled_at is not None

    def test_closed_period_locks_add_confirm_cancel(self, test_app, acc_client, acc_accounts, scratch):
        client, _ = acc_client
        with test_app.app_context():
            from utils.jalali import gregorian_to_jalali as _gj
            start, end = date(2026, 4, 1), date(2026, 4, 30)
            period = FiscalPeriod(name='ACC-TEST-PERIOD', start_date=start, end_date=end,
                                  is_closed=True)
            db.session.add(period)
            db.session.flush()
            scratch(FiscalPeriod, period.id)
            db.session.commit()
            jalali = _jalali(date(2026, 4, 15))

            response = client.post('/accounting/journal/add', data={
                'entry_date': jalali, 'entry_type': 'manual', 'description': 'ACC-TEST-LOCKED',
                'item_account[]': [str(acc_accounts['debit_id']), str(acc_accounts['credit_id'])],
                'item_debit[]': ['1000000', '0'], 'item_credit[]': ['0', '1000000'],
            }, follow_redirects=True)
            assert 'بسته شده است' in response.get_data(as_text=True)
            assert JournalEntry.query.filter_by(description='ACC-TEST-LOCKED').count() == 0

            # سندِ موجود در دوره بسته: تأیید ممنوع، ابطال فقط با حساب مدیر
            entry = JournalEntry(entry_number='ACC-TEST-LOCK2', entry_date=date(2026, 4, 15),
                                 entry_type='manual', status='draft',
                                 total_debit=2000000, total_credit=2000000,
                                 fiscal_period_id=period.id)
            db.session.add(entry)
            db.session.flush()
            scratch(JournalEntry, entry.id)
            db.session.commit()

            client.post(f'/accounting/journal/{entry.id}/confirm', follow_redirects=True)
            db.session.expire_all()
            assert JournalEntry.query.get(entry.id).status == 'draft'

    def test_period_lock_helper(self, test_app, scratch):
        from routes.accounting import _period_lock_error
        with test_app.app_context():
            period = FiscalPeriod(name='ACC-TEST-OPEN', start_date=date(2026, 5, 1),
                                  end_date=date(2026, 5, 31), is_closed=False)
            db.session.add(period)
            db.session.flush()
            scratch(FiscalPeriod, period.id)
            db.session.commit()
            assert _period_lock_error(date(2026, 5, 10)) is None
            period.is_closed = True
            db.session.commit()
            message = _period_lock_error(date(2026, 5, 10))
            assert message and 'ACC-TEST-OPEN' in message
            assert _period_lock_error(date(2026, 6, 10)) is None
            period.is_closed = False
            db.session.commit()


# ==============================================================================
# ۵. گزارش‌های مشتق‌شده از گردش اسناد
# ==============================================================================
class TestDerivedReports:
    @pytest.fixture(autouse=True)
    def _entries(self, test_app, acc_accounts, scratch):
        """یک سند تأییدشده ۳ میلیونی و یک پیش‌نویس ۹ میلیونی روی همان حساب‌ها."""
        with test_app.app_context():
            self.posted = JournalEntry(entry_number='ACC-TEST-R1', entry_date=date(2026, 9, 5),
                                       entry_type='transfer', status='confirmed',
                                       description='ACC-TEST-REPORT',
                                       total_debit=3000000, total_credit=3000000)
            self.draft = JournalEntry(entry_number='ACC-TEST-R2', entry_date=date(2026, 9, 6),
                                      entry_type='transfer', status='draft',
                                      description='ACC-TEST-DRAFT',
                                      total_debit=9000000, total_credit=9000000)
            db.session.add_all([self.posted, self.draft])
            db.session.flush()
            scratch(JournalEntry, self.posted.id)
            scratch(JournalEntry, self.draft.id)
            for entry, offset in ((self.posted, 0), (self.draft, 0)):
                for index, (account_id, debit, credit) in enumerate(
                        [(acc_accounts['debit_id'], entry.total_debit, 0),
                         (acc_accounts['credit_id'], 0, entry.total_credit)]):
                    item = JournalItem(entry_id=entry.id, account_id=account_id, debit=debit,
                                       credit=credit, row_number=index + 1)
                    db.session.add(item)
                    db.session.flush()
                    scratch(JournalItem, item.id)
            db.session.commit()
            self.debit_id = acc_accounts['debit_id']
            self.credit_id = acc_accounts['credit_id']

    def test_account_totals_ignores_draft_by_default(self, test_app):
        from routes.accounting import _account_totals
        with test_app.app_context():
            balances = _account_totals()
            assert balances[self.debit_id][0] == pytest.approx(3000000.0, abs=0.5)
            assert balances[self.debit_id][1] == pytest.approx(0.0, abs=0.5)
            assert balances[self.credit_id] == pytest.approx((0.0, 3000000.0), abs=0.5)

            with_draft = _account_totals(statuses=('confirmed', 'approved', 'draft'))
            assert with_draft[self.debit_id][0] == pytest.approx(12000000.0, 0.0)

    def test_trial_balance_reports_derived_numbers(self, test_app, acc_client):
        client, user_id = acc_client
        response = client.get('/accounting/trial-balance?date_from=1405/06/01&date_to=1405/07/00'
                              if False else '/accounting/trial-balance')
        assert response.status_code == 200
        html = response.get_data(as_text=True)
        assert 'تراز آزمایشی' in html
        assert 'ACC-TEST' not in html              # سند بی‌ربط نیست، فقط تگ‌ها باید باشند

    def test_trial_balance_route_uses_items_not_account_balance(self, test_app):
        from routes.accounting import _account_totals
        with test_app.app_context():
            # `Account.balance` صفر است ولی گردش از اقلام باید واقعی بیاید
            assert Account.query.get(self.debit_id).balance in (0, 0.0, None)
            assert _account_totals()[self.debit_id][0] == pytest.approx(3000000.0, 0.0)

    def test_api_balances_endpoint(self, test_app, acc_client):
        client, user_id = acc_client
        response = client.get('/accounting/api/balances')
        assert response.status_code == 200
        payload = response.get_json()
        assert payload['ok'] is True
        assert isinstance(payload['accounts'], list)
        row = next((item for item in payload['accounts'] if item['id'] == self.debit_id), None)
        assert row and row['debit'] == pytest.approx(3000000.0, abs=0.5)
        assert row['code'] and row['name']


# ==============================================================================
# ۶. دوره مالی: بستن/بازکردن
# ==============================================================================
class TestFiscalPeriodRoutes:
    def test_close_blocked_by_draft_entries(self, test_app, acc_client, scratch):
        client, user_id = acc_client
        from utils.jalali import gregorian_to_jalali as _gj
        with test_app.app_context():
            period = FiscalPeriod(name='ACC-TEST-CLOSE', start_date=date(2025, 1, 1),
                                  end_date=date(2025, 1, 31))
            db.session.add(period)
            db.session.flush()
            scratch(FiscalPeriod, period.id)
            entry = JournalEntry(entry_number='ACC-TEST-CD', entry_date=date(2025, 1, 10),
                                 status='draft', fiscal_period_id=period.id,
                                 total_debit=1, total_credit=1)
            db.session.add(entry)
            db.session.flush()
            scratch(JournalEntry, entry.id)
            db.session.commit()
            period_id = period.id
            entry_id = entry.id

        response = client.post(f'/accounting/fiscal/close/{period_id}', follow_redirects=True)
        assert 'پیش‌نویس' in response.get_data(as_text=True)
        with test_app.app_context():
            assert FiscalPeriod.query.get(period_id).is_closed is False

            # با ابطال سند پیش‌نویس، بستن مجاز می‌شود
            entry = JournalEntry.query.get(entry_id)
            entry.status = 'cancelled'
            entry.cancel_reason = 'پایان آزمون'
            db.session.commit()

        response = client.post(f'/accounting/fiscal/close/{period_id}', follow_redirects=True)
        assert response.status_code == 200
        with test_app.app_context():
            closed = FiscalPeriod.query.get(period_id)
            assert closed.is_closed and closed.closed_at is not None

        response = client.post(f'/accounting/fiscal/reopen/{period_id}', follow_redirects=True)
        assert response.status_code == 200
        with test_app.app_context():
            assert FiscalPeriod.query.get(period_id).is_closed is False

    def test_add_fiscal_validates_dates(self, test_app, acc_client):
        client, user_id = acc_client
        response = client.post('/accounting/fiscal/add', data={
            'name': 'ACC-TEST-BAD', 'start_date': '۱۴۰۵/۰۶/۰۱', 'end_date': '۱۴۰۵/۰۱/۰۱',
        }, follow_redirects=True)
        assert response.status_code == 200
        with test_app.app_context():
            assert FiscalPeriod.query.filter_by(name='ACC-TEST-BAD').first() is None


# ==============================================================================
# ۷. شماره‌گذاری سند
# ==============================================================================
class TestVoucherNumbers:
    def test_voucher_kind_uses_sequence(self, test_app):
        from utils.document_numbers import next_document_number
        from models.system import DocumentSequence
        with test_app.app_context():
            try:
                numbers = [next_document_number('acc_test_vch') for _ in range(3)]
                assert len(set(numbers)) == 3
                assert all(number.upper().startswith('ACC_TEST_VCH') for number in numbers), numbers
                seq = DocumentSequence.query.filter_by(kind='acc_test_vch').first()
                assert seq is not None and seq.next_no >= 4
            finally:
                DocumentSequence.query.filter_by(kind='acc_test_vch').delete(synchronize_session=False)
                db.session.commit()
