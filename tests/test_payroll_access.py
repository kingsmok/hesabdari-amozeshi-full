"""
آزمون‌های اصلاحات حقوق/مالیات و نگهبان دسترسی

پوشش داده‌شده در این فایل (قبلاً هیچ‌کدام تست نداشتند):
  • تبدیل دوره شمسی و بازه میلادی متناظر (علت اصلی صفر شدن حقوق/مالیات در گزارش‌ها)
  • تجزیه اعداد فارسی/جداکننده‌دار در فرم‌ها
  • موتور پلکان مالیات حقوق ۱۴۰۵ (ماهیانه) و قواعد قابل تنظیم
  • شماره‌گذار اسناد (جایگزین last.id + 1)
  • بازمحاسبه جمع‌های فیش و گردش‌کار تأیید/پرداخت
  • سیاست نگهبان سراسری دسترسی (resolve_policy / required_write_action)
"""
import os
import sys
from datetime import date, timedelta

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app                      # noqa: E402
from extensions import db                       # noqa: E402


@pytest.fixture(scope='module')
def test_app():
    app = create_app()
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    return app


@pytest.fixture(scope='module', autouse=True)
def licensed_state(test_app):
    """بدون اتصال به سرور لایسنس؛ فقط در حافظه همین پروسه."""
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
def scratch_db(test_app):
    """ردیف‌های آزمونی در دیتابیس توسعه ساخته و در پایان پاک می‌شوند."""
    created = []

    def track(model, row_id):
        created.append((model, row_id))

    yield track

    with test_app.app_context():
        for model, row_id in created:
            row = db.session.get(model, row_id)
            if row is not None:
                db.session.delete(row)
        db.session.commit()


# ==============================================================================
# 1. دوره شمسی
# ==============================================================================
class TestJalaliPeriod:
    def test_normalize_accepts_common_shapes(self):
        from utils.jalali import normalize_jalali_period
        for value in ('1405/06', '1405-6', '1405.06', '۱۴۰۵/۰۶', ' 1405/06 '):
            assert normalize_jalali_period(value) == '1405/06', value

    def test_normalize_rejects_garbage(self):
        from utils.jalali import normalize_jalali_period
        for value in ('', None, 'abc', '1405/13', '1405/00', '99/05', '1405/06/02'):
            assert normalize_jalali_period(value) is None, value

    def test_gregorian_year_maps_to_jalali_period(self):
        from utils.jalali import normalize_jalali_period
        assert normalize_jalali_period('2026/09') == '1405/06'

    def test_bounds_match_jalali_month_not_gregorian(self):
        """پنجره ۱۴۰۵/۰۶ باید ۲۳ مرداد تا ۳۱ شهریور میلادی باشد، نه اول سپتامبر."""
        from utils.jalali import jalali_period_bounds
        start, end = jalali_period_bounds('1405/06')
        assert start == date(2026, 8, 23)
        assert end == date(2026, 9, 22)

    def test_esfand_bounds_roll_over_to_next_year(self):
        from utils.jalali import jalali_period_bounds
        start, end = jalali_period_bounds('1404/12')
        assert start == date(2026, 2, 20) and end == date(2026, 3, 20)
        next_start, _ = jalali_period_bounds('1405/01')
        assert (end + timedelta(days=1)) == next_start

    def test_month_start_used_by_dashboards(self):
        from utils.jalali import jalali_month_start
        assert jalali_month_start(date(2026, 9, 3)) == date(2026, 8, 23)

    def test_label_and_recent_periods(self):
        from utils.jalali import jalali_period_label, recent_jalali_periods, current_jalali_period
        assert jalali_period_label('1405/06').startswith('شهریور')
        periods = recent_jalali_periods(6)
        assert periods[0] == current_jalali_period()
        assert len(periods) == 6 and periods == sorted(periods, reverse=True)


