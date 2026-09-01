@echo off
chcp 65001 >nul 2>&1
title Academy Manager Pro
echo.
echo  شروع سیستم مدیریت آموزشگاه...
echo  آدرس: http://localhost:5000
echo  نام کاربری: admin / **رمز حذف شده برای امنیت**
echo.
set PYTHONUTF8=1
python app_desktop.py
if errorlevel 1 (
    echo.
    echo  If you saw TypingOnly / __firstlineno__ / SQLAlchemy error:
    echo    python -m pip install --upgrade "SQLAlchemy>=2.0.31"
    echo    then run this file again.
    echo  Or run install.bat first.
    echo.
)
pause
