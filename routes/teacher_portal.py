"""
پورتال اختصاصی مدرس — فقط اطلاعات خودش
"""
from datetime import datetime, date, timedelta
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from extensions import db

teacher_bp = Blueprint('teacher_portal', __name__)


def get_my_teacher():
    """پیدا کردن مدرس مرتبط با کاربر فعلی"""
    from models.teacher import Teacher
    # اتصال از طریق user_id
    teacher = Teacher.query.filter_by(user_id=current_user.id).first()
    if not teacher and current_user.is_admin:
        teacher = Teacher.query.filter_by(is_active=True).first()
    return teacher


@teacher_bp.route('/my')
@login_required
def my_dashboard():
    teacher = get_my_teacher()
    if not teacher:
        flash('پروفایل مدرس یافت نشد. لطفاً با مدیر تماس بگیرید.', 'error')
        return redirect(url_for('dashboard.index'))
    
    from models.classes import ClassGroup
    from models.attendance import TeacherAttendance
    
    today = datetime.utcnow()
    today_weekday = (today.weekday() + 2) % 7
    
    my_classes = ClassGroup.query.filter_by(teacher_id=teacher.id, status='active').all()
    today_classes = [c for c in my_classes if c.days_of_week and str(today_weekday) in c.days_of_week]
    total_students = sum(c.current_count or 0 for c in my_classes)
    total_sessions = sum(c.completed_sessions_count for c in my_classes)
    
    month_start = today.replace(day=1)
    month_hours = db.session.query(db.func.sum(TeacherAttendance.teaching_hours)).filter(
        TeacherAttendance.teacher_id == teacher.id,
        TeacherAttendance.created_at >= month_start
    ).scalar() or 0
    
    return render_template('teacher_portal/dashboard.html',
                         teacher=teacher, my_classes=my_classes,
                         today_classes=today_classes,
                         total_students=total_students,
                         total_sessions=total_sessions,
                         month_hours=month_hours)


@teacher_bp.route('/my/classes')
@login_required
def my_classes():
    from models.classes import ClassGroup
    teacher = get_my_teacher()
    if not teacher:
        return redirect(url_for('dashboard.index'))
    classes = ClassGroup.query.filter_by(teacher_id=teacher.id).order_by(ClassGroup.created_at.desc()).all()
    return render_template('teacher_portal/my_classes.html', teacher=teacher, classes=classes)


@teacher_bp.route('/my/classes/<int:id>')
@login_required
def my_class_detail(id):
    from models.classes import ClassGroup, ClassSession
    teacher = get_my_teacher()
    if not teacher:
        return redirect(url_for('dashboard.index'))
    cls = ClassGroup.query.get_or_404(id)
    if cls.teacher_id != teacher.id:
        flash('این کلاس متعلق به شما نیست', 'error')
        return redirect(url_for('teacher_portal.my_classes'))
    students = [r.student for r in cls.registrations.filter_by(status='active').all()]
    sessions = cls.sessions.order_by(ClassSession.session_date).all()
    return render_template('teacher_portal/my_class_detail.html',
                         teacher=teacher, cls=cls, students=students, sessions=sessions)


@teacher_bp.route('/my/students')
@login_required
def my_students():
    from models.classes import ClassGroup
    teacher = get_my_teacher()
    if not teacher:
        return redirect(url_for('dashboard.index'))
    classes = ClassGroup.query.filter_by(teacher_id=teacher.id, status='active').all()
    student_ids = set()
    students_data = []
    for cls in classes:
        for reg in cls.registrations.filter_by(status='active').all():
            if reg.student_id not in student_ids:
                student_ids.add(reg.student_id)
                students_data.append({'student': reg.student, 'class': cls, 'registration': reg})
    return render_template('teacher_portal/my_students.html', teacher=teacher, students_data=students_data)


@teacher_bp.route('/my/schedule')
@login_required
def my_schedule():
    from models.classes import ClassGroup
    teacher = get_my_teacher()
    if not teacher:
        return redirect(url_for('dashboard.index'))
    classes = ClassGroup.query.filter_by(teacher_id=teacher.id, status='active').all()
    days = ['شنبه', 'یکشنبه', 'دوشنبه', 'سه‌شنبه', 'چهارشنبه', 'پنجشنبه', 'جمعه']
    schedule = {i: [] for i in range(7)}
    for cls in classes:
        if cls.days_of_week:
            try:
                import json
                try:
                    day_indices = json.loads(cls.days_of_week)
                except json.JSONDecodeError:
                    from ast import literal_eval
                    day_indices = literal_eval(cls.days_of_week)
                for day in day_indices:
                    day = int(day)
                    if day in schedule:
                        schedule[day].append(cls)
            except (TypeError, ValueError, SyntaxError):
                continue
    return render_template('teacher_portal/my_schedule.html', teacher=teacher, schedule=schedule, days=days)


@teacher_bp.route('/my/attendance')
@login_required
def my_attendance():
    teacher = get_my_teacher()
    if not teacher:
        return redirect(url_for('dashboard.index'))
    from models.attendance import TeacherAttendance
    records = TeacherAttendance.query.filter_by(teacher_id=teacher.id).order_by(
        TeacherAttendance.created_at.desc()
    ).limit(50).all()
    total_hours = sum(r.teaching_hours or 0 for r in records)
    total_sessions = len(records)
    present = sum(1 for r in records if r.status == 'present')
    return render_template('teacher_portal/my_attendance.html',
                         teacher=teacher, records=records,
                         total_hours=total_hours, total_sessions=total_sessions, present=present)


@teacher_bp.route('/my/salary')
@login_required
def my_salary():
    teacher = get_my_teacher()
    if not teacher:
        return redirect(url_for('dashboard.index'))
    from models.finance import Payslip
    payslips = Payslip.query.filter_by(
        person_type='teacher', person_id=teacher.id
    ).order_by(Payslip.created_at.desc()).all()
    return render_template('teacher_portal/my_salary.html', teacher=teacher, payslips=payslips)


@teacher_bp.route('/my/evaluations')
@login_required
def my_evaluations():
    teacher = get_my_teacher()
    if not teacher:
        return redirect(url_for('dashboard.index'))
    from models.teacher import TeacherEvaluation
    evaluations = TeacherEvaluation.query.filter_by(teacher_id=teacher.id).order_by(
        TeacherEvaluation.created_at.desc()
    ).limit(20).all()
    avg_score = 0
    if evaluations:
        scores = [e.overall_satisfaction or 0 for e in evaluations]
        avg_score = round(sum(scores) / len(scores), 1)
    return render_template('teacher_portal/my_evaluations.html',
                         teacher=teacher, evaluations=evaluations, avg_score=avg_score)