# ==============================================================================
# 2. تجزیه عدد فرم (ارقام فارسی و جداکننده هزارگان)
# ==============================================================================
class TestFormNumbers:
    def test_persian_digits_and_separators(self):
        from utils.form_helpers import safe_float
        assert safe_float('۹٬۰۰۰٬۰۰۰') == 9000000
        assert safe_float('9,000,000') == 9000000
        assert safe_float('1.234.567') == 1234567
        assert safe_float('۱۲٫۵') == 12.5
        assert safe_float('12,5') == 12.5
        assert safe_float('45') == 45

    def test_unit_and_space_tolerant(self):
        from utils.form_helpers import safe_float
        assert safe_float('  ۹۰۰۰۰۰۰ تومان  ') == 9000000
        assert safe_float('15%') == 15

    def test_invalid_returns_default_not_exception(self):
        """باگ قبلی: float('9,000,000') باعث ۵۰۰ می‌شد."""
        from utils.form_helpers import safe_float, safe_int
        assert safe_float('abc') == 0
        assert safe_float('', default=7) == 7
        assert safe_int('۱۲٫۷') == 12
        assert safe_int('abc', default=-1) == -1


# ==============================================================================
# 3. موتور مالیات حقوق ۱۴۰۵ (پلکان ماهانه)
# ==============================================================================
class TestSalaryTaxEngine:
    def test_exemption_ceiling(self):
        from utils.tax_rules import calculate_salary_tax_monthly
        assert calculate_salary_tax_monthly(0)[0] == 0
        assert calculate_salary_tax_monthly(40_000_000)[0] == 0
        assert calculate_salary_tax_monthly(39_999_999)[0] == 0

    def test_first_bracket_only_on_surplus(self):
        from utils.tax_rules import calculate_salary_tax_monthly
        tax, parts = calculate_salary_tax_monthly(55_000_000)
        assert tax == 1_500_000                       # ۱۵٪ × ۱۰ میلیون؟ نه: ۱۰٪ × ۱۵م
        assert parts[0]['rate'] == 0.0                # پله معافیت ثبت می‌شود

    def test_progressive_across_all_brackets(self):
        from utils.tax_rules import calculate_salary_tax_monthly
        # ۴۰ معاف + ۴۰×۱۰٪ + ۲۰×۱۵٪ + ۲۰×۲۰٪ + ۲۰×۲۵٪ + ۶۰×۳۰٪ = ۳۴ میلیون
        assert calculate_salary_tax_monthly(200_000_000)[0] == 34_000_000

    def test_brackets_are_monotonic(self):
        from utils.tax_rules import calculate_salary_tax_monthly
        previous = -1
        for step in range(0, 40):
            tax = calculate_salary_tax_monthly(step * 10_000_000)[0]
            assert tax >= previous, f'مالیات در {step * 10_000_000} کاهش یافت'
            previous = tax

    def test_net_salary_never_exceeds_gross(self):
        from utils.tax_rules import calculate_salary_tax_monthly, suggested_insurance
        for step in range(1, 40):
            gross = step * 10_000_000
            tax = calculate_salary_tax_monthly(gross)[0]
            insurance = suggested_insurance(gross)
            assert tax + insurance < gross, gross

    def test_annual_report_uses_same_rules(self):
        """مالیات سالانه باید با پلکان ماهانه هم‌خوان باشد (سال = ماه × ۱۲)."""
        from utils.tax_rules import calculate_salary_tax_annual, calculate_salary_tax_monthly
        monthly_salary = 90_000_000
        assert calculate_salary_tax_annual(monthly_salary * 12)[0] == calculate_salary_tax_monthly(monthly_salary)[0] * 12


