# سامانه لایسنس و به‌روزرسانی خودکار — حساب داری آموزشگاهی رهسا

سرور لایسنس: `https://ls.ariapadideh.ir` · شناسه محصول: `hesabdari` ·
نوع برنامه: `desktop_windows` · نسخه فعلی: `1.0.1`

> **یک بیلد برای همه‌ی مشتری‌ها.** هیچ کلید لایسنس، نام مشتری، تاریخ انقضا یا
> فهرست دسترسی در کد ثابت نشده است. کاربر کلید را در صفحه‌ی `/license/activate`
> وارد می‌کند و همه‌ی این مقادیر از پاسخِ **امضاشده‌ی** سرور خوانده می‌شود.

---

## ۱) نقشه‌ی برنامه (فاز ۰) و تصمیم متناظر

| یافته در برنامه مقصد | محل | تصمیم پیاده‌سازی |
|---|---|---|
| الگوی کارخانه `create_app()` | `app.py:12` | `init_license(app)` داخل کارخانه، **پیش از** ثبت Blueprintها (`app.py`، بعد از ساخت پوشه‌های آپلود) |
| چند نقطه ورود: `app.py`, `app_desktop.py`, `wsgi.py`, `passenger_wsgi.py` | ریشه | همه از `create_app()` عبور می‌کنند → یک نقطه‌ی تزریق کافی است |
| ۳۰ Blueprint و ۳۴۲ مسیر | `routes/*.py` | نگاشت بخش↔مسیر به‌صورت داده در `license_features.py` + نگهبان `before_request` که **همه‌ی** مسیرهای هر بخش را می‌پوشاند |
| Flask-Login با `@login_required` و `utils/decorators.require_permission` | `routes/*` | `@license_required` بالای `@login_required` و `@licensed_section()` زیر آن؛ هیچ دکوراتور موجودی حذف یا جابه‌جا نشد |
| SQLAlchemy + SQLite در `instance/academy.db` | `config.py` | افزوده شدن به فهرست محافظت‌شده‌ی به‌روزرسانی (`license_updater.PRESERVE`) |
| پیکربندی در `settings.json` (`config.load_config`) | `config.py` | بخش جدید `license` در همان فایل (server_url/channel/auto_update) — بدون مکانیزم جدید |
| آپلودها در `static/uploads`, بکاپ در `backups/` | `app.py:36-38` | هر دو در فهرست محافظت‌شده |
| نمایش پیام با `flash()` + قالب پایه `templates/base/layout.html` | قالب‌ها | پیام‌های لایسنس با همان `flash()`؛ `locked.html` از همان `base/layout.html` ارث می‌برد |
| اسکجولر پشتیبان‌گیری خودکار (APScheduler) | `app.py:126` | تسک زمان‌بندی‌شده هم بررسی بخش `backup` می‌کند |
| Long-Polling ربات بله در استارتاپ | `app.py` | فقط با لایسنسِ بخش `integrations` راه می‌افتد |
| CSRFProtect سراسری | `extensions.py` | فرم فعال‌سازی `csrf_token` دارد؛ هیچ معافیتی اضافه نشد |

---

## ۲) فایل‌های اضافه‌شده

| فایل | نقش |
|---|---|
| `license_client.py` | هسته: تایید امضای RSA، شناسه دستگاه، کش رمزنگاری‌شده، ماشین وضعیت، ضربان، دکوراتورها، نگهبان `before_request`، `init_license` |
| `license_features.py` | فهرست ۲۵ بخش قابل قفل + نگاشت کامل endpoint↔بخش + گزارش پوشش |
| `license_updater.py` | بررسی/دانلود/تایید SHA-256/نصب (`full` و `manifest`)/پشتیبان و بازگردانی/ری‌استارت ویندوز |
| `routes/license.py` | Blueprint `license`: فعال‌سازی، وضعیت، اعتبارسنجی مجدد، آزادسازی، به‌روزرسانی دستی، health |
| `templates/license/activate.html` | صفحه‌ی فعال‌سازی (مستقل از قالب پایه — بدون نیاز به ورود کاربر) |
| `templates/license/blocked.html` | صفحه‌ی «لایسنس نامعتبر» با پیام دقیق سرور |
| `templates/license/locked.html` | بخش قفل: فقط جمله‌ی «لایسنس شما معتبر نیست»، با ارث‌بری از `base/layout.html` |
| `templates/license/status.html` | وضعیت لایسنس و فهرست بخش‌ها |
| `templates/license/banner.html` | نوار هشدار مهلت نرمش / حالت آفلاین |
| `VERSION` | نسخه‌ی جاری (`1.0.1`) — مرجع `update/check` |
| `tests/test_license.py` | ۵۸ آزمون با سرور لایسنس ساختگیِ امضاکننده |

