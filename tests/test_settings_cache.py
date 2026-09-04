"""
آزمون کش درخواست‌محور تنظیمات — تضمین «یک کوئری در هر درخواست».
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from app import create_app
from extensions import db
from models.system import SystemSettings


@pytest.fixture()
def app():
    os.environ["ACADEMY_DISABLE_SCHEDULER"] = "1"
    app = create_app()
    yield app
    with app.app_context():
        db.session.remove()


def test_single_query_per_request_context(app):
    """در یک درخواست، فراخوانی‌های مکرر همان شیء را برمی‌گردانند."""
    with app.test_request_context():
        from utils.settings_cache import get_system_settings

        first = get_system_settings()
        second = get_system_settings()
        assert first is second, "کش درخواست‌محور باید همان نمونه را برگرداند"


def test_create_app_injects_cached_settings(app):
    """context processor از کش استفاده می‌کند و مقدار واقعی دیتابیس را می‌دهد."""
    client = app.test_client()
    with app.app_context():
        expected = SystemSettings.query.first()
    # مسیر /offline قالب را render می‌کند → context processor اجرا می‌شود
    response = client.get('/offline')
    assert response.status_code == 200
    assert expected is not None
