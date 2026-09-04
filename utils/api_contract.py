"""
قرارداد یکپارچهٔ API — پاسخ‌های JSON با ساختار ثابت (Contract Design)
════════════════════════════════════════════
در پروژه، پاسخ‌های JSON هر مسیر شکل خودش را داشتند: یکی `{results: ...}`،
یکی `{ok: true, ...}`، یکی پیام خطای آزاد. برای کلاینت‌های جدید (پنل موبایل،
ربات، یکپارچه‌سازی AI) این یعنی هر endpoint یک قرارداد جدا دارد.

این ماژول یک قرارداد واحد می‌دهد:
    موفق:   {ok: true,  data: ..., request_id: ...}
    خطا:    {ok: false, error: {code, message}, request_id: ...}

برای سازگاری کامل با کدهای موجود، مسیرها می‌توانند فیلدهای قدیمی خودشان را
هم در `data` نگه دارند (مثلاً `results`) — اینجا فقط ساختار بیرونی یکنواخت
می‌شود و تا زمانی که مسیرها مهاجرت نکرده‌اند، هیچ‌چیز نمی‌شکند.
"""
from __future__ import annotations

from flask import jsonify

try:                                      # noqa: SIM105 — request_id اختیاری
    from utils.request_id import current_request_id
except Exception:                        # pragma: no cover
    def current_request_id():             # type: ignore[no-redef]
        return None


def ok(data=None, status: int = 200, **extra):
    """پاسخ موفق با قرارداد واحد."""
    payload = {'ok': True, 'data': data}
    payload.update(extra)                                # فیلدهای قدیمی/خاص مسیر
    rid = current_request_id()
    if rid:
        payload['request_id'] = rid
    return jsonify(payload), status


def error(message: str, *, code: str = 'BAD_REQUEST', status: int = 400, **extra):
    """پاسخ خطا با قرارداد واحد."""
    payload = {
        'ok': False,
        'error': {'code': code, 'message': message},
    }
    payload.update(extra)
    rid = current_request_id()
    if rid:
        payload['request_id'] = rid
    return jsonify(payload), status
