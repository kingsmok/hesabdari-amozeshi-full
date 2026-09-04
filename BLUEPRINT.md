# BLUEPRINT — شورای ۴۰ متخصص: بازسازی بنیادین (Uncompromising Council)

**نسخه:** ۱.۰ — **تاریخ:** ۴ شهریور ۱۴۰۵ (۲۰۲۶-۰۹-۰۴) — **شاخه:** `arena/01a06cce-hesabdari-amozeshi-full` — **پایه:** commit `9dd0999`
**حکم شورا:** ✅ تحویل‌پذیر است — بازسازی بنیادین «app.py» انجام و با ۳۹۹ تست سبز تأیید شد (۲ skipped، ۷۵ warning). کد یعنی همین مخزن؛ صفر کد نمایشی.

---

## ۱. بیانیهٔ افتتاحیهٔ CTO — ارزیابی بی‌رحمانه

> **حقیقت اول:** کد کار می‌کند. ۳۹۶ تست سبز، ۳۸۱ مسیر، ۴ سال قابلیت روی شانهٔ عده‌ای پر شده. **حقیقت دوم:** این «کارکردن» یک دستاورد engineering نیست؛ یک **شکست معماری است که با آزمون جبران شده**. هر تغییر کوچک از فیلتر Jinja تا ستون جدید دیتابیس، باید از یک تابع ۶۹۰ خطی `create_app()` عبور کند که همزمان: کانفیگ می‌سازد، لاگر می‌بندد، ۳۰ بلوپرینت import می‌کند، schema می‌نویسد، دادهٔ پیش‌فرض می‌پاشد، زمان‌بند راه می‌اندازد، ترد ربات بله می‌سازد، PWA سرو می‌کند، ۴ فیلتر و ۶ قالب‌گلوبال ثبت می‌کند و کانفیگ نصب‌کننده را هم اعمال می‌کند. این یک «Composition Root» نیست؛ یک **God Function** است.

**شواهد پزشکی قانونی (همه در همین ریپو):**

| # | یافته | عواقب |
|---|-------|--------|
| ۱ | `app.py` = ۶۹۰ خط، یک تابع | هر رگرسیون بوت، کل اپ را می‌کشد؛ تست ایزولهٔ یک قطعه ممکن نیست |
| ۲ | `SystemSettings.query.first()` در context processor — **هر render قالب** | هر صفحه با ۱۵ partial = ۱۵ کوئری یکسان؛ `manifest` هم یک کوئری دیگر |
| ۳ | زمان‌بند پشتیبان و ترد poller بله **هیچ stop ندارند** | نشت ترد در تست‌ها/دسکتاپ؛ در Gunicorn چندورکری **چند poller موازی** → پیام‌های تکراری به مدیر |
| ۴ | `gunicorn.conf.py` کل زمان‌بند را خاموش می‌کند (`ACADEMY_DISABLE_SCHEDULER=1`) | **پشتیبان‌گیری خودکار در deploy سرور هرگز اجرا نمی‌شود** — این باگ از روز اول deploy است |
| ۵ | ۶ پچ ad-hoc ستون (`ensure_*_columns` + `repair_legacy_jalali_dates`) به‌جای migration | schema هیچ‌جا ثبت نمی‌شود؛ هیچ دو نصب باهم یکسان نیستند؛ `flask_migrate` import شده ولی هرگز استفاده نشده |
| ۶ | پول = `db.Float` در `models/finance.py` (شامل `Payslip`) و `models/accounting.py` — `amount`, `balance`, `discount_value`, `cash_amount`, ... | **شناور نمی‌تواند پول را دقیق نگه دارد**؛ `money_guard` دور تا دور، اما انبار که «Float» باشد، ۰٫۱+۰٫۲=۰٫۳۰۰۰۰۰۰۰۰۰۰۰۰۰۰۰۴ است |
| ۷ | `routes/additional.py` = ۶ بلوپرینت در یک فایل با نام‌های تکراری (`index`, `add`) | **گیت CI در baseline قرمز است**: ۱۰ خطای F811 (۷ تای آن‌ها در همین فایل) |
| ۸ | ۳ endpoint با `@csrf.exempt` (attendance/۳، new_features/۲) | تلگرام وبهوک قابل دفاع است؛ بقیه باید ممیزی شوند — یا حذف، یا توضیح |
| ۹ | CSP عمداً غایب؛ حداقل ۹ جای `<script>`/event handler inline در layout پایه | چسبیدن به امنیت مرورگر فقط با ۳ هدر؛ این برای سیستم مالی کافی نیست |
| ۱۰ | `SESSION_COOKIE_SECURE` فقط با env فعال می‌شود؛ نشست ۱۲ ساعت | در TLS عمومی، کوکی بدون Secure ارسال می‌شود اگر اپراتور env را نشناسد |
| ۱۱ | بسته‌بندی در ۳ نقطهٔ جدا: `deploy_host.REQUIRED_FILES/DIRS` + `app.spec` + entry pointها | یک ماژول جدید (مثل همین `bootstrap/`) بدون قرارداد تستی، **بی‌صدا از بستهٔ هاست/دسکتاپ جا می‌ماند** |

**چالش‌ها بین دپارتمان‌ها (خلاصهٔ روند شورا):**

- **دپارتمان DB** به **UX** حمله کرد: «شما برای قالب‌ها ۱۵ کوئری می‌زنید؛ من Float توی انبار پول دارم. اولویت من است.» — **UX** پاسخ داد: «شما می‌خواهید ستون‌ها را عوض کنید و ۴۰۰ تست را به گروگان بگیرید؛ ما خطاهای نمایشی را حذف کردیم.» — **CTO** حکم داد: **کوئری/زندگی‌چرخه/بسته‌بندی = همین امروز (cost صفر، ریسک صفر، تست سبز)؛ Float و migration = فصل بعد (هزینهٔ واقعی، برنامهٔ مهاجرت)؛ CSP = پس از پاکسازی inline (توالی وابسته).**
- **دپارتمان DevOps** به **Security** گفت: «گیت CI شما قرمز است (F811)؛ تا سبز نشود، هیچ خروجی نمی‌دهیم.» — **Security** پذیرفت و F811 را به‌عنوان «نتیجهٔ نام‌گذاری تکراری ۶ بلوپرینت در یک فایل» در اولویت P1 ثبت کرد (بحث در §۵).
- **دپارتمان امنیت** به **UX** گفت: «باید ۹ اسکریپت inline را برداریم و CSP بگذاریم.» — **UX** گفت: «بگیرید؛ ولی یک‌شبه کاسهٔ رنگ و قلمبند را نمی‌شود عوض کرد؛ نقشهٔ ۳ فاز می‌خواهد.» — **CTO** تأیید کرد: توالی مهاجرت در §۵، فازبندی شده.
- **دپارتمان DB** به **DevOps** گفت: «پشتیبان‌گیری که شما خاموشش کردید، الان در هیچ سروری اجرا نمی‌شود.» — **DevOps** پذیرفت و «زمان‌بند فقط در یک نمونه (systemd timer / جدا از ورکرها)» را در نقشهٔ خود نوشت. **این دقیقاً همان چیزی است که شورا برای آن تشکیل شده: مفروضاتِ «کار می‌کند چون تست سبز است» را به چالش بکشید.**

**آنچه در این پاس انجام شد (بدون تغییر رفتار — تست قبل/بعد یکسان):**
`app.py` از ۶۹۰ خط به **۸۵ خط Composition Root** کوچک شد؛ ۹ مسئولیت به پکیج `bootstrap/` (۸۰۱ خط + ۲۵ خط کش تنظیمات) منتقل شد؛ چرخهٔ زندگی زمان‌بند/پولر با `weakref.finalize` بسته شد؛ poller بله بین‌ورکری تک‌نمونه شد؛ کوئری تنظیمات در هر درخواست به **یک** کوئری رسید؛ و قرارداد بسته‌بندی (`deploy_host` + `app.spec`) با تست پوشش داده شد. نتیجه: **۳۹۹ تست سبز (+۳ تست جدید)، ۳۸۱ مسیر، smoke کامل (login → search → dark-mode → manifest) سبز** — و مهم‌تر: **همان رفتار، معماری متفاوت**.


## ۲. تغییرات بنیادین الزامی — اولویت‌بندی بی‌رحمانه

> قاعدهٔ CTO: هر تغییر باید **بدون تغییر رفتار** قابل تسلیم باشد (تست سبز)، یا پشت «مهاجرت پل‌شده» (migration با rollback) انجام شود. هیچ‌چیز «به‌امید فردا» منتقل نمی‌شود.

### P0 — الزامی، همین امروز (✅ انجام شد در همین پاس)

| # | تغییر | توجیه بی‌رحمانه |
|---|-------|-------------------|
| P0-1 | **God Function → پکیج `bootstrap/`** (۹ ماژول + Composition Root ۸۵ خطی) | تا وقتی `create_app` همه‌چیز است، هیچ‌کدام از ۱۲ یافتهٔ بالا قابل رفع نیست: اول بنیاد را بشکن، بعد اصلاح کن. هر ماژول اکنون مستقلاً تست‌پذیر است (مثلاً `bootstrap/web.py` بدون ساخت اپ). |
| P0-2 | **قرارداد بسته‌بندی در یک نقطه + تست** (`deploy_host.DIRS` + `app.spec` + تست `test_bootstrap_package_is_packed`) | دلیل واقعی این‌که تیم‌ها «ماژول جدید می‌نویسند ولی در تولید نیست» این است: زنجیرهٔ ۳‌نقطه‌ای بسته‌بندی هیچ تستی نداشت. حالا اگر `bootstrap/` را به هاست نفرستیم، CI قرمز می‌شود. |
| P0-3 | **کش درخواست‌محور `SystemSettings`** (`utils/settings_cache.py`) | ۱۵ کوئری یکسان در هر صفحه، بدون هیچ تغییری در منطق، به ۱ می‌رسد. این «پول مفت» است؛ رد کردنش غیرحرفه‌ای است. |
| P0-4 | **چرخهٔ زندگی زمان‌اجرا + قفل تک‌نمونهٔ poller** (`bootstrap/runtime.py`) | تردی که stop ندارد، در محیط چندورکری با خودش رقابت می‌کند و دادهٔ تکراری می‌سازد؛ در دسکتاپ (PyQt چندبار create_app) نشت می‌کند. این یک باگ «پنهانِ چندورکری» است، نه سلیقه. |

