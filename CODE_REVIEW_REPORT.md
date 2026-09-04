# گزارش بررسی ۳۶۰ درجه — Academy Manager Pro (hesabdari-amozeshi-full)

**نسخه بازبینی‌شده:** `VERSION = 1.0.1` — کامیت پایه `4dd86fc`
**تاریخ:** ۲۰۲۶/۰۹/۰۴
**نتیجه کل:** ✅ تمام تغییرات اعمال و روی دیتابیس تازه اجرا شده است:
**`396 passed, 2 skipped`** (قبل از اصلاحات: 6 خطای setup در دیتابیس تازه).

---

## ۱) فهرست مشکلات پیدا شده و رفع‌شده

### باگ‌های منطقی / داده‌ای (Critical)

| # | فایل | مشکل | رفع |
|---|------|------|-----|
| 1 | `models/user.py` | `ActivityLog.user_id` با `nullable=False` تعریف شده بود، ولی رویدادهای امنیتیِ «کاربر ناشناس» (`login_locked` با نام کاربری اشتباه) با `user_id=None` ثبت می‌شدند → `IntegrityError` و از دست رفتنِ بی‌صدای لاگ امنیتی | ستون `nullable=True` شد تا رویدادهای سیستمی/ناشناس هم ثبت شوند |
| 2 | `routes/finance.py` | ابطال/بازگردانی پرداخت دو مرحله‌ای «چک وضعیت + تغییر» بود؛ دو درخواست هم‌زمان (یا دابل‌کلیک) هر دو تأیید می‌گرفتند → **دو بار مرجوعی/دو بار برگشت** مبلغ | ماژول جدید `utils/money_guard.py` با انتقال وضعیت اتمیک (CAS: `UPDATE ... WHERE status`) — فقط اولین درخواست برنده است |
| 3 | `routes/payroll.py` | همان race در **پرداخت فیش حقوقی** (دو بار حقوق!) و **ابطال فیش** (دو بار برگشت وجه به صندوق) | همان گارد اتمیک روی `pay` و `cancel` |
| 4 | `routes/payroll.py` | فیشِ «تأییدشده» (`approved`) قابل ویرایش بود؛ یعنی بعد از تأیید، مبلغ عوض می‌شد و همان فیشِ تأییدشده پرداخت می‌شد | ویرایش فقط برای `draft`؛ تأییدشده باید ابطال و دوباره صادر شود |
| 5 | `routes/registration.py` | `payment_method` از فرم بدون whitelist گرفته می‌شد → مقدار دلخواه باعث می‌شد `settle_cashbox` سهم نقدی را صفر ببیند و «پرداخت نقدی» به صندوق نرود | روش پرداخت فقط از مقادیر مجاز (`cash/card/online/check/combined`) |
| 6 | `config.py` | URI دیتابیس MySQL/PostgreSQL بدون کدکردن نام کاربری/رمز ساخته می‌شد؛ رمز دارای `@` یا `:` اتصال را می‌شکست | `urllib.parse.quote_plus` روی اعتبارنامه‌ها |
| 7 | `routes/tax.py` | سال پیش‌فرض داشبورد مالیاتی هاردکد `1405` بود | از `current_jalali_period()` خوانده می‌شود |
| 8 | `tests/test_report_builder.py`، `tests/test_uploads.py` | تست‌ها به وجود «حساب مدیر» در دیتابیس مشترک وابسته بودند؛ ولی `create_app()` عمداً مدیر پیش‌فرض نمی‌سازد (ویزارد `/setup`) → اجرای `pytest` روی دیتابیس تازه ۶ خطای setup می‌داد | fixture‌های `admin_client`/`live_client` خودکفا شدند (ساخت موقت + پاک‌سازی) |
| 9 | `tests/test_deploy_host.py` | فهرست ماژول‌های استانداردِ تست ناقص بود (`time` غایب) و با import جدید خطای کاذب می‌داد | `time` به `third_party` اضافه شد |

### باگ‌های عملکردی (Performance)

| # | فایل | مشکل | رفع |
|---|------|------|-----|
| 10 | `routes/accounting.py` | دفتر حساب (`account_ledger`) برای هر ردیف، ۲ کوئری جداگانه (`Account` و `Entry`) می‌زد → N+1 با ده‌ها هزار ردیف | `joinedload` + `contains_eager` — همه در یک کوئری |
| 11 | `routes/payroll.py` (`/payroll/tax`) | به‌ازای هر فیش یک `Teacher.query.get` | نام مدرس‌ها یک‌جا با یک کوئری (`id, first_name, last_name`) |
| 12 | `routes/tax.py` (داشبورد + گزارش سالانه) | همان N+1 برای نام مدرس‌ها | جمع‌آوری یک‌جا |
| 13 | `routes/accounting.py` | در ثبت و ویرایش سند، دوره مالی دو بار `FiscalPeriod.for_date` کوئری می‌شد | یک‌بار محاسبه و استفاده مجدد |

### اتلاف منابع / رشد بی‌نهایت داده (معادل «نشت حافظه» در سطح دیتابیس)

| # | فایل | مشکل | رفع |
|---|------|------|-----|
| 14 | `utils/session_maintenance.py` *(جدید)* | جدول‌های `user_sessions` و `activity_logs` هرگز پاک نمی‌شدند — در نصب‌های پرکاربرد تا میلیون‌ها ردیف رشد می‌کردند | پاک‌سازی روزانه در بوت (نشست‌های بسته >۹۰ روز، نشست‌های باز رهاشده >۶۰ روز، لاگ‌ها >۱ سال)؛ یک‌بار در روز (timestamp stamp) |

