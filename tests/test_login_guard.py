"""
آزمون کنترل دسترسی/امنیت ورود (بازبینی امنیت و صحت داده — بند A3)
════════════════════════════════════════════════════════════════════
سه چیزی که پیش‌ نبود داشت و این فایل می‌پاید:

۱) `POST /login` هیچ محدودیت تعداد تلاش نداشت ⇒ brute force آزاد روی میزبانی عمومی.
۲) `load_user` کاربر غیرفعال را هم بار می‌کرد ⇒ حسابی که مدیر از دسترس خارج کرده
   بود، با کوکی Remember-Me (۱۴ روزه) کارش ادامه می‌داد.
۳) `password reset` با مقدار پیش‌فرض `123456` یک در پشتی همیشگی می‌ساخت.

اتصال به دیتابیس توسعه؛ همه ردیف‌های آزمونی در پایان پاک می‌شوند.
"""
import os
import sys
from datetime import datetime

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app                      # noqa: E402
from extensions import db                       # noqa: E402
from models.user import User, UserSession       # noqa: E402
from utils import login_guard                   # noqa: E402


@pytest.fixture(scope='module')
def test_app():
    app = create_app()
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    app.debug = False
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


@pytest.fixture(autouse=True)
def _clean_guard():
    login_guard.clear_all()
    yield
    login_guard.clear_all()


@pytest.fixture
def accounts(test_app):
    """دو حساب آزمونی: یک مدیر و یک کاربر عادی (در پایان پاک می‌شوند)."""
    created = []
    with test_app.app_context():
        from models.user import Role
        role = Role.query.first()
        admin = User(username='guard_admin_test', full_name='مدیر آزمون گارد',
                     is_admin=True, is_active=True, role_id=role.id if role else None)
        admin.set_password('Guard-Admin-123!')
        victim = User(username='guard_user_test', full_name='کاربر آزمون گارد',
                      is_admin=False, is_active=True, role_id=role.id if role else None)
        victim.set_password('Guard-User-123!')
        db.session.add_all([admin, victim])
        db.session.commit()
        created = [admin.id, victim.id]
    yield {'admin_id': admin.id, 'victim_id': victim.id,
           'admin_name': 'guard_admin_test', 'victim_name': 'guard_user_test',
           'victim_password': 'Guard-User-123!'}
    with test_app.app_context():
        from models.user import ActivityLog
        for uid in created:
            UserSession.query.filter_by(user_id=uid).delete(synchronize_session=False)
            ActivityLog.query.filter_by(user_id=uid).delete(synchronize_session=False)
            row = db.session.get(User, uid)
            if row is not None:
                db.session.delete(row)
        db.session.commit()


class TestLoginThrottle:
    def test_five_failures_lock_the_account(self, test_app, accounts):
        client = test_app.test_client()
        for attempt in range(login_guard.MAX_ATTEMPTS):
            response = client.post('/login', data={'username': accounts['victim_name'],
                                                   'password': f'wrong-{attempt}'})
            if attempt < login_guard.MAX_ATTEMPTS - 1:
                assert response.status_code == 200
        # تلاش بعدی حتی با رمز درست باید رد شود
        response = client.post('/login', data={'username': accounts['victim_name'],
                                               'password': accounts['victim_password']})
        assert response.status_code == 429, 'قفل پس از تلاش‌های ناموفق کار نمی‌کند'
        assert 'قفل' in response.get_data(as_text=True)
        assert login_guard.is_locked(accounts['victim_name'], '127.0.0.1')

    def test_unknown_user_is_also_counted(self, test_app):
        client = test_app.test_client()
        for _ in range(login_guard.MAX_ATTEMPTS):
            client.post('/login', data={'username': 'no-such-user-xyz', 'password': 'x'})
        assert login_guard.is_locked('no-such-user-xyz', '127.0.0.1'), \
            'نام کاربری‌های قابل حدس باید مثل بقیه قفل شوند'

    def test_success_resets_the_counter(self, test_app, accounts):
        client = test_app.test_client()
        client.post('/login', data={'username': accounts['victim_name'], 'password': 'nope'})
        assert login_guard.failures_of(accounts['victim_name'], '127.0.0.1') == 1
        response = client.post('/login', data={'username': accounts['victim_name'],
                                               'password': accounts['victim_password']})
        assert response.status_code == 302
        assert login_guard.failures_of(accounts['victim_name'], '127.0.0.1') == 0

    def test_lock_expires(self):
        key_user, key_ip = 'u1', '1.2.3.4'
        now = 1_000_000.0
        for _ in range(login_guard.MAX_ATTEMPTS):
            login_guard.register_failure(key_user, key_ip, now=now)
        assert login_guard.lock_remaining(key_user, key_ip, now=now) == login_guard.LOCK_SECONDS
        assert login_guard.lock_remaining(key_user, key_ip,
                                          now=now + login_guard.LOCK_SECONDS + 1) == 0

    def test_window_forgets_old_attempts(self):
        now = 2_000_000.0
        for _ in range(login_guard.MAX_ATTEMPTS - 1):
            login_guard.register_failure('u2', '5.6.7.8', now=now)
        # پنجره ۱۵ دقیقه‌ای ⇒ تلاش‌های قدیمی شمرده نمی‌شوند
        later = now + login_guard.WINDOW_SECONDS + 60
        assert login_guard.register_failure('u2', '5.6.7.8', now=later) == 1
        assert not login_guard.is_locked('u2', '5.6.7.8', now=later)

    def test_lock_message_rounds_up_to_minutes(self):
        message = login_guard.lock_message(599)      # ۹ دقیقه و ۵۹ ثانیه ⇒ ۱۰ دقیقه
        assert 'قفل' in message and '10 دقیقه' in message, message


