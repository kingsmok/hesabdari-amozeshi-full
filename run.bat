@echo off
chcp 65001 >nul 2>&1
title Academy Manager Pro
echo.
echo  شروع سیستم مدیریت آموزشگاه...
echo  آدرس: http://localhost:5000
echo  نام کاربری: admin / **رمز حذف شده برای امنیت**
echo.
python app_desktop.py
pause
