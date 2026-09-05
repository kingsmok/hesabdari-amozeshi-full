"""
آزمون حساب مدیر پیش‌فرض نصب تازه (admin / admin123).

اجرا:
    pytest tests/test_default_admin.py -q
"""
import os
import sys

import pytest
from flask import Flask

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from extensions import db  # noqa: E402


@pytest.fixture
def app(tmp_path, monkeypatch):
    application = Flask(__name__)
    application.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{tmp_path}/test.db'
    application.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    application.config['TESTING'] = True
    db.init_app(application)
    with application.app_context():
        import models.user      # noqa: F401
        import models.student   # noqa: F401
        import models.teacher   # noqa: F401
        import models.course    # noqa: F401
        import models.classes   # noqa: F401
        import models.registration  # noqa: F401
        import models.finance   # noqa: F401
        import models.accounting    # noqa: F401
        import models.attendance    # noqa: F401
        import models.exam      # noqa: F401
        import models.system    # noqa: F401
        import models.bot       # noqa: F401
        db.create_all()
        # نصب‌کننده‌ای در کار نیست (روی هاست هم config.ini نیست)
        from utils import installer_config
        monkeypatch.setattr(installer_config, 'read_installer_config', lambda: {})
        yield application
        db.session.remove()
        db.drop_all()


class TestDefaultAdmin:
    def test_created_on_fresh_install(self, app):
        from bootstrap.defaults import create_default_data
        from models.user import User

        create_default_data()
        admin = User.query.filter_by(username='admin').first()
        assert admin is not None
        assert admin.is_admin and admin.is_active
        assert admin.check_password('admin123')
        assert admin.role_id is not None

    def test_idempotent(self, app):
        from bootstrap.defaults import create_default_data
        from models.user import User

        create_default_data()
        create_default_data()
        assert User.query.filter_by(username='admin').count() == 1

    def test_existing_users_are_never_touched(self, app):
        from bootstrap.defaults import create_default_data
        from models.user import User

        staff = User(username='existing', full_name='کاربر موجود', is_admin=False,
                     is_active=True)
        staff.set_password('Something-Else-123!')
        db.session.add(staff)
        db.session.commit()

        create_default_data()
        assert User.query.filter_by(username='admin').first() is None
        assert User.query.filter_by(username='existing').first().check_password(
            'Something-Else-123!')

    def test_env_override(self, app, monkeypatch):
        monkeypatch.setenv('ACADEMY_ADMIN_USER', 'rootuser')
        monkeypatch.setenv('ACADEMY_ADMIN_PASSWORD', 'S3cret-Pass!')
        from bootstrap.defaults import create_default_data
        from models.user import User

        create_default_data()
        custom = User.query.filter_by(username='rootuser').first()
        assert custom is not None and custom.check_password('S3cret-Pass!')
        assert User.query.filter_by(username='admin').first() is None

    def test_installer_admin_takes_precedence(self, app, monkeypatch):
        """اگر نصب‌کننده مدیر خودش را دارد، پیش‌فرض ساخته نمی‌شود تا نوبت
        به قدم installer برسد (وگرنه رمز اپراتور نادیده گرفته می‌شد)."""
        from utils import installer_config

        monkeypatch.setattr(
            installer_config, 'read_installer_config',
            lambda: {'admin': {'username': 'modir', 'password': 'Str0ngPass!',
                               'consumed': False}})
        from bootstrap.defaults import _ensure_default_admin
        from models.user import User

        assert _ensure_default_admin() == ''
        assert User.query.count() == 0

    def test_constants_helper(self):
        from utils.constants import (FALLBACK_ADMIN_PASSWORD,
                                     FALLBACK_ADMIN_USERNAME,
                                     is_default_admin_password)
        assert FALLBACK_ADMIN_USERNAME == 'admin'
        assert FALLBACK_ADMIN_PASSWORD == 'admin123'
        assert len(FALLBACK_ADMIN_PASSWORD) >= 8  # سیاست حداقل رمز سیستم
        assert is_default_admin_password('admin', 'admin123')
        assert not is_default_admin_password('admin', 'wrong')
