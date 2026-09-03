"""
قابلیت‌های جدید:
۱) مدیریت کامل دوره‌ها (ثبت/ویرایش/سرفصل)
۲) PDF لیست کلاس برای استاد (با تیک حضور)
۳) ربات تلگرام (استعلام هنرجو + اطلاعات دوره)
۴) ربات بله (همان قابلیت‌ها)
۵) اتصال فراز اس‌ام‌اس (ارسال تبلیغاتی + اقساط)
۶) سیستم اقساطی قوی (جریمه + یادآوری خودکار + گزارش)
"""
import os, json, io, requests
from datetime import datetime, timedelta, date
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, send_file, make_response, current_app, abort
from flask_login import login_required, current_user
from license_client import license_required, licensed_section
from extensions import db, csrf
from utils.form_helpers import get_jalali_date, safe_float, safe_int
from utils.access_control import require_permission

new_features_bp = Blueprint('new_features', __name__)

# وب‌هوک‌ها نیاز به CSRF ندارند (از خارج فراخوانی می‌شوند)
# این کد بعد از register_blueprint در app.py اجرا می‌شود


# ═══════════════════════════════════════════════════════════════
#  ۱) مدیریت کامل دوره‌ها
# ═══════════════════════════════════════════════════════════════

@new_features_bp.route('/courses', strict_slashes=False)
@license_required
@login_required
@licensed_section('courses')
def course_list():
    """لیست کامل دوره‌ها"""
    from models.course import Course, Field
    field_id = request.args.get('field_id', '', type=str)
    search = request.args.get('search', '')
    
    query = Course.query
    if field_id:
        query = query.filter_by(field_id=int(field_id))
    if search:
        query = query.filter(Course.title.contains(search) | Course.code.contains(search))
    
    courses = query.order_by(Course.created_at.desc()).all()
    fields = Field.query.filter_by(is_active=True).all()
    
    return render_template('new/course_list.html', courses=courses, fields=fields, search=search, field_id=field_id)


@new_features_bp.route('/courses/add', methods=['GET', 'POST'])
@login_required
def course_add():
    """ثبت دوره جدید"""
    from models.course import Course, Field, Syllabus
    
    if request.method == 'POST':
        field_id = safe_int(request.form.get('field_id'))
        if not field_id:
            flash('انتخاب رشته آموزشی الزامی است', 'danger')
            fields = Field.query.filter_by(is_active=True).all()
            return render_template('new/course_add.html', fields=fields), 400
        last = Course.query.order_by(Course.id.desc()).first()
        next_num = (last.id + 1) if last else 1
        code = f'CRS-{next_num:04d}'
        
        course = Course(
            title=request.form['title'],
            code=code,
            field_id=field_id,
            description=request.form.get('description'),
            duration_hours=safe_int(request.form.get('duration_hours')),
            total_sessions=safe_int(request.form.get('total_sessions')),
            base_fee=safe_float(request.form.get('base_fee')),
            registration_fee=safe_float(request.form.get('registration_fee')),
            book_fee=safe_float(request.form.get('book_fee')),
            exam_fee=safe_float(request.form.get('exam_fee')),
            certificate_fee=safe_float(request.form.get('certificate_fee')),
            other_fees=safe_float(request.form.get('other_fees')),
            standard_code=request.form.get('standard_code'),
            standard_name=request.form.get('standard_name'),
            branch_id=request.form.get('branch_id', 1),
            is_active=True
        )
        db.session.add(course)
        db.session.flush()
        
        # سرفصل‌ها
        chapters = request.form.getlist('syl_chapter[]')
        lessons = request.form.getlist('syl_lesson[]')
        hours = request.form.getlist('syl_hours[]')
        
        for i in range(len(chapters)):
            if chapters[i].strip():
                syl = Syllabus(
                    course_id=course.id,
                    chapter_no=i + 1,
                    chapter_title=chapters[i],
                    lesson_title=lessons[i] if i < len(lessons) else '',
                    hours=float(hours[i]) if i < len(hours) and hours[i] else 0,
                    order=i + 1
                )
                db.session.add(syl)
        
        db.session.commit()
        flash(f'دوره "{course.title}" با کد {code} ثبت شد', 'success')
        return redirect(url_for('new_features.course_view', id=course.id))
    
    from models.course import Field
    fields = Field.query.filter_by(is_active=True).all()
    return render_template('new/course_add.html', fields=fields)


