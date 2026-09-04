"""تنظیمات مشترک پوشش آزمون‌ها (pytest این فایل را قبل از ماژول‌ها بارگذاری می‌کند)

۱) ترد زمان‌بندی پشتیبان‌گیری خاموش می‌شود: هر ماژول آزمون با `create_app()` یک
   برنامه می‌سازد و آن برنامه *زندگی می‌کند*؛ ترد APSchedulerِ همهٔ آن اپ‌ها روی
   همان فایل SQLite می‌نویسد و قفل می‌کند ⇒ «database is locked» و آزمون‌های
   بی‌ربط می‌ترکند (در دیتابیس پرحجم محسوس‌تر است).
۲) در پایان هر ماژول، engine آزاد می‌شود تا اتصال‌های باز استخر، فایل دیتابیس
   را بین ماژول‌ها قفل نگه ندارند.

این فایل عمداً هیچ fixture مشترکی به تست‌ها نمی‌دهد؛ هر ماژول مستقل است و فقط
محیط/پاکسازی در اینجا انجام می‌شود.
"""
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

# باید پیش از import app (و ساخت هر اپلیکیشن) تنظیم شود
os.environ.setdefault('ACADEMY_DISABLE_SCHEDULER', '1')
# در آزمون‌ها زود شکست می‌خوریم تا قفل‌ماندن پنهان نماند (در production ۱۰ ثانیه است)
os.environ.setdefault('ACADEMY_SQLITE_BUSY_TIMEOUT', '2')

import pytest  # noqa: E402


@pytest.fixture(autouse=True, scope='module')
def _release_db_between_modules():
    yield
    try:
        from extensions import db
        if db.engine is not None:
            db.engine.dispose()
    except Exception:
        pass
