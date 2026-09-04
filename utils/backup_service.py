"""
موتور پشتیبان‌گیری و بازیابی داخلی — حساب داری آموزشگاهی رهسا
────────────────────────────────────────────────────────────────
هر بسته‌ی پشتیبان یک فایل ZIP با ساختار زیر است:

    manifest.json            اطلاعات بسته (نسخه، نوع، هش دیتابیس، زمان)
    database/academy.db      کپی سازگار دیتابیس (SQLite Backup API)
    uploads/...              فایل‌های آپلودی هنرجو/مدرس/گواهینامه (در نوع کامل)
    config/settings.json     پیکربندی همان نصب (بدون کلید لایسنس)
    VERSION                  نسخه‌ی نرم‌افزار در زمان تهیه پشتیبان

قواعد ثابت:
  • پیش از هر بازیابی، یک «پشتیبان ایمنی» خودکار گرفته می‌شود.
  • سلامت فایل دیتابیس (PRAGMA integrity_check) و هش SHA-256 پیش از
    جایگزینی بررسی می‌شود؛ فایل ناسالم هرگز جایگزین نمی‌شود.
  • در برابر Zip-Slip محافظت شده است.
  • بسته‌های قدیمیِ نسخه‌های پیشین (`backup_*.db.zip`) هم پشتیبانی می‌شوند.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
import zipfile
from datetime import datetime

from flask import current_app

from extensions import db

BACKUP_PREFIX = 'backup_'
SAFETY_PREFIX = 'safety_'
ALLOWED_EXTENSIONS = ('.zip',)
MANIFEST_NAME = 'manifest.json'
DB_ENTRY = 'database/academy.db'
KIND_FULL = 'full'
KIND_DATABASE = 'database'


class BackupError(RuntimeError):
    """خطای قابل نمایش به کاربر در فرایند پشتیبان‌گیری/بازیابی"""


# ══════════════════════════════════════════════════════════════
#  مسیرها
# ══════════════════════════════════════════════════════════════
def backup_folder() -> str:
    folder = current_app.config.get('BACKUP_FOLDER')
    if not folder:
        folder = os.path.join(current_app.root_path, 'backups')
    os.makedirs(folder, exist_ok=True)
    return folder


def uploads_folder() -> str:
    folder = current_app.config.get('UPLOAD_FOLDER')
    if not folder:
        folder = os.path.join(current_app.root_path, 'static', 'uploads')
    os.makedirs(folder, exist_ok=True)
    return folder


def safe_backup_path(name: str) -> str | None:
    """جلوگیری از پیمایش مسیر؛ فقط فایل‌های داخل پوشه پشتیبان پذیرفته می‌شوند."""
    safe_name = os.path.basename(name or '')
    if not safe_name or safe_name != name:
        return None
    if not safe_name.lower().endswith(ALLOWED_EXTENSIONS):
        return None
    folder = os.path.abspath(backup_folder())
    path = os.path.abspath(os.path.join(folder, safe_name))
    if os.path.commonpath([folder, path]) != folder:
        return None
    return path


def _sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _app_version() -> str:
    try:
        from license_client import current_version
        return current_version()
    except Exception:
        return '1.0.1'


def _timestamp() -> str:
    return datetime.now().strftime('%Y%m%d_%H%M%S')


def _unique_name(folder: str, base: str) -> str:
    """اگر در همان ثانیه چند پشتیبان ساخته شود، نام‌ها روی هم نمی‌افتند."""
    name = f'{base}.zip'
    index = 2
    while os.path.exists(os.path.join(folder, name)):
        name = f'{base}_{index}.zip'
        index += 1
    return name


def _integrity_of(path: str) -> str:
    """PRAGMA integrity_check روی یک فایل؛ فایل غیر-SQLite هم خطای خوانا می‌دهد."""
    try:
        connection = sqlite3.connect(path)
        try:
            row = connection.execute('PRAGMA integrity_check').fetchone()
        finally:
            connection.close()
    except sqlite3.DatabaseError as exc:
        raise BackupError(f'فایل دیتابیس خوانا نیست: {exc}') from exc
    return str(row[0]) if row else 'unknown'


# ══════════════════════════════════════════════════════════════
#  ساخت پشتیبان
# ══════════════════════════════════════════════════════════════
def create_backup(kind: str = KIND_FULL, note: str = '', prefix: str = BACKUP_PREFIX) -> dict:
    """
    ساخت یک بسته‌ی پشتیبان کامل یا فقط-دیتابیس.
    خروجی: dict اطلاعات بسته‌ی ساخته‌شده.
    """
    from utils.database_tools import sqlite_backup, sqlite_database_path

    if sqlite_database_path() is None:
        raise BackupError('پشتیبان‌گیری داخلی فقط برای دیتابیس SQLite در دسترس است. '
                          'برای MySQL/PostgreSQL از ابزار پشتیبان همان سرویس استفاده کنید.')

    kind = KIND_FULL if kind == KIND_FULL else KIND_DATABASE
    folder = backup_folder()
    name = _unique_name(folder, f'{prefix}{kind}_{_timestamp()}')
    target = os.path.join(folder, name)
    staging = tempfile.mkdtemp(prefix='backup_stage_')

    try:
        # ۱) کپی سازگار دیتابیس
        db_copy = os.path.join(staging, 'academy.db')
        sqlite_backup(db_copy)

        integrity = _integrity_of(db_copy)
        if integrity.lower() != 'ok':
            raise BackupError(f'دیتابیس سالم نیست: {integrity}')

        db_hash = _sha256_file(db_copy)

        # ۲) فایل‌های همراه
        included_uploads = 0
        with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as archive:
            archive.write(db_copy, DB_ENTRY)

            if kind == KIND_FULL:
                uploads = uploads_folder()
                for root, _dirs, files in os.walk(uploads):
                    for item in files:
                        absolute = os.path.join(root, item)
                        relative = os.path.relpath(absolute, uploads).replace('\\', '/')
                        archive.write(absolute, f'uploads/{relative}')
                        included_uploads += 1

            settings_file = os.path.join(current_app.root_path, 'settings.json')
            if os.path.isfile(settings_file):
                archive.write(settings_file, 'config/settings.json')

            version_file = os.path.join(current_app.root_path, 'VERSION')
            if os.path.isfile(version_file):
                archive.write(version_file, 'VERSION')

            manifest = {
                'product': 'hesabdari',
                'kind': kind,
                'app_version': _app_version(),
                'created_at': datetime.now().isoformat(timespec='seconds'),
                'database_sha256': db_hash,
                'database_size': os.path.getsize(db_copy),
                'uploads_count': included_uploads,
                'note': (note or '').strip()[:200],
            }
            archive.writestr(MANIFEST_NAME,
                             json.dumps(manifest, ensure_ascii=False, indent=2))

        return describe_backup(target)
    except Exception:
        if os.path.exists(target):
            os.remove(target)
        raise
    finally:
        shutil.rmtree(staging, ignore_errors=True)


# ══════════════════════════════════════════════════════════════
#  فهرست و توصیف بسته‌ها
# ══════════════════════════════════════════════════════════════
def read_manifest(path: str) -> dict:
    try:
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            if MANIFEST_NAME in names:
                return json.loads(archive.read(MANIFEST_NAME).decode('utf-8'))
            # بسته‌ی نسخه‌های قدیمی: فقط یک فایل .db داخل زیپ
            legacy = [item for item in names if item.lower().endswith('.db')]
            if legacy:
                return {'kind': 'legacy', 'app_version': '', 'note': 'بسته نسخه قدیمی',
                        'created_at': '', 'legacy_entry': legacy[0]}
    except (OSError, zipfile.BadZipFile, ValueError, KeyError):
        return {}
    return {}


def describe_backup(path: str) -> dict:
    stat = os.stat(path)
    manifest = read_manifest(path)
    created = manifest.get('created_at') or datetime.fromtimestamp(stat.st_mtime).isoformat(timespec='seconds')
    return {
        'name': os.path.basename(path),
        'size_mb': round(stat.st_size / (1024 * 1024), 2),
        'size_bytes': stat.st_size,
        'modified': datetime.fromtimestamp(stat.st_mtime).strftime('%Y/%m/%d %H:%M'),
        'created_at': created,
        'kind': manifest.get('kind') or 'legacy',
        'app_version': manifest.get('app_version') or '—',
        'note': manifest.get('note') or '',
        'uploads_count': manifest.get('uploads_count') or 0,
        'valid': bool(manifest),
        'is_safety': os.path.basename(path).startswith(SAFETY_PREFIX),
    }


def list_backups() -> list[dict]:
    folder = backup_folder()
    items = []
    for name in os.listdir(folder):
        if not name.lower().endswith(ALLOWED_EXTENSIONS):
            continue
        path = os.path.join(folder, name)
        if os.path.isfile(path):
            items.append(describe_backup(path))
    return sorted(items, key=lambda item: item['name'], reverse=True)


def backup_stats() -> dict:
    items = list_backups()
    total = sum(item['size_bytes'] for item in items)
    return {
        'count': len(items),
        'total_mb': round(total / (1024 * 1024), 2),
        'latest': items[0] if items else None,
        'folder': backup_folder(),
    }


# ══════════════════════════════════════════════════════════════
#  بازیابی
# ══════════════════════════════════════════════════════════════
def _drop_sidecars(paths) -> None:
    """حذف فایل‌های کمکی SQLite (WAL/journal)؛ نبودنشان خطا نیست."""
    for item in paths:
        try:
            os.remove(item)
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise BackupError(
                f'فایل {os.path.basename(item)} قفل است. برای بازیابی، برنامه را '
                'بندازید (یا سرویس/پشتیبان‌گیر خودکار متوقف شود) و دوباره تلاش کنید.') from exc


def _validate_members(archive: zipfile.ZipFile) -> None:
    """دفاع در برابر Zip-Slip روی همه‌ی ورودی‌های بسته."""
    for member in archive.namelist():
        normalized = member.replace('\\', '/')
        if normalized.startswith('/') or '..' in normalized.split('/'):
            raise BackupError(f'مسیر خطرناک در بسته پشتیبان: {member}')
        if len(normalized) > 1 and normalized[1] == ':':
            raise BackupError(f'مسیر مطلق در بسته پشتیبان: {member}')


def _extract_database(archive: zipfile.ZipFile, manifest: dict, destination: str) -> None:
    names = archive.namelist()
    entry = DB_ENTRY if DB_ENTRY in names else manifest.get('legacy_entry')
    if not entry:
        candidates = [item for item in names if item.lower().endswith('.db')]
        if len(candidates) != 1:
            raise BackupError('ساختار بسته پشتیبان معتبر نیست (فایل دیتابیس پیدا نشد).')
        entry = candidates[0]
    with archive.open(entry) as source, open(destination, 'wb') as target:
        shutil.copyfileobj(source, target)


def restore_backup(name: str, restore_uploads: bool = True) -> dict:
    """
    بازیابی از یک بسته‌ی موجود.
    پیش از جایگزینی: پشتیبان ایمنی + بررسی هش + بررسی سلامت دیتابیس.
    """
    from utils.database_tools import sqlite_database_path

    path = safe_backup_path(name)
    if not path or not os.path.isfile(path):
        raise BackupError('فایل پشتیبان معتبر یافت نشد.')

    db_path = sqlite_database_path()
    if not db_path:
        raise BackupError('بازیابی داخلی فقط برای دیتابیس SQLite در دسترس است.')

    manifest = read_manifest(path)
    staging = tempfile.mkdtemp(prefix='restore_')
    temp_db = os.path.join(staging, 'restore.db')

    try:
        with zipfile.ZipFile(path) as archive:
            if archive.testzip() is not None:
                raise BackupError('بسته پشتیبان خراب است.')
            _validate_members(archive)
            _extract_database(archive, manifest, temp_db)

            expected = manifest.get('database_sha256')
            if expected and _sha256_file(temp_db).lower() != str(expected).lower():
                raise BackupError('هش دیتابیس داخل بسته با مقدار ثبت‌شده هم‌خوانی ندارد؛ '
                                  'فایل احتمالاً دستکاری شده است.')

            integrity = _integrity_of(temp_db)
            if integrity.lower() != 'ok':
                raise BackupError(f'دیتابیس داخل بسته سالم نیست: {integrity}')

            # ── پشتیبان ایمنی پیش از هر تغییر ──
            safety = create_backup(kind=KIND_DATABASE, note='پیش از بازیابی',
                                   prefix=SAFETY_PREFIX)

            # ── جایگزینی دیتابیس ──
            # با حالت WAL کنار دیتابیس فایل‌های `-wal`/`-shm` می‌ماند؛ اگر بعد از
            # جایگزینی، آن‌ها پاک نشوند SQLite آن‌ها را روی دیتابیسِ بازگردانده‌شده
            # اعمال می‌کند ⇒ داده‌های تازهٔ بی‌ربط روی فایل قدیمی سوار می‌شود.
            db.session.remove()
            db.engine.dispose()
            sidecars = tuple(db_path + suffix for suffix in ('-wal', '-shm', '-journal'))
            _drop_sidecars(sidecars)
            shutil.copy2(temp_db, db_path)
            _drop_sidecars(sidecars)

            # ── بازگرداندن فایل‌های آپلودی ──
            restored_uploads = 0
            if restore_uploads:
                uploads = uploads_folder()
                for member in archive.namelist():
                    normalized = member.replace('\\', '/')
                    if not normalized.startswith('uploads/') or normalized.endswith('/'):
                        continue
                    relative = normalized[len('uploads/'):]
                    destination = os.path.join(uploads, *relative.split('/'))
                    os.makedirs(os.path.dirname(destination), exist_ok=True)
                    with archive.open(member) as source, open(destination, 'wb') as target:
                        shutil.copyfileobj(source, target)
                    restored_uploads += 1

        return {
            'name': os.path.basename(path),
            'safety_backup': safety['name'],
            'restored_uploads': restored_uploads,
            'app_version': manifest.get('app_version') or '',
        }
    finally:
        shutil.rmtree(staging, ignore_errors=True)


# ══════════════════════════════════════════════════════════════
#  ورود بسته از فایل کاربر
# ══════════════════════════════════════════════════════════════
def import_backup(file_storage) -> dict:
    """
    ذخیره‌ی امن یک بسته‌ی پشتیبان آپلودشده در پوشه پشتیبان‌ها.
    فایل پیش از پذیرش اعتبارسنجی می‌شود.
    """
    filename = os.path.basename(getattr(file_storage, 'filename', '') or '')
    if not filename.lower().endswith('.zip'):
        raise BackupError('فقط فایل ZIP پشتیبان پذیرفته می‌شود.')

    folder = backup_folder()
    name = f'{BACKUP_PREFIX}imported_{_timestamp()}.zip'
    target = os.path.join(folder, name)
    file_storage.save(target)

    try:
        with zipfile.ZipFile(target) as archive:
            if archive.testzip() is not None:
                raise BackupError('فایل آپلودشده خراب است.')
            _validate_members(archive)
            names = archive.namelist()
            if MANIFEST_NAME not in names and not any(item.lower().endswith('.db') for item in names):
                raise BackupError('این فایل یک بسته پشتیبان معتبر نیست.')
    except zipfile.BadZipFile:
        os.remove(target)
        raise BackupError('فایل آپلودشده ZIP معتبر نیست.')
    except BackupError:
        os.remove(target)
        raise

    return describe_backup(target)


# ══════════════════════════════════════════════════════════════
#  حذف و نگهداری
# ══════════════════════════════════════════════════════════════
def delete_backup(name: str) -> str:
    path = safe_backup_path(name)
    if not path or not os.path.isfile(path):
        raise BackupError('فایل پشتیبان معتبر یافت نشد.')
    os.remove(path)
    return os.path.basename(path)


def prune_backups(max_keep: int) -> int:
    """نگهداری تعداد مشخصی از بسته‌های عادی (بسته‌های ایمنی دست‌نخورده می‌مانند)."""
    try:
        max_keep = int(max_keep)
    except (TypeError, ValueError):
        max_keep = 30
    if max_keep <= 0:
        return 0
    items = [item for item in list_backups() if not item['is_safety']]
    removed = 0
    for item in items[max_keep:]:
        try:
            delete_backup(item['name'])
            removed += 1
        except BackupError:
            continue
    return removed


# ══════════════════════════════════════════════════════════════
#  ارسال بسته پشتیبان به ربات بله (برای مدیر)
# ══════════════════════════════════════════════════════════════
BOT_PROVIDER = 'bale'
BOT_HARD_LIMIT_MB = 50          # سقف سرویس بله برای فایل عمومی


def _settings_row():
    from models.system import SystemSettings
    return SystemSettings.query.first()


def bot_targets(settings=None) -> list[str]:
    """
    مقصدهای ارسال: شناسه‌های واردشده در تنظیمات + کاربران «مدیر ربات».
    ترتیب حفظ و تکراری‌ها حذف می‌شوند.
    """
    settings = settings or _settings_row()
    targets: list[str] = []

    raw = (getattr(settings, 'backup_bot_chat_id', '') or '') if settings else ''
    for chunk in raw.replace('؛', ',').replace(';', ',').replace('\n', ',').split(','):
        chat_id = chunk.strip()
        if chat_id and chat_id not in targets:
            targets.append(chat_id)

    try:
        from models.bot import BotUser
        admins = BotUser.query.filter_by(is_admin_bot=True, provider=BOT_PROVIDER).all()
        for admin in admins:
            if admin.is_blocked:
                continue
            chat_id = str(admin.chat_id)
            if chat_id not in targets:
                targets.append(chat_id)
    except Exception:                     # جدول ربات ممکن است هنوز ساخته نشده باشد
        pass

    return targets


def bot_delivery_status() -> dict:
    """وضعیت آمادگی ارسال به ربات، برای نمایش در رابط کاربری."""
    settings = _settings_row()
    token = (getattr(settings, 'bale_bot_token', '') or '') if settings else ''
    targets = bot_targets(settings)
    return {
        'enabled': bool(getattr(settings, 'backup_bot_enabled', False)) if settings else False,
        'has_token': bool(token),
        'targets': targets,
        'targets_count': len(targets),
        'max_mb': int(getattr(settings, 'backup_bot_max_mb', 0) or 45) if settings else 45,
        'kind': (getattr(settings, 'backup_bot_kind', '') or KIND_DATABASE) if settings else KIND_DATABASE,
        'ready': bool(token) and bool(targets),
    }


def _caption_for(info: dict, settings=None) -> str:
    settings = settings or _settings_row()
    academy = (getattr(settings, 'academy_name', '') or '').strip() if settings else ''
    kind_label = {KIND_FULL: 'کامل (دیتابیس + فایل‌ها)',
                  KIND_DATABASE: 'فقط دیتابیس'}.get(info.get('kind'), info.get('kind') or '—')
    try:
        from utils.jalali import gregorian_to_jalali
        stamp = f"{gregorian_to_jalali(datetime.now().date())} {datetime.now().strftime('%H:%M')}"
    except Exception:
        stamp = datetime.now().strftime('%Y/%m/%d %H:%M')

    lines = [
        '📦 بسته پشتیبان نرم‌افزار' + (f' — {academy}' if academy else ''),
        f"نام فایل: {info['name']}",
        f'نوع: {kind_label}',
        f"حجم: {info['size_mb']} مگابایت",
        f'تاریخ: {stamp}',
        f"نسخه نرم‌افزار: {info.get('app_version') or '—'}",
    ]
    if info.get('uploads_count'):
        lines.append(f"فایل‌های همراه: {info['uploads_count']}")
    if info.get('note'):
        lines.append(f"یادداشت: {info['note']}")
    lines.append('این فایل را در جای امن نگه دارید؛ با آن می‌توان کل اطلاعات را بازگرداند.')
    return '\n'.join(lines)


def _log_bot_message(chat_id, text):
    try:
        from models.bot import BotMessage
        db.session.add(BotMessage(chat_id=int(chat_id), direction='outgoing',
                                  text=text[:1000], msg_type='document',
                                  provider=BOT_PROVIDER))
        db.session.commit()
    except Exception:
        db.session.rollback()


def send_backup_to_bot(name: str, targets: list[str] | None = None) -> dict:
    """
    ارسال یک بسته‌ی پشتیبان موجود به ربات بله.
    خروجی: dict گزارش {'sent', 'failed', 'targets', 'name'}
    """
    # لایه‌ی کنترل مستقل: بخش پشتیبان‌گیری باید در لایسنس باز باشد
    try:
        from license_client import assert_feature
        assert_feature('backup')
    except ImportError:
        pass

    path = safe_backup_path(name)
    if not path or not os.path.isfile(path):
        raise BackupError('فایل پشتیبان معتبر یافت نشد.')

    settings = _settings_row()
    token = (getattr(settings, 'bale_bot_token', '') or '').strip() if settings else ''
    if not token:
        raise BackupError('توکن ربات بله ثبت نشده است؛ ابتدا از بخش اتصالات آن را وارد کنید.')

    targets = targets or bot_targets(settings)
    if not targets:
        raise BackupError('مقصدی برای ارسال مشخص نشده است؛ شناسه گفت‌وگوی مدیر را در '
                          'تنظیمات وارد کنید یا یکی از کاربران ربات را «مدیر ربات» کنید.')

    max_mb = int(getattr(settings, 'backup_bot_max_mb', 0) or 45) if settings else 45
    max_mb = min(max_mb, BOT_HARD_LIMIT_MB)
    size_mb = round(os.path.getsize(path) / (1024 * 1024), 2)
    if size_mb > max_mb:
        raise BackupError(f'حجم بسته {size_mb} مگابایت است و از سقف ارسال ربات '
                          f'({max_mb} مگابایت) بیشتر است؛ از گزینه دانلود استفاده کنید '
                          'یا پشتیبان «فقط دیتابیس» بگیرید.')

    info = describe_backup(path)
    caption = _caption_for(info, settings)

    from utils.bot_services import send_bot_document

    sent, failed = [], []
    for chat_id in targets:
        result = send_bot_document(BOT_PROVIDER, token, chat_id, path,
                                   caption=caption, filename=info['name'])
        if result.get('ok'):
            sent.append(chat_id)
            _log_bot_message(chat_id, caption)
        else:
            failed.append({'chat_id': chat_id,
                           'error': result.get('description') or 'خطای نامشخص'})

    return {'name': info['name'], 'size_mb': size_mb, 'targets': targets,
            'sent': sent, 'failed': failed}


# ══════════════════════════════════════════════════════════════
#  پشتیبان‌گیری خودکار (توسط زمان‌بند برنامه صدا زده می‌شود)
# ══════════════════════════════════════════════════════════════
def latest_backup_time() -> datetime | None:
    items = [item for item in list_backups() if not item['is_safety']]
    if not items:
        return None
    path = os.path.join(backup_folder(), items[0]['name'])
    return datetime.fromtimestamp(os.stat(path).st_mtime)


def run_scheduled_backup() -> str:
    """
    اجرای پشتیبان خودکار بر اساس تنظیمات سیستم.
    خروجی: پیام وضعیت (برای لاگ).
    """
    from models.system import SystemSettings

    settings = SystemSettings.query.first()
    if not settings or not settings.auto_backup:
        return 'پشتیبان خودکار غیرفعال است'

    interval = int(settings.backup_interval_hours or 24)
    latest = latest_backup_time()
    if latest and (datetime.now() - latest).total_seconds() < interval * 3600:
        return 'هنوز زمان پشتیبان بعدی نرسیده است'

    info = create_backup(kind=KIND_FULL, note='پشتیبان خودکار')
    removed = prune_backups(settings.max_backups or 30)
    report = f"{info['name']} ساخته شد" + (f'؛ {removed} نسخه قدیمی حذف شد' if removed else '')

    # ارسال خودکار به ربات بله (در صورت فعال بودن) — خطایش پشتیبان را باطل نمی‌کند
    if getattr(settings, 'backup_bot_enabled', False):
        try:
            kind = getattr(settings, 'backup_bot_kind', '') or KIND_DATABASE
            package = info
            if kind == KIND_DATABASE:
                package = create_backup(kind=KIND_DATABASE, note='پشتیبان خودکار برای ربات')
            delivery = send_backup_to_bot(package['name'])
            report += f"؛ برای {len(delivery['sent'])} مقصد در بله ارسال شد"
            if delivery['failed']:
                report += f" ({len(delivery['failed'])} مقصد ناموفق)"
        except Exception as exc:
            report += f'؛ ارسال به ربات انجام نشد ({exc})'

    return report