@new_features_bp.route('/courses/<int:id>')
@login_required
@require_permission('courses', 'view')
def course_view(id):
    """مشاهده جزئیات دوره"""
    from models.course import Course, Syllabus
    from models.registration import Registration
    from models.classes import ClassGroup
    
    course = Course.query.get_or_404(id)
    if (not current_user.is_admin and current_user.branch_id and
            course.branch_id not in (None, current_user.branch_id)):
        abort(404)
    syllabus = Syllabus.query.filter_by(course_id=id).order_by(Syllabus.order).all()
    registrations_query = Registration.query.filter_by(course_id=id)
    classes_query = ClassGroup.query.filter_by(course_id=id)
    if not current_user.is_admin and current_user.branch_id:
        registrations_query = registrations_query.filter(
            Registration.branch_id == current_user.branch_id
        )
        classes_query = classes_query.filter(
            ClassGroup.branch_id == current_user.branch_id
        )
    registrations = registrations_query.order_by(
        Registration.created_at.desc()
    ).limit(20).all()
    classes = classes_query.all()
    total_regs = registrations_query.count()
    active_regs = registrations_query.filter_by(status='active').count()
    
    return render_template('new/course_view.html', 
                         course=course, syllabus=syllabus,
                         registrations=registrations, classes=classes,
                         total_regs=total_regs, active_regs=active_regs)


