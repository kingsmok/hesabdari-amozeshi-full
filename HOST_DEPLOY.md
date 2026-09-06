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

## سرعت صفحه‌ها روی هاست

همهٔ منابع ظاهر برنامه **محلی** هستند — هیچ CDN بیرونی (jsDelivr، Google Fonts،
cdnjs و…) در کار نیست، بنابراین سرعت به تحریم/کندی سرویس خارجی وابسته نیست.
`download_assets.py` فقط در زمان **ساخت بسته** یک‌بار از CDN دانلود می‌کند و
فایل‌ها را داخل `static/` می‌گذارد.

سه کار خودکار انجام می‌شود:

| کار | اثر |
|-----|-----|
| **فشرده‌سازی سمت برنامه** (`bootstrap/static_assets.py`) | بستهٔ CSS ۳۷۴KB → ۴۴KB و بستهٔ JS ۱۷۰KB → ۴۰KB. پیش‌تر استاتیک بدون هیچ فشرده‌سازی فرستاده می‌شد، چون `mod_deflate` آپاچی روی همهٔ هاست‌ها روشن نیست و روی VPS/Docker آپاچی اصلاً در کار نیست |
| **Brotli به‌جای gzip (اختیاری)** | اگر بستهٔ `brotli` نصب باشد، `br` ترجیح داده می‌شود: CSS ۵۸KB → ۴۴KB و JS ۴۵KB → ۴۰KB. چون نتیجه در زمان **بوت** فشرده می‌شود، هیچ کاربری هزینهٔ CPU آن را نمی‌پردازد. نبودِ بسته هیچ چیزی را نمی‌شکند و gzip جای آن را می‌گیرد |
| **کش یک‌سالهٔ `immutable`** | آدرس فایل‌ها با `?v=<mtime>-<size>` نسخه‌دار است، پس کش یک‌ساله امن است. پیش‌تر کش یک‌روزه بود ⇒ کاربر هر روز همه‌چیز را دوباره دانلود می‌کرد. بازدید دوم عملاً هیچ بایتی نمی‌گیرد |
| **ادغام CSS/JS در یک فایل** (`utils/asset_bundle.py`) | ۲۰ منبع → ۸ منبع. روی HTTP/1.1 هر منبع یک رفت‌وبرگشت کامل است؛ این یعنی چند صد میلی‌ثانیه کمتر |
| **preload پنج وزن فونت** | خودِ چیدمان پایه به پنج وزن (۴۰۰/۵۰۰/۶۰۰/۷۰۰/۸۰۰ ≈ ۲۵۵KB) نیاز دارد. با preload، دانلودشان **موازی** با CSS شروع می‌شود نه بعد از تجزیهٔ آن |

بسته‌ها در `static/gen/` ساخته می‌شوند و **نیاز به بیلد دستی ندارند**: در هر بوت،
اثر انگشت محتوا محاسبه می‌شود و با تغییر هر فایل منبع، بستهٔ تازه ساخته و
قبلی پاک می‌شود. اگر `static/` قابل نوشتن نباشد، برنامه بی‌صدا به همان فایل‌های
جدا برمی‌گردد (پس روی نصب دسکتاپ/PyInstaller هم درست کار می‌کند).

> **نکتهٔ مهم دربارهٔ بسته‌سازی:** بسته در `static/gen/` می‌نشیند، یعنی یک سطح
> عمیق‌تر از جای اصلی منابع. آدرس‌های نسبیِ `url(...)` هنگام ساخت بسته بازنویسی
> می‌شوند (`utils/asset_bundle.py::_rebase_urls`)؛ وگرنه `url("fonts/bootstrap-icons.woff2")`
> که در `static/css/` درست بود، از `static/gen/` به مسیری حل می‌شد که وجود ندارد و
> **همهٔ آیکون‌ها خالی نمایش داده می‌شدند**. تست
> `TestBundleRelativeUrls::test_icon_font_is_served_at_the_url_the_bundle_points_to`
> دقیقاً همین را با همان کاری که مرورگر می‌کند بررسی می‌کند.

