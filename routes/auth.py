"""Authentication routes"""
from datetime import datetime
from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from extensions import db
from models.user import User, UserSession, ActivityLog
from utils import login_guard

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        remember = request.form.get('remember', False)
        ip = request.remote_addr or 'unknown'
        
        # ── قفل پس از تلاش‌های ناموفق پیاپی ─────────────────────────────
        # پیش‌تر فقط لاگ ثبت می‌شد و brute force آزاد بود (بازبینی امنیت، بند A3)
        seconds_left = login_guard.lock_remaining(username, ip)
        if seconds_left:
            flash(login_guard.lock_message(seconds_left), 'error')
            return render_template('auth/login.html'), 429
        
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            # خودترمیم: در نصب‌های قدیمی ستون `is_active` خالی است و Flask-Login
            # در `login_user()` مقدار falsy را «حساب غیرفعال» می‌شمارد ⇒ ورود
            # بی‌صدا رد می‌شد. پیش از بررسی، آن را به پیش‌فرض («فعال») برمی‌گردانیم.
            if user.is_active is None:
                user.is_active = True
            if user.is_blocked:
                flash('حساب کاربری شما غیرفعال است', 'error')
                return render_template('auth/login.html')
            
            # Record login
            user.last_login = datetime.utcnow()
            user.last_ip = request.remote_addr
            user.login_count = (user.login_count or 0) + 1
            
            # Create session
            session = UserSession(
                user_id=user.id,
                ip_address=request.remote_addr,
                user_agent=request.user_agent.string[:300] if request.user_agent else ''
            )
            db.session.add(session)
            
            # Log activity
            log = ActivityLog(
                user_id=user.id,
                action='login',
                module='system',
                description=f'ورود به سیستم از IP: {request.remote_addr}',
                ip_address=request.remote_addr
            )
            db.session.add(log)
            db.session.commit()
            
            login_guard.reset(username, ip)     # ورود موفق ⇒ شمارش پاک می‌شود
            login_user(user, remember=bool(remember))
            next_page = request.args.get('next')
            if next_page and next_page.startswith('/') and not next_page.startswith('//'):
                return redirect(next_page)
            return redirect(url_for('dashboard.index'))
        else:
            login_guard.register_failure(username, ip)
            if user:
                log = ActivityLog(
                    user_id=user.id,
                    action='failed_login',
                    module='system',
                    description=f'ورود ناموفق از IP: {request.remote_addr}',
                    ip_address=request.remote_addr
                )
                db.session.add(log)
                db.session.commit()
            if login_guard.is_locked(username, ip):
                flash(login_guard.lock_message(login_guard.lock_remaining(username, ip)), 'error')
                try:
                    db.session.add(ActivityLog(
                        user_id=user.id if user else None, action='login_locked', module='security',
                        description=f'قفل موقت حساب پس از {login_guard.MAX_ATTEMPTS} تلاش ناموفق — '
                                    f'IP: {ip}', ip_address=ip))
                    db.session.commit()
                except Exception:
                    db.session.rollback()
                return render_template('auth/login.html'), 429
            flash('نام کاربری یا رمز عبور اشتباه است', 'error')
    
    return render_template('auth/login.html')


@auth_bp.route('/logout')
@login_required
def logout():
    # Log activity
    log = ActivityLog(
        user_id=current_user.id,
        action='logout',
        module='system',
        description='خروج از سیستم',
        ip_address=request.remote_addr
    )
    db.session.add(log)
    
    # Close session
    session = UserSession.query.filter_by(
        user_id=current_user.id, is_active=True
    ).order_by(UserSession.id.desc()).first()
    if session:
        session.logout_at = datetime.utcnow()
        session.is_active = False
    
    db.session.commit()
    logout_user()
    flash('با موفقیت خارج شدید', 'success')
    return redirect(url_for('auth.login'))
