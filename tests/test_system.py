"""
Academy Manager Pro - Comprehensive Architectural Test Suite
Deterministic Verification for All Critical Paths, Edge Cases, and Invariants
"""
import pytest
from datetime import date, datetime
from decimal import Decimal
from app import create_app
from extensions import db
from models.user import User, Role, Permission, RolePermission
from models.system import SystemSettings, Branch
from models.student import Student
from models.teacher import Teacher
from models.course import Course, Field, CertificateTemplate, Certificate, Room
from models.classes import ClassGroup, ClassSession
from models.registration import Registration, Installment
from models.attendance import Attendance
from models.exam import Exam, QuestionBank, ExamQuestion, ExamResult, Grade
from models.accounting import AccountGroup, Account, SubAccount, DetailAccount, JournalEntry, JournalItem, FiscalPeriod
from models.finance import Cashbox, BankAccount, Payment, Check
from utils.jalali import (
    jalali_to_gregorian,
    gregorian_to_jalali,
    parse_jalali_date,
    today_jalali,
    jalali_month_name,
    jalali_weekday_name
)
from utils.sms_service import normalize_iran_mobile, send_sms


@pytest.fixture(scope='module')
def test_app():
    app = create_app()
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    return app


@pytest.fixture(scope='module', autouse=True)
def licensed_state(test_app):
    """
    آزمون‌ها نباید به سرور لایسنس وصل شوند؛ یک وضعیت معتبر
    فقط در حافظه‌ی همین پروسه تزریق می‌شود (نه روی دیسک و نه در بیلد).
    """
    import license_client
    from license_features import AVAILABLE_FEATURES

    data = {
        'success': True,
        'status': 'SUCCESS',
        'client_name': 'آموزشگاه آزمون',
        'allowed_features': {item['key']: True for item in AVAILABLE_FEATURES},
    }
    original_refresh = license_client.refresh_state

    def _fake_refresh(*_args, **_kwargs):
        return license_client._store_state(license_client.LicenseState(
            status='SUCCESS', message='', data=data, valid=True, source='online'))

    license_client.refresh_state = _fake_refresh
    _fake_refresh()
    yield
    license_client.refresh_state = original_refresh
    license_client._store_state(None)


@pytest.fixture(scope='module')
def test_client(test_app):
    return test_app.test_client()


# ==============================================================================
# 1. Jalali Date Engine Tests (ISO & Edge Cases)
# ==============================================================================
class TestJalaliEngine:
    def test_known_gregorian_to_jalali_mapping(self):
        # 2026-03-21 is 1405/01/01 (Nowruz)
        g_date = date(2026, 3, 21)
        j_str = gregorian_to_jalali(g_date)
        assert j_str == '1405/01/01'

    def test_known_jalali_to_gregorian_mapping(self):
        g_date = jalali_to_gregorian(1405, 1, 1)
        assert g_date == date(2026, 3, 21)

    def test_persian_digit_normalization_in_parser(self):
        # Persian digits: ۱۴۰۵/۰۱/۱۶
        parsed = parse_jalali_date('۱۴۰۵/۰۱/۱۶')
        assert parsed is not None
        assert parsed == date(2026, 4, 5)

    def test_iso_date_string_parser(self):
        parsed = parse_jalali_date('2026-04-05')
        assert parsed == date(2026, 4, 5)

    def test_invalid_date_strings_safe_none(self):
        assert parse_jalali_date('') is None
        assert parse_jalali_date(None) is None
        assert parse_jalali_date('invalid-date') is None
        assert parse_jalali_date('9999/99/99') is None

    def test_month_and_weekday_names(self):
        assert jalali_month_name(1) == 'فروردین'
        assert jalali_month_name(12) == 'اسفند'
        assert jalali_month_name(13) == ''
        assert jalali_weekday_name(0) == 'شنبه'
        assert jalali_weekday_name(6) == 'جمعه'


# ==============================================================================
# 2. SMS Normalization Tests
# ==============================================================================
class TestSMSNormalization:
    def test_standard_iran_mobile(self):
        assert normalize_iran_mobile('09123456789') == '09123456789'

    def test_with_international_prefix_plus98(self):
        assert normalize_iran_mobile('+989123456789') == '09123456789'

    def test_with_prefix_0098(self):
        assert normalize_iran_mobile('00989123456789') == '09123456789'

    def test_without_leading_zero(self):
        assert normalize_iran_mobile('9123456789') == '09123456789'

    def test_persian_unicode_digits_mobile(self):
        assert normalize_iran_mobile('۰۹۱۲۳۴۵۶۷۸۹') == '09123456789'

    def test_invalid_mobile_formats(self):
        assert normalize_iran_mobile('12345') is None
        assert normalize_iran_mobile('02112345678') is None
        assert normalize_iran_mobile(None) is None


# ==============================================================================
# 3. Double-Entry Accounting Invariants
# ==============================================================================
class TestAccountingInvariants:
    def test_double_entry_balance_invariant(self, test_app):
        with test_app.app_context():
            # Create account group if needed
            group = AccountGroup.query.filter_by(code='TEST-1').first()
            if not group:
                group = AccountGroup(code='TEST-1', name='دارایی‌های تست', account_type='asset')
                db.session.add(group)
                db.session.commit()

            # Create Asset & Revenue accounts
            acc_cash = Account.query.filter_by(code='TEST-101').first()
            if not acc_cash:
                acc_cash = Account(code='TEST-101', name='صندوق تست', group_id=group.id, account_type='asset', nature='debit')
                db.session.add(acc_cash)

            acc_rev = Account.query.filter_by(code='TEST-401').first()
            if not acc_rev:
                acc_rev = Account(code='TEST-401', name='درآمد شهریه تست', group_id=group.id, account_type='revenue', nature='credit')
                db.session.add(acc_rev)
            db.session.commit()

            # Create Balanced Journal Entry
            import random
            entry_num = f'JRN-{random.randint(100000, 999999)}'
            entry = JournalEntry(
                entry_number=entry_num,
                entry_date=date.today(),
                entry_type='income',
                description='ثبت آزمایشی درآمد نقدی',
                status='approved'
            )
            db.session.add(entry)
            db.session.flush()

            # Item 1: Debit Cash 500,000
            item1 = JournalItem(entry_id=entry.id, account_id=acc_cash.id, debit=500000.0, credit=0.0, row_number=1)
            # Item 2: Credit Tuition 500,000
            item2 = JournalItem(entry_id=entry.id, account_id=acc_rev.id, debit=0.0, credit=500000.0, row_number=2)
            db.session.add_all([item1, item2])
            db.session.commit()

            # Assert Total Invariant
            assert entry.calculate_totals() is True
            assert entry.total_debit == 500000.0
            assert entry.total_credit == 500000.0


