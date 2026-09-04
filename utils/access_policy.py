"""
نگهبان متمرکز دسترسی (Role Guard)
════════════════════════════════════════════════════════════════

چرا این فایل هست؟
    تا پیش از این، نقش‌ها فقط منوی سایدبار را فیلتر می‌کردند (مخفی‌سازی) و تقریباً همه
    مسیرهای نوشتنی فقط `@login_required` داشتند؛ یعنی یک کاربر با نقش «مدرس» می‌توانست
    با درخواست مستقیم، کاربر بسازد، نقش حذف کند، حقوق پرداخت کند یا صندوق را خالی کند.

این ماژول همان سیاست را به یک لایه اجرایی تبدیل می‌کند:
    • مسیرهای حساس → فقط مدیر کل
    • مسیرهای ماژول‌دار → دسترسی به همان ماژول الزامی است
    • مسیرهای حذف/بازیابی → صریحاً «delete» (بقیه عملیات با دسترسی ماژول مجازند)

طرح دو لایه:
    سطح «action» (create/edit/delete) برای همه نوشتن‌ها اجباری است، اما `backfill_role_actions()`
    در اولین درخواست، ردیف‌های اکشن هر «نقش × ماژول» را کامل می‌کند (فقط اضافه، هرگز حذف
    نه) ⇒ نصب‌های موجود دقیقاً همان دسترسی دیروز را دارند و از این پس برداشتن یک اکشن در
    «ویرایش دسترسی نقش» واقعی است. کلید پشتیبانی میدانی: `ACADEMY_DISABLE_ACTION_GUARD=1`.

نکته ایمنی: نگهبان فقط روی کاربر «واردشده» اعمال می‌شود تا مسیرهای بدون نشست
(تقویم دستگاه حضور و غیاب، webhook ربات، ویزارد setup) نشکنند؛ آن‌ها مکانیزم احراز
هویت خودشان (توکن/`login_required`) را دارند.
"""
from __future__ import annotations

import os
import re

from flask import flash, jsonify, redirect, request, url_for
from flask_login import current_user

#: الزام سطح «اکشن» برای نوشتن‌ها (create/edit/delete) — روشن است، چون
#: `backfill_role_actions()` در بوت، ردیف‌های اکشنِ نقش‌های نصب‌های قدیمی را
#: کامل می‌کند و لذا رفتار عوض نمی‌شود؛ فقط از این پس برداشتن یک اکشن در
#: «ویرایش دسترسی نقش» واقعاً اعمال می‌شود.
#: در صورت نیاز به عیب‌یابی میدانی: `ACADEMY_DISABLE_ACTION_GUARD=1`
ENFORCE_ACTION_FOR_WRITES = True

#: اکشن‌هایی که برای هر «نقش × ماژول» ساخته/تکمیل می‌شوند
BACKFILL_ACTIONS = ('view', 'create', 'edit', 'delete')


def action_guard_enabled() -> bool:
    """آیا الزام سطح اکشن فعال است؟ (متغیر محیطی = کلید پشتیبانی)"""
    if os.environ.get('ACADEMY_DISABLE_ACTION_GUARD') == '1':
        return False
    return ENFORCE_ACTION_FOR_WRITES

#: پیشوند مسیر → ماژول دسترسی (نام‌ها همان `permissions.module` است)
MODULE_BY_PREFIX = {
    'students': 'students',
    'teachers': 'teachers',
    'classes': 'classes',
    'courses': 'courses',
    'registration': 'registration',
    'attendance': 'attendance',
    'exams': 'exams',
    'grades': 'exams',
    'finance': 'finance',
    'expenses': 'finance',
    'accounting': 'accounting',
    'payroll': 'payroll',
    'salary': 'payroll',
    'tax': 'tax',
    'reports': 'reports',
    'export': 'reports',
    'analytics': 'reports',
    'messaging': 'messaging',
    'certificates': 'certificates',
}

#: این بخش‌ها حتی برای مدیر آموزشگاه هم فقط با حساب «مدیر کل» باز می‌شوند
ADMIN_ONLY_PREFIXES = {
    'settings',
    'perms',
    'panel',
    'backup-center',
    'bot-panel',
    'license',
    'demo',
    'network-info',
}

#: مسیرهای دقیق (بدون پیشوند) که مدیریتی هستند
ADMIN_ONLY_PATHS = {
    '/reports/custom-builder',
    '/api/network',
    '/dashboard/customize',
}

