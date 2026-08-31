"""
خواندن config.ini ساخته‌شده توسط نصب‌کننده (Inno Setup)
────────────────────────────────────────────────────────────────
نصب‌کننده در پایان نصب، پاسخ‌های اپراتور را در `{app}\\config.ini`
می‌نویسد. این ماژول همان فایل را می‌خواند و در اولین اجرا:

  • حساب مدیر را می‌سازد (اگر هنوز هیچ مدیری وجود نداشته باشد)
  • آدرس هاست پلتفرم و تنظیمات لایسنس را در `settings.json` می‌نشاند
  • بلافاصله پس از ساخت حساب، رمز عبور را از فایل پاک می‌کند
    (`password_consumed = true`) تا رمز به‌صورت متنی روی دیسک نماند

هیچ خطایی در این مسیر نباید مانع بالا آمدن برنامه شود.
"""
from __future__ import annotations

import configparser
import logging
import os
import sys

logger = logging.getLogger('installer.config')

INI_NAME = 'config.ini'
TRUE_WORDS = {'1', 'true', 'yes', 'on'}


def base_dir() -> str:
    """کنار فایل اجرایی (حالت نصب‌شده) یا ریشه‌ی پروژه (حالت توسعه)."""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def ini_path() -> str:
    return os.path.join(base_dir(), INI_NAME)


def _as_bool(value, default=False) -> bool:
    if value is None:
        return default
    return str(value).strip().lower() in TRUE_WORDS


def _load_parser(path):
    """
    خواندن فایل با کدگذاری‌های محتمل.
    ویندوز مقادیر غیرانگلیسی را با کدپیج سیستم (مثلاً cp1256) می‌نویسد،
    در حالی که خود برنامه UTF-8 می‌نویسد؛ هر دو باید خوانده شوند.
    """
    for encoding in ('utf-8-sig', 'utf-16', 'cp1256', 'latin-1'):
        parser = configparser.ConfigParser()
        try:
            with open(path, 'r', encoding=encoding) as handle:
                parser.read_file(handle)
            return parser
        except (UnicodeDecodeError, UnicodeError):
            continue
        except (configparser.Error, OSError) as exc:
            logger.warning('config.ini خوانده نشد: %s', exc)
            return None
    logger.warning('کدگذاری config.ini شناسایی نشد')
    return None


def read_installer_config() -> dict:
    """
    محتوای config.ini را به شکل dict برمی‌گرداند.
    اگر فایل نباشد یا خراب باشد، dict خالی برمی‌گردد.
    """
    path = ini_path()
    if not os.path.isfile(path):
        return {}

    parser = _load_parser(path)
    if parser is None:
        return {}

    def get(section, option, fallback=''):
        try:
            return parser.get(section, option, fallback=fallback).strip()
        except (configparser.Error, AttributeError):
            return fallback

    return {
        'admin': {
            'username': get('Admin', 'username'),
            'password': get('Admin', 'password'),
            'consumed': _as_bool(get('Admin', 'password_consumed', 'false')),
        },
        'platform': {
            'host_url': get('Platform', 'host_url'),
            'verify_ssl': _as_bool(get('Platform', 'verify_ssl', 'true'), True),
        },
        'license': {
            'server_url': get('License', 'server_url'),
            'channel': get('License', 'channel', 'stable'),
            'auto_update': _as_bool(get('License', 'auto_update', 'true'), True),
        },
        'install': {
            'version': get('Install', 'version'),
            'installed_at': get('Install', 'installed_at'),
            'install_dir': get('Install', 'install_dir'),
        },
    }


