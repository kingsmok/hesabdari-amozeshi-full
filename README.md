# Academy Manager Pro
## سیستم مدیریت آموزشگاه — نسخه ۱.۰.۰

### نصب

#### روش ۱: نصب‌کننده (توصیه شده)
1. فایل `AcademyManager_Setup_v1.0.0.exe` را اجرا کنید
2. مراحل نصب را دنبال کنید
3. پس از نصب، آیکون برنامه در دسکتاپ و منوی استارت ایجاد می‌شود
4. برنامه را اجرا کنید

#### روش ۲: اجرا بدون نصب
1. پوشه `AcademyManager` را در هر جا کپی کنید
2. فایل `AcademyManager.exe` را اجرا کنید

### اطلاعات ورود پیش‌فرض

```
نام کاربری: admin
رمز عبور:   admin123
```

> ⚠ حتماً پس از اولین ورود، رمز عبور را تغییر دهید!

### امکانات

- ✅ مدیریت هنرجویان (ثبت‌نام، پرونده، کارت شناسایی)
- ✅ مدیریت کلاس‌ها و دوره‌ها
- ✅ حضور و غیاب
- ✅ آزمون‌ها و نمرات
- ✅ مالی و حسابداری (دفترداری دوبل)
- ✅ حقوق و دستمزد + مالیات
- ✅ سیستم اقساط
- ✅ پیامک (FarazSMS)
- ✅ ربات تلگرام و بله
- ✅ تقویم شمسی (جلالی)
- ✅ حالت تاریک
- ✅ جستجوی سراسری (Ctrl+K)
- ✅ گزارش‌های متنوع
- ✅ مدیریت دسترسی‌ها (نقش‌محور)

### اطلاعات شبکه

برای دسترسی از سایر کامپیوترها:
- آدرس شبکه: `http://<IP>:5000`
- صفحه اطلاعات شبکه: منو → اطلاعات شبکه

### پشتیبان‌گیری

از منوی `تنظیمات > پشتیبان‌گیری` می‌توانید:
- پشتیبان‌گیری از دیتابیس
- بازگردانی اطلاعات
- دانلود فایل پشتیبان

### ساختار فایل‌ها

```
AcademyManager/
├── AcademyManager.exe    # برنامه اصلی
├── instance/
│   └── academy.db       # دیتابیس (SQLite)
├── backups/             # فایل‌های پشتیبان
├── static/
│   ├── css/            # استایل‌ها
│   ├── js/             # اسکریپت‌ها
│   ├── fonts/          # فونت‌های فارسی
│   ├── images/         # تصاویر
│   └── uploads/        # فایل‌های آپلود شده
├── templates/           # قالب‌های HTML
├── models/             # مدل‌های دیتابیس
├── routes/             # مسیرهای وب
└── utils/              # ابزارهای کمکی
```

### عیب‌یابی

**مشکل:** برنامه اجرا نمی‌شود
- مطمئن شوید پورت 5000 اشغال نیست
- فایل `instance/academy.db` را حذف کنید و دوباره اجرا کنید

**مشکل:** خطای `TypingOnly` / `__firstlineno__` / `__static_attributes__`
- علت: SQLAlchemy قدیمی با پایتون ۳.۱۳ یا ۳.۱۴ ناسازگار است
- برنامه هنگام شروع سعی می‌کند SQLAlchemy را خودکار به‌روز کند
- اگر به‌روزرسانی خودکار ممکن نبود:

```
python -m pip install --upgrade "SQLAlchemy>=2.0.31"
```

سپس `start_desktop.bat` را دوباره اجرا کنید. پایدارترین نسخه پایتون برای این برنامه ۳.۱۱ یا ۳.۱۲ است.

**مشکل:** خطای `Failed building wheel for greenlet` هنگام `pip install`

```
× Building wheel for greenlet (pyproject.toml) did not run successfully.
ERROR: Failed building wheel for greenlet
```

- علت: `greenlet` وابسته‌ی SQLAlchemy است و یک افزونه‌ی C دارد. اگر برای نسخه‌ی
  پایتون شما wheel آماده نباشد (معمولاً پایتون ۳.۱۳/۳.۱۴ به بالا یا پلتفرم غیرمعمول)،
  pip سعی می‌کند آن را کامپایل کند و بدون کامپایلر شکست می‌خورد.
- راه‌حل یک‌خطی (خودش هر سه راه‌حل را به ترتیب امتحان می‌کند):

```
python tools/install_deps.py
```

- راه‌حل‌های دستی، به ترتیب:

```
python -m pip install --upgrade pip setuptools wheel
python -m pip install --only-binary=:all: --upgrade greenlet
pip install --prefer-binary -r requirements.txt
```

- اگر برای پلتفرم شما اصلاً wheel وجود ندارد، بدون `greenlet` نصب کنید؛
  برنامه sync است و `greenlet` فقط برای SQLAlchemy async لازم است:

