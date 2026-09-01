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
if errorlevel 1 (
    echo.
    echo  If you saw TypingOnly / __firstlineno__ / SQLAlchemy error:
    echo    python -m pip install --upgrade "SQLAlchemy>=2.0.31"
    echo    then run this file again.
    echo  Or run install.bat first.
    echo.
)
pause
