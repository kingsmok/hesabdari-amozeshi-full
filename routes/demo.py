"""
مسیر ایجاد داده نمونه — برای تست کامل اتصالات
"""
from flask import Blueprint, redirect, url_for, flash
from flask_login import login_required, current_user

demo_bp = Blueprint('demo', __name__)


@demo_bp.route('/demo/create-data', methods=['POST'])
@login_required
def create_demo():
    """ایجاد داده‌های نمونه"""
    if not current_user.is_admin:
        flash('فقط مدیر کل', 'error')
        return redirect(url_for('dashboard.index'))
    
    from utils.demo_data import create_demo_data
    result = create_demo_data()
    flash(result, 'success')
    return redirect(url_for('dashboard.index'))
