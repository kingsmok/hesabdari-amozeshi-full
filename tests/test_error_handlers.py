"""
آزمون هندلرهای سراسری خطا — کد واقعی HTTP باید حفظ شود، نه ۵۰۰.

پیش‌تر هر خطای HTTP (مثلاً ۴۰۰ِ CSRF یا ۴۰۵) به صفحهٔ ۵۰۰ تبدیل می‌شد و
عیب‌یابی — مخصوصاً روی هاست — را گمراه می‌کرد.

اجرا:
    pytest tests/test_error_handlers.py -q
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app  # noqa: E402


@pytest.fixture(scope='module')
def test_app():
    app = create_app()
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    app.debug = False
    return app


@pytest.fixture(scope='module')
def csrf_app():
    """اپ با CSRF روشن (پیش‌فرض واقعی) برای آزمون شکست توکن."""
    app = create_app()
    app.config['TESTING'] = True
    app.debug = False
    assert app.config['WTF_CSRF_ENABLED']
    return app


class TestHttpErrorCodes:
    def test_404_keeps_code(self, test_app):
        response = test_app.test_client().get('/no-such-page-xyz')
        assert response.status_code == 404

    def test_405_keeps_code_with_persian_message(self, test_app):
        # این مسیر فقط POST است؛ GET باید ۴۰۵ بدهد، نه ۵۰۰
        response = test_app.test_client().get('/perms/users/1/reset-password')
        assert response.status_code == 405, \
            f'انتظار 405 بود ولی {response.status_code} برگشت'
        assert 'روش مجاز نیست' in response.data.decode('utf-8')

    def test_405_json_for_api_clients(self, test_app):
        response = test_app.test_client().get(
            '/perms/users/1/reset-password',
            headers={'X-Requested-With': 'XMLHttpRequest'})
        assert response.status_code == 405
        assert response.is_json
        assert response.get_json()['ok'] is False


class TestCsrfFailure:
    def test_missing_token_redirects_back_not_500(self, csrf_app):
        # شبیه‌سازی نشست منقضی: POST بدون توکن
        response = csrf_app.test_client().post(
            '/login', data={'username': 'admin', 'password': 'x'})
        assert response.status_code == 302, \
            f'شکست CSRF باید به فرم برگردد ولی {response.status_code} برگشت'

    def test_missing_token_json_for_api_clients(self, csrf_app):
        response = csrf_app.test_client().post(
            '/login', data={'username': 'admin', 'password': 'x'},
            headers={'X-Requested-With': 'XMLHttpRequest'})
        assert response.status_code == 400
        payload = response.get_json()
        assert payload['ok'] is False
        assert payload['error']['code'] == 'CSRF_FAILED'