```
python tools/install_deps.py --skip-greenlet
```

- **روی هاست اشتراکی بدون SSH/Terminal** (فقط دکمه‌ی **Run Pip Install** در
  cPanel): دیگر لازم نیست کاری انجام دهید — خود `requirements.txt` خط
  `--only-binary=:all:` دارد، بنابراین pip هرگز پکیج‌های C (`greenlet` و ...)
  را از سورس کامپایل نمی‌کند و همان خطا پیش نمی‌آید:

  ```
  # cPanel → Setup Python App → Configuration files
  # → Run Pip Install روی requirements.txt (یا requirements-nobuild.txt)
  ```

**مشکل:** فونت‌ها نمایش داده نمی‌شوند
- فایل‌های فونت در `static/fonts/` باید موجود باشند

**مشکل:** فراموشی رمز عبور
- فایل `instance/academy.db` را حذف کنید (اطلاعات حذف می‌شوند)
- یا از ابزار بازنشانی رمز استفاده کنید

### استقرار در سرور (Docker — پیشنهادی)

```bash
# ۱) کلید امن را در فایل .env بگذارید (هرگز در git!)
echo "ACADEMY_SECRET_KEY=$(python -c 'import secrets; print(secrets.token_hex(32))')" > .env

# ۲) ساخت و اجرا
docker compose up -d --build

# ۳) لاگ / بررسی سلامت
docker compose logs -f academy
docker compose ps
```

- دیتابیس (`instance/`)، پشتیبان‌ها، لاگ‌ها و فایل‌های آپلودی روی `volume` هستند؛
  با `docker compose down` داده‌ها از بین نمی‌روند.
- برای HTTPS، یک reverse proxy (Caddy/Nginx) جلوی پورت ۵۰۰۰ بگذارید و
  `ACADEMY_COOKIE_SECURE=1` را در `.env` فعال کنید.
- پشتیبان‌گیری خودکار داخل container با CRON هاست انجام می‌شود
  (در gunicorn به‌صورت پیش‌فرض خاموش است تا چند ورکر هم‌زمان پشتیبان نسازند).

### استقرار بدون Docker (Gunicorn)

```bash
pip install -r requirements.txt -r requirements-prod.txt
export SECRET_KEY="$(python -c 'import secrets; print(secrets.token_hex(32))')"
gunicorn --config gunicorn.conf.py 'app:create_app()'   # http://0.0.0.0:5000
```

### CI / تست

هر push/PR توسط GitHub Actions (`py3.11` و `py3.12`) بررسی می‌شود:
lint (ruff) + `compileall` + کل تست‌ها (`pytest -q`).

### متغیرهای محیطی (Environment)

| متغیر | پیش‌فرض | توضیح |
|-------|---------|-------|
| `SECRET_KEY` | تولید خودکار | کلید امضای نشست — در production حتماً ثابت و قوی |
| `ACADEMY_LOG_LEVEL` | `INFO` | DEBUG/INFO/WARNING/ERROR/CRITICAL |
| `ACADEMY_DISABLE_SCHEDULER` | `0` | خاموش‌کردن زمان‌بند پشتیبان (تست‌ها/ورکرها) |
| `ACADEMY_COOKIE_SECURE` | `0` | کوکی امن (فقط HTTPS) |
| `ACADEMY_SQLITE_BUSY_TIMEOUT` | `10` | ثانیه‌های انتظار برای قفل SQLite |
| `ACADEMY_RATE_LIMIT` / `ACADEMY_RATE_PERIOD` | `120` / `60` | سقف درخواست‌های API به ازای IP+مسیر |
| `ACADEMY_ADMIN_USER` / `ACADEMY_ADMIN_PASSWORD` | `admin` / `admin123` | مشخصات مدیر پیش‌فرض در نصب تازه (فقط وقتی هیچ کاربری نیست) |
| `ACADEMY_DISABLE_BALE` | `0` | خاموش‌کردن دریافت خودکار پیام‌های بله (روی هاست اشتراکی خودکار خاموش است) |
| `GUNICORN_WORKERS` | `2` | تعداد ورکرها (SQLite ⇒ کم) |

### اطلاعات فنی

- **فریمورک:** Flask (Python) + Gunicorn (production)
- **رابط کاربری:** PyQt6 + WebEngine (دسکتاپ) / Bootstrap 5.3 (وب)
- **دیتابیس:** SQLite (پیش‌فرض)، MySQL، PostgreSQL
- **تقویم:** شمسی (جلالی)
- **زبان:** فارسی (RTL)
- **مشاهده‌پذیری:** `logs/academy.log` چرخشی + `X-Request-ID` در پاسخ‌ها

### آموزشگاه رهسا
- **وبسایت:** [rahsacademic.com](https://rahsacademic.com)
- **ایمیل:** info@rahsacademic.com

---
نسخه ۱.۰.۰ — ساخته شده با ❤️
