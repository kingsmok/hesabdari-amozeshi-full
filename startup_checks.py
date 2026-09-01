"""
بررسی سازگاری نسخه‌ها پیش از اجرای برنامه — Academy Manager Pro

مشکل شناخته‌شده (github.com/sqlalchemy/sqlalchemy/issues/11334):
نسخه‌های SQLAlchemy قدیمی‌تر از ۲.۰.۳۱ با پایتون ۳.۱۳ و ۳.۱۴ سازگار نیستند
و هنگام import با خطای زیر متوقف می‌شوند:

    AssertionError: Class ... directly inherits TypingOnly but has
    additional attributes {'__firstlineno__', '__static_attributes__'}

این ماژول پیش از هر import دیگری اجرا می‌شود و اگر نسخه‌ها ناسازگار باشند،
پیام راهنمای واضح (فارسی) نشان می‌دهد.
"""
import re
import sys

# اولین نسخه SQLAlchemy که با پایتون ۳.۱۳/۳.۱۴ کار می‌کند
MIN_SQLALCHEMY = (2, 0, 31)


def _parse_version(value):
    """تبدیل رشته نسخه به تاپل عددی برای مقایسه، مثل (2, 0, 31)"""
    nums = re.findall(r"\d+", str(value))
    return tuple(int(n) for n in nums[:3]) if nums else (0,)


def ensure_compatible(exit_on_error=True):
    """
    بررسی پایتون و SQLAlchemy قبل از لود شدن برنامه.
    در صورت ناسازگاری، راهنمای رفع مشکل چاپ می‌شود.
    """
    ok = True
    py_ver = sys.version.split()[0]

    if sys.version_info < (3, 10):
        print(f"  ⚠ هشدار: پایتون {py_ver} قدیمی است؛ نسخه ۳.۱۰ به بالا توصیه می‌شود.")

    try:
        import sqlalchemy
    except ImportError:
        print("  ✗ کتابخانه SQLAlchemy نصب نیست!")
        print("    راه‌حل:  pip install -r requirements.txt")
        ok = False
    else:
        sa_ver = getattr(sqlalchemy, "__version__", "?")
        if _parse_version(sa_ver) < MIN_SQLALCHEMY:
            print(f"  ✗ نسخه SQLAlchemy نصب‌شده ({sa_ver}) با پایتون {py_ver} ناسازگار است.")
            print("    نسخه‌های قدیمی SQLAlchemy باعث خطای «TypingOnly» و توقف برنامه می‌شوند.")
            print('    راه‌حل:  pip install --upgrade "SQLAlchemy>=2.0.31"')
            print("    یا نصب مجدد کامل:  pip install -r requirements.txt --upgrade")
            ok = False

    if not ok and exit_on_error:
        print("\n  پس از اصلاح، دوباره برنامه را اجرا کنید.")
        try:
            input("  برای بستن، Enter را فشار دهید...")
        except (EOFError, KeyboardInterrupt):
            pass
        sys.exit(1)

    return ok
