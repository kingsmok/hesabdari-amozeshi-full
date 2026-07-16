@echo off
chcp 65001 >nul 2>&1
title ساخت نصب‌کننده Academy Manager Pro
color 0A

echo.
echo  ╔══════════════════════════════════════════════════════════╗
echo  ║   ساخت نصب‌کننده حرفه‌ای - Academy Manager Pro         ║
echo  ║   آموزشگاه رهسا - rahsacademic.com                     ║
echo  ╚══════════════════════════════════════════════════════════╝
echo.

:: ─────────────────────────────────────
::  مرحله ۱: بررسی پیش‌نیازها
:: ─────────────────────────────────────
echo  [1/7] بررسی پیش‌نیازها...
echo  ─────────────────────────────────────────

python --version >nul 2>&1
if errorlevel 1 (
    echo  ✗ Python نصب نیست!
    echo    لطفاً Python 3.10+ نصب کنید
    pause
    exit /b 1
)
echo  ✓ Python

pyinstaller --version >nul 2>&1
if errorlevel 1 (
    echo  ✗ PyInstaller نصب نیست! در حال نصب...
    pip install pyinstaller
)

:: بررسی Inno Setup
where iscc >nul 2>&1
if errorlevel 1 (
    if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" (
        set "ISCC=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
    ) else if exist "C:\Program Files\Inno Setup 6\ISCC.exe" (
        set "ISCC=C:\Program Files\Inno Setup 6\ISCC.exe"
    ) else (
        echo.
        echo  ⚠ Inno Setup نصب نیست!
        echo    لطفاً از https://jrsoftware.org/isinfo.php دانلود و نصب کنید
        echo    سپس این فایل را دوباره اجرا کنید
        echo.
        echo    یا فایل dist\AcademyManager\AcademyManager.exe را اجرا کنید
        echo    (بدون نصب‌کننده هم کار می‌کند)
        echo.
        pause
        exit /b 1
    )
) else (
    set "ISCC=iscc"
)
echo  ✓ PyInstaller
echo  ✓ Inno Setup

:: ─────────────────────────────────────
::  مرحله ۲: نصب پکیج‌ها
:: ─────────────────────────────────────
echo.
echo  [2/7] نصب پکیج‌های مورد نیاز...
echo  ─────────────────────────────────────────
pip install -q Flask Flask-SQLAlchemy Flask-Login Flask-WTF Flask-Migrate jdatetime requests reportlab PyQt6 PyQt6-WebEngine 2>nul
:: حذف PySide6 اگر نصب باشد (تضاد با PyQt6)
pip uninstall -y PySide6 PySide2 2>nul
echo  ✓ پکیج‌ها نصب شدند

:: ─────────────────────────────────────
::  مرحله ۳: دانلود فونت و فایل‌های استاتیک
:: ─────────────────────────────────────
echo.
echo  [3/7] دانلود فونت‌ها و فایل‌های استاتیک...
echo  ─────────────────────────────────────────
python setup.py 2>nul
echo  ✓ فایل‌های استاتیک آماده

:: ─────────────────────────────────────
::  مرحله ۴: ساخت آیکون برنامه
:: ─────────────────────────────────────
echo.
echo  [4/7] ساخت آیکون برنامه...
echo  ─────────────────────────────────────────
python create_icon.py 2>nul
echo  ✓ آیکون ساخته شد

:: ─────────────────────────────────────
::  مرحله ۵: وارد کردن اطلاعات اولیه
:: ─────────────────────────────────────
echo.
echo  [5/7] وارد کردن اطلاعات آموزشگاه رهسا...
echo  ─────────────────────────────────────────
python import_rahs_data.py 2>nul
echo  ✓ اطلاعات وارد شد

:: ─────────────────────────────────────
::  مرحله ۶: ساخت EXE (حالت پوشه‌ای)
:: ─────────────────────────────────────
echo.
echo  [6/7] ساخت فایل اجرایی...
echo  ─────────────────────────────────────────
pyinstaller --noconfirm --clean app_desktop.spec

if not exist "dist\AcademyManager\AcademyManager.exe" (
    echo.
    echo  ✗ ساخت EXE ناموفق بود!
    echo    لاگ خطا را بررسی کنید
    pause
    exit /b 1
)
echo  ✓ فایل اجرایی ساخته شد

:: ─────────────────────────────────────
::  مرحله ۷: ساخت نصب‌کننده با Inno Setup
:: ─────────────────────────────────────
echo.
echo  [7/7] ساخت نصب‌کننده (Inno Setup)...
echo  ─────────────────────────────────────────

mkdir installer_output 2>nul
"%ISCC%" /Q installer.iss

if exist "installer_output\AcademyManager_Setup_v1.0.0.exe" (
    echo.
    echo  ╔══════════════════════════════════════════════════════════╗
    echo  ║                                                          ║
    echo  ║   ✅ نصب‌کننده با موفقیت ساخته شد!                      ║
    echo  ║                                                          ║
    echo  ║   فایل: installer_output\AcademyManager_Setup_v1.0.0.exe ║
    echo  ║                                                          ║
    echo  ║   این فایل را می‌توانید:                                 ║
    echo  ║   • در فلش بریزید و هر کجا نصب کنید                     ║
    echo  ║   • ایمیل کنید                                           ║
    echo  ║   • در شبکه به اشتراک بگذارید                           ║
    echo  ║                                                          ║
    echo  ╚══════════════════════════════════════════════════════════╝
) else (
    echo.
    echo  ⚠ ساخت نصب‌کننده ناموفق!
    echo    اما فایل اجرایی آماده است:
    echo    dist\AcademyManager\AcademyManager.exe
)

echo.
pause
