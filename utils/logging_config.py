"""
پیکربندی مرکزی لاگ — Academy Manager Pro
════════════════════════════════════════════
پیش از این، پیام‌های بوت/خطا با `print()` چاپ می‌شدند و هیچ فایل لاگی ساخته
نمی‌شد؛ یعنی خرابیِ سرویسِ کاربر فقط در کنسولِ ویندوز دیده می‌شد و برای
پشتیبانی میدانی چیزی برای ارسال نبود.

این ماژول:
  • لاگ را به فایل‌های چرخشی (RotatingFileHandler) در `logs/` می‌فرستد؛
  • سطح لاگ را از env (ACADEMY_LOG_LEVEL) یا config می‌خواند؛
  • فرمت لاگ شامل زمان/سطح/نام ماژول است؛
  • مدیرِ root را با handler کاربران (Werkzeug/APScheduler) سازگار می‌کند؛
  • تابع `configure_app_logging(app)` باید یک‌بار در `create_app()` صدا زده شود.
"""
from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler

LOG_FORMAT = '%(asctime)s %(levelname)-7s [%(name)s] %(message)s'
LOG_DATE_FORMAT = '%Y-%m-%d %H:%M:%S'

_configured = False


def log_dir(base_dir: str | None = None) -> str:
    """پوشه لاگ‌ها — کنار برنامه (سازگار با PyInstaller)."""
    if base_dir is None:
        import sys
        base_dir = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) \
            else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    folder = os.path.join(base_dir, 'logs')
    os.makedirs(folder, exist_ok=True)
    return folder


def _level(env_value: str | None, default: str = 'INFO') -> str:
    value = (env_value or default or 'INFO').strip().upper()
    return value if value in ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL') else default


def configure_app_logging(app) -> None:
    """راه‌اندازی لاگ فایل چرخشی؛ idempotent است (تست‌ها چندبار create_app می‌کنند)."""
    global _configured
    if _configured:
        return

    try:
        level = _level(os.environ.get('ACADEMY_LOG_LEVEL')
                       or (app.config.get('LOG_LEVEL') or 'INFO'))
        folder = log_dir(app.config.get('BASE_DIR'))
        handler = RotatingFileHandler(
            os.path.join(folder, 'academy.log'),
            maxBytes=5 * 1024 * 1024,      # هر فایل ۵ مگابایت
            backupCount=5,                 # تا ۵ نسخه قدیمی
            encoding='utf-8',
        )
        handler.setFormatter(logging.Formatter(LOG_FORMAT, LOG_DATE_FORMAT))

        root = logging.getLogger()
        # از اضافه شدن handler تکراری بعد از reloader (پروسه مجزا) جلوگیری می‌شود
        if not any(isinstance(h, RotatingFileHandler) for h in root.handlers):
            root.addHandler(handler)
        root.setLevel(level)

        # لاگر خود اپ هم از همین تنظیم استفاده کند
        app.logger.setLevel(level)
        _configured = True
    except Exception as exc:               # noqa: BLE001
        # لاگ نباید بوت برنامه را متوقف کند
        print(f'[LOGGING] setup failed: {exc}', flush=True)


def get_logger(name: str) -> logging.Logger:
    """ساخت/بازگردانی لاگر ماژول‌دار (جایگزین print)."""
    return logging.getLogger(name)
