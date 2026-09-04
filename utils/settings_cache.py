"""
کش درخواست‌محور تنظیمات سیستم — پایان «یک کوئری برای هر render»
═══════════════════════════════════════════════════════════════════════
مشکل: context processor (هر قالب) و /manifest.webmanifest هر بار
`SystemSettings.query.first()` می‌زدند؛ با ۱۵ قالب partial در یک صفحه،
۱۵ کوئری یکسان. راه‌حل: یک نمونه در هر درخواست (g) — خارج از درخواست
(زمان‌بند/استخراج) تازه از دیتابیس خوانده می‌شود.
"""
from __future__ import annotations

from flask import g, has_request_context

from models.system import SystemSettings


def get_system_settings(refresh: bool = False):
    """تنظیمات سیستم؛ در هر درخواست فقط یک کوئری (refresh اجباری بی‌اعتبار می‌کند)."""
    if not has_request_context():
        return SystemSettings.query.first()

    cached = getattr(g, '_system_settings', None)
    if cached is None or refresh:
        cached = SystemSettings.query.first()
        g._system_settings = cached
    return cached
