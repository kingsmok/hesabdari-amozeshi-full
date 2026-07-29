"""
پنل تنظیمات جامع — اتصالات واقعی تلگرام، بله، فراز اس‌ام‌اس
"""
import os, json, requests
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, current_app
from flask_login import login_required, current_user
from extensions import db

settings_panel_bp = Blueprint('settings_panel', __name__)


# ═══════════════════════════════════════════════════════════════
#  صفحه اصلی پنل تنظیمات
# ═══════════════════════════════════════════════════════════════

@settings_panel_bp.route('/control-panel')
@login_required
def control_panel():
    """پنل مدیریت اتصالات"""
    from models.system import SystemSettings
    settings = SystemSettings.query.first()
    from utils.bot_services import bale_polling_manager
    bale_status = bale_polling_manager.status()
    
    # وضعیت «تنظیم‌شده» از وضعیت اجرایی جداست تا اتصال کاذب نمایش داده نشود.
    connections = {
        'telegram': {
            'name': 'ربات تلگرام',
            'icon': 'bi-telegram',
            'configured': bool(settings and settings.telegram_bot_token),
            'status': 'configured' if settings and settings.telegram_bot_token else 'not_configured',
            'label': 'تنظیم‌شده' if settings and settings.telegram_bot_token else 'تنظیم نشده',
        },
        'bale': {
            'name': 'ربات بله',
            'icon': 'bi-chat-dots',
            'configured': bool(settings and settings.bale_bot_token),
            'status': 'running' if bale_status['running'] else 'stopped',
            'label': 'در حال دریافت' if bale_status['running'] else ('متوقف' if settings and settings.bale_bot_token else 'تنظیم نشده'),
        },
        'farazsms': {
            'name': 'پنل پیامکی فراز',
            'icon': 'bi-phone',
            'configured': bool(settings and settings.farazsms_api_key),
            'status': 'configured' if settings and settings.farazsms_api_key else 'not_configured',
            'label': 'تنظیم‌شده' if settings and settings.farazsms_api_key else 'تنظیم نشده',
        },
    }
    
    return render_template('settings_panel/main.html', settings=settings, connections=connections)


# ═══════════════════════════════════════════════════════════════
#  تنظیمات تلگرام — واقعی
# ═══════════════════════════════════════════════════════════════

@settings_panel_bp.route('/telegram', methods=['GET', 'POST'])
@login_required
def telegram_config():
    """تنظیمات کامل ربات تلگرام"""
    from models.system import SystemSettings
    settings = SystemSettings.query.first()
    
    if request.method == 'POST':
        settings.telegram_bot_token = request.form.get('telegram_bot_token', '').strip()
        settings.telegram_webhook_url = request.form.get('telegram_webhook_url', '').strip()
        db.session.commit()
        
        # تست اتصال به تلگرام
        if settings.telegram_bot_token:
            try:
                resp = requests.get(
                    f'https://api.telegram.org/bot{settings.telegram_bot_token}/getMe',
                    timeout=10
                ).json()
                if resp.get('ok'):
                    bot_info = resp.get('result', {})
                    flash(f'اتصال موفق! نام بات: @{bot_info.get("username", "?")}', 'success')
                else:
                    flash(f'خطا در اتصال: {resp.get("description", "نامشخص")}', 'error')
            except Exception as e:
                flash(f'خطا در اتصال به تلگرام: {str(e)}', 'error')
        
        return redirect(url_for('settings_panel.telegram_config'))
    
    # دریافت اطلاعات بات فعلی
    bot_info = None
    webhook_info = None
    
    if settings and settings.telegram_bot_token:
        try:
            resp = requests.get(
                f'https://api.telegram.org/bot{settings.telegram_bot_token}/getMe',
                timeout=10
            ).json()
            if resp.get('ok'):
                bot_info = resp.get('result', {})
        except:
            pass
        
        try:
            resp = requests.get(
                f'https://api.telegram.org/bot{settings.telegram_bot_token}/getWebhookInfo',
                timeout=10
            ).json()
            if resp.get('ok'):
                webhook_info = resp.get('result', {})
        except:
            pass
    
    return render_template('settings_panel/telegram.html', 
                         settings=settings, bot_info=bot_info, webhook_info=webhook_info)


