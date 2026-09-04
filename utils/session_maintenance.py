"""
نگهداری نشست‌ها — حذف سوابق کهنه
════════════════════════════════════════════
پیش از این `user_sessions` هیچ‌وقت پاک نمی‌شد: هر ورود/خروج یک ردیف می‌گذاشت
و جدول در نصب‌های پرکاربرد بی‌نهایت بزرگ می‌شد (رشد پایدار دیتابیس — معادل
«نشت حافظه» در سطح داده). سوابقِ لاگ فعالیت هم با همان نرخ رشد می‌کنند.

قاعده:
  • نشست‌های بستهٔ قدیمی‌تر از ۹۰ روز و نشست‌های بازِ قدیمی‌تر از ۶۰ روز
    (که یعنی کاربر بدون logout خارج شده) حذف می‌شوند؛
  • فعالیت‌های قدیمی‌تر از یک سال فقط یک‌بار در روز (در بوت) پاک می‌شوند؛
  • کارها فقط در بوت (ترد جدا) اجرا می‌شوند و خطاها هرگز بوت را نمی‌شکنند.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta


def _last_cleanup_file(base_dir: str) -> str:
    folder = os.path.join(base_dir, 'instance')
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, '.session_cleanup_stamp')


def _stamp_ok(base_dir: str) -> bool:
    """فقط یک‌بار در روز اجرا می‌شویم (بوت‌های متعدد بی‌فایده نباشند)."""
    stamp = _last_cleanup_file(base_dir)
    try:
        last = os.path.getmtime(stamp)
        return (datetime.now() - datetime.fromtimestamp(last)) > timedelta(hours=20)
    except OSError:
        return True


def _touch(base_dir: str) -> None:
    try:
        with open(_last_cleanup_file(base_dir), 'w', encoding='utf-8'):
            pass
    except OSError:
        pass


def run_session_maintenance(app) -> str:
    """پاک‌سازی نشست‌ها/لاگ‌های کهنه؛ خروجی: پیام وضعیت برای لاگ بوت."""
    from extensions import db
    from models.user import ActivityLog, UserSession

    base_dir = app.config.get('BASE_DIR') or app.root_path
    if not _stamp_ok(base_dir):
        return 'نگهداری نشست‌ها: امروز انجام شده'

    removed_sessions = removed_logs = 0
    try:
        now = datetime.utcnow()
        # برای سازگاری با هر دو دیالکت (SQLite/MySQL/PG) از آستانهٔ تاریخ استفاده می‌کنیم
        closed_cutoff = now - timedelta(days=90)
        open_cutoff = now - timedelta(days=60)
        closed_count = UserSession.query.filter(
            UserSession.is_active.is_(False),
            UserSession.login_at < closed_cutoff,
        ).delete(synchronize_session=False)
        open_count = UserSession.query.filter(
            UserSession.is_active.is_(True),
            UserSession.login_at < open_cutoff,
        ).delete(synchronize_session=False)
        removed_sessions = closed_count + open_count

        # لاگ فعالیت‌های قدیمی‌تر از یک سال (تاریخچهٔ مفید معمولاً کوتاه‌تر است)
        log_cutoff = now - timedelta(days=365)
        removed_logs = ActivityLog.query.filter(
            ActivityLog.created_at < log_cutoff,
        ).delete(synchronize_session=False)

        db.session.commit()
        _touch(base_dir)
        detail = (f'نشست‌های کهنه حذف شد: {removed_sessions}، '
                  f'ردیف‌های لاگ قدیمی: {removed_logs}')
        app.logger.info('session maintenance: %s', detail)
        return detail
    except Exception as exc:               # noqa: BLE001
        db.session.rollback()
        app.logger.warning('session maintenance failed: %s', exc)
        return f'نگهداری نشست‌ها ناموفق بود: {exc}'
