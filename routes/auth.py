"""Authentication routes"""
from datetime import datetime
from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from extensions import db
from models.user import User, UserSession
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
            
            # Log activity — نقطهٔ مشترک لاگ (DRY)
            from utils.activity_log import log_activity
            log_activity('login', f'ورود به سیستم از IP: {request.remote_addr}',
                         module='system', user_id=user.id,
                         ip_address=request.remote_addr)
            db.session.commit()
            
            login_guard.reset(username, ip)     # ورود موفق ⇒ شمارش پاک می‌شود
            login_user(user, remember=bool(remember))
            # هشدار رمز پیش‌فرض: اگر هنوز با مشخصات کارخانه وارد می‌شود، در
            # داشبورد یادآوری می‌شود تا حتماً عوضش کند (امنیت نصب تازه).
            try:
                from utils.constants import is_default_admin_password
                if is_default_admin_password(username, password):
                    flash('شما با رمز پیش‌فرض وارد شده‌اید؛ حتماً از بخش کاربران، '
                          'رمز عبور را تغییر دهید', 'warning')
            except Exception:
                pass
            next_page = request.args.get('next')
            if next_page and next_page.startswith('/') and not next_page.startswith('//'):
                return redirect(next_page)
            return redirect(url_for('dashboard.index'))
        else:
            login_guard.register_failure(username, ip)
            if user:
                from utils.activity_log import log_activity
                log_activity('failed_login', f'ورود ناموفق از IP: {request.remote_addr}',
                             module='system', user_id=user.id,
                             ip_address=request.remote_addr)
                db.session.commit()
            if login_guard.is_locked(username, ip):
                flash(login_guard.lock_message(login_guard.lock_remaining(username, ip)), 'error')
                # رویداد قفل حتی برای «نام کاربری ناشناس» هم ثبت می‌شود
                # (نقطهٔ مشترک لاگ: کاربر ناشناس → user_id=None)
                from utils.activity_log import log_activity
                log_activity(
                    'login_locked',
                    f'قفل موقت حساب پس از {login_guard.MAX_ATTEMPTS} تلاش ناموفق — IP: {ip}',
                    module='security', user_id=user.id if user else None,
                    ip_address=ip, commit=True)
                return render_template('auth/login.html'), 429
            flash('نام کاربری یا رمز عبور اشتباه است', 'error')
    
    return render_template('auth/login.html')


@auth_bp.route('/logout')
@login_required
def logout():
    # Log activity — نقطهٔ مشترک لاگ (DRY)
    from utils.activity_log import log_activity
    log_activity('logout', 'خروج از سیستم', module='system')
    
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


@auth_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    """پروفایل من: مشاهده مشخصات + ویرایش + تغییر رمز عبور خودم.

    برای همهٔ نقش‌ها آزاد است (گارد دسترسی مسیر profile را مقید نکرده و
    در UNLOCKED_ENDPOINTS لایسنس هم ثبت شده) تا هر کاربری — از جمله مدیری
    که با رمز پیش‌فرض وارد شده — بتواند رمزش را عوض کند.
    """
    user = current_user
    if request.method == 'POST':
        user.full_name = request.form.get('full_name', user.full_name).strip() or user.full_name
        user.email = request.form.get('email', '') or None
        user.phone = request.form.get('phone', '') or None

        current = request.form.get('current_password', '')
        new_pass = request.form.get('new_password', '')
        confirm = request.form.get('confirm_password', '')
        if new_pass or confirm:
            if not user.check_password(current):
                flash('رمز فعلی اشتباه است', 'error')
                return render_template('auth/profile.html')
            if len(new_pass) < 8:
                flash('رمز جدید باید حداقل ۸ نویسه باشد', 'error')
                return render_template('auth/profile.html')
            if new_pass != confirm:
                flash('تکرار رمز جدید با آن مطابقت ندارد', 'error')
                return render_template('auth/profile.html')
            user.set_password(new_pass)
            from utils.activity_log import log_activity
            log_activity('change_password', 'تغییر رمز عبور توسط خود کاربر',
                         module='system', user_id=user.id,
                         ip_address=request.remote_addr)
            db.session.commit()
            flash('مشخصات و رمز عبور با موفقیت به‌روز شد', 'success')
            return redirect(url_for('auth.profile'))
        db.session.commit()
        flash('مشخصات با موفقیت ذخیره شد', 'success')
        return redirect(url_for('auth.profile'))
    return render_template('auth/profile.html')
