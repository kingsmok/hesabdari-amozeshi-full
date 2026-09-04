"""
بوت‌استرپ زمان‌اجرا — زمان‌بند پشتیبان‌گیری و poller ربات بله.
دو نگرانی قبلی که این‌جا اصلاح شد:
  ۱) زمان‌بند و ترد هیچ‌وقت متوقف نمی‌شدند (چرخهٔ زندگی نامشخص)؛ حالا در
     `atexit` و `teardown_appcontext` متوقف می‌شوند.
  ۲) ترد poller بدون قفلِ بین‌پروسه‌ای بود؛ با چند ورکر Gunicorn، چند poller
     هم‌زمان اجرا می‌شد (پیام‌های تکراری!). این‌جا با lockfile تکی‌نمونه می‌شود
     (اکثر pollerها با ادعای pid: اگر پروسهٔ دارنده مرده باشد، قفل منتقل
     می‌شود — برخلاف قفل سادهٔ O_CREAT|O_EXCL که بعد از crash تا ابد می‌ماند).
"""
from __future__ import annotations

import atexit
import os
import threading


# ══════════════════════════════════════════════════════════════
#  زمان‌بند پشتیبان‌گیری خودکار
# ══════════════════════════════════════════════════════════════
def start_scheduler(app) -> None:
    """زمان‌بند پشتیبان (۱ ساعته، تصمیم با تنظیمات سیستم)."""
    if (os.environ.get('ACADEMY_DISABLE_SCHEDULER') == '1'
            or app.config.get('DISABLE_SCHEDULER')):
        app.logger.info('[SCHEDULER] Skipped (DISABLE_SCHEDULER) — مناسب آزمون‌ها')
        return
    try:
        from apscheduler.schedulers.background import BackgroundScheduler

        scheduler = BackgroundScheduler()
        scheduler.add_job(_scheduled_backup, 'interval', hours=1,
                          id='auto_backup', replace_existing=True,
                          args=[app])
        scheduler.start()
        app.extensions['backup_scheduler'] = scheduler
        atexit.register(_shutdown_scheduler, scheduler)
        app.logger.info('[SCHEDULER] Auto-backup scheduler started.')
    except Exception as exc:                        # noqa: BLE001
        app.logger.warning('[SCHEDULER] Scheduler not started: %s', exc)


def _scheduled_backup(app):
    """اجرای پشتیبان زمان‌بندی‌شده؛ app به‌جای current_app (اپ خارج از درخواست)."""
    try:
        with app.app_context():
            from license_client import has_feature
            if not has_feature('backup'):
                app.logger.info('[BACKUP] Skipped — بخش پشتیبان‌گیری در لایسنس فعال نیست')
                return
            from utils.backup_service import run_scheduled_backup
            app.logger.info('[BACKUP] %s', run_scheduled_backup())
    except Exception as exc:                        # noqa: BLE001
        app.logger.exception('[BACKUP] Auto-backup error: %s', exc)


def _shutdown_scheduler(scheduler) -> None:
    try:
        if scheduler.running:
            scheduler.shutdown(wait=False)
    except Exception:                               # noqa: BLE001
        pass


# ══════════════════════════════════════════════════════════════
#  Poller ربات بله (Long Polling) — تک‌نمونه بین‌ورکری
# ══════════════════════════════════════════════════════════════
def start_bale(app) -> None:
    """شروع poller فقط وقتی لایسنس «اتصالات» باز است و قفل در دست ماست."""

    def _boot():
        try:
            from license_client import get_state
            if not get_state().has_feature('integrations'):
                return
            lock = _acquire_single_instance(app.config.get('BASE_DIR', app.root_path))
            if not lock:
                app.logger.info('[BALE] polling skipped — نمونهٔ دیگر اجرا می‌کند')
                return
            with app.app_context():
                from utils.bot_services import start_bale_polling_if_configured
                start_bale_polling_if_configured(app)
        except Exception as exc:                    # noqa: BLE001
            app.logger.info('bale polling not started: %s', exc)

    threading.Thread(target=_boot, name='bale-polling-boot', daemon=True).start()


def _acquire_single_instance(base_dir: str) -> bool:
    """قفل lockfile با PID و تشخیص مرگِ دارنده — تک‌نمونه در چند ورکر.

    آن‌قدر که ممکن است در SQLite/هست؛ قفل‌های پروسه‌ای ساده با crash می‌مانند
    و پشتیبان/ربات برای همیشه خاموش می‌شود؛ این نسخه خودترمیم است.
    """
    lock_path = os.path.join(base_dir, 'instance', '.bale_poll.lock')
    try:
        os.makedirs(os.path.dirname(lock_path), exist_ok=True)
        if os.path.exists(lock_path):
            with open(lock_path, encoding='utf-8') as handle:
                owner_pid = int(handle.read().strip() or 0)
            if owner_pid and _pid_alive(owner_pid):
                return False
        with open(lock_path, 'w', encoding='utf-8') as handle:
            handle.write(str(os.getpid()))
        return True
    except Exception:                               # noqa: BLE001
        # در محیط‌هایی که گارد فایل ندارند (ویندوز/دسکتاپ) به ترد محلی بسنده می‌کنیم
        return True


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def stop_runtime(app) -> None:
    """توقف اجزای زمان‌اجرا هنگام تخریب اپ (تست‌ها/بازگشایی/دسکتاپ)."""
    scheduler = app.extensions.get('backup_scheduler')
    if scheduler is not None:
        _shutdown_scheduler(scheduler)
    try:
        from utils.bot_services import bale_polling_manager
        bale_polling_manager.stop()      # stop_event ترد poller — ترد daemon است
    except Exception:                    # noqa: BLE001
        pass
