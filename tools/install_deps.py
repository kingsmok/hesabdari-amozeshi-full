"""
نصب هوشمند وابستگی‌ها — Academy Manager Pro

چرا این فایل وجود دارد؟
═══════════════════════
خطای رایج هنگام `pip install -r requirements.txt`:

    error: subprocess-exited-with-error
    × Building wheel for greenlet (pyproject.toml) did not run successfully.
    ERROR: Failed building wheel for greenlet
    error: failed-wheel-build-for-install
    × Failed to build installable wheels for some pyproject.toml based projects
    ╰─> greenlet

«greenlet» در requirements.txt ما نیست؛ SQLAlchemy آن را روی معماری‌های
x86_64/amd64/aarch64 به‌عنوان وابستگی اعلام می‌کند. greenlet یک افزونه‌ی C است:
اگر pip برای پایتون شما wheel آماده پیدا نکند، سعی می‌کند آن را از سورس
کامپایل کند و بدون کامپایلر (Visual C++ Build Tools روی ویندوز یا gcc روی
هاست) شکست می‌خورد.

سه دلیل معمول نبودن wheel:
  ۱. پایتون خیلی جدید (۳.۱۳/۳.۱۴/۳.۱۵) + نسخه‌ی قدیمی greenlet که فقط تا
     cp312 wheel دارد → راه‌حل: نصب greenlet جدیدتر (۳.۲.۴ به بالا).
  ۲. pip قدیمی که resolver درست ندارد → راه‌حل: ارتقای pip.
  ۳. پلتفرم بدون wheel (پایتون ۳۲بیتی ویندوز، برخی ARM/musl) → راه‌حل:
     نصب بدون greenlet. برنامه sync است و به greenlet نیازی ندارد؛ greenlet
     فقط برای SQLAlchemy asyncio لازم است که ما استفاده نمی‌کنیم.

این اسکریپت هر سه را به ترتیب امتحان می‌کند و در پایان گزارش می‌دهد.

اجرا:
    python tools/install_deps.py                 # نصب معمولی + رفع خودکار
    python tools/install_deps.py --desktop       # + PyQt6 برای نسخه دسکتاپ
    python tools/install_deps.py --skip-greenlet # مستقیم برو سراغ حالت بدون greenlet
    python tools/install_deps.py --dry-run       # فقط نشان بده چه دستوری اجرا می‌شود
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_REQUIREMENTS = os.path.join(REPO_ROOT, "requirements.txt")

# بسته‌هایی که نبودشان اشکالی ندارد و نباید در حالت fallback نصب شوند
OPTIONAL_PACKAGES = {"greenlet"}

# پیام‌هایی که یعنی «کامپایل greenlet شکست خورد»
_GREENLET_FAILURE_PATTERNS = (
    "building wheel for greenlet",
    "failed building wheel for greenlet",
    "could not build wheels for greenlet",
    "failed-wheel-build-for-install",
    "no matching distribution found for greenlet",
    "could not find a version that satisfies the requirement greenlet",
)

# خروجی `pip check`:  "flask 3.1.3 requires werkzeug, which is not installed."
_PIP_CHECK_MISSING = re.compile(
    r"requires\s+([A-Za-z0-9._-]+)[^,]*,\s*which is not installed", re.IGNORECASE
)


# ───────────────────────────── توابع خالص (قابل آزمون) ─────────────────────────────


def is_greenlet_failure(output: str) -> bool:
    """آیا این خروجی pip، شکست ساخت/یافتن greenlet است؟"""
    if not output:
        return False
    text = output.lower()
    if "greenlet" not in text:
        return False
    return any(pattern in text for pattern in _GREENLET_FAILURE_PATTERNS)


def parse_missing_dependencies(pip_check_output: str, skip=OPTIONAL_PACKAGES):
    """نام بسته‌های گم‌شده را از خروجی `pip check` بیرون می‌کشد.

    بسته‌های داخل ``skip`` (پیش‌فرض: greenlet) نادیده گرفته می‌شوند.
    خروجی: فهرست یکتا و مرتب‌شده از نام‌های نرمال‌شده.
    """
    skip_norm = {normalize_name(name) for name in (skip or ())}
    found = []
    for raw in _PIP_CHECK_MISSING.findall(pip_check_output or ""):
        name = normalize_name(raw)
        if name and name not in skip_norm and name not in found:
            found.append(name)
    return sorted(found)


def normalize_name(name: str) -> str:
    """نرمال‌سازی نام بسته طبق PEP 503 (Flask_SQLAlchemy → flask-sqlalchemy)."""
    return re.sub(r"[-_.]+", "-", (name or "").strip()).lower()


def pip_cmd(*args, python=None):
    """ساخت دستور pip با همان مفسری که این اسکریپت را اجرا می‌کند."""
    return [python or sys.executable, "-m", "pip", *args]


def python_report() -> str:
    """یک خط توصیف محیط، برای گزارش خطا."""
    import platform

    bits = "64-bit" if sys.maxsize > 2**32 else "32-bit"
    return (
        f"Python {platform.python_version()} ({bits}) | "
        f"{platform.system()} {platform.machine()} | "
        f"executable: {sys.executable}"
    )


# ───────────────────────────── اجرای دستورها ─────────────────────────────


def run(cmd, dry_run=False, echo=True):
    """اجرای دستور و برگرداندن (returncode, output). خروجی هم چاپ می‌شود."""
    if echo:
        print("   $ " + " ".join(cmd))
    if dry_run:
        return 0, ""
    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            errors="replace",
        )
    except OSError as exc:
        print(f"   ✗ اجرای دستور ممکن نشد: {exc}")
        return 1, str(exc)
    if proc.stdout:
        sys.stdout.write(proc.stdout)
        sys.stdout.flush()
    return proc.returncode, proc.stdout or ""


def upgrade_pip(dry_run=False):
    print("\n[۱] ارتقای pip / setuptools / wheel (رایج‌ترین علت شکست wheel)...")
    code, _ = run(
        pip_cmd("install", "--upgrade", "pip", "setuptools", "wheel"), dry_run=dry_run
    )
    if code != 0:
        print("   ⚠ ارتقای pip موفق نبود؛ با همین نسخه ادامه می‌دهیم.")
    return code == 0


def install_requirements(req_path, dry_run=False, extra=()):
    """نصب معمولی با ترجیح wheel آماده."""
    cmd = pip_cmd("install", "--prefer-binary", "-r", req_path, *extra)
    return run(cmd, dry_run=dry_run)


def install_greenlet_wheel(dry_run=False):
    """نصب جدیدترین greenlet که برای این پایتون wheel آماده دارد.

    با ``--only-binary=:all:`` هیچ‌وقت کامپایل انجام نمی‌شود؛ pip عقب می‌رود تا
    نسخه‌ای با wheel سازگار پیدا کند (مثلاً روی cp314 → greenlet 3.2.4+).
    """
    print("\n[۲] تلاش برای نصب greenlet به‌صورت wheel آماده (بدون کامپایل)...")
    cmd = pip_cmd("install", "--only-binary=:all:", "--upgrade", "greenlet")
    code, out = run(cmd, dry_run=dry_run)
    if code == 0:
        print("   ✓ greenlet با wheel آماده نصب شد.")
    else:
        print("   ⚠ برای این نسخه پایتون/پلتفرم هیچ wheel آماده‌ای از greenlet نیست.")
    return code == 0, out


def install_without_greenlet(req_path, dry_run=False, extra=(), max_rounds=6):
    """نصب کامل وابستگی‌ها بدون greenlet.

    مرحله ۱: همه‌ی بسته‌های پین‌شده با ``--no-deps`` (پس pip اصلاً سراغ
             greenlet نمی‌رود).
    مرحله ۲: با ``pip check`` وابستگی‌های واقعیِ گم‌شده پیدا و نصب می‌شوند —
             به‌جز greenlet که برنامه به آن نیازی ندارد.
    """
    print("\n[۳] نصب بدون greenlet (برنامه sync است و به آن نیاز ندارد)...")
    code, out = run(
        pip_cmd("install", "--prefer-binary", "--no-deps", "-r", req_path, *extra),
        dry_run=dry_run,
    )
    if code != 0:
        return False, out
    if dry_run:
        run(pip_cmd("check"), dry_run=True)
        return True, out

    for round_no in range(1, max_rounds + 1):
        _, check_out = run(pip_cmd("check"), echo=(round_no == 1))
        missing = parse_missing_dependencies(check_out)
        if not missing:
            break
        print(f"   → نصب وابستگی‌های گم‌شده (دور {round_no}): {', '.join(missing)}")
        # باز هم --no-deps تا pip از راه یک وابستگیِ دیگر دوباره سراغ greenlet نرود؛
        # وابستگی‌های خودِ این بسته‌ها در دور بعدی pip check پیدا می‌شوند.
        code, out = run(pip_cmd("install", "--prefer-binary", "--no-deps", *missing))
        if code != 0:
            return False, out
    else:
        print("   ⚠ وابستگی‌ها بعد از چند دور هنوز کامل نیستند.")

    return True, out


DESKTOP_PACKAGES = ("PyQt6", "PyQt6-WebEngine")


def install_desktop_extras(dry_run=False):
    """نصب PyQt6 برای نسخه‌ی دسکتاپ (اختیاری — نبودش فقط حالت دسکتاپ را غیرفعال می‌کند)."""
    print("\n[+] نصب بسته‌های نسخه دسکتاپ (PyQt6)...")
    code, _ = run(
        pip_cmd("install", "--prefer-binary", *DESKTOP_PACKAGES), dry_run=dry_run
    )
    if code != 0:
        print("   ⚠ نصب PyQt6 موفق نبود؛ حالت مرورگر (python app.py) همچنان کار می‌کند.")
    return code == 0


def verify_imports(dry_run=False):
    """اطمینان از اینکه هسته‌ی برنامه واقعاً import می‌شود."""
    print("\n[۴] بررسی نهایی نصب...")
    snippet = (
        "import sys;"
        "from importlib.metadata import version;"
        "import flask, sqlalchemy, flask_sqlalchemy;"
        "print('  Python        ', sys.version.split()[0]);"
        "print('  Flask         ', version('flask'));"
        "print('  SQLAlchemy    ', version('sqlalchemy'));"
        "print('  Flask-SQLAlchemy', version('flask-sqlalchemy'))"
    )
    code, _ = run([sys.executable, "-c", snippet], dry_run=dry_run)
    if code == 0 and not dry_run:
        try:
            import greenlet  # noqa: F401

            print("  greenlet       نصب است (اختیاری)")
        except Exception:
            print("  greenlet       نصب نیست — اشکالی ندارد؛ فقط برای SQLAlchemy async لازم است.")
    return code == 0


# ───────────────────────────── جریان اصلی ─────────────────────────────


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="نصب وابستگی‌های Academy Manager Pro با رفع خودکار خطای greenlet"
    )
    parser.add_argument("-r", "--requirements", default=DEFAULT_REQUIREMENTS)
    parser.add_argument("--desktop", action="store_true", help="نصب PyQt6 برای نسخه دسکتاپ")
    parser.add_argument("--skip-greenlet", action="store_true", help="از اول بدون greenlet نصب کن")
    parser.add_argument("--no-upgrade-pip", action="store_true", help="pip را ارتقا نده")
    parser.add_argument("--dry-run", action="store_true", help="فقط دستورها را نشان بده")
    args = parser.parse_args(argv)

    req = args.requirements
    if not os.path.isfile(req):
        print(f"✗ فایل requirements پیدا نشد: {req}")
        return 2

    print("═" * 64)
    print("  نصب وابستگی‌های Academy Manager Pro")
    print("  " + python_report())
    print("═" * 64)

    if not args.no_upgrade_pip:
        upgrade_pip(dry_run=args.dry_run)

    def finish(core_ok, note=None):
        if not core_ok:
            return 1
        if args.desktop:
            install_desktop_extras(dry_run=args.dry_run)
        ok = verify_imports(args.dry_run)
        if ok and note:
            print(f"\n{note}")
        elif ok:
            print("\n✓ نصب کامل شد.")
        return 0 if ok else 1

    if args.skip_greenlet:
        ok, _ = install_without_greenlet(req, dry_run=args.dry_run)
        return finish(ok, "✓ نصب کامل شد (بدون greenlet — برنامه به آن نیازی ندارد).")

    print("\n[۲] نصب بسته‌ها از requirements.txt ...")
    code, out = install_requirements(req, dry_run=args.dry_run)
    if code == 0:
        return finish(True)

    if not is_greenlet_failure(out):
        print("\n✗ نصب شکست خورد و علت آن greenlet نیست. متن خطای بالا را ببینید.")
        return 1

    print("\n⚠ خطای شناخته‌شده: ساخت wheel برای greenlet شکست خورد.")
    installed, _ = install_greenlet_wheel(dry_run=args.dry_run)
    if installed:
        code, out = install_requirements(req, dry_run=args.dry_run)
        if code == 0:
            return finish(True)
        if not is_greenlet_failure(out):
            print("\n✗ نصب شکست خورد (علت جدید). متن خطای بالا را ببینید.")
            return 1

    ok, _ = install_without_greenlet(req, dry_run=args.dry_run)
    if not ok:
        print("\n✗ نصب حتی بدون greenlet هم کامل نشد.")
        print("  راه‌حل‌های پیشنهادی:")
        print("   • پایتون ۳.۱۱ یا ۳.۱۲ (۶۴ بیتی) نصب کنید و دوباره تلاش کنید.")
        print("   • یا کامپایلر نصب کنید (ویندوز: Visual C++ Build Tools، لینوکس: gcc + python3-dev).")
        return 1

    return finish(True, "✓ نصب کامل شد (بدون greenlet — برنامه به آن نیازی ندارد).")


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
