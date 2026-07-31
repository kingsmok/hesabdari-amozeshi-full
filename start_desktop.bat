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
pause