@settings_panel_bp.route('/telegram/set-webhook', methods=['POST'])
@login_required
def set_telegram_webhook():
    """تنظیم وب‌هوک تلگرام"""
    from models.system import SystemSettings
    settings = SystemSettings.query.first()
    
    if not settings or not settings.telegram_bot_token:
        flash('ابتدا توکن بات را وارد کنید', 'error')
        return redirect(url_for('settings_panel.telegram_config'))
    
    webhook_url = request.form.get('webhook_url', '').strip()
    if not webhook_url:
        flash('آدرس وب‌هوک را وارد کنید', 'error')
        return redirect(url_for('settings_panel.telegram_config'))
    
    try:
        # حذف وب‌هوک قبلی
        requests.get(f'https://api.telegram.org/bot{settings.telegram_bot_token}/deleteWebhook', timeout=10)
        
        # تنظیم وب‌هوک جدید
        result = requests.get(
            f'https://api.telegram.org/bot{settings.telegram_bot_token}/setWebhook',
            params={'url': webhook_url, 'allowed_updates': json.dumps(['message'])},
            timeout=10
        ).json()
        
        if result.get('ok'):
            settings.telegram_webhook_url = webhook_url
            db.session.commit()
            flash('وب‌هوک با موفقیت تنظیم شد ✓', 'success')
        else:
            flash(f'خطا: {result.get("description", "نامشخص")}', 'error')
    except Exception as e:
        flash(f'خطا: {str(e)}', 'error')
    
    return redirect(url_for('settings_panel.telegram_config'))


@settings_panel_bp.route('/telegram/test-message', methods=['POST'])
@login_required
def test_telegram_message():
    """تست ارسال پیام تلگرام"""
    from models.system import SystemSettings
    settings = SystemSettings.query.first()
    
    if not settings or not settings.telegram_bot_token:
        flash('توکن بات تنظیم نشده', 'error')
        return redirect(url_for('settings_panel.telegram_config'))
    
    chat_id = request.form.get('chat_id', '').strip()
    message = request.form.get('message', 'تست اتصال از سیستم مدیریت آموزشگاه ✓')
    
    if not chat_id:
        flash('شناسه چت را وارد کنید', 'error')
        return redirect(url_for('settings_panel.telegram_config'))
    
    try:
        result = requests.post(
            f'https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage',
            json={'chat_id': chat_id, 'text': message},
            timeout=10
        ).json()
        
        if result.get('ok'):
            flash('پیام با موفقیت ارسال شد ✓', 'success')
        else:
            flash(f'خطا: {result.get("description", "نامشخص")}', 'error')
    except Exception as e:
        flash(f'خطا: {str(e)}', 'error')
    
    return redirect(url_for('settings_panel.telegram_config'))


# ═══════════════════════════════════════════════════════════════
#  تنظیمات بله — واقعی
# ═══════════════════════════════════════════════════════════════

@settings_panel_bp.route('/bale', methods=['GET', 'POST'])
@login_required
def bale_config():
    """تنظیمات ربات بله با Long Polling و بدون وب‌هوک."""
    from models.system import SystemSettings
    from utils.bot_services import bale_polling_manager

    settings = SystemSettings.query.first()
    if request.method == 'POST':
        token = request.form.get('bale_bot_token', '').strip()
        settings.bale_bot_token = token
        settings.bale_webhook_url = None
        db.session.commit()

        if token:
            try:
                response = requests.get(f'https://tapi.bale.ai/bot{token}/getMe', timeout=10)
                result = response.json()
                if result.get('ok'):
                    bot_info = result.get('result', {})
                    started, message = bale_polling_manager.start(current_app._get_current_object(), token)
                    flash(f'اتصال موفق به @{bot_info.get("username", "?")} — {message}', 'success' if started else 'warning')
                else:
                    flash(f'توکن ذخیره شد اما اتصال ناموفق بود: {result.get("description", "نامشخص")}', 'danger')
            except (requests.RequestException, ValueError) as exc:
                flash(f'توکن ذخیره شد؛ ارتباط با بله برقرار نشد: {exc}', 'warning')
        else:
            bale_polling_manager.stop()
            flash('توکن بله پاک و دریافت خودکار متوقف شد', 'success')
        return redirect(url_for('settings_panel.bale_config'))

    bot_info = None
    if settings and settings.bale_bot_token:
        try:
            result = requests.get(
                f'https://tapi.bale.ai/bot{settings.bale_bot_token}/getMe', timeout=10
            ).json()
            if result.get('ok'):
                bot_info = result.get('result', {})
        except (requests.RequestException, ValueError):
            pass

    return render_template(
        'settings_panel/bale.html',
        settings=settings,
        bot_info=bot_info,
        polling_status=bale_polling_manager.status()
    )