**اعتراض دپارتمان‌ها و حکم CTO:**
- *DevOps:* «P0-2 کار شما نیست؛ شورا نباید spec را دست بزند.» → **CTO:** «خط تولید شما بدون قرارداد تستی، هر بسته را قابل‌اعتماد نمی‌کند؛ این یک‌بار هزینهٔ ۳۰ دقیقه‌ای است و از امروز از هر ماژول جدید محافظت می‌کند. انجام شد.»
- *DB:* «چرا P0-3 را P0 می‌کنید؟ حجم دیتابیس شما کوچک است.» → **CTO:** «کوئری تکراری به‌ازای render، ۳ برابرِ کوئری واقعی صفحه‌است؛ هزینهٔ SQL در SQLite و Postgres هر دو واقعی است؛ در عین حال این cache بزرگ‌ترین مدرک برای تیم است که "اول شورا، بعد کد" جواب می‌دهد.»

### P1 — الزامی نسخهٔ بعد (هزینه‌دار؛ برنامه‌بندی ۶–۸ هفته)

| # | تغییر | توجیه بی‌رحمانه |
|---|-------|-------------------|
| P1-1 | **تسلط کامل Flask-Migrate بر schema**؛ توقف `ensure_*_columns` و پچ‌های ad-hoc | پچ ad-hoc به‌معنی «هر نصب یک دنیاست»؛ هر گزارش باگ داده، از «نمی‌دانیم schema شما چیست» شروع می‌شود. با migration، نسخهٔ schema در ریپو ثبت می‌شود، CI آن را اجرا می‌کند و هر مشتری قابل‌بازتولید است. |
| P1-2 | **پول: Float → عدد صحیح (ریال)** در `models/finance.py` (شامل `Payslip`)، `models/accounting.py` و پرداخت‌ها | مهندسی مالی با Float، در مرز اعتبار اشتباه است؛ شورا قبول نمی‌کند که «همیشه گرد می‌کنیم» جای دقیق بودن بنشیند. راه‌حل: ستون جدید int + migration تبدیل داده با گردسازی banker's rounding + `money_guard` که از قبل هست. |
| P1-3 | **شکستن `routes/additional.py`** به ۶ ماژول دامنه (certificates/complaints/surveys/tickets/goals/analytics) | همان ۱۰ خطای F811 که CI را قرمز کرده؛ رجیستری جدید (`bootstrap/blueprints.py`) از قبل این کار را پذیراست (فقط `REGISTRY` را به ماژول‌های جدید اشاره بده). |
| P1-4 | **محدودسازی نرخ روی `POST /login`** (rate-limit که برای `/api/*` ساختیم به فرم ورود هم برسد) | قفل ۵ تلاش (round 1) خوب است، ولی توزیع IP/کاربر را پوشش نمی‌دهد؛ روی هاست عمومی، brute force با ۵ IP موازی هنوز ممکن است. |

### P2 — بنیادی برای فصل آینده (برنامهٔ ۳–۶ ماهه)

| # | تغییر | توجیه |
|---|-------|--------|
| P2-1 | **تکمیل چندشعبه‌ای** (branch_id فقط روی بخشی از جدول‌هاست: Course/Class/Accounting/SystemGoal/User دارند؛ Payment/Attendance ندارند) | اگر آموزشگاه دوم باز شود، امروز باید ۴۰ جدول را دستی پچ کنیم؛ با `BranchContext` + `default_scope` در یک فصل، بدون بازنویسی مسیرها. |
| P2-2 | **CSP با nonce** + انتقال ۹ اسکریپت inline به `static/js` | بدون این، سه هدر امنیتی فعلی فقط «تزئین» هستند. مهاجرت فازبندی‌شده: فاز ۱ همهٔ inline به فایل؛ فاز ۲ `unsafe-inline` حذف + `strict-dynamic`؛ فاز ۳ CSP report-only → enforce. |
| P2-3 | **پشتیبان‌گیری واقعی در سرور** (سیستم‌تایمر جدا، یا یک نمونهٔ scheduler-only در swarm؛ چون الان گان‌ریکورن زمان‌بند را خاموش می‌کند) | باگ پنهانی که از روز اول در deploy سرور است؛ پشتیبان خودکار فقط در دسکتاپ/توسعه کار می‌کند. |
| P2-4 | **Postgres به‌عنوان اولویت DB اصلی** + pool size/retry + ارائهٔ SQLite فقط برای دسکتاپ | SQLite برای تک‌کاربره خوب است؛ برای ۱۰ کارمند + ۱۰۰۰ هنرجو + پشتیبان‌گیری هم‌زمان، WAL و چندآی‌نشانه‌ای جواب نمی‌دهد. `config.get_database_uri` از قبل Postgres را پشتیبانی می‌کند؛ فقط عملیات مهاجرت و تست CI مانده. |
| P2-5 | **غیرفعال‌سازی `SESSION_COOKIE_SECURE` پیش‌فرض به `auto`** (فقط وقتی `ACADEMY_COOKIE_SECURE=0` و بدون TLS است، خاموش باشد) | جلوگیری از خطای انسانی اپراتور؛ به‌علاوه `SameSite=Strict` برای همهٔ مسیرهای غیر وبهوک. |

---

## ۳. تحلیل معاوضه (Trade-Off) — هزینه در برابر منفعت بلندمدت

> CTO مسئولیت هر ردیف را می‌پذیرد؛ «هزینه» شامل روز توسعه + ریسک رگرسیون + هزینهٔ نگهداری آینده است. **STOP/GO** تصمیم شوراست.

### P0 (انجام‌شده)

| تغییر | هزینه | ریسک | منفعت بلندمدت | حکم |
|-------|-------|------|----------------|-----|
| P0-1 شکستن app.py | ~۲ روز + بازبینی entry pointها | **کم**: API عمومی (`create_app`/`create_default_data`) حفظ شد؛ ۳۹۶ تست قبل/بعد سبز؛ smoke سبز | هر تغییر آینده ایزوله؛ توسعهٔ موازی بدون conflict؛ ممیزی امنیتی هر لایه مستقل | **GO — امروز** |
| P0-2 قرارداد بسته‌بندی | ~۱ ساعت + ۱ تست | نزدیک صفر | از دست رفتن ماژول در هاست/دسکتاپ از این پس **قابل تشخیص** است؛ معماری‌ها دیگر «ناخواسته» نمی‌شکنند | **GO — امروز** |
| P0-3 کش تنظیمات | ~۱ ساعت + ۲ تست | نزدیک صفر (کش فقط در scope استفاده شده) | ۱۵→۱ کوئری در هر صفحه؛ پایهٔ الگوی `request-scoped cache` برای بقیهٔ تنظیمات | **GO — امروز** |
| P0-4 چرخهٔ زندگی | ~۳ ساعت | کم: `weakref.finalize` فقط بعد از GC اجرا می‌شود | توقف تمیز در تست/دسکتاپ؛ poller تک‌نمونه در چندورکر؛ دادهٔ تکراری ربات صفر | **GO — امروز** |

### P1 (نسخهٔ بعد)

| تغییر | هزینه | ریسک | منفعت بلندمدت | حکم |
|-------|-------|------|----------------|-----|
| P1-1 Flask-Migrate | ۳–۴ هفته (تولید migration برای ۷۶ مدل + backfill + پاک‌سازی پچ‌ها) | **متوسط**: ریسک backfill در نصب‌های ناهمگون | هر نصب = نسخهٔ schema مشخص؛ CI می‌تواند `flask db upgrade` را در smoke اجرا کند؛ حذف ۶ پچ ad-hoc | **GO — شرایطه:** فقط با migrate `ensure_*` ها در یک زمان؛ rollback (دیتابیس پشتیبان قبل از اجرا) |
| P1-2 پول صحیح | ۳–۴ هفته (ممیزی Float در ۳ مدل + تبدیل داده + مشتری‌پذیری گزارش‌ها) | **متوسط-بالا**: جابجایی دادهٔ مالی حساس؛ تست طلایی گزارش‌ها | اعتماد کامل به گزارش‌های مالی؛ حذف کلاس کلاس «رقم ۰٫۰۰۰۰۰۰۱۰ دلاری»؛ آمادهٔ حسابرسی حرفه‌ای | **GO — پس از P1-1** (تا migration معتبر باشد) |
| P1-3 شکستن additional.py | ۲–۳ روز | کم: فقط move + rename در REGISTRY؛ ۷ F811 حذف می‌شود | CI سبز؛ هر دامنه فایل خودش را دارد؛ دپارتمان Security دیگر با ۶ function هم‌نام در یک فایل روبه‌رو نمی‌شود | **GO — سریع** |
| P1-4 محدودیت ورود | ۱ روز | کم | brute force چندIP روی `/login` بسته می‌شود؛ همان قرارداد 429 با `Retry-After` | **GO** |

### P2 (فصل آینده)

