# راهنمای نصب روی هاست (Host Deployment Guide)

## ساخت بسته‌ی آپلود (در ویندوز)

فقط **`deploy_host.bat`** را دوبار کلیک کنید (یا `python deploy_host.py`). این اسکریپت:

- پوشه‌ی `host_deploy/` را می‌سازد و دقیقاً همان فایل‌های لازم برای هاست را
  در آن کپی می‌کند (بدون فایل‌های بیلد، بدون دیتابیس محلی، بدون فایل‌های حساس)
- یک `settings.json` **تمیز و بدون راز** مخصوص هاست می‌سازد
  (`settings.json` محلی شما هرگز کپی نمی‌شود)
- پوشه‌های `instance/` و `backups/` و `logs/` و `static/uploads/` را خالی می‌سازد
- همه‌ی `import`های محلی را بررسی می‌کند تا روی هاست `ModuleNotFoundError` نگیرید
- یک فایل ZIP آماده‌ی آپلود می‌سازد: `host_deploy_v<نسخه>.zip`

## پیش‌نیازها

- **Python 3.11** روی هاست (نسخه‌ی پشتیبانی‌شده)
- دسترسی به pip / venv (در cPanel از طریق Setup Python App)
- حدود ۵۰۰ مگابایت فضای خالی (بسته‌ها + دیتابیس + آپلودها)

> هاست Python 3.11 با `requirements.txt` فعلی (از جمله SQLAlchemy ۲.۰.۵۲) سازگار است.
> فایل `startup_checks.py` باید در ریشه‌ی آپلود باشد؛ `app.py` آن را لازم دارد.
> روی هاست هرگز pip خودکار یا پنجره‌ی Enter اجرا نمی‌شود.

---

## مسیر A) هاست اشتراکی cPanel (پیشنهادی برای شروع)

### ۱. آپلود فایل‌ها

1. وارد cPanel → **File Manager** شوید و به `public_html` بروید
2. فایل `host_deploy_v<نسخه>.zip` را **Upload** کنید
3. روی آن راست‌کلیک → **Extract** (تیک Delete archive after extraction را بزنید)
4. حالا پوشه‌ی `public_html/host_deploy/` ساخته شده است

### ۲. ساخت اپلیکیشن Python

1. در cPanel وارد **Setup Python App** شوید
2. **Create Application** با این مقادیر دقیق:
   - **Python version:** `3.11`
   - **Application root:** `public_html/host_deploy`
   - **Application URL:** دامنه‌ی شما (مثلاً `panel.example.com`)
   - **Application startup file:** `passenger_wsgi.py`
   - **Application Entry point:** `application`
3. **Create** را بزنید و صبر کنید محیط ساخته شود

### ۳. نصب پکیج‌ها

#### ۳-الف) بدون SSH/Terminal — فقط با دکمه‌ی **Run Pip Install**

اگر دسترسی Terminal/SSH ندارید، فقط دکمه‌ی نصب را بزنید. لازم نیست فایل
جداگانه‌ای بسازید؛ **هم `requirements.txt` و هم `requirements-nobuild.txt`**
از قبل `--only-binary=:all:` دارند و برای هاست امن‌اند:

1. در صفحه‌ی اپلیکیشن → **Configuration files**، اگر `requirements-nobuild.txt`
   را دیدید همان را انتخاب کنید؛ وگرنه `requirements.txt` را انتخاب کنید.
2. **Run Pip Install** را بزنید.

چرا دیگر خطا نمی‌دهد؟ خطِ `--only-binary=:all:` یعنی pip فقط از **wheel آماده**
نصب می‌کند و **هرگز از سورس کامپایل نمی‌کند**. چون خطای شما مثل
`Failed building wheel for greenlet` دقیقاً از کامپایل `greenlet` (یا سایر
پکیج‌های C مثل `cryptography` و `Pillow`) است، این روش بدون کامپایلر هم تمام
می‌شود.

> اگر نصب `cryptography` طول کشید طبیعی است؛ فقط یک‌بار انجام می‌شود.
> درایور MySQL (`PyMySQL`) هم داخل همین فایل است.

#### ۳-ب) با Terminal (اختیاری)

اگر در همان صفحه‌ی اپلیکیشن **Terminal** دارید (آدرس فعال‌سازی venv بالای
صفحه نوشته شده)، اجرا کنید:

```bash
pip install --prefer-binary -r requirements.txt
```

> روی هاست اشتراکی معمولاً کامپایلر C وجود ندارد. اگر خطای
> `Failed building wheel for greenlet` گرفتید، به‌جای دستور بالا این را اجرا کنید:
>
> ```bash
> python tools/install_deps.py
> ```
>
> این اسکریپت اول pip را به‌روز می‌کند، بعد greenlet را فقط از wheel آماده نصب
> می‌کند و اگر wheel نبود، همه‌چیز را بدون greenlet نصب می‌کند (برنامه sync است
> و به greenlet نیازی ندارد).

### ۴. دسترسی پوشه‌ها

در همان Terminal:

```bash
chmod 755 instance backups logs static/uploads
```

(اگر باز خطای «قابل نوشتن نیست» دیدید، `755` را `775` کنید.)

### ۵. ورود به برنامه

اپلیکیشن را **Restart** کنید و دامنه را باز کنید:

```
نام کاربری: admin
رمز عبور:   admin123
```

> ⚠ **حتماً پس از اولین ورود** از بخش «کاربران»، رمز عبور را تغییر دهید!
> تا وقتی رمز پیش‌فرض است، در هر ورود هشدار می‌بینید.

### ۶. تنظیمات اختیاری پس از ورود

