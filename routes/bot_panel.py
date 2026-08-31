"""
پنل مدیریت ربات تلگرام و بله
- مدیریت کاربران ربات (ثبت‌نام با شماره تلفن)
- ارسال پیام گروهی
- تنظیمات ربات
- کیبوردهای شیشه‌ای
"""
import json
import time
import requests
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, current_app
from flask_login import login_required, current_user
from license_client import license_required, licensed_section
from extensions import db

bot_panel_bp = Blueprint('bot_panel', __name__)


# ═══════════════════════════════════════════════════════════════
#  داشبورد
# ═══════════════════════════════════════════════════════════════

@bot_panel_bp.route('/bot-panel')
@license_required
@login_required
@licensed_section('bot_panel')
def dashboard():
    """داشبورد پنل ربات"""
    from models.bot import BotUser, BotMessage, BotBroadcast
    from models.system import SystemSettings

    settings = SystemSettings.query.first()

    # آمار کاربران
    total_users = BotUser.query.count()
    verified_users = BotUser.query.filter_by(is_verified=True).count()
    bale_users = BotUser.query.filter_by(provider='bale').count()
    telegram_users = BotUser.query.filter_by(provider='telegram').count()
    blocked_users = BotUser.query.filter_by(is_blocked=True).count()

    # آخرین پیام‌ها
    recent_messages = BotMessage.query.order_by(BotMessage.sent_at.desc()).limit(20).all()

    # آخرین broadcasts
    recent_broadcasts = BotBroadcast.query.order_by(BotBroadcast.created_at.desc()).limit(5).all()

    # وضعیت polling
    from utils.bot_services import bale_polling_manager
    bale_status = bale_polling_manager.status()

    stats = {
        'total_users': total_users,
        'verified_users': verified_users,
        'bale_users': bale_users,
        'telegram_users': telegram_users,
        'blocked_users': blocked_users,
    }

    return render_template('bot_panel/dashboard.html',
                         stats=stats,
                         recent_messages=recent_messages,
                         recent_broadcasts=recent_broadcasts,
                         bale_status=bale_status,
                         settings=settings)


# ═══════════════════════════════════════════════════════════════
#  مدیریت کاربران ربات
# ═══════════════════════════════════════════════════════════════

@bot_panel_bp.route('/bot-panel/users')
@login_required
def users():
    """لیست کاربران ربات"""
    from models.bot import BotUser

    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '').strip()
    provider = request.args.get('provider', '')
    verified = request.args.get('verified', '')
    blocked = request.args.get('blocked', '')

    query = BotUser.query

    if search:
        query = query.filter(
            db.or_(
                BotUser.phone.contains(search),
                BotUser.first_name.contains(search),
                BotUser.last_name.contains(search),
                BotUser.username.contains(search),
                BotUser.chat_id.cast(db.String).contains(search)
            )
        )
    if provider:
        query = query.filter_by(provider=provider)
    if verified == '1':
        query = query.filter_by(is_verified=True)
    elif verified == '0':
        query = query.filter_by(is_verified=False)
    if blocked == '1':
        query = query.filter_by(is_blocked=True)

    users_page = query.order_by(BotUser.joined_at.desc()).paginate(
        page=page, per_page=30, error_out=False
    )

    return render_template('bot_panel/users.html',
                         users=users_page,
                         search=search,
                         provider=provider,
                         verified=verified,
                         blocked=blocked)


@bot_panel_bp.route('/bot-panel/users/<int:id>')
@login_required
def user_detail(id):
    """جزئیات کاربر ربات"""
    from models.bot import BotUser, BotMessage

    bot_user = BotUser.query.get_or_404(id)
    messages = BotMessage.query.filter_by(chat_id=bot_user.chat_id).order_by(
        BotMessage.sent_at.desc()
    ).limit(50).all()

    # اطلاعات هنرجو (اگر مرتبط باشد)
    student = None
    if bot_user.student_id:
        from models.student import Student
        student = Student.query.get(bot_user.student_id)

    return render_template('bot_panel/user_detail.html',
                         bot_user=bot_user,
                         messages=messages,
                         student=student)


@bot_panel_bp.route('/bot-panel/users/<int:id>/toggle-block', methods=['POST'])
@login_required
def toggle_block(id):
    """بلاک/آنبلاک کاربر"""
    from models.bot import BotUser
    bot_user = BotUser.query.get_or_404(id)
    bot_user.is_blocked = not bot_user.is_blocked
    db.session.commit()
    status = 'بلاک' if bot_user.is_blocked else 'رفع بلاک'
    flash(f'کاربر {status} شد', 'success')
    return redirect(url_for('bot_panel.user_detail', id=id))