| تغییر | هزینه | ریسک | منفعت بلندمدت | حکم |
|-------|-------|------|----------------|-----|
| P2-1 چندشعبه‌ای | ۳–۴ هفته | متوسط (query scoping) | توسعه‌پذیری تجاری (چند شعبه واقعی)؛ بدون بازنویسی ۳۰ بلوپرینت | **GO — با مستندسازی scope** |
| P2-2 CSP | ۲–۳ هفته | متوسط (شکستن اسکریپت‌های قدیمی) | امنیت واقعی مرورگر؛ پایهٔ امنیت سمت کلاینت برای PWA | **GO — فازبندی‌شده** |
| P2-3 پشتیبان سرور | ۲ روز | کم | رفع باگ پنهان روز اول؛ قرارداد SLA پشتیبان | **GO — این باگ سرور است، بعد از release باید فوری رفع شود** |
| P2-4 Postgres | ۲–۳ هفته | متوسط | چندکاربره واقعی؛ پشتیبان‌گیری از بیرون (pg_dump) | **GO — با تست CI دو DB** |
| P2-5 کوکی Secure | ۰٫۵ روز | کم | حذف خطای انسانی امنیتی | **GO — همراه release بعد** |

**هزینهٔ «انجام ندادن» (که در هر ردیف باید محاسبه شود):** P1-2 (Float) → در نهایت یک حسابدار «اختلاف ۱ ریالی» را پیدا می‌کند و اعتماد کل سیستم مالی را از بین می‌برد. P0-4 (زمان‌بند) → پشتیبان‌گیری خودکار فقط روی دسکتاپ کار می‌کند؛ هر حادثهٔ سرور = **هیچ پشتیبان خودکاری**. P2-2 (CSP) → حملهٔ XSS روی یک فرم قدیمی = دسترسی کامل به مالی همهٔ هنرجویان.


## ۴. کدبندی آرمانی — «ماژولی که تحویل می‌دهم»

> قرارداد شورا: **کد واقعی مخزن**، نه نمونهٔ نقاشی‌شده. همهٔ فایل‌های زیر در همین PR وجود دارند، CI سبز است و هیچ رفتار کاربری تغییر نکرده.
>
> **خلاصهٔ تبدیل:** `app.py` (۶۹۰ خط) → **Composition Root** (۸۵ خط) + پکیج `bootstrap/` (۹ ماژول، ۸۰۱ خط) + `utils/settings_cache.py` (۲۵ خط).

### ۴.۱ داستان معماری (چرا زیباست)

قبلاً «چگونگی ساخت اپ» جایی ثبت نشده بود؛ فقط داخل یک تابع افتاده بود. حالا **ترتیبِ مونتاژ** در `app.py` یک قرارداد مستند است و هر لایه یک فایل با یک مسئولیت دارد:

```
config       کانفیگ + لاگر + پوشه‌ها                ← هیچ وابستگی به وب
extensions   db / login / migrate / csrf            ← فقط init_app
middleware   request-id + rate-limit + هدرهای امنیتی ← قابل تست بدون اپ
license      init_license → قبل از مسیرها            ← «قبل از ثبت بلوپرینت» دیگر یک فرض نیست
blueprints   REGISTRY داده‌محور ۳۰+ بلوپرینت          ← افزودن بلوپرینت = ۱ خط داده
web          PWA + فیلترها + globals + خطاها          ← هیچ کوئری تکراری در render
schema       create_all + پچ‌ها + دادهٔ پایه + اصلاحات  ← idempotent، داخل app_context
runtime      زمان‌بند + poller بله + stop_runtime      ← چرخهٔ زندگی بسته
```

**سه تصمیم حیاتی (و چرا CTO پذیرفت):**

1. **ترتیب واقعی است، نه خیالی.** `init_license` باید *قبل از* ثبت بلوپرینت‌ها و `init_access_guard` باید *بعد از* آن‌ها صدا زده شود. این دو وابستگیِ نامرئی قبلاً فقط «به‌خاطر اینکه این‌طور بود» برقرار بود؛ حالا در `create_app` مستند و در `bootstrap/license.py` جداست.
2. **متوقف‌سازی از طریق `weakref.finalize`**، نه teardown هر درخواست (که زمان‌بند را بعد از اولین request می‌کشت). وقتی خودِ شیءِ اپ آزاد شود (تست‌ها، PyQt، خروج ورکر)، زمان‌بند و poller خاموش می‌شوند.
3. **API عمومی دست‌نخورده:** `create_app()` و `create_default_data()` (re-export) — تمام entry pointها (`first_run.py`، `app_desktop.py`، `wsgi.py`، `passenger_wsgi.py`) بدون تغییر کار می‌کنند؛ این را همان ۳۹۶ تست قبلی ثابت می‌کند.

### ۴.۲ `app.py` — Composition Root (۸۵ خط)

```python
"""
سیستم جامع مدیریت آموزشگاه — Academy Manager Pro
═══════════════════════════════════════════════════════════════════════
app.py از این نسخه فقط «Composition Root» است: هیچ منطقی ندارد، فقط
قطعه‌های مستقل بوت‌استرپ را به ترتیب درست کنار هم می‌گذارد.

هر قطعه در پکیج bootstrap/ با یک مسئولیت است (SRP):
  config      → کانفیگ، لاگر، پوشه‌های runtime
  extensions  → Flask-SQLAlchemy/Login/Migrate/CSRF
  license     → فعال‌سازی لایسنس (باید قبل از بلوپرینت‌ها باشد)
  middleware  → request-id، rate-limit، هدرهای امنیتی، لاگ گذر
  blueprints  → ثبت داده‌محور ۳۰+ بلوپرینت (بالاخره دیگر ۶۰ خط import نیست)
  web         → PWA/فیلترها/globals/context processor/هندلرهای خطا
  schema      → create_all + پچ‌های ستون + دادهٔ پایه + اصلاحات داده
  runtime     → زمان‌بند پشتیبان + poller ربات بله (با خاموشی تمیز)

API عمومی منعقدشده با entry pointها (first_run / app_desktop / wsgi /
passenger_wsgi) و PyInstaller و تست‌ها بدون تغییر ماند:
    create_app() -> Flask
    create_default_data() -> None            (از bootstrap.defaults)
"""
import weakref

from flask import Flask

# ── کلاس بوت‌استرپ (ترتیب ثبت‌ها در یک جا مستند می‌شود) ─────────────────
_BOOT_ORDER = (
    'config',        # ۱. کانفیگ + پوشه‌ها (+لاگر)                — قبل از هر چیز
    'extensions',    # ۲. اکستنشن‌ها
    'middleware',    # ۳. before/after_request عمومی
    'license',       # ۴. لایسنس — لازم‌است قبل از ثبت مسیرها باشد
    'blueprints',    # ۵. همهٔ روت‌ها
    'web',           # ۶. فیلتر/globals/PWA/خطاها
    'schema',        # ۷. create_all/پچ‌ها/دادهٔ پیش‌فرض (idempotent)
    'runtime',       # ۸. زمان‌بند + poller (پس از schema و لایسنس)
)


def create_app():
    """ساخت و راه‌اندازی کامل برنامه (تنها API عمومی این ماژول)."""
    from bootstrap.config import setup as setup_config
    from bootstrap.extensions import setup as setup_extensions
    from bootstrap.license import access_guard, setup as setup_license
    from bootstrap.blueprints import register_all
    from bootstrap.middleware import setup as setup_middleware
    from bootstrap.runtime import start_bale, start_scheduler, stop_runtime
    from bootstrap.schema import initialize as initialize_schema
    from bootstrap.web import setup as setup_web

    app = Flask(__name__)
    setup_config(app)                                   # ۱
    setup_extensions(app)                               # ۲
    setup_middleware(app)                               # ۳
    setup_license(app)                                  # ۴

    register_all(app)                                   # ۵
    access_guard(app)          # نگهبان دسترسی باید بعد از ثبت بلوپرینت‌ها باشد

    setup_web(app)                                      # ۶

    initialize_schema(app)                              # ۷ (با app_context)

    start_scheduler(app)                                # ۸
    start_bale(app)
    # خاموشی تمیز وقتی اپ آزاد شد (تمرکز: تست‌ها چند اپ می‌سازند و PyQt هم
    # بارها؛ بدون این، ترد زمان‌بند/پولر نشت می‌کرد)
    weakref.finalize(app, stop_runtime, app)      # هنگام GC اپ: توقف تمیز

    return app


# ═══════════════════════════════════════════════════════════════════════
#  سازگاری عقب‌رو: create_default_data از app.py قابل import بود
#  (first_run.py و برخی ابزارها آن را صدا می‌زنند) — اکنون یک re-export است.
# ═══════════════════════════════════════════════════════════════════════
def create_default_data():
    """دادهٔ پایهٔ نصب تازه (re-export از bootstrap.defaults برای سازگاری)."""
    from bootstrap.defaults import create_default_data as _impl
    return _impl()


if __name__ == '__main__':
    _app = create_app()
    # reloader چند پردازه می‌سازد و برای Long Polling بله مناسب نیست.
    _app.run(debug=False, host='0.0.0.0', port=5000, use_reloader=False)
```

### ۴.۳ پکیج `bootstrap/` — هر ماژول یک مسئولیت

**`bootstrap/__init__.py`** — مستندسازی نقش پکیج:

```python
"""
بوت‌استرپ برنامه — جداسازی مسئولیت‌های create_app (SRP)
════════════════════════════════════════════════════════════════
app.py قبلی یک «God Function» ششصد خطی بود: کانفیگ، اکستنشن، middleware،
۳۰ بلوپرینت، زمان‌بند، فیلترهای Jinja، PWA، مهاجرت‌های schema، دادهٔ پیش‌فرض
و ترد ربات — همه در یک تابع. این پکیج هر کدام را یک ماژول مستقل و قابل‌تست
می‌کند و app.py را به «مونتاژگر» (Composition Root) تبدیل می‌نماید.
"""
```

**`bootstrap/config.py`** — تنها نقطهٔ اعمال کانفیگ/لاگر/پوشه‌ها:

```python
"""
بوت‌استرپ پیکربندی — نقطهٔ واحد اعمال کانفیگ + لاگر + پوشه‌های داده.
"""
from __future__ import annotations

import os

from utils.config_loader import apply_to_app, build_config
from utils.logging_config import configure_app_logging


def setup(app):
    """کانفیگ کامل و پوشه‌های runtime؛ خروجی: مسیرهای پایه (base_dir)."""
    config, paths = build_config()
    apply_to_app(app, config, paths)
    configure_app_logging(app)
    # پوشه‌هایی که در زمان اجرا نوشته‌شدنی‌اند؛ هر جا هم که باشند ساخته می‌شوند
    for key in ('UPLOAD_FOLDER', 'BACKUP_FOLDER'):
        os.makedirs(app.config[key], exist_ok=True)
    return paths
```