- **مشخصات آموزشگاه:** منوی تنظیمات (یا `/setup?force=1` برای ویزارد کامل)
- **MySQL به‌جای SQLite:** منوی «تنظیمات دیتابیس» (`/setup/database`) را باز کنید،
  اطلاعات دیتابیسی که در cPanel → MySQL Databases ساخته‌اید را وارد کنید،
  ذخیره کنید و بعد اپلیکیشن را **Restart** کنید
- **لایسنس:** اگر کلید دارید، از صفحه‌ی فعال‌سازی وارد کنید

---

## مسیر B) سرور مجازی VPS (لینوکس + Gunicorn + Nginx)

```bash
# ۱. انتقال و باز کردن بسته
unzip host_deploy_v*.zip && cd host_deploy

# ۲. محیط مجازی و نصب (شامل gunicorn)
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements-prod.txt

# ۳. دسترسی‌ها
chmod 755 instance backups logs static/uploads

# ۴. کلید ثابت نشست (خیلی مهم — وگرنه هر ری‌استارت همه خارج می‌شوند)
export SECRET_KEY="$(python -c 'import secrets; print(secrets.token_hex(32))')"

# ۵. اجرا
gunicorn --config gunicorn.conf.py wsgi:application
# سپس در Nginx:  proxy_pass http://127.0.0.1:5000;
```

ورود پیش‌فرض مثل مسیر A است: `admin` / `admin123`.

> نکته‌ی SQLite: بیش از ۲ ورکر نگذارید (نوشتن همزمان محدود است).
> برای ترافیک بالا، MySQL/PostgreSQL را از `/setup/database` فعال کنید.

---

## نکات مهم رفتاری روی هاست

| موضوع | رفتار |
|------|-------|
| `SECRET_KEY` | در اولین بوت همان هاست ساخته و در `settings.json` ذخیره می‌شود؛ نیازی به تنظیم دستی نیست (روی VPS با `export SECRET_KEY` ثابت نگهش دارید) |
| پشتیبان‌گیری خودکار | روی هاست اشتراکی **خاموش** است (محدودیت منابع)؛ از «مرکز پشتیبان‌گیری» داخل برنامه به‌صورت دستی بگیرید |
| ربات بله | دریافت خودکار روی هاست اشتراکی **خاموش** است؛ ارسال دستی از داخل برنامه کار می‌کند |
| دیتابیس | پیش‌فرض SQLite در `instance/academy.db`؛ همان‌جا ساخته می‌شود |
| لاگ‌ها | `logs/academy.log` (لاگ برنامه) و `logs/passenger_error.log` (خطای بوت) |

روشن‌کردن دستی زمان‌بند/ربات روی هاست اشتراکی (توصیه نمی‌شود):
در Setup Python App → همان اپلیکیشن → Environment variables مقدار
`ACADEMY_DISABLE_SCHEDULER` یا `ACADEMY_DISABLE_BALE` را `0` بگذارید و Restart کنید.

## عیب‌یابی

| علامت | علت محتمل و راه‌حل |
|------|---------------------|
| خطای 500 یا «Internal Server Error» | `logs/passenger_error.log` و `logs/academy.log` را در File Manager بخوانید؛ علت دقیق آن‌جاست. سپس Restart کنید |
| «unable to open database file» | پوشه‌ی `instance/` قابل نوشتن نیست → `chmod 755 instance` و Restart |
| نشست‌ها بعد از Restart می‌پرند | `settings.json` قابل نوشتن نیست و `SECRET_KEY` ذخیره نمی‌شود → `chmod 644 settings.json` و Restart |
| صفحه‌ی سفید / 404 روی همه‌ی مسیرها | Application root یا startup file اشتباه است؛ باید `public_html/host_deploy` و `passenger_wsgi.py` باشد |
| `ModuleNotFoundError` | `pip install -r requirements.txt` کامل اجرا نشده؛ در Terminal همان اپلیکیشن دوباره اجرا و Restart کنید |
| `Failed building wheel for greenlet` | هاست کامپایلر C ندارد. اگر فقط دکمه‌ی **Run Pip Install** دارید، روی `requirements.txt` یا `requirements-nobuild.txt` نصب کنید (هر دو wheel-only هستند و کامپایل نمی‌کنند)؛ اگر **Terminal** دارید `python tools/install_deps.py` را اجرا کنید (خودکار wheel آماده را نصب می‌کند و در نبود آن، بدون greenlet ادامه می‌دهد) |
| تغییر دیتابیس به MySQL اعمال نشد | پس از ذخیره در `/setup/database` حتماً اپلیکیشن را Restart کنید |
| فراموشی رمز مدیر | در Terminal همان اپلیکیشن (داخل `public_html/host_deploy` با venv فعال): `ACADEMY_DISABLE_SCHEDULER=1 python -c "from app import create_app; from extensions import db; from models.user import User; a=create_app(); a.app_context().push(); u=User.query.filter_by(username='admin').first(); u.set_password('admin123'); db.session.commit(); print('done: admin password reset')"` — سپس Restart کنید و با `admin123` وارد شوید |

## نکات امنیتی

- `settings.json` و `instance/` و `backups/` و `logs/` با `.htaccess` از دسترس وب
  خارج‌اند؛ آن فایل‌ها را پاک نکنید
- رمز پیش‌فرض (`admin123`) را در اولین فرصت عوض کنید
- روی VPS حتماً `SECRET_KEY` ثابت و HTTPS (Nginx + گواهی) بگذارید و
  `ACADEMY_COOKIE_SECURE=1` را فعال کنید
