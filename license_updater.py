"""
سامانه به‌روزرسانی خودکار — حساب داری آموزشگاهی رهسا
────────────────────────────────────────────────────────────────
بسته‌های نسخه‌ی جدید از همان سرور لایسنس گرفته می‌شوند و فقط با
لایسنس معتبر قابل دانلودند. زنجیره‌ی اعتماد:

    امضای RSA پاسخ  →  sha256 امضاشده  →  هش فایل دانلودشده

هیچ بسته‌ای پیش از تطابق کامل هش باز نمی‌شود، و هیچ خطایی در این
مسیر نباید مانع بالا آمدن برنامه شود.
"""
import hashlib
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import zipfile

import requests

import license_client
from license_client import (
    LicenseError,
    PRODUCT_SLUG,
    ServerUnreachable,
    SignatureError,
    app_root,
    current_version,
    get_device_identifier,
    load_license_key,
    update_channel,
)

logger = logging.getLogger('license.update')

DOWNLOAD_TIMEOUT = 300
BACKUP_DIR_NAME = '.update_backup'


# ══════════════════════════════════════════════════════════════
#  فاز ۸٫۴ — فهرست محافظت‌شده (داده‌های مشتری)
#  با یافته‌های فاز ۰ این برنامه تکمیل شده است.
# ══════════════════════════════════════════════════════════════
PRESERVE = (
    'instance',                 # academy.db و کلیدهای محلی
    'venv', '.venv', 'env',
    'logs', 'log',
    'backups', '.backups',
    BACKUP_DIR_NAME,
    'static/uploads',           # فایل‌های آپلودی هنرجو/مدرس/گواهینامه
    'uploads', 'media',
    '.env',
    'settings.json',            # پیکربندی و SECRET_KEY همین نصب
    'cookies.txt',
    'migrations/versions',
    '__pycache__', '.git',
)

PRESERVE_EXT = ('.db', '.sqlite', '.sqlite3', '.log', '.enc', '.dat')


def is_preserved(rel_path):
    """آیا این مسیر جزو داده‌های مشتری است و نباید لمس شود؟"""
    norm = str(rel_path).replace('\\', '/').strip('/').lower()
    if not norm:
        return True
    for pattern in PRESERVE:
        pattern = pattern.lower()
        if norm == pattern or norm.startswith(pattern + '/'):
            return True
        # پوشه‌های محافظت‌شده در هر عمقی (مثل __pycache__)
        if f'/{pattern}/' in f'/{norm}/':
            return True
    return norm.endswith(PRESERVE_EXT)


# ══════════════════════════════════════════════════════════════
#  وضعیت به‌روزرسانی اجباری
# ══════════════════════════════════════════════════════════════
_required_update_message = None
_apply_lock = threading.Lock()


def required_update_message():
    """اگر نصب نسخه‌ی جدید اجباری است و انجام نشده، پیام آن را برمی‌گرداند."""
    return _required_update_message


def _set_required_update(message):
    global _required_update_message
    _required_update_message = message


# ══════════════════════════════════════════════════════════════
#  ۸٫۱ — بررسی وجود نسخه جدید
# ══════════════════════════════════════════════════════════════
def _parse_version(value):
    parts = []
    for chunk in str(value or '0').strip().split('.'):
        digits = ''.join(ch for ch in chunk if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:4])


def check_for_update():
    """
    پرسش از سرور. خروجی: dict اطلاعات به‌روزرسانی یا None.
    امضا و nonce توسط license_client._call تایید می‌شوند.
    """
    license_key = load_license_key()
    if not license_key:
        return None

    payload = {
        'license_key': license_key,
        'device_identifier': get_device_identifier(),
        'product': PRODUCT_SLUG,
        'current_version': current_version(),
        'channel': update_channel(),
    }
    envelope = license_client._call('/api/v1/update/check', payload)
    data = license_client.envelope_data(envelope)

    if not data.get('success'):
        logger.info('update: server said %s', data.get('status'))
        return None
    if not data.get('update_available'):
        return None
    if _parse_version(data.get('latest_version')) <= _parse_version(current_version()):
        return None
    if not data.get('sha256') or not data.get('download_url'):
        logger.warning('update: پاسخ بدون هش یا آدرس دانلود — نادیده گرفته شد')
        return None
    return data


