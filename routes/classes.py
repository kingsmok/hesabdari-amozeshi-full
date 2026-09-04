"""Classes routes"""
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from license_client import license_required, licensed_section
from extensions import db
from utils.document_numbers import next_sequence_number
from utils.form_helpers import get_jalali_date, safe_float, safe_int
from utils.jalali import current_jalali_year
from models.classes import ClassGroup, ClassSession, Holiday
from models.course import Course, Room
from models.teacher import Teacher
# لاگ فعالیت از نقطهٔ مشترک utils/activity_log استفاده می‌شود
from datetime import datetime, timedelta
import json

classes_bp = Blueprint('classes', __name__)


@classes_bp.route('/')
@license_required
@login_required
@licensed_section('classes')
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
        
        class_name = (request.form.get('name') or '').strip()
        course_id = request.form.get('course_id', type=int)
        course = Course.query.filter_by(id=course_id, is_active=True).first() if course_id else None
        if not class_name or not course:
            flash('نام کلاس یا دوره انتخاب‌شده معتبر نیست', 'danger')
            return redirect(url_for('classes.add'))
        max_capacity = request.form.get('max_capacity', 20, type=int)
        if not max_capacity or max_capacity < 1:
            flash('ظرفیت کلاس باید بیشتر از صفر باشد', 'danger')
            return redirect(url_for('classes.add'))

        # پیشوند از کد دوره می‌آید ⇒ قالب ثابت نیست؛ فقط عدد از شمارنده پایدار
        prefix = course.code[:2].upper() if course.code else 'CL'
        code = f'{prefix}-{current_jalali_year()}-{next_sequence_number("class"):02d}'
        
        days = [int(day) for day in request.form.getlist('days') if day.isdigit() and 0 <= int(day) <= 6]
        if not days:
            flash('حداقل یک روز برای تشکیل کلاس انتخاب کنید', 'danger')
            return redirect(url_for('classes.add'))
        start_date = get_jalali_date(request.form, 'start_date') if request.form.get('start_date') else None
        end_date = get_jalali_date(request.form, 'end_date') if request.form.get('end_date') else None
        if start_date and end_date and end_date < start_date:
            flash('تاریخ پایان کلاس نمی‌تواند قبل از تاریخ شروع باشد', 'danger')
            return redirect(url_for('classes.add'))

        class_group = ClassGroup(
            class_code=code,
            name=class_name,
            course_id=course.id,
            teacher_id=request.form.get('teacher_id') or None,
            room_id=request.form.get('room_id') or None,
            max_capacity=max_capacity,
            days_of_week=json.dumps(days),
            start_time=request.form.get('start_time'),
            end_time=request.form.get('end_time'),
            start_date=start_date,
            end_date=end_date,
            status='active',
            branch_id=request.form.get('branch_id', 1),
            notes=request.form.get('notes'),
            created_by=current_user.id
        )
        
        db.session.add(class_group)
        
        # نقطهٔ مشترک لاگ (DRY)
        from utils.activity_log import log_activity
        log_activity('create', f'ایجاد کلاس: {class_group.name}',
                     module='classes', entity_type='class', entity_id=class_group.id)
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
    
    if ClassSession.query.filter_by(class_id=id).count():
        flash('جلسات این کلاس قبلاً تولید شده‌اند', 'warning')
        return redirect(url_for('classes.sessions', id=id))

    total = max(1, min(class_group.course.total_sessions or 10, 365))
    try:
        try:
            raw_days = json.loads(class_group.days_of_week or '[]')
        except json.JSONDecodeError:
            from ast import literal_eval
            raw_days = literal_eval(class_group.days_of_week or '[]')
        days = [int(day) for day in raw_days if 0 <= int(day) <= 6]
    except (TypeError, ValueError, SyntaxError):
        days = []
    if not days:
        flash('روزهای تشکیل کلاس معتبر نیست؛ ابتدا کلاس را ویرایش کنید', 'danger')
        return redirect(url_for('classes.edit', id=id))

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
    if class_group.status == 'completed':
        flash('این کلاس قبلاً بسته شده است', 'warning')
        return redirect(url_for('classes.view', id=id))

    class_group.status = 'completed'
    completed_registrations = class_group.registrations.filter_by(status='active').all()
    for registration in completed_registrations:
        registration.status = 'completed'
    class_group.current_count = 0
    db.session.commit()
    flash(f'کلاس بسته و وضعیت {len(completed_registrations)} ثبت‌نام تکمیل شد', 'success')
    return redirect(url_for('classes.view', id=id))