@new_features_bp.route('/courses/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def course_edit(id):
    """ویرایش دوره"""
    from models.course import Course, Field, Syllabus
    
    course = Course.query.get_or_404(id)
    
    if request.method == 'POST':
        course.title = request.form['title']
        course.field_id = safe_int(request.form.get('field_id'))
        course.description = request.form.get('description')
        course.duration_hours = safe_int(request.form.get('duration_hours'))
        course.total_sessions = safe_int(request.form.get('total_sessions'))
        course.base_fee = safe_float(request.form.get('base_fee'))
        course.registration_fee = safe_float(request.form.get('registration_fee'))
        course.book_fee = safe_float(request.form.get('book_fee'))
        course.exam_fee = safe_float(request.form.get('exam_fee'))
        course.certificate_fee = safe_float(request.form.get('certificate_fee'))
        course.other_fees = safe_float(request.form.get('other_fees'))
        course.standard_code = request.form.get('standard_code')
        course.standard_name = request.form.get('standard_name')
        
        # بروزرسانی سرفصل‌ها
        Syllabus.query.filter_by(course_id=id).delete()
        chapters = request.form.getlist('syl_chapter[]')
        lessons = request.form.getlist('syl_lesson[]')
        hours = request.form.getlist('syl_hours[]')
        
        for i in range(len(chapters)):
            if chapters[i].strip():
                syl = Syllabus(
                    course_id=id, chapter_no=i + 1,
                    chapter_title=chapters[i],
                    lesson_title=lessons[i] if i < len(lessons) else '',
                    hours=float(hours[i]) if i < len(hours) and hours[i] else 0,
                    order=i + 1
                )
                db.session.add(syl)
        
        db.session.commit()
        flash('دوره بروزرسانی شد', 'success')
        return redirect(url_for('new_features.course_view', id=id))
    
    fields = Field.query.filter_by(is_active=True).all()
    syllabus = Syllabus.query.filter_by(course_id=id).order_by(Syllabus.order).all()
    return render_template('new/course_edit.html', course=course, fields=fields, syllabus=syllabus)


# ═══════════════════════════════════════════════════════════════
#  ۲) PDF لیست کلاس برای استاد
# ═══════════════════════════════════════════════════════════════

@new_features_bp.route('/classes/<int:id>/pdf')
@login_required
def class_pdf(id):
    """تولید PDF لیست کلاس برای استاد — بدون تاریخ ثبت‌نام، با ستون تیک حضور"""
    from models.classes import ClassGroup
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT
    
    class_group = ClassGroup.query.get_or_404(id)
    registrations = class_group.registrations.filter_by(status='active').all()
    
    # تلاش برای رجیستر فونت فارسی
    try:
        font_paths = [
            '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
            '/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf',
        ]
        font_name = 'DejaVuSans'
        for fp in font_paths:
            if os.path.exists(fp):
                pdfmetrics.registerFont(TTFont(font_name, fp))
                break
        else:
            font_name = 'Helvetica'
    except:
        font_name = 'Helvetica'
    
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, rightMargin=20*mm, leftMargin=20*mm,
                           topMargin=20*mm, bottomMargin=20*mm)
    
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('title', parent=styles['Title'], fontName=font_name, fontSize=14)
    normal_style = ParagraphStyle('normal', parent=styles['Normal'], fontName=font_name, fontSize=9)
    
    elements = []
    
    # عنوان
    elements.append(Paragraph(f"Class List - {class_group.name}", title_style))
    elements.append(Spacer(1, 5*mm))
    
    info_data = [
        ['Course:', class_group.course.title if class_group.course else '-',
         'Teacher:', class_group.teacher.full_name if class_group.teacher else '-'],
        ['Schedule:', f"{class_group.start_time}-{class_group.end_time}",
         'Room:', class_group.room.name if class_group.room else '-'],
        ['Date:', str(class_group.start_date) if class_group.start_date else '-',
         'Students:', str(len(registrations))],
    ]
    
    info_table = Table(info_data, colWidths=[50, 150, 50, 150])
    info_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), font_name),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('FONTNAME', (0, 0), (0, -1), font_name),
        ('FONTNAME', (2, 0), (2, -1), font_name),
        ('BACKGROUND', (0, 0), (0, -1), colors.Color(0.9, 0.95, 1)),
        ('BACKGROUND', (2, 0), (2, -1), colors.Color(0.9, 0.95, 1)),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.Color(0.8, 0.8, 0.8)),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    elements.append(info_table)
    elements.append(Spacer(1, 8*mm))
    
    # جدول هنرجویان
    # ستون‌ها: ردیف | نام | کد | موبایل | ۱۲ ستون حضور (برای تیک استاد)
    header = ['#', 'Student Name', 'Code', 'Phone']
    for i in range(1, 13):
        header.append(str(i))
    
    data = [header]
    
    for idx, reg in enumerate(registrations):
        student = reg.student
        row = [
            str(idx + 1),
            f"{student.first_name} {student.last_name}",
            student.student_code,
            student.mobile or ''
        ]
        # ۱۲ خانه خالی برای تیک حضور
        for _ in range(12):
            row.append('')
        data.append(row)
    
    col_widths = [25, 120, 65, 70] + [22] * 12
    table = Table(data, colWidths=col_widths, repeatRows=1)
    
    style_commands = [
        ('FONTNAME', (0, 0), (-1, -1), font_name),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('FONTNAME', (0, 0), (-1, 0), font_name),
        ('FONTSIZE', (0, 0), (-1, 0), 7),
        ('BACKGROUND', (0, 0), (-1, 0), colors.Color(0.13, 0.35, 0.55)),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.Color(0.7, 0.7, 0.7)),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('ALIGN', (1, 1), (1, -1), 'RIGHT'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.Color(0.96, 0.97, 0.98)]),
    ]
    
    table.setStyle(TableStyle(style_commands))
    elements.append(table)
    
    elements.append(Spacer(1, 10*mm))
    elements.append(Paragraph("Teacher Signature: ________________          Date: ________________", normal_style))
    
    doc.build(elements)
    buf.seek(0)
    
    return send_file(buf, mimetype='application/pdf',
                    as_attachment=True,
                    download_name=f'class_{class_group.class_code}_list.pdf')