# ══════════════════════════════════════════════════════════════
#  ۸٫۲ — دانلود و تایید بسته
# ══════════════════════════════════════════════════════════════
def download_and_verify(info):
    digest = hashlib.sha256()
    folder = tempfile.mkdtemp(prefix='update_')
    path = os.path.join(folder, 'package.zip')

    with requests.get(info['download_url'], stream=True, timeout=DOWNLOAD_TIMEOUT) as response:
        response.raise_for_status()
        header_hash = response.headers.get('X-Package-SHA256')
        if header_hash and header_hash.lower() != str(info['sha256']).lower():
            raise RuntimeError('هش هدر دانلود با هش امضاشده هم‌خوانی ندارد.')
        with open(path, 'wb') as handle:
            for chunk in response.iter_content(65536):
                handle.write(chunk)
                digest.update(chunk)

    if digest.hexdigest().lower() != str(info['sha256']).lower():
        os.remove(path)
        raise RuntimeError('بسته دانلودشده دستکاری شده است.')

    with zipfile.ZipFile(path) as archive:
        if archive.testzip() is not None:
            os.remove(path)
            raise RuntimeError('بسته خراب است.')
        for member in archive.namelist():          # دفاع در برابر Zip-Slip
            normalized = member.replace('\\', '/')
            if normalized.startswith('/') or '..' in normalized.split('/'):
                os.remove(path)
                raise RuntimeError(f'مسیر خطرناک در بسته: {member}')
            if os.path.isabs(normalized) or (len(normalized) > 1 and normalized[1] == ':'):
                os.remove(path)
                raise RuntimeError(f'مسیر مطلق در بسته: {member}')
    return path


def _extract(package_path):
    """بسته را در یک پوشه موقت باز می‌کند و ریشه‌ی واقعی محتوا را برمی‌گرداند."""
    folder = tempfile.mkdtemp(prefix='update_extract_')
    with zipfile.ZipFile(package_path) as archive:
        archive.extractall(folder)
    entries = os.listdir(folder)
    if len(entries) == 1 and os.path.isdir(os.path.join(folder, entries[0])) \
            and entries[0] not in ('payload', 'static', 'templates', 'routes', 'models', 'utils'):
        return os.path.join(folder, entries[0])
    return folder


# ══════════════════════════════════════════════════════════════
#  پشتیبان و بازگردانی
# ══════════════════════════════════════════════════════════════
def _backup_targets(root, relative_paths):
    """از فایل‌هایی که قرار است تغییر کنند پشتیبان می‌گیرد."""
    backup_root = os.path.join(root, BACKUP_DIR_NAME, time.strftime('%Y%m%d_%H%M%S'))
    os.makedirs(backup_root, exist_ok=True)
    saved = []
    for rel in relative_paths:
        source = os.path.join(root, rel)
        if not os.path.isfile(source):
            saved.append((rel, None))
            continue
        target = os.path.join(backup_root, rel)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copy2(source, target)
        saved.append((rel, target))
    return backup_root, saved


def _rollback(root, saved):
    """بازگردانی کامل به وضعیت پیش از نصب."""
    for rel, backup_path in saved:
        destination = os.path.join(root, rel)
        try:
            if backup_path is None:
                if os.path.isfile(destination):
                    os.remove(destination)          # فایلی که تازه اضافه شده بود
            else:
                os.makedirs(os.path.dirname(destination), exist_ok=True)
                shutil.copy2(backup_path, destination)
        except OSError:
            logger.exception('update: rollback failed for %s', rel)


def _cleanup_old_backups(root, keep=3):
    base = os.path.join(root, BACKUP_DIR_NAME)
    if not os.path.isdir(base):
        return
    entries = sorted(
        (name for name in os.listdir(base) if os.path.isdir(os.path.join(base, name)))
    )
    while len(entries) > keep:
        shutil.rmtree(os.path.join(base, entries.pop(0)), ignore_errors=True)