@settings_panel_bp.route('/bale/set-webhook', methods=['POST'])
@login_required
def set_bale_webhook():
    """مسیر سازگاری نسخه قبل: وب‌هوک را حذف و Long Polling را فعال می‌کند."""
    return start_bale_polling()


@settings_panel_bp.route('/bale/polling/start', methods=['POST'])
@login_required
def start_bale_polling():
    from models.system import SystemSettings
    from utils.bot_services import bale_polling_manager

    settings = SystemSettings.query.first()
    if not settings or not settings.bale_bot_token:
        flash('ابتدا توکن ربات بله را وارد کنید', 'danger')
        return redirect(url_for('settings_panel.bale_config'))

    try:
        requests.post(
            f'https://tapi.bale.ai/bot{settings.bale_bot_token}/deleteWebhook', timeout=10
        )
    except requests.RequestException:
        pass
    settings.bale_webhook_url = None
    db.session.commit()

    started, message = bale_polling_manager.start(
        current_app._get_current_object(), settings.bale_bot_token
    )
    flash(message, 'success' if started else 'danger')
    return redirect(url_for('settings_panel.bale_config'))


@settings_panel_bp.route('/bale/polling/stop', methods=['POST'])
@login_required
def stop_bale_polling():
    from utils.bot_services import bale_polling_manager

    bale_polling_manager.stop()
    flash('دریافت خودکار پیام‌های بله متوقف شد', 'success')
    return redirect(url_for('settings_panel.bale_config'))


@settings_panel_bp.route('/bale/test-message', methods=['POST'])
@login_required
def test_bale_message():
    """تست ارسال پیام بله"""
    from models.system import SystemSettings
    settings = SystemSettings.query.first()
    
    if not settings or not settings.bale_bot_token:
        flash('توکن بات تنظیم نشده', 'error')
        return redirect(url_for('settings_panel.bale_config'))
    
    chat_id = request.form.get('chat_id', '').strip()
    message = request.form.get('message', 'تست اتصال از سیستم مدیریت آموزشگاه ✓')
    
    if not chat_id:
        flash('شناسه چت را وارد کنید', 'error')
        return redirect(url_for('settings_panel.bale_config'))
    
    try:
        result = requests.post(
            f'https://tapi.bale.ai/bot{settings.bale_bot_token}/sendMessage',
            json={'chat_id': chat_id, 'text': message},
            timeout=10
        ).json()
        
        if result.get('ok'):
            flash('پیام با موفقیت ارسال شد ✓', 'success')
        else:
            flash(f'خطا: {result.get("description", "نامشخص")}', 'error')
    except Exception as e:
        flash(f'خطا: {str(e)}', 'error')
    
    return redirect(url_for('settings_panel.bale_config'))


# ═══════════════════════════════════════════════════════════════
#  تنظیمات فراز اس‌ام‌اس — واقعی
# ═══════════════════════════════════════════════════════════════

@settings_panel_bp.route('/farazsms', methods=['GET', 'POST'])
@login_required
def farazsms_config():
    """تنظیم پنل فراز با API رسمی و تست اعتبار بدون ارسال پیامک."""
    from models.system import SystemSettings
    from utils.sms_service import check_farazsms_connection

    settings = SystemSettings.query.first()
    if request.method == 'POST':
        settings.farazsms_api_key = request.form.get('farazsms_api_key', '').strip()
        settings.farazsms_sender = request.form.get('farazsms_sender', '').strip()
        settings.farazsms_pattern_code = request.form.get('farazsms_pattern_code', '').strip()
        # تنظیمات عمومی قدیمی نیز با پنل فعال همگام می‌شوند.
        settings.sms_provider = 'farazsms'
        settings.sms_api_key = settings.farazsms_api_key
        settings.sms_sender = settings.farazsms_sender
        db.session.commit()

        result = check_farazsms_connection(settings.farazsms_api_key)
        if result.get('ok'):
            balance = result.get('balance_amount')
            suffix = f' — اعتبار: {balance:,.0f} ریال' if isinstance(balance, (int, float)) else ''
            flash(f'اتصال پنل پیامکی با موفقیت تأیید شد{suffix}', 'success')
        else:
            flash(f'تنظیمات ذخیره شد اما اتصال تأیید نشد: {result.get("error")}', 'danger')
        return redirect(url_for('settings_panel.farazsms_config'))

    return render_template('settings_panel/farazsms.html', settings=settings)


