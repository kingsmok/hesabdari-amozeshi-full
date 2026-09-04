# زنجیره‌ی بیلد محلی (PyInstaller → Inno Setup)

سه فایل اصلی، همگی در ریشه‌ی پروژه:

| فایل | نقش |
|------|-----|
| `app.spec` | ساخت خروجی **onedir** با PyInstaller (`dist\AcademyManager\AcademyManager.exe`) |
| `setup.iss` | ساخت نصب‌کننده‌ی ویندوزی + صفحه‌ی سفارشی ویزارد + نوشتن `config.ini` |
| `build.bat` | اجرای کل زنجیره: پاک‌سازی → PyInstaller → ISCC → گزارش |

> فایل‌های قدیمی `app_desktop.spec` / `installer.iss` / `build_installer.bat`
> هنوز در دسترس‌اند؛ زنجیره‌ی جدید جایگزین آن‌هاست و می‌توانید بعداً آن‌ها را حذف کنید.
>
> **نکته (تعمیر `build_installer.bat`):** مشکل «باز و بسته شدن فوری پنجره» به‌خاطر
> باگ معروف cmd.exe با متن فارسی در فایل‌های بچ (code page 65001) و خط‌ختم‌های
> Unix (LF) در این فایل بود. حالا `build_installer.bat` یک پوسته‌ی کوچک ASCII است و
> تمام منطق در `build_installer.py` اجرا می‌شود؛ متن فارسی توسط Python نمایش داده
> می‌شود و پنجره تا پایان باز می‌ماند. همچنین همه‌ی پکیج‌های `requirements.txt`
> (نه فقط بخشی از آن‌ها) نصب می‌شوند.
>
> **Inno Setup نصب نیست؟** دیگر لازم نیست بیلد فوراً متوقف شود. اگر
> `ISCC.exe` پیدا نشود، `build_installer.py` از شما می‌پرسد و سعی می‌کند
> Inno Setup را خودکار نصب کند:
>
> - ابتدا از `winget install --id JRSoftware.InnoSetup` استفاده می‌کند؛
> - اگر winget در دسترس نباشد، آخرین نسخه‌ی ۶ را از صفحه‌ی رسمی
>   `https://jrsoftware.org/isdl.php` دانلود و به‌صورت بی‌صدا
>   (`/VERYSILENT /CURRENTUSER`) نصب می‌کند.
>
> اگر نصب خودکار جواب نداد، می‌توانید Inno Setup را دستی نصب کنید و همان پنجره
> را ببندید و دوباره `build_installer.bat` را اجرا کنید. برای اجرای کاملاً بی‌پرسش
> در اسکریپت/اتوماسیون، متغیر محیطی `AUTO_INSTALL_INNO=1` را قرار دهید.

## اجرا

```bat
pip install pyinstaller
build.bat
```

خروجی‌ها:

- برنامه: `dist\AcademyManager\AcademyManager.exe`
- نصب‌کننده: `installer_output\HesabdariRahsa_Setup_1.0.1.exe`

`build.bat` در هر مرحله `errorlevel` را بررسی می‌کند و با کد خروج ۱ متوقف می‌شود.
مسیر `ISCC.exe` به‌ترتیب از `PATH`، `Program Files (x86)\Inno Setup 6` و
`Program Files\Inno Setup 6` جست‌وجو می‌شود.

## صفحه‌ی سفارشی نصب‌کننده

بعد از صفحه‌ی انتخاب مسیر (`wpSelectDir`) یک صفحه‌ی
`CreateInputQueryPage` با سه ورودی نمایش داده می‌شود:

1. `Admin username`
2. `Admin password` (ماسک‌شده با `*`، حداقل ۶ کاراکتر)
3. `cPanel host URL / IP` (اگر `http(s)://` نداشته باشد، خودکار اضافه می‌شود)

در `ssPostInstall` این مقادیر با `SetIniString` در `{app}\config.ini` نوشته می‌شوند.

نکته‌های عملیاتی که در اسکریپت رعایت شده‌اند:

- **نام کاربری فقط ASCII** (حروف/رقم/`. _ -`)؛ چون `SetIniString` مقادیر را با
  کدپیج سیستم می‌نویسد و حروف فارسی ممکن است خراب شوند.
- **نصب مجدد/ارتقا**: اگر `config.ini` از قبل وجود داشته باشد، `ShouldSkipPage`
  صفحه را رد می‌کند و بخش `[Admin]`/`[Platform]` هرگز بازنویسی نمی‌شود؛
  فقط `[Install]` (نسخه و تاریخ) تازه می‌شود.
- **نصب بی‌صدا**:
  `setup.exe /VERYSILENT /AdminUser=admin /AdminPass=Secret123 /Host=panel.example.com`
- **دسترسی‌ها**: پوشه‌های `instance`, `backups`, `logs`, `static\uploads` با
  `Permissions: users-modify` ساخته می‌شوند (برنامه در Program Files نصب می‌شود
  و کاربر معمولی باید بتواند در دیتابیس بنویسد). روی `config.ini` هم با `icacls`
  دسترسی به Administrators/SYSTEM (کامل) و Users (تغییر) محدود می‌شود تا برنامه‌ی
  غیر‌ادمین بتواند رمز یک‌بارمصرف را پاک کند.