## ۳) فایل‌های تغییر یافته (فقط افزودنی)

| فایل | تغییر |
|---|---|
| `app.py` | `from license_client import init_license; init_license(app)` پیش از ثبت Blueprintها · ثبت `license_bp` · بررسی بخش `backup` در `_scheduled_backup` · راه‌اندازی مشروط پولینگ بله |
| `config.py` | بخش `license` در `load_config()` |
| `requirements.txt` | `cryptography==43.0.1` |
| `routes/*.py` (۲۱ فایل) | `import` + `@license_required` و `@licensed_section('...')` روی یک مسیر شاخص از هر بخش (لایه‌ی دوم مستقل) |
| `utils/sms_service.py` | `send_configured_sms` بدون بخش `messaging` ارسال نمی‌کند (کنترل در عمق سرویس) |
| `routes/features.py` | `perform_backup()` با `assert_feature('backup')` |
| `templates/base/layout.html` | `{% include 'license/banner.html' %}` |
| `templates/base/sidebar.html` | لینک «لایسنس و به‌روزرسانی» (بدون هیچ شرط `has_feature`) |
| `app_desktop.spec` | افزودن ماژول‌های لایسنس و `cryptography` به بیلد PyInstaller |
| `tests/test_system.py` | fixture تزریق وضعیت معتبر در حافظه برای آزمون‌های موجود |
| `.gitignore` | `restart.bat`، `.update_backup/` |

نصب وابستگی‌ها:

```bash
pip install -r requirements.txt        # یا حداقل: pip install requests cryptography
```

---

## ۴) فهرست بخش‌ها برای ثبت در پنل مدیریت (فاز ۶-۱)

این فهرست هنگام `activate` به‌صورت خودکار در فیلد `available_features` به سرور
اعلام می‌شود. اگر خواستید دستی وارد کنید:

```json
[
  {"key": "students",         "label": "مدیریت هنرجویان",              "description": "فهرست، ثبت، ویرایش و پرونده هنرجویان، کارت و QR"},
  {"key": "teachers",         "label": "مدیریت مدرسان",                "description": "فهرست و پرونده مدرسان، برنامه و رتبه‌بندی"},
  {"key": "courses",          "label": "دوره‌ها و رشته‌ها",             "description": "تعریف رشته‌ها، دوره‌ها و سرفصل‌ها"},
  {"key": "classes",          "label": "کلاس‌ها و جلسات",               "description": "ایجاد کلاس، تقویم، جلسات، ادغام و تفکیک کلاس"},
  {"key": "registration",     "label": "ثبت‌نام",                       "description": "ثبت‌نام هنرجو در دوره، ثبت‌نام سریع و انصراف"},
  {"key": "attendance",       "label": "حضور و غیاب",                   "description": "ثبت حضور، گزارش غیبت و دستگاه‌های حضور و غیاب"},
  {"key": "exams",            "label": "آزمون‌ها و نمرات",              "description": "آزمون، بانک سوالات، ثبت نمره و کارنامه"},
  {"key": "finance",          "label": "امور مالی",                     "description": "پرداخت‌ها، صندوق، بانک، چک، هزینه‌ها و تخفیف‌ها"},
  {"key": "installments",     "label": "اقساط",                         "description": "داشبورد اقساط، پرداخت قسط، جریمه دیرکرد و یادآوری"},
  {"key": "accounting",       "label": "حسابداری",                      "description": "دفتر کل، روزنامه، معین، تراز و سود و زیان"},
  {"key": "payroll",          "label": "حقوق و دستمزد",                 "description": "قرارداد، محاسبه حقوق، فیش حقوقی و هزینه‌های پیشرفته"},
  {"key": "tax",              "label": "مالیات",                        "description": "محاسبه‌گر مالیات، لیست ماهانه و گزارش سالانه"},
  {"key": "reports",          "label": "گزارش‌ها",                      "description": "گزارش‌های هنرجو، مالی، حضور، ثبت‌نام و رتبه‌بندی"},
  {"key": "analytics",        "label": "تحلیل هوشمند",                  "description": "پیش‌بینی ثبت‌نام، ریزش، بدهکاران پرخطر و دستیار هوشمند"},
  {"key": "messaging",        "label": "پیام‌رسانی و پیامک",            "description": "ارسال پیامک، پیام داخلی، قالب‌ها و یادآورهای خودکار"},
  {"key": "integrations",     "label": "اتصالات (تلگرام، بله، پنل پیامک)", "description": "پیکربندی ربات‌ها، وب‌هوک‌ها و پنل پیامکی"},
  {"key": "bot_panel",        "label": "پنل ربات",                      "description": "کاربران ربات، پیام همگانی، کیبوردها و آمار"},
  {"key": "certificates",     "label": "گواهینامه‌ها",                  "description": "صدور، چاپ، استعلام و قالب گواهینامه"},
  {"key": "crm",              "label": "باشگاه مشتریان و پشتیبانی",     "description": "شکایات، نظرسنجی، تیکت، اهداف، مشتریان سازمانی و نمایندگی"},
  {"key": "teacher_portal",   "label": "پرتال مدرس",                    "description": "پنل اختصاصی مدرس: کلاس‌ها، برنامه، حقوق و ارزیابی"},
  {"key": "user_management",  "label": "کاربران و سطوح دسترسی",         "description": "تعریف کاربر، نقش، مجوزها و تنظیمات امنیتی"},
  {"key": "backup",           "label": "پشتیبان‌گیری و بازیابی",         "description": "ساخت، دانلود، بازیابی، رمزگذاری و آزمون فایل پشتیبان"},
  {"key": "export_data",      "label": "خروجی اکسل و PDF",              "description": "دانلود خروجی CSV/PDF گزارش‌ها و فهرست‌ها"},
  {"key": "hardware_devices", "label": "دستگاه‌های سخت‌افزاری",          "description": "دستگاه حضور، بارکدخوان، چاپگر کارت، POS و دوربین"},
  {"key": "advanced_tools",   "label": "ابزارهای پیشرفته",              "description": "فرم‌ساز، قالب چاپ، پاکسازی و نگهداری پایگاه‌داده"}
]
```

---

## ۵) جدول نگاشت بخش ↔ مسیرهای واقعی (فاز ۶-۶)

پوشش کامل است: `python tests/test_license.py` بررسی می‌کند که **هیچ**
endpointی بدون نگاشت نمانده باشد (بخش ۱۴ آزمون).