@settings_panel_bp.route('/farazsms/check', methods=['POST'])
@login_required
def check_farazsms():
    from models.system import SystemSettings
    from utils.sms_service import check_farazsms_connection

    settings = SystemSettings.query.first()
    result = check_farazsms_connection(settings.farazsms_api_key if settings else '')
    if result.get('ok'):
        flash(f'اتصال برقرار است — تعداد پیامک قابل ارسال: {result.get("balance_count", "نامشخص")}', 'success')
    else:
        flash(result.get('error') or 'اتصال پنل ناموفق بود', 'danger')
    return redirect(url_for('settings_panel.farazsms_config'))


@settings_panel_bp.route('/farazsms/test', methods=['POST'])
@login_required
def test_farazsms():
    """تست ارسال پیامک فراز"""
    from models.system import SystemSettings
    settings = SystemSettings.query.first()
    
    if not settings or not settings.farazsms_api_key:
        flash('API Key تنظیم نشده', 'error')
        return redirect(url_for('settings_panel.farazsms_config'))
    
    phone = request.form.get('phone', '').strip()
    message = request.form.get('message', 'تست اتصال از سیستم مدیریت آموزشگاه')
    
    if not phone:
        flash('شماره موبایل را وارد کنید', 'error')
        return redirect(url_for('settings_panel.farazsms_config'))
    
    from utils.sms_service import send_farazsms
    result = send_farazsms(settings, phone, message)
    if result.get('ok'):
        flash(f'پیامک آزمایشی ارسال شد — شناسه: {result.get("provider_id", "نامشخص")}', 'success')
    else:
        flash(result.get('error') or 'ارسال پیامک ناموفق بود', 'danger')
    
    return redirect(url_for('settings_panel.farazsms_config'))


@settings_panel_bp.route('/farazsms/send-bulk', methods=['POST'])
@login_required
def farazsms_bulk():
    """ارسال گروهی از فراز"""
    from models.system import SystemSettings, Message
    from models.student import Student
    from models.registration import Registration
    
    settings = SystemSettings.query.first()
    if not settings or not settings.farazsms_api_key:
        flash('API Key تنظیم نشده', 'error')
        return redirect(url_for('settings_panel.farazsms_config'))
    
    target = request.form.get('target')
    message_text = request.form.get('message_text', '').strip()
    send_type = request.form.get('send_type', 'manual')
    
    if not message_text:
        flash('متن پیام را وارد کنید', 'error')
        return redirect(url_for('settings_panel.farazsms_config'))
    
    phones = []
    
    if target == 'all_students':
        students = Student.query.filter_by(status='active').all()
        phones = [(s.mobile, s.full_name, s.id) for s in students if s.mobile]
    
    elif target == 'debtors':
        regs = Registration.query.filter(
            Registration.remaining_amount > 0,
            Registration.status == 'active'
        ).all()
        seen = set()
        for r in regs:
            if r.student and r.student.mobile and r.student_id not in seen:
                phones.append((r.student.mobile, r.student.full_name, r.student_id))
                seen.add(r.student_id)
    
    elif target == 'specific':
        phone = request.form.get('phone', '').strip()
        if phone:
            phones = [(phone, phone, None)]
    
    sent_count = 0
    failed_count = 0
    
    for phone, name, student_id in phones:
        personalized = message_text.replace('{نام}', name)
        
        from utils.sms_service import send_farazsms
        result = send_farazsms(settings, phone, personalized)
        success = result.get('ok', False)
        
        log = Message(
            recipient_type='student',
            recipient_id=student_id,
            phone=phone,
            message_text=personalized,
            send_type=send_type,
            status='sent' if success else 'failed',
            sent_at=datetime.utcnow() if success else None,
            error_message=result.get('error') if not success else None,
            created_by=current_user.id
        )
        db.session.add(log)
        
        if success:
            sent_count += 1
        else:
            failed_count += 1
    
    db.session.commit()
    category = 'success' if sent_count else 'danger'
    flash(f'{sent_count} پیامک ارسال شد' + (f' | {failed_count} ناموفق' if failed_count else ''), category)
    return redirect(url_for('settings_panel.farazsms_config'))


