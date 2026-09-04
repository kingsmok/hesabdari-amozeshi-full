# گزارش ارتقا و تکمیل پروژه — فاز ۲ (Refactoring / Missing Features / UI State)

**پایه:** کامیت `a7f8d41` (فاز ۱ — باگ‌فیکس) → این هفته روی همین شاخه
**نتیجه آزمون:** ✅ `396 passed, 2 skipped` — تمام تغییرات روی دیتابیس تازه اجرا شده و `app.py` (با لایسنس فعال مشابه تست‌ها) بالا می‌آید.

---

## ۱) فهرست بهبودها و ویژگی‌های جدید

### الف) ریفکتور Clean Code / SOLID / DRY

| # | فایل | تغییر |
|---|------|-------|
| 1 | **`utils/activity_log.py`** *(جدید)* | نقطهٔ واحد ثبت رویدادها. قبل از این ۵ ماژول `_log` جدا داشتند و ۱۸ جا `ActivityLog(...)` دست‌ساز بود (با `module` تکراری و ریسک شکستن تراکنش). حالا یک تابع `log_activity()` با کاربر/IP خودکار و هرگز-خطا. |
| 2 | `routes/auth.py, classes.py, students.py, teachers.py, registration.py, backup_center.py, new_features.py, finance.py, payroll.py, tax.py, accounting.py` | همهٔ لاگ‌های دستی به `utils/activity_log` سوق داده شدند (حذف ~۱۸ ساخت تکراری) |
| 3 | **`utils/constants.py`** *(جدید)* | منبع واحد ثابت‌ها: `PAYMENT_METHODS`، `CASHBOX_REF_TYPES`، `CONTRACT_TYPES`، `PERSON_TYPES`، `MAX_MONEY`، `APP_VERSION` (خوانده‌شده از `VERSION`) |
| 4 | `routes/payroll.py` | حذف دیکشنری‌های هاردکد `_CONTRACT_TYPES/_PERSON_TYPES` → import از `constants` |
| 5 | **`utils/validators.py`** *(جدید)* | اعتبارسنجی مرکزی: `normalize_payment_method`، `normalize_ref_type`، `validate_period`، `money_in_range` |
| 6 | `routes/finance.py, registration.py` | whitelist روش پرداخت/نوع مرجع → `validators` (رفتار یکسان در همهٔ مسیرها) |
| 7 | **`utils/config_loader.py`** *(جدید)* | کانفیگ مرکزی: `build_config()` = کنترل سازگاری نسخه‌ها + بارگذاری `settings.json` + مسیرها؛ `apply_to_app()` = اعمال همهٔ تنظیمات امنیتی/سشن/کش در یک نقطه (SRP). قبل از این ~۴۰ خط تنظیمات در `app.py` و چک‌ها جدا بود. |
| 8 | `app.py` | برداشته شدن ۴۰+ خط پیکربندی تکراری؛ فقط `build_config()` + `apply_to_app()` |

### ب) تکمیل امکانات جاافتاده

| # | قابلیت | فایل | توضیح |
|---|--------|------|-------|
| 9 | **مدیریت جامع خطاها** | `utils/error_handling.py` + `templates/errors/500.html` | هندلر ۴۰۳/۴۰۴/۵۰۰/Exception سراسری: ثبت `traceback` کامل در لاگ فایل، بدون لو دادن جزئیات به کاربر، نمایش «کد پیگیری» برای پشتیبانی؛ در DEBUG همان stack Werkzeug | 
| 10 | **لاگ‌گیری فایل** | `utils/logging_config.py` *(فاز ۱ — اکنون توسط هندلر خطا هم استفاده می‌شود)* | `logs/academy.log` چرخشی ۵MB×۵ |
| 11 | **اعتبارسنجی ورودی مرکزی** | `utils/validators.py` | قواعد روش پرداخت، نوع مرجع صندوق، دورهٔ شمسی، بازهٔ مبلغ — یک منبع |
| 12 | **کانفیگ مرکزی** | `utils/config_loader.py` | یک ورودی واحد برای تمام اسکریپت‌های بوت (در آینده `first_run.py`/`app_desktop.py` هم می‌توانند از آن استفاده کنند) |
| 13 | **هدرهای امنیتی + لاگ درخواست** | `app.py` *(فاز ۱ — در جدول می‌ماند چون بخشی از زیرساخت حرفه‌ای است)* | `nosniff`, `SAMEORIGIN`, `Referrer-Policy`, `Permissions-Policy` + لاگ POST/5xx با زمان |

### ج) پرفورمنس (کوئری‌ها/حلقه‌ها)

| # | محل | قبل | بعد |
|---|-----|-----|-----|
| 14 | `app.py → get_user_menu_items` | برای هر آیتم منو (≈۱۵) یک کوئری `has_module_access` → تا ۱۵ کوئری در *هر* صفحه | یک کوئری `module` های نقش (`JOIN role_permissions`) |
| 15 | `routes/dashboard.py → admin_dashboard` | `today_classes` → ۱+N کوئری مدرس؛ `recent_regs` → ۱+۲N کوئری هنرجو/دوره | `joinedload(ClassGroup.teacher)` و `joinedload(Registration.student/course)` |
| 16 | `routes/dashboard.py → secretary_dashboard` | `recent_regs` N+1 | همان `joinedload` |
| 17 | `routes/accounting.py` (فاز ۱) + `payroll/tax`, `tax/dashboard` (فاز ۱) | N+1 در دفتر/گزارش‌ها | یک‌جا load — نگه‌داری و تست شده |

