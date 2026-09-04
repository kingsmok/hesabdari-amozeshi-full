"""
ثبت مرکزی رویدادها — Activity Log (DRY)
════════════════════════════════════════════
پیش از این، ۵ ماژول route هرکدام `_log`/`_log_payment_action`/`_log_tax` جدا داشت
و ۱۸ جا مستقیم `ActivityLog(...)` می‌ساختند؛ همه یک کار را با کد کپی‌شده انجام
می‌دادند (نقض DRY) و هر جا یک‌بار هم `module` اشتباه می‌گذاشتند.

این ماژول یک نقطهٔ واحد است:
  • کاربر/آی‌پی خودکار از context جاری خوانده می‌شوند؛
  • خطای لاگ هرگز عملیات اصلی (مثلاً ثبت پرداخت) را نمی‌شکند؛
  • `commit=True` برای رویدادهای مستقلی که خارج از تراکنش اصلی ثبت می‌شوند.
"""
from __future__ import annotations

from flask import has_request_context, request
from flask_login import current_user

from extensions import db
from models.user import ActivityLog


def _current_user_id():
    try:
        if current_user.is_authenticated:
            return current_user.id
    except Exception:                      # noqa: BLE001 — خارج از context لاگین
        return None
    return None


def _current_ip() -> str | None:
    if has_request_context():
        return request.remote_addr
    return None


def log_activity(action: str, description: str, *,
                 module: str = 'system',
                 entity_type: str | None = None,
                 entity_id: int | None = None,
                 user_id: int | None = None,
                 ip_address: str | None = None,
                 commit: bool = False) -> ActivityLog | None:
    """افزودن یک ردیف رویداد؛ خروجی None یعنی ثبت نشد (هرگز exception نمی‌دهد).

    پارامترهای `user_id/ip_address` فقط وقتی لازم‌اند که از «کاربر جاری»
    استفاده نشود (مثلاً رویدادهای ناشناس/مدیران ربات).
    """
    try:
        log = ActivityLog(
            user_id=user_id if user_id is not None else _current_user_id(),
            action=(action or 'system')[:50],
            module=(module or 'system')[:50],
            entity_type=(entity_type or None),
            entity_id=entity_id,
            description=(description or '')[:2000],
            ip_address=ip_address if ip_address is not None else _current_ip(),
        )
        db.session.add(log)
        if commit:
            db.session.commit()
        return log
    except Exception:                      # noqa: BLE001 — لاگ نباید عملیات را بشکند
        db.session.rollback()
        return None
