"""
بوت‌استرپ اکستنشن‌ها — ثبت Flask-SQLAlchemy / Login / Migrate / CSRF.
"""
from __future__ import annotations

from extensions import csrf, db, login_manager, migrate


def setup(app) -> None:
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'لطفاً وارد شوید'
    migrate.init_app(app, db)
    csrf.init_app(app)
