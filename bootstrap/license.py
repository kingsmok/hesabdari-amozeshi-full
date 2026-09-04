"""
بوت‌استرپ لایسنس — فعال‌سازی قبل از ثبت هر مسیر و نگهبان دسترسی.
(ترتیبِ init_license → بلوپرینت‌ها → init_access_guard حیاتی است.)
"""
from __future__ import annotations


def setup(app) -> None:
    from license_client import init_license
    init_license(app)


def access_guard(app) -> None:
    """ثبت نگهبان سراسری نقش/اکشن روی همهٔ مسیرها (پس از ثبت Blueprintها)."""
    from utils.access_policy import init_access_guard
    init_access_guard(app)