def _write_option(section: str, option: str, value: str) -> bool:
    """نوشتن یک مقدار در config.ini با حفظ بقیه‌ی محتوا."""
    path = ini_path()
    if not os.path.isfile(path):
        return False
    parser = _load_parser(path)
    if parser is None:
        return False
    try:
        if not parser.has_section(section):
            parser.add_section(section)
        parser.set(section, option, value)
        with open(path, 'w', encoding='utf-8') as handle:
            # بدون فاصله دور «=» تا Windows INI API (GetPrivateProfileString)
            # و SetIniString نصب‌کننده هم دقیقاً همین کلیدها را بخوانند
            parser.write(handle, space_around_delimiters=False)
        return True
    except (configparser.Error, OSError) as exc:
        logger.warning('config.ini به‌روزرسانی نشد: %s', exc)
        return False


def consume_admin_password() -> bool:
    """رمز عبور را از فایل پاک می‌کند تا فقط یک‌بار مصرف باشد."""
    ok = _write_option('Admin', 'password', '')
    ok = _write_option('Admin', 'password_consumed', 'true') and ok
    return ok


def apply_platform_settings(data: dict) -> bool:
    """آدرس هاست و تنظیمات لایسنس را در settings.json می‌نشاند."""
    try:
        from config import load_config, save_config
    except ImportError:
        return False

    changed = False
    settings = load_config()

    host = (data.get('platform') or {}).get('host_url')
    if host:
        platform_section = settings.setdefault('platform', {})
        if platform_section.get('host_url') != host:
            platform_section['host_url'] = host
            platform_section['verify_ssl'] = data['platform'].get('verify_ssl', True)
            changed = True

    license_data = data.get('license') or {}
    if license_data.get('server_url'):
        license_section = settings.setdefault('license', {})
        for key in ('server_url', 'channel', 'auto_update'):
            value = license_data.get(key)
            if value not in (None, '') and license_section.get(key) != value:
                license_section[key] = value
                changed = True

    if changed:
        try:
            save_config(settings)
        except OSError as exc:
            logger.warning('settings.json ذخیره نشد: %s', exc)
            return False
    return changed


def bootstrap_admin(data: dict) -> str:
    """
    ساخت حساب مدیر با اطلاعات نصب‌کننده.
    خروجی: پیام وضعیت (برای لاگ). حساب موجود هرگز بازنویسی نمی‌شود.
    """
    admin = data.get('admin') or {}
    username = (admin.get('username') or '').strip()
    password = admin.get('password') or ''

    if admin.get('consumed'):
        return 'رمز نصب‌کننده قبلاً مصرف شده است'
    if not username or not password:
        return 'اطلاعات مدیر در config.ini کامل نیست'

    from extensions import db
    from models.user import Role, User

    if User.query.filter_by(is_admin=True).first():
        consume_admin_password()
        return 'مدیر از قبل وجود دارد؛ رمز نصب‌کننده پاک شد'

    if User.query.filter_by(username=username).first():
        consume_admin_password()
        return f'کاربر «{username}» از قبل وجود دارد'

    admin_role = Role.query.filter_by(is_admin=True).first() or Role.query.first()
    user = User(
        username=username,
        full_name='مدیر سیستم',
        is_admin=True,
        is_active=True,
        role_id=admin_role.id if admin_role else None,
    )
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    consume_admin_password()
    return f'حساب مدیر «{username}» از روی config.ini ساخته شد'


def apply_installer_config() -> str:
    """
    نقطه‌ی ورود: در استارتاپ برنامه (داخل app context) صدا زده می‌شود.
    هرگز استثنا به بیرون نمی‌دهد.
    """
    try:
        data = read_installer_config()
        if not data:
            return ''
        apply_platform_settings(data)
        return bootstrap_admin(data)
    except Exception as exc:                      # noqa: BLE001 — نباید استارتاپ را بخواباند
        logger.warning('اعمال config.ini انجام نشد: %s', exc)
        try:
            from extensions import db
            db.session.rollback()
        except Exception:
            pass
        return ''


def platform_host() -> str:
    """آدرس هاست cPanel/وردپرس — اول settings.json، بعد config.ini."""
    try:
        from config import load_config
        host = (load_config().get('platform') or {}).get('host_url')
        if host:
            return host
    except Exception:
        pass
    return (read_installer_config().get('platform') or {}).get('host_url', '')
