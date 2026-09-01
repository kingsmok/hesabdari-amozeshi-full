#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Academy Manager Pro - build the Windows installer
==================================================

اجرا:
    python build_installer.py

این اسکریپت همان کاری را می‌کند که build_installer.bat قدیمی انجام می‌داد،
اما تمام منطق در Python است. فایل .bat فقط یک پوسته‌ی کوچک ASCII است.
دلیل: cmd.exe با فایل‌های بچ که متن فارسی دارند (code page 65001)
باگ معروف دارد — پنجره بلافاصله باز و بسته می‌شود. Python متن فارسی
را در ویندوز 10/11 درست نمایش می‌دهد و خطاها را هم پنهان نمی‌کند.
"""

import glob
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request

MIN_PYTHON = (3, 9)
ROOT = os.path.dirname(os.path.abspath(__file__))

# صفحه‌ای که بیشترین لینک دانلود مستقیم Inno Setup 6 در آن آمده است
INNO_SETUP_PAGE = "https://jrsoftware.org/isdl.php"
# نقطه‌ی شروع بررسی نسخه‌ی جدید (اگر دانلود صفحه‌ی رسمی نشد)
INNO_SETUP_BASE_URL = "https://github.com/jrsoftware/issrc/releases/download"
INNO_INSTALL_TIMEOUT = 300  # ثانیه

# package‌هایی که در requirements.txt نیستند (GUI + ابزار بیلد)
EXTRA_PACKAGES = ["PyQt6", "PyQt6-WebEngine", "pyinstaller"]


# ──────────────────────────── console ────────────────────────────

def _prepare_console():
    """اگر خروجی redirect شده باشد (کنسول تعاملی نیست)، UTF-8 را
    اجباری کن تا متن فارسی هرگز اسکریپت را کرش نکند."""
    if os.name != "nt":
        return
    for stream in (sys.stdout, sys.stderr):
        try:
            if getattr(stream, "isatty", lambda: False)():
                continue  # کنسول واقعی: Python خودش از API یونیکد استفاده می‌کند
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
    print("  ║  ساخت نصب‌کننده - Academy Manager Pro                ║")
    print("  ║  آموزشگاه رهسا - rahsacademic.com                    ║")
    print("  ╚" + "═" * 58 + "╝")
    print()


def step(n, total, title):
    print()
    print(f"  [{n}/{total}] {title}")
    print("  " + "─" * 58)


# ──────────────────────── subprocess helpers ─────────────────────

def child_env():
    env = dict(os.environ)
    # اسکریپت‌های فرعی Python متن فارسی چاپ می‌کنند؛ با pipe (غیر از
    # کنسول) خروجی‌شان UTF-8 شود تا با خطای رمزگذاری کرش نکنند
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def run_live(cmd, note=None):
    """اجرای فرمان و نمایش زنده‌ی خروجی. کد خروج را برمی‌گرداند."""
    if note:
        print(f"      {note}")
    print(f"      $ {' '.join(cmd)}", flush=True)
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=ROOT,
            env=child_env(),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except OSError as exc:
        print(f"      اجرای فرمان ممکن نبود: {exc}")
        return 1
    for line in proc.stdout:
        sys.stdout.write(line)
    return proc.wait()


def run_quiet(cmd, what):
    """اجرای فرمان بدون نمایش خروجی؛ یک خط وضعیت نشان می‌دهد و در
    صورت خطا، انتهای لاگ را چاپ می‌کند. در موفقیت True برمی‌گرداند."""
    print(f"      {what} ...", flush=True)
    started = time.time()
    proc = subprocess.run(
        cmd,
        cwd=ROOT,
        env=child_env(),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    took = time.time() - started
    if proc.returncode == 0:
        print(f"      OK ({took:.0f} ثانیه)")
        return True
    print(f"      ❌ با خطا تمام شد (بعد از {took:.0f} ثانیه) - انتهای لاگ:")
    for line in (proc.stdout or "").strip().splitlines()[-25:]:
        print("      " + line)
    print("      " + "─" * 50)
    return False


def pip(args):
    return [sys.executable, "-m", "pip"] + list(args)


# ─────────────────────────── ISCC lookup ─────────────────────────

def find_iscc():
    found = shutil.which("ISCC") or shutil.which("iscc")
    if found:
        return found
    candidates = [
        r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        r"C:\Program Files\Inno Setup 6\ISCC.exe",
        r"C:\Program Files (x86)\Inno Setup 7\ISCC.exe",
        r"C:\Program Files\Inno Setup 7\ISCC.exe",
    ]
    local = os.environ.get("LOCALAPPDATA", "")
    if local:
        # نصب‌های per-user (e.g. winget بدون حقوق مدیر یا نصب with /CURRENTUSER)
        candidates.extend([
            os.path.join(local, "Programs", "Inno Setup 6", "ISCC.exe"),
            os.path.join(local, "Programs", "Inno Setup 7", "ISCC.exe"),
        ])
    for cand in candidates:
        if os.path.exists(cand):
            return cand
    # جست‌وجوی هر نسخه‌ی Inno Setup در پوشه‌های Program Files
    roots = [
        os.environ.get("PROGRAMFILES", r"C:\Program Files"),
        os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"),
    ]
    for root in roots:
        if not root or not os.path.isdir(root):
            continue
        try:
            entries = sorted(os.listdir(root))
        except OSError:
            continue
        for name in entries:
            if name.lower().startswith("inno setup"):
                cand = os.path.join(root, name, "ISCC.exe")
                if os.path.exists(cand):
                    return cand
    return None


# ─────────────────────────── Inno install ────────────────────────

def _inno_version_from_url(url):
    """استخراج (major, minor, patch) از آدرس innosetup-x.y.z.exe."""
    m = re.search(r"innosetup-(\d+)\.(\d+)\.(\d+)\.exe", url or "")
    if not m:
        return (0, 0, 0)
    return tuple(int(x) for x in m.groups())


def latest_inno6_url():
    """خواندن صفحه‌ی رسمی و پیدا کردن آخرین لینک مستقیم Inno Setup 6.

    اگر اینترنت یا صفحه در دسترس نباشد به آخرین نسخه‌ی شناخته‌شده
    برمی‌گردد تا اسکریپت همچنان بتواند ادامه بدهد.
    """
    try:
        req = urllib.request.Request(
            INNO_SETUP_PAGE,
            headers={"User-Agent": "AcademyManager-Build/1.0"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            html = resp.read().decode("utf-8", "replace")
        urls = set(re.findall(
            r"https://github\.com/jrsoftware/issrc/releases/download/"
            r"is-6_[^/]*/innosetup-6\.\d+\.\d+\.exe",
            html,
        ))
        if urls:
            return max(urls, key=_inno_version_from_url)
    except Exception:
        pass
    return (
        INNO_SETUP_BASE_URL
        + "/is-6_7_3/innosetup-6.7.3.exe"
    )


def _run_quiet_timeout(cmd, timeout):
    try:
        return subprocess.run(
            cmd,
            cwd=ROOT,
            env=child_env(),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=timeout,
        ).returncode
    except subprocess.TimeoutExpired:
        return -1


def win_install_inno_with_winget():
    """تلاش برای نصب با winget (در ویندوز 10/11 معمولاً سریع)."""
    if shutil.which("winget") is None:
        print("      winget در PATH پیدا نشد")
        return False
    print("      نصب Inno Setup با winget ...")
    rc = _run_quiet_timeout(
        [
            "winget", "install", "--id", "JRSoftware.InnoSetup", "-e",
            "--silent",
            "--accept-package-agreements", "--accept-source-agreements",
        ],
        timeout=INNO_INSTALL_TIMEOUT,
    )
    if rc == 0:
        print("      نصب با winget انجام شد")
        return True
    print(f"      نصب با winget ناموفق بود (کد {rc})")
    return False


def win_install_inno_direct():
    """دانلود مستقیم و نصب بی‌صدا (fallback وقتی winget نیست)."""
    url = latest_inno6_url()
    fname = os.path.basename(url)
    dest = os.path.join(tempfile.gettempdir(), fname)
    print(f"      دانلود Inno Setup 6 ...")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "AcademyManager-Build/1.0"})
        with urllib.request.urlopen(req, timeout=60) as resp, open(dest, "wb") as fh:
            shutil.copyfileobj(resp, fh)
    except Exception as exc:
        print(f"      دانلود ممکن نبود: {exc}")
        return False

    print("      نصب بی‌صدا (CURRENTUSER) ...")
    rc = _run_quiet_timeout(
        [
            dest,
            "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-",
            "/CURRENTUSER",
            f"/LOG={dest}.log",
        ],
        timeout=INNO_INSTALL_TIMEOUT,
    )
    if rc == 0:
        print("      نصب مستقیم انجام شد")
        return True
    print(f"      نصب مستقیم ناموفق بود (کد {rc}).")
    print("      اگر پنجره‌ی کنترل حساب کاربری (UAC) ظاهر شد، آن را تأیید کنید.")
    return False


def install_inno_interactive():
    """پرسیدن از کاربر و تلاش برای نصب Inno Setup.

    در حالت غیر تعاملی (مثلاً پایپ) یا وقتی کاربر جواب «No» بدهد
    None برمی‌گرداند تا اسکریپت با راهنمای دستی متوقف شود.
    """
    print()
    print("  ! Inno Setup نصب نیست.")
    print("    این ابزار برای ساخت فایل نصب‌کننده‌ی ویندوزی (EXE) لازم است.")

    # اجرای خودکار بدون پرسش
    auto = os.environ.get("AUTO_INSTALL_INNO", "").strip().lower()
    if auto in ("1", "true", "yes", "y"):
        answer = "y"
    else:
        try:
            answer = input("    آیا همین حالا نصبش کنم؟ [Y/n] ").strip().lower()
        except EOFError:
            answer = "n"

    if answer not in ("", "y", "yes"):
        return None
    if os.name != "nt":
        print("      نصب خودکار فقط روی ویندوز امکان‌پذیر است.")
        return None

    installed = win_install_inno_with_winget() or win_install_inno_direct()
    if not installed:
        print("      نصب خودکار ناموفق بود.")
        return None
    return find_iscc()


# ─────────────────────────────── main ────────────────────────────

def main():
    os.chdir(ROOT)
    _prepare_console()

    if sys.version_info < MIN_PYTHON:
        die(
            f"نسخه‌ی Python فعلی {sys.version.split()[0]} است؛ حداقل "
            f"3.{MIN_PYTHON[1]} لازم است.\n"
            "  آخرین نسخه را از https://www.python.org/downloads/ بگیرید"
        )

    for required in ("app_desktop.spec", "installer.iss", "requirements.txt"):
        if not os.path.exists(required):
            die(
                f"فایل {required} در پوشه‌ی پروژه پیدا نشد.\n"
                "  این فایل باید از پوشه‌ی اصلی پروژه اجرا شود "
                "(همان پوشه‌ای که همین فایل در آن است)"
            )

    header()
    started = time.time()

    # ── [1/7] پیش‌نیازها ──
    step(1, 7, "بررسی پیش‌نیازها ...")
    print(f"      Python {sys.version.split()[0]}")
    probe = subprocess.run(
        [sys.executable, "-m", "PyInstaller", "--version"],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if probe.returncode != 0:
        print("      PyInstaller نصب نیست - در حال نصب ...")
        if not run_quiet(pip(["install", "-q", "pyinstaller"]),
                         "pip install pyinstaller"):
            die("نصب PyInstaller ممکن نبود. اتصال اینترنت را بررسی کنید و دوباره امتحان کنید.")
    iscc = find_iscc()
    if iscc:
        print(f"      Inno Setup: {iscc}")
    else:
        iscc = install_inno_interactive()
        if not iscc:
            die(
                "Inno Setup نصب نیست!\n"
                "  1) دوباره همین فایل را اجرا کنید و Yes بدهید تا نصب خودکار انجام شود.\n"
                "  2) یا Inno Setup 6 را دستی نصب کنید:  https://jrsoftware.org/isdl.php\n"
                "  3) اگر خودتان نصب کردید، همین پنجره را ببندید و دوباره اجرا کنید."
            )
        print(f"      Inno Setup: {iscc}")
    print("      OK")

    # ── [2/7] پکیج‌ها ──
    step(2, 7, "نصب پکیج‌های مورد نیاز ...")
    if not run_quiet(pip(["install", "-q", "-r", "requirements.txt"]),
                     "نصب پکیج‌های requirements.txt (اولین بار ممکن است چند دقیقه طول بکشد)"):
        die("نصب پکیج‌های requirements.txt ممکن نبود. اتصال اینترنت را بررسی کنید و دوباره امتحان کنید.")
    if not run_quiet(pip(["install", "-q"] + EXTRA_PACKAGES),
                     " ".join(EXTRA_PACKAGES)):
        die("نصب PyQt6 / PyInstaller ممکن نبود. اتصال اینترنت را بررسی کنید و دوباره امتحان کنید.")
    # حذف PySide در صورت وجود (تضاد با PyQt6)
    subprocess.run(
        pip(["uninstall", "-q", "-y", "PySide6", "PySide2"]),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    print("      OK")

    # ── [3/7] فایل‌های استاتیک ──
    step(3, 7, "دانلود فونت‌ها و فایل‌های استاتیک (setup.py) ...")
    if os.path.exists("setup.py"):
        if run_live([sys.executable, "setup.py"],
                    note="اگر فایل‌ها قبلاً دانلود نشده‌اند، ممکن است چند دقیقه طول بکشد") != 0:
            die("setup.py با خطا تمام شد. خط‌های بالا را بررسی کنید.")
    else:
        print("      setup.py پیدا نشد - رد می‌شود")

    # ── [4/7] آیکون ──
    step(4, 7, "ساخت آیکون برنامه ...")
    if os.path.exists("create_icon.py"):
        if run_live([sys.executable, "create_icon.py"]) != 0:
            die("ساخت آیکون ممکن نبود. خط‌های بالا را بررسی کنید.")
    else:
        print("      create_icon.py پیدا نشد - از آیکون موجود استفاده می‌شود")

    # ── [5/7] داده‌های رهسا ──
    step(5, 7, "وارد کردن اطلاعات آموزشگاه رهسا ...")
    if os.path.exists("import_rahs_data.py"):
        if run_live([sys.executable, "import_rahs_data.py"]) != 0:
            die("وارد کردن اطلاعات ممکن نبود. خط‌های بالا را بررسی کنید.")
    else:
        print("      import_rahs_data.py پیدا نشد - رد می‌شود")

    # ── [6/7] ساخت EXE ──
    step(6, 7, "ساخت فایل اجرایی (PyInstaller) ...")
    print("      این مرحله طولانی‌ترین مرحله است (حدود ۵ تا ۲۰ دقیقه)")
    rc = run_live([sys.executable, "-m", "PyInstaller",
                   "--noconfirm", "--clean", "app_desktop.spec"])
    exe = os.path.join("dist", "AcademyManager", "AcademyManager.exe")
    if rc != 0 or not os.path.exists(exe) or os.path.getsize(exe) == 0:
        die("ساخت فایل اجرایی ناموفق بود! لاگ PyInstaller را در بالا بررسی کنید.")
    print(f"      OK: {exe}  ({os.path.getsize(exe) // (1024 * 1024)} MB)")

    # ── [7/7] ساخت نصب‌کننده ──
    step(7, 7, "ساخت نصب‌کننده (Inno Setup) ...")
    os.makedirs("installer_output", exist_ok=True)
    if not run_quiet([iscc, "/Q", "installer.iss"], "iscc installer.iss"):
        print()
        print("      ⚠ ساخت نصب‌کننده ناموفق بود، اما فایل اجرایی آماده است:")
        print(f"      {os.path.abspath(exe)}")
        print("      می‌توانید همان پوشه را کپی کنید، یا Inno Setup را درست کنید و دوباره اجرا کنید")
    else:
        outputs = sorted(
            glob.glob(os.path.join("installer_output", "AcademyManager_Setup_v*.exe")),
            key=os.path.getmtime,
            reverse=True,
        )
        if outputs:
            out = outputs[0]
            size_mb = os.path.getsize(out) / (1024 * 1024)
            print()
            print("  ╔" + "═" * 58 + "╗")
            print("  ║  ✅ نصب‌کننده با موفقیت ساخته شد!                       ║")
            print("  ║                                                          ║")
            print(f"  ║  فایل:  {out}     ")
            print(f"  ║  حجم:  {size_mb:.1f} MB                              ║")
            print("  ║                                                          ║")
            print("  ║  این فایل را می‌توانید:                                 ║")
            print("  ║    • در فلش بریزید و هر کجا نصب کنید                   ║")
            print("  ║    • ایمیل کنید                                         ║")
            print("  ║    • در شبکه به اشتراک بگذارید                         ║")
            print("  ╚" + "═" * 58 + "╝")
        else:
            print()
            print("      ⚠ ISCC تمام شد اما فایل نصب‌کننده در installer_output پیدا نشد")
            print("      فایل اجرایی آماده است:")
            print(f"      {os.path.abspath(exe)}")

    print()
    total = time.time() - started
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
