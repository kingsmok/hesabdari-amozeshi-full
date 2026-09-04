# شورای مهندسی و محصول — گزارش یکپارچه (Council Report)

**پروژه:** Academy Manager Pro — `hesabdari-amozeshi-full` (Flask + SQLAlchemy + Bootstrap/Jinja + PyQt6 desktop shell)
**مبنای بررسی:** کد فعلی مخزن (`b0c2173` + این فاز) — بدون باگ‌یابی، فقط معماری/بهینه‌سازی/تکمیل
**نتیجهٔ آزمون:** ✅ `396 passed, 2 skipped` — همهٔ تغییرات اجرا و تست شده است.

> این گزارش، دیدگاه ۴۰ متخصص را در ۸ دپارتمان در **یک** سند واحد تلفیق می‌کند.
> هر موردی که «پیاده‌سازی شد» علامت ✅ و هر «توصیهٔ نقشهٔ راه» علامت 🗺 دارد.

---

## ۱) خلاصهٔ اجرایی (Tech Lead — رأی نهایی)

نرم‌افزار، محصولی **کامل و سودمند در سطح ۱.۰ حرفه‌ای** است؛ اما از دید معماری،
«زیرساخت حرفه‌ای» (قرارداد API، مشاهده‌پذیری، استقرار استاندارد، تکرارهای کد)
هنوز با کیفیت خود محصول فاصله داشت. شورا ۶ تصمیم پرریسک را در دو فاز قبلی و
این فاز نهایی کرد:

1. **یک لاگر/ثبت رویداد مرکزی** (`utils/activity_log.py`) — پایان ۱۸ ساخت تکراری.
2. **یک قرارداد API واحد** (`utils/api_contract.py`) — کلاینت‌های آینده (موبایل/ربات/AI) فقط یک شکل پاسخ را می‌فهمند.
3. **مشاهده‌پذیری درخواست‌به‌درخواست** (`X-Request-ID` در هدر و لاگ).
4. **حفاظت از سرویس در برابر سیل API** (`utils/rate_limit.py`).
5. **استقرار استاندارد** (Docker + Gunicorn + CI) به‌جای dev server.
6. **پایان N+1 در داشبوردها و منو** (مسیرهای پربازدید).

**جمع‌بندی:** ساختار در پایان این مرحله برای نسخهٔ ۲.۰ (چند-شعبه‌ای/هاست/ربات‌محور) آماده است.

---

## ۲) تغییرات معماری بحرانی (دپارتمان ۱ و ۲)

| تغییر | پیاده‌سازی | چرا (دیدگاه متخصص) |
|-------|-----------|---------------------|
| کانفیگ مرکزی: چک سازگاری + `settings.json` + مسیرها در یک نقطه | ✅ `utils/config_loader.py` → `app.py` از ۴۰+ خط به ۲ فراخوان | Chief Architect: «یک منبع حقیقت برای config؛ اسکریپت‌های بوت (first_run، desktop، host) دیگر کپی نمی‌کنند» |
| ثبت رویداد مرکزی (user/IP خودکار، هرگز خطا) | ✅ `utils/activity_log.py` — ۱۱ ماژول route مهاجرت کردند | Clean Code: «DRY به معنای حذف ۵ نسخهٔ `_log` و ۱۸ ساخت دستی؛ SOLID: مسوولیت لاگ فقط یک کلاس» |
| ثابت‌های مرکزی + اعتبارسنجی (روش پرداخت، دوره، مرجع صندوق) | ✅ `utils/constants.py` + `utils/validators.py` | Design Pattern: «Enum/Registry — تغییر آینده فقط در یک فایل» |
| قرارداد JSON یکنواخت `{ok, data, request_id}` | ✅ `utils/api_contract.py` + `/api/search`، `/api/dark-mode` | API/Integration: «Contract-first؛ هیچ endpoint ای دیگر shape خودش را ندارد» |
| شناسهٔ درخواست (گزارهٔ همبستگی) | ✅ `utils/request_id.py` + هدر در همهٔ پاسخ‌ها + لاگ خطا | Observability: «از «خطا دیدم» تا یافتن traceback در لاگ < ۱۰ ثانیه» |
| محدودسازی نرخ `/api/*` (سطل لغزان در حافظه) | ✅ `utils/rate_limit.py`؛ در TESTING خاموش | SRE: «جلوگیری از قفل SQLite توسط اسکریپت — گارد دومِ login_guard» |
| رفع N+1 داشبورد (کلاس‌های امروز، آخرین ثبت‌نام‌ها) و منو (۱۵ → ۱ کوئری) | ✅ `routes/dashboard.py`، `app.py` | DBA/ORM: «eager loading در پربازدیدترین صفحات؛ منوی هر صفحه دیگر ۱۵ پرس‌وجو نمی‌زند» |
| مدیریت جامع خطا (۴۰۳/۴۰۴/۵۰۰/Exception + کد پیگیری) | ✅ `utils/error_handling.py` + `errors/500.html` | Error Handling: «graceful degradation؛ کاربر هرگز stack نمی‌بیند، پشتیبانی reference code می‌گیرد» |

