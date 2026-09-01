# راهنمای نصب روی هاست (Host Deployment Guide)

## روش سریع (ویندوز)

فقط **`deploy_host.bat`** را دوبار کلیک کنید. این اسکریپت:
- پوشه‌ی `host_deploy/` را می‌سازد و دقیقاً همان فایل‌های لازم برای هاست را
  در آن کپی می‌کند (بدون فایل‌های بیلد، بدون دیتابیس محلی، بدون فایل‌های حساس)
- یک فایل ZIP آماده‌ی آپلود می‌سازد: `host_deploy_v<نسخه>.zip`
- در پایان، مراحل آپلود روی cPanel (Python 3.11) را نمایش می‌دهد

سپس ادامه را طبق مراحل زیر (بخش «مراحل سریع») روی هاست انجام دهید.

## پیش‌نیازها
- **Python 3.11** روی هاست (نسخه‌ی پشتیبانی‌شده؛ ۳.۱۴ فقط برای دسکتاپ ویندوز مشکل‌ساز است)
- دسترسی به pip / venv
- برای نسخه وب: Apache (mod_wsgi / Passenger) یا Nginx + Gunicorn

> هاست Python 3.11 با `requirements.txt` فعلی (از جمله SQLAlchemy ۲.۰.۵۲) سازگار است.
> فایل `startup_checks.py` باید در ریشهٔ آپلود باشد؛ `app.py` آن را لازم دارد.
> روی هاست هرگز pip خودکار یا پنجرهٔ Enter اجرا نمی‌شود.

## مراحل سریع

### ۱. آپلود فایل‌ها
کل محتویات این پوشه را در `public_html` (یا پوشه اصلی دامنه) آپلود کنید.

### ۲. نصب پکیج‌ها (در هاست)
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### ۳. ایجاد پوشه‌های لازم و دسترسی
```bash
mkdir -p instance static/uploads backups
chmod 755 instance static/uploads backups
```

### ۴. تنظیم دیتابیس
فایل `settings.json` (در صورت وجود) یا `config.py` را بررسی کنید.
پیش‌فرض SQLite است (`instance/academy.db`). اگر MySQL دارید، `config.py` را ویرایش کنید.

### ۵. ورود به برنامه
پس از اجرای سرور:
- کاربر: `admin`
- رمز عبور: در تنظیمات اولیه تعریف شده (اولین بار از طریق `first_run.py` یا ورود پیش‌فرض تنظیم می‌شود)

## روش‌های راه‌اندازی

### A) cPanel / Passenger (اشتراکی)
فایل `passenger_wsgi.py` در ریشه دامنه قرار دارد.
معمولاً کافیست در cPanel → Setup Python App، پروژه را انتخاب کنید.
یا در `.htaccess` خطوط `PassengerAppRoot` را اضافه کنید.

### B) VPS / سرور لینوکس (Gunicorn + Nginx)
```bash
source venv/bin/activate
gunicorn --bind 0.0.0.0:5000 wsgi:application
```
سپس Nginx را به `proxy_pass http://127.0.0.1:5000;` تنظیم کنید.

### C) اجرای سریع (تست)
```bash
source venv/bin/activate
python app.py
```
سپس در مرورگر: `http://IP:5000`

## نکات مهم امنیتی
- `settings.json` را در دسترس عموم قرار ندهید (در `.htaccess` مسدود شده)
- `instance/` را قابل نوشتن (writable) کنید
- `SECRET_KEY` را در محیط سرور (`.env` یا `settings.json`) تنظیم کنید
