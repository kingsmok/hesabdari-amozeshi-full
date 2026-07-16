"""Additional routes - Certificates, Complaints, Surveys, Tickets, Analytics"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from extensions import db
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


@certificates_bp.route('/')
@login_required
def index():
    certs = Certificate.query.order_by(Certificate.issue_date.desc()).all()
    return render_template('certificates/index.html', certificates=certs,
                         total_issued=len(certs),
                         active_certs=sum(1 for c in certs if c.status == 'active'),
                         cancelled_certs=sum(1 for c in certs if c.status == 'cancelled'))


@certificates_bp.route('/issue/<int:student_id>/<int:registration_id>', methods=['POST'])
@login_required
def issue(student_id, student):
    student = Student.query.get_or_404(student_id)
    reg = Registration.query.get_or_404(registration_id)
    
    serial = f'CERT-1405-{uuid.uuid4().hex[:6].upper()}'
    cert = Certificate(
        serial_number=serial,
        student_id=student_id,
        registration_id=registration_id,
        course_id=reg.course_id,
        issue_date=datetime.utcnow().date(),
        status='active',
        issued_by=current_user.id
    )
    db.session.add(cert)
    db.session.commit()
    
    flash(f'گواهینامه {serial} صادر شد', 'success')
    return redirect(url_for('certificates.index'))


@certificates_bp.route('/verify/<serial>')
def verify(serial):
    cert = Certificate.query.filter_by(serial_number=serial).first()
    if cert:
        return render_template('certificates/verify.html', cert=cert, verified=True)
    return render_template('certificates/verify.html', cert=None, verified=False)


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
        last = Complaint.query.order_by(Complaint.id.desc()).first()
        num = f'CMP-{(last.id + 1) if last else 1:04d}'
        
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
@login_required
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
        last = Ticket.query.order_by(Ticket.id.desc()).first()
        num = f'TKT-{(last.id + 1) if last else 1:04d}'
        
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
    responses = TicketResponse.query.filter_by(ticket_id=id).order_by(TicketResponse.created_at).all()
    return render_template('management/view_ticket.html', ticket=ticket, responses=responses)


@tickets_bp.route('/<int:id>/respond', methods=['POST'])
@login_required
def respond(id):
    ticket = Ticket.query.get_or_404(id)
    response = TicketResponse(
        ticket_id=id,
        user_id=current_user.id,
        response_text=request.form['response_text']
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
@login_required
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