خاموش‌کردن ادغام (فقط برای عیب‌یابی):

```bash
export ACADEMY_ASSET_BUNDLE=0
```

### اندازه‌گیری‌شده (صفحهٔ اصلی، روی سرور واقعی)

شمارش با قاعدهٔ واقعی مرورگر انجام شده: قالب `.woff` قدیمی شمرده نمی‌شود
(مرورگر woff2 را ترجیح می‌دهد) و از نُه وزن فونت فقط پنج وزنی شمرده شده که
یک عنصرِ واقعاً رندرشده استفاده می‌کند.

| | قبل | بعد |
|---|---|---|
| تعداد درخواست | ۲۵ | **۱۳** |
| بایت روی سیم | ۹۴۴٬۰۶۴ | **۴۸۱٬۷۹۹** (−۴۹٪) |
| CSS | ۳۷۴٬۱۳۴ (بدون فشرده‌سازی) | **۴۴٬۰۲۹** (brotli) |
| JS | ۱۷۰٬۲۸۴ (بدون فشرده‌سازی) | **۳۹٬۹۲۱** (brotli) |
| زمان تقریبی با RTT=۱۵۰ms و ۲Mbps | ۴٬۵۲۶ms | **۲٬۳۷۷ms** (−۴۷٪) |
| زمان تقریبی با RTT=۳۰۰ms و ۱Mbps | ۹٬۰۵۳ms | **۴٬۷۵۴ms** (−۴۷٪) |

**بزرگ‌ترین بخش باقی‌مانده فونت‌ها هستند:** ۵ وزن وزیرمتن (۲۵۵KB) + فونت
آیکون‌ها (۱۳۰KB) = ۳۸۵KB از ۴۸۲KB. این فایل‌ها از قبل فشرده‌اند و gzip/brotli
روی‌شان اثری ندارد. تنها راه کوچک‌کردن‌شان، **فونت متغیر** (`Vazirmatn[wght].woff2`)
است که هر پنج وزن را در یک فایل می‌دهد؛ چون فایلش در این مخزن نیست و باید از
بالادستی گرفته شود، انجام‌نشده باقی مانده.

### اگر روی VPS با Nginx هستید

Nginx را جلوی gunicorn طوری بگذارید که استاتیک را **خودش** سرو کند؛ این از
هر بهینه‌سازی سمت پایتون سریع‌تر است:

```nginx
location /static/ {
    alias /path/to/app/static/;
    gzip_static on;                 # اگر فایل .gz کنارش باشد
    expires 1y;
    add_header Cache-Control "public, max-age=31536000, immutable";
    access_log off;
}
location / { proxy_pass http://127.0.0.1:5000; }
gzip on;
gzip_types text/css application/javascript application/json image/svg+xml;
```

### چند نکتهٔ باقی‌مانده

- فونت `bootstrap-icons.woff2` حدود ۱۲۷KB است و ~۲۰۰۰ گلیف دارد، در حالی که
  برنامه ~۲۲۶ آیکون استفاده می‌کند. زیرمجموعه‌کردن (subset) آن ~۱۱۰KB صرفه‌جویی
  می‌دهد، ولی چون بعضی کلاس‌های آیکون **پویا** ساخته می‌شوند
  (مثل `bi-{{ 'pause' if ... }}`) انجامش ریسک «آیکون خالی» دارد؛ عمداً دست
  نخورده باقی مانده.
- صفحهٔ ورود عمداً layout سبک خودش را دارد (۳ فایل CSS) تا اولین چیزی که
  کاربر می‌بیند سریع بیاید.

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

### سرعت ربات بله روی هاست

سرور بله (`tapi.bale.ai`) بیرون از هاست است، پس هزینهٔ اصلی هر پاسخ یک
رفت‌وبرگشت شبکه است — نه CPU هاست. poller برای همین این‌طور کار می‌کند:

