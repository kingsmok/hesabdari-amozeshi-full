"""
سیستم کنترل دسترسی واقعی
- مدرس: فقط کلاس‌های خودش
- منشی: ثبت‌نام + هنرجو
- حسابدار: فقط مالی
- مدیر: همه چیز
"""
from functools import wraps
from flask import redirect, url_for, flash, request
from flask_login import current_user


# منوهای سایدبار و دسترسی مورد نیاز
MENU_MAP = {
    # منو: (ماژول, عملیات)
    'dashboard': (None, None),  # همه
    'students': ('students', 'view'),
    'registration': ('registration', 'view'),
    'courses': ('courses', 'view'),
    'classes': ('classes', 'view'),
    'teachers': ('teachers', 'view'),
    'attendance': ('attendance', 'view'),
    'exams': ('exams', 'view'),
    'finance': ('finance', 'view'),
    'accounting': ('accounting', 'view'),
    'payroll': ('payroll', 'view'),
    'tax': ('tax', 'view'),
    'reports': ('reports', 'view'),
    'messaging': ('messaging', 'view'),
    'settings': ('settings', 'view'),
    'certificates': ('certificates', 'view'),
    'analytics': ('reports', 'view'),
    'tickets': ('settings', 'view'),
    'complaints': ('settings', 'view'),
}


def has_perm(module, action='view'):
    """بررسی دسترسی کاربر فعلی"""
    if not current_user.is_authenticated:
        return False
    if current_user.is_admin:
        return True
    return current_user.has_permission(module, action)


def require_permission(module, action='view'):
    """دکوراتور بررسی دسترسی"""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for('auth.login'))
            if not has_perm(module, action):
                flash('شما دسترسی به این بخش را ندارید', 'error')
                return redirect(url_for('dashboard.index'))
            return f(*args, **kwargs)
        return decorated
    return decorator


def get_allowed_menus():
    """دریافت منوهای مجاز برای کاربر فعلی"""
    if not current_user.is_authenticated:
        return []
    
    if current_user.is_admin:
        return list(MENU_MAP.keys())
    
    allowed = []
    for menu_key, (module, action) in MENU_MAP.items():
        if module is None or has_perm(module, action):
            allowed.append(menu_key)
    
    return allowed


def filter_teacher_classes(query, model_class):
    """فیلتر کلاس‌ها برای مدرس — فقط کلاس‌های خودش"""
    if not current_user.is_authenticated:
        return query.filter(False)  # هیچ چیز
    
    if current_user.is_admin:
        return query
    
    # اگر مدرس بود، فقط کلاس‌های خودش
    from models.teacher import Teacher
    teacher = Teacher.query.filter_by(user_id=current_user.id).first()
    if teacher:
        return query.filter_by(teacher_id=teacher.id)
    return query
