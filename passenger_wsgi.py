"""Passenger WSGI entry for cPanel / shared hosting (Python 3.11).

نکات هاست اشتراکی که این‌جا رعایت شده:
  • تردهای پس‌زمینه (زمان‌بند پشتیبان + پولر بله) روی هاست اشتراکی هم منابع
    را هدر می‌دهند و هم توسط میزبان کشته می‌شوند؛ پس پیش‌فرض خاموش‌اند مگر
    این‌که اپراتور صراحتاً با 0 روشنشان کند.
  • پوشه‌های runtime پیش از بوت ساخته می‌شوند تا خطای «قابل نوشتن نیست»
    با پیام روشن در لاگ بیاید، نه 500 بی‌توضیح.
  • هر خطای بوت در logs/passenger_error.log هم نوشته می‌شود تا بدون دسترسی
    به لاگ آپاچی هم علت پیدا شود.
"""
import os
import sys
import traceback

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# قبل از import برنامه علامت هاست را می‌گذاریم تا startup_checks
# هرگز pip یا input() را روی Passenger اجرا نکند.
os.environ.setdefault("PASSENGER_APP_ENV", os.environ.get("PASSENGER_APP_ENV", "production"))

# پیش‌فرض هاست اشتراکی: بدون ترد پس‌زمینه (روشن‌کردن دستی: مقدار 0 در
# Environment variables همان اپلیکیشن در Setup Python App).
os.environ.setdefault("ACADEMY_DISABLE_SCHEDULER", "1")
os.environ.setdefault("ACADEMY_DISABLE_BALE", "1")

# پوشه‌هایی که برنامه در زمان اجرا داخلشان می‌نویسد
_RUNTIME_DIRS = (
    "instance",
    "backups",
    "logs",
    os.path.join("static", "uploads"),
    os.path.join("static", "uploads", "students"),
    os.path.join("static", "uploads", "teachers"),
    os.path.join("static", "uploads", "certificates"),
    os.path.join("static", "uploads", "documents"),
)

for _dirname in _RUNTIME_DIRS:
    try:
        os.makedirs(os.path.join(BASE_DIR, _dirname), exist_ok=True)
    except OSError:
        pass

try:
    from app import create_app

    application = create_app()
except Exception:
    try:
        _log_dir = os.path.join(BASE_DIR, "logs")
        os.makedirs(_log_dir, exist_ok=True)
        with open(os.path.join(_log_dir, "passenger_error.log"), "a", encoding="utf-8") as _fh:
            _fh.write("=" * 70 + "\n")
            _fh.write(traceback.format_exc())
    except OSError:
        pass
    raise