@new_features_bp.route('/classes/<int:id>/attendance-sheet')
@login_required
def attendance_sheet(id):
    """برگه حضور و غیاب چاپی برای استاد — با ستون‌های جلسه"""
    from models.classes import ClassGroup
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.lib.enums import TA_CENTER
    
    class_group = ClassGroup.query.get_or_404(id)
    registrations = class_group.registrations.filter_by(status='active').all()
    sessions_count = class_group.course.total_sessions if class_group.course else 10
    
    try:
        font_path = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
        if os.path.exists(font_path):
            pdfmetrics.registerFont(TTFont('DejaVuSans', font_path))
            font_name = 'DejaVuSans'
        else:
            font_name = 'Helvetica'
    except:
        font_name = 'Helvetica'
    
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), rightMargin=15*mm, leftMargin=15*mm,
                           topMargin=15*mm, bottomMargin=15*mm)
    
    title_style = ParagraphStyle('t', fontName=font_name, fontSize=12, alignment=TA_CENTER)
    
    elements = []
    elements.append(Paragraph(f"Attendance Sheet - {class_group.name} ({class_group.class_code})", title_style))
    elements.append(Spacer(1, 3*mm))
    
    # سربرگ: ردیف | نام | کد | ۱ تا N جلسه | مجموع
    max_sessions = min(sessions_count, 20)  # حداکثر ۲۰ جلسه در یک صفحه
    
    header = ['#', 'Name', 'Code']
    for i in range(1, max_sessions + 1):
        header.append(str(i))
    header.append('Total')
    header.append('%')
    
    data = [header]
    
    for idx, reg in enumerate(registrations):
        s = reg.student
        row = [str(idx + 1), f"{s.first_name} {s.last_name}", s.student_code]
        for _ in range(max_sessions):
            row.append('')
        row.append('')  # مجموع
        row.append('')  # درصد
        data.append(row)
    
    col_widths = [22, 110, 55] + [18] * max_sessions + [30, 28]
    table = Table(data, colWidths=col_widths, repeatRows=1)
    
    table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), font_name),
        ('FONTSIZE', (0, 0), (-1, -1), 7),
        ('BACKGROUND', (0, 0), (-1, 0), colors.Color(0.13, 0.35, 0.55)),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.4, colors.Color(0.7, 0.7, 0.7)),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('ALIGN', (1, 1), (1, -1), 'RIGHT'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.Color(0.97, 0.97, 0.98)]),
    ]))
    elements.append(table)
    
    doc.build(elements)
    buf.seek(0)
    
    return send_file(buf, mimetype='application/pdf',
                    as_attachment=True,
                    download_name=f'class_{class_group.class_code}_attendance.pdf')


# ═══════════════════════════════════════════════════════════════
#  ۳) ربات تلگرام
# ═══════════════════════════════════════════════════════════════

@new_features_bp.route('/settings/telegram', methods=['GET', 'POST'])
@login_required
def telegram_settings():
    """مسیر قدیمی؛ تنظیمات ربات‌ها در پنل اتصال یکپارچه شده است."""
    return redirect(url_for('settings_panel.telegram_config'))


@new_features_bp.route('/webhook/telegram', methods=['POST'])
@csrf.exempt
def telegram_webhook():
    """دریافت پیام تلگرام؛ منطق پاسخ با ربات بله مشترک است."""
    from models.system import SystemSettings
    from utils.bot_services import build_academy_bot_response, send_bot_message

    data = request.get_json(silent=True) or {}
    message = data.get('message') or data.get('edited_message')
    if not message or not message.get('chat') or not message.get('text'):
        return jsonify({'ok': True})

    settings = SystemSettings.query.first()
    token = settings.telegram_bot_token if settings else ''
    if not token:
        return jsonify({'ok': False, 'description': 'توکن تلگرام تنظیم نشده'}), 503

    expected = request.args.get('secret') or request.headers.get('X-Telegram-Bot-Api-Secret-Token')
    import hashlib
    expected_secret = hashlib.sha256(token.encode('utf-8')).hexdigest()[:24]
    if expected != expected_secret:
        return jsonify({'ok': False, 'description': 'unauthorized'}), 401

    try:
        answer = build_academy_bot_response(message.get('text', ''))
        result = send_bot_message('telegram', token, message['chat']['id'], answer)
        if not result.get('ok'):
            return jsonify(result), 502
    except Exception as exc:
        current_app.logger.exception('Telegram bot response failed')
        return jsonify({'ok': False, 'description': str(exc)}), 500
    return jsonify({'ok': True})


@new_features_bp.route('/settings/telegram/set-webhook', methods=['POST'])
@login_required
def set_telegram_webhook():
    """تنظیم وب‌هوک تلگرام"""
    from models.system import SystemSettings
    settings = SystemSettings.query.first()
    
    if not settings or not settings.telegram_bot_token:
        flash('ابتدا توکن بات را وارد کنید', 'error')
        return redirect(url_for('new_features.telegram_settings'))
    
    webhook_url = request.form.get('webhook_url', '')
    if not webhook_url:
        flash('آدرس وب‌هوک را وارد کنید', 'error')
        return redirect(url_for('new_features.telegram_settings'))
    
    result = requests.get(
        f'https://api.telegram.org/bot{settings.telegram_bot_token}/setWebhook',
        params={'url': webhook_url}
    ).json()
    
    if result.get('ok'):
        flash('وب‌هوک تلگرام با موفقیت تنظیم شد ✓', 'success')
    else:
        flash(f'خطا: {result.get("description", "نامشخص")}', 'error')
    
    return redirect(url_for('new_features.telegram_settings'))


