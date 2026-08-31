"""
آزمون‌های خواندن config.ini نصب‌کننده (Inno Setup) و راه‌اندازی اولیه.

اجرا:
    pytest tests/test_installer_config.py -q
"""
import os
import sys

import pytest
from flask import Flask

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from extensions import db                               # noqa: E402
from utils import installer_config                      # noqa: E402

SAMPLE_INI = """[Admin]
username=modir
password=Str0ngPass!
password_consumed=false

[Platform]
host_url=https://panel.example.com
verify_ssl=true

[License]
server_url=https://ls.ariapadideh.ir
channel=stable
auto_update=true

[Install]
version=1.0.1
installed_at=2026-08-31 10:20:30
install_dir=C:\\Program Files\\Hesabdari Rahsa
"""


@pytest.fixture
def ini_dir(tmp_path, monkeypatch):
    """config.ini نمونه در یک پوشه موقت و هدایت base_dir/settings.json به آن."""
    path = tmp_path / 'config.ini'
    path.write_text(SAMPLE_INI, encoding='utf-8')
    monkeypatch.setattr(installer_config, 'base_dir', lambda: str(tmp_path))
    # settings.json واقعی پروژه نباید در آزمون تغییر کند
    import config as app_config
    monkeypatch.setattr(app_config, 'CONFIG_FILE', str(tmp_path / 'settings.json'))
    return tmp_path


@pytest.fixture
def app(tmp_path):
    application = Flask(__name__)
    application.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{tmp_path}/test.db'
    application.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    application.config['TESTING'] = True
    db.init_app(application)
    with application.app_context():
        # همان مجموعه‌ای که app.py پیش از create_all وارد می‌کند
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
        yield application
        db.session.remove()
        db.drop_all()


class TestParsing:
    def test_missing_file_returns_empty(self, tmp_path, monkeypatch):
        monkeypatch.setattr(installer_config, 'base_dir', lambda: str(tmp_path))
        assert installer_config.read_installer_config() == {}

    def test_sections_are_parsed(self, ini_dir):
        data = installer_config.read_installer_config()
        assert data['admin']['username'] == 'modir'
        assert data['admin']['password'] == 'Str0ngPass!'
        assert data['admin']['consumed'] is False
        assert data['platform']['host_url'] == 'https://panel.example.com'
        assert data['platform']['verify_ssl'] is True
        assert data['license']['server_url'] == 'https://ls.ariapadideh.ir'
        assert data['install']['version'] == '1.0.1'

    def test_broken_file_is_ignored(self, tmp_path, monkeypatch):
        (tmp_path / 'config.ini').write_text('!! not an ini !!', encoding='utf-8')
        monkeypatch.setattr(installer_config, 'base_dir', lambda: str(tmp_path))
        assert installer_config.read_installer_config() == {}

    def test_consume_password_clears_value(self, ini_dir):
        assert installer_config.consume_admin_password() is True
        data = installer_config.read_installer_config()
        assert data['admin']['password'] == ''
        assert data['admin']['consumed'] is True
        # بقیه مقادیر دست‌نخورده می‌مانند
        assert data['platform']['host_url'] == 'https://panel.example.com'


class TestBootstrapAdmin:
    def test_creates_admin_and_consumes_password(self, app, ini_dir):
        from models.user import User

        note = installer_config.apply_installer_config()
        assert 'modir' in note
        user = User.query.filter_by(username='modir').first()
        assert user is not None and user.is_admin and user.check_password('Str0ngPass!')
        assert installer_config.read_installer_config()['admin']['password'] == ''

    def test_is_idempotent(self, app, ini_dir):
        from models.user import User

        installer_config.apply_installer_config()
        installer_config.apply_installer_config()
        assert User.query.filter_by(username='modir').count() == 1

    def test_existing_admin_is_never_overwritten(self, app, ini_dir):
        from models.user import User

        existing = User(username='admin', full_name='مدیر', is_admin=True, is_active=True)
        existing.set_password('old-password')
        db.session.add(existing)
        db.session.commit()

        installer_config.apply_installer_config()

        assert User.query.filter_by(username='modir').first() is None
        assert User.query.filter_by(username='admin').first().check_password('old-password')
        # رمز نصب‌کننده حتی در این حالت هم از فایل پاک می‌شود
        assert installer_config.read_installer_config()['admin']['consumed'] is True

    def test_no_ini_is_a_no_op(self, app, tmp_path, monkeypatch):
        from models.user import User

        monkeypatch.setattr(installer_config, 'base_dir', lambda: str(tmp_path))
        assert installer_config.apply_installer_config() == ''
        assert User.query.count() == 0