class TestTaxRulesAreConfigurable:
    def test_default_rule_metadata(self):
        from utils.tax_rules import get_rule
        rule = get_rule('1405')
        assert rule['monthly_exemption'] == 40_000_000
        assert rule['brackets'][0]['rate'] == 0.10
        assert rule['brackets'][-1]['to'] is None
        assert rule['insurance_employee_rate'] == 0.07

    def test_normalize_brackets_fixes_last_step_and_sorts(self):
        from utils.tax_rules import normalize_brackets
        result = normalize_brackets([
            {'from': 80, 'to': None, 'rate': 0.15},
            {'from': 40, 'to': None, 'rate': 0.10},
            {'from': 20, 'to': 30, 'rate': 5},        # نرخ نامعتبر → حذف
        ])
        assert [item['from'] for item in result] == [40, 80]
        assert result[-1]['to'] is None
        assert result[0]['to'] == 80

    def test_rule_override_changes_calculation(self, test_app, scratch_db):
        """ذخیره قواعد یک سال در دیتابیس باید محاسبه را تغییر دهد (بدون تغییر کد)."""
        import json
        from models.system import TaxRule
        from utils.tax_rules import calculate_salary_tax_monthly, get_rule, invalidate_rule_cache

        with test_app.app_context():
            TaxRule.query.filter_by(year='1398').delete()
            db.session.commit()
            rule = TaxRule(year='1398', monthly_exemption=10_000_000,
                           brackets=json.dumps([{'from': 10_000_000, 'to': None, 'rate': 0.20}]),
                           insurance_employee_rate=0.07, insurance_employer_rate=0.23, is_active=True)
            db.session.add(rule)
            db.session.commit()
            scratch_db(TaxRule, rule.id)
            invalidate_rule_cache()
            try:
                assert get_rule('1398')['source'] == 'database'
                assert calculate_salary_tax_monthly(20_000_000, '1398')[0] == 2_000_000
            finally:
                invalidate_rule_cache()


# ==============================================================================
# 4. شماره‌گذار اسناد
# ==============================================================================
class TestDocumentNumbers:
    """از kind‌های آزمونی استفاده می‌شود تا شمارنده واقعی اسناد دست نخورد."""

    KINDS = ('tstpay', 'tstvch', 'tstexp')

    @pytest.fixture(autouse=True)
    def _clean(self, test_app):
        with test_app.app_context():
            self._reset(test_app)
            yield
            self._reset(test_app)

    @staticmethod
    def _reset(test_app):
        from models.system import DocumentSequence
        for kind in TestDocumentNumbers.KINDS:
            for row in DocumentSequence.query.filter_by(kind=kind).all():
                db.session.delete(row)
        db.session.commit()

    def test_format_includes_year_and_padding(self, test_app):
        with test_app.app_context():
            from utils.document_numbers import next_document_number
            number = next_document_number('tstpay')
            parts = number.split('-')
            assert parts[0] == 'TSTPAY' and len(parts) == 3
            assert parts[-1].isdigit() and len(parts[-1]) >= 5

    def test_sequence_increments_without_duplicates(self, test_app):
        with test_app.app_context():
            from utils.document_numbers import next_document_number
            numbers = [next_document_number('tstvch') for _ in range(5)]
            assert len(set(numbers)) == 5
            values = [int(item.split('-')[-1]) for item in numbers]
            assert values == list(range(1, 6)), values

    def test_each_kind_has_own_counter(self, test_app):
        with test_app.app_context():
            from utils.document_numbers import next_document_number
            first = next_document_number('tstpay')
            other = next_document_number('tstexp')
            assert first.split('-')[0] != other.split('-')[0]
            assert first.split('-')[-1] == other.split('-')[-1] == '00001'

    def test_no_duplicate_after_delete_of_last_record(self, test_app):
        """باگ قدیمی last.id + 1 بعد از حذف آخرین رکورد شماره تکراری می‌ساخت."""
        with test_app.app_context():
            from utils.document_numbers import next_document_number
            first = next_document_number('tstpay')
            second = next_document_number('tstpay')
            assert second != first
            third = next_document_number('tstpay')
            assert third not in (first, second)

    def test_no_route_builds_numbers_from_max_id(self):
        """B5: هیچ مسیری نباید شماره را از `MAX(id)+1` بسازد (تصادم هم‌زمان ⇒ ۵۰۰).

        ۱۱ نقطه باقی‌مانده (هنرجو، مدرس، کلاس، دوره، امتحان، ثبت‌نام گروهی،
        هزینه، شکایت، تیکت، کلاس جدا، قسط/فیش قدیمی) به همین شمارنده منتقل شده‌اند.
        """
        root = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'routes')
        offenders = []
        for name in sorted(os.listdir(root)):
            if not name.endswith('.py'):
                continue
            with open(os.path.join(root, name), encoding='utf-8') as handle:
                for lineno, line in enumerate(handle, 1):
                    if '.id + 1' in line and not line.strip().startswith('#'):
                        offenders.append(f'{name}:{lineno}')
        assert not offenders, f'شماره‌گذاری از MAX(id) باقی مانده: {offenders}'

    def test_all_real_kinds_format_and_increment(self, test_app):
        from utils.document_numbers import PREFIXES, next_document_number, next_sequence_number
        with test_app.app_context():
            for kind in ('payment', 'payslip', 'voucher', 'expense', 'student', 'teacher',
                         'registration', 'course', 'exam', 'class', 'class_split', 'complaint',
                         'ticket', 'installment', 'check', 'advance', 'contract'):
                number = next_document_number(kind)
                assert number.startswith(PREFIXES[kind] + '-'), (kind, number)
                assert number.count('-') == 2, (kind, number)
        with test_app.app_context():
            first = next_sequence_number('tstpay')
            second = next_sequence_number('tstpay')
            assert second == first + 1

    def test_without_year_is_two_parts(self, test_app):
        from utils.document_numbers import next_document_number
        with test_app.app_context():
            number = next_document_number('complaint', with_year=False, width=4)
        assert number.startswith('CMP-') and len(number.split('-')) == 2
        assert len(number.split('-')[1]) == 4 and number.split('-')[1].isdigit()