| شناسه بخش | مسیرهای واقعی (نمونه‌ی کامل در `license_features.py`) | فایل | وضعیت |
|---|---|---|---|
| `students` | `/students/*` (فهرست، ثبت، ویرایش، حذف، جستجو، لیست انتظار) · `/students/<id>/qr` · `/students/<id>/card` · `/students/<id>/suggested-courses` | `routes/students.py`, `features.py`, `features2.py` | منطبق |
| `teachers` | `/teachers/*` · `/teachers/ranking` | `routes/teachers.py`, `features.py` | منطبق |
| `courses` | `/courses`, `/courses/add`, `/courses/<id>`, `/courses/<id>/edit` · `/settings/fields(+/add)` · `/settings/courses(+/add)` | `routes/new_features.py`, `settings.py` | منطبق |
| `classes` | `/classes/*` (ایجاد، ویرایش، حذف، جلسات، انتقال، تقویم) · `/classes/<id>/merge|split|print|pdf|attendance-sheet` · `/settings/rooms(+/add)` · `/settings/academic-year(+/add)` | `routes/classes.py`, `features.py`, `new_features.py`, `settings.py` | منطبق |
| `registration` | `/registration/*` (افزودن، مشاهده، انصراف، اقساط، سریع) · `/students/<id>/multi-register` | `routes/registration.py`, `final.py` | منطبق |
| `attendance` | `/attendance/*` شامل `POST /attendance/session/<id>`، `/attendance/api/class-sessions/<id>`، `/attendance/device/punch`، `/attendance/devices/<id>/toggle` | `routes/attendance.py` | منطبق |
| `exams` | `/exams/*` · `/exams/<id>/auto-generate` · `/grades/report-card/<student_id>` · `/grades/report-card/class/<class_id>` | `routes/exams.py`, `features.py` | منطبق |
| `finance` | `/finance/payments|cashbox|bank|checks|expenses|discounts|salary|dashboard` و همه‌ی POSTهای آن‌ها · `/finance/checks/alerts` · `/settings/expense-categories(+add/edit/delete)` | `routes/finance.py`, `features.py`, `settings.py` | منطبق |
| `installments` | `/finance/installments` · `POST /finance/installments/<id>/pay` · `/finance/installments/batch-reminders|report|auto-late-fee` | `routes/new_features.py` | منطبق |
| `accounting` | `/accounting/*` (دفتر، روزنامه، معین، تراز، سود و زیان و همه‌ی POSTها) | `routes/accounting.py` | منطبق |
| `payroll` | `/payroll*`, `/payroll/contracts(+add)`, `/payroll/calculate`, `/payroll/payslip/<id>(+approve/pay)`, `/expenses/advanced(+add)`, `/expenses/categories(+add)`, `/reports/comprehensive` | `routes/payroll.py` | منطبق |
| `tax` | `/tax`, `/tax/calculator`, `/tax/receipt/<id>`, `/tax/annual-report`, `/tax/monthly-list`, `POST /tax/auto-calculate` | `routes/tax.py` | منطبق |
| `reports` | `/reports/*` · `/reports/course-ranking|branch-ranking|staff-ranking|staff-rewards|custom-builder` | `routes/reports.py`, `features.py`, `features2.py` | منطبق |
| `analytics` | `/analytics/dashboard|enrollment-forecast|churn-analysis|high-risk-debtors|customer-behavior|marketing-suggestions` · `/assistant` · `/settings/usage-analytics` | `routes/additional.py`, `features2.py`, `features.py` | منطبق |
| `messaging` | `/messaging/*` · `/messaging/farazsms/send` · `/messaging/birthday-check` · `/settings/sms` · `/settings/message-templates(+add)` · `/settings/auto-sms-triggers` و ۴ تریگر · `/panel/farazsms/send-bulk` · `/panel/farazsms/send-installment-reminders` · `/settings/crisis-alert` | `routes/messaging.py`, `features.py`, `final.py`, `settings.py`, `settings_panel.py`, `features2.py` | منطبق |
| `integrations` | `/settings/telegram(+set-webhook)`, `/settings/bale`, `/settings/farazsms`, `/webhook/telegram`, `/webhook/bale`, `/panel/telegram*`, `/panel/bale*`, `/panel/farazsms(+check/test)` | `routes/new_features.py`, `settings_panel.py` | منطبق |
| `bot_panel` | `/bot-panel/*` شامل APIهای `/bot-panel/api/users` و `/bot-panel/api/stats` | `routes/bot_panel.py` | منطبق |
| `certificates` | `/certificates/*` (صدور، PDF، ابطال، استعلام، طرح زیبا) · `/certificates/bulk/<type>` · `/settings/cert-templates` | `routes/additional.py`, `features.py`, `settings.py` | منطبق |
| `crm` | `/complaints/*`, `/surveys/*`, `/tickets/*`, `/goals/*`, `/corporate(+add)`, `/corporate/<id>/invoice`, `/franchise`, `/polls` | `routes/additional.py`, `features2.py`, `final.py` | منطبق |
| `teacher_portal` | `/my`, `/my/classes(+<id>)`, `/my/students`, `/my/schedule`, `/my/attendance`, `/my/salary`, `/my/evaluations` | `routes/teacher_portal.py` | منطبق |
| `user_management` | `/perms/*` (کاربران، نقش‌ها، مجوزها) · `/settings/users(+add/edit)` · `/settings/roles(+add)` · `/settings/security/authorized-devices` · `/settings/security/two-factor` | `routes/permissions.py`, `settings.py`, `features2.py` | منطبق |
| `backup` | `/settings/backup` · `/settings/backup/create|list|restore/<n>|download/<n>|delete/<n>|encrypt|test/<n>` · `/panel/backup(+/create)` | `routes/settings.py`, `features.py`, `features2.py`, `settings_panel.py` | منطبق |
| `export_data` | `/export/students/csv` · `/export/payments/csv` · `/finance/expenses/pdf` · `/settings/expense-categories/pdf` | `routes/features.py`, `finance.py`, `settings.py` | منطبق |
| `hardware_devices` | `/settings/hardware/attendance-device(+/sync)`, `/settings/hardware/barcode-scanner`, `/api/barcode/<code>`, `/settings/hardware/card-printer|pos-terminal|security-cameras` | `routes/features2.py` | منطبق |
| `advanced_tools` | `/settings/database/optimize|repair|stats`, `/settings/database-log`, `/settings/cleanup`, `/settings/form-builder`, `/settings/print-templates`, `/settings/workflows`, `/documents/<id>/versions`, `/settings/demo-mode`, `POST /demo/create-data` | `routes/features2.py`, `features.py`, `demo.py` | منطبق |

