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
  • خطاهای HTTP (مثل ۴۰۰/۴۰۵/۴۱۳) با همان کد واقعی پاسخ داده می‌شوند —
    پیش‌تر همه به صفحهٔ ۵۰۰ تبدیل می‌شدند و عیب‌یابی را گمراه می‌کردند.
"""
from __future__ import annotations

import secrets

from flask import jsonify, redirect, render_template
from werkzeug.exceptions import HTTPException

#: عنوان و پیام فارسی خطاهای رایج HTTP (کلید = کد وضعیت)
_HTTP_MESSAGES = {
    400: ('درخواست نامعتبر', 'درخواست شما ناقص است؛ صفحه را تازه کنید و دوباره تلاش کنید.'),
    401: ('نیاز به ورود', 'برای دیدن این صفحه باید وارد شوید.'),
    405: ('روش مجاز نیست', 'این آدرس با این روش قابل فراخوانی نیست.'),
    408: ('مهلت درخواست', 'درخواست بیش از حد طول کشید؛ دوباره تلاش کنید.'),
    413: ('حجم فایل زیاد است', 'حجم فایل از سقف مجاز (۵۰ مگابایت) بیشتر است.'),
    414: ('آدرس طولانی است', 'آدرس درخواست بیش از حد طولانی است.'),
    429: ('درخواست زیاد', 'تعداد درخواست‌ها بیش از حد مجاز است؛ کمی صبر کنید.'),
    503: ('سرویس در دسترس نیست', 'سرویس موقتاً در دسترس نیست؛ لحظاتی بعد تلاش کنید.'),
}

_FA_DIGITS = str.maketrans('0123456789', '۰۱۲۳۴۵۶۷۸۹')


def _fa_digits(value) -> str:
    return str(value).translate(_FA_DIGITS)


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
        try:
            return render_template('errors/500.html', reference_code=_reference_code()), 500
        except Exception:                      # noqa: BLE001 — قالب ۵۰۰ خودش نباید ۵۰۰ بسازد
            return ('خطای داخلی سرور', 500)

    # CSRF ناموفق تقریباً همیشه یعنی «نشست منقضی شده»؛ به‌جای صفحهٔ ترسناک
    # ۵۰۰، کاربر با یک پیام روشن به همان صفحه برمی‌گردد و دوباره تلاش می‌کند.
    @app.errorhandler(400)
    def bad_request_handler(error):
        from flask_wtf.csrf import CSRFError
        if isinstance(error, CSRFError):
            app.logger.warning('CSRF failure [%s] on %s: %s',
                               _request_id(), _request_path(), error)
            if _wants_json():
                return jsonify({'ok': False, 'error': {
                    'code': 'CSRF_FAILED',
                    'message': 'نشست منقضی شده؛ صفحه را تازه کنید و دوباره تلاش کنید.'}}), 400
            try:
                from flask import flash
                flash('نشست شما منقضی شده است؛ لطفاً دوباره تلاش کنید', 'error')
            except Exception:                      # noqa: BLE001
                pass
            return redirect(_safe_back_target())
        return _http_error_page(app, error, 400)

    # استثناهای غیر HTTP غیرمنتظره نیز به ۵۰۰ کاربرپسند تبدیل می‌شوند؛
    # خطاهای HTTP شناخته‌شده با همان کد واقعی پاسخ داده می‌شوند (نه ۵۰۰).
    @app.errorhandler(Exception)
    def generic_error_handler(error):
        if isinstance(error, HTTPException) and getattr(error, 'code', None):
            code = int(error.code)
            if code == 404:
                return not_found_handler(error)
            if code == 403:
                return forbidden_handler(error)
            if code == 400:
                return bad_request_handler(error)
            if code == 500:
                return internal_error_handler(error)
            return _http_error_page(app, error, code)
        app.logger.error('Unhandled exception [%s] on %s: %s',
                         _request_id(), _request_path(), error, exc_info=error)
        if app.debug:
            raise error
        try:
            return render_template('errors/500.html',
                                   reference_code=_reference_code()), 500
        except Exception:                      # noqa: BLE001
            return ('خطای داخلی سرور', 500)


def _http_error_page(app, error, code: int):
    """صفحهٔ عمومی خطای HTTP با کد وضعیت واقعی (405/413/...)."""
    title, message = _HTTP_MESSAGES.get(code, ('خطا', 'درخواستی نامعتبر دریافت شد.'))
    app.logger.warning('HTTP %s [%s] on %s: %s',
                       code, _request_id(), _request_path(), error)
    if _wants_json():
        return jsonify({'ok': False, 'error': {'code': f'HTTP_{code}',
                                               'message': message}}), code
    return render_template('errors/error.html', code=code,
                           code_fa=_fa_digits(code), title=title,
                           message=message), code


def _wants_json() -> bool:
    try:
        from flask import request
        if request.path.startswith('/api/'):
            return True
        if request.is_json:
            return True
        return request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    except Exception:                              # noqa: BLE001
        return False


def _safe_back_target() -> str:
    """بازگشت به صفحهٔ قبلی فقط اگر همان‌هاست باشد (ضد open-redirect)."""
    try:
        from urllib.parse import urlsplit

        from flask import request
        ref = request.referrer or ''
        if ref:
            parts = urlsplit(ref)
            host = urlsplit(request.host_url).netloc
            if (not parts.netloc or parts.netloc == host) \
                    and (parts.path or '/').startswith('/'):
                return parts.path or '/'
    except Exception:                              # noqa: BLE001
        pass
    return '/'


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