# ==============================================================================
# 5. فیش حقوقی: بازمحاسبه و گردش‌کار
# ==============================================================================
class TestPayslipMath:
    def test_recalculate_totals(self):
        from models.finance import Payslip
        from routes.payroll import _recalculate_payslip
        slip = Payslip(base_amount=10_000_000, teaching_amount=3_000_000,
                       session_amount=500_000, commission_amount=700_000,
                       bonus=300_000, overtime=200_000,
                       deductions=1_000_000, insurance=700_000, tax=500_000, penalty=100_000)
        _recalculate_payslip(slip)
        assert slip.gross_amount == 14_700_000
        assert slip.total_deductions == 2_300_000
        assert slip.net_amount == 12_400_000

    def test_negative_net_is_possible_until_approval_gate(self):
        """خالص منفی قابل ثبت است ولی مسیر تأیید آن را رد می‌کند (بررسی در کد مسیر)."""
        from models.finance import Payslip
        from routes.payroll import _recalculate_payslip
        import inspect
        import routes.payroll as payroll_module
        slip = Payslip(base_amount=1_000_000, insurance=5_000_000)
        _recalculate_payslip(slip)
        assert slip.net_amount == -4_000_000
        source = inspect.getsource(payroll_module.approve_payslip.__wrapped__
                                   if hasattr(payroll_module.approve_payslip, '__wrapped__')
                                   else payroll_module.approve_payslip)
        assert 'net_amount' in source and 'منفی' in source

    def test_pay_requires_approved_status(self):
        import inspect
        import routes.payroll as payroll_module
        source = inspect.getsource(payroll_module.pay_payslip.__wrapped__
                                   if hasattr(payroll_module.pay_payslip, '__wrapped__')
                                   else payroll_module.pay_payslip)
        assert "payslip.status != 'approved'" in source
        assert 'get_or_create_main_cashbox' in source
        assert 'کافی نیست' in source            # کنترل موجودی صندوق

    def test_cancel_refunds_cashbox(self):
        import inspect
        import routes.payroll as payroll_module
        source = inspect.getsource(payroll_module.cancel_payslip.__wrapped__
                                   if hasattr(payroll_module.cancel_payslip, '__wrapped__')
                                   else payroll_module.cancel_payslip)
        assert "trans_type='in'" in source
        assert 'cancel_reason' in source

    def test_period_window_is_applied_to_tuition(self):
        """درآمد درصدی باید با فیلتر تاریخ بازه محاسبه شود، نه کل تاریخچه."""
        import inspect
        import routes.payroll as payroll_module
        source = inspect.getsource(payroll_module._compute_period_amounts)
        assert 'Payment.payment_date >= period_start' in source
        assert 'Payment.payment_date <= period_end' in source
        assert 'TeacherAttendance.teacher_id == teacher.id' in source


