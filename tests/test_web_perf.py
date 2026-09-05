"""آزمون بهینه‌سازی نسخهٔ وب: سلامت، لایسنس بدون بلاک، gzip، کش دسترسی."""
import os
import sys
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app  # noqa: E402


@pytest.fixture(scope='module')
def test_app():
    os.environ.setdefault('ACADEMY_DISABLE_SCHEDULER', '1')
    app = create_app()
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    app.debug = False
    return app


@pytest.fixture(scope='module')
def client(test_app):
    return test_app.test_client()


class TestHealthz:
    def test_healthz_is_public(self, client):
        response = client.get('/healthz')
        assert response.status_code == 200
        payload = response.get_json()
        assert payload['ok'] is True
        assert payload['db'] == 'ok'
        assert 'no-store' in response.headers.get('Cache-Control', '')

    def test_healthz_not_redirected_to_license_or_login(self, client):
        response = client.get('/healthz', follow_redirects=False)
        assert response.status_code == 200
        assert response.headers.get('Location') in (None, '')


class TestGzip:
    def test_html_is_gzipped_when_client_accepts(self, client):
        response = client.get('/login', headers={'Accept-Encoding': 'gzip'})
        assert response.status_code == 200
        assert response.headers.get('Content-Encoding') == 'gzip'
        # test client decompresses automatically in some versions; either way body exists
        assert response.data

    def test_no_gzip_without_accept(self, client):
        response = client.get('/login')
        assert response.headers.get('Content-Encoding') in (None, '')


class TestLicenseDoesNotBlock:
    def test_first_get_state_without_key_is_instant(self):
        import license_client
        license_client._store_state(None)
        license_client.clear_cache()
        license_client.clear_license_key()
        started = time.monotonic()
        state = license_client.get_state()
        elapsed = time.monotonic() - started
        assert state.needs_activation
        assert elapsed < 2.0, f'get_state بدون کلید {elapsed:.1f}s طول کشید (نباید شبکه برود)'

    def test_invalid_state_revalidation_does_not_block(self):
        import license_client
        license_client._store_state(license_client.LicenseState(
            status='OFFLINE_NO_CACHE', message='x', transient=True))
        # سن را کهنه کن تا _needs_revalidation True شود
        license_client._state.checked_monotonic = time.monotonic() - 10_000
        started = time.monotonic()
        state = license_client.get_state()
        elapsed = time.monotonic() - started
        assert state.status == 'OFFLINE_NO_CACHE'
        assert elapsed < 1.0, f'وضعیت نامعتبر {elapsed:.1f}s روی شبکه رفت'


class TestPermissionCache:
    def test_role_perms_cached_in_request(self, test_app):
        from extensions import db
        from models.user import Role, User

        with test_app.app_context():
            role = Role.query.filter_by(is_admin=False).first()
            if role is None:
                pytest.skip('no non-admin role')
            user = User(username='perf_cache_user', full_name='تست',
                        role_id=role.id, is_admin=False)
            user.set_password('x')
            db.session.add(user)
            db.session.commit()
            user_id = user.id

        with test_app.test_request_context():
            from flask import g
            from models.user import User as UserModel
            with test_app.app_context():
                loaded = db.session.get(UserModel, user_id)
                first = loaded._role_perm_pairs()
                second = loaded._role_perm_pairs()
                assert first is second or first == second
                assert getattr(g, f'_role_perms_{loaded.role_id}', None) is not None

        with test_app.app_context():
            db.session.delete(db.session.get(User, user_id))
            db.session.commit()