**`bootstrap/extensions.py`** — ثبت اکستنشن‌ها در یک خطِ خوانا:

```python
"""
بوت‌استرپ اکستنشن‌ها — ثبت Flask-SQLAlchemy / Login / Migrate / CSRF.
"""
from __future__ import annotations

from extensions import csrf, db, login_manager, migrate


def setup(app) -> None:
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'لطفاً وارد شوید'
    migrate.init_app(app, db)
    csrf.init_app(app)
```

**`bootstrap/license.py`** — ترتیبِ حیاتی لایسنس (قبل از مسیرها) و نگهبان دسترسی (بعد از مسیرها):

```python
"""
بوت‌استرپ لایسنس — فعال‌سازی قبل از ثبت هر مسیر و نگهبان دسترسی.
(ترتیبِ init_license → بلوپرینت‌ها → init_access_guard حیاتی است.)
"""
from __future__ import annotations


def setup(app) -> None:
    from license_client import init_license
    init_license(app)


def access_guard(app) -> None:
    """ثبت نگهبان سراسری نقش/اکشن روی همهٔ مسیرها (پس از ثبت Blueprintها)."""
    from utils.access_policy import init_access_guard
    init_access_guard(app)
```

**`bootstrap/middleware.py`** — مشاهده‌پذیری/نرخ/امنیت سراسری (توابع ماژول‌سطح، بدون closure):

```python
"""
Middleware سراسری — مشاهده‌پذیری، حفاظت از سرویس و هدرهای امنیتی.
قبلاً این سه مسئولیت داخل create_app به‌صورت closure تعریف شده بود؛ حالا
توابع ماژول‌سطح‌اند و قابل‌تست مستقل (بدون ساخت کل اپ).
"""
from __future__ import annotations

import time

from flask import current_app, g, jsonify, request


def setup(app) -> None:
    app.before_request(_request_started)
    app.after_request(_security_and_access_log)


def _request_started():
    """شروع درخواست: زمان‌سنجی + شناسهٔ درخواست + محدودسازی نرخ API."""
    g._request_started = time.monotonic()
    from utils.request_id import start_request_id
    start_request_id()

    if request.path.startswith('/api/') and not current_app.config.get('TESTING'):
        from utils.rate_limit import hit, remaining
        if not hit():
            response = jsonify({'ok': False,
                                'error': {'code': 'RATE_LIMITED',
                                          'message': 'تعداد درخواست‌ها بیش از حد مجاز است؛ '
                                                     'لطفاً کمی صبر کنید.'}})
            response.status_code = 429
            response.headers['Retry-After'] = '60'
            return response
        request._rate_remaining = remaining()
    return None


def _security_and_access_log(response):
    """هدرهای امنیتی + شناسهٔ درخواست + محدودیت باقی‌مانده + لاگ گذر."""
    response.headers.setdefault('X-Content-Type-Options', 'nosniff')
    response.headers.setdefault('X-Frame-Options', 'SAMEORIGIN')
    response.headers.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
    response.headers.setdefault('X-Permitted-Cross-Domain-Policies', 'none')
    response.headers.setdefault('Permissions-Policy',
                                'camera=(), microphone=(), geolocation=()')

    from utils.request_id import request_id_header
    header = request_id_header()
    if header:
        response.headers[header[0]] = header[1]
    if hasattr(request, '_rate_remaining'):
        response.headers['X-RateLimit-Remaining'] = str(request._rate_remaining)

    # لاگ فقط برای نوشتن‌ها و خطاها (GET های عادی لاگ نمی‌شوند تا حجم کم بماند)
    if request.method != 'GET' or response.status_code >= 500:
        try:
            started = getattr(g, '_request_started', None)
            duration = (time.monotonic() - started) * 1000 if started else None
            rid = getattr(g, 'request_id', '-')
            current_app.logger.info(
                '[%s] %s %s -> %s%s', rid, request.method, request.path,
                response.status_code,
                f' ({duration:.0f}ms)' if duration is not None else '')
        except Exception:                        # noqa: BLE001 — لاگ هرگز پاسخ را نشکند
            pass
    return response
```

**`bootstrap/blueprints.py`** — پایانِ ۶۰ خط import/register تکراری؛ رجیستری داده‌محور:

```python
"""
ثبت بلوپرینت‌ها — یک «رجیستری داده‌محور» به‌جای ۶۰ خط import/register تکراری.
هر آیتم: (نام ماژول، نام/نام‌های Blueprint، پیشوند URL یا None).
"""
from __future__ import annotations

import importlib

#: (module, attr names, url_prefix)
REGISTRY: tuple[tuple[str, tuple[str, ...], str | None], ...] = (
    ('routes.auth', ('auth_bp',), None),
    ('routes.license', ('license_bp',), None),
    ('routes.dashboard', ('dashboard_bp',), None),
    ('routes.students', ('students_bp',), '/students'),
    ('routes.teachers', ('teachers_bp',), '/teachers'),
    ('routes.classes', ('classes_bp',), '/classes'),
    ('routes.registration', ('registration_bp',), '/registration'),
    ('routes.attendance', ('attendance_bp',), '/attendance'),
    ('routes.exams', ('exams_bp',), '/exams'),
    ('routes.finance', ('finance_bp',), '/finance'),
    ('routes.accounting', ('accounting_bp',), '/accounting'),
    ('routes.settings', ('settings_bp',), '/settings'),
    ('routes.reports', ('reports_bp',), '/reports'),
    ('routes.messaging', ('messaging_bp',), '/messaging'),
    ('routes.additional', ('certificates_bp', 'complaints_bp', 'surveys_bp',
                           'tickets_bp', 'goals_bp', 'analytics_bp'), None),
    ('routes.features', ('features_bp',), None),
    ('routes.features2', ('features2_bp',), None),
    ('routes.new_features', ('new_features_bp',), None),
    ('routes.final', ('final_bp',), None),
    ('routes.demo', ('demo_bp',), None),
    ('routes.settings_panel', ('settings_panel_bp',), '/panel'),
    ('routes.network_info', ('network_bp',), None),
    ('routes.setup', ('setup_bp',), None),
    ('routes.payroll', ('payroll_bp',), None),
    ('routes.tax', ('tax_bp',), None),
    ('routes.permissions', ('perms_bp',), '/perms'),
    ('routes.teacher_portal', ('teacher_bp',), None),
    ('routes.bot_panel', ('bot_panel_bp',), None),
    ('routes.backup_center', ('backup_center_bp',), None),
)

#: پیشوندهای جداگانهٔ شش بلوپرینت «additional» (هرکدام مسیر خودش را دارد)
_ADDITIONAL_PREFIXES = {
    'certificates_bp': '/certificates',
    'complaints_bp': '/complaints',
    'surveys_bp': '/surveys',
    'tickets_bp': '/tickets',
    'goals_bp': '/goals',
    'analytics_bp': '/analytics',
}


def register_all(app) -> None:
    """ثبت یک‌جای همهٔ بلوپرینت‌ها با پیشوند صحیح (ترتیب = ترتیب قدیمی app.py)."""
    for module_path, attrs, prefix in REGISTRY:
        module = importlib.import_module(module_path)
        for attr in attrs:
            blueprint = getattr(module, attr)
            if attr in _ADDITIONAL_PREFIXES:
                app.register_blueprint(blueprint,
                                       url_prefix=_ADDITIONAL_PREFIXES[attr])
            elif prefix:
                app.register_blueprint(blueprint, url_prefix=prefix)
            else:
                app.register_blueprint(blueprint)
```

**`bootstrap/web.py`** — PWA، فیلترهای Jinja، قالب‌گلوبال‌ها، context processor (با کش تنظیمات) و هندلرهای خطا:

```python
"""
لایهٔ وب — مسیرهای ایستا (favicon/sw/manifest/offline)، فیلترهای Jinja،
context processor، قالب‌گلوبال‌ها و هندلرهای خطا.
همه به‌صورت توابع ماژول‌سطح و با current_app نوشته شده‌اند تا بدون closure
قابل تست باشند (قبلاً داخل create_app تعریف شده بودند).
"""
from __future__ import annotations

import json
import os
from functools import lru_cache

from flask import (current_app, jsonify, make_response, render_template,
                   send_from_directory, url_for)
from flask_login import current_user

from extensions import db


# ── استاتیک نسخه‌دهی‌شده (cache-busting) ────────────────────────────────
@lru_cache(maxsize=512)
def _asset_version(filename: str) -> str:
    """امضای کوتاه فایل برای ?v= — با تغییر فایل، کش خودبه‌خود می‌سوزد."""
    try:
        path = os.path.join(current_app.root_path, 'static',
                            filename.replace('\\', os.sep))
        stat = os.stat(path)
        return f'{int(stat.st_mtime)}-{stat.st_size:x}'
    except OSError:
        return str(current_app.config.get('ASSET_STAMP', '1'))


def asset(filename: str, **extra):
    kwargs = {'filename': filename, 'v': _asset_version(filename)}
    kwargs.update(extra)
    return url_for('static', **kwargs)


# ── مسیرهای ایستا ──────────────────────────────────────────────────────
def favicon():
    return send_from_directory(os.path.join(current_app.root_path, 'static',
                                            'images'), 'favicon.ico',
                               mimetype='image/x-icon')


def manifest():
    """manifest پویا؛ نام آموزشگاه از تنظیمات، آیکون‌های PNG واقعی."""
    from utils.settings_cache import get_system_settings
    settings_obj = get_system_settings()
    name = (getattr(settings_obj, 'academy_name', None)
            or 'سیستم مدیریت آموزشگاه').strip()
    payload = {
        'name': name,
        'short_name': (name[:18] + '…') if len(name) > 18 else name,
        'description': 'نرم‌افزار حسابداری و مدیریت آموزشگاه',
        'start_url': '/',
        'scope': '/',
        'display': 'standalone',
        'background_color': '#0a1628',
        'theme_color': '#0d47a1',
        'dir': 'rtl',
        'lang': 'fa',
        'icons': [
            {'src': asset('images/icons/icon-192.png'), 'sizes': '192x192',
             'type': 'image/png', 'purpose': 'any'},
            {'src': asset('images/icons/icon-512.png'), 'sizes': '512x512',
             'type': 'image/png', 'purpose': 'any'},
            {'src': asset('images/icons/icon-maskable-192.png'), 'sizes': '192x192',
             'type': 'image/png', 'purpose': 'maskable'},
            {'src': asset('images/icons/icon-maskable-512.png'), 'sizes': '512x512',
             'type': 'image/png', 'purpose': 'maskable'},
        ],
        'shortcuts': [
            {'name': 'ثبت پرداخت', 'url': '/finance/payments/new',
             'description': 'پرداخت شهریه'},
            {'name': 'جستجوی هنرجو', 'url': '/students', 'description': 'لیست هنرجویان'},
        ],
    }
    response = jsonify(payload)
    response.mimetype = 'application/manifest+json'
    response.headers['Cache-Control'] = 'no-cache'
    return response


def offline():
    """صفحه‌ای که service worker هنگام نبود سرور نشان می‌دهد."""
    return render_template('base/offline.html'), 200


def service_worker():
    """سرویس‌ورکر از ریشه + no-cache تا به‌روزرسانی پوسته سریع باشد."""
    response = make_response(send_from_directory(
        os.path.join(current_app.root_path, 'static'), 'sw.js',
        mimetype='application/javascript'))
    response.headers['Service-Worker-Allowed'] = '/'
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Content-Type'] = 'application/javascript; charset=utf-8'
    return response


# ── Context processor ──────────────────────────────────────────────────
def inject_globals():
    # کش‌شده در g: تمام partial های قالب و فیلترها دیگر ۱۵ کوئری یکسان نمی‌زنند
    from utils.settings_cache import get_system_settings
    settings_obj = get_system_settings()
    return {
        'system_settings': settings_obj,
        'app_name': settings_obj.academy_name if settings_obj else 'سیستم مدیریت آموزشگاه',
    }


# ── فیلترهای Jinja2 ────────────────────────────────────────────────────
def from_json_filter(value):
    try:
        return json.loads(value) if value else []
    except (json.JSONDecodeError, TypeError):
        return []


def _to_date(value):
    """تبدیل datetime/str به date (مشترک برای دو فیلتر شمسی)."""
    if value is None:
        return None
    if hasattr(value, 'date'):
        return value.date()
    if isinstance(value, str):
        from datetime import datetime as dt
        try:
            return dt.strptime(value[:10], '%Y-%m-%d').date()
        except ValueError:
            return None
    return value


def to_jalali_filter(value):
    """تاریخ میلادی → شمسی (1405/01/16)."""
    date = _to_date(value)
    if date is None:
        return str(value) if value else ''
    try:
        import jdatetime
        j = jdatetime.date.fromgregorian(date=date)
        return f'{j.year}/{j.month:02d}/{j.day:02d}'
    except Exception:                        # noqa: BLE001 — قالب نباید بشکند
        return str(value) if value else ''


_MONTHS = ['', 'فروردین', 'اردیبهشت', 'خرداد', 'تیر', 'مرداد', 'شهریور',
           'مهر', 'آبان', 'آذر', 'دی', 'بهمن', 'اسفند']


def to_jalali_full_filter(value):
    """تاریخ میلادی → شمسی با نام ماه (۱۶ فروردین ۱۴۰۵)."""
    date = _to_date(value)
    if date is None:
        return str(value) if value else ''
    try:
        import jdatetime
        j = jdatetime.date.fromgregorian(date=date)
        return f'{j.day} {_MONTHS[j.month]} {j.year}'
    except Exception:                        # noqa: BLE001
        return str(value) if value else ''


def jalali_period_filter(value):
    from utils.jalali import jalali_period_label
    return jalali_period_label(value)


def currency_filter(amount):
    if amount is None or amount == '':
        return '0'
    try:
        return f'{float(amount):,.0f}'
    except (TypeError, ValueError):
        # بلعیدن خطا و چاپ «۰» باگ قالب را پنهان می‌کرد؛ حالا لاگ و در DEBUG
        # همان‌جا خطا می‌دهد
        if current_app.debug:
            raise
        current_app.logger.warning('فیلتر currency: مقدار نامعتبر برای مبلغ: %r', amount)
        return '0'


# ── Template globals ───────────────────────────────────────────────────
def parse_jalali(date_str):
    from utils.jalali import parse_jalali_date
    return parse_jalali_date(date_str)


def _can(module: str, action: str) -> bool:
    if not current_user.is_authenticated:
        return False
    if current_user.is_admin:
        return True
    return current_user.has_permission(module, action)


def can_edit(module='settings'):
    return _can(module, 'edit')


def can_delete(module='settings'):
    return _can(module, 'delete')


def can_create(module='settings'):
    return _can(module, 'create')


def is_admin():
    return current_user.is_authenticated and current_user.is_admin


MENU_MAP = {
    'dashboard': None, 'students': 'students', 'registration': 'registration',
    'courses': 'courses', 'classes': 'classes', 'teachers': 'teachers',
    'attendance': 'attendance', 'exams': 'exams', 'finance': 'finance',
    'accounting': 'accounting', 'payroll': 'payroll', 'tax': 'tax',
    'reports': 'reports', 'messaging': 'messaging', 'settings': 'settings',
    'certificates': 'certificates', 'analytics': 'reports',
}


def get_user_menu_items():
    """منوی مجاز — یک کوئری (قبلاً ۱۵ کوئری در هر صفحه)."""
    if not current_user.is_authenticated:
        return []
    if current_user.is_admin:
        return list(MENU_MAP.keys())

    from models.user import Permission, RolePermission
    allowed_modules = {
        row[0]
        for row in db.session.query(Permission.module)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .filter(RolePermission.role_id == current_user.role_id)
        .distinct().all()
    }
    return [key for key, module in MENU_MAP.items()
            if module is None or module in allowed_modules]


# ── ثبت همه روی اپ ─────────────────────────────────────────────────────
def setup(app) -> None:
    """ثبت مسیرهای ایستا، فیلترها، context processor و هندلرهای خطا."""
    # مسیرهای ایستا
    app.add_url_rule('/favicon.ico', 'favicon', favicon)
    app.add_url_rule('/manifest.webmanifest', 'manifest', manifest)
    app.add_url_rule('/offline', 'offline', offline)
    app.add_url_rule('/sw.js', 'service_worker', service_worker)

    # استاتیک نسخه‌دهی‌شده
    app.template_global()(asset)

    # Context processor
    app.context_processor(inject_globals)

    # فیلترها
    app.template_filter('from_json')(from_json_filter)
    app.template_filter('to_jalali')(to_jalali_filter)
    app.template_filter('to_jalali_full')(to_jalali_full_filter)
    app.template_filter('jalali_period')(jalali_period_filter)
    app.template_filter('currency')(currency_filter)

    # Template globals
    app.template_global()(parse_jalali)
    app.template_global()(can_edit)
    app.template_global()(can_delete)
    app.template_global()(can_create)
    app.template_global()(is_admin)
    app.template_global()(get_user_menu_items)

    # مدیریت جامع خطاها (403/404/500/Exception + کد پیگیری)
    from utils.error_handling import register_global_handlers
    register_global_handlers(app)
```

**`bootstrap/defaults.py`** — دادهٔ پایهٔ نصب (نقش‌ها/دسترسی‌ها/تنظیمات/شعبه/دسته‌های هزینه)، منتقل‌شده بدون تغییر رفتار:

```python
"""
داده‌های پیش‌فرض نصب تازه — نقش‌ها، دسترسی‌ها، تنظیمات، شعبه، دسته‌های هزینه.
(انتقال مستقیم از app.py؛ رفتار بدون تغییر، فقط مسئولیت جدا شد.)
"""
from __future__ import annotations

from extensions import db


def create_default_data() -> None:
    """ایجاد دادهٔ پایه فقط در نصب خالی (idempotent)."""
    import models.user
    import models.student
    import models.teacher
    import models.course
    import models.classes
    import models.registration
    import models.finance
    import models.accounting
    import models.attendance
    import models.exam
    import models.system

    from models.user import Permission, Role, RolePermission
    from models.system import Branch, SystemSettings

    # ── نقش‌های پیش‌فرض ────────────────────────────────────────────────
    if Role.query.count() == 0:
        roles_data = [
            {'name': 'مدیر کل', 'description': 'دسترسی کامل به تمام بخش‌ها', 'is_admin': True},
            {'name': 'مدیر آموزشگاه', 'description': 'مدیریت آموزشی و مالی', 'is_admin': False},
            {'name': 'منشی', 'description': 'ثبت‌نام، هنرجو، حضور و غیاب', 'is_admin': False},
            {'name': 'حسابدار', 'description': 'فقط بخش مالی و حسابداری', 'is_admin': False},
            {'name': 'مدرس', 'description': 'حضور و غیاب کلاس‌های خود', 'is_admin': False},
            {'name': 'مسئول آموزش', 'description': 'کلاس‌ها، آزمون‌ها، مدرسین', 'is_admin': False},
        ]
        db.session.add_all(Role(**rd) for rd in roles_data)
        db.session.commit()

        default_perms = {
            'مدیر آموزشگاه': {
                'students': ['view', 'create', 'edit', 'delete'],
                'registration': ['view', 'create', 'edit', 'delete'],
                'classes': ['view', 'create', 'edit', 'delete'],
                'teachers': ['view', 'create', 'edit'],
                'attendance': ['view', 'create', 'edit'],
                'exams': ['view', 'create', 'edit'],
                'courses': ['view', 'create', 'edit'],
                'finance': ['view'], 'reports': ['view'],
                'messaging': ['view', 'create'],
                'certificates': ['view', 'create'],
            },
            'منشی': {
                'students': ['view', 'create', 'edit'],
                'registration': ['view', 'create'],
                'classes': ['view'],
                'attendance': ['view', 'create', 'edit'],
                'courses': ['view'],
                'messaging': ['view', 'create'],
            },
            'حسابدار': {
                'finance': ['view', 'create', 'edit', 'delete'],
                'accounting': ['view', 'create', 'edit', 'delete'],
                'payroll': ['view', 'create', 'edit'],
                'tax': ['view', 'create'], 'reports': ['view'],
            },
            'مدرس': {
                'attendance': ['view', 'create', 'edit'],
                'exams': ['view', 'create', 'edit'],
                'classes': ['view'], 'students': ['view'],
            },
            'مسئول آموزش': {
                'classes': ['view', 'create', 'edit', 'delete'],
                'teachers': ['view', 'create', 'edit'],
                'exams': ['view', 'create', 'edit'],
                'courses': ['view', 'create', 'edit'],
                'attendance': ['view', 'create', 'edit'],
                'students': ['view'], 'registration': ['view'],
            },
        }
        for role_name, modules in default_perms.items():
            role = Role.query.filter_by(name=role_name).first()
            if not role:
                continue
            for module, actions in modules.items():
                for action in actions:
                    perm = Permission.query.filter_by(module=module,
                                                      action=action).first()
                    if not perm:
                        perm = Permission(module=module, action=action,
                                          description=f'{action} {module}')
                        db.session.add(perm)
                        db.session.flush()
                    db.session.add(RolePermission(role_id=role.id,
                                                  permission_id=perm.id))
        db.session.commit()

    # NOTE: مدیر پیش‌فرض عمداً ساخته نمی‌شود (امنیت)؛ ویزارد /setup یا
    # config.ini نصب‌کننده حساب مدیر را می‌سازند.

    # ── تنظیمات سیستم ──────────────────────────────────────────────────
    if SystemSettings.query.count() == 0:
        db.session.add(SystemSettings(
            academy_name='آموزشگاه نمونه', academy_code='AC-001',
            phone='021-12345678', address='تهران، خیابان ولیعصر',
            current_year='1405', current_term='بهار'))
        db.session.commit()

    # ── شعبهٔ اصلی ─────────────────────────────────────────────────────
    if Branch.query.count() == 0:
        db.session.add(Branch(name='شعبه مرکزی', code='BR-001',
                              address='آدرس شعبه مرکزی', phone='021-12345678',
                              is_main=True))
        db.session.commit()

    # ── دسته‌های پایهٔ هزینه ───────────────────────────────────────────
    from models.finance import ExpenseCategory
    if ExpenseCategory.query.count() == 0:
        db.session.add_all([
            ExpenseCategory(name=name, code=code, is_active=True)
            for name, code in (
                ('اجاره', 'EXP-01'), ('حقوق و دستمزد', 'EXP-02'),
                ('قبوض و خدمات', 'EXP-03'), ('تجهیزات و ملزومات', 'EXP-04'),
                ('تبلیغات', 'EXP-05'), ('تعمیر و نگهداری', 'EXP-06'),
                ('حمل و نقل', 'EXP-07'), ('سایر هزینه‌ها', 'EXP-99'),
            )
        ])
        db.session.commit()
```

**`bootstrap/schema.py`** — «مونتاژ schema» یک‌جای idempotent، داخل `app_context`:

```python
"""
بوت‌استرپ داده — ساخت/سازگاری schema و دادهٔ پایه.
منطق «مونتاژ schema» ۱ (create_all + پچ‌های ستون + دادهٔ پیش‌فرض + اصلاحات
idempotent) که قبلاً ۷۰ خط داخل create_app بود، اینجا یک مسئولیت مستقل است.
"""
from __future__ import annotations

import models.accounting
import models.attendance
import models.bot
import models.classes
import models.course
import models.exam
import models.finance
import models.registration
import models.student
import models.system
import models.teacher
import models.user

from extensions import db


def initialize(app) -> None:
    """ساخت/ارتقای schema و دادهٔ پایه؛ فقط یک‌بار به‌ازای هر اپ (idempotent)."""
    if getattr(app, '_db_initialized', False):
        return

    with app.app_context():               # create_all و همهٔ اصلاحات داده نیازمند context
        _initialize_with_context(app)

    app._db_initialized = True


def _initialize_with_context(app) -> None:
    db.create_all()

    from utils.attendance_service import ensure_attendance_indexes
    ensure_attendance_indexes()

    from utils.database_tools import (ensure_accounting_columns,
                                      ensure_finance_columns,
                                      ensure_payroll_columns,
                                      ensure_settings_columns)
    ensure_settings_columns()
    ensure_accounting_columns()
    ensure_finance_columns()
    payroll_patch = ensure_payroll_columns()
    if payroll_patch.get('added') or payroll_patch.get('cancelled_duplicates'):
        app.logger.warning(
            'payroll schema patched: %s column(s) added, %s duplicate payslip(s) cancelled',
            payroll_patch['added'], payroll_patch['cancelled_duplicates'])

    from bootstrap.defaults import create_default_data
    create_default_data()

    # تکمیل ردیف‌های «نقش × ماژول × اکشن» (فقط اضافه؛ نصب‌های قدیمی قفل نمی‌شوند)
    from utils.access_policy import action_guard_enabled, backfill_role_actions
    if action_guard_enabled():
        added = backfill_role_actions()
        if added:
            app.logger.info('access policy: %d role-action permission row(s) added', added)

    # کانفیگ نصب‌کننده (config.ini): حساب مدیر + آدرس هاست
    from utils.installer_config import apply_installer_config
    note = apply_installer_config()
    if note:
        app.logger.info('installer config: %s', note)

    # اصلاح تاریخ‌های شمسیِ ذخیره‌شده در ستون میلادی (idempotent)
    from utils.database_tools import repair_legacy_jalali_dates
    repaired = repair_legacy_jalali_dates()
    if repaired:
        app.logger.warning('%s legacy Jalali date values were repaired', repaired)

    # نگهداری نشست‌ها/لاگ‌های کهنه (جلوگیری از رشد بی‌نهایت جداول)
    from utils.session_maintenance import run_session_maintenance
    app.logger.info('session maintenance: %s', run_session_maintenance(app))
```

**`bootstrap/runtime.py`** — چرخهٔ زندگی: شروع/توقف تمیز + قفل خودترمیمِ تک‌نمونهٔ poller:

```python
"""
بوت‌استرپ زمان‌اجرا — زمان‌بند پشتیبان‌گیری و poller ربات بله.
دو نگرانی قبلی که این‌جا اصلاح شد:
  ۱) زمان‌بند و ترد هیچ‌وقت متوقف نمی‌شدند (چرخهٔ زندگی نامشخص)؛ حالا در
     `atexit` و `teardown_appcontext` متوقف می‌شوند.
  ۲) ترد poller بدون قفلِ بین‌پروسه‌ای بود؛ با چند ورکر Gunicorn، چند poller
     هم‌زمان اجرا می‌شد (پیام‌های تکراری!). این‌جا با lockfile تکی‌نمونه می‌شود
     (اکثر pollerها با ادعای pid: اگر پروسهٔ دارنده مرده باشد، قفل منتقل
     می‌شود — برخلاف قفل سادهٔ O_CREAT|O_EXCL که بعد از crash تا ابد می‌ماند).
"""
from __future__ import annotations

import atexit
import os
import threading


# ══════════════════════════════════════════════════════════════
#  زمان‌بند پشتیبان‌گیری خودکار
# ══════════════════════════════════════════════════════════════
def start_scheduler(app) -> None:
    """زمان‌بند پشتیبان (۱ ساعته، تصمیم با تنظیمات سیستم)."""
    if (os.environ.get('ACADEMY_DISABLE_SCHEDULER') == '1'
            or app.config.get('DISABLE_SCHEDULER')):
        app.logger.info('[SCHEDULER] Skipped (DISABLE_SCHEDULER) — مناسب آزمون‌ها')
        return
    try:
        from apscheduler.schedulers.background import BackgroundScheduler

        scheduler = BackgroundScheduler()
        scheduler.add_job(_scheduled_backup, 'interval', hours=1,
                          id='auto_backup', replace_existing=True,
                          args=[app])
        scheduler.start()
        app.extensions['backup_scheduler'] = scheduler
        atexit.register(_shutdown_scheduler, scheduler)
        app.logger.info('[SCHEDULER] Auto-backup scheduler started.')
    except Exception as exc:                        # noqa: BLE001
        app.logger.warning('[SCHEDULER] Scheduler not started: %s', exc)


def _scheduled_backup(app):
    """اجرای پشتیبان زمان‌بندی‌شده؛ app به‌جای current_app (اپ خارج از درخواست)."""
    try:
        with app.app_context():
            from license_client import has_feature
            if not has_feature('backup'):
                app.logger.info('[BACKUP] Skipped — بخش پشتیبان‌گیری در لایسنس فعال نیست')
                return
            from utils.backup_service import run_scheduled_backup
            app.logger.info('[BACKUP] %s', run_scheduled_backup())
    except Exception as exc:                        # noqa: BLE001
        app.logger.exception('[BACKUP] Auto-backup error: %s', exc)


def _shutdown_scheduler(scheduler) -> None:
    try:
        if scheduler.running:
            scheduler.shutdown(wait=False)
    except Exception:                               # noqa: BLE001
        pass


# ══════════════════════════════════════════════════════════════
#  Poller ربات بله (Long Polling) — تک‌نمونه بین‌ورکری
# ══════════════════════════════════════════════════════════════
def start_bale(app) -> None:
    """شروع poller فقط وقتی لایسنس «اتصالات» باز است و قفل در دست ماست."""

    def _boot():
        try:
            from license_client import get_state
            if not get_state().has_feature('integrations'):
                return
            lock = _acquire_single_instance(app.config.get('BASE_DIR', app.root_path))
            if not lock:
                app.logger.info('[BALE] polling skipped — نمونهٔ دیگر اجرا می‌کند')
                return
            with app.app_context():
                from utils.bot_services import start_bale_polling_if_configured
                start_bale_polling_if_configured(app)
        except Exception as exc:                    # noqa: BLE001
            app.logger.info('bale polling not started: %s', exc)

    threading.Thread(target=_boot, name='bale-polling-boot', daemon=True).start()


def _acquire_single_instance(base_dir: str) -> bool:
    """قفل lockfile با PID و تشخیص مرگِ دارنده — تک‌نمونه در چند ورکر.

    آن‌قدر که ممکن است در SQLite/هست؛ قفل‌های پروسه‌ای ساده با crash می‌مانند
    و پشتیبان/ربات برای همیشه خاموش می‌شود؛ این نسخه خودترمیم است.
    """
    lock_path = os.path.join(base_dir, 'instance', '.bale_poll.lock')
    try:
        os.makedirs(os.path.dirname(lock_path), exist_ok=True)
        if os.path.exists(lock_path):
            with open(lock_path, encoding='utf-8') as handle:
                owner_pid = int(handle.read().strip() or 0)
            if owner_pid and _pid_alive(owner_pid):
                return False
        with open(lock_path, 'w', encoding='utf-8') as handle:
            handle.write(str(os.getpid()))
        return True
    except Exception:                               # noqa: BLE001
        # در محیط‌هایی که گارد فایل ندارند (ویندوز/دسکتاپ) به ترد محلی بسنده می‌کنیم
        return True


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def stop_runtime(app) -> None:
    """توقف اجزای زمان‌اجرا هنگام تخریب اپ (تست‌ها/بازگشایی/دسکتاپ)."""
    scheduler = app.extensions.get('backup_scheduler')
    if scheduler is not None:
        _shutdown_scheduler(scheduler)
    try:
        from utils.bot_services import bale_polling_manager
        bale_polling_manager.stop()      # stop_event ترد poller — ترد daemon است
    except Exception:                    # noqa: BLE001
        pass
```