#: همیشه آزاد برای کاربر واردشده (تخصصی/ابزاری/عمومی)
EXEMPT_PREFIXES = {
    'static', 'login', 'logout', 'favicon.ico', 'manifest.webmanifest', 'sw.js',
    'offline', 'apple-touch-icon.png',
    'my',           # پورتال مدرس — خودش داده را به کاربر جاری مقید می‌کند
    'webhook',      # تلگرام/بله — با توکن اعتبارسنجی می‌شوند
    'api',          # api/* پایین‌تر بررسی می‌شود (network مدیریتی است)
    'dashboard', 'search', 'favorites', 'help', 'support', 'assistant', 'suggestions',
    'polls', 'surveys', 'complaints', 'tickets', 'documents', 'corporate', 'franchise',
    'goals',
    'setup',        # ویزارد نصب — خودش بررسی می‌کند نصب کامل شده است و مسیرهای
                    # حساس‌اش (@login_required) جداگانه قفل‌اند
    '',             # صفحه خانگی
}

_WRITE_METHODS = {'POST', 'PUT', 'PATCH', 'DELETE'}

# مسیرهایی که «تخریبی» تلقی می‌شوند و به اکشن delete نیاز دارند
_DESTRUCTIVE = re.compile(
    r'(/delete(/|$)|/destroy|/restore(/|$)|/prune$|/cleanup$|/deactivate$|/roles/.*delete)'
)
_ACTION_BY_SEGMENT = (
    (re.compile(r'/edit(/|$)'), 'edit'),
    (re.compile(r'/(approve|confirm|pay|cancel|close|resolve|respond|toggle|reset-password'
                r'|status|sync|repair|optimize|import|upload|bulk|batch|restore)'), 'edit'),
)


def _wants_json() -> bool:
    if request.path.startswith('/api/'):
        return True
    if request.is_json:
        return True
    return request.headers.get('X-Requested-With') == 'XMLHttpRequest'


def _deny(reason: str):
    """پاسخ «دسترسی نداری» — برای AJAX json و برای بقیه redirect با پیام."""
    if _wants_json():
        return jsonify({'ok': False, 'status': 'FORBIDDEN', 'message': reason}), 403
    try:
        flash(reason, 'error')
    except Exception:
        pass
    return redirect(url_for('dashboard.index'))


def resolve_policy(path: str, method: str) -> tuple[str, str] | None:
    """
    بازگرداندن (what, module_action) برای یک مسیر:
        ('admin', None)        → فقط مدیر کل
        ('module', <module>)   → دسترسی به ماژول لازم است
        ('delete', <module>)   → ماژول + اکشن delete
        None                   → آزاد
    """
    clean = '/' + (path or '').lstrip('/')
    if len(clean) > 1:
        clean = clean.rstrip('/')
    segment = clean.strip('/').split('/')[0]

    if clean in ADMIN_ONLY_PATHS or segment in ADMIN_ONLY_PREFIXES:
        return ('admin', None)
    if segment in EXEMPT_PREFIXES:
        return None

    module = MODULE_BY_PREFIX.get(segment)
    if not module:
        return None

    if method.upper() in _WRITE_METHODS:
        if _DESTRUCTIVE.search(clean):
            return ('delete', module)
        if action_guard_enabled():
            return (f'action:{required_write_action(clean)}', module)
    return ('module', module)


def required_write_action(path: str) -> str:
    """اکشن پیشنهادی برای دکوراتورهای موضعی (create/edit/delete)."""
    clean = '/' + (path or '').lstrip('/')
    for pattern, action in _ACTION_BY_SEGMENT:
        if pattern.search(clean):
            return action
    if _DESTRUCTIVE.search(clean):
        return 'delete'
    return 'create'


def check_access() -> tuple[bool, str]:
    """True اگر کاربر جاری مجاز است. برای کاربر واردنشده همیشه True (مسئولیت با login_required)."""
    if not current_user.is_authenticated:
        return True, ''

    policy = resolve_policy(request.path, request.method)
    if policy is None:
        return True, ''

    kind, module = policy
    if kind == 'admin':
        if current_user.is_admin:
            return True, ''
        return False, 'این بخش فقط برای مدیر کل قابل دسترسی است'

    if current_user.is_admin:
        return True, ''
    if not current_user.role_id:
        return False, 'برای حساب شما هیچ نقشی تعریف نشده است؛ با مدیر کل تماس بگیرید'

    if kind == 'delete':
        if current_user.has_permission(module, 'delete') or current_user.has_permission(module, 'edit'):
            return True, ''
        return False, 'شما اجازه حذف یا بازیابی در این بخش را ندارید'
    if kind.startswith('action:'):
        action = kind.split(':', 1)[1]
        if current_user.has_permission(module, action) or current_user.has_permission(module, 'edit'):
            return True, ''
        return False, f'شما اجازه «{action}» در بخش {module} را ندارید'

    if current_user.has_module_access(module):
        return True, ''
    return False, 'شما دسترسی به این بخش را ندارید'


