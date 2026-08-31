# زنجیره‌ی بیلد محلی (PyInstaller → Inno Setup)

سه فایل اصلی، همگی در ریشه‌ی پروژه:

| فایل | نقش |
|------|-----|
| `app.spec` | ساخت خروجی **onedir** با PyInstaller (`dist\AcademyManager\AcademyManager.exe`) |
| `setup.iss` | ساخت نصب‌کننده‌ی ویندوزی + صفحه‌ی سفارشی ویزارد + نوشتن `config.ini` |
| `build.bat` | اجرای کل زنجیره: پاک‌سازی → PyInstaller → ISCC → گزارش |

> فایل‌های قدیمی `app_desktop.spec` / `installer.iss` / `build_installer.bat` دست‌نخورده
> باقی مانده‌اند؛ زنجیره‌ی جدید جایگزین آن‌هاست و می‌توانید بعداً آن‌ها را حذف کنید.

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
```

## نکته‌های مهم `app.spec`

- `contents_directory='.'` تنظیم شده تا PyInstaller ۶ خروجی را در پوشه‌ی
  `_internal` نریزد؛ کل برنامه مسیرها را از کنار فایل اجرایی می‌خواند.
- `settings.json` بسته‌بندی نمی‌شود (مخصوص هر نصب).
- درایورهای `psycopg2`/`pymysql` در `excludes` هستند (نسخه‌ی دسکتاپ SQLite است و
  `config.py` آن‌ها را داخل `try/except ImportError` وارد می‌کند).
- برای ساخت به `PyQt6` و `PyQt6-WebEngine` نیاز است:
  `pip install -r requirements-build.txt` (خود `build.bat` هم بررسی می‌کند).
