"""
دکوراتورهای کنترل دسترسی
"""
from functools import wraps
from flask import redirect, url_for, flash
from flask_login import current_user


def require_permission(module, action='view'):
    """دکوراتور بررسی دسترسی"""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for('auth.login'))
            if not current_user.is_admin:
                if not current_user.has_permission(module, action):
                    flash('شما دسترسی به این بخش را ندارید', 'error')
                    return redirect(url_for('dashboard.index'))
            return f(*args, **kwargs)
        return decorated
    return decorator


def require_admin(f):
    """دکوراتور فقط مدیر کل"""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login'))
        if not current_user.is_admin:
            flash('فقط مدیر کل دسترسی دارد', 'error')
            return redirect(url_for('dashboard.index'))
        return f(*args, **kwargs)
    return decorated