@bot_panel_bp.route('/bot-panel/users/<int:id>/delete', methods=['POST'])
@login_required
def delete_user(id):
    """حذف کاربر از ربات"""
    from models.bot import BotUser, BotMessage
    bot_user = BotUser.query.get_or_404(id)
    BotMessage.query.filter_by(chat_id=bot_user.chat_id).delete()
    db.session.delete(bot_user)
    db.session.commit()
    flash('کاربر حذف شد', 'success')
    return redirect(url_for('bot_panel.users'))


@bot_panel_bp.route('/bot-panel/users/link-student/<int:id>', methods=['POST'])
@login_required
def link_student(id):
    """اتصال دستی کاربر ربات به هنرجو"""
    from models.bot import BotUser
    bot_user = BotUser.query.get_or_404(id)
    student_id = request.form.get('student_id', type=int)
    if student_id:
        from models.student import Student
        student = Student.query.get(student_id)
        if student:
            bot_user.student_id = student.id
            bot_user.is_verified = True
            db.session.commit()
            flash(f'به هنرجوی "{student.full_name}" متصل شد', 'success')
        else:
            flash('هنرجو یافت نشد', 'danger')
    return redirect(url_for('bot_panel.user_detail', id=id))


# ═══════════════════════════════════════════════════════════════
#  ارسال پیام گروهی (Broadcast)
# ═══════════════════════════════════════════════════════════════

@bot_panel_bp.route('/bot-panel/broadcast', methods=['GET', 'POST'])
@login_required
def broadcast():
    """ارسال پیام گروهی به کاربران ربات"""
    from models.bot import BotUser, BotBroadcast

    if request.method == 'POST':
        message_text = request.form.get('message_text', '').strip()
        target_type = request.form.get('target_type', 'all')
        provider = request.form.get('provider', 'both')
        title = request.form.get('title', '').strip() or 'پیام گروهی'

        if not message_text:
            flash('متن پیام را وارد کنید', 'danger')
            return redirect(url_for('bot_panel.broadcast'))

        # ساخت broadcast record
        broadcast_rec = BotBroadcast(
            title=title,
            message_text=message_text,
            target_type=target_type,
            provider=provider,
            status='sending',
            created_by=current_user.id
        )
        db.session.add(broadcast_rec)
        db.session.flush()

        # ساخت query کاربران هدف
        query = BotUser.query.filter_by(is_blocked=False)
        if target_type == 'verified':
            query = query.filter_by(is_verified=True)
        elif target_type == 'students':
            query = query.filter(BotUser.student_id.isnot(None))
        if provider != 'both':
            query = query.filter_by(provider=provider)

        recipients = query.all()
        broadcast_rec.total_recipients = len(recipients)
        db.session.flush()

        sent_count = 0
        failed_count = 0
        errors = []

        from models.system import SystemSettings
        settings = SystemSettings.query.first()

        for bot_user in recipients:
            token = None
            prov = bot_user.provider
            if prov == 'bale' and settings and settings.bale_bot_token:
                token = settings.bale_bot_token
            elif prov == 'telegram' and settings and settings.telegram_bot_token:
                token = settings.telegram_bot_token
            elif provider == 'bale' and settings and settings.bale_bot_token:
                token = settings.bale_bot_token
            elif provider == 'telegram' and settings and settings.telegram_bot_token:
                token = settings.telegram_bot_token

            if not token:
                failed_count += 1
                continue

            base_url = 'https://tapi.bale.ai' if prov == 'bale' else 'https://api.telegram.org'
            try:
                resp = requests.post(
                    f'{base_url}/bot{token}/sendMessage',
                    json={'chat_id': bot_user.chat_id, 'text': message_text},
                    timeout=15
                )
                result = resp.json()
                if result.get('ok'):
                    sent_count += 1
                else:
                    failed_count += 1
                    errors.append(f"chat_id={bot_user.chat_id}: {result.get('description', 'نامشخص')}")
            except Exception as e:
                failed_count += 1
                errors.append(f"chat_id={bot_user.chat_id}: {str(e)[:100]}")

            # محدودیت rate
            time.sleep(0.05)

        broadcast_rec.sent_count = sent_count
        broadcast_rec.failed_count = failed_count
        broadcast_rec.status = 'completed'
        broadcast_rec.completed_at = datetime.utcnow()
        db.session.commit()

        if errors:
            flash(f'ارسال شد: {sent_count} | ناموفق: {failed_count} | خطاها: {" | ".join(errors[:3])}', 'warning')
        else:
            flash(f'پیام گروهی ارسال شد: {sent_count} موفق', 'success')
        return redirect(url_for('bot_panel.broadcast_history'))

    # GET: نمایش فرم
    from models.bot import BotUser
    total = BotUser.query.filter_by(is_blocked=False).count()
    verified = BotUser.query.filter_by(is_verified=True, is_blocked=False).count()
    students = BotUser.query.filter(BotUser.student_id.isnot(None), BotUser.is_blocked == False).count()

    return render_template('bot_panel/broadcast.html',
                         total=total,
                         verified=verified,
                         students=students)