# ==============================================================================
# 4. RBAC & Permissions Integrity
# ==============================================================================
class TestAccessControl:
    def test_admin_has_full_access(self, test_app):
        with test_app.app_context():
            admin_user = User.query.filter_by(is_admin=True).first()
            if not admin_user:
                admin_user = User(username='test_admin', full_name='Test Admin', is_admin=True, is_active=True)
                admin_user.set_password('Admin@123')
                db.session.add(admin_user)
                db.session.commit()

            assert admin_user.is_admin is True
            assert admin_user.has_permission('accounting', 'delete') is True
            assert admin_user.has_permission('finance', 'create') is True

    def test_role_based_permission_check(self, test_app):
        with test_app.app_context():
            role = Role.query.filter_by(name='تست منشی').first()
            if not role:
                role = Role(name='تست منشی', description='نقش آزمایشی', is_admin=False)
                db.session.add(role)
                db.session.commit()

            perm = Permission.query.filter_by(module='students', action='view').first()
            if not perm:
                perm = Permission(module='students', action='view', description='مشاهده هنرجویان')
                db.session.add(perm)
                db.session.commit()

            rp = RolePermission.query.filter_by(role_id=role.id, permission_id=perm.id).first()
            if not rp:
                rp = RolePermission(role_id=role.id, permission_id=perm.id)
                db.session.add(rp)
                db.session.commit()

            user = User.query.filter_by(username='test_secretary').first()
            if not user:
                user = User(
                    username='test_secretary',
                    full_name='منشی آزمایشی',
                    is_admin=False,
                    is_active=True,
                    role_id=role.id
                )
                user.set_password('Sec@123')
                db.session.add(user)
                db.session.commit()

            assert user.has_permission('students', 'view') is True
            assert user.has_permission('accounting', 'delete') is False


# ==============================================================================
# 5. Core Endpoints HTTP Response Tests
# ==============================================================================
class TestEndpoints:
    def test_login_page_renders_200(self, test_client):
        response = test_client.get('/login')
        assert response.status_code == 200
        assert b'<!DOCTYPE html>' in response.data or b'<html' in response.data

    def test_unauthenticated_dashboard_redirects_to_login(self, test_client):
        response = test_client.get('/')
        assert response.status_code in (302, 301)
        assert '/login' in response.headers.get('Location', '')

    def test_authenticated_dashboard_renders_200(self, test_app, test_client):
        with test_app.app_context():
            admin = User.query.filter_by(is_admin=True, is_active=True).first()
            with test_client.session_transaction() as sess:
                sess['_user_id'] = str(admin.id)
                sess['_fresh'] = True

            response = test_client.get('/')
            assert response.status_code == 200

# ==============================================================================
# 6. Education & Financial Lifecycle Tests
# ==============================================================================
class TestEducationAndFinance:
    def test_student_and_registration_lifecycle(self, test_app):
        with test_app.app_context():
            import random
            rand_code = random.randint(10000, 99999)
            
            # 1. Create Student
            student = Student(
                student_code=f'STU-{rand_code}',
                national_code=f'{rand_code}12345'[:10],
                first_name='علی',
                last_name=f'تست‌پور_{rand_code}',
                mobile='09121112233',
                status='active'
            )
            db.session.add(student)
            db.session.commit()
            assert student.id is not None
            assert student.full_name == f'علی تست‌پور_{rand_code}'

            # 2. Create Course & Class
            field = Field.query.first()
            if not field:
                field = Field(name='فناوری اطلاعات', code='IT-01')
                db.session.add(field)
                db.session.commit()

            course = Course.query.filter_by(code=f'CRS-{rand_code}').first()
            if not course:
                course = Course(
                    code=f'CRS-{rand_code}',
                    title='دوره پایتون جامع',
                    field_id=field.id,
                    base_fee=3500000.0,
                    duration_hours=40
                )
                db.session.add(course)
                db.session.commit()

            cls = ClassGroup(
                class_code=f'CLS-{rand_code}',
                name='کلاس بهار پایتون',
                course_id=course.id,
                max_capacity=15,
                status='active',
                start_date=date.today()
            )
            db.session.add(cls)
            db.session.commit()

            # 3. Register Student in Class
            reg = Registration(
                reg_code=f'REG-{rand_code}',
                student_id=student.id,
                course_id=course.id,
                class_id=cls.id,
                base_fee=3500000.0,
                total_fee=3500000.0,
                paid_amount=1000000.0,
                remaining_amount=2500000.0,
                status='active'
            )
            db.session.add(reg)
            cls.current_count = 1
            db.session.commit()

            # Add corresponding payment for financial consistency
            payment = Payment(
                receipt_no=f'RCP-{rand_code}',
                student_id=student.id,
                registration_id=reg.id,
                amount=1000000.0,
                payment_method='cash',
                status='confirmed'
            )
            db.session.add(payment)
            db.session.commit()

            assert reg.id is not None
            assert reg.remaining_amount == 2500000.0

            # 4. Create Installments
            inst1 = Installment(
                registration_id=reg.id,
                installment_number=1,
                amount=1250000.0,
                due_date=date.today(),
                status='pending'
            )
            inst2 = Installment(
                registration_id=reg.id,
                installment_number=2,
                amount=1250000.0,
                due_date=date.today(),
                status='pending'
            )
            db.session.add_all([inst1, inst2])
            db.session.commit()

            assert reg.installments.count() == 2

            # 5. Create Session & Attendance
            session = ClassSession(
                class_id=cls.id,
                session_number=1,
                session_date=date.today(),
                status='completed'
            )
            db.session.add(session)
            db.session.commit()

            att = Attendance(
                session_id=session.id,
                student_id=student.id,
                status='present'
            )
            db.session.add(att)
            db.session.commit()

            assert att.status == 'present'

            # Cleanup test artifacts
            db.session.delete(att)
            db.session.delete(session)
            db.session.delete(inst1)
            db.session.delete(inst2)
            db.session.delete(payment)
            db.session.delete(reg)
            db.session.delete(cls)
            db.session.delete(course)
            db.session.delete(student)
            db.session.commit()


