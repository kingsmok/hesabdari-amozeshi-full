"""
مدیریت جامع خطاها — درجه‌بندی و ثبت استثناها به‌جای صفحهٔ عمومی ۵۰۰
════════════════════════════════════════════
پیش از این `app.errorhandler(500)` فقط یک قالب ثابت را برمی‌گرداند؛ کاربر هیچ
سرنخی از «چه شد» نداشت و پشتیبانی هم باید خودش لاگ سرور را می‌گشت.

این ماژول:
  • exception مورد نظر را به `traceback` می‌فرستند؛
  • در حالت DEBUG همان پاسخ Werkzeug (مفید برای توسعه) برگردانده می‌شود؛
  • در حالت عادی، پیامِ کاربرپسند + کد پیگیری (reference code) نمایش داده
    می‌شود تا کاربر بتواند راحت به پشتیبانی اطلاع دهد؛
  • همه‌چیز در `logs/academy.log` ثبت می‌شود (راه‌اندازی در app.py).
"""
from __future__ import annotations

import secrets

from flask import render_template


def _reference_code() -> str:
    """کد پیگیری کوتاه برای مکاتبه با پشتیبانی (مثلاً 4F9A-2C71)."""
    raw = secrets.token_hex(4).upper()
    return f'{raw[:4]}-{raw[4:]}'


def register_global_handlers(app) -> None:
    """ثبت هندلرهای سراسری؛ باید در بوت یک‌بار صدا زده شود."""

    @app.errorhandler(404)
    def not_found_handler(error):
        return render_template('errors/404.html'), 404

    @app.errorhandler(403)
    def forbidden_handler(error):
        return render_template('errors/403.html'), 403

    @app.errorhandler(500)
    def internal_error_handler(error):
        # لاگ کامل traceback به همراه شناسهٔ درخواست (همبستگی لاگ و پاسخ)
        app.logger.error('Unhandled exception [%s] on %s: %s',
                         _request_id(), _request_path(), error, exc_info=error)
        if app.debug:
            # در توسعه، پاسخ پیش‌فرض Werkzeug مفیدتر است
            raise error
        return render_template('errors/500.html', reference_code=_reference_code()), 500

    # استثناهای غیر HTTP غیرمنتظره نیز به ۵۰۰ کاربرپسند تبدیل می‌شوند
    @app.errorhandler(Exception)
    def generic_error_handler(error):
        if isinstance(error, Exception) and not getattr(error, 'code', None):
            app.logger.error('Unhandled exception [%s] on %s: %s',
                             _request_id(), _request_path(), error, exc_info=error)
            if app.debug:
                raise error
            return render_template('errors/500.html',
                                   reference_code=_reference_code()), 500
        # خطاهای HTTP شناخته‌شده (404/403/...) با هندلر بالا مدیریت می‌شوند
        return internal_error_handler(error)


def _request_path() -> str:
    try:
        from flask import request
        return request.path
    except Exception:                      # noqa: BLE001
        return '(no request context)'


def _request_id() -> str:
    """شناسهٔ درخواست جاری (برای همبستگی با هدر X-Request-ID)."""
    try:
        from utils.request_id import current_request_id
        return current_request_id() or '-'
    except Exception:                      # noqa: BLE001
        return '-'