@bot_panel_bp.route('/bot-panel/broadcast/history')
@login_required
def broadcast_history():
    """تاریخچه پیام‌های گروهی"""
    from models.bot import BotBroadcast
    page = request.args.get('page', 1, type=int)
    broadcasts = BotBroadcast.query.order_by(BotBroadcast.created_at.desc()).paginate(
        page=page, per_page=20, error_out=False
    )
    return render_template('bot_panel/broadcast_history.html', broadcasts=broadcasts)


# ═══════════════════════════════════════════════════════════════
#  تنظیمات ربات
# ═══════════════════════════════════════════════════════════════

@bot_panel_bp.route('/bot-panel/settings', methods=['GET', 'POST'])
@login_required
def settings():
    """تنظیمات ربات"""
    from models.system import SystemSettings
    settings_obj = SystemSettings.query.first()

    if request.method == 'POST':
        # تنظیمات پیام
        settings_obj.welcome_message = request.form.get('welcome_message', '')
        # phone_required — stored in welcome_message prefix
        # auto_reply — future feature

        # توکن‌ها
        if request.form.get('bale_bot_token'):
            settings_obj.bale_bot_token = request.form.get('bale_bot_token', '').strip()
        if request.form.get('telegram_bot_token'):
            settings_obj.telegram_bot_token = request.form.get('telegram_bot_token', '').strip()

        db.session.commit()
        flash('تنظیمات ذخیره شد', 'success')
        return redirect(url_for('bot_panel.settings'))

    return render_template('bot_panel/settings.html', settings=settings_obj)


# ═══════════════════════════════════════════════════════════════
#  مدیریت کیبوردها
# ═══════════════════════════════════════════════════════════════

@bot_panel_bp.route('/bot-panel/keyboards')
@login_required
def keyboards():
    """لیست کیبوردها"""
    from models.bot import BotKeyboard
    keyboards = BotKeyboard.query.order_by(BotKeyboard.created_at.desc()).all()
    return render_template('bot_panel/keyboards.html', keyboards=keyboards)


@bot_panel_bp.route('/bot-panel/keyboards/add', methods=['GET', 'POST'])
@login_required
def keyboard_add():
    """ایجاد کیبورد جدید"""
    from models.bot import BotKeyboard

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        if not name:
            flash('نام کیبورد الزامی است', 'danger')
            return render_template('bot_panel/keyboard_add.html'), 400

        description = request.form.get('description', '').strip()
        keyboard_type = request.form.get('keyboard_type', 'reply')
        provider = request.form.get('provider', 'both')

        # دریافت دکمه‌ها
        rows_data = request.form.get('buttons_data', '[]')
        try:
            buttons = json.loads(rows_data)
        except json.JSONDecodeError:
            buttons = []

        kb = BotKeyboard(
            name=name,
            description=description,
            keyboard_type=keyboard_type,
            buttons=json.dumps(buttons, ensure_ascii=False),
            provider=provider,
            is_active=True
        )
        try:
            db.session.add(kb)
            db.session.commit()
            flash(f'کیبورد "{name}" ایجاد شد', 'success')
            return redirect(url_for('bot_panel.keyboards'))
        except Exception:
            db.session.rollback()
            flash('خطا در ثبت کیبورد (احتمالاً نام تکراری است)', 'danger')
            return render_template('bot_panel/keyboard_add.html'), 400

    return render_template('bot_panel/keyboard_add.html')