# ==============================================================================
# 12. Unified Reporting Catalogue Integration
# ==============================================================================
class TestUnifiedReportingIntegration:
    def test_direct_fiscal_period_selection_supplies_its_jalali_range(self, test_app):
        from routes.reports import _report_filters
        from utils.reporting import REPORT_CATALOG

        with test_app.app_context():
            period = FiscalPeriod(name='دوره آزمون گزارش',
                                  start_date=date(2026, 3, 21),
                                  end_date=date(2027, 3, 20))
            db.session.add(period)
            db.session.commit()

            class AdminScope:
                is_admin = True
                branch_id = None

            filters = _report_filters(
                REPORT_CATALOG['journal'],
                {'fiscal_id': str(period.id), 'date_from': '', 'date_to': ''},
                AdminScope(),
            )
            assert filters.date_from == period.start_date
            assert filters.date_to == period.end_date
            as_of = _report_filters(
                REPORT_CATALOG['receivables-aging'],
                {'date_from': '1405/01/01', 'date_to': '1405/06/11'},
                AdminScope(),
            )
            assert as_of.date_from is None
            assert as_of.date_to == date(2026, 9, 2)
            db.session.delete(period)
            db.session.commit()

    def test_report_filter_contract_drops_unsupported_fields_and_bounds_bad_dates(self, test_app):
        from routes.reports import _report_filters
        from utils.reporting import REPORT_CATALOG

        class AdminScope:
            is_admin = True
            branch_id = None

        with test_app.app_context():
            journal = _report_filters(
                REPORT_CATALOG['journal'],
                {'date_from': 'not-a-date', 'date_to': '۱۴۰۵/۱۳/۴۰',
                 'student_id': '999', 'compare': 'previous'},
                AdminScope(),
            )
            assert journal.date_from is not None
            assert journal.date_to is not None
            assert journal.student_id is None
            assert journal.compare == 'previous'

            capacity = _report_filters(
                REPORT_CATALOG['class-capacity'],
                {'date_from': '1405/01/01', 'date_to': '1405/02/01',
                 'student_id': '999', 'compare': 'year'},
                AdminScope(),
            )
            assert capacity.date_from is None and capacity.date_to is None
            assert capacity.student_id is None and capacity.compare == ''

    def test_aging_keeps_old_open_debt_in_current_year_as_of_report(self, test_app):
        """The range start must not hide an older registration that is still unpaid."""
        from uuid import uuid4
        from utils.reporting import ReportFilters, run_report

        token = uuid4().hex[:10]
        with test_app.app_context(), test_app.test_request_context('/'):
            field = Field(name='رشته آزمون مطالبات', code=f'AF-{token}')
            db.session.add(field)
            db.session.flush()
            course = Course(title='دوره آزمون مطالبات', code=f'AC-{token}',
                            field_id=field.id)
            student = Student(student_code=f'AS-{token}', first_name='هنرجوی',
                              last_name='مطالبه قدیمی', mobile='09120000000')
            db.session.add_all([course, student])
            db.session.flush()
            registration = Registration(
                reg_code=f'AR-{token}', student_id=student.id, course_id=course.id,
                registration_date=date(2025, 1, 1), total_fee=123456,
                paid_amount=0, remaining_amount=123456, status='active',
            )
            db.session.add(registration)
            db.session.flush()
            installment = Installment(
                registration_id=registration.id, installment_number=1,
                amount=123456, due_date=date(2025, 2, 1), status='overdue',
            )
            db.session.add(installment)
            db.session.commit()

            filters = ReportFilters(
                date_from=date(2026, 3, 21), date_to=date(2026, 9, 2),
                student_id=student.id,
            )
            result = run_report('receivables-aging', filters, paginate=False)
            metrics = {item['label']: item['value'] for item in result['kpis']}
            assert metrics['پرونده بدهکار'] == 1
            assert metrics['کل مطالبات'] == 123456
            assert next(row for row in result['rows']
                        if row['bucket'] == 'بیش از ۹۰ روز')['accounts'] == 1

            db.session.delete(installment)
            db.session.delete(registration)
            db.session.delete(student)
            db.session.delete(course)
            db.session.delete(field)
            db.session.commit()

    def test_receivable_as_of_reconstructs_payments_after_the_cutoff(self, test_app):
        from uuid import uuid4
        from utils.reporting import ReportFilters, run_report

        token = uuid4().hex[:10]
        with test_app.app_context(), test_app.test_request_context('/'):
            field = Field(name=f'رشته مانده تاریخی {token}', code=f'HF-{token}')
            branch = Branch(name=f'شعبه مانده تاریخی {token}', code=f'HB-{token}')
            db.session.add_all([field, branch])
            db.session.flush()
            course = Course(title=f'دوره مانده تاریخی {token}', code=f'HC-{token}',
                            field_id=field.id, branch_id=branch.id)
            student = Student(student_code=f'HS-{token}', first_name='هنرجوی',
                              last_name='مانده تاریخی', mobile='09120000005',
                              branch_id=branch.id)
            db.session.add_all([course, student])
            db.session.flush()
            registration = Registration(
                reg_code=f'HR-{token}', student_id=student.id, course_id=course.id,
                registration_date=date(2026, 1, 1), total_fee=1000000,
                paid_amount=1000000, remaining_amount=0, status='active',
                branch_id=branch.id,
            )
            db.session.add(registration)
            db.session.flush()
            installment = Installment(
                registration_id=registration.id, installment_number=1,
                due_date=date(2026, 9, 10), amount=1000000,
                paid_amount=1000000, paid_date=date(2026, 9, 2), status='paid',
            )
            db.session.add(installment)
            db.session.flush()
            payment = Payment(
                receipt_no=f'HP-{token}', student_id=student.id,
                registration_id=registration.id, installment_id=installment.id,
                amount=1000000, payment_method='cash',
                payment_date=date(2026, 9, 2), status='confirmed',
                branch_id=branch.id,
            )
            db.session.add(payment)
            db.session.commit()

            before_payment = run_report('debtors', ReportFilters(
                date_to=date(2026, 9, 1), student_id=student.id,
                branch_id=branch.id,
            ), paginate=False)
            assert before_payment['total_rows'] == 1
            assert before_payment['rows'][0]['paid'] == 0
            assert before_payment['rows'][0]['remaining'] == 1000000
            assert before_payment['rows'][0]['bucket'] == 'سررسیدنشده'

            executive_before = run_report('executive-dashboard', ReportFilters(
                date_from=date(2026, 9, 1), date_to=date(2026, 9, 1),
                branch_id=branch.id,
            ), paginate=False)
            executive_debt = next(
                item['value'] for item in executive_before['kpis']
                if item['label'] == 'مطالبات'
            )
            assert executive_debt == 1000000
            assert next(
                item['value'] for item in executive_before['kpis']
                if item['label'] == 'اقساط معوق'
            ) == 0  # سررسید این قسط هنوز نرسیده است.

            after_payment = run_report('debtors', ReportFilters(
                date_to=date(2026, 9, 3), student_id=student.id,
                branch_id=branch.id,
            ), paginate=False)
            assert after_payment['total_rows'] == 0

            db.session.delete(payment)
            db.session.delete(installment)
            db.session.delete(registration)
            db.session.delete(student)
            db.session.delete(course)
            db.session.delete(field)
            db.session.delete(branch)
            db.session.commit()

    def test_enrollment_cash_trend_and_profitability_use_each_events_own_date(self, test_app):
        """A new payment for an old enrolment belongs to the payment month only."""
        from uuid import uuid4
        from utils.reporting import ReportFilters, run_report

        token = uuid4().hex[:10]
        with test_app.app_context(), test_app.test_request_context('/'):
            field = Field(name=f'رشته تاریخ رویداد {token}', code=f'EF-{token}')
            db.session.add(field)
            db.session.flush()
            course = Course(title=f'دوره تاریخ رویداد {token}', code=f'EC-{token}',
                            field_id=field.id)
            student = Student(student_code=f'ES-{token}', first_name='هنرجوی',
                              last_name='تاریخ رویداد', mobile='09120000003')
            db.session.add_all([course, student])
            db.session.flush()
            registration = Registration(
                reg_code=f'ER-{token}', student_id=student.id, course_id=course.id,
                registration_date=date(2025, 1, 1), total_fee=1000000,
                paid_amount=500000, remaining_amount=500000,
                teacher_payment_amount=400000, status='active',
            )
            db.session.add(registration)
            db.session.flush()
            payment = Payment(
                receipt_no=f'EP-{token}', student_id=student.id,
                registration_id=registration.id, amount=500000,
                payment_method='cash', payment_date=date(2026, 9, 2),
                status='confirmed',
            )
            db.session.add(payment)
            db.session.commit()

            filters = ReportFilters(
                date_from=date(2026, 9, 1), date_to=date(2026, 9, 3),
                course_id=course.id,
            )
            trend = run_report('enrollment-trend', filters, paginate=False)
            assert trend['total_rows'] == 1
            assert trend['rows'][0]['count'] == 0
            assert trend['rows'][0]['fee'] == 0
            assert trend['rows'][0]['paid'] == 500000

            profitability = run_report('course-profitability', filters, paginate=False)
            row = next(item for item in profitability['rows'] if item['code'] == course.code)
            assert row['registrations'] == 0
            assert row['contract_value'] == 0
            assert row['revenue'] == 500000
            assert row['direct_cost'] == 0
            assert row['profit'] == 0

            db.session.delete(payment)
            db.session.delete(registration)
            db.session.delete(student)
            db.session.delete(course)
            db.session.delete(field)
            db.session.commit()

    def test_teacher_student_count_uses_status_and_period_overlap(self, test_app):
        from uuid import uuid4
        from utils.reporting import ReportFilters, run_report

        token = uuid4().hex[:10]
        with test_app.app_context(), test_app.test_request_context('/'):
            field = Field(name=f'رشته عملکرد {token}', code=f'TF-{token}')
            db.session.add(field)
            db.session.flush()
            course = Course(title=f'دوره عملکرد {token}', code=f'TC-{token}',
                            field_id=field.id)
            teacher = Teacher(teacher_code=f'TT-{token}', first_name='مدرس',
                              last_name='عملکرد', mobile='09120000004')
            db.session.add_all([course, teacher])
            db.session.flush()
            class_group = ClassGroup(
                class_code=f'TG-{token}', name=f'کلاس عملکرد {token}',
                course_id=course.id, teacher_id=teacher.id,
                start_date=date(2026, 1, 1), end_date=date(2026, 12, 31),
                status='active',
            )
            students = [
                Student(student_code=f'TS{i}-{token}', first_name='هنرجو',
                        last_name=f'عملکرد {i}', mobile=f'0912000010{i}')
                for i in range(3)
            ]
            db.session.add(class_group)
            db.session.add_all(students)
            db.session.flush()
            registrations = [
                Registration(reg_code=f'TR1-{token}', student_id=students[0].id,
                             course_id=course.id, class_id=class_group.id,
                             teacher_id=teacher.id, registration_date=date(2026, 8, 1),
                             status='active', is_reserved=False),
                Registration(reg_code=f'TR2-{token}', student_id=students[1].id,
                             course_id=course.id, class_id=class_group.id,
                             teacher_id=teacher.id, registration_date=date(2026, 8, 1),
                             status='withdrawn', is_reserved=False),
                Registration(reg_code=f'TR3-{token}', student_id=students[2].id,
                             course_id=course.id, class_id=class_group.id,
                             teacher_id=teacher.id, registration_date=date(2026, 10, 1),
                             status='active', is_reserved=False),
            ]
            db.session.add_all(registrations)
            db.session.commit()

            result = run_report('teacher-performance', ReportFilters(
                date_from=date(2026, 9, 1), date_to=date(2026, 9, 30),
                teacher_id=teacher.id, course_id=course.id,
            ), paginate=False)
            row = next(item for item in result['rows'] if item['code'] == teacher.teacher_code)
            assert row['classes'] == 1
            assert row['students'] == 1

            for registration in registrations:
                db.session.delete(registration)
            for student in students:
                db.session.delete(student)
            db.session.delete(class_group)
            db.session.delete(teacher)
            db.session.delete(course)
            db.session.delete(field)
            db.session.commit()

    def test_every_catalogue_report_runs_against_the_application_schema(self, test_app):
        """Catch model/schema drift in any one of the 64 report builders."""
        from utils.reporting import REPORT_CATALOG, ReportFilters, run_report

        with test_app.test_request_context('/'):
            class AdminScope:
                is_admin = True
                branch_id = None

            filters = ReportFilters.from_mapping({'per_page': 10}, AdminScope())
            assert len(REPORT_CATALOG) == 64
            for report_key in REPORT_CATALOG:
                result = run_report(report_key, filters)
                assert result['meta']['key'] == report_key
                assert result['page'] >= 1
                assert result['pages'] >= 1