### د) UI/UX و State Management

| # | قابلیت | فایل | توضیح |
|---|--------|------|-------|
| 18 | **`ui-core.js` (State مرکزی)** | `static/js/ui-core.js` *(جدید)* | `Ui.api()` = fetch مشترک با CSRF + JSON + شمارندهٔ busy مرکزی + Toast خطا؛ `Ui.toast()`، `Ui.busy()`، `Ui.confirm()`، `Ui.csrf()` — قبلاً هر fetch جدا بود و وضعیت busy/خطا هیچ‌جا یکپارچه نبود |
| 19 | **نشانگر «در حال پردازش» سراسری** | `templates/base/layout.html` | یک element `#globalBusy` با شمارندهٔ مرکزی؛ درخواست‌های موازی درست کار می‌کند و بعد از ۳۰۰ms ظاهر می‌شود (بدون پرش) |
| 20 | **نمایش یکپارچهٔ پیام‌ها** | `app.js` | `showToast` قدیمی به `Ui.toast` سوق داده شد (سازگاری کامل)؛ جستجوی سراسری و dark-mode به `Ui.api` منتقل شدند |
| 21 | **بستن خودکار flashها** | `app.js` | هشدارهای موفقیت/خطای سمت سرور بعد از ۶ ثانیه خودکار بسته می‌شوند (قبلاً روی صفحه می‌ماندند) |
| 22 | **جلوگیری از ارسال دوبارهٔ فرم** | `app.js` | دابل‌کلیک روی «ذخیره» دیگر درخواست تکراری نمی‌فرستد؛ دکمه بعد از submit غیرفعال و بعد از ۱۰ ثانیه آزاد می‌شود (لایهٔ دومِ گارد اتمیک سمت سرور) |
| 23 | **Login خودکفا** | `templates/auth/login.html` | `ui-core.js` روی صفحهٔ ورود هم لود می‌شود (قبلاً هیچ‌کدام از JS های اصلی نبود) |

---

## ۲) فایل‌های نهایی اصلاح‌شده (آمادهٔ جایگزینی)

```diff
+ utils/activity_log.py        # NEW  ثبت مرکزی رویدادها (جایگزین ۱۸ ساخت تکراری)
+ utils/constants.py           # NEW  ثابت‌های مرکزی (روش پرداخت، قرارداد، نسخه...)
+ utils/validators.py          # NEW  اعتبارسنجی مرکزی ورودی‌ها
+ utils/config_loader.py       # NEW  کانفیگ مرکزی (چک سازگاری + settings.json + مسیرها)
+ utils/error_handling.py      # NEW  مدیریت جامع خطاها (403/404/500/Exception)
+ templates/errors/500.html    # NEW  صفحهٔ ۵۰۰ کاربرپسند با کد پیگیری
+ static/js/ui-core.js         # NEW  State Management مرکزی UI (fetch/CSRF/busy/toast)

M app.py                       # پیکربندی از ۴۰+ خط به ۲ فراخوان؛ هندلر خطا؛ منو با یک کوئری
M routes/auth.py               # لاگ مرکزی (ورود/خروج/ناموفق/قفل)
M routes/students.py           # لاگ مرکزی
M routes/teachers.py           # لاگ مرکزی
M routes/classes.py            # لاگ مرکزی
M routes/registration.py       # لاگ مرکزی + اعتبارسنجی روش پرداخت
M routes/finance.py            # لاگ مرکزی + اعتبارسنجی مرکزی
M routes/accounting.py         # لاگ مرکزی
M routes/payroll.py            # لاگ مرکزی + ثابت‌ها از constants + دوره از validators
M routes/tax.py                # لاگ مرکزی
M routes/backup_center.py      # لاگ مرکزی
M routes/new_features.py       # لاگ مرکزی
M routes/dashboard.py          # رفع N+1 (کلاس‌های امروز + آخرین ثبت‌نام‌ها)
M templates/base/layout.html   # ui-core + نشانگر سراسری busy + کلاس flash-alert
M templates/auth/login.html    # ui-core روی صفحهٔ ورود
M static/js/app.js             # Ui.api در جستجو/dark-mode؛ بستن flash؛ گارد دابل‌ارسال
```

## ۳) نحوهٔ اجرا / آزمون

```bash
pip install -r requirements.txt pytest
python -m pytest -q                 # → 396 passed, 2 skipped
python app.py                       # http://0.0.0.0:5000
# مشاهدهٔ لاگ: logs/academy.log ; سطح: ACADEMY_LOG_LEVEL=DEBUG
```

**تست دستی پیشنهادی:** یک مسیر را عمداً خطا بدهید → باید صفحهٔ ۵۰۰ با «کد پیگیری» + traceback در `logs/academy.log` ببینید؛ در صفحات داخل سیستم، هنگام هر درخواست، نشانگر «در حال پردازش…» بالای صفحه و بستن خودکار هشدارها را ببینید.