- **حذف نصب**: داده‌ها فقط با تأیید صریح کاربر پاک می‌شوند و در حالت بی‌صدا هرگز.
- فایل `setup.iss` با **UTF-8 + BOM** ذخیره شده (لازمه‌ی Inno Setup پیش از ۶٫۳
  برای رشته‌های فارسی).

## ساختار config.ini

```ini
[Admin]
username=admin
password=ChangeMe123
password_consumed=false

[Platform]
host_url=https://panel.example.com
verify_ssl=true

[License]
server_url=https://ls.ariapadideh.ir
channel=stable
auto_update=true

[Install]
version=1.0.1
installed_at=2026-08-31 10:20:30
install_dir=C:\Program Files\Hesabdari Rahsa
```

نمونه‌ی کامل: `config.ini.example` (خود `config.ini` در `.gitignore` است).

## خواندن در پایتون

ماژول `utils/installer_config.py`:

```python
from utils.installer_config import read_installer_config, platform_host

data = read_installer_config()
print(data['admin']['username'])      # admin
print(data['platform']['host_url'])   # https://panel.example.com
print(platform_host())                # settings.json → fallback به config.ini
```

فراخوانی خودکار در `app.py` (بلافاصله پس از `create_default_data()`):

```python
from utils.installer_config import apply_installer_config
installer_note = apply_installer_config()
```

`apply_installer_config()` سه کار انجام می‌دهد و هرگز استثنا به بیرون نمی‌دهد:

1. `host_url` و تنظیمات لایسنس را در `settings.json` می‌نشاند.
2. اگر هیچ مدیری در دیتابیس نباشد، حساب مدیر را از روی `[Admin]` می‌سازد.
3. رمز عبور را از `config.ini` پاک می‌کند و `password_consumed=true` می‌گذارد
   (رمز فقط یک‌بار مصرف است و به‌صورت متنی روی دیسک نمی‌ماند).

## آزمون‌ها

```bash
pytest tests/test_installer_config.py -q      # ۱۰ آزمون
pytest tests -q                               # کل پوشش (۳۱۴ آزمون، ~۱۲ ثانیه)
```

بخش زیادی از آزمون‌ها روی همان `instance/academy.db` (دیتابیس توسعه) کار می‌کنند و
ردیف‌های آزمونی را در پایان پاک می‌کنند؛ برای همین دو متغیر محیطی در
`tests/conftest.py` تنظیم می‌شود:

- `ACADEMY_DISABLE_SCHEDULER=1` — ترد زمان‌بندی پشتیبان‌گیری خودکار خاموش می‌شود.
  هر ماژول آزمون یک `create_app()` می‌سازد و اگر تردهای همه آن اپ‌ها زنده بمانند،
  روی یک فایل SQLite با هم می‌جنگند.
- `ACADEMY_SQLITE_BUSY_TIMEOUT=2` — مهلت انتظار برای قفل؛ در production مقدار
  پیش‌فرض ۱۰ ثانیه است (`config.py`، با `busy_timeout_seconds` در `settings.json`
  قابل تغییر). چون دیتابیس روی WAL رفته، خوانندهٔ طولانی دیگر نوشتن را قفل نمی‌کند.

اگر جایی `database is locked` دیدید، اول شک کنید یک `app_context()` باز مانده است
(مثلاً `yield` داخل `with app.app_context()` در یک fixture)؛ آن context یک
تراکنش خواندن را تا آخر ماژول باز نگه می‌دارد.

## نکته‌های مهم `app.spec`

- `contents_directory='.'` تنظیم شده تا PyInstaller ۶ خروجی را در پوشه‌ی
  `_internal` نریزد؛ کل برنامه مسیرها را از کنار فایل اجرایی می‌خواند.
- `settings.json` بسته‌بندی نمی‌شود (مخصوص هر نصب).
- درایورهای `psycopg2`/`pymysql` فقط از **بسته‌ی ویندوزی** حذف شده‌اند
  (`excludes`)؛ این کار هیچ اثری روی اجرای وب/هاست ندارد.
  پیش‌فرض هر دو حالت (دسکتاپ و وب) SQLite است — `config.py` نوع دیتابیس را
  `sqlite` می‌گذارد و SQLite با ماژول استاندارد `sqlite3` کار می‌کند و به هیچ
  درایور اضافه‌ای نیاز ندارد. اگر روزی روی هاست MySQL/PostgreSQL خواستید، کافی است
  `pip install pymysql` یا `psycopg2-binary` را روی همان سرور نصب کنید؛
  `config.py` آن‌ها را داخل `try/except ImportError` وارد می‌کند.
- برای ساخت به `PyQt6` و `PyQt6-WebEngine` نیاز است:
  `pip install -r requirements-build.txt` (خود `build.bat` هم بررسی می‌کند).