# ══════════════════════════════════════════════════════════════
#  ۸٫۳ — دو روش نصب
# ══════════════════════════════════════════════════════════════
def _plan_full(source_root):
    """فهرست فایل‌های بسته که باید روی برنامه نوشته شوند."""
    plan = []
    for current, _dirs, files in os.walk(source_root):
        for name in files:
            absolute = os.path.join(current, name)
            rel = os.path.relpath(absolute, source_root).replace('\\', '/')
            if rel == 'manifest.json':
                continue
            if is_preserved(rel):
                logger.info('update: مسیر محافظت‌شده نادیده گرفته شد: %s', rel)
                continue
            plan.append(('replace', rel, absolute))
    return plan


def _plan_manifest(source_root, manifest):
    plan = []
    for item in manifest.get('files') or []:
        # ورودی می‌تواند رشته‌ی ساده («مسیر فایل») یا dict کامل باشد
        if isinstance(item, str):
            item = {'action': 'replace', 'path': item}
        elif not isinstance(item, dict):
            continue
        action = str(item.get('action') or 'replace').lower()
        rel = str(item.get('path') or '').replace('\\', '/').strip('/')
        if not rel or is_preserved(rel):
            logger.info('update: مسیر محافظت‌شده در manifest نادیده گرفته شد: %s', rel)
            continue
        if '..' in rel.split('/'):
            logger.warning('update: مسیر خطرناک در manifest: %s', rel)
            continue
        if action in ('replace', 'add'):
            source = os.path.join(source_root, str(item.get('source') or rel))
            if not os.path.isfile(source):
                raise RuntimeError(f'فایل «{rel}» در بسته پیدا نشد.')
            plan.append((action, rel, source))
        elif action == 'delete':
            plan.append(('delete', rel, None))
    return plan


def _apply_plan(root, plan):
    saved = None
    backup_root = None
    try:
        backup_root, saved = _backup_targets(root, [rel for _action, rel, _src in plan])
        for action, rel, source in plan:
            destination = os.path.join(root, rel)
            if action == 'delete':
                if os.path.isfile(destination):
                    os.remove(destination)
                continue
            os.makedirs(os.path.dirname(destination) or root, exist_ok=True)
            shutil.copy2(source, destination)
        return backup_root
    except Exception:
        if saved:
            _rollback(root, saved)
        raise


def apply_update(package_path, info):
    """نصب بسته با پشتیبان و بازگردانی خودکار در صورت خطا."""
    root = app_root()
    source_root = _extract(package_path)
    mode = str(info.get('apply_mode') or 'full').lower()

    manifest_path = os.path.join(source_root, 'manifest.json')
    if mode == 'manifest' or os.path.isfile(manifest_path):
        if not os.path.isfile(manifest_path):
            raise RuntimeError('بسته manifest.json ندارد.')
        with open(manifest_path, encoding='utf-8') as handle:
            manifest = json.load(handle)
        plan = _plan_manifest(source_root, manifest)
    else:
        plan = _plan_full(source_root)

    if not plan:
        raise RuntimeError('بسته هیچ فایل قابل نصبی ندارد.')

    _apply_plan(root, plan)

    # فقط در صورت موفقیت کامل، نسخه به‌روز می‌شود
    version = str(info.get('latest_version') or '').strip()
    if version:
        with open(os.path.join(root, 'VERSION'), 'w', encoding='utf-8') as handle:
            handle.write(version + '\n')

    shutil.rmtree(source_root, ignore_errors=True)
    shutil.rmtree(os.path.dirname(package_path), ignore_errors=True)
    _cleanup_old_backups(root)
    return version


# ══════════════════════════════════════════════════════════════
#  ۸٫۴٫۱ — نصب دستی بسته ZIP (بدون سرور)
#  برای زمانی که مشتری بسته را از پشتیبانی می‌گیرد و خودش نصب می‌کند.
# ══════════════════════════════════════════════════════════════
def _validate_zip(path):
    """سلامت و امنیت مسیرهای داخل بسته را بررسی می‌کند."""
    if not zipfile.is_zipfile(path):
        raise RuntimeError('فایل انتخاب‌شده یک بسته ZIP معتبر نیست.')
    with zipfile.ZipFile(path) as archive:
        if archive.testzip() is not None:
            raise RuntimeError('بسته خراب است.')
        for member in archive.namelist():
            normalized = member.replace('\\', '/')
            if normalized.startswith('/') or '..' in normalized.split('/'):
                raise RuntimeError(f'مسیر خطرناک در بسته: {member}')
            if len(normalized) > 1 and normalized[1] == ':':
                raise RuntimeError(f'مسیر مطلق در بسته: {member}')


