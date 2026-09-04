#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Academy Manager Pro - prepare the folder for hosting
====================================================

اجرا:
    python deploy_host.py

یک پوشه‌ی `host_deploy` می‌سازد که دقیقاً همان فایل‌هایی که هاست
(cPanel / Python 3.11) برای اجرای نسخه‌ی وب نیاز دارد در آن کپی شده:
بدون فایل‌های بیلد، بدون دیتابیس محلی و بدون فایل‌های حساس.
در پایان یک فایل ZIP هم می‌سازد تا راحت آپلود کنید.
"""

import os
import shutil
import sys
import time
import zipfile

ROOT = os.path.dirname(os.path.abspath(__file__))
STAGE = os.path.join(ROOT, "host_deploy")

# ── فایل‌هایی که در ریشه‌ی پوشه‌ی خروجی لازم است ──
REQUIRED_FILES = [
    "app.py",
    "extensions.py",
    "config.py",
    "wsgi.py",
    "passenger_wsgi.py",
    ".htaccess",
    "VERSION",
    "requirements.txt",
    "LICENSE.txt",
    "README.md",
    "HOST_DEPLOY.md",
    # app.py این را قبل از Flask وارد می‌کند — بدون آن هاست با ModuleNotFoundError می‌خوابد
    "startup_checks.py",
    # راه‌اندازی اولیه و داده‌های پایه (first_run این دو را import می‌کند)
    "first_run.py",
    "import_rahs_data.py",
    # سامانه‌ی لایسنس
    "license_client.py",
    "license_features.py",
    "license_updater.py",
]

# در صورت وجود، کپی می‌شود (شامل SECRET_KEY / تنظیمات دیتابیس)
OPTIONAL_FILES = ["settings.json"]

# ── پوشه‌های کد و قالب‌ها ──
# bootstrap/ (جداسازی create_app به ماژول‌های مستقل — app.py از آن import می‌کند)
DIRS = ["routes", "models", "utils", "bootstrap", "templates", "static"]

# ── پوشه‌های خالی که اپ در زمان اجرا نیاز دارد (قابل نوشتن باشند) ──
RUNTIME_DIRS = [
    "instance",
    "backups",
    os.path.join("static", "uploads"),
    os.path.join("static", "uploads", "students"),
    os.path.join("static", "uploads", "teachers"),
    os.path.join("static", "uploads", "certificates"),
    os.path.join("static", "uploads", "documents"),
]

# چیزی که هرگز نباید روی هاست برود
NEVER_COPY = {
    "__pycache__", ".git", ".venv", "venv", "env", ".idea", ".vscode",
    "build", "dist", "installer_output", "installer", "backups",
    "tests", ".pytest_cache", ".mypy_cache",
}


# ──────────────────────────── helpers ────────────────────────────

def _prepare_console():
    if os.name != "nt":
        return
    for stream in (sys.stdout, sys.stderr):
        try:
            if getattr(stream, "isatty", lambda: False)():
                continue
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def die(msg):
    print()
    lines = str(msg).splitlines()
    print("  ✗ " + lines[0])
    for line in lines[1:]:
        print("    " + line)
    print()
    sys.exit(1)


def header():
    print()
    print("  ╔" + "═" * 58 + "╗")
    print("  ║  آماده‌سازی فایل‌ها برای آپلود روی هاست                    ║")
    print("  ║  Academy Manager Pro - آموزشگاه رهسا                       ║")
    print("  ╚" + "═" * 58 + "╝")
    print()


def step(n, total, title):
    print()
    print(f"  [{n}/{total}] {title}")
    print("  " + "─" * 58)


def dir_size_mb(path):
    total = 0
    for root, _dirs, files in os.walk(path):
        for f in files:
            fp = os.path.join(root, f)
            if os.path.isfile(fp):
                total += os.path.getsize(fp)
    return total / (1024 * 1024)


# ─────────────────────────────── main ────────────────────────────

def main():
    os.chdir(ROOT)
    _prepare_console()

    for f in ("app.py", "requirements.txt", "VERSION", "passenger_wsgi.py"):
        if not os.path.exists(f):
            die(
                f"فایل {f} پیدا نشد.\n"
                "  این فایل باید از پوشه‌ی اصلی پروژه اجرا شود."
            )

    version = open("VERSION", encoding="utf-8").read().strip() or "1.0.0"

    header()
    started = time.time()

    # ── [1/4] پاک‌سازی پوشه‌ی قبلی ──
    step(1, 4, "آماده‌سازی پوشه‌ی host_deploy ...")
    if os.path.exists(STAGE):
        shutil.rmtree(STAGE)
        print("      پوشه‌ی قبلی پاک شد")
    os.makedirs(STAGE)
    print("      OK")

    # ── [2/4] کپی فایل‌ها ──
    step(2, 4, "کپی فایل‌های مورد نیاز ...")
    count = 0

    # فایل‌های ریشه
    for f in REQUIRED_FILES:
        if not os.path.exists(f):
            die(f"فایل {f} در پروژه پیدا نشد — کپی متوقف شد")
        shutil.copy2(f, os.path.join(STAGE, f))
        count += 1
        print(f"      ✓ {f}")

    for f in OPTIONAL_FILES:
        if os.path.exists(f):
            shutil.copy2(f, os.path.join(STAGE, f))
            count += 1
            print(f"      ✓ {f}  (مشتمل بر تنظیمات/کلید — محتویاتش را بررسی کنید)")

    # پوشه‌ها
    for d in DIRS:
        if not os.path.isdir(d):
            die(f"پوشه‌ی {d} در پروژه پیدا نشد — کپی متوقف شد")
        shutil.copytree(
            d,
            os.path.join(STAGE, d),
            ignore=shutil.ignore_patterns(
                "__pycache__", "*.pyc", "*.pyo", ".DS_Store", "Thumbs.db"
            ),
        )
        n = sum(len(fs) for _r, _ds, fs in os.walk(os.path.join(STAGE, d)))
        count += n
        print(f"      ✓ {d}/  ({n} فایل)")

    # آپلودهای موجود در ماشین توسعه نباید به هاست منتقل شوند؛
    # پوشه‌ی آپلود خالی و تازه ساخته می‌شود
    uploads = os.path.join(STAGE, "static", "uploads")
    if os.path.exists(uploads):
        shutil.rmtree(uploads)
        for d in RUNTIME_DIRS:
            if d.startswith(os.path.join("static", "uploads")):
                os.makedirs(os.path.join(STAGE, d), exist_ok=True)
        print("      ✓ static/uploads/  (تازه و خالی ساخته شد — فایل‌های قدیمی انتقال نیفتادند)")

    for d in RUNTIME_DIRS:
        os.makedirs(os.path.join(STAGE, d), exist_ok=True)
    print("      ✓ پوشه‌های instance/ , backups/ و زیرمجلدهای آپلود ساخته شدند")
    print(f"      مجموعاً {count} فایل")

    # ── [3/4] بررسی نهایی ──
    step(3, 4, "بررسی پوشه‌ی خروجی ...")
    problems = []
    for f in ("app.py", "requirements.txt", "passenger_wsgi.py", "wsgi.py", ".htaccess"):
        if not os.path.exists(os.path.join(STAGE, f)):
            problems.append(f)
    for needed in ("startup_checks.py", "passenger_wsgi.py", "wsgi.py"):
        if not os.path.exists(os.path.join(STAGE, needed)):
            problems.append(f"{needed} (برای هاست Python 3.11 لازم است)")
    for banned in ("academy.db", "cookies.txt", "config.ini", "app_desktop.py"):
        if os.path.exists(os.path.join(STAGE, banned)):
            problems.append(f"{banned} (نمی‌بایست در خروجی باشد!)")
    if problems:
        die("مشکلی در پوشه‌ی خروجی پیدا شد: " + ", ".join(problems))
    size_mb = dir_size_mb(STAGE)
    print(f"      OK - پوشه آماده است ({size_mb:.1f} MB)")

    # ── [4/4] ساخت ZIP ──
    step(4, 4, "ساخت فایل ZIP برای آپلود ...")
    zip_name = f"host_deploy_v{version}.zip"
    zip_path = os.path.join(ROOT, zip_name)
    if os.path.exists(zip_path):
        os.remove(zip_path)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for root, dirs, files in os.walk(STAGE):
            dirs[:] = [d for d in dirs if d not in NEVER_COPY]
            # پوشه‌های خالی را هم در ZIP نگه می‌داریم
            rel = os.path.relpath(root, ROOT)
            if not files and not [d for d in dirs if d not in NEVER_COPY]:
                zf.writestr(rel.replace(os.sep, "/") + "/", "")
            for f in files:
                fp = os.path.join(root, f)
                arc = os.path.relpath(fp, ROOT).replace(os.sep, "/")
                zf.write(fp, arc)
    zmb = os.path.getsize(zip_path) / (1024 * 1024)
    print(f"      OK: {zip_name}  ({zmb:.1f} MB)")

    # ── راهنمای آپلود ──
    total = time.time() - started
    print()
    print("  ╔" + "═" * 58 + "╗")
    print("  ║  ✅ فایل‌ها آماده‌ی آپلود هستند!                          ║")
    print("  ╚" + "═" * 58 + "╝")
    print()
    print(f"  • پوشه‌ی آماده:      {os.path.abspath(STAGE)}")
    print(f"  • فایل ZIP برای آپلود: {os.path.abspath(zip_path)}")
    print()
    print("  راهنمای آپلود (cPanel با Python 3.11):")
    print("  ─────────────────────────────────────────────────────────")
    print("  1. به cPanel بروید و وارد بخش  Python Apps / Setup Python App  شوید")
    print("  2. فایل ZIP را در File Manager داخل public_html آپلود و Extract کنید")
    print("     (تیک  Delete archive after extraction  را بزنید؛ پوشه‌ی host_deploy ساخته می‌شود)")
    print("  3. یک اپلیکیشن جدید بسازید:")
    print("       • Application root:  public_html/host_deploy")
    print("       • Application startup file:  passenger_wsgi.py")
    print("       • Python version:  3.11")
    print("  4. در Terminal همان cPanel، داخل venv اپلیکیشن:")
    print("       pip install -r requirements.txt")
    print("  5. مطمئن شوید پوشه‌های  instance/  و  static/uploads/  و  backups/")
    print("     قابل نوشتن (writable) هستند")
    print("  6. دامنه را باز کنید و به آدرس زیر بروید تا حساب مدیر ساخته شود:")
    print("       https://domain.com/setup")
    print()
    print("  نکات:")
    print("  • دیتابیس روی هاست تازه ساخته می‌شود (SQLite در instance/) —")
    print("    دیتابیس محلی شما آپلود نمی‌شود")
    print("  • پوشه‌ی آپلود (عکس و مدارک) خالی است؛ اگر فایل‌های قبلی را می‌خواهید،")
    print("    خودتان static/uploads را جداگانه کپی کنید")
    print("  • requirements.txt با Python 3.11 هاست شما سازگار است")
    print()
    print(f"  زمان کل: {int(total // 60)} دقیقه و {int(total % 60)} ثانیه")
    print()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print()
        print("  ⚠ توسط کاربر لغو شد (Ctrl+C)")
        sys.exit(1)
