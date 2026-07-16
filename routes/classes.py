"""Classes routes"""
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from extensions import db
from utils.form_helpers import get_jalali_date, safe_float, safe_int
from models.classes import ClassGroup, ClassSession, Holiday
from models.course import Course, Room
from models.teacher import Teacher
from models.user import ActivityLog
from datetime import datetime, timedelta

classes_bp = Blueprint('classes', __name__)


@classes_bp.route('/')
@login_required
def index():
    page = request.args.get('page', 1, type=int)
    status = request.args.get('status', 'active')
    search = request.args.get('search', '')
    
    query = ClassGroup.query
    if status:
        query = query.filter_by(status=status)
    if search:
        query = query.filter(ClassGroup.name.contains(search) | ClassGroup.class_code.contains(search))
    
    classes = query.order_by(ClassGroup.created_at.desc()).paginate(page=page, per_page=20)
    return render_template('classes/index.html', classes=classes, status=status, search=search)


@classes_bp.route('/add', methods=['GET', 'POST'])
@login_required
def add():
    if request.method == 'POST':
        last = ClassGroup.query.order_by(ClassGroup.id.desc()).first()
        next_num = (last.id + 1) if last else 1
        
        course = Course.query.get(request.form['course_id'])
        prefix = course.code[:2].upper() if course else 'CL'
        code = f'{prefix}-1405-{next_num:02d}'
        
        days = request.form.getlist('days')
        
        class_group = ClassGroup(
            class_code=code,
            name=request.form['name'],
            course_id=request.form['course_id'],
            teacher_id=request.form.get('teacher_id') or None,
            room_id=request.form.get('room_id') or None,
            max_capacity=int(request.form.get('max_capacity', 20)),
            days_of_week=str(days),
            start_time=request.form.get('start_time'),
            end_time=request.form.get('end_time'),
            start_date=get_jalali_date(request.form, 'start_date') if request.form.get('start_date') else None,
            end_date=get_jalali_date(request.form, 'end_date') if request.form.get('end_date') else None,
            status='active',
            branch_id=request.form.get('branch_id', 1),
            notes=request.form.get('notes'),
            created_by=current_user.id
        )
        
        db.session.add(class_group)
        
        log = ActivityLog(
            user_id=current_user.id, action='create', module='classes',
            entity_type='class',
            description=f'ایجاد کلاس: {class_group.name}',
            ip_address=request.remote_addr
        )
        db.session.add(log)
        db.session.commit()
        
        flash(f'کلاس "{class_group.name}" ایجاد شد', 'success')
        return redirect(url_for('classes.view', id=class_group.id))
    
    courses = Course.query.filter_by(is_active=True).all()
    teachers = Teacher.query.filter_by(is_active=True).all()
    rooms = Room.query.filter_by(status='available').all()
    
    return render_template('classes/add.html', courses=courses, teachers=teachers, rooms=rooms)


@classes_bp.route('/<int:id>')
@login_required
def view(id):
    class_group = ClassGroup.query.get_or_404(id)
    sessions = ClassSession.query.filter_by(class_id=id).order_by(ClassSession.session_date).all()
    students = [r.student for r in class_group.registrations.filter_by(status='active').all()]
    
    return render_template('classes/view.html', 
                         class_group=class_group, 
                         sessions=sessions, 
                         students=students)


@classes_bp.route('/<int:id>/sessions')
@login_required
def sessions(id):
    class_group = ClassGroup.query.get_or_404(id)
    sessions = ClassSession.query.filter_by(class_id=id).order_by(ClassSession.session_number).all()
    return render_template('classes/sessions.html', class_group=class_group, sessions=sessions)


@classes_bp.route('/<int:id>/generate-sessions', methods=['POST'])
@login_required
def generate_sessions(id):
    class_group = ClassGroup.query.get_or_404(id)
    
    if not class_group.start_date or not class_group.course:
        flash('تاریخ شروع و دوره باید مشخص باشد', 'error')
        return redirect(url_for('classes.view', id=id))
    
    total = class_group.course.total_sessions or 10
    days = eval(class_group.days_of_week) if class_group.days_of_week else [0, 2]
    
    current_date = class_group.start_date
    session_num = 1
    
    while session_num <= total:
        weekday = (current_date.weekday() + 2) % 7
        if weekday in days:
            session = ClassSession(
                class_id=id,
                session_number=session_num,
                session_date=current_date,
                start_time=class_group.start_time,
                end_time=class_group.end_time,
                status='scheduled'
            )
            db.session.add(session)
            session_num += 1
        current_date += timedelta(days=1)
    
    db.session.commit()
    flash(f'{total} جلسه ایجاد شد', 'success')
    return redirect(url_for('classes.sessions', id=id))


@classes_bp.route('/<int:id>/close', methods=['POST'])
@login_required
def close(id):
    class_group = ClassGroup.query.get_or_404(id)
    class_group.status = 'completed'
    db.session.commit()
    flash('کلاس بسته شد', 'success')
    return redirect(url_for('classes.view', id=id))


@classes_bp.route('/<int:class_id>/transfer', methods=['GET', 'POST'])
@login_required
def transfer(class_id):
    class_group = ClassGroup.query.get_or_404(class_id)
    
    if request.method == 'POST':
        from models.classes import ClassTransfer
        transfer = ClassTransfer(
            student_id=request.form['student_id'],
            from_class_id=class_id,
            to_class_id=request.form['to_class_id'],
            reason=request.form.get('reason'),
            fee_change=safe_float(request.form.get('fee_change')),
            approved_by=current_user.id
        )
        db.session.add(transfer)
        db.session.commit()
        flash('انتقال انجام شد', 'success')
        return redirect(url_for('classes.view', id=class_id))
    
    all_classes = ClassGroup.query.filter(
        ClassGroup.status == 'active',
        ClassGroup.id != class_id
    ).all()
    students = [r.student for r in class_group.registrations.filter_by(status='active').all()]
    
    return render_template('classes/transfer.html', 
                         class_group=class_group, 
                         all_classes=all_classes, 
                         students=students)


@classes_bp.route('/calendar')
@login_required
def calendar():
    classes = ClassGroup.query.filter_by(status='active').all()
    return render_template('classes/calendar.html', classes=classes)