**مسیرهایی که عمداً قفل نمی‌شوند** (لایسنس لازم دارند ولی به بخشی وابسته نیستند):
داشبورد `/`، تنظیمات عمومی و شعب و لاگ، پنل مدیریت و پایش فنی، سلامت سیستم،
جستجوی سراسری، راهنما و پیشنهادات، ترجیحات ظاهری (تم/زبان/علاقه‌مندی‌ها)، ویزارد نصب.

**مسیرهای کاملاً معاف از لایسنس:** `static`, `favicon`, `/login`, `/logout`
و کل بلوپرینت `license` (`/license/activate`, `/license/health`, ...).

---

## ۶) چرخه‌ی اجرا

```
اجرا → کلید ذخیره‌شده؟ ── نه ─→ /license/activate (کاربر کلید را وارد می‌کند)
                          │                    ↓  POST /api/v1/activate (+available_features)
                          │            امضا و nonce تایید → کلید رمزنگاری‌شده ذخیره
                          └ بله → POST /api/v1/verify (اگر NOT_ACTIVATED بود → activate)
                                        │
                          موفق ─────────┴──── ناموفق/شبکه قطع
                            ↓                        ↓
                   کش امضاشده به‌روز شد        کش محلی (تا ۷۲ ساعت، با بررسی انقضا و ساعت)
```