# ═══════════════════════════════════════════════════════════════
#  ۴) ربات بله
# ═══════════════════════════════════════════════════════════════

@new_features_bp.route('/settings/bale', methods=['GET', 'POST'])
@login_required
def bale_settings():
    """مسیر قدیمی؛ بله اکنون بدون وب‌هوک و با Long Polling اجرا می‌شود."""
    return redirect(url_for('settings_panel.bale_config'))


@new_features_bp.route('/webhook/bale', methods=['POST'])
@csrf.exempt
def bale_webhook():
    """وب‌هوک بله عمداً غیرفعال است؛ دریافت پیام فقط با Long Polling انجام می‌شود."""
    return jsonify({
        'ok': False,
        'description': 'Bale webhook is disabled; the application uses getUpdates long polling.'
    }), 410


# ═══════════════════════════════════════════════════════════════
#  ۵) اتصال فراز اس‌ام‌اس
# ═══════════════════════════════════════════════════════════════

@new_features_bp.route('/settings/farazsms', methods=['GET', 'POST'])
@login_required
def farazsms_settings():
    """مسیر قدیمی؛ تنظیم پنل پیامکی در پنل اتصال یکپارچه شده است."""
    return redirect(url_for('settings_panel.farazsms_config'))


def send_farazsms(phone, message, pattern_code=None, pattern_values=None):
    """تابع سازگار قدیمی که از سرویس رسمی و یکپارچه پیامک استفاده می‌کند."""
    from utils.sms_service import send_configured_sms
    return send_configured_sms(
        phone,
        message,
        pattern_code=pattern_code,
        pattern_values=pattern_values,
    )


@new_features_bp.route('/messaging/farazsms/send', methods=['GET', 'POST'])
@login_required
def farazsms_send():
    """ارسال پیامک تبلیغاتی / اقساط از فراز"""
    from models.student import Student
    from models.system import Message
    
    if request.method == 'POST':
        target = request.form.get('target')
        message_text = request.form['message_text']
        send_type = request.form.get('send_type', 'manual')
        
        phones = []
        if target == 'all_students':
            students = Student.query.filter_by(status='active').all()
            phones = [(s.mobile, s.full_name) for s in students if s.mobile]
        elif target == 'debtors':
            from models.registration import Registration
            regs = Registration.query.filter(Registration.remaining_amount > 0, Registration.status == 'active').all()
            phones = [(r.student.mobile, r.student.full_name) for r in regs if r.student and r.student.mobile]
        elif target == 'specific':
            phone = request.form.get('phone')
            if phone:
                phones = [(phone, phone)]
        
        sent_count = 0
        for phone, name in phones:
            personalized = message_text.replace('{نام}', name)
            result = send_farazsms(phone, personalized)
            
            success = result.get('ok', False)
            msg = Message(
                recipient_type='student',
                phone=phone,
                message_text=personalized,
                send_type=send_type,
                status='sent' if success else 'failed',
                sent_at=datetime.utcnow() if success else None,
                error_message=result.get('error') if not success else None,
                created_by=current_user.id
            )
            db.session.add(msg)
            if success:
                sent_count += 1
        
        db.session.commit()
        flash(f'{sent_count} پیامک از طریق فراز ارسال شد', 'success')
        return redirect(url_for('new_features.farazsms_send'))
    
    return render_template('new/farazsms_send.html')


@new_features_bp.route('/messaging/farazsms/installment-reminders', methods=['POST'])
@login_required
def send_installment_reminders():
    """ارسال یادآوری اقساط از طریق فراز"""
    from models.registration import Installment
    from models.system import Message
    
    today = date.today()
    upcoming = today + timedelta(days=3)
    
    # اقساط نزدیک سررسید
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
                f"یادآوری: قسط شماره {inst.installment_number} "
                f"به مبلغ {inst.amount:,.0f} تومان "
                f"در تاریخ {inst.due_date} سررسید می‌شود.\n"
                f"آموزشگاه"
            )
            
            result = send_farazsms(reg.student.mobile, msg_text)
            
            log = Message(
                recipient_type='student',
                recipient_id=reg.student_id,
                phone=reg.student.mobile,
                message_text=msg_text,
                send_type='installment_reminder',
                status='sent' if result.get('ok', False) else 'failed',
                created_by=current_user.id
            )
            db.session.add(log)
            
            if result.get('ok', False):
                inst.reminder_sent = True
                sent += 1
    
    db.session.commit()
    flash(f'{sent} یادآوری قسط ارسال شد', 'success')
    return redirect(url_for('new_features.farazsms_send'))