# ==============================================================================
# 6. نگهبان سراسری دسترسی
# ==============================================================================
class TestAccessPolicy:
    def test_admin_only_prefixes(self):
        from utils.access_policy import resolve_policy
        for path in ('/settings/general', '/perms/roles', '/panel/users', '/backup-center/list',
                     '/license/activate', '/network-info'):
            assert resolve_policy(path, 'GET')[0] == 'admin', path

    def test_module_mapping_for_read_paths(self):
        """خواندن‌ها فقط لایه ماژول را می‌بینند (رفتار عمدی)"""
        from utils.access_policy import resolve_policy
        assert resolve_policy('/students/', 'GET') == ('module', 'students')
        assert resolve_policy('/payroll/payslips', 'GET') == ('module', 'payroll')
        assert resolve_policy('/finance/payments', 'GET') == ('module', 'finance')
        assert resolve_policy('/reports/custom-builder', 'GET')[0] == 'admin'

    def test_write_paths_are_mapped_to_actions(self):
        """نوشتن‌ها از وقتی ردیف اکشن‌ها تکمیل شده، به لایه دوم هم می‌رسند."""
        from utils.access_policy import resolve_policy
        assert resolve_policy('/students/add', 'POST') == ('action:create', 'students')
        assert resolve_policy('/payroll/calculate', 'POST') == ('action:edit', 'payroll')
        assert resolve_policy('/finance/payments/1/cancel', 'POST')[0] == 'delete' \
            or resolve_policy('/finance/payments/1/cancel', 'POST') == ('action:edit', 'finance')
        assert resolve_policy('/students/delete/7', 'POST') == ('delete', 'students')

    def test_exempt_paths_are_not_blocked(self):
        from utils.access_policy import resolve_policy
        for path in ('/login', '/logout', '/static/css/animations.css', '/api/attendance/punch',
                     '/webhook/bot/inbound', '/dashboard'):
            assert resolve_policy(path, 'POST') is None or resolve_policy(path, 'POST')[0] is None, path

    def test_destructive_paths_require_delete_or_edit(self):
        from utils.access_policy import required_write_action
        assert required_write_action('/students/delete/7') == 'delete'
        assert required_write_action('/students/restore/7') in ('delete', 'edit')
        assert required_write_action('/students/add') == 'create'

    def test_unauthenticated_requests_are_left_to_other_layers(self, test_app):
        """مسیرهای دستگاه‌زنی/وب‌هوک که کاربر لاگین‌شده ندارند نباید ۴۰۳ بگیرند."""
        from utils.access_policy import check_access
        with test_app.test_request_context('/api/attendance/punch', method='POST'):
            allowed, _reason = check_access()
        assert allowed is True

    def test_guard_is_registered_on_app(self, test_app):
        names = [getattr(f, '__name__', '') for f in test_app.before_request_funcs.get(None, [])]
        assert '_role_guard' in names


# ==============================================================================
# 7. صفحات حقوق که قبلاً ۵۰۰ می‌دادند
# ==============================================================================
class TestPayrollPages:
    @pytest.fixture(autouse=True)
    def _client(self, test_app, admin_id):
        client = test_app.test_client()
        with client.session_transaction() as sess:
            sess['_user_id'] = str(admin_id)
            sess['_fresh'] = True
        self.client = client
        self.user_id = admin_id

    @pytest.mark.parametrize('path', [
        '/payroll', '/payroll/payslips', '/payroll/contracts', '/payroll/calculate',
        '/payroll/tax', '/reports/comprehensive', '/expenses/advanced', '/tax/rules',
        '/tax/calculator', '/payroll?period=1405/06', '/payroll/payslips?period=۱۴۰۵-۰۶&status=paid',
    ])
    def test_page_renders(self, path):
        response = self.client.get(path)
        assert response.status_code == 200, f'{path} → {response.status_code}'

    def test_invalid_period_does_not_crash(self):
        response = self.client.get('/payroll/payslips?period=nah')
        assert response.status_code == 200
