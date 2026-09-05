"""
Middleware سراسری — مشاهده‌پذیری، حفاظت از سرویس و هدرهای امنیتی.
قبلاً این سه مسئولیت داخل create_app به‌صورت closure تعریف شده بود؛ حالا
توابع ماژول‌سطح‌اند و قابل‌تست مستقل (بدون ساخت کل اپ).
"""
from __future__ import annotations

import time

from flask import current_app, g, jsonify, request


def setup(app) -> None:
    # gzip باید آخر اجرا شود (after_request معکوس ثبت می‌شود)
    app.after_request(_gzip_response)
    app.before_request(_request_started)
    app.after_request(_security_and_access_log)


def _request_started():
    """شروع درخواست: زمان‌سنجی + شناسهٔ درخواست + محدودسازی نرخ API."""
    g._request_started = time.monotonic()
    from utils.request_id import start_request_id
    start_request_id()

    if request.path.startswith('/api/') and not current_app.config.get('TESTING'):
        from utils.rate_limit import hit, remaining
        if not hit():
            response = jsonify({'ok': False,
                                'error': {'code': 'RATE_LIMITED',
                                          'message': 'تعداد درخواست‌ها بیش از حد مجاز است؛ '
                                                     'لطفاً کمی صبر کنید.'}})
            response.status_code = 429
            response.headers['Retry-After'] = '60'
            return response
        request._rate_remaining = remaining()
    return None


def _security_and_access_log(response):
    """هدرهای امنیتی + شناسهٔ درخواست + محدودیت باقی‌مانده + لاگ گذر."""
    response.headers.setdefault('X-Content-Type-Options', 'nosniff')
    response.headers.setdefault('X-Frame-Options', 'SAMEORIGIN')
    response.headers.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
    response.headers.setdefault('X-Permitted-Cross-Domain-Policies', 'none')
    response.headers.setdefault('Permissions-Policy',
                                'camera=(), microphone=(), geolocation=()')

    from utils.request_id import request_id_header
    header = request_id_header()
    if header:
        response.headers[header[0]] = header[1]
    if hasattr(request, '_rate_remaining'):
        response.headers['X-RateLimit-Remaining'] = str(request._rate_remaining)

    # لاگ فقط برای نوشتن‌ها و خطاها (GET های عادی لاگ نمی‌شوند تا حجم کم بماند)
    if request.method != 'GET' or response.status_code >= 500:
        try:
            started = getattr(g, '_request_started', None)
            duration = (time.monotonic() - started) * 1000 if started else None
            rid = getattr(g, 'request_id', '-')
            current_app.logger.info(
                '[%s] %s %s -> %s%s', rid, request.method, request.path,
                response.status_code,
                f' ({duration:.0f}ms)' if duration is not None else '')
        except Exception:                        # noqa: BLE001 — لاگ هرگز پاسخ را نشکند
            pass
    return response


_GZIP_TYPES = ('text/', 'javascript', 'json', 'xml', 'svg', 'font')


def _gzip_response(response):
    """فشرده‌سازی HTML/CSS/JSON — CSS بوت‌استرپ ۲۲۸KB است؛ روی خط ضعیف محسوس است.

    فایل‌های استاتیک از send_file معمولاً direct_passthrough هستند و رد می‌شوند
    (کش مرورگر کافی است). فقط پاسخ‌های قالب/JSON فشرده می‌شوند.
    """
    try:
        if getattr(response, 'direct_passthrough', False):
            return response
        if response.status_code < 200 or response.status_code >= 300:
            return response
        if response.headers.get('Content-Encoding'):
            return response
        accept = request.headers.get('Accept-Encoding', '')
        if 'gzip' not in accept.lower():
            return response
        ctype = (response.headers.get('Content-Type') or '').lower()
        if not any(token in ctype for token in _GZIP_TYPES):
            return response
        data = response.get_data()
        if not data or len(data) < 800:
            return response
        import gzip
        compressed = gzip.compress(data, compresslevel=4)
        if len(compressed) >= len(data) - 64:
            return response
        response.set_data(compressed)
        response.headers['Content-Encoding'] = 'gzip'
        response.headers['Content-Length'] = str(len(compressed))
        vary = response.headers.get('Vary', '')
        if 'Accept-Encoding' not in vary:
            response.headers['Vary'] = (vary + ', Accept-Encoding').lstrip(', ')
    except Exception:                            # noqa: BLE001 — فشرده‌سازی هرگز پاسخ را نشکند
        pass
    return response