# ═══════════════════════════════════════════════════════════════
#  ۶) سیستم اقساطی قوی
# ═══════════════════════════════════════════════════════════════

@new_features_bp.route('/finance/installments')
@license_required
@login_required
@licensed_section('installments')
def installment_dashboard():
    """داشبورد مدیریت اقساط"""
    from models.registration import Installment, Registration
    
    today = date.today()
    
    # آمار کلی
    total_pending = Installment.query.filter(Installment.status.in_(['pending', 'partial'])).count()
    total_overdue = Installment.query.filter(
        Installment.due_date < today,
        Installment.status.in_(['pending', 'partial'])
    ).count()
    total_paid = Installment.query.filter_by(status='paid').count()
    
    total_pending_amount = db.session.query(db.func.sum(Installment.amount - Installment.paid_amount)).filter(
        Installment.status.in_(['pending', 'partial'])
    ).scalar() or 0
    
    total_overdue_amount = db.session.query(db.func.sum(Installment.amount - Installment.paid_amount)).filter(
        Installment.due_date < today,
        Installment.status.in_(['pending', 'partial'])
    ).scalar() or 0
    
    # اقساط معوقه
    overdue_list = Installment.query.filter(
        Installment.due_date < today,
        Installment.status.in_(['pending', 'partial'])
    ).order_by(Installment.due_date).limit(30).all()
    
    # محاسبه روزهای تأخیر و جریمه
    for inst in overdue_list:
        inst.late_days = (today - inst.due_date).days
        # جریمه: ۱٪ در ماه = ۰.۰۳۳٪ در روز
        daily_rate = 0.01 / 30
        inst.calculated_late_fee = round(inst.amount * daily_rate * inst.late_days)
    
    # اقساط نزدیک سررسید (۷ روز آینده)
    upcoming = Installment.query.filter(
        Installment.due_date.between(today, today + timedelta(days=7)),
        Installment.status.in_(['pending', 'partial'])
    ).order_by(Installment.due_date).all()
    
    # اقساط پرداخت شده اخیر
    recent_paid = Installment.query.filter_by(status='paid').order_by(
        Installment.paid_date.desc()
    ).limit(15).all()
    
    stats = {
        'total_pending': total_pending,
        'total_overdue': total_overdue,
        'total_paid': total_paid,
        'total_pending_amount': total_pending_amount,
        'total_overdue_amount': total_overdue_amount,
        'collection_rate': round(total_paid / (total_paid + total_pending) * 100, 1) if (total_paid + total_pending) > 0 else 0,
    }
    
    return render_template('new/installment_dashboard.html',
                         stats=stats, overdue_list=overdue_list,
                         upcoming=upcoming, recent_paid=recent_paid, today=today)