**🗺 نقشهٔ راه بعدی (تأیید شده ولی خارج از این فاز):** چند-تنسی (multi-tenancy رسمی با `branch_id` در همهٔ جدول‌ها)، مهاجرت واقعی به Flask-Migrate روی MySQL/PG، ایندکس‌های ترکیبی گزارش مالی، حذف `Query.get` legacy (۶۰ مورد).

---

## ۳) UI/UX و روانشناسی (دپارتمان ۳)

| توصیه | وضعیت | منطق |
|-------|-------|------|
| State مرکزی UI: `Ui.api/busy/toast/confirm/csrf` در یک ماژول | ✅ `static/js/ui-core.js` | State Guru: «هر fetch جداگانه = state پراکنده؛ درخواست‌های موازی شمارندهٔ مرکزی دارند» |
| نشانگر سراسری «در حال پردازش…» با تأخیر ۳۰۰ms | ✅ `#globalBusy` در layout | Behavioral: «پرش‌های ۵۰ms حساسیت را بالا می‌برد؛ تأخیر کوتاه = آرامش در کارهای طولانی» |
| بستن خودکار flashها (۶ ثانیه) | ✅ `app.js` | UX: «هشدارهای کهنه توجه کاربر را از کار اصلی می‌دزدد» |
| جلوگیری از دابل‌ارسال فرم | ✅ `initSubmitGuard()` | Behavioral: «کلیک دوبارهٔ عصبی رایج‌ترین منبع دادهٔ تکراری است» |
| دسترس‌پذیری (لیبل‌ها، کیبورد، contrast تست‌شده) | ✅ قبلاً + تست `frontend_pwa` | a11y: «تست خودکار کم‌کنتراست — دقیقاً همان کاری که این فاز یک نقض را گرفت» |
| پیوستگی بصری (glassmorphism/درجه‌بندی) | 🗺 | Senior UI: تم dark/light هست؛ پیشنهاد: توکن‌های CSS رسمی و Card-glass در dashboard |
| Gamification (نوار پیشرفت هنرجو/معلم، streak حضور) | 🗺 | Gamification: در پورتال مدرس/هنرجو — «جلسات پیاپی» انگیزشی است؛ بدون POINTS زائد |
| کاهش cognitive load فرم‌ها (Step-wizard ثبت‌نام) | 🗺 | HCI: ثبت‌نام ۳۰ فیلد در یک صفحه است؛ ۳ مرحله = نرخ تکمیل بالاتر |

---

## ۴) امنیت و قابلیت اطمینان (دپارتمان ۴)

موجود/تقویت‌شده در این فازها:

- ✅ هدرهای امنیتی (`nosniff`, `SAMEORIGIN`, `Referrer-Policy`, `Permissions-Policy`) + `SESSION_COOKIE_SECURE` (env).
- ✅ گارد اتمیک عملیات مالی (CAS) — جلوگیری از پرداخت/مرجوعی دوباره.
- ✅ Rate-limit API + قفل ورود (login_guard)؛ آپلود با whitelist امضا/حجم/نام (uploads.py).
- ✅ لاگ چرخشی + `X-Request-ID` + لاگ همهٔ POST/خطاها با زمان‌سنجی.
- ✅ صفحهٔ ۵۰۰ «بی‌جزئیات» با کد پیگیری؛ `logs/academy.log` منبع پشتیبانی.
- ✅ نگهداری نشست‌ها/لاگ‌ها (توقف رشد بی‌نهایت جداول).
- ✅ تنظیمات اتمیک با `chmod 600`؛ URI دیتابیس با کدکردن اعتبارنامه.

**🗺 نقشهٔ راه:** MFA/OTP برای مدیر کل، احراز دوباره برای حذف/ابیطال مالی، CSP تدریجی (ghost mode فقط برای صفحات عمومی)، ارسال منظم reports (پشتیبان + سلامت) به ربات مدیر.

---

## ۵) آینده‌نگری و DevOps (دپارتمان ۵، ۷، ۸)

### استقرار (انجام شد ✅)
- **Dockerfile** چند-مرحله‌ای سبک (`python:3.11-slim`، کاربر `nobody`، healthcheck، volumes).
- **docker-compose.yml** با `.env` الزامی `SECRET_KEY` و چهار volume داده.
- **gunicorn.conf.py** (۲ ورکر برای SQLite، `max_requests=1000`، لاگ به stdout).
- **`.github/workflows/ci.yml`** — py3.11/3.12 × lint+compile+pytest.
- **README** — راهنمای Docker/Gunicorn/env و جدول متغیرهای محیطی.
- **`.dockerignore`** — تصویر بدون git/tests/backups.

