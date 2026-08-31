"""
مسیرهای فعال‌سازی و مدیریت لایسنس

این بلوپرینت تنها بخشی از برنامه است که بدون لایسنس معتبر هم در
دسترس می‌ماند؛ بقیه مسیرها توسط نگهبان سراسری به همین‌جا هدایت می‌شوند.
"""
from flask import Blueprint, jsonify, redirect, render_template, request, url_for, flash
from flask_login import current_user, login_required

import license_client
from license_features import AVAILABLE_FEATURES
from license_client import (
    PRODUCT_NAME,
    activate_with_key,
    current_version,
    deactivate_current_device,
    get_device_identifier,
    get_device_label,
    get_state,
    normalize_license_key,
    refresh_state,
)

license_bp = Blueprint('license', __name__, url_prefix='/license')

# آخرین نتیجه‌ی بررسی سرور، فقط برای نمایش در صفحه‌ی مرکز به‌روزرسانی
_pending_update = {'info': None}



@license_bp.route('/activate', methods=['GET', 'POST'])
def activate():
    """صفحه‌ی فعال‌سازی — کلید را کاربر وارد می‌کند، نه کد برنامه."""
    state = get_state()

    if request.method == 'POST':
        key = normalize_license_key(request.form.get('license_key'))
        if not key:
            return render_template('license/activate.html', state=state,
                                   error='کلید لایسنس را وارد کنید.',
                                   entered_key='')
        result = activate_with_key(key)
        if result.get('success'):
            flash(result.get('message') or 'لایسنس با موفقیت فعال شد.', 'success')
            return redirect(url_for('dashboard.index'))
        return render_template('license/activate.html', state=get_state(),
                               error=result.get('message') or 'کلید معتبر نیست.',
                               entered_key=key)

    if state.valid:
        return redirect(url_for('license.status'))
    return render_template('license/activate.html', state=state, error=None, entered_key='')


@license_bp.route('/status')
@login_required
def status():
    """وضعیت لایسنس این دستگاه — نام مشتری و بخش‌های مجاز از سرور می‌آید."""
    state = get_state()
    return render_template(
        'license/status.html',
        state=state,
        device_identifier=get_device_identifier(),
        device_label=get_device_label(),
        product_name=PRODUCT_NAME,
        version=current_version(),
        available_features=AVAILABLE_FEATURES,
    )


@license_bp.route('/refresh', methods=['POST'])
@login_required
def refresh():
    """اعتبارسنجی فوری با سرور (دور زدن کش)."""
    state = refresh_state()
    flash(state.message or 'وضعیت لایسنس به‌روز شد.',
          'success' if state.valid else 'error')
    return redirect(url_for('license.status'))


@license_bp.route('/deactivate', methods=['POST'])
@login_required
def deactivate():
    """آزادسازی این دستگاه تا لایسنس روی دستگاه دیگری فعال شود."""
    if not current_user.is_admin:
        flash('فقط مدیر کل دسترسی دارد', 'error')
        return redirect(url_for('license.status'))
    result = deactivate_current_device()
    flash(result.get('message') or '', 'success' if result.get('success') else 'error')
    if result.get('success'):
        return redirect(url_for('license.activate'))
    return redirect(url_for('license.status'))


@license_bp.route('/update', methods=['POST'])
@login_required
def check_update():
    """بررسی و نصب دستی نسخه جدید — خطا هرگز برنامه را نمی‌خواباند."""
    if not current_user.is_admin:
        flash('فقط مدیر کل دسترسی دارد', 'error')
        return redirect(url_for('license.status'))
    try:
        from license_updater import check_and_apply_update
        result = check_and_apply_update(silent=False, force_apply=True)
    except Exception:                             # noqa: BLE001 — گزارش محترمانه به کاربر
        license_client.logger.exception('به‌روزرسانی ناموفق بود')
        flash('به‌روزرسانی انجام نشد؛ برنامه با نسخه فعلی ادامه می‌دهد.', 'error')
        return redirect(url_for('license.status'))
    flash(result.get('message') or 'بررسی به‌روزرسانی انجام شد.',
          'success' if result.get('status') in ('UPDATED', 'NO_UPDATE') else 'warning')
    return redirect(url_for('license.status'))


