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
