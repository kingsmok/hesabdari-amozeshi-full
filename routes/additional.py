"""Additional routes - Certificates, Complaints, Surveys, Tickets, Analytics"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from license_client import license_required, licensed_section
from extensions import db
from utils.document_numbers import next_document_number
from utils.form_helpers import get_jalali_date, safe_float, safe_int
from models.course import Certificate, CertificateTemplate
from models.student import Student
from models.registration import Registration
from models.system import Complaint, Survey, SurveyResponse, Ticket, TicketResponse, SystemGoal
from models.user import ActivityLog
from datetime import datetime
import uuid


# ===== Certificates =====
certificates_bp = Blueprint('certificates', __name__)


def _create_certificate(registration, template_id=None, notes=None):
    """صدور امن گواهینامه و جلوگیری از صدور تکراری برای یک ثبت‌نام."""
    from utils.jalali import today_jalali

    existing = Certificate.query.filter(
        Certificate.registration_id == registration.id,
        Certificate.status.in_(['active', 'reissued'])
    ).first()
    if existing:
        return existing, False

    year = today_jalali().split('/')[0]
    serial = f'CERT-{year}-{uuid.uuid4().hex[:8].upper()}'
    certificate = Certificate(
        serial_number=serial,
        student_id=registration.student_id,
        registration_id=registration.id,
        course_id=registration.course_id,
        template_id=template_id or None,
        issue_date=datetime.utcnow().date(),
        status='active',
        notes=(notes or '').strip() or None,
        issued_by=current_user.id
    )
    db.session.add(certificate)
    db.session.flush()
    certificate.qr_code = url_for('certificates.verify', serial=serial, _external=True)
    db.session.commit()
    return certificate, True


@certificates_bp.route('/')
@license_required
@login_required
@licensed_section('certificates')
def index():
    certs = Certificate.query.order_by(Certificate.issue_date.desc(), Certificate.id.desc()).all()
    issued_registration_ids = [
        row[0] for row in db.session.query(Certificate.registration_id).filter(
            Certificate.registration_id.isnot(None),
            Certificate.status.in_(['active', 'reissued'])
        ).all()
    ]

    eligible_query = Registration.query.filter(Registration.status.in_(['active', 'completed']))
    if issued_registration_ids:
        eligible_query = eligible_query.filter(~Registration.id.in_(issued_registration_ids))
    eligible_registrations = eligible_query.order_by(Registration.created_at.desc()).all()
    templates = CertificateTemplate.query.filter_by(is_active=True).order_by(CertificateTemplate.name).all()

    return render_template(
        'certificates/index.html',
        certificates=certs,
        eligible_registrations=eligible_registrations,
        templates=templates,
        total_issued=len(certs),
        active_certs=sum(1 for cert in certs if cert.status in ('active', 'reissued')),
        cancelled_certs=sum(1 for cert in certs if cert.status == 'cancelled')
    )


@certificates_bp.route('/issue', methods=['POST'])
@login_required
def issue():
    registration_id = request.form.get('registration_id', type=int)
    registration = Registration.query.get_or_404(registration_id) if registration_id else None
    if not registration or registration.status not in ('active', 'completed'):
        flash('ثبت‌نام انتخاب‌شده برای صدور گواهینامه معتبر نیست', 'danger')
        return redirect(url_for('certificates.index'))

    template_id = request.form.get('template_id', type=int)
    if template_id and not CertificateTemplate.query.filter_by(id=template_id, is_active=True).first():
        flash('قالب گواهینامه انتخاب‌شده معتبر نیست', 'danger')
        return redirect(url_for('certificates.index'))

    certificate, created = _create_certificate(
        registration,
        template_id=template_id,
        notes=request.form.get('notes')
    )
    if created:
        flash(f'گواهینامه {certificate.serial_number} با موفقیت صادر شد', 'success')
    else:
        flash('برای این ثبت‌نام قبلاً گواهینامه فعال صادر شده است', 'warning')
    return redirect(url_for('certificates.pdf', id=certificate.id))


@certificates_bp.route('/issue/<int:student_id>/<int:registration_id>', methods=['POST'])
@login_required
def issue_legacy(student_id, registration_id):
    """سازگاری با لینک‌های نسخه قبلی که به علت امضای اشتباه تابع کار نمی‌کردند."""
    registration = Registration.query.get_or_404(registration_id)
    if registration.student_id != student_id:
        flash('ثبت‌نام با هنرجوی انتخاب‌شده مطابقت ندارد', 'danger')
        return redirect(url_for('certificates.index'))
    certificate, _ = _create_certificate(registration)
    return redirect(url_for('certificates.pdf', id=certificate.id))


@certificates_bp.route('/<int:id>/pdf')
@login_required
def pdf(id):
    """خروجی رسمی گواهینامه؛ پاسخ همیشه PDF است و تصویر جداگانه تولید نمی‌شود."""
    import io
    import qrcode
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.units import mm
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas
    from models.system import SystemSettings
    from utils.jalali import gregorian_to_jalali
    from utils.pdf_helpers import fa_text, pdf_response, register_pdf_fonts

    certificate = Certificate.query.get_or_404(id)
    settings = SystemSettings.query.first()
    regular_font, bold_font = register_pdf_fonts()

    buffer = io.BytesIO()
    page_width, page_height = landscape(A4)
    document = canvas.Canvas(buffer, pagesize=(page_width, page_height))
    document.setTitle(certificate.serial_number)
    document.setAuthor((settings.academy_name if settings else '') or 'Academy Manager Pro')

    # زمینه و قاب رسمی
    document.setFillColor(colors.HexColor('#fbfaf5'))
    document.rect(0, 0, page_width, page_height, stroke=0, fill=1)
    document.setStrokeColor(colors.HexColor('#0d47a1'))
    document.setLineWidth(3)
    document.rect(11 * mm, 11 * mm, page_width - 22 * mm, page_height - 22 * mm, stroke=1, fill=0)
    document.setStrokeColor(colors.HexColor('#c9a227'))
    document.setLineWidth(1)
    document.rect(15 * mm, 15 * mm, page_width - 30 * mm, page_height - 30 * mm, stroke=1, fill=0)

    academy_name = (settings.academy_name if settings else None) or 'آموزشگاه'
    manager_name = (settings.manager_name if settings else None) or 'مدیریت آموزشگاه'
    student_name = certificate.student.full_name if certificate.student else '-'
    course_title = certificate.course.title if certificate.course else '-'
    duration = certificate.course.duration_hours if certificate.course else 0
    issue_date = gregorian_to_jalali(certificate.issue_date)

    document.setFillColor(colors.HexColor('#0d47a1'))
    document.setFont(bold_font, 19)
    document.drawCentredString(page_width / 2, page_height - 32 * mm, fa_text(academy_name))
    document.setFillColor(colors.HexColor('#b18b12'))
    document.setFont(bold_font, 26)
    document.drawCentredString(page_width / 2, page_height - 53 * mm, fa_text('گواهینامه پایان دوره'))

    document.setFillColor(colors.HexColor('#37474f'))
    document.setFont(regular_font, 13)
    document.drawCentredString(page_width / 2, page_height - 76 * mm, fa_text('بدین‌وسیله گواهی می‌شود'))
    document.setFillColor(colors.HexColor('#0d47a1'))
    document.setFont(bold_font, 22)
    document.drawCentredString(page_width / 2, page_height - 94 * mm, fa_text(student_name))
    document.setFillColor(colors.HexColor('#37474f'))
    document.setFont(regular_font, 13)
    description = f'دوره «{course_title}» را به مدت {duration or 0} ساعت با موفقیت گذرانده است.'
    document.drawCentredString(page_width / 2, page_height - 114 * mm, fa_text(description))

    # مشخصات و امضا
    document.setFont(regular_font, 9.5)
    document.drawRightString(page_width - 27 * mm, 36 * mm, fa_text(f'شماره سریال: {certificate.serial_number}'))
    document.drawRightString(page_width - 27 * mm, 28 * mm, fa_text(f'تاریخ صدور: {issue_date}'))
    document.setFont(bold_font, 10.5)
    document.drawCentredString(page_width / 2, 36 * mm, fa_text(manager_name))
    document.setFont(regular_font, 8.5)
    document.drawCentredString(page_width / 2, 28 * mm, fa_text('مهر و امضا'))

    # QR فقط داخل فایل PDF قرار می‌گیرد و endpoint تصویری ندارد.
    verify_url = certificate.qr_code or url_for('certificates.verify', serial=certificate.serial_number, _external=True)
    qr = qrcode.QRCode(version=2, box_size=5, border=1)
    qr.add_data(verify_url)
    qr.make(fit=True)
    qr_image = qr.make_image(fill_color='#0d47a1', back_color='white')
    qr_buffer = io.BytesIO()
    qr_image.save(qr_buffer, format='PNG')
    qr_buffer.seek(0)
    document.drawImage(ImageReader(qr_buffer), 24 * mm, 24 * mm, 28 * mm, 28 * mm, preserveAspectRatio=True, mask='auto')
    document.setFont(regular_font, 6.5)
    document.setFillColor(colors.HexColor('#607d8b'))
    document.drawString(24 * mm, 20 * mm, 'QR Verification')

    if certificate.status == 'cancelled':
        document.saveState()
        document.setFillColor(colors.Color(0.8, 0.05, 0.05, alpha=0.18))
        document.translate(page_width / 2, page_height / 2)
        document.rotate(25)
        document.setFont(bold_font, 48)
        document.drawCentredString(0, 0, fa_text('باطل شده'))
        document.restoreState()

    document.showPage()
    document.save()
    return pdf_response(
        buffer,
        f'certificate-{certificate.serial_number}.pdf',
        download=request.args.get('download') == '1'
    )


@certificates_bp.route('/beautiful/<cert_type>/<int:id>')
@login_required
def beautiful_certificate(cert_type, id):
    from models.student import Student
    from models.teacher import Teacher
    from models.course import Certificate
    import qrcode, io, base64
    
    if cert_type == 'student':
        obj = Student.query.get_or_404(id)
        name = obj.full_name
        code = obj.student_code or '---'
        course = obj.course.title if obj.course else 'دوره آموزشگاه رهسا'
        cert_code = f'CERT-S-{id:05d}'
    elif cert_type == 'teacher':
        obj = Teacher.query.get_or_404(id)
        name = obj.full_name
        code = obj.teacher_code or '---'
        course = 'دوره آموزشی و تدریس'
        cert_code = f'CERT-T-{id:05d}'
    else:
        # system / default
        obj = None
        name = 'سیستم مدیریت آموزشگاه رهسا'
        code = f'SYS-{id}'
        course = 'گواهینامه عملکرد و اعتبارسنجی سیستم'
        cert_code = f'CERT-X-{id:05d}'
    
    # Generate QR
    qr = qrcode.QRCode(version=1, box_size=10, border=2)
    qr.add_data(f'{cert_type}:{id}:{cert_code}')
    qr.make(fit=True)
    img = qr.make_image(fill_color="#0d47a1", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    qr_data = base64.b64encode(buf.getvalue()).decode()
    
    return render_template('certificates/beautiful.html',
                           name=name, student_code=code, course_title=course,
                           cert_code=cert_code, issue_date='۱۴۰۵/۰۱/۰۱',
                           manager_name='مدیر آموزشگاه رهسا', qr_data=qr_data)


@certificates_bp.route('/<int:id>/cancel', methods=['POST'])
@login_required
def cancel(id):
    certificate = Certificate.query.get_or_404(id)
    certificate.status = 'cancelled'
    certificate.notes = (request.form.get('reason') or certificate.notes or '').strip() or None
    db.session.commit()
    flash(f'گواهینامه {certificate.serial_number} باطل شد', 'success')
    return redirect(url_for('certificates.index'))


@certificates_bp.route('/verify/<serial>')
def verify(serial):
    cert = Certificate.query.filter_by(serial_number=serial).first()
    verified = bool(cert and cert.status in ('active', 'reissued'))
    return render_template('certificates/verify.html', cert=cert, verified=verified)


# ===== Complaints =====
complaints_bp = Blueprint('complaints', __name__)


@complaints_bp.route('/')
@login_required
def index():
    status = request.args.get('status', '')
    query = Complaint.query
    if status:
        query = query.filter_by(status=status)
    complaints = query.order_by(Complaint.created_at.desc()).all()
    return render_template('management/complaints.html', complaints=complaints, status=status)


@complaints_bp.route('/add', methods=['GET', 'POST'])
@login_required
def add():
    if request.method == 'POST':
        num = next_document_number('complaint', with_year=False, width=4)
        
        complaint = Complaint(
            complaint_number=num,
            complainant_name=request.form.get('complainant_name'),
            complainant_phone=request.form.get('complainant_phone'),
            student_id=request.form.get('student_id') or None,
            subject=request.form['subject'],
            description=request.form.get('description'),
            status='new'
        )
        db.session.add(complaint)
        db.session.commit()
        flash('شکایت ثبت شد', 'success')
        return redirect(url_for('complaints.index'))
    
    students = Student.query.filter_by(status='active').all()
    return render_template('management/add_complaint.html', students=students)


@complaints_bp.route('/<int:id>/resolve', methods=['POST'])
@login_required
def resolve(id):
    complaint = Complaint.query.get_or_404(id)
    complaint.status = 'resolved'
    complaint.response = request.form.get('response')
    complaint.resolved_by = current_user.id
    complaint.resolved_at = datetime.utcnow()
    db.session.commit()
    flash('شکایت رسیدگی شد', 'success')
    return redirect(url_for('complaints.index'))


# ===== Surveys =====
surveys_bp = Blueprint('surveys', __name__)


@surveys_bp.route('/')
@login_required
def index():
    surveys = Survey.query.order_by(Survey.created_at.desc()).all()
    return render_template('management/surveys.html', surveys=surveys)


@surveys_bp.route('/add', methods=['GET', 'POST'])
@login_required
def add():
    if request.method == 'POST':
        survey = Survey(
            title=request.form['title'],
            description=request.form.get('description'),
            survey_type=request.form.get('survey_type', 'general'),
            target_id=request.form.get('target_id') or None,
            is_active=True,
            start_date=get_jalali_date(request.form, 'start_date') if request.form.get('start_date') else None,
            end_date=get_jalali_date(request.form, 'end_date') if request.form.get('end_date') else None
        )
        db.session.add(survey)
        db.session.commit()
        flash('نظرسنجی ایجاد شد', 'success')
        return redirect(url_for('surveys.index'))
    
    return render_template('management/add_survey.html')


@surveys_bp.route('/<int:id>/results')
@login_required
def results(id):
    survey = Survey.query.get_or_404(id)
    responses = SurveyResponse.query.filter_by(survey_id=id).all()
    avg_score = sum(r.score or 0 for r in responses) / len(responses) if responses else 0
    return render_template('management/survey_results.html', survey=survey, responses=responses, avg_score=round(avg_score, 1))


# ===== Tickets =====
tickets_bp = Blueprint('tickets', __name__)


@tickets_bp.route('/')
@license_required
@login_required
@licensed_section('crm')
def index():
    if current_user.is_admin:
        tickets = Ticket.query.order_by(Ticket.created_at.desc()).all()
    else:
        tickets = Ticket.query.filter_by(user_id=current_user.id).order_by(Ticket.created_at.desc()).all()
    return render_template('management/tickets.html', tickets=tickets)


@tickets_bp.route('/add', methods=['GET', 'POST'])
@login_required
def add():
    if request.method == 'POST':
        num = next_document_number('ticket', with_year=False, width=4)
        
        ticket = Ticket(
            ticket_number=num,
            user_id=current_user.id,
            subject=request.form['subject'],
            description=request.form.get('description'),
            priority=request.form.get('priority', 'medium'),
            status='open'
        )
        db.session.add(ticket)
        db.session.commit()
        flash('تیکت ثبت شد', 'success')
        return redirect(url_for('tickets.index'))
    
    return render_template('management/add_ticket.html')


@tickets_bp.route('/<int:id>')
@login_required
def view(id):
    ticket = Ticket.query.get_or_404(id)
    if not current_user.is_admin and current_user.id not in (ticket.user_id, ticket.assigned_to):
        flash('اجازه مشاهده این تیکت را ندارید', 'danger')
        return redirect(url_for('tickets.index'))
    responses = TicketResponse.query.filter_by(ticket_id=id).order_by(TicketResponse.created_at).all()
    return render_template('management/view_ticket.html', ticket=ticket, responses=responses)


@tickets_bp.route('/<int:id>/respond', methods=['POST'])
@login_required
def respond(id):
    ticket = Ticket.query.get_or_404(id)
    if not current_user.is_admin and current_user.id not in (ticket.user_id, ticket.assigned_to):
        flash('اجازه پاسخ به این تیکت را ندارید', 'danger')
        return redirect(url_for('tickets.index'))
    response_text = (request.form.get('response_text') or '').strip()
    if not response_text:
        flash('متن پاسخ نمی‌تواند خالی باشد', 'danger')
        return redirect(url_for('tickets.view', id=id))
    response = TicketResponse(
        ticket_id=id,
        user_id=current_user.id,
        response_text=response_text
    )
    db.session.add(response)
    
    if ticket.status == 'open':
        ticket.status = 'in_progress'
    
    db.session.commit()
    flash('پاسخ ثبت شد', 'success')
    return redirect(url_for('tickets.view', id=id))


@tickets_bp.route('/<int:id>/close', methods=['POST'])
@login_required
def close(id):
    ticket = Ticket.query.get_or_404(id)
    if not current_user.is_admin and current_user.id not in (ticket.user_id, ticket.assigned_to):
        flash('اجازه بستن این تیکت را ندارید', 'danger')
        return redirect(url_for('tickets.index'))
    ticket.status = 'resolved'
    ticket.resolved_at = datetime.utcnow()
    db.session.commit()
    flash('تیکت بسته شد', 'success')
    return redirect(url_for('tickets.view', id=id))


# ===== Goals =====
goals_bp = Blueprint('goals', __name__)


@goals_bp.route('/')
@login_required
def index():
    goals = SystemGoal.query.filter_by(is_active=True).all()
    return render_template('management/goals.html', goals=goals)


@goals_bp.route('/add', methods=['POST'])
@login_required
def add():
    goal = SystemGoal(
        title=request.form['title'],
        goal_type=request.form.get('goal_type'),
        target_value=safe_float(request.form.get('target_value')),
        period=request.form.get('period', 'monthly'),
        branch_id=request.form.get('branch_id') or None,
        is_active=True
    )
    db.session.add(goal)
    db.session.commit()
    flash('هدف ثبت شد', 'success')
    return redirect(url_for('goals.index'))


# ===== Analytics =====
analytics_bp = Blueprint('analytics', __name__)


@analytics_bp.route('/dashboard')
@license_required
@login_required
@licensed_section('analytics')
def smart_dashboard():
    from models.student import Student
    from models.registration import Registration
    from models.finance import Payment
    from models.classes import ClassGroup
    from models.teacher import Teacher
    from datetime import timedelta
    
    today = datetime.utcnow()
    
    # Enrollment trend (last 6 months)
    enrollment_trend = []
    for i in range(5, -1, -1):
        d = today - timedelta(days=30*i)
        count = Registration.query.filter(
            db.extract('year', Registration.created_at) == d.year,
            db.extract('month', Registration.created_at) == d.month
        ).count()
        enrollment_trend.append({'month': d.strftime('%Y-%m'), 'count': count})
    
    # Top courses
    from models.course import Course
    top_courses = db.session.query(
        Course.title, db.func.count(Registration.id).label('count')
    ).join(Registration).group_by(Course.title).order_by(
        db.func.count(Registration.id).desc()
    ).limit(5).all()
    
    # Student status distribution
    status_dist = db.session.query(
        Student.status, db.func.count(Student.id)
    ).group_by(Student.status).all()
    
    # Referral sources
    referral_dist = db.session.query(
        Student.referral_source, db.func.count(Student.id)
    ).filter(Student.referral_source.isnot(None)).group_by(Student.referral_source).all()
    
    # Revenue by month
    revenue_trend = []
    for i in range(5, -1, -1):
        d = today - timedelta(days=30*i)
        total = db.session.query(db.func.sum(Payment.amount)).filter(
            db.extract('year', Payment.payment_date) == d.year,
            db.extract('month', Payment.payment_date) == d.month,
            Payment.status == 'confirmed'
        ).scalar() or 0
        revenue_trend.append({'month': d.strftime('%Y-%m'), 'amount': total})
    
    return render_template('management/analytics.html',
                         enrollment_trend=enrollment_trend,
                         top_courses=top_courses,
                         status_dist=status_dist,
                         referral_dist=referral_dist,
                         revenue_trend=revenue_trend)