### پاک‌سازی و Refactoring

| # | فایل | مشکل | رفع |
|---|------|------|-----|
| 15 | `utils/uploads.py` | `_silent_remove` دو بار `os.remove` بی‌فایده صدا می‌زد | حذف تکرار |
| 16 | `models/user.py` | کامنت تکراری (ورد شده) در `load_user` | یکپارچه‌سازی |
| 17 | `routes/accounting.py` | کامنت/کد تکراری جزئی در `edit_entry` | حذف |

---

## ۲) ویژگی‌های حرفه‌ای اضافه‌شده (Missing Features)

| قابلیت | فایل | توضیح |
|--------|------|-------|
| **سامانه لاگ‌گیری مرکزی** | `utils/logging_config.py` *(جدید)* | فایل لاگ چرخشی `logs/academy.log` (۵ مگ × ۵ نسخه)؛ سطح از `ACADEMY_LOG_LEVEL`؛ جایگزین `print`های بوت |
| **هدرهای امنیتی سراسری** | `app.py` | `X-Content-Type-Options: nosniff`، `X-Frame-Options: SAMEORIGIN`، `Referrer-Policy`، `Permissions-Policy`، `X-Permitted-Cross-Domain-Policies` |
| **لاگ درخواست‌های مهم** | `app.py` | هر `POST/PUT/PATCH/DELETE` و هر پاسخ ≥500 با زمان‌سنجی ثبت می‌شود |
| **کوکی امن روی HTTPS** | `app.py` | `SESSION_COOKIE_SECURE` از `ACADEMY_COOKIE_SECURE=1` (نصب‌های HTTP داخلی نمی‌شکنند) |
| **گارد اتمیک عملیات مالی** | `utils/money_guard.py` *(جدید)* | CAS (`UPDATE ... WHERE status`) برای پرداخت/ابطال/مرجوعی — دقیق‌ترین کنترل همزمانی |
| **ذخیره امن تنظیمات** | `config.py` | نوشتن اتمیک (tmp + `os.replace` + `fsync`) و `chmod 600` (شامل توکن‌ها/کلیدها) |
| **کدگذاری اعتبارنامه DB** | `config.py` | `quote_plus` → پشتیبانی از رمزهای خاص‌نویسه |
| **انتخاب موتور-aware ایندکس حقوق** | `utils/database_tools.py` | ایندکس یکتای جزئی فقط on SQLite/PostgreSQL؛ در MySQL گارد برنامه‌ای با لاگ روشن |
| **UX / State** | `static/js/app.js` | جستجوی سراسری: رفع race (شماره توالی + `AbortController`)؛ dark-mode: هندل خطای شبکه با fallback محلی |
| **ایزولیشن تست‌ها** | ۲ فایل تست + ۱ فهرست stdlib | اجرای کامل `pytest` روی چک‌اوت تازه |

---

## ۳) فایل‌های نهایی اصلاح‌شده (آماده جایگزینی)

```
app.py                      — لاگ مرکزی، هدرهای امنیتی، لاگ درخواست، نگهداری نشست‌ها
config.py                   — URI امن + ذخیره اتمی تنظیمات
models/user.py              — nullable بودن user_id در ActivityLog
routes/auth.py              — ثبت رویداد قفل برای کاربر ناشناس
routes/accounting.py        — رفع N+1 دفتر حساب + حذف کوئری تکراری
routes/finance.py           — گارد اتمیک ابطال/بازگردانی + whitelist reference_type
routes/payroll.py           — گارد اتمیک پرداخت/ابطال + قفل ویرایش فیش تأییدشده + رفع N+1
routes/registration.py      — whitelist روش پرداخت
routes/tax.py               — سال پویا + رفع N+1
static/js/app.js            — رفع race جستجو + هندل خطای dark-mode
utils/database_tools.py     — ایندکس یکتای سازگار با موتور دیتابیس
utils/uploads.py            — پاک‌سازی کد تکراری
utils/logging_config.py     — جدید: لاگ چرخشی مرکزی
utils/money_guard.py        — جدید: انتقال وضعیت اتمیک (CAS)
utils/session_maintenance.py— جدید: پاک‌سازی نشست‌ها/لاگ‌های کهنه
tests/test_report_builder.py— ایزولیشن fixture مدیر
tests/test_uploads.py       — ایزولیشن fixture مدیر
tests/test_deploy_host.py   — تکمیل فهرست stdlib
.gitignore                  — نادیده گرفتن state های runtime جدید
```

## ۴) نحوه اجرا و آزمون

```bash
# اجرای کامل تست‌ها (روی دیتابیس تازه هم کار می‌کند)
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt pytest
.venv/bin/python -m pytest -q          # → 396 passed, 2 skipped

# اجرای برنامه
python app.py                          # http://0.0.0.0:5000

# تنظیمات اختیاری
ACADEMY_LOG_LEVEL=DEBUG                # سطح لاگ (پیش‌فرض INFO)
ACADEMY_DISABLE_SCHEDULER=1            # خاموش‌کردن زمان‌بند پشتیبان (تست‌ها)
ACADEMY_COOKIE_SECURE=1                # کوکی امن روی HTTPS
```

> **نکته:** `create_app()` عمداً کاربر مدیر پیش‌فرض نمی‌سازد (امنیت — از طریق ویزارد `/setup` یا `config.ini` نصب‌کننده ساخته می‌شود). این رفتار عمداً حفظ شده است.