- **اتصال پایدار:** همهٔ فراخوانی‌های API روی یک `requests.Session` با pool
  اتصال می‌روند؛ TLS handshake برای هر پیام تکرار نمی‌شود.
- **پردازش موازی به تفکیک کاربر:** پیام‌ها بین چند ترد کارگر تقسیم می‌شوند
  (پیش‌فرض ۳). ترتیب پیام‌های هر کاربر حفظ می‌شود ولی کاربرهای مختلف
  هم‌زمان سرویس می‌گیرند؛ با ۵۰ پیام تلنبارشده، نفر آخر پشت سر ۴۹ نفر
  قبلی نمی‌ماند.
- **جداسازی خطا:** اگر ارسال پاسخ به یک کاربر شکست بخورد (کاربر ربات را
  block کرده، چت وجود ندارد، محدودیت نرخ ۴۲۹ و…) فقط همان پیام از کار
  می‌افتد؛ بقیهٔ صف متوقف نمی‌شود و پاسخ کسی گم نمی‌رود.

تنظیم تعداد تردهای پردازش با متغیر محیطی `ACADEMY_BALE_WORKERS`:

```bash
# روی VPS با gunicorn
export ACADEMY_BALE_WORKERS=6
gunicorn --config gunicorn.conf.py wsgi:application
```

| مقدار | مناسب برای |
|-------|------------|
| `1` | پردازش کاملاً پشت‌سرهم (کم‌مصرف‌ترین حالت؛ فقط برای عیب‌یابی) |
| `3` | پیش‌فرض — هاست اشتراکی و VPS کوچک |
| `6` تا `8` | VPS با رم کافی و تعداد کاربر بالا |

وضعیت زندهٔ poller (تعداد کارگرها، پیام‌های پاسخ‌داده‌شده، ناموفق‌ها، صف
انتظار و **میانگین زمان پاسخ** به میلی‌ثانیه) در صفحهٔ
`تنظیمات → ربات بله` نمایش داده می‌شود. اگر «میانگین زمان پاسخ» بزرگ است
(بیش از ۱۵۰۰ میلی‌ثانیه)، گلوگاه مسیر شبکهٔ هاست تا `tapi.bale.ai` است؛ اگر
«در صف انتظار» بزرگ می‌ماند، `ACADEMY_BALE_WORKERS` را بالا ببرید.

> پیام گروهی (Broadcast) هم در پس‌زمینه ارسال می‌شود و صفحهٔ وب را معطل
> نمی‌کند؛ پیشرفت آن در «تاریخچهٔ پیام‌های گروهی» دیده می‌شود.

## عیب‌یابی