def _read_package_info(path):
    """
    اطلاعات نسخه را از داخل بسته می‌خواند (اختیاری).
    فایل‌های شناخته‌شده: update.json / update_info.json / VERSION
    """
    info = {}
    try:
        with zipfile.ZipFile(path) as archive:
            names = {name.replace('\\', '/'): name for name in archive.namelist()}
            for candidate in ('update.json', 'update_info.json'):
                for key, original in names.items():
                    if key.rsplit('/', 1)[-1] == candidate:
                        info.update(json.loads(archive.read(original).decode('utf-8')))
                        break
                if info:
                    break
            if not info.get('latest_version'):
                for key, original in names.items():
                    if key.rsplit('/', 1)[-1] == 'VERSION':
                        info['latest_version'] = archive.read(original).decode('utf-8').strip()
                        break
    except (OSError, ValueError, KeyError, zipfile.BadZipFile):
        return {}
    return info


def inspect_local_package(path):
    """گزارش خواندنی از بسته‌ی محلی: نسخه، هش، تعداد فایل‌ها، حالت نصب."""
    _validate_zip(path)
    info = _read_package_info(path)
    with zipfile.ZipFile(path) as archive:
        members = [name for name in archive.namelist() if not name.endswith('/')]
        has_manifest = any(name.replace('\\', '/').rsplit('/', 1)[-1] == 'manifest.json'
                           for name in archive.namelist())
    return {
        'sha256': _sha256_of(path),
        'size_mb': round(os.path.getsize(path) / (1024 * 1024), 2),
        'files': len(members),
        'latest_version': str(info.get('latest_version') or '').strip(),
        'release_notes': info.get('release_notes') or '',
        'apply_mode': 'manifest' if has_manifest else 'full',
    }