- کش و کلید در `%LOCALAPPDATA%\HesabdariRahsa\license\` با دسترسی `0600`،
  رمزنگاری‌شده با کلیدی که از **شناسه‌ی دستگاه** مشتق می‌شود و مهرشده با HMAC.
- ضربان هر ۶ ساعت در ترد `daemon=True` با قفل فایل (در استقرار چندworker فقط یکی).
- بازه‌ی اعتبارسنجی و مهلت آفلاین از `revalidate_minutes` و `offline_grace_hours`
  همان پاسخ امضاشده خوانده می‌شود؛ در `in_grace` برنامه **کار می‌کند** و فقط نوار
  هشدار تمدید نشان داده می‌شود.

## ۷) لایه‌های مستقل کنترل (۸٫۵٫۴)

1. اعتبارسنجی هنگام راه‌اندازی (`init_license` → ترد پس‌زمینه)
2. نگهبان سراسری `before_request` (لایسنس + قفل بخش برای همه‌ی ۳۴۲ مسیر)
3. دکوراتورهای `@license_required` / `@licensed_section()` روی مسیرهای شاخص
4. بررسی داخل سرویس‌ها: `utils/sms_service.send_configured_sms`،
   `routes/features.perform_backup`، تسک زمان‌بندی‌شده‌ی پشتیبان، پولینگ ربات بله
5. تصمیم همیشه از **داده‌ی امضاشده** خوانده می‌شود، نه از یک پرچم بولی

---

## ۸) سناریوهای آزمون دستی

| سناریو | روش | انتظار |
|---|---|---|
| اجرای اول بدون کلید | برنامه را اجرا و `http://localhost:5000/` را باز کنید | هدایت به `/license/activate`، بدون خطای ۵۰۰ |
| کلید نامعتبر | کلید اشتباه وارد کنید | همان پیام سرور (`INVALID_KEY`) نمایش داده می‌شود |
| فعال‌سازی موفق | کلید درست (حتی با فاصله و حروف کوچک) | ورود به داشبورد؛ `license.dat` و `state.dat` در `%LOCALAPPDATA%` ساخته می‌شوند |
| اجرای دوم | برنامه را ببندید و دوباره باز کنید | فقط یک `verify` در استارتاپ؛ در حین کار درخواست اضافه‌ای نمی‌رود |
| بخش خریداری‌نشده | آیتم منوی آن بخش را کلیک کنید | کد ۲۰۰ و فقط «لایسنس شما معتبر نیست»؛ منو دست‌نخورده است |
| قفل عمقی | `POST` یا دانلود خروجی همان بخش را مستقیم صدا بزنید | همان پیام (JSON برای AJAX با کد ۲۰۰) |
| قطع اینترنت | کابل شبکه را جدا کنید و برنامه را باز کنید | برنامه کار می‌کند + نوار «ارتباط با سرور برقرار نشد» |
| پایان مهلت آفلاین | ساعت سیستم را ۴ روز جلو ببرید (بدون اینترنت) | صفحه‌ی «برای ادامه، اتصال اینترنت لازم است» |
| عقب کشیدن ساعت | ساعت را به عقب ببرید | مهلت آفلاین باطل و اتصال آنلاین الزامی می‌شود |
| ابطال از پنل | لایسنس را در پنل غیرفعال کنید و «اعتبارسنجی مجدد» بزنید | قفل کامل + پاک شدن کش؛ اجرای بعدی هم قفل است |
| کپی کش روی دستگاه دیگر | `%LOCALAPPDATA%\HesabdariRahsa\license` را به سیستم دیگر ببرید | بی‌اثر است؛ فایل باز نمی‌شود |
| سرور جعلی | با فایل hosts دامنه را به سرور خودتان بدهید | امضا رد می‌شود → «امضای سرور نامعتبر است» |
| آزادسازی دستگاه | `/license/status` → «آزادسازی این دستگاه» | یک ظرفیت آزاد و برنامه به صفحه‌ی فعال‌سازی برمی‌گردد |
| به‌روزرسانی | `/license/status` → «بررسی به‌روزرسانی» | تایید SHA-256، نصب با پشتیبان، به‌روزرسانی `VERSION`، ری‌استارت (ویندوز) |
| بسته‌ی دستکاری‌شده | هش بسته را در پنل تغییر دهید | دانلود پاک و نصب متوقف می‌شود؛ برنامه با نسخه‌ی قبلی ادامه می‌دهد |

آزمون خودکار:

```bash
python tests/test_license.py     # ۵۸ بررسی با سرور لایسنس ساختگیِ امضاکننده
python -m pytest tests/test_system.py -q
```