class TestSessionRevocation:
    def test_deactivated_user_loses_access_immediately(self, test_app, accounts):
        admin = test_app.test_client()
        assert admin.post('/login', data={'username': accounts['admin_name'],
                                          'password': 'Guard-Admin-123!'}).status_code == 302
        victim = test_app.test_client()
        assert victim.post('/login', data={'username': accounts['victim_name'],
                                           'password': accounts['victim_password']}).status_code == 302
        assert victim.get('/').status_code == 200, 'داشبورد برای کاربر فعال باید باز باشد'
        with test_app.app_context():
            assert UserSession.query.filter_by(user_id=accounts['victim_id'],
                                               is_active=True).count() >= 1

        response = admin.post(f"/perms/users/{accounts['victim_id']}/delete",
                              follow_redirects=False)
        assert response.status_code == 302

        # نشست قدیمی نباید کاری از پیش ببرد
        assert victim.get('/').status_code == 302, \
            'کاربر غیرفعال‌شده هنوز با کوکی قبلی دسترسی دارد'
        with test_app.app_context():
            assert UserSession.query.filter_by(user_id=accounts['victim_id'],
                                                is_active=True).count() == 0, \
                'نشست‌های باز هنگام غیرفعال‌سازی بسته نشدند'

    def test_null_is_active_still_loads(self, test_app, accounts):
        """در نصب‌های قدیمی ستون NULL است؛ نباید همه را بیرون بیندازیم."""
        victim = test_app.test_client()
        assert victim.post('/login', data={'username': accounts['victim_name'],
                                           'password': accounts['victim_password']}).status_code == 302
        with test_app.app_context():
            db.session.execute(db.text('UPDATE users SET is_active = NULL WHERE id = :i'),
                               {'i': accounts['victim_id']})
            db.session.commit()
        assert victim.get('/').status_code == 200, 'کاربر با is_active=NULL نباید قفل شود'
        with test_app.app_context():
            db.session.execute(db.text('UPDATE users SET is_active = 0 WHERE id = :i'),
                               {'i': accounts['victim_id']})
            db.session.commit()
        assert victim.get('/').status_code == 302, 'False صریح باید دسترسی را قطع کند'

    def test_password_change_closes_sessions(self, test_app, accounts):
        admin = test_app.test_client()
        assert admin.post('/login', data={'username': accounts['admin_name'],
                                          'password': 'Guard-Admin-123!'}).status_code == 302
        victim = test_app.test_client()
        assert victim.post('/login', data={'username': accounts['victim_name'],
                                           'password': accounts['victim_password']}).status_code == 302

        response = admin.post(f"/perms/users/{accounts['victim_id']}/reset-password",
                              data={'new_password': 'Rotated-Password-9!'},
                              follow_redirects=False)
        assert response.status_code == 302
        with test_app.app_context():
            assert UserSession.query.filter_by(user_id=accounts['victim_id'],
                                                is_active=True).count() == 0

    def test_weak_reset_password_is_refused(self, test_app, accounts):
        admin = test_app.test_client()
        assert admin.post('/login', data={'username': accounts['admin_name'],
                                          'password': 'Guard-Admin-123!'}).status_code == 302
        with test_app.app_context():
            before = db.session.get(User, accounts['victim_id']).password_hash
        admin.post(f"/perms/users/{accounts['victim_id']}/reset-password",
                   data={'new_password': '123456'}, follow_redirects=False)
        with test_app.app_context():
            assert db.session.get(User, accounts['victim_id']).password_hash == before, \
                'رمز ساده ۱۲۳۴۵۶ هنوز پذیرفته می‌شود'


class TestUserAccountFlags:
    """تله `UserMixin.is_authenticated` که با ستون `is_active` قاتی می‌شد."""

    def test_null_is_active_counts_as_authenticated(self, test_app):
        from models.user import User as UserModel
        legacy = UserModel(username='legacy', full_name='کاربر قدیمی')
        legacy.is_active = None
        assert legacy.is_authenticated is True, 'NULL نباید کاربر را بیرون بیندازد'
        assert legacy.is_blocked is False

    def test_explicit_false_blocks(self, test_app):
        from models.user import User as UserModel
        blocked = UserModel(username='blocked', full_name='کاربر مسدود')
        blocked.is_active = False
        assert blocked.is_authenticated is False
        assert blocked.is_blocked is True

    def test_legacy_null_user_can_still_log_in(self, test_app, accounts):
        """نصب قدیمی با ستون خالی نباید در ورود قفل شود."""
        with test_app.app_context():
            db.session.execute(db.text('UPDATE users SET is_active = NULL WHERE id = :i'),
                               {'i': accounts['victim_id']})
            db.session.commit()
        client = test_app.test_client()
        response = client.post('/login', data={'username': accounts['victim_name'],
                                               'password': accounts['victim_password']})
        assert response.status_code == 302, 'ورود کاربر با is_active=NULL رد شد'
        assert client.get('/').status_code == 200


class TestCurrencyFilter:
    def test_invalid_value_is_logged_not_silently_zeroed(self, test_app):
        template = test_app.jinja_env.from_string('{{ value|currency }}')
        assert template.render(value=1_200_000) == '1,200,000'
        assert template.render(value=None) == '0'
        with pytest.raises(Exception):
            test_app.debug = True
            try:
                test_app.jinja_env.from_string('{{ value|currency }}').render(value={'a': 1})
            finally:
                test_app.debug = False
