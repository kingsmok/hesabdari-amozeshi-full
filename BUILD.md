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

در `ssPostInstall` این مقادیر با `SetIniString` در `{app}\config.ini` نوشته
می‌شوند و دسترسی فایل با `icacls` فقط به Administrators/SYSTEM محدود می‌شود.

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
pytest tests/test_installer_config.py -q      # ۸ آزمون
```
