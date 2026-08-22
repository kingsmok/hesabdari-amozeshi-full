"""
مسیر ویزارد نصب و تنظیمات دیتابیس
"""
import os
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, abort
from flask_login import current_user, login_required
from extensions import db
from config import load_config, save_config, test_database_connection, create_database_if_not_exists

setup_bp = Blueprint('setup', __name__)


def _users_exist():
    from models.user import User
    return User.query.count() > 0


def _require_fresh_install_or_admin():
    if not _users_exist():
        return None
    if current_user.is_authenticated and current_user.is_admin:
        return None
    abort(403)


@setup_bp.route('/setup', methods=['GET', 'POST'])
def wizard():
    """ویزارد نصب اولیه"""
    from models.user import User
    
    # پس از نصب، فقط مدیر می‌تواند ویزارد را با force باز کند
    if _users_exist() and request.args.get('force') != '1':
        return redirect('/')
    if _users_exist() and request.args.get('force') == '1':
        if not current_user.is_authenticated or not current_user.is_admin:
            abort(403)
    
    config = load_config()
    
    if request.method == 'POST':
        step = request.form.get('step', '1')
        
        if step == '1':
            # ذخیره اطلاعات آموزشگاه
            from models.system import SystemSettings
            settings = SystemSettings.query.first()
            if settings:
                settings.academy_name = request.form.get('academy_name', 'آموزشگاه')
                settings.phone = request.form.get('phone', '')
                settings.address = request.form.get('address', '')
            db.session.commit()
            
            return render_template('setup/wizard.html', step=2, config=config)
        
        elif step == '2':
            # تنظیمات دیتابیس
            db_type = request.form.get('db_type', 'sqlite')
            
            config['database']['type'] = db_type
            
            if db_type == 'mysql':
                config['database']['mysql_host'] = request.form.get('mysql_host', 'localhost')
                config['database']['mysql_port'] = int(request.form.get('mysql_port', 3306))
                config['database']['mysql_user'] = request.form.get('mysql_user', 'root')
                config['database']['mysql_password'] = request.form.get('mysql_password', '')
                config['database']['mysql_database'] = request.form.get('mysql_database', 'academy_manager')
            elif db_type == 'postgresql':
                config['database']['postgresql_host'] = request.form.get('postgresql_host', 'localhost')
                config['database']['postgresql_port'] = int(request.form.get('postgresql_port', 5432))
                config['database']['postgresql_user'] = request.form.get('postgresql_user', 'postgres')
                config['database']['postgresql_password'] = request.form.get('postgresql_password', '')
                config['database']['postgresql_database'] = request.form.get('postgresql_database', 'academy_manager')
            
            save_config(config)
            
            # تست اتصال
            ok, msg = test_database_connection(config)
            if ok:
                # ساخت دیتابیس MySQL اگر نیاز بود
                if db_type == 'mysql':
                    create_database_if_not_exists(config)
                flash(f'اتصال دیتابیس: {msg}', 'success')
            else:
                flash(f'خطا: {msg}', 'error')
            
            return render_template('setup/wizard.html', step=3, config=config)
        
        elif step == '3':
            # تنظیمات مدیر — ایجاد در صورت نبود کاربر
            from models.user import Role
            admin_user = User.query.filter_by(username='admin').first()
            new_password = request.form.get('admin_password', '')
            full_name = request.form.get('admin_name', 'مدیر سیستم')
            admin_role = Role.query.filter_by(is_admin=True).first()
            if not admin_user:
                if not new_password:
                    flash('رمز عبور مدیر الزامی است', 'error')
                    return render_template('setup/wizard.html', step=3, config=config)
                admin_user = User(
                    username='admin',
                    full_name=full_name,
                    is_admin=True,
                    is_active=True,
                    role_id=admin_role.id if admin_role else None,
                )
                admin_user.set_password(new_password)
                db.session.add(admin_user)
                db.session.commit()
                flash('حساب مدیر ایجاد شد', 'success')
            elif new_password:
                admin_user.set_password(new_password)
                admin_user.full_name = full_name
                db.session.commit()
                flash('رمز مدیر تغییر کرد', 'success')
            
            return render_template('setup/wizard.html', step=4, config=config)
    
    return render_template('setup/wizard.html', step=1, config=config)


@setup_bp.route('/setup/test-db', methods=['POST'])
def test_db():
    """API تست اتصال دیتابیس"""
    _require_fresh_install_or_admin()
    config = load_config()
    db_type = request.json.get('type', 'sqlite')
    
    config['database']['type'] = db_type
    if db_type == 'mysql':
        config['database']['mysql_host'] = request.json.get('host', 'localhost')
        config['database']['mysql_port'] = int(request.json.get('port', 3306))
        config['database']['mysql_user'] = request.json.get('user', 'root')
        config['database']['mysql_password'] = request.json.get('password', '')
        config['database']['mysql_database'] = request.json.get('database', 'academy_manager')
    
    ok, msg = test_database_connection(config)
    return jsonify({'ok': ok, 'message': msg})


@setup_bp.route('/setup/database', methods=['GET', 'POST'])
@login_required
def database_settings():
    """تنظیمات دیتابیس"""
    if not current_user.is_admin:
        abort(403)
    config = load_config()
    
    if request.method == 'POST':
        db_type = request.form.get('db_type', 'sqlite')
        config['database']['type'] = db_type
        
        if db_type == 'mysql':
            config['database']['mysql_host'] = request.form.get('mysql_host', 'localhost')
            config['database']['mysql_port'] = int(request.form.get('mysql_port', 3306))
            config['database']['mysql_user'] = request.form.get('mysql_user', 'root')
            config['database']['mysql_password'] = request.form.get('mysql_password', '')
            config['database']['mysql_database'] = request.form.get('mysql_database', 'academy_manager')
        elif db_type == 'postgresql':
            config['database']['postgresql_host'] = request.form.get('postgresql_host', 'localhost')
            config['database']['postgresql_port'] = int(request.form.get('postgresql_port', 5432))
            config['database']['postgresql_user'] = request.form.get('postgresql_user', 'postgres')
            config['database']['postgresql_password'] = request.form.get('postgresql_password', '')
            config['database']['postgresql_database'] = request.form.get('postgresql_database', 'academy_manager')
        else:
            config['database']['sqlite_path'] = request.form.get('sqlite_path', 'instance/academy.db')
        
        save_config(config)
        flash('تنظیمات دیتابیس ذخیره شد. لطفاً برنامه را ری‌استارت کنید.', 'success')
        return redirect(url_for('setup.database_settings'))
    
    return render_template('setup/database.html', config=config)