| علامت | علت محتمل و راه‌حل |
|------|---------------------|
| خطای 500 یا «Internal Server Error» | اول `/healthz` را باز کنید: اگر `{ok:true}` بود برنامه بالا آمده و خطا از یک صفحهٔ خاص است. وگرنه `logs/passenger_error.log` و `logs/academy.log` را بخوانید؛ علت دقیق آن‌جاست. سپس Restart کنید. روی هاست ضعیف، حالت `ACADEMY_LOW_RESOURCE=1` از قبل در `passenger_wsgi.py` روشن است |
| «unable to open database file» | پوشه‌ی `instance/` قابل نوشتن نیست → `chmod 755 instance` و Restart |
| نشست‌ها بعد از Restart می‌پرند | `settings.json` قابل نوشتن نیست و `SECRET_KEY` ذخیره نمی‌شود → `chmod 644 settings.json` و Restart |
| صفحه‌ی سفید / 404 روی همه‌ی مسیرها | Application root یا startup file اشتباه است؛ باید `public_html/host_deploy` و `passenger_wsgi.py` باشد |
| `ModuleNotFoundError` | `pip install -r requirements.txt` کامل اجرا نشده؛ در Terminal همان اپلیکیشن دوباره اجرا و Restart کنید |
| `Failed building wheel for greenlet` | هاست کامپایلر C ندارد. اگر فقط دکمه‌ی **Run Pip Install** دارید، روی `requirements.txt` یا `requirements-nobuild.txt` نصب کنید (هر دو wheel-only هستند و کامپایل نمی‌کنند)؛ اگر **Terminal** دارید `python tools/install_deps.py` را اجرا کنید (خودکار wheel آماده را نصب می‌کند و در نبود آن، بدون greenlet ادامه می‌دهد) |
| تغییر دیتابیس به MySQL اعمال نشد | پس از ذخیره در `/setup/database` حتماً اپلیکیشن را Restart کنید |
| صفحه‌ها روی هاست کند باز می‌شوند | اول `curl -sI -H 'Accept-Encoding: gzip' https://دامنه/static/css/main.css` را بزنید: باید `Content-Encoding: gzip` و `Cache-Control: …immutable` داشته باشد. اگر نداشت، استاتیک مستقیم توسط آپاچی سرو می‌شود و `mod_deflate`/`mod_headers` هاست خاموش است — در cPanel → Optimize Website گزینهٔ Compress All Content را روشن کنید. اگر `static/gen/` ساخته نشده، پوشهٔ `static` قابل نوشتن نیست (`chmod 755 static`) |
| آیکون‌ها خالی (مربع) نمایش داده می‌شوند | فونت آیکون‌ها نرسیده. آدرس دقیقش را از بسته بردارید و خودتان امتحان کنید: `curl -sI https://دامنه/static/gen/$(ls static/gen | grep '\.css$')` را ببینید و سپس `curl -sI https://دامنه/static/css/fonts/bootstrap-icons.woff2` — باید `200` باشد. آدرس‌های نسبی داخل بسته در زمان ساخت بازنویسی می‌شوند؛ اگر خودتان بسته را دستی ساخته‌اید، `static/gen/` را پاک کنید تا برنامه در بوت بعدی درست بسازدش |
| ربات بله کند جواب می‌دهد | صفحهٔ `تنظیمات → ربات بله` را ببینید: اگر «در صف انتظار» بالا است `ACADEMY_BALE_WORKERS` را بیشتر کنید؛ اگر «میانگین زمان پاسخ» بالا است مسیر شبکهٔ هاست تا `tapi.bale.ai` کند است (با `curl -w '%{time_total}' https://tapi.bale.ai` از Terminal هاست اندازه بگیرید). روی هاست اشتراکی یادتان باشد `ACADEMY_DISABLE_BALE=1` پیش‌فرض است و poller اصلاً اجرا نمی‌شود |
| ربات بله جواب نمی‌دهد | در صفحهٔ `تنظیمات → ربات بله` باید «دریافت خودکار فعال» باشد. روی VPS با چند ورکر، فقط یک ورکر poller را نگه می‌دارد (`instance/.bale_poll.lock`)؛ اگر آن ورکر ری‌استارت شد چند ثانیه طول می‌کشد تا ورکر جدید جای آن را بگیرد |
| فراموشی رمز مدیر | در Terminal همان اپلیکیشن (داخل `public_html/host_deploy` با venv فعال): `ACADEMY_DISABLE_SCHEDULER=1 python -c "from app import create_app; from extensions import db; from models.user import User; a=create_app(); a.app_context().push(); u=User.query.filter_by(username='admin').first(); u.set_password('admin123'); db.session.commit(); print('done: admin password reset')"` — سپس Restart کنید و با `admin123` وارد شوید |

## نکات امنیتی

- `settings.json` و `instance/` و `backups/` و `logs/` با `.htaccess` از دسترس وب
  خارج‌اند؛ آن فایل‌ها را پاک نکنید
- رمز پیش‌فرض (`admin123`) را در اولین فرصت عوض کنید
- روی VPS حتماً `SECRET_KEY` ثابت و HTTPS (Nginx + گواهی) بگذارید و
  `ACADEMY_COOKIE_SECURE=1` را فعال کنید