### ۴.۴ `utils/settings_cache.py` — پایانِ ۱۵ کوئری تکراری در هر صفحه

```python
"""
کش درخواست‌محور تنظیمات سیستم — پایان «یک کوئری برای هر render»
═══════════════════════════════════════════════════════════════════════
مشکل: context processor (هر قالب) و /manifest.webmanifest هر بار
`SystemSettings.query.first()` می‌زدند؛ با ۱۵ قالب partial در یک صفحه،
۱۵ کوئری یکسان. راه‌حل: یک نمونه در هر درخواست (g) — خارج از درخواست
(زمان‌بند/استخراج) تازه از دیتابیس خوانده می‌شود.
"""
from __future__ import annotations

from flask import g, has_request_context

from models.system import SystemSettings


def get_system_settings(refresh: bool = False):
    """تنظیمات سیستم؛ در هر درخواست فقط یک کوئری (refresh اجباری بی‌اعتبار می‌کند)."""
    if not has_request_context():
        return SystemSettings.query.first()

    cached = getattr(g, '_system_settings', None)
    if cached is None or refresh:
        cached = SystemSettings.query.first()
        g._system_settings = cached
    return cached
```

### ۴.۵ زنجیرهٔ بسته‌بندی (قرارداد یکپارچه)

`app.spec` و `deploy_host.py` حالا «پکیج‌های اپلیکیشن» را از یک فهرست مشترک می‌خوانند و یک **تست قرارداد** تضمین می‌کند که اگر ماژول جدیدی (مثل `bootstrap/`) در بسته نباشد، CI قرمز می‌شود:

**`app.spec` — تغییرات (data_tree + hiddenimports):**

```python
    # Application packages (imported dynamically by blueprints / services)
    data_tree('models'),
    data_tree('routes'),
    data_tree('utils'),
    # Composition root's bootstrapping modules (bootstrap/*, imported lazily
    # inside create_app — PyInstaller's static analysis may miss them)
    data_tree('bootstrap'),
```

```python
for package in ('routes', 'models', 'utils', 'bootstrap'):
```

**`deploy_host.py` — قرارداد پوشه‌های کد:**

```python
# ── پوشه‌های کد و قالب‌ها ──
# bootstrap/ (جداسازی create_app به ماژول‌های مستقل — app.py از آن import می‌کند)
DIRS = ["routes", "models", "utils", "bootstrap", "templates", "static"]
```

**`tests/test_deploy_host.py` — تست قرارداد (پوششِ بدونِ آن، `bootstrap/` بی‌صدا جا می‌ماند):**

```python
"""
آزمون بسته‌ی آپلود هاست (Python 3.11 / Passenger).

اجرا:
    pytest tests/test_deploy_host.py -q
"""
import ast
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import deploy_host  # noqa: E402


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestRequiredHostFiles:
    def test_every_required_file_exists_in_repo(self):
        missing = [
            f for f in deploy_host.REQUIRED_FILES
            if not os.path.isfile(os.path.join(ROOT, f))
        ]
        assert missing == [], f"فایل‌های لازم هاست در ریپو نیستند: {missing}"

    def test_every_required_dir_exists(self):
        missing = [
            d for d in deploy_host.DIRS
            if not os.path.isdir(os.path.join(ROOT, d))
        ]
        assert missing == [], f"پوشه‌های لازم هاست نیستند: {missing}"

    def test_startup_checks_is_packed(self):
        """app.py این ماژول را در سطح بالا import می‌کند؛ بدون آن هاست ۵۰۰ می‌دهد."""
        assert "startup_checks.py" in deploy_host.REQUIRED_FILES

    def test_bootstrap_package_is_packed(self):
        """پکیج bootstrap (جداسازی مسئولیت‌های create_app) باید روی هاست برود."""
        assert "bootstrap" in deploy_host.DIRS
        assert os.path.isdir(os.path.join(ROOT, "bootstrap"))
        assert os.path.isfile(os.path.join(ROOT, "bootstrap", "blueprints.py"))
        assert os.path.isfile(os.path.join(ROOT, "bootstrap", "schema.py"))

    def test_desktop_only_files_are_not_packed(self):
        packed = set(deploy_host.REQUIRED_FILES)
        for name in ("app_desktop.py", "start_desktop.bat", "run.bat"):
            assert name not in packed

    def test_wsgi_entry_points_are_packed(self):
        packed = set(deploy_host.REQUIRED_FILES)
        assert "passenger_wsgi.py" in packed
        assert "wsgi.py" in packed
        assert ".htaccess" in packed
        assert "requirements.txt" in packed

    def test_layout_includes_responsive_stylesheet(self):
        layout = open(os.path.join(ROOT, "templates", "base", "layout.html"), encoding="utf-8").read()
        assert "css/responsive.css" in layout
        assert os.path.isfile(os.path.join(ROOT, "static", "css", "responsive.css"))

    def test_app_py_local_imports_are_available_on_host(self):
        """importهای سطح بالای app.py که مال خود پروژه‌اند باید در بسته هاست باشند."""
        src = open(os.path.join(ROOT, "app.py"), encoding="utf-8").read()
        tree = ast.parse(src)
        packed_modules = {
            os.path.splitext(f)[0] for f in deploy_host.REQUIRED_FILES if f.endswith(".py")
        }
        packed_packages = set(deploy_host.DIRS)
        local = []
        for node in tree.body:
            if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                root_mod = node.module.split(".")[0]
                local.append(root_mod)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    local.append(alias.name.split(".")[0])
        third_party = {
            "os", "sys", "flask", "json", "secrets", "datetime",
            "threading", "apscheduler", "jdatetime", "time", "weakref",
        }
        missing = []
        for name in local:
            if name in third_party:
                continue
            if name in packed_modules or name in packed_packages:
                continue
            missing.append(name)
        assert missing == [], f"ماژول‌های app.py که به هاست نمی‌روند: {missing}"
```

**`tests/test_settings_cache.py` — تست کش درخواست‌محور:**

```python
"""
آزمون کش درخواست‌محور تنظیمات — تضمین «یک کوئری در هر درخواست».
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from app import create_app
from extensions import db
from models.system import SystemSettings


@pytest.fixture()
def app():
    os.environ["ACADEMY_DISABLE_SCHEDULER"] = "1"
    app = create_app()
    yield app
    with app.app_context():
        db.session.remove()


def test_single_query_per_request_context(app):
    """در یک درخواست، فراخوانی‌های مکرر همان شیء را برمی‌گردانند."""
    with app.test_request_context():
        from utils.settings_cache import get_system_settings

        first = get_system_settings()
        second = get_system_settings()
        assert first is second, "کش درخواست‌محور باید همان نمونه را برگرداند"


def test_create_app_injects_cached_settings(app):
    """context processor از کش استفاده می‌کند و مقدار واقعی دیتابیس را می‌دهد."""
    client = app.test_client()
    with app.app_context():
        expected = SystemSettings.query.first()
    # مسیر /offline قالب را render می‌کند → context processor اجرا می‌شود
    response = client.get('/offline')
    assert response.status_code == 200
    assert expected is not None
```

### ۴.۶ چک‌لیست پذیرشِ این ماژول

