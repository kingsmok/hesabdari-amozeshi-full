"""
آزمون صفحه «پروفایل من» — مشاهده مشخصات و تغییر رمز توسط خود کاربر.

اجرا:
    pytest tests/test_profile.py -q
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app                      # noqa: E402
from extensions import db                       # noqa: E402
from models.user import User                    # noqa: E402


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


@pytest.fixture
def account(test_app):
    """یک کاربر غیرمدیر (در پایان کامل پاک می‌شود)."""
    with test_app.app_context():
        from models.user import Role
        role = Role.query.first()
        user = User(username='profile_user_test', full_name='کاربر پروفایل',
                    is_admin=False, is_active=True,
                    role_id=role.id if role else None)
        user.set_password('Profile-Old-123!')
        db.session.add(user)
        db.session.commit()
        user_id = user.id
    yield {'id': user_id, 'username': 'profile_user_test',
           'password': 'Profile-Old-123!'}
    with test_app.app_context():
        from models.user import ActivityLog, UserSession
        UserSession.query.filter_by(user_id=user_id).delete(synchronize_session=False)
        ActivityLog.query.filter_by(user_id=user_id).delete(synchronize_session=False)
        row = db.session.get(User, user_id)
        if row is not None:
            db.session.delete(row)
        db.session.commit()


def _login(test_app, username, password):
    client = test_app.test_client()
    response = client.post('/login', data={'username': username, 'password': password})
    assert response.status_code in (302, 303), 'ورود آزمونی باید موفق باشد'
    return client


class TestProfilePage:
    def test_requires_login(self, test_app):
        response = test_app.test_client().get('/profile')
        assert response.status_code in (302, 303)
        assert '/login' in response.headers.get('Location', '')

    def test_user_can_view_own_profile(self, test_app, account):
        client = _login(test_app, account['username'], account['password'])
        response = client.get('/profile')
        assert response.status_code == 200
        assert 'پروفایل من' in response.data.decode('utf-8')

    def test_wrong_current_password_is_rejected(self, test_app, account):
        client = _login(test_app, account['username'], account['password'])
        response = client.post('/profile', data={
            'full_name': 'کاربر پروفایل', 'current_password': 'nope-wrong',
            'new_password': 'Profile-New-123!', 'confirm_password': 'Profile-New-123!'})
        assert response.status_code == 200
        assert 'رمز فعلی اشتباه است' in response.data.decode('utf-8')
        with test_app.app_context():
            assert db.session.get(User, account['id']).check_password('Profile-Old-123!')

    def test_short_and_mismatched_passwords_are_rejected(self, test_app, account):
        client = _login(test_app, account['username'], account['password'])
        short = client.post('/profile', data={
            'full_name': 'x', 'current_password': 'Profile-Old-123!',
            'new_password': 'short', 'confirm_password': 'short'})
        assert 'حداقل ۸ نویسه' in short.data.decode('utf-8')
        mismatch = client.post('/profile', data={
            'full_name': 'x', 'current_password': 'Profile-Old-123!',
            'new_password': 'Profile-New-123!', 'confirm_password': 'Other-12345!'})
        assert 'مطابقت ندارد' in mismatch.data.decode('utf-8')

    def test_password_change_works(self, test_app, account):
        client = _login(test_app, account['username'], account['password'])
        response = client.post('/profile', data={
            'full_name': 'نام تازه', 'current_password': 'Profile-Old-123!',
            'new_password': 'Profile-New-123!', 'confirm_password': 'Profile-New-123!'},
            follow_redirects=False)
        assert response.status_code in (302, 303)
        with test_app.app_context():
            user = db.session.get(User, account['id'])
            assert user.check_password('Profile-New-123!')
            assert user.full_name == 'نام تازه'
        # ورود با رمز جدید
        fresh = test_app.test_client()
        assert fresh.post('/login', data={'username': account['username'],
                                          'password': 'Profile-New-123!'}).status_code in (302, 303)
