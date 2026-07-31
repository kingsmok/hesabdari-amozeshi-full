@echo off
chcp 65001 >nul 2>&1
title Academy Manager Pro v1.0
echo.
echo ============================================
echo   Academy Manager Pro v1.0
echo ============================================
echo.
echo   URL:  http://localhost:5000
echo   User: admin
echo   Pass: **رمز حذف شده برای امنیت**
echo.
echo ============================================
echo.
start http://localhost:5000
set PYTHONUTF8=1
python app.py
pause