def backfill_role_actions(commit: bool = True) -> int:
    """تکمیل ردیف‌های اکشن (view/create/edit/delete) برای هر «نقش × ماژول».

    چرا؟ تا پیش از این، اکثر نقش‌ها فقط یک ردیف `view` (یا `create`) داشتند؛
    اگر الزام سطح اکشن بدون این تکمیل روشن می‌شد، همان کاربرانی که امروز
    مجازند قفل می‌شدند. این تابع **فقط اضافه می‌کند** و هیچ ردیفی را حذف
    نمی‌کند، پس رفتار عیناً همان چیزی می‌ماند که هست — با این تفاوت که از این
    پس می‌توان در «ویرایش دسترسی نقش» هر اکشن را جدا برداشت و همان لحظه اعمال
    می‌شود. نقش‌های ادمین رد می‌شوند (در نگهبان دور می‌زنند).
    """
    from extensions import db
    from models.user import Permission, Role, RolePermission

    admin_roles = {row.id for row in Role.query.filter_by(is_admin=True).all()}
    pairs = db.session.query(RolePermission, Permission).join(
        Permission, RolePermission.permission_id == Permission.id).all()
    existing = {(rp.role_id, perm.module, perm.action) for rp, perm in pairs}
    modules_by_role: dict[int, set] = {}
    for role_id, module, _action in existing:
        if role_id in admin_roles:
            continue
        modules_by_role.setdefault(role_id, set()).add(module)

    added = 0
    for role_id in sorted(modules_by_role):
        for module in sorted(modules_by_role[role_id]):
            for action in BACKFILL_ACTIONS:
                if (role_id, module, action) in existing:
                    continue
                perm = Permission.query.filter_by(module=module, action=action).first()
                if perm is None:
                    perm = Permission(module=module, action=action,
                                      description=f'{action} {module}')
                    db.session.add(perm)
                    db.session.flush()
                db.session.add(RolePermission(role_id=role_id, permission_id=perm.id))
                existing.add((role_id, module, action))
                added += 1
    if commit:
        db.session.commit()
    return added


def audit_access_policy(app) -> list[str]:
    """مسیرهایی که هیچ policy ندارند — برای اینکه هیچ چیزی بی‌صدا بی‌محافظ نماند."""
    covered = set(MODULE_BY_PREFIX) | set(ADMIN_ONLY_PREFIXES) | set(EXEMPT_PREFIXES)
    unmapped = set()
    for rule in app.url_map.iter_rules():
        segment = str(rule.rule).strip('/').split('/')[0]
        if str(rule.rule).rstrip('/') in {p.rstrip('/') for p in ADMIN_ONLY_PATHS}:
            continue
        if segment not in covered:
            unmapped.add(segment or '/')
    return sorted(unmapped)


def init_access_guard(app) -> None:
    """ثبت نگهبان روی برنامه. باید بعد از init_license و ثبت blueprint صدا زده شود."""

    @app.before_request
    def _role_guard():
        allowed, reason = check_access()
        if allowed:
            return None
        try:
            _log_denial(reason)
        except Exception:
            pass
        return _deny(reason)

    unmapped = audit_access_policy(app)
    if unmapped:
        app.logger.warning('access policy: مسیرهای بدون پوشش نگهبان: %s', ', '.join(unmapped))


def _log_denial(reason: str) -> None:
    from flask import current_app
    from models.user import ActivityLog
    from extensions import db

    current_app.logger.warning('access denied: user=%s %s %s (%s)',
                               getattr(current_user, 'id', '?'), request.method,
                               request.path, reason)
    db.session.add(ActivityLog(
        user_id=current_user.id,
        action='denied',
        module='security',
        description=f'دسترسی رد شد: {request.method} {request.path} — {reason}',
        ip_address=request.remote_addr,
    ))
    db.session.commit()


def require_role(module: str, action: str = 'view'):
    """دکوراتور موضعی برای مسیرهای حساس (کنترل لایه دوم)."""
    from functools import wraps

    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            allowed, reason = _role_check(module, action)
            if allowed:
                return f(*args, **kwargs)
            return _deny(reason)
        return wrapper
    return decorator


def _role_check(module: str, action: str) -> tuple[bool, str]:
    if not current_user.is_authenticated:
        return True, ''
    if current_user.is_admin:
        return True, ''
    if not current_user.role_id:
        return False, 'برای حساب شما هیچ نقشی تعریف نشده است؛ با مدیر کل تماس بگیرید'
    if current_user.has_permission(module, action):
        return True, ''
    # اگر اکشن دقیق وجود نداشت ولی کاربر در آن ماژول دسترسی ویرایش دارد، برای
    # عملیات غیرتخریبی اجازه بده (سازگاری با نقش‌های قدیمی).
    if action in ('edit', 'create') and current_user.has_permission(module, 'edit'):
        return True, ''
    if action == 'view' and current_user.has_module_access(module):
        return True, ''
    return False, f'شما دسترسی «{action}» به بخش {module} را ندارید'