### 🗺 نقشهٔ راه AI/LLM (دپارتمان ۳۷)
1. **دستیار داخلی** («آخرین ماندهٔ هنرجو را بگو») — RAG روی جدول‌ها، بدون ارسال داده به بیرون.
2. **خلاصهٔ جلسه/گزارش هفتگی** به مدیر (Prompt از دادهٔ داخلی).
3. **پیشنهاد تخفیف/ریسک بدهی** (`high_risk_debtors` موجود است — فقط LLM narrative).
4. **ربات بله/تلگرام** از قبل هست؛ توسعهٔ دستورات طبیعی → ابزار n8n/webhook برای اعلان‌های مالی.

### 🗺 DevOps بیشتر
- nginx/Caddy نمونه برای TLS؛ cron پشتیبان با `academy-backup` script.
- `locust`/`k6` سناریوی «صد منشی همزمان» برای یافتن قفل SQLite واقعی.
- SEO: اپ پشت لاگین است → فقط `meta theme-color`/PWA (انجام شده) و `robots.txt` گزینهٔ ناچیز است؛ تمرکز روی سرعت استاتیک.

---

## ۶) کدهای نهایی — قطعات کلیدی تغییرات این فاز

### `utils/api_contract.py` — قرارداد یکپارچهٔ پاسخ
```python
def ok(data=None, status=200, **extra):
    """پاسخ موفق با قرارداد واحد: {ok: True, data: ..., request_id}"""
    payload = {'ok': True, 'data': data}
    payload.update(extra)                      # فیلدهای قدیمی/خاص مسیر (سازگاری)
    rid = current_request_id()
    if rid:
        payload['request_id'] = rid
    return jsonify(payload), status

def error(message, *, code='BAD_REQUEST', status=400, **extra):
    """پاسخ خطا: {ok: False, error: {code, message}, request_id}"""
    ...
```

### `app.py` — مشاهده‌پذیری + Rate-Limit (چکیده)
```python
@app.before_request
def _request_started():
    g._request_started = time.monotonic()
    start_request_id()                          # شناسهٔ درخواست (X-Request-ID)
    if request.path.startswith('/api/') and not app.config.get('TESTING'):
        if not rate_limit_hit():                # سطل لغزان: 120/min per IP+path
            return jsonify({'ok': False, 'error': {'code': 'RATE_LIMITED', ...}}), 429
        request._rate_remaining = rate_limit_remaining()

@app.after_request
def _security_and_access_log(response):
    ...headers امنیتی...
    response.headers['X-Request-ID'] = current_request_id()
    if response.status_code >= 500 or request.method != 'GET':
        app.logger.info('[%s] %s %s -> %s (%dms)', rid, method, path, status, ms)
    return response
```

### `utils/error_handling.py` — حالتی که خطا رخ می‌دهد
```python
@app.errorhandler(500)
def internal_error_handler(error):
    app.logger.error('Unhandled exception [%s] on %s: %s', _request_id(),
                     _request_path(), error, exc_info=error)
    if app.debug:
        raise error                             # توسعه: stack کامل
    return render_template('errors/500.html', reference_code=_reference_code()), 500
```

### `gunicorn.conf.py` — نکات SQLite
```python
workers = int(os.environ.get('GUNICORN_WORKERS', 2))   # SQLite ⇒ کم
worker_class = 'gthread'
max_requests = 1000                                     # جلوگیری از نشت تدریجی
os.environ['ACADEMY_DISABLE_SCHEDULER'] = '1'           # پشتیبان = CRON هاست
```

---

## پیوست — فایل‌های این فاز

```
+ utils/api_contract.py      قرارداد JSON یکنواخت
+ utils/request_id.py        شناسهٔ درخواست (همبستگی لاگ/پاسخ)
+ utils/rate_limit.py        محدودسازی نرخ API (سطل لغزان)
+ Dockerfile                 تصویر production
+ docker-compose.yml         اجرای چندسرویسه با volumes
+ .dockerignore              تصویر سبک
+ gunicorn.conf.py           WSGI سرور برای production
+ requirements-prod.txt      وابستگی‌های فقط-تولید (gunicorn)
+ .github/workflows/ci.yml   CI خودکار (3.11/3.12)
+ COUNCIL_REPORT.md          همین گزارش

M app.py                     قبل/بعد درخواست: request-id + rate-limit + لاگ
M routes/final.py            /api/search و /api/dark-mode → قرارداد واحد
M utils/error_handling.py    لاگ خطا با شناسهٔ درخواست
M static/js/app.js           سازگاری کلاینت با قرارداد جدید
M README.md                  مستندات استقرار + متغیرهای محیطی
```