# ==============================================================================
# 13. Unified Reporting HTTP, Ownership, Branch and Licence Boundaries
# ==============================================================================
class TestUnifiedReportingRoutes:
    @staticmethod
    def _login(client, user_id):
        with client.session_transaction() as session:
            session['_user_id'] = str(user_id)
            session['_fresh'] = True

    @staticmethod
    def _admin():
        user = User.query.filter_by(username='report_route_admin').first()
        if user is None:
            user = User(username='report_route_admin', full_name='مدیر آزمون گزارش',
                        is_admin=True, is_active=True)
            user.set_password('ReportAdmin@123')
            db.session.add(user)
            db.session.commit()
        return user

    @staticmethod
    def _branch_user(branch):
        role = Role.query.filter_by(name='نقش آزمون مرزبندی گزارش').first()
        if role is None:
            role = Role(name='نقش آزمون مرزبندی گزارش', is_admin=False)
            db.session.add(role)
            db.session.flush()
        for module, action in (
            ('reports', 'view'), ('students', 'view'),
            ('registration', 'view'), ('finance', 'view'),
            ('finance', 'create'), ('finance', 'edit'), ('finance', 'delete'),
        ):
            permission = Permission.query.filter_by(module=module, action=action).first()
            if permission is None:
                permission = Permission(module=module, action=action,
                                        description=f'{action} {module}')
                db.session.add(permission)
                db.session.flush()
            exists = RolePermission.query.filter_by(
                role_id=role.id, permission_id=permission.id
            ).first()
            if exists is None:
                db.session.add(RolePermission(role_id=role.id,
                                              permission_id=permission.id))
        user = User.query.filter_by(username='report_branch_user').first()
        if user is None:
            user = User(username='report_branch_user', full_name='کاربر شعبه گزارش',
                        role_id=role.id, branch_id=branch.id,
                        is_admin=False, is_active=True)
            user.set_password('ReportBranch@123')
            db.session.add(user)
        else:
            user.role_id = role.id
            user.branch_id = branch.id
        db.session.commit()
        return user

    def test_centre_builder_api_and_json_export(self, test_app, test_client):
        from models.reporting import ReportExportLog

        with test_app.app_context():
            admin = self._admin()
            admin_id = admin.id
        self._login(test_client, admin_id)

        centre = test_client.get('/reports/')
        assert centre.status_code == 200
        assert 'مرکز جامع گزارش‌ها'.encode() in centre.data
        assert '64 گزارش'.encode() in centre.data

        builder = test_client.get('/reports/builder')
        assert builder.status_code == 200
        assert 'گزارش‌ساز بدون برنامه‌نویسی'.encode() in builder.data

        api = test_client.get('/reports/api/run/journal?per_page=10')
        assert api.status_code == 200
        payload = api.get_json()
        assert payload['meta']['key'] == 'journal'
        assert payload['per_page'] == 10

        exported = test_client.get(
            '/reports/export/executive-dashboard/json?columns=indicator,not_a_column'
        )
        assert exported.status_code == 200
        assert exported.mimetype == 'application/json'
        exported_payload = exported.get_json()
        assert [column['key'] for column in exported_payload['columns']] == ['indicator']

        printable = test_client.get(
            '/reports/view/executive-dashboard?print=1&columns=indicator,status'
        )
        assert printable.status_code == 200
        assert b'data-column="indicator"' in printable.data
        assert b'data-column="area"' not in printable.data
        assert b'data-column="value"' not in printable.data

        with test_app.app_context():
            assert ReportExportLog.query.filter_by(
                user_id=admin_id, report_key='executive-dashboard',
                export_format='json', status='completed'
            ).count() == 1

    def test_global_search_includes_payroll_entities(self, test_app, test_client):
        from models.finance import Payslip
        from uuid import uuid4

        token = uuid4().hex[:10]
        with test_app.app_context():
            admin = self._admin()
            item = Payslip(
                payslip_number=f'PAYROLL-{token}', person_type='employee',
                person_id=987654, period='1405/06', net_amount=123456,
                status='draft',
            )
            db.session.add(item)
            db.session.commit()
            admin_id, item_id = admin.id, item.id
        self._login(test_client, admin_id)

        response = test_client.get(f'/api/search?q={token}&type=payroll')
        assert response.status_code == 200
        results = response.get_json()['results']
        assert any(result['name'] == f'PAYROLL-{token}' for result in results)

        with test_app.app_context():
            db.session.delete(db.session.get(Payslip, item_id))
            db.session.commit()

    def test_print_export_and_automation_honor_granular_report_actions(
            self, test_app, test_client):
        from models.system import Branch

        with test_app.app_context():
            branch = Branch.query.first()
            user = self._branch_user(branch)
            user_id = user.id
        self._login(test_client, user_id)

        report = test_client.get('/reports/view/executive-dashboard')
        assert report.status_code == 200
        assert 'Excel حرفه‌ای'.encode() not in report.data
        assert 'چاپ همه نتایج'.encode() not in report.data
        assert test_client.get(
            '/reports/view/executive-dashboard?print=1'
        ).status_code == 403
        assert test_client.get(
            '/reports/export/executive-dashboard/json'
        ).status_code == 403
        assert test_client.post('/reports/schedules', data={
            'name': 'غیرمجاز', 'report_key': 'executive-dashboard',
        }).status_code == 403

    def test_favorite_writes_are_idempotent(self, test_app, test_client):
        from models.reporting import ReportFavorite

        with test_app.app_context():
            admin = self._admin()
            admin_id = admin.id
            ReportFavorite.query.filter_by(
                user_id=admin_id, report_key='executive-dashboard'
            ).delete(synchronize_session=False)
            db.session.commit()
        self._login(test_client, admin_id)

        first = test_client.post('/reports/api/favorites/executive-dashboard')
        second = test_client.post('/reports/api/favorites/executive-dashboard')
        assert first.status_code == second.status_code == 200
        assert first.get_json()['favorite'] is True
        assert second.get_json()['favorite'] is True
        with test_app.app_context():
            assert ReportFavorite.query.filter_by(
                user_id=admin_id, report_key='executive-dashboard'
            ).count() == 1

        first_delete = test_client.delete('/reports/api/favorites/executive-dashboard')
        second_delete = test_client.delete('/reports/api/favorites/executive-dashboard')
        assert first_delete.get_json()['favorite'] is False
        assert second_delete.get_json()['favorite'] is False

    def test_presets_and_snapshots_are_normalised_and_owner_isolated(
            self, test_app, test_client):
        from models.reporting import ReportPreset, ReportSnapshot

        with test_app.app_context():
            owner = self._admin()
            other = User.query.filter_by(username='report_other_admin').first()
            if other is None:
                other = User(username='report_other_admin', full_name='مدیر دوم گزارش',
                             is_admin=True, is_active=True)
                other.set_password('OtherAdmin@123')
                db.session.add(other)
                db.session.commit()
            owner_id, other_id = owner.id, other.id
        self._login(test_client, owner_id)

        response = test_client.post('/reports/api/presets', json={
            'report_key': 'journal', 'name': 'نمای امن',
            'filters': {'status': 'not-valid', 'q': 'سند آزمون'},
            'columns': ['number', '<script>', 'description'],
        })
        assert response.status_code == 200
        preset_id = response.get_json()['id']
        snapshot_response = test_client.post('/reports/api/snapshots', json={
            'report_key': 'executive-dashboard',
            'title': 'تصویر مدیریتی', 'filters': {},
        })
        assert snapshot_response.status_code == 200
        snapshot_id = snapshot_response.get_json()['id']

        with test_app.app_context():
            import json
            preset = db.session.get(ReportPreset, preset_id)
            assert preset.user_id == owner_id
            assert json.loads(preset.columns_json) == ['number', 'description']
            assert 'status' not in json.loads(preset.filters_json)
            snapshot = db.session.get(ReportSnapshot, snapshot_id)
            assert snapshot.user_id == owner_id
            assert isinstance(json.loads(snapshot.metrics_json), list)

        self._login(test_client, other_id)
        assert test_client.get(f'/reports/presets/{preset_id}/apply').status_code == 404
        assert test_client.get(f'/reports/snapshots/{snapshot_id}/apply').status_code == 404
        assert test_client.delete(f'/reports/api/presets/{preset_id}').status_code == 404

    def test_schedule_input_is_safe_and_owned(self, test_app, test_client):
        from models.reporting import ReportSchedule

        with test_app.app_context():
            admin = self._admin()
            admin_id = admin.id
            before = ReportSchedule.query.filter_by(user_id=admin_id).count()
        self._login(test_client, admin_id)

        response = test_client.post('/reports/schedules', data={
            'name': 'ارسال دوره‌ای امن', 'report_key': 'executive-dashboard',
            'frequency': 'monthly', 'export_format': 'json',
            'delivery_method': 'internal', 'run_date': '2099-01-01',
            'run_time': '08:15',
            'filters': '{"q":"آزمون","columns":["indicator","bad<column"]}',
        })
        assert response.status_code == 302
        with test_app.app_context():
            import json
            schedule = ReportSchedule.query.filter_by(
                user_id=admin_id, name='ارسال دوره‌ای امن'
            ).one()
            saved = json.loads(schedule.filters_json)
            assert saved['columns'] == 'indicator'
            assert saved['q'] == 'آزمون'
            assert schedule.schedule_day is not None
            schedule_id = schedule.id
            assert ReportSchedule.query.filter_by(user_id=admin_id).count() == before + 1

        invalid = test_client.post('/reports/schedules', data={
            'name': 'ایمیل نامعتبر', 'report_key': 'executive-dashboard',
            'delivery_method': 'email', 'recipient': 'not-an-email',
            'run_date': '2099-01-01', 'run_time': '09:00',
        }, headers={'Referer': 'https://attacker.invalid/redirect'})
        assert invalid.status_code == 302
        assert invalid.headers['Location'].endswith('/reports/schedules')
        with test_app.app_context():
            assert ReportSchedule.query.filter_by(
                user_id=admin_id, name='ایمیل نامعتبر'
            ).count() == 0
            other = User.query.filter_by(username='report_other_admin').one()
            other_id = other.id
        self._login(test_client, other_id)
        assert test_client.post(f'/reports/schedules/{schedule_id}/toggle').status_code == 404
        assert test_client.post(f'/reports/schedules/{schedule_id}/delete').status_code == 404

    def test_budget_and_reconciliation_validate_financial_inputs(
            self, test_app, test_client):
        from models.finance import Cashbox, ExpenseCategory
        from models.reporting import AccountReconciliation, ReportBudget
        from uuid import uuid4

        token = uuid4().hex[:8]
        with test_app.app_context():
            admin = self._admin()
            cashbox = Cashbox(name=f'صندوق تطبیق {token}', code=f'RC-{token}',
                              balance=Decimal('1000000'))
            category = ExpenseCategory(name=f'دسته بودجه {token}', code=f'BC-{token}')
            db.session.add_all([cashbox, category])
            db.session.commit()
            admin_id, cashbox_id, category_id = admin.id, cashbox.id, category.id
        self._login(test_client, admin_id)

        valid_budget = test_client.post('/reports/budgets', data={
            'fiscal_year': '۱۴۰۵', 'period': 'quarter', 'period_no': '1',
            'title': f'بودجه آزمون {token}', 'budget_type': 'expense',
            'amount': '۵۰٬۰۰۰٬۰۰۰', 'expense_category_id': str(category_id),
        })
        assert valid_budget.status_code == 302
        invalid_budget = test_client.post('/reports/budgets', data={
            'fiscal_year': '۱۴۰۵', 'period': 'year',
            'title': f'بودجه ناسازگار {token}', 'budget_type': 'revenue',
            'amount': '1000', 'expense_category_id': str(category_id),
        })
        assert invalid_budget.status_code == 302

        reconciliation = test_client.post('/reports/reconciliations', data={
            'account_kind': 'cashbox', 'cashbox_id': str(cashbox_id),
            'reconciliation_date': '۱۴۰۵/۰۶/۱۱',
            'statement_balance': '۱٬۲۵۰٬۰۰۰', 'notes': 'تطبیق آزمون',
        })
        assert reconciliation.status_code == 302
        with test_app.app_context():
            budget = ReportBudget.query.filter_by(title=f'بودجه آزمون {token}').one()
            assert budget.amount == Decimal('50000000.00')
            assert ReportBudget.query.filter_by(title=f'بودجه ناسازگار {token}').count() == 0
            item = AccountReconciliation.query.filter_by(notes='تطبیق آزمون').one()
            assert item.system_balance == Decimal('1000000.00')
            assert item.statement_balance == Decimal('1250000.00')
            assert item.difference == Decimal('250000.00')
            reconciliation_id = item.id

        assert test_client.post(
            f'/reports/reconciliations/{reconciliation_id}/resolve'
        ).status_code == 302
        assert test_client.post(
            f'/reports/reconciliations/{reconciliation_id}/resolve'
        ).status_code == 302
        with test_app.app_context():
            item = db.session.get(AccountReconciliation, reconciliation_id)
            assert item.status == 'resolved'
            assert item.resolved_by == admin_id
            assert item.resolved_at is not None

    def test_budget_actual_keeps_global_and_branch_scopes_distinct(self, test_app):
        from models.finance import Expense, ExpenseCategory
        from models.reporting import ReportBudget
        from utils.reporting import ReportFilters, run_report
        from uuid import uuid4

        token = uuid4().hex[:8]
        with test_app.app_context(), test_app.test_request_context('/'):
            admin = self._admin()
            first = Branch(name=f'بودجه شعبه یک {token}', code=f'BB1-{token}')
            second = Branch(name=f'بودجه شعبه دو {token}', code=f'BB2-{token}')
            category = ExpenseCategory(name=f'بودجه دسته {token}', code=f'BBC-{token}')
            db.session.add_all([first, second, category])
            db.session.flush()
            global_budget = ReportBudget(
                fiscal_year='1405', period='year', title=f'کل سازمان {token}',
                budget_type='expense', amount=1000, expense_category_id=category.id,
                created_by=admin.id,
            )
            branch_budget = ReportBudget(
                fiscal_year='1405', period='year', title=f'شعبه یک {token}',
                budget_type='expense', amount=500, branch_id=first.id,
                expense_category_id=category.id, created_by=admin.id,
            )
            own_expense = Expense(
                expense_number=f'BE1-{token}', category_id=category.id, amount=125,
                expense_date=date(2026, 9, 2), status='confirmed', branch_id=first.id,
            )
            other_expense = Expense(
                expense_number=f'BE2-{token}', category_id=category.id, amount=75,
                expense_date=date(2026, 9, 2), status='confirmed', branch_id=second.id,
            )
            db.session.add_all([global_budget, branch_budget, own_expense, other_expense])
            db.session.commit()

            branch_result = run_report('budget-actual', ReportFilters(
                date_from=date(2026, 9, 1), date_to=date(2026, 9, 3),
                branch_id=first.id, q=token,
            ), paginate=False)
            assert [row['title'] for row in branch_result['rows']] == [f'شعبه یک {token}']
            assert branch_result['rows'][0]['actual'] == 125

            central_result = run_report('budget-actual', ReportFilters(
                date_from=date(2026, 9, 1), date_to=date(2026, 9, 3), q=token,
            ), paginate=False)
            by_title = {row['title']: row for row in central_result['rows']}
            assert by_title[f'کل سازمان {token}']['actual'] == 200
            assert by_title[f'شعبه یک {token}']['actual'] == 125

            for item in (own_expense, other_expense, global_budget, branch_budget,
                         category, first, second):
                db.session.delete(item)
            db.session.commit()

    def test_branch_scope_applies_to_report_api_search_and_reconciliation(
            self, test_app, test_client):
        from models.finance import Cashbox
        from uuid import uuid4

        token = uuid4().hex[:8]
        with test_app.app_context():
            first = Branch(name=f'شعبه یک {token}', code=f'B1-{token}')
            second = Branch(name=f'شعبه دو {token}', code=f'B2-{token}')
            db.session.add_all([first, second])
            db.session.flush()
            own_student = Student(student_code=f'OWN-{token}', first_name='ArenaScope',
                                  last_name=f'Own {token}', mobile='09120000001',
                                  branch_id=first.id)
            other_student = Student(student_code=f'OTHER-{token}', first_name='ArenaScope',
                                    last_name=f'Other {token}', mobile='09120000002',
                                    branch_id=second.id)
            own_box = Cashbox(name=f'صندوق خودی {token}', code=f'CB1-{token}',
                              branch_id=first.id, balance=100)
            other_box = Cashbox(name=f'صندوق دیگری {token}', code=f'CB2-{token}',
                                branch_id=second.id, balance=100)
            global_box = Cashbox(name=f'صندوق سراسری {token}', code=f'CBG-{token}',
                                 branch_id=None, balance=100)
            db.session.add_all([own_student, other_student, own_box, other_box, global_box])
            db.session.flush()
            user = self._branch_user(first)
            db.session.commit()
            user_id, own_code, other_code = user.id, own_student.student_code, other_student.student_code
            own_student_id, other_student_id = own_student.id, other_student.id
            own_box_id, other_box_id = own_box.id, other_box.id
            global_box_id = global_box.id
        self._login(test_client, user_id)

        assert test_client.get(f'/students/{own_student_id}').status_code == 200
        assert test_client.get(f'/students/{other_student_id}').status_code == 404

        report = test_client.get(f'/reports/api/run/students?q={token}')
        assert report.status_code == 200
        report_text = report.get_data(as_text=True)
        assert own_code in report_text
        assert other_code not in report_text

        search = test_client.get(f'/api/search?q={token}&type=students&limit=10')
        assert search.status_code == 200
        names = [item['name'] for item in search.get_json()['results']]
        assert any('Own' in name for name in names)
        assert all('Other' not in name for name in names)

        own = test_client.post('/reports/reconciliations', data={
            'account_kind': 'cashbox', 'cashbox_id': str(own_box_id),
            'reconciliation_date': '1405/06/11', 'statement_balance': '100',
        })
        assert own.status_code == 302
        forbidden = test_client.post('/reports/reconciliations', data={
            'account_kind': 'cashbox', 'cashbox_id': str(other_box_id),
            'reconciliation_date': '1405/06/11', 'statement_balance': '100',
        })
        assert forbidden.status_code == 403
        global_forbidden = test_client.post('/reports/reconciliations', data={
            'account_kind': 'cashbox', 'cashbox_id': str(global_box_id),
            'reconciliation_date': '1405/06/11', 'statement_balance': '100',
        })
        assert global_forbidden.status_code == 403

    def test_scheduler_archives_internal_output_and_failure_artifact(
            self, test_app, monkeypatch):
        from models.reporting import ReportExportLog, ReportSchedule
        from models.system import Notification
        import utils.report_scheduler as scheduler

        with test_app.app_context():
            admin = self._admin()
            next_at = datetime(2099, 1, 1, 8, 0)
            internal = ReportSchedule(
                user_id=admin.id, name='آرشیو داخلی آزمون',
                report_key='executive-dashboard', filters_json='{}',
                export_format='json', frequency='monthly', schedule_day=1,
                delivery_method='internal', next_run_at=next_at,
            )
            db.session.add(internal)
            db.session.commit()
            path = scheduler.deliver_schedule(internal, advance=False)
            assert path.is_file()
            assert internal.last_status == 'completed'
            assert internal.next_run_at == next_at
            completed_log = ReportExportLog.query.filter_by(
                user_id=admin.id, file_name=path.name, status='completed'
            ).one()
            assert completed_log.row_count >= 0
            assert Notification.query.filter_by(
                user_id=admin.id, reference_type='report_export',
                reference_id=completed_log.id
            ).count() == 1

            failing = ReportSchedule(
                user_id=admin.id, name='تحویل ناموفق آزمون',
                report_key='executive-dashboard', filters_json='{}',
                export_format='json', frequency='monthly', schedule_day=1,
                delivery_method='telegram', recipient='12345', next_run_at=next_at,
            )
            db.session.add(failing)
            db.session.commit()

            def fail_delivery(*_args, **_kwargs):
                raise RuntimeError('خطای تحویل کنترل‌شده')

            monkeypatch.setattr(scheduler, '_deliver_bot', fail_delivery)
            with pytest.raises(RuntimeError, match='خطای تحویل کنترل‌شده'):
                scheduler.deliver_schedule(failing, advance=False)
            db.session.refresh(failing)
            assert failing.last_status == 'failed'
            failed_log = ReportExportLog.query.filter_by(
                user_id=admin.id, status='failed',
                error_message='خطای تحویل کنترل‌شده'
            ).order_by(ReportExportLog.id.desc()).first()
            assert failed_log is not None and failed_log.file_name
            failed_path = path.parent / failed_log.file_name
            assert failed_path.is_file()
            path.unlink(missing_ok=True)
            failed_path.unlink(missing_ok=True)

    def test_executive_dashboard_redacts_unpermitted_source_modules(
            self, test_app, test_client):
        from uuid import uuid4

        token = uuid4().hex[:8]
        with test_app.app_context():
            permission = Permission.query.filter_by(module='reports', action='view').first()
            if permission is None:
                permission = Permission(module='reports', action='view',
                                        description='view reports')
                db.session.add(permission)
                db.session.flush()
            role = Role(name=f'نقش فقط گزارش {token}', is_admin=False)
            db.session.add(role)
            db.session.flush()
            db.session.add(RolePermission(role_id=role.id, permission_id=permission.id))
            user = User(username=f'reports_only_{token}', full_name='کاربر فقط گزارش',
                        role_id=role.id, is_admin=False, is_active=True)
            user.set_password('ReportsOnly@123')
            db.session.add(user)
            db.session.commit()
            user_id = user.id

        self._login(test_client, user_id)
        response = test_client.get('/reports/api/run/executive-dashboard')
        assert response.status_code == 200
        payload = response.get_json()
        assert payload['rows'] == []
        assert payload['kpis'] == []
        assert any('دسترسی مشاهده' in warning for warning in payload['warnings'])
        # Composite rankings must not become a side channel into finance,
        # registration, course or student data for a reports-only role.
        assert test_client.get('/reports/api/run/course-ranking').status_code == 403

    def test_source_feature_lock_hides_reports_and_global_search(
            self, test_app, test_client):
        import license_client

        with test_app.app_context():
            admin = self._admin()
            admin_id = admin.id
        self._login(test_client, admin_id)
        old_state = license_client.get_state()
        data = dict(old_state.data)
        features = dict(old_state.allowed_features)
        features['reports'] = True
        features['finance'] = False
        data['allowed_features'] = features
        locked_state = license_client.LicenseState(
            status='SUCCESS', message='', data=data, valid=True, source='online'
        )
        license_client._store_state(locked_state)
        try:
            assert test_client.get('/reports/view/receipts-payments').status_code == 403
            assert test_client.get('/reports/budgets').status_code == 403
            assert test_client.post('/reports/budgets').status_code == 403
            assert test_client.post('/reports/budgets/999/delete').status_code == 403
            assert test_client.get('/reports/reconciliations').status_code == 403
            assert test_client.post('/reports/reconciliations').status_code == 403
            assert test_client.post('/reports/reconciliations/999/resolve').status_code == 403
            centre = test_client.get('/reports/')
            assert centre.status_code == 200
            assert 'دریافت‌ها و پرداخت‌ها'.encode() not in centre.data
            executive = test_client.get('/reports/api/run/executive-dashboard').get_json()
            executive_labels = {item['label'] for item in executive['kpis']}
            assert 'درآمد' not in executive_labels
            assert 'مطالبات' not in executive_labels
            search = test_client.get('/api/search?q=پرداخت&type=finance')
            assert search.status_code == 200
            assert search.get_json()['results'] == []

            installment_features = dict(features)
            installment_features['finance'] = True
            installment_features['installments'] = False
            installment_data = dict(data)
            installment_data['allowed_features'] = installment_features
            license_client._store_state(license_client.LicenseState(
                status='SUCCESS', message='', data=installment_data,
                valid=True, source='online'
            ))
            assert test_client.get(
                '/reports/view/installment-calendar'
            ).status_code == 403
            executive = test_client.get('/reports/api/run/executive-dashboard').get_json()
            executive_labels = {item['label'] for item in executive['kpis']}
            assert 'درآمد' in executive_labels
            assert 'اقساط معوق' not in executive_labels
            centre = test_client.get('/reports/')
            assert 'تقویم وصول اقساط'.encode() not in centre.data
        finally:
            license_client._store_state(old_state)

    def test_export_feature_lock_blocks_downloads_and_new_automation(
            self, test_app, test_client):
        import license_client
        from utils.report_scheduler import run_due_report_schedules

        with test_app.app_context():
            admin = self._admin()
            admin_id = admin.id
        self._login(test_client, admin_id)
        old_state = license_client.get_state()
        data = dict(old_state.data)
        features = dict(old_state.allowed_features)
        features['reports'] = True
        features['export_data'] = False
        data['allowed_features'] = features
        license_client._store_state(license_client.LicenseState(
            status='SUCCESS', message='', data=data, valid=True, source='online'
        ))
        try:
            assert test_client.get(
                '/reports/export/executive-dashboard/json'
            ).status_code == 403
            assert test_client.post('/reports/schedules', data={
                'report_key': 'executive-dashboard', 'name': 'نباید ساخته شود'
            }).status_code == 403
            assert test_client.post('/reports/schedules/999/run').status_code == 403
            assert test_client.get('/reports/exports/999/download').status_code == 403

            report = test_client.get('/reports/view/executive-dashboard')
            assert report.status_code == 200
            assert 'Excel حرفه‌ای'.encode() not in report.data
            assert b'data-bs-target="#scheduleModal"' not in report.data
            schedules = test_client.get('/reports/schedules')
            assert schedules.status_code == 200
            assert 'زمان‌بندی جدید'.encode() not in schedules.data
            with test_app.app_context():
                assert run_due_report_schedules() == {
                    'due': 0, 'claimed': 0, 'completed': 0, 'failed': []
                }
        finally:
            license_client._store_state(old_state)
