"""Authentication routes"""
from datetime import datetime
from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from extensions import db
from models.user import User, UserSession, ActivityLog

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        remember = request.form.get('remember', False)
        
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            if not user.is_active:
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
            
            login_user(user, remember=bool(remember))
            next_page = request.args.get('next')
            return redirect(next_page or url_for('dashboard.index'))
        else:
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