def _sha256_of(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for chunk in iter(lambda: handle.read(65536), b''):
            digest.update(chunk)
    return digest.hexdigest()


def apply_local_package(path, expected_sha256=None, version=None, make_backup=True):
    """
    نصب یک بسته‌ی ZIP که کاربر خودش انتخاب کرده است.

    مراحل: بررسی ZIP → تطبیق اختیاری هش → پشتیبان دیتابیس →
    نصب با همان موتور به‌روزرسانی (با بازگردانی خودکار در صورت خطا).
    """
    if not _apply_lock.acquire(blocking=False):
        raise RuntimeError('یک به‌روزرسانی دیگر در حال انجام است.')
    try:
        _validate_zip(path)
        digest = _sha256_of(path)
        if expected_sha256 and digest.lower() != str(expected_sha256).strip().lower():
            raise RuntimeError('هش بسته با مقدار واردشده هم‌خوانی ندارد؛ نصب انجام نشد.')

        package_info = _read_package_info(path)
        target_version = str(version or package_info.get('latest_version') or '').strip()

        safety_backup = None
        if make_backup:
            try:
                from utils import backup_service
                safety_backup = backup_service.create_backup(
                    kind=backup_service.KIND_DATABASE,
                    note='پیش از نصب بسته به‌روزرسانی',
                )['name']
            except Exception as exc:                       # پشتیبان نباید مانع نصب شود
                logger.warning('update: پشتیبان پیش از نصب گرفته نشد (%s)', exc)

        # بسته در پوشه‌ی موقت کپی می‌شود چون apply_update پوشه‌ی والد را پاک می‌کند
        folder = tempfile.mkdtemp(prefix='update_local_')
        staged = os.path.join(folder, 'package.zip')
        shutil.copy2(path, staged)

        info = dict(package_info)
        info['latest_version'] = target_version
        info['apply_mode'] = info.get('apply_mode') or 'full'
        applied = apply_update(staged, info)
        _set_required_update(None)
        logger.info('update: بسته محلی نصب شد (نسخه %s)', applied or current_version())
        return {
            'status': 'UPDATED',
            'latest_version': applied or current_version(),
            'sha256': digest,
            'safety_backup': safety_backup,
            'message': 'بسته با موفقیت نصب شد.',
        }
    finally:
        _apply_lock.release()


# ══════════════════════════════════════════════════════════════
#  ۸٫۵ — ری‌استارت پس از نصب
# ══════════════════════════════════════════════════════════════
def _restart_windows():
    """اسکریپت واسط می‌سازد تا پس از بسته‌شدن پروسه، برنامه دوباره باز شود."""
    root = app_root()
    args = [sys.executable, os.path.abspath(sys.argv[0]), *sys.argv[1:]]
    quoted = ' '.join(f'"{item}"' for item in args)
    bat = os.path.join(root, 'restart.bat')
    with open(bat, 'w', encoding='utf-8', newline='') as handle:
        handle.write(
            '@echo off\r\n'
            f'cd /d "{root}"\r\n'
            ':wait\r\n'
            f'tasklist /fi "PID eq {os.getpid()}" | find "{os.getpid()}" >nul\r\n'
            'if not errorlevel 1 ( timeout /t 1 /nobreak >nul & goto wait )\r\n'
            f'start "" {quoted}\r\n'
        )
    subprocess.Popen(['cmd', '/c', 'start', '', '/min', bat], cwd=root, close_fds=True)
    os._exit(0)


def restart_application():
    if os.name == 'nt':
        _restart_windows()
    else:
        logger.info('update: نصب کامل شد؛ برای اعمال نسخه جدید برنامه را دوباره اجرا کنید.')


# ══════════════════════════════════════════════════════════════
#  ۸٫۶ — نقطه‌ی ورود
# ══════════════════════════════════════════════════════════════
def check_and_apply_update(silent=True, force_apply=False):
    """
    بررسی، دانلود، تایید و نصب نسخه جدید.
    خروجی: dict گزارش. هرگز استثنا به بیرون نمی‌دهد وقتی silent=True.
    """
    if not _apply_lock.acquire(blocking=False):
        return {'status': 'BUSY', 'message': 'یک به‌روزرسانی در حال انجام است.'}
    try:
        try:
            info = check_for_update()
        except (LicenseError, ServerUnreachable, SignatureError, requests.RequestException) as exc:
            logger.info('update: check failed (%s)', exc)
            if silent:
                return {'status': 'CHECK_FAILED', 'message': 'بررسی به‌روزرسانی انجام نشد.'}
            raise

        if not info:
            _set_required_update(None)
            return {'status': 'NO_UPDATE', 'message': 'نرم‌افزار شما به‌روز است.',
                    'current_version': current_version()}

        required = bool(info.get('update_required'))
        version = info.get('latest_version')

        if silent and not required and not force_apply \
                and str(info.get('restart_mode') or '').lower() == 'manual':
            # نصب دستی: فقط اطلاع‌رسانی
            return {'status': 'UPDATE_AVAILABLE', 'latest_version': version,
                    'release_notes': info.get('release_notes') or '',
                    'message': f'نسخه {version} آماده نصب است.'}

        try:
            package_path = download_and_verify(info)
            applied = apply_update(package_path, info)
        except Exception as exc:
            logger.exception('update: نصب نسخه %s ناموفق بود', version)
            if required:
                _set_required_update(
                    f'نصب نسخه {version} الزامی است ولی انجام نشد. '
                    'لطفاً اتصال اینترنت را بررسی کنید و برنامه را دوباره اجرا کنید.'
                )
            if silent:
                return {'status': 'FAILED', 'message': 'نصب به‌روزرسانی انجام نشد.'}
            raise RuntimeError(str(exc))

        _set_required_update(None)
        logger.info('update: نسخه %s با موفقیت نصب شد', applied)

        if str(info.get('restart_mode') or 'auto').lower() == 'auto':
            restart_application()

        return {'status': 'UPDATED', 'latest_version': applied,
                'message': f'نسخه {applied} با موفقیت نصب شد.'}
    finally:
        _apply_lock.release()