@classes_bp.route('/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit(id):
    class_group = ClassGroup.query.get_or_404(id)
    
    if request.method == 'POST':
        course_id = request.form.get('course_id', type=int)
        course = Course.query.filter_by(id=course_id, is_active=True).first() if course_id else None
        max_capacity = request.form.get('max_capacity', 20, type=int)
        start_date = get_jalali_date(request.form, 'start_date') if request.form.get('start_date') else None
        end_date = get_jalali_date(request.form, 'end_date') if request.form.get('end_date') else None
        class_name = (request.form.get('name') or '').strip()
        if not class_name or not course or not max_capacity or max_capacity < max(1, class_group.current_count or 0):
            flash('نام، دوره یا ظرفیت کلاس معتبر نیست؛ ظرفیت نباید کمتر از هنرجویان فعال باشد', 'danger')
            return redirect(url_for('classes.edit', id=id))
        if start_date and end_date and end_date < start_date:
            flash('تاریخ پایان نمی‌تواند قبل از تاریخ شروع باشد', 'danger')
            return redirect(url_for('classes.edit', id=id))

        class_group.name = class_name
        class_group.course_id = course.id
        class_group.teacher_id = request.form.get('teacher_id', type=int)
        class_group.room_id = request.form.get('room_id', type=int)
        class_group.max_capacity = max_capacity
        selected_days = [int(day) for day in request.form.getlist('days') if day.isdigit() and 0 <= int(day) <= 6]
        if not selected_days:
            flash('حداقل یک روز برای تشکیل کلاس انتخاب کنید', 'danger')
            return redirect(url_for('classes.edit', id=id))
        class_group.days_of_week = json.dumps(selected_days)
        class_group.start_time = request.form.get('start_time')
        class_group.end_time = request.form.get('end_time')
        class_group.start_date = start_date
        class_group.end_date = end_date
        class_group.notes = request.form.get('notes')
        class_group.status = request.form.get('status', class_group.status)
        
        # نقطهٔ مشترک لاگ (DRY)
        from utils.activity_log import log_activity
        log_activity('edit', f'ویرایش کلاس: {class_group.name}',
                     module='classes', entity_type='class', entity_id=id)
        db.session.commit()
        
        flash(f'کلاس "{class_group.name}" بروزرسانی شد', 'success')
        return redirect(url_for('classes.view', id=id))
    
    courses = Course.query.filter_by(is_active=True).all()
    teachers = Teacher.query.filter_by(is_active=True).all()
    rooms = Room.query.filter_by(status='available').all()
    
    return render_template('classes/edit.html', 
                         class_group=class_group, 
                         courses=courses, 
                         teachers=teachers, 
                         rooms=rooms)


@classes_bp.route('/<int:id>/delete', methods=['POST'])
@login_required
def delete(id):
    class_group = ClassGroup.query.get_or_404(id)
    
    # بررسی ثبت‌نام فعال
    active_regs = class_group.registrations.filter_by(status='active').count()
    if active_regs > 0:
        flash(f'این کلاس دارای {active_regs} هنرجوی فعال است و قابل حذف نیست. ابتدا هنرجویان را منتقل یا حذف کنید.', 'danger')
        return redirect(url_for('classes.view', id=id))
    
    # حذف جلسات مرتبط
    ClassSession.query.filter_by(class_id=id).delete()
    
    class_name = class_group.name
    db.session.delete(class_group)
    
    # نقطهٔ مشترک لاگ (DRY)
    from utils.activity_log import log_activity
    log_activity('delete', f'حذف کلاس: {class_name}',
                 module='classes', entity_type='class', entity_id=id)
    db.session.commit()
    
    flash(f'کلاس "{class_name}" حذف شد', 'success')
    return redirect(url_for('classes.index'))


@classes_bp.route('/<int:class_id>/transfer', methods=['GET', 'POST'])
@login_required
def transfer(class_id):
    class_group = ClassGroup.query.get_or_404(class_id)
    
    if request.method == 'POST':
        from models.classes import ClassTransfer
        from models.registration import Registration

        student_id = request.form.get('student_id', type=int)
        target_id = request.form.get('to_class_id', type=int)
        registration = Registration.query.filter_by(
            student_id=student_id, class_id=class_id, status='active'
        ).first()
        target = ClassGroup.query.filter_by(id=target_id, status='active').first() if target_id else None

        if not registration or not target:
            flash('هنرجو یا کلاس مقصد معتبر نیست', 'danger')
            return redirect(url_for('classes.transfer', class_id=class_id))
        if target.id == class_group.id or target.course_id != class_group.course_id:
            flash('کلاس مقصد باید کلاس دیگری از همین دوره باشد', 'danger')
            return redirect(url_for('classes.transfer', class_id=class_id))
        if target.is_full:
            flash('ظرفیت کلاس مقصد تکمیل است', 'danger')
            return redirect(url_for('classes.transfer', class_id=class_id))

        transfer = ClassTransfer(
            student_id=student_id,
            from_class_id=class_id,
            to_class_id=target.id,
            reason=request.form.get('reason'),
            fee_change=safe_float(request.form.get('fee_change')),
            approved_by=current_user.id
        )
        registration.class_id = target.id
        registration.teacher_id = target.teacher_id
        db.session.add(transfer)
        db.session.flush()

        class_group.current_count = Registration.query.filter_by(class_id=class_id, status='active').count()
        target.current_count = Registration.query.filter_by(class_id=target.id, status='active').count()
        db.session.commit()
        flash(f'هنرجو به کلاس «{target.name}» منتقل شد', 'success')
        return redirect(url_for('classes.view', id=target.id))
    
    all_classes = ClassGroup.query.filter(
        ClassGroup.status == 'active',
        ClassGroup.id != class_id,
        ClassGroup.course_id == class_group.course_id
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
