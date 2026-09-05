"""
بوت‌استرپ داده — ساخت/سازگاری schema و دادهٔ پایه.
منطق «مونتاژ schema» ۱ (create_all + پچ‌های ستون + دادهٔ پیش‌فرض + اصلاحات
idempotent) که قبلاً ۷۰ خط داخل create_app بود، اینجا یک مسئولیت مستقل است.
"""
from __future__ import annotations

import models.accounting
import models.attendance
import models.bot
import models.classes
import models.course
import models.exam
import models.finance
import models.registration
import models.student
import models.system
import models.teacher
import models.user

from extensions import db


def initialize(app) -> None:
    """ساخت/ارتقای schema و دادهٔ پایه؛ فقط یک‌بار به‌ازای هر اپ (idempotent)."""
    if getattr(app, '_db_initialized', False):
        return

    with app.app_context():               # create_all و همهٔ اصلاحات داده نیازمند context
        _initialize_with_context(app)

    app._db_initialized = True


def _initialize_with_context(app) -> None:
    _warn_unwritable_runtime_dirs(app)
    db.create_all()

    from utils.attendance_service import ensure_attendance_indexes
    ensure_attendance_indexes()

    from utils.database_tools import (ensure_accounting_columns,
                                      ensure_finance_columns,
                                      ensure_payroll_columns,
                                      ensure_settings_columns)
    ensure_settings_columns()
    ensure_accounting_columns()
    ensure_finance_columns()
    payroll_patch = ensure_payroll_columns()
    if payroll_patch.get('added') or payroll_patch.get('cancelled_duplicates'):
        app.logger.warning(
            'payroll schema patched: %s column(s) added, %s duplicate payslip(s) cancelled',
            payroll_patch['added'], payroll_patch['cancelled_duplicates'])

    from bootstrap.defaults import create_default_data
    create_default_data()

    # تکمیل ردیف‌های «نقش × ماژول × اکشن» (فقط اضافه؛ نصب‌های قدیمی قفل نمی‌شوند)
    from utils.access_policy import action_guard_enabled, backfill_role_actions
    if action_guard_enabled():
        added = backfill_role_actions()
        if added:
            app.logger.info('access policy: %d role-action permission row(s) added', added)

    # کانفیگ نصب‌کننده (config.ini): حساب مدیر + آدرس هاست
    from utils.installer_config import apply_installer_config
    note = apply_installer_config()
    if note:
        app.logger.info('installer config: %s', note)

    # اصلاح تاریخ‌های شمسیِ ذخیره‌شده در ستون میلادی (idempotent)
    from utils.database_tools import repair_legacy_jalali_dates
    repaired = repair_legacy_jalali_dates()
    if repaired:
        app.logger.warning('%s legacy Jalali date values were repaired', repaired)

    # نگهداری نشست‌ها/لاگ‌های کهنه (جلوگیری از رشد بی‌نهایت جداول)
    from utils.session_maintenance import run_session_maintenance
    app.logger.info('session maintenance: %s', run_session_maintenance(app))


def _warn_unwritable_runtime_dirs(app) -> None:
    """هشدار زودهنگام اگر پوشه‌های runtime قابل نوشتن نیستند (مشکل رایج هاست).

    روی هاست اشتراکی، فراموش‌شدن chmod روی instance/ یعنی «unable to open
    database file» و 500 بی‌توضیح؛ این هشدار علت را در لاگ روشن می‌کند.
    غیرکشنده است تا روی MySQL/Postgres (که instance حیاتی نیست) بوت نخوابد.
    """
    import os

    base = app.config.get('BASE_DIR') or app.root_path
    candidates = {
        'instance': os.path.join(base, 'instance'),
        'backups': app.config.get('BACKUP_FOLDER') or os.path.join(base, 'backups'),
        'uploads': app.config.get('UPLOAD_FOLDER') or os.path.join(base, 'static', 'uploads'),
    }
    try:
        from utils.logging_config import log_dir
        candidates['logs'] = log_dir(base)
    except Exception:
        candidates['logs'] = os.path.join(base, 'logs')
    for name, folder in candidates.items():
        try:
            os.makedirs(folder, exist_ok=True)
            if not os.access(folder, os.W_OK):
                app.logger.error(
                    'runtime dir "%s" is not writable (%s) — '
                    'on cPanel run: chmod 755 %s (or chown to the app user)',
                    name, folder, name)
        except Exception as exc:                       # noqa: BLE001 — فقط هشدار
            app.logger.error('runtime dir "%s" check failed (%s): %s', name, folder, exc)