@settings_panel_bp.route('/farazsms/send-installment-reminders', methods=['POST'])
@login_required
def farazsms_installment_reminders():
    """ارسال یادآوری اقساط از فراز"""
    from models.system import SystemSettings, Message
    from models.registration import Installment
    
    settings = SystemSettings.query.first()
    if not settings or not settings.farazsms_api_key:
        flash('API Key تنظیم نشده', 'error')
        return redirect(url_for('settings_panel.farazsms_config'))
    
    from datetime import date, timedelta
    today = date.today()
    upcoming = today + timedelta(days=3)
    
    installments = Installment.query.filter(
        Installment.due_date.between(today, upcoming),
        Installment.status.in_(['pending', 'partial']),
        Installment.reminder_sent == False
    ).all()
    
    sent = 0
    for inst in installments:
        reg = inst.registration
        if reg and reg.student and reg.student.mobile:
            msg_text = (
                f"یادآوری قسط:\n"
                f"هنرجوی گرامی {reg.student.full_name}\n"
                f"قسط شماره {inst.installment_number} به مبلغ {inst.amount:,.0f} تومان\n"
                f"تاریخ سررسید: {inst.due_date}\n"
                f"لطفاً قبل از سررسید اقدام فرمایید."
            )
            
            from utils.sms_service import send_farazsms
            result = send_farazsms(settings, reg.student.mobile, msg_text)
            success = result.get('ok', False)
            
            log = Message(
                recipient_type='student',
                recipient_id=reg.student_id,
                phone=reg.student.mobile,
                message_text=msg_text,
                send_type='installment_reminder',
                status='sent' if success else 'failed',
                sent_at=datetime.utcnow() if success else None,
                error_message=result.get('error') if not success else None,
                created_by=current_user.id
            )
            db.session.add(log)
            
            # در صورت خطا، قسط برای تلاش مجدد علامت‌گذاری نمی‌شود.
            if success:
                inst.reminder_sent = True
                sent += 1
    
    db.session.commit()
    flash(f'{sent} یادآوری قسط ارسال شد', 'success')
    return redirect(url_for('settings_panel.farazsms_config'))


# ═══════════════════════════════════════════════════════════════
#  پایش ارتباطات و ایرادات فنی
# ═══════════════════════════════════════════════════════════════

@settings_panel_bp.route('/diagnostics')
@login_required
def diagnostics():
    from utils.system_diagnostics import run_system_diagnostics
    report = run_system_diagnostics()
    return render_template('settings_panel/diagnostics.html', **report)


@settings_panel_bp.route('/diagnostics/repair', methods=['POST'])
@login_required
def repair_diagnostics():
    if not current_user.is_admin:
        flash('فقط مدیر کل می‌تواند اصلاح خودکار را اجرا کند', 'danger')
        return redirect(url_for('settings_panel.diagnostics'))

    from utils.system_diagnostics import repair_safe_consistency_issues
    result = repair_safe_consistency_issues()
    flash(
        f'اصلاح امن انجام شد: {result["dates"]} تاریخ و '
        f'{result["classes"]} ظرفیت کلاس همگام‌سازی شد',
        'success'
    )
    return redirect(url_for('settings_panel.diagnostics'))


# ═══════════════════════════════════════════════════════════════
#  تنظیمات عمومی پنل
# ═══════════════════════════════════════════════════════════════

