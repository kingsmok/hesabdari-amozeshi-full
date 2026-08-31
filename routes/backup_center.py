"""
مرکز پشتیبان‌گیری و بازیابی — رابط کاربری داخلی نرم‌افزار

همه‌ی مسیرها فقط برای مدیر کل، با لایسنس معتبر و بخش «backup» باز.
"""
import os

from flask import (Blueprint, flash, redirect, render_template, request,
                   send_file, url_for)
from flask_login import current_user, login_required

from extensions import db
from license_client import license_required, licensed_section
from models.user import ActivityLog
from utils import backup_service
from utils.backup_service import BackupError

backup_center_bp = Blueprint('backup_center', __name__, url_prefix='/backup-center')


def _admin_only():
    if not current_user.is_admin:
        flash('فقط مدیر کل به مرکز پشتیبان‌گیری دسترسی دارد', 'error')
        return redirect(url_for('dashboard.index'))
    return None


def _log(action, description):
    try:
        db.session.add(ActivityLog(
            user_id=current_user.id,
            action=action,
            module='backup',
            description=description,
            ip_address=request.remote_addr,
        ))
        db.session.commit()
    except Exception:
        db.session.rollback()


@backup_center_bp.route('/')
@license_required
@login_required
@licensed_section('backup')
def index():
    """صفحه اصلی: تنظیمات، آمار و فهرست بسته‌های پشتیبان"""
    guard = _admin_only()
    if guard:
        return guard

    from models.system import SystemSettings
    from utils.database_tools import database_backend, database_size_bytes

    settings = SystemSettings.query.first()
    return render_template(
        'backup/index.html',
        settings=settings,
        backups=backup_service.list_backups(),
        stats=backup_service.backup_stats(),
        db_backend=database_backend(),
        db_size_mb=round(database_size_bytes() / (1024 * 1024), 2),
    )


@backup_center_bp.route('/create', methods=['POST'])
@license_required
@login_required
@licensed_section('backup')
def create():
    """ساخت بسته پشتیبان جدید (کامل یا فقط دیتابیس)"""
    guard = _admin_only()
    if guard:
        return guard

    kind = request.form.get('kind') or backup_service.KIND_FULL
    note = request.form.get('note', '')
    try:
        info = backup_service.create_backup(kind=kind, note=note)
        _log('backup_create', f"ساخت پشتیبان {info['name']}")
        flash(f"پشتیبان «{info['name']}» با حجم {info['size_mb']} مگابایت ساخته شد", 'success')
    except BackupError as exc:
        flash(str(exc), 'error')
    except Exception as exc:
        flash(f'خطا در پشتیبان‌گیری: {exc}', 'error')
    return redirect(url_for('backup_center.index'))


@backup_center_bp.route('/download/<name>')
@license_required
@login_required
@licensed_section('backup')
def download(name):
    """دانلود بسته پشتیبان"""
    guard = _admin_only()
    if guard:
        return guard

    path = backup_service.safe_backup_path(name)
    if not path or not os.path.isfile(path):
        flash('فایل پشتیبان معتبر یافت نشد', 'error')
        return redirect(url_for('backup_center.index'))
    _log('backup_download', f'دانلود پشتیبان {name}')
    return send_file(path, as_attachment=True, download_name=os.path.basename(path))


@backup_center_bp.route('/restore/<name>', methods=['POST'])
@license_required
@login_required
@licensed_section('backup')
def restore(name):
    """بازیابی از بسته انتخاب‌شده (با پشتیبان ایمنی خودکار)"""
    guard = _admin_only()
    if guard:
        return guard

    restore_uploads = 'restore_uploads' in request.form
    try:
        result = backup_service.restore_backup(name, restore_uploads=restore_uploads)
        _log('backup_restore', f"بازیابی از {result['name']}")
        flash(
            f"بازیابی از «{result['name']}» انجام شد. "
            f"پشتیبان ایمنی: {result['safety_backup']}"
            + (f" — {result['restored_uploads']} فایل بازگردانده شد" if result['restored_uploads'] else '')
            + '. لطفاً برنامه را یک‌بار ببندید و دوباره باز کنید.',
            'success')
    except BackupError as exc:
        flash(str(exc), 'error')
    except Exception as exc:
        flash(f'خطا در بازیابی: {exc}', 'error')
    return redirect(url_for('backup_center.index'))


@backup_center_bp.route('/upload', methods=['POST'])
@license_required
@login_required
@licensed_section('backup')
def upload():
    """آپلود بسته پشتیبان از فایل کاربر (و در صورت درخواست، بازیابی فوری)"""
    guard = _admin_only()
    if guard:
        return guard

    file_storage = request.files.get('backup_file')
    if not file_storage or not file_storage.filename:
        flash('فایل پشتیبان را انتخاب کنید', 'error')
        return redirect(url_for('backup_center.index'))

    try:
        info = backup_service.import_backup(file_storage)
        _log('backup_import', f"ورود بسته {info['name']}")
        flash(f"بسته «{info['name']}» بارگذاری شد", 'success')
        if 'restore_now' in request.form:
            result = backup_service.restore_backup(info['name'], restore_uploads=True)
            _log('backup_restore', f"بازیابی از {result['name']}")
            flash(f"بازیابی انجام شد. پشتیبان ایمنی: {result['safety_backup']}. "
                  'لطفاً برنامه را یک‌بار ببندید و دوباره باز کنید.', 'success')
    except BackupError as exc:
        flash(str(exc), 'error')
    except Exception as exc:
        flash(f'خطا در بارگذاری: {exc}', 'error')
    return redirect(url_for('backup_center.index'))


@backup_center_bp.route('/delete/<name>', methods=['POST'])
@license_required
@login_required
@licensed_section('backup')
def delete(name):
    """حذف بسته پشتیبان"""
    guard = _admin_only()
    if guard:
        return guard

    try:
        removed = backup_service.delete_backup(name)
        _log('backup_delete', f'حذف پشتیبان {removed}')
        flash(f'بسته «{removed}» حذف شد', 'success')
    except BackupError as exc:
        flash(str(exc), 'error')
    return redirect(url_for('backup_center.index'))


@backup_center_bp.route('/settings', methods=['POST'])
@license_required
@login_required
@licensed_section('backup')
def save_settings():
    """ذخیره تنظیمات پشتیبان خودکار"""
    guard = _admin_only()
    if guard:
        return guard

    from models.system import SystemSettings
    from utils.form_helpers import safe_int

    settings = SystemSettings.query.first()
    if settings:
        settings.auto_backup = 'auto_backup' in request.form
        settings.backup_interval_hours = safe_int(request.form.get('backup_interval_hours'), 24) or 24
        settings.max_backups = safe_int(request.form.get('max_backups'), 30) or 30
        db.session.commit()
        flash('تنظیمات پشتیبان‌گیری خودکار ذخیره شد', 'success')
    return redirect(url_for('backup_center.index'))


@backup_center_bp.route('/prune', methods=['POST'])
@license_required
@login_required
@licensed_section('backup')
def prune():
    """حذف نسخه‌های قدیمی بر اساس سقف تعیین‌شده"""
    guard = _admin_only()
    if guard:
        return guard

    from models.system import SystemSettings
    settings = SystemSettings.query.first()
    removed = backup_service.prune_backups(settings.max_backups if settings else 30)
    flash(f'{removed} نسخه قدیمی حذف شد' if removed else 'نسخه‌ای برای حذف وجود نداشت',
          'success' if removed else 'info')
    return redirect(url_for('backup_center.index'))
