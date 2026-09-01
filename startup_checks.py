"""
بررسی سازگاری نسخه‌ها پیش از اجرای برنامه — Academy Manager Pro

مشکل شناخته‌شده (github.com/sqlalchemy/sqlalchemy/issues/11334):
نسخه‌های SQLAlchemy قدیمی‌تر از ۲.۰.۳۱ با پایتون ۳.۱۳ و ۳.۱۴ سازگار نیستند
و هنگام import با خطای زیر متوقف می‌شوند:

    AssertionError: Class ... directly inherits TypingOnly but has
    additional attributes {'__firstlineno__', '__static_attributes__'}

روی هاست (Python 3.11 + Passenger/WSGI) این باگ وجود ندارد؛ آنجا فقط
SQLAlchemy ۲.۰ کافی است و هرگز pip یا input() اجرا نمی‌شود.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys

# Flask-SQLAlchemy 3.1 به SQLAlchemy ۲.۰ نیاز دارد
MIN_SQLALCHEMY_BASE = (2, 0, 16)
# اولین نسخه که با پایتون ۳.۱۳/۳.۱۴ کار می‌کند
MIN_SQLALCHEMY_PY313 = (2, 0, 31)
MIN_SQLALCHEMY = MIN_SQLALCHEMY_PY313  # برای پیام‌ها و سازگاری با آزمون‌های قدیمی
SQLALCHEMY_UPGRADE_SPEC = "SQLAlchemy>=2.0.31"
REEXEC_GUARD_ENV = "ACADEMY_SA_REEXEC"


def parse_version(value):
    """تبدیل رشته نسخه به تاپل عددی برای مقایسه، مثل (2, 0, 31)."""
    nums = re.findall(r"\d+", str(value or ""))
    return tuple(int(n) for n in nums[:3]) if nums else (0,)


def min_sqlalchemy_required(python_version=None):
    """حداقل نسخه SQLAlchemy بر اساس نسخه پایتون."""
    py = python_version or sys.version_info
    if py >= (3, 13):
        return MIN_SQLALCHEMY_PY313
    return MIN_SQLALCHEMY_BASE


def format_version(ver):
    return ".".join(str(n) for n in ver[:3])


def installed_sqlalchemy_version():
    """نسخه نصب‌شده را بدون import کردن خود بسته برمی‌گرداند (یا None)."""
    try:
        from importlib.metadata import PackageNotFoundError, version
    except ImportError:  # pragma: no cover - پایتون خیلی قدیمی
        return None
    try:
        return version("sqlalchemy")
    except PackageNotFoundError:
        return None
    except Exception:
        return None


def sqlalchemy_is_compatible(version_str, python_version=None):
    """آیا این رشته نسخه با این پایتون سازگار است؟"""
    if not version_str:
        return False
    return parse_version(version_str) >= min_sqlalchemy_required(python_version)


def _is_frozen():
    return bool(getattr(sys, "frozen", False))


def _in_tests():
    return "pytest" in sys.modules or bool(os.environ.get("PYTEST_CURRENT_TEST"))


def _is_interactive():
    try:
        return bool(sys.stdin and sys.stdin.isatty())
    except Exception:
        return False


def running_on_host():
    """
    تشخیص اجرای روی هاست (cPanel Passenger / WSGI).
    در این حالت pip و input() نباید اجرا شوند.
    """
    if os.environ.get("PASSENGER_APP_ENV") or os.environ.get("IN_PASSENGER"):
        return True
    if "passenger_wsgi" in sys.modules or "wsgi" in sys.modules:
        return True
    script = os.path.basename(sys.argv[0] if sys.argv else "")
    if script in {"passenger_wsgi.py", "wsgi.py"}:
        return True
    return False


def should_auto_fix():
    """آیا اجازه داریم pip را برای رفع ناسازگاری اجرا کنیم؟"""
    if _is_frozen() or _in_tests() or running_on_host():
        return False
    if not _is_interactive():
        return False
    flag = os.environ.get("ACADEMY_NO_AUTOFIX", "").strip().lower()
    if flag in {"1", "true", "yes", "on"}:
        return False
    return True


def _looks_like_typingonly(exc):
    text = str(exc or "")
    return "TypingOnly" in text or "__firstlineno__" in text or "__static_attributes__" in text


def try_import_sqlalchemy():
    """
    تلاش برای import.
    برمی‌گرداند: (version_or_None, error_or_None)
    AssertionError مربوط به TypingOnly را قورت می‌دهد تا traceback خام دیده نشود.
    """
    try:
        import sqlalchemy
    except ImportError as exc:
        return None, exc
    except AssertionError as exc:
        return None, exc
    except Exception as exc:
        return None, exc
    return getattr(sqlalchemy, "__version__", None), None


def diagnose_sqlalchemy(python_version=None):
    """
    وضعیت SQLAlchemy را بدون کرش کردن برنامه تشخیص می‌دهد.

    کلیدهای خروجی:
        ok, version, reason, error
        reason: ok | missing | too_old | typingonly | import_error
    """
    py = python_version or sys.version_info
    meta = installed_sqlalchemy_version()
    if meta is not None and not sqlalchemy_is_compatible(meta, py):
        return {
            "ok": False,
            "version": meta,
            "reason": "too_old",
            "error": None,
        }

    imported, err = try_import_sqlalchemy()
    if err is None:
        version = imported or meta
        if sqlalchemy_is_compatible(version, py):
            return {"ok": True, "version": version, "reason": "ok", "error": None}
        return {
            "ok": False,
            "version": version,
            "reason": "too_old" if version else "missing",
            "error": None,
        }

    if isinstance(err, ImportError) and meta is None:
        return {"ok": False, "version": None, "reason": "missing", "error": err}
    if _looks_like_typingonly(err):
        return {
            "ok": False,
            "version": meta,
            "reason": "typingonly",
            "error": err,
        }
    if meta is not None and not sqlalchemy_is_compatible(meta, py):
        return {"ok": False, "version": meta, "reason": "too_old", "error": err}
    return {
        "ok": False,
        "version": meta,
        "reason": "import_error",
        "error": err,
    }


def _print_incompatible(diag, py_ver):
    version = diag.get("version") or "نامشخص"
    reason = diag.get("reason")
    need = format_version(min_sqlalchemy_required())
    print(f"  ✗ SQLAlchemy با پایتون {py_ver} سازگار نیست.")
    if reason == "missing":
        print("    کتابخانه SQLAlchemy نصب نیست.")
        print("    روی هاست:  pip install -r requirements.txt")
    elif reason == "too_old":
        print(f"    نسخه نصب‌شده: {version}  —  حداقل لازم: {need}")
        if sys.version_info >= (3, 13):
            print("    نسخه‌های قدیمی هنگام اجرا با خطای TypingOnly متوقف می‌شوند")
            print("    (__firstlineno__ / __static_attributes__).")
    elif reason == "typingonly":
        print(f"    نسخه نصب‌شده: {version}")
        print("    خطای TypingOnly هنگام بارگذاری SQLAlchemy رخ داد.")
        print("    این خطا مخصوص پایتون ۳.۱۳/۳.۱۴ و SQLAlchemy قدیمی است.")
        print("    هاست Python 3.11 این مشکل را ندارد.")
    else:
        print(f"    نسخه: {version}")
        err = diag.get("error")
        if err:
            print(f"    جزئیات: {err}")


def _print_manual_fix():
    print()
    if running_on_host():
        print("    روی هاست (Python 3.11)، در Terminal همان اپلیکیشن:")
        print("      pip install -r requirements.txt")
        print("    سپس اپلیکیشن را Restart کنید.")
    else:
        print("    راه‌حل دستی (در همان پوشه برنامه):")
        print(f'      {sys.executable} -m pip install --upgrade "{SQLALCHEMY_UPGRADE_SPEC}"')
        print("    یا نصب کامل وابستگی‌ها:")
        print(f"      {sys.executable} -m pip install -r requirements.txt --upgrade")
        print("    سپس برنامه را دوباره اجرا کنید.")
        print()
        print("    دسکتاپ ویندوز: پایتون ۳.۱۱ یا ۳.۱۲ پایدارترین گزینه است.")
        print("    هاست: Python 3.11 — فقط pip install -r requirements.txt")


def upgrade_sqlalchemy():
    """نصب/ارتقا SQLAlchemy با pip. True اگر دستور pip موفق باشد."""
    if _is_frozen() or running_on_host():
        return False
    cmd = [sys.executable, "-m", "pip", "install", "--upgrade", SQLALCHEMY_UPGRADE_SPEC]
    print("  در حال نصب نسخه سازگار SQLAlchemy...")
    print("   ", " ".join(cmd))
    try:
        result = subprocess.run(cmd, check=False)
    except OSError as exc:
        print(f"  ✗ اجرای pip ناموفق بود: {exc}")
        return False
    if result.returncode != 0:
        print(f"  ✗ pip با کد {result.returncode} متوقف شد.")
        return False
    new_ver = installed_sqlalchemy_version()
    if new_ver and sqlalchemy_is_compatible(new_ver):
        print(f"  ✓ SQLAlchemy {new_ver} نصب شد.")
        return True
    print(f"  ⚠ پس از نصب، نسخه خوانده‌شده {new_ver or 'نامشخص'} است.")
    return bool(new_ver and sqlalchemy_is_compatible(new_ver))


def reexec_current_process(extra_env=None):
    """جایگزینی پروسه فعلی با همان دستور — لازم است چون ماژول خراب در حافظه مانده."""
    if extra_env:
        os.environ.update(extra_env)
    python = sys.executable
    argv = [python, *sys.argv]
    os.execv(python, argv)


def _pause_and_exit(code=1):
    print("\n  پس از اصلاح، دوباره برنامه را اجرا کنید.")
    if _is_interactive() and not running_on_host():
        try:
            input("  برای بستن، Enter را فشار دهید...")
        except (EOFError, KeyboardInterrupt):
            pass
    sys.exit(code)


def ensure_compatible(exit_on_error=True, auto_fix=None):
    """
    بررسی پایتون و SQLAlchemy قبل از لود شدن برنامه.

    روی هاست Python 3.11 فقط در صورت نبودن/خراب بودن SQLAlchemy خطا می‌دهد؛
    pip خودکار و input() هرگز روی Passenger اجرا نمی‌شوند.
    """
    py_ver = sys.version.split()[0]

    if sys.version_info < (3, 10):
        print(f"  ⚠ هشدار: پایتون {py_ver} قدیمی است؛ نسخه ۳.۱۰ به بالا توصیه می‌شود.")
    elif sys.version_info >= (3, 14) and not running_on_host():
        print(
            f"  ℹ پایتون {py_ver} خیلی جدید است؛ "
            "۳.۱۱ یا ۳.۱۲ توصیه می‌شود (ادامه با بررسی SQLAlchemy)."
        )

    diag = diagnose_sqlalchemy()
    if diag["ok"]:
        return True

    _print_incompatible(diag, py_ver)

    already_tried = os.environ.get(REEXEC_GUARD_ENV) == "1"
    do_fix = should_auto_fix() if auto_fix is None else bool(auto_fix)
    version_already_new = sqlalchemy_is_compatible(diag.get("version"))

    if do_fix and not _is_frozen() and not running_on_host() and not already_tried and not version_already_new:
        if upgrade_sqlalchemy():
            print("  برنامه دوباره راه‌اندازی می‌شود...\n")
            try:
                reexec_current_process({REEXEC_GUARD_ENV: "1"})
            except OSError as exc:
                print(f"  ✗ راه‌اندازی مجدد ناموفق بود: {exc}")
                print("    لطفاً برنامه را خودتان دوباره اجرا کنید.")
                if exit_on_error:
                    _pause_and_exit(0)
                return False
        else:
            _print_manual_fix()
    else:
        if already_tried:
            print("  ⚠ ارتقای SQLAlchemy انجام شد اما مشکل باقی است.")
        if version_already_new and diag.get("reason") == "typingonly":
            print("  ⚠ حتی SQLAlchemy جدید با این نسخه پایتون بارگذاری نشد.")
            print("    پایتون ۳.۱۱ یا ۳.۱۲ را نصب کنید و دوباره تلاش کنید.")
        if _is_frozen():
            print("    نسخه نصب‌شده برنامه را به‌روز کنید یا از روی سورس با")
            print(f'    pip install --upgrade "{SQLALCHEMY_UPGRADE_SPEC}" اجرا کنید.')
        else:
            _print_manual_fix()

    if exit_on_error:
        _pause_and_exit(1)
    return False