@new_features_bp.route('/finance/installments/<int:id>/pay', methods=['POST'])
@login_required
def pay_installment(id):
    """پرداخت قسط"""
    from models.registration import Installment, Registration
    from models.finance import Payment, Cashbox, CashboxTransaction
    
    inst = Installment.query.get_or_404(id)
    amount = safe_float(request.form.get('amount'))
    method = request.form.get('method', 'cash')
    
    if amount <= 0:
        flash('مبلغ نامعتبر', 'error')
        return redirect(url_for('new_features.installment_dashboard'))
    if inst.status == 'paid' or amount > max(0, inst.remaining):
        flash('قسط تسویه شده یا مبلغ بیشتر از مانده قسط است', 'danger')
        return redirect(url_for('new_features.installment_dashboard'))
    
    # بروزرسانی قسط
    inst.paid_amount = (inst.paid_amount or 0) + amount
    inst.paid_date = date.today()
    inst.late_fee = safe_float(request.form.get('late_fee')) if request.form.get('late_fee') else 0
    
    if inst.paid_amount >= inst.amount + inst.late_fee:
        inst.status = 'paid'
    else:
        inst.status = 'partial'
    
    # ثبت پرداخت
    last = Payment.query.order_by(Payment.id.desc()).first()
    receipt = f'PAY-{(last.id + 1) if last else 1:06d}'
    
    reg = inst.registration
    payment = Payment(
        receipt_no=receipt,
        student_id=reg.student_id,
        registration_id=reg.id,
        installment_id=inst.id,
        amount=amount,
        payment_method=method,
        payment_date=date.today(),
        description=f'پرداخت قسط شماره {inst.installment_number}',
        branch_id=reg.branch_id,
        created_by=current_user.id
    )
    db.session.add(payment)
    
    # بروزرسانی ثبت‌نام
    reg.paid_amount = (reg.paid_amount or 0) + amount
    reg.remaining_amount = max(0, (reg.total_fee or 0) - reg.paid_amount)
    
    # بروزرسانی صندوق
    if method == 'cash':
        from models.finance import get_or_create_main_cashbox
        cashbox = get_or_create_main_cashbox()
        if cashbox:
            cashbox.balance = (cashbox.balance or 0) + amount
            tx = CashboxTransaction(
                cashbox_id=cashbox.id, trans_type='in', amount=amount,
                description=f'قسط {inst.installment_number} - {reg.student.full_name}',
                reference_type='installment', balance_after=cashbox.balance,
                created_by=current_user.id
            )
            db.session.add(tx)
    
    db.session.commit()
    flash(f'پرداخت قسط {inst.installment_number} ثبت شد ({amount:,.0f} تومان)', 'success')
    return redirect(url_for('new_features.installment_dashboard'))


@new_features_bp.route('/finance/installments/batch-reminders', methods=['POST'])
@login_required
def batch_reminders():
    """ارسال یادآوری گروهی اقساط (درون‌برنامه‌ای)"""
    from models.registration import Installment
    from models.system import Notification
    
    today = date.today()
    upcoming = today + timedelta(days=3)
    
    installments = Installment.query.filter(
        Installment.due_date.between(today, upcoming),
        Installment.status.in_(['pending', 'partial'])
    ).all()
    
    count = 0
    for inst in installments:
        reg = inst.registration
        if reg and reg.student:
            # اعلان داخلی
            notif = Notification(
                user_id=1,  # مدیر
                title=f'یادآوری قسط: {reg.student.full_name}',
                body=f'قسط {inst.installment_number} به مبلغ {inst.amount:,.0f} تومان در {inst.due_date}',
                notif_type='payment'
            )
            db.session.add(notif)
            inst.reminder_sent = True
            count += 1
    
    db.session.commit()
    flash(f'{count} یادآوری ارسال شد', 'success')
    return redirect(url_for('new_features.installment_dashboard'))


@new_features_bp.route('/finance/installments/report')
@login_required
def installment_report():
    """گزارش تفصیلی اقساط"""
    from models.registration import Installment, Registration
    from models.student import Student
    
    status_filter = request.args.get('status', '')
    
    query = Installment.query
    if status_filter:
        if status_filter == 'overdue':
            query = query.filter(Installment.due_date < date.today(), Installment.status.in_(['pending', 'partial']))
        elif status_filter == 'upcoming':
            query = query.filter(Installment.due_date.between(date.today(), date.today() + timedelta(days=7)))
        else:
            query = query.filter_by(status=status_filter)
    
    installments = query.order_by(Installment.due_date).limit(100).all()
    
    return render_template('new/installment_report.html', installments=installments, status_filter=status_filter)


@new_features_bp.route('/finance/installments/auto-late-fee', methods=['POST'])
@login_required
def auto_late_fee():
    """محاسبه خودکار جریمه دیرکرد"""
    from models.registration import Installment
    
    today = date.today()
    overdue = Installment.query.filter(
        Installment.due_date < today,
        Installment.status.in_(['pending', 'partial'])
    ).all()
    
    count = 0
    for inst in overdue:
        days = (today - inst.due_date).days
        daily_rate = 0.01 / 30  # 1% per month
        late_fee = round(inst.amount * daily_rate * days)
        
        if late_fee > (inst.late_fee or 0):
            inst.late_fee = late_fee
            inst.late_days = days
            count += 1
    
    db.session.commit()
    flash(f'جریمه دیرکرد {count} قسط محاسبه شد', 'success')
    return redirect(url_for('new_features.installment_dashboard'))