@bot_panel_bp.route('/bot-panel/keyboards/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def keyboard_edit(id):
    """ویرایش کیبورد"""
    from models.bot import BotKeyboard
    kb = BotKeyboard.query.get_or_404(id)

    if request.method == 'POST':
        kb.name = request.form.get('name', '').strip()
        kb.description = request.form.get('description', '').strip()
        kb.keyboard_type = request.form.get('keyboard_type', 'reply')
        kb.provider = request.form.get('provider', 'both')
        kb.is_active = 'is_active' in request.form

        rows_data = request.form.get('buttons_data', '[]')
        try:
            kb.buttons = json.dumps(json.loads(rows_data), ensure_ascii=False)
        except json.JSONDecodeError:
            pass

        db.session.commit()
        flash('کیبورد بروزرسانی شد', 'success')
        return redirect(url_for('bot_panel.keyboards'))

    try:
        buttons = json.loads(kb.buttons or '[]')
    except json.JSONDecodeError:
        buttons = []

    return render_template('bot_panel/keyboard_edit.html', kb=kb, buttons=buttons)


@bot_panel_bp.route('/bot-panel/keyboards/<int:id>/delete', methods=['POST'])
@login_required
def keyboard_delete(id):
    """حذف کیبورد"""
    from models.bot import BotKeyboard
    kb = BotKeyboard.query.get_or_404(id)
    db.session.delete(kb)
    db.session.commit()
    flash('کیبورد حذف شد', 'success')
    return redirect(url_for('bot_panel.keyboards'))


# ═══════════════════════════════════════════════════════════════
#  ارسال تست به یک کاربر
# ═══════════════════════════════════════════════════════════════

@bot_panel_bp.route('/bot-panel/send-test', methods=['POST'])
@login_required
def send_test():
    """ارسال پیام تست به یک کاربر"""
    from models.bot import BotUser
    from models.system import SystemSettings

    chat_id = request.form.get('chat_id', '').strip()
    if not chat_id:
        flash('شناسه چت الزامی است', 'danger')
        return redirect(url_for('bot_panel.dashboard'))

    message = request.form.get('message', 'تست از پنل مدیریت ✓').strip()
    provider = request.form.get('provider', 'bale')

    settings_obj = SystemSettings.query.first()
    token = None
    if provider == 'bale' and settings_obj:
        token = settings_obj.bale_bot_token
    elif provider == 'telegram' and settings_obj:
        token = settings_obj.telegram_bot_token

    if not token:
        flash('توکن ربات تنظیم نشده', 'danger')
        return redirect(url_for('bot_panel.dashboard'))

    base_url = 'https://tapi.bale.ai' if provider == 'bale' else 'https://api.telegram.org'
    try:
        resp = requests.post(
            f'{base_url}/bot{token}/sendMessage',
            json={'chat_id': int(chat_id), 'text': message},
            timeout=15
        )
        result = resp.json()
        if result.get('ok'):
            flash('پیام با موفقیت ارسال شد ✓', 'success')
        else:
            flash(f'خطا: {result.get("description", "نامشخص")}', 'danger')
    except Exception as e:
        flash(f'خطا: {str(e)}', 'danger')

    return redirect(url_for('bot_panel.dashboard'))


# ═══════════════════════════════════════════════════════════════
#  آمار و گزارش
# ═══════════════════════════════════════════════════════════════

@bot_panel_bp.route('/bot-panel/stats')
@login_required
def stats():
    """آمار کامل ربات"""
    from models.bot import BotUser, BotMessage, BotBroadcast
    from models.system import SystemSettings

    # آمار روزانه (۷ روز اخیر)
    from datetime import timedelta
    seven_days_ago = datetime.utcnow() - timedelta(days=7)

    daily_users = db.session.query(
        db.func.date(BotUser.joined_at).label('date'),
        db.func.count(BotUser.id).label('count')
    ).filter(BotUser.joined_at >= seven_days_ago).group_by(
        db.func.date(BotUser.joined_at)
    ).all()

    daily_messages = db.session.query(
        db.func.date(BotMessage.sent_at).label('date'),
        db.func.count(BotMessage.id).label('count')
    ).filter(BotMessage.sent_at >= seven_days_ago).group_by(
        db.func.date(BotMessage.sent_at)
    ).all()

    # کل آمار
    total_stats = {
        'total_users': BotUser.query.count(),
        'verified_users': BotUser.query.filter_by(is_verified=True).count(),
        'total_messages': BotMessage.query.count(),
        'total_broadcasts': BotBroadcast.query.count(),
        'total_messages_sent': BotBroadcast.query.with_entities(
            db.func.sum(BotBroadcast.sent_count)
        ).scalar() or 0,
    }

    return render_template('bot_panel/stats.html',
                         daily_users=daily_users,
                         daily_messages=daily_messages,
                         total_stats=total_stats)


# ═══════════════════════════════════════════════════════════════
#  API endpoints
# ═══════════════════════════════════════════════════════════════

@bot_panel_bp.route('/bot-panel/api/users')
@login_required
def api_users():
    """API لیست کاربران (برای AJAX)"""
    from models.bot import BotUser
    users = BotUser.query.order_by(BotUser.joined_at.desc()).limit(100).all()
    return jsonify([{
        'id': u.id,
        'chat_id': u.chat_id,
        'phone': u.phone,
        'name': u.full_name,
        'verified': u.is_verified,
        'blocked': u.is_blocked,
        'provider': u.provider,
        'joined': u.joined_at.isoformat() if u.joined_at else None,
    } for u in users])


@bot_panel_bp.route('/bot-panel/api/stats')
@login_required
def api_stats():
    """API آمار لحظه‌ای"""
    from models.bot import BotUser, BotMessage
    from utils.bot_services import bale_polling_manager

    return jsonify({
        'total_users': BotUser.query.count(),
        'verified_users': BotUser.query.filter_by(is_verified=True).count(),
        'bale_status': bale_polling_manager.status(),
    })
