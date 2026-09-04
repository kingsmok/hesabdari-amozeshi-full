"""
شناسهٔ درخواست (Request-ID) — همبستگی لاگ‌ها و ردیابی میدانی (Observability)
════════════════════════════════════════════
بدون این، وقتی کاربر می‌گوید «یک خطا دیدم»، در لاگ هیچ راهی نیست که بفهمیم
کدام درخواست همان خطا بود (چندین کاربر هم‌زمان کار می‌کنند).

• هر درخواست: `g.request_id` (از هدر ورودی `X-Request-ID` یا uuid کوتاه)
• هر پاسخ: هدر `X-Request-ID` → کاربر/پروکسی می‌تواند همان شناسه را برگرداند
• لاگ خطاها و درخواست‌ها همین شناسه را چاپ می‌کنند → «چرا خطا؟» در ۱۰ ثانیه
"""
from __future__ import annotations

import uuid

from flask import g, has_request_context, request


def start_request_id() -> str:
    """در before_request صدا زده می‌شود؛ شناسهٔ پایدار برای این درخواست."""
    rid = (request.headers.get('X-Request-ID') or '').strip()[:64]
    if not rid:
        rid = uuid.uuid4().hex[:16]
    g.request_id = rid
    return rid


def current_request_id() -> str | None:
    """شناسهٔ درخواست جاری (برای قرارداد API و لاگ)."""
    if not has_request_context():
        return None
    return getattr(g, 'request_id', None)


def request_id_header() -> tuple[str, str] | None:
    """برای after_request: (نام هدر، مقدار) یا None."""
    rid = current_request_id()
    return ('X-Request-ID', rid) if rid else None
