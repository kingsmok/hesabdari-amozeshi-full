"""
سیستم جامع مدیریت آموزشگاه — Academy Manager Pro
═══════════════════════════════════════════════════════════════════════
app.py از این نسخه فقط «Composition Root» است: هیچ منطقی ندارد، فقط
قطعه‌های مستقل بوت‌استرپ را به ترتیب درست کنار هم می‌گذارد.

هر قطعه در پکیج bootstrap/ با یک مسئولیت است (SRP):
  config      → کانفیگ، لاگر، پوشه‌های runtime
  extensions  → Flask-SQLAlchemy/Login/Migrate/CSRF
  license     → فعال‌سازی لایسنس (باید قبل از بلوپرینت‌ها باشد)
  middleware  → request-id، rate-limit، هدرهای امنیتی، لاگ گذر
  blueprints  → ثبت داده‌محور ۳۰+ بلوپرینت (بالاخره دیگر ۶۰ خط import نیست)
  web         → PWA/فیلترها/globals/context processor/هندلرهای خطا
  schema      → create_all + پچ‌های ستون + دادهٔ پایه + اصلاحات داده
  runtime     → زمان‌بند پشتیبان + poller ربات بله (با خاموشی تمیز)

API عمومی منعقدشده با entry pointها (first_run / app_desktop / wsgi /
passenger_wsgi) و PyInstaller و تست‌ها بدون تغییر ماند:
    create_app() -> Flask
    create_default_data() -> None            (از bootstrap.defaults)
"""
import weakref

from flask import Flask

# ── کلاس بوت‌استرپ (ترتیب ثبت‌ها در یک جا مستند می‌شود) ─────────────────
_BOOT_ORDER = (
    'config',        # ۱. کانفیگ + پوشه‌ها (+لاگر)                — قبل از هر چیز
    'extensions',    # ۲. اکستنشن‌ها
    'middleware',    # ۳. before/after_request عمومی
    'license',       # ۴. لایسنس — لازم‌است قبل از ثبت مسیرها باشد
    'blueprints',    # ۵. همهٔ روت‌ها
    'web',           # ۶. فیلتر/globals/PWA/خطاها
    'schema',        # ۷. create_all/پچ‌ها/دادهٔ پیش‌فرض (idempotent)
    'runtime',       # ۸. زمان‌بند + poller (پس از schema و لایسنس)
)


def create_app():
    """ساخت و راه‌اندازی کامل برنامه (تنها API عمومی این ماژول)."""
    from bootstrap.config import setup as setup_config
    from bootstrap.extensions import setup as setup_extensions
    from bootstrap.license import access_guard, setup as setup_license
    from bootstrap.blueprints import register_all
    from bootstrap.middleware import setup as setup_middleware
    from bootstrap.runtime import start_bale, start_scheduler, stop_runtime
    from bootstrap.schema import initialize as initialize_schema
    from bootstrap.web import setup as setup_web

    app = Flask(__name__)
    setup_config(app)                                   # ۱
    setup_extensions(app)                               # ۲
    setup_middleware(app)                               # ۳
    setup_license(app)                                  # ۴

    register_all(app)                                   # ۵
    access_guard(app)          # نگهبان دسترسی باید بعد از ثبت بلوپرینت‌ها باشد

    setup_web(app)                                      # ۶

    initialize_schema(app)                              # ۷ (با app_context)

    start_scheduler(app)                                # ۸
    start_bale(app)
    # خاموشی تمیز وقتی اپ آزاد شد (تمرکز: تست‌ها چند اپ می‌سازند و PyQt هم
    # بارها؛ بدون این، ترد زمان‌بند/پولر نشت می‌کرد)
    weakref.finalize(app, stop_runtime, app)      # هنگام GC اپ: توقف تمیز

    return app


# ═══════════════════════════════════════════════════════════════════════
#  سازگاری عقب‌رو: create_default_data از app.py قابل import بود
#  (first_run.py و برخی ابزارها آن را صدا می‌زنند) — اکنون یک re-export است.
# ═══════════════════════════════════════════════════════════════════════
def create_default_data():
    """دادهٔ پایهٔ نصب تازه (re-export از bootstrap.defaults برای سازگاری)."""
    from bootstrap.defaults import create_default_data as _impl
    return _impl()


if __name__ == '__main__':
    _app = create_app()
    # reloader چند پردازه می‌سازد و برای Long Polling بله مناسب نیست.
    _app.run(debug=False, host='0.0.0.0', port=5000, use_reloader=False)
