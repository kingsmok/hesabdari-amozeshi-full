"""
کانفیگ مرکزی — پل بین `config.py` و `startup_checks.py`
════════════════════════════════════════════
دو نقطهٔ تکراری/پراکنده که در این پروژه وجود داشت:
  ۱) `startup_checks.ensure_compatible()` — که مدام جای چک‌های جدید باز می‌شد؛
  ۲) `config.load_config()` — که هم در app.py و هم در اسکریپت‌ها جدا صدا زده
     می‌شد.

این ماژول هر دو را یک‌جا می‌کند (یک نقطهٔ ورود): ابتدا سازگاری نسخه‌ها، سپس
بارگذاری تنظیمات — و تنظیمات رو به جلو (مثل مسیرها) را یک‌جا به app می‌دهد.
"""
from __future__ import annotations

import os


def ensure_runtime_checks():
    """بررسی سازگاری نسخه‌ها پیش از بارگذاری برنامه (idempotent).

    نکته: این تابع عمداً هیچ import دیگری از پروژه را صدا نمی‌زند تا اگر
    نسخه‌های ناسازگار نصب هستند، همان اولین خط خوانا دیده شود.
    """
    from startup_checks import ensure_compatible
    ensure_compatible()


def build_config():
    """بارگذاری و آماده‌سازی کامل کانفیگ — خروجی: (config dict, paths dict)."""
    ensure_runtime_checks()

    import sys

    import config as app_config

    # مسیر پایه: در بسته PyInstaller کنار exe، در توسعه کنار فایل
    if getattr(sys, 'frozen', False):
        base_dir = os.path.dirname(sys.executable)
    else:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    config = app_config.load_config()
    paths = {
        'base_dir': base_dir,
        'uploads': os.path.join(base_dir, 'static', 'uploads'),
        'backups': os.path.join(base_dir, 'backups'),
    }
    return config, paths


def apply_to_app(app, config: dict, paths: dict) -> None:
    """اعمال کانفیگ روی شیء Flask؛ یک نقطهٔ واحد برای کل تنظیمات."""
    import secrets

    from datetime import timedelta

    secret = os.environ.get('SECRET_KEY') or config.get('app', {}).get('secret_key')
    if not secret:
        secret = secrets.token_hex(32)
        try:
            import config as app_config
            config.setdefault('app', {})['secret_key'] = secret
            app_config.save_config(config)
        except Exception as exc:               # noqa: BLE001 — بوت متوقف نشود
            # روی هاست اگر settings.json قابل نوشتن نباشد، هر ری‌استارت کلید
            # عوض می‌شود و همهٔ نشست‌ها + توکن‌های CSRF می‌پرند؛ پس بلند هشدار
            # می‌دهیم تا در لاگ Passenger دیده شود (لاگر هنوز ساخته نشده).
            print(f'[CONFIG] WARNING: SECRET_KEY could not be saved ({exc}); '
                  f'sessions will break on restart — make settings.json writable.',
                  flush=True)

    app.config['SECRET_KEY'] = secret
    app.config['SQLALCHEMY_DATABASE_URI'] = __import__('config').get_database_uri(config)
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = __import__('config').get_engine_options(config)
    app.config['UPLOAD_FOLDER'] = paths['uploads']
    app.config['BACKUP_FOLDER'] = paths['backups']
    app.config['BASE_DIR'] = paths['base_dir']
    app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024     # 50MB سقف آپلود
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    app.config['SESSION_COOKIE_SECURE'] = os.environ.get('ACADEMY_COOKIE_SECURE') == '1'
    app.config['REMEMBER_COOKIE_HTTPONLY'] = True
    app.config['REMEMBER_COOKIE_SAMESITE'] = 'Lax'
    # Remember-Me ۱۴ روز (پیش‌فرض Flask-Login یک سال است)؛ نشست فعال ۱۲ ساعت
    app.config['REMEMBER_COOKIE_DURATION'] = timedelta(days=14)
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=12)
    app.config['WTF_CSRF_TIME_LIMIT'] = 3600
    # کش استاتیک ۱ روز (فایل‌های آپلودی از همین مسیر سرو می‌شوند)
    app.config['SEND_FILE_MAX_AGE_DEFAULT'] = timedelta(days=1)
    return app