@settings_panel_bp.route('/general', methods=['GET', 'POST'])
@login_required
def general_config():
    """تنظیمات عمومی آموزشگاه"""
    from models.system import SystemSettings
    settings = SystemSettings.query.first()
    
    if request.method == 'POST':
        settings.academy_name = request.form.get('academy_name', '')
        settings.academy_code = request.form.get('academy_code', '')
        settings.license_number = request.form.get('license_number', '')
        settings.manager_name = request.form.get('manager_name', '')
        settings.phone = request.form.get('phone', '')
        settings.fax = request.form.get('fax', '')
        settings.email = request.form.get('email', '')
        settings.website = request.form.get('website', '')
        settings.address = request.form.get('address', '')
        settings.current_year = request.form.get('current_year', '')
        settings.current_term = request.form.get('current_term', '')
        db.session.commit()
        flash('تنظیمات ذخیره شد', 'success')
        return redirect(url_for('settings_panel.general_config'))
    
    return render_template('settings_panel/general.html', settings=settings)


@settings_panel_bp.route('/backup', methods=['GET', 'POST'])
@login_required
def backup_config():
    """تنظیمات پشتیبان‌گیری"""
    from models.system import SystemSettings
    settings = SystemSettings.query.first()
    
    if request.method == 'POST':
        settings.auto_backup = 'auto_backup' in request.form
        settings.backup_interval_hours = int(request.form.get('backup_interval_hours', 24))
        settings.backup_path = request.form.get('backup_path', '')
        settings.max_backups = int(request.form.get('max_backups', 30))
        db.session.commit()
        flash('تنظیمات پشتیبان‌گیری ذخیره شد', 'success')
        return redirect(url_for('settings_panel.backup_config'))
    
    # لیست پشتیبان‌ها
    from flask import current_app
    import glob
    backup_dir = current_app.config['BACKUP_FOLDER']
    os.makedirs(backup_dir, exist_ok=True)
    backups = []
    for f in sorted(glob.glob(os.path.join(backup_dir, 'backup_*.zip')), reverse=True):
        stat = os.stat(f)
        backups.append({
            'name': os.path.basename(f),
            'size': round(stat.st_size / 1024, 1),
            'date': datetime.fromtimestamp(stat.st_mtime).strftime('%Y/%m/%d %H:%M'),
        })
    
    return render_template('settings_panel/backup.html', settings=settings, backups=backups)


@settings_panel_bp.route('/backup/create', methods=['POST'])
@login_required
def create_backup():
    """ایجاد پشتیبان"""
    from flask import current_app
    import zipfile
    
    if not current_user.is_admin:
        flash('فقط مدیر کل', 'error')
        return redirect(url_for('settings_panel.backup_config'))
    
    backup_dir = current_app.config['BACKUP_FOLDER']
    os.makedirs(backup_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_name = f'backup_{timestamp}.db'
    backup_path = os.path.join(backup_dir, backup_name)
    
    try:
        from utils.database_tools import sqlite_backup
        sqlite_backup(backup_path)
        zip_path = backup_path + '.zip'
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.write(backup_path, backup_name)
        os.remove(backup_path)
        flash(f'پشتیبان {backup_name}.zip ایجاد شد ✓', 'success')
    except Exception as e:
        flash(f'خطا: {str(e)}', 'error')
    
    return redirect(url_for('settings_panel.backup_config'))


# ═══════════════════════════════════════════════════════════════
#  API وضعیت (برای AJAX)
# ═══════════════════════════════════════════════════════════════

@settings_panel_bp.route('/api/status')
@login_required
def api_status():
    """API وضعیت اتصالات"""
    from models.system import SystemSettings
    settings = SystemSettings.query.first()
    
    from utils.bot_services import bale_polling_manager
    result = {
        'telegram': bool(settings and settings.telegram_bot_token),
        'bale': bale_polling_manager.status()['running'],
        'bale_configured': bool(settings and settings.bale_bot_token),
        'farazsms': bool(settings and settings.farazsms_api_key),
    }
    return jsonify(result)


# ═══════════════════════════════════════════════════════════════
#  تابع کمکی ارسال فراز
# ═══════════════════════════════════════════════════════════════

def send_farazsms_real(settings, phone, message, pattern_code=None, pattern_values=None):
    """نام قدیمی تابع برای سازگاری؛ پیاده‌سازی واقعی در سرویس یکپارچه است."""
    from utils.sms_service import send_farazsms
    return send_farazsms(
        settings,
        phone,
        message,
        pattern_code=pattern_code,
        pattern_values=pattern_values,
    )
