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
    from flask import g, has_request_context

    if has_request_context():
        cached = getattr(g, '_user_menu_items', None)
        if cached is not None:
            return cached

    if not current_user.is_authenticated:
        result = []
    elif current_user.is_admin:
        result = list(MENU_MAP.keys())
    else:
        from models.user import Permission, RolePermission
        allowed_modules = {
            row[0]
            for row in db.session.query(Permission.module)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .filter(RolePermission.role_id == current_user.role_id)
            .distinct().all()
        }
        result = [key for key, module in MENU_MAP.items()
                  if module is None or module in allowed_modules]

    if has_request_context():
        g._user_menu_items = result
    return result


# ── ثبت همه روی اپ ─────────────────────────────────────────────────────
def healthz():
    """سلامت سبک برای Passenger/Docker/مانیتور — بدون لایسنس، بدون ورود.

    SELECT 1 فقط اتصال دیتابیس را می‌سنجد؛ اگر دیتابیس خواب باشد ۵۰۳ می‌دهیم
    تا reverse-proxy نسخهٔ قبلی را نگه دارد، نه اینکه ۵۰۰ مبهم نشان دهد.
    """
    payload = {'ok': True, 'db': 'ok'}
    status = 200
    try:
        from sqlalchemy import text
        db.session.execute(text('SELECT 1'))
    except Exception as exc:                     # noqa: BLE001
        current_app.logger.warning('healthz db failed: %s', exc)
        payload = {'ok': False, 'db': 'error'}
        status = 503
    response = jsonify(payload)
    response.headers['Cache-Control'] = 'no-store'
    return response, status


def setup(app) -> None:
    """ثبت مسیرهای ایستا، فیلترها، context processor و هندلرهای خطا."""
    # مسیرهای ایستا
    app.add_url_rule('/favicon.ico', 'favicon', favicon)
    app.add_url_rule('/manifest.webmanifest', 'manifest', manifest)
    app.add_url_rule('/offline', 'offline', offline)
    app.add_url_rule('/sw.js', 'service_worker', service_worker)
    app.add_url_rule('/healthz', 'healthz', healthz)

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
