@echo off
chcp 65001 >nul 2>&1
title Academy Manager Pro - Desktop
echo.
echo ============================================
echo   Academy Manager Pro - Desktop Mode
echo ============================================
echo.
echo   URL:  http://localhost:5000
echo   User: admin
echo   Pass: **رمز حذف شده برای امنیت**
echo.
echo ============================================
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
