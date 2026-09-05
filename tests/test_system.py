"""
Academy Manager Pro - Comprehensive Architectural Test Suite
Deterministic Verification for All Critical Paths, Edge Cases, and Invariants
"""
import pytest
from datetime import date, datetime
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


@pytest.fixture
def admin_user(test_app):
    """حساب مدیر کل — اگر نبود موقتاً ساخته و در پایان حذف می‌شود تا دیتابیس
    توسعه با ردیف آزمونی آلوده نماند."""
    with test_app.app_context():
        admin = User.query.filter_by(is_admin=True, is_active=True).first()
        created_id = None
        if admin is None:
            admin = User(username='test_system_admin', full_name='مدیر آزمون',
                         is_admin=True, is_active=True)
            admin.set_password('Test@123')
            db.session.add(admin)
            db.session.commit()
            created_id = admin.id
        yield admin
    if created_id is not None:
        with test_app.app_context():
            row = db.session.get(User, created_id)
            if row is not None:
                db.session.delete(row)
                db.session.commit()



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
    def test_admin_has_full_access(self, test_app, admin_user):
        with test_app.app_context():
            assert admin_user.is_admin is True
            assert admin_user.has_permission('accounting', 'delete') is True
            assert admin_user.has_permission('finance', 'create') is True

    def test_role_based_permission_check(self, test_app):
        """نقش → مجوز → کاربر؛ هرچه این آزمون ساختن است در پایان پاک می‌کند تا
        دیتابیس توسعه با ردیف آزمونی آلوده نماند (ردیف از پیش موجود دست‌نخورده)."""
        created = []
        with test_app.app_context():
            role = Role.query.filter_by(name='تست منشی').first()
            if not role:
                role = Role(name='تست منشی', description='نقش آزمایشی', is_admin=False)
                db.session.add(role)
                db.session.commit()
                created.append(role)

            perm = Permission.query.filter_by(module='students', action='view').first()
            if not perm:
                perm = Permission(module='students', action='view', description='مشاهده هنرجویان')
                db.session.add(perm)
                db.session.commit()
                created.append(perm)

            rp = RolePermission.query.filter_by(role_id=role.id, permission_id=perm.id).first()
            if not rp:
                rp = RolePermission(role_id=role.id, permission_id=perm.id)
                db.session.add(rp)
                db.session.commit()
                created.append(rp)

            user = User.query.filter_by(username='test_secretary').first()
            created_user = None
            if not user:
                user = created_user = User(
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

            # ترتیب حذف مهم است: اول وابسته‌ها (کاربر و نقش-مجوز)، بعد خود نقش/مجوز
            if created_user is not None:
                db.session.delete(created_user)
            for row in reversed(created):
                db.session.delete(row)
            db.session.commit()


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

    def test_authenticated_dashboard_renders_200(self, test_app, test_client, admin_user):
        with test_app.app_context():
            admin = admin_user
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