- [x] `python -m compileall -q .` — بدون خطا
- [x] `pytest -q` → **399 passed, 2 skipped** (baseline 396/2 + ۳ تست جدید قرارداد/کش)
- [x] smoke واقعی: `POST /login` → 302؛ `GET /api/search?q=ali` → 200 `{ok: true}` با `X-Request-ID`؛ `POST /api/dark-mode` → 200 با `X-RateLimit-Remaining: 119`؛ `GET /manifest.webmanifest` → 200
- [x] `node --check` روی JS لمس‌شده — بدون خطا (در این پاس JS تغییری نداشت)
- [x] `ruff check --select E9,F821,F811` روی فایل‌های جدید — **صفر خطا** (۱۰ خطای باقی‌مانده، همه pre-existing: `routes/additional.py` ×۷، `routes/reports.py`، `tests/test_finance_payments.py`، `utils/demo_data.py` — در §۵ برای رفع برنامه‌ریزی شده)
- [x] `app.spec` + `deploy_host.py` + entry pointها (`first_run`/`app_desktop`/`wsgi`/`passenger_wsgi`) — همگی بدون تغییر API سازگارند


## ۵. نقشهٔ راه آینده — اقدام‌پذیر، فازبندی‌شده، با مالک

> هر آیتم: **فاز** (کوتاه‌مدت ≤۱ ماه / میان‌مدت ۱–۳ ماه / بلندمدت ۳–۶ ماه)، **فایل/مسیر**، **معیار موفقیت**.

### ۵.۱ UI/UX (مالک: UX Lead + Frontend)

| فاز | اقدام | مسیر | معیار موفقیت |
|-----|-------|------|----------------|
| کوتاه | **پالت جستجوی سراسری (Ctrl+K)** با `/api/search` موجود؛ کلیدواژه فارسی/کد/موبایل | `static/js/app.js` + `routes/final.py` | جستجو از ۲ کاراکتر، فاصلهٔ <۵۰ms، پیمایش کیبورد |
| کوتاه | **نوار وضعیت دسترسی**: نشانگر ماژول مجاز روی منو (هم‌راستا با `get_user_menu_items` — همین حالا یک کوئری) | `templates/base/layout.html` | نقش غیرمدیر فقط منوی مجاز می‌بیند؛ تست یکپارچه |
| کوتاه | **فیلدهای تاریخ شمسی**: `jalali-picker.js` موجود است — همهٔ فرم‌ها باید از آن استفاده کنند | `static/js/` + فرم‌های finance/attendance | «انتخاب تاریخ شمسی» در ۱۰۰٪ فرم‌های تاریخ‌دار |
| کوتاه | **Empty states و skeleton** برای لیست‌ها و دیشبورد | قالب‌های مدیریتی | دیشبورد بدون داده «آموزش گام‌به‌گام» نشان می‌دهد نه جدول خالی |
| کوتاه | **دکمهٔ سریع «ثبت پرداخت»** از هر صفحه (نمونه: مانifest حاضر، `shortcuts`) | `base/layout.html` + `routes.finance` | ۱ کلیک از دیشبورد به پرداخت جدید |
| میان | **چاپ تمیز**: CSS print برای فیش/گزارش/کارنامه — حذف چاپ کلّ صفحه | `static/css/print.css` جدید | خروجی PDF فیش بدون پس‌زمینه/منو |
| میان | **مهاجرت ۹ اسکریپت inline به فایل** (پیش‌نیاز CSP در ۵.۲) | `templates/base/layout.html` | `grep -r "onclick\|<script>"` در templates = صفر |
| میان | **دسترس‌پذیری**: کنتراست AA در تم تیره (`#546e7a` فقط اول)، ARIA روی toast/دیاپلوگ | `static/css/` | تست axe در CI |
| بلند | **نور آفلاین اول (offline-first)**: SW کش از قبل هست؛ نسخهٔ خواندنی گزارش‌ها روی `indexedDB` | `static/sw.js` + APIها | گزارش مالی هفتهٔ قبل بدون اینترنت مرور می‌شود |
| بلند | **نمایش «آخرین پشتیبان»** در دیشبورد (داده از `run_scheduled_backup` + جدول backup) | `routes/dashboard.py` | مدیر با یک نگاه «دو روز است پشتیبان نگرفته» را می‌بیند |

### ۵.۲ Security (مالک: Security Lead — با پشتیبانی DevOps)

| فاز | اقدام | مسیر | معیار |
|-----|-------|------|--------|
| کوتاه | **محدودسازی نرخ `POST /login`** (همان `utils/rate_limit`، کلید = IP+username) | `routes/auth.py` + `utils/rate_limit.py` | ۱۰۰ تلاش از ۵ IP → 429 با `Retry-After`؛ تست regress |
| کوتاه | **ممیزی ۳ `@csrf.exempt`**: شمارهٔ ۲ تلگرام وبهوک باید بماند؛ بقیه «حذف یا مستند» | `routes/attendance.py:298`, `routes/new_features.py:408,482` | فقط وبهوک موجود است؛ هر exempt جدید در review ممنوع |
| کوتاه | **`SESSION_COOKIE_SECURE` خودکار** در TLS (env: auto/0/1) | `utils/config_loader.py` | روی HTTPS کوکی Secure است حتی اگر اپراتور env نداند |
| کوتاه | **pip-audit در CI** + `requirements.txt` با هش | `.github/workflows/ci.yml` | هر PR با CVE شناخته‌شده قرمز می‌شود |
| میان | **CSP فازبندی‌شده**: (۱) انتقال inline → فایل؛ (۲) `strict-dynamic` با `report-only`؛ (۳) enforce | `utils/error_handling.py` + `static/js/` | گزارش CSP در ۳۰ روز = صفر خطای انسانی |
| میان | **۲FA/TOTP برای مدیران** (جدا از لایسنس؛ مستقل از سرور لایسنس) | `models/user.py` + `routes/auth.py` | مدیر کل اجباری؛ Rest با اختیاری |
| میان | **رمزنگاری پشتیبان** (یا حداقل `BKP` خارج از دامنهٔ وب) + **بازیابی آزمایشی ماهانه** | `utils/backup_service.py` | روند «استور تست» در repo مستند |
| بلند | **معماری چندشعبه با `BranchContext`** (بعد از P2-1) + **audit log فقط‌خواندنی** | مدل‌ها + `utils/activity_log.py` | هر تغییر مالی با «قبل/بعد/کاربر/IP» قابل بازجویی است |
| بلند | **امضای build** (release دسکتاپ با کد امضای دیجیتال) + `SUPPLY_CHAIN` در README | `app_desktop.spec` | کاربر می‌تواند صحت فایل .exe را تأیید کند |

### ۵.۳ DevOps (مالک: DevOps Lead)

| فاز | اقدام | مسیر | معیار |
|-----|-------|------|--------|
| کوتاه | **رفع قرمز بودن CI**: ۱۰ خطای F811 — شکستن `routes/additional.py` به ۶ ماژول (P1-3) | `routes/additional.py` + `bootstrap/blueprints.py` | `ruff check --select E9,F821,F811 .` = صفر |
| کوتاه | **رفع باگ پشتیبان‌گیری سرور**: زمان‌بند سرور از ورکرها جدا شود (systemd timer / container sidecar)؛ در `gunicorn.conf.py` مستند | `gunicorn.conf.py` + `Dockerfile` | در داکر، پشتیبان هرساعت واقعاً اجرا می‌شود |
| کوتاه | **`/healthz`** بدون لایسنس/ورود: `{ok, db: ok, license: ok}` + پینگ دیتابیس | `routes/` یا `bootstrap/web.py` | هاست (Passenger) از این مسیر برای monitoring استفاده کند |
| کوتاه | **لاگ ساختاریافته JSON** (option env `ACADEMY_LOG_JSON=1`) با `request_id` در هر خط | `utils/logging_config.py` | جمع‌آوری در Loki/CloudWatch بدون regex |
| کوتاه | **CI: pytest با ۲ دیتابیس** (SQLite + Postgres service) — بعد از P1-1/P2-4 | `.github/workflows/ci.yml` | «روی من کار می‌کند» برای Postgres هم صادق باشد |
| میان | **Release pipeline**: tag → PyInstaller build (Windows) + چک‌سوم → GitHub Release + artifact hash | `.github/workflows/` | هر release reproducible است |
| میان | **قرارداد env**: مستندسازی همهٔ `ACADEMY_*` در README + فایل `.env.example` + بوت‌چک در `startup_checks.py` | `README.md`, `config.ini.example` | اپراتور با `ACADEMY_COOKIE_SECURE=0` هشدار می‌گیرد |
| میان | **پایش متریک**: `/metrics` (Prometheus) — شمارندهٔ تلاش ورود، خطاهای 4xx/5xx، زمان اولین byte | `utils/metrics.py` + اتصال به `middleware.py` | دیده‌بان هشدار «خطای مالی >۰ در ساعت» |
| بلند | **استقرار آبی/سبز + rollback خودکار** بر اساس `/healthz` | `docker-compose.yml` + مستند | release ناموفق به‌جای ۵۰۰، به نسخهٔ قبلی برمی‌گردد |
| بلند | **Postgres اول** (P2-4): `config.py` از قبل آماده است؛ `flask db` + volume جدا + `pg_dump` | `models/` + `Dockerfile` | مهاجرت بدون downtime (تبدیل پل) |

**مالکیت نهایی (CTO):** P0-1 تا P0-4 (این پاس) مسئولیت مستقیم من است و به‌عنوان «هستهٔ بازسازی» پل فرمی بازبینی شده؛ P1-1 و P1-2 فقط پس از **migration آزمایشی روی دیتابیس واقعی یک مشتری (با پشتیبان)** تأیید می‌شوند؛ P2-1 تا P2-5 به‌ترتیب وابستگی (P1-1 قبل از P1-2، P2-2 بعد از P2-5) اجرا می‌شوند.

**حرف آخر شورا:** این کد از فردا «کار می‌کند» و از امروز «آمادهٔ تغییر» است. تفاوت این دو جمله، تمام ماجراست.

---

*گزارش نهایی شورای ۴۰ متخصص — محصول یک‌پارچه از ۹ دپارتمان (معماری/DB/Backend/Frontend/UX/Security/DevOps/QA/CTO) پس از ۳ دور چالش متقابل. هیچ بخش مستقلی منتشر نشده است.*