@license_bp.route('/update-center')
@login_required
def update_center():
    """مرکز به‌روزرسانی: نسخه فعلی، بررسی سرور و نصب دستی بسته ZIP."""
    if not current_user.is_admin:
        flash('فقط مدیر کل دسترسی دارد', 'error')
        return redirect(url_for('dashboard.index'))
    from license_updater import required_update_message
    state = get_state()
    return render_template(
        'license/update.html',
        state=state,
        product_name=PRODUCT_NAME,
        version=current_version(),
        channel=license_client.update_channel(),
        server_url=license_client.server_url(),
        required_message=required_update_message(),
        pending=_pending_update.get('info'),
    )


@license_bp.route('/update/check', methods=['POST'])
@login_required
def check_only():
    """فقط پرسش از سرور — بدون نصب."""
    if not current_user.is_admin:
        flash('فقط مدیر کل دسترسی دارد', 'error')
        return redirect(url_for('dashboard.index'))
    try:
        from license_updater import check_for_update
        info = check_for_update()
    except Exception as exc:                       # noqa: BLE001
        license_client.logger.info('update: بررسی ناموفق (%s)', exc)
        _pending_update['info'] = None
        flash('ارتباط با سرور به‌روزرسانی برقرار نشد؛ می‌توانید بسته را دستی نصب کنید.', 'warning')
        return redirect(url_for('license.update_center'))

    if not info:
        _pending_update['info'] = None
        flash(f'نرم‌افزار شما به‌روز است (نسخه {current_version()}).', 'success')
    else:
        _pending_update['info'] = {
            'latest_version': info.get('latest_version'),
            'release_notes': info.get('release_notes') or '',
            'update_required': bool(info.get('update_required')),
            'size_mb': info.get('size_mb') or info.get('package_size_mb') or '—',
            'sha256': info.get('sha256'),
        }
        flash(f"نسخه {info.get('latest_version')} برای نصب آماده است.", 'info')
    return redirect(url_for('license.update_center'))


@license_bp.route('/update/upload', methods=['POST'])
@login_required
def upload_package():
    """نصب دستی بسته‌ی به‌روزرسانی که کاربر آپلود می‌کند."""
    if not current_user.is_admin:
        flash('فقط مدیر کل دسترسی دارد', 'error')
        return redirect(url_for('dashboard.index'))

    file_storage = request.files.get('package')
    if not file_storage or not file_storage.filename:
        flash('فایل بسته به‌روزرسانی را انتخاب کنید.', 'error')
        return redirect(url_for('license.update_center'))
    if not file_storage.filename.lower().endswith('.zip'):
        flash('فقط فایل ZIP پذیرفته می‌شود.', 'error')
        return redirect(url_for('license.update_center'))

    import os
    import tempfile

    folder = tempfile.mkdtemp(prefix='upload_pkg_')
    staged = os.path.join(folder, 'package.zip')
    try:
        file_storage.save(staged)
        from license_updater import apply_local_package, inspect_local_package
        report = inspect_local_package(staged)
        expected = (request.form.get('sha256') or '').strip()
        result = apply_local_package(
            staged,
            expected_sha256=expected or None,
            version=(request.form.get('version') or '').strip() or None,
        )
        _pending_update['info'] = None
        flash(
            f"بسته با {report['files']} فایل نصب شد؛ نسخه فعلی: {result['latest_version']}."
            + (f" پشتیبان پیش از نصب: {result['safety_backup']}." if result.get('safety_backup') else '')
            + ' برای اعمال کامل، برنامه را یک‌بار ببندید و دوباره باز کنید.',
            'success')
    except Exception as exc:                       # noqa: BLE001
        license_client.logger.exception('نصب دستی بسته ناموفق بود')
        flash(f'نصب بسته انجام نشد: {exc}', 'error')
    finally:
        import shutil
        shutil.rmtree(folder, ignore_errors=True)
    return redirect(url_for('license.update_center'))


@license_bp.route('/health')
def health():
    """بررسی سلامت — بدون لایسنس هم پاسخ می‌دهد."""
    state = get_state()
    return jsonify({
        'ok': True,
        'product': license_client.PRODUCT_SLUG,
        'version': current_version(),
        'license_status': state.status,
        'licensed': state.valid,
    })
