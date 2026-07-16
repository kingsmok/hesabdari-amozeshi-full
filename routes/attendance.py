"""
ماژول حضور و غیاب — بازطراحی کامل
"""
from datetime import datetime, date, timedelta
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from extensions import db

attendance_bp = Blueprint('attendance', __name__)


@attendance_bp.route('/')
@login_required
def index():
    """لیست کلاس‌ها برای حضور و غیاب"""
    from models.classes import ClassGroup
    classes = ClassGroup.query.filter_by(status='active').all()
    
    # آمار امروز
    today = date.today()
    from models.attendance import Attendance
    today_total = Attendance.query.filter(
        db.func.date(Attendance.created_at) == today
    ).count()
    today_present = Attendance.query.filter(
        db.func.date(Attendance.created_at) == today,
        Attendance.status == 'present'
    ).count()
    
    return render_template('attendance/index.html', 
                         classes=classes, 
                         today_total=today_total,
                         today_present=today_present)


@attendance_bp.route('/class/<int:class_id>')
@login_required
def class_attendance(class_id):
    """لیست جلسات یک کلاس"""
    from models.classes import ClassGroup, ClassSession
    class_group = ClassGroup.query.get_or_404(class_id)
    sessions = ClassSession.query.filter_by(class_id=class_id).order_by(ClassSession.session_date).all()
    students = [r.student for r in class_group.registrations.filter_by(status='active').all()]
    return render_template('attendance/class.html', class_group=class_group, sessions=sessions, students=students)


@attendance_bp.route('/session/<int:session_id>', methods=['GET', 'POST'])
@login_required
def session_attendance(session_id):
    """ثبت حضور و غیاب یک جلسه"""
    from models.classes import ClassSession
    from models.attendance import Attendance
    from models.system import Notification
    
    session = ClassSession.query.get_or_404(session_id)
    
    if request.method == 'POST':
        registrations = session.class_group.registrations.filter_by(status='active').all()
        
        for reg in registrations:
            sid = str(reg.student_id)
            status = request.form.get(f'status_{sid}', 'absent')
            arrival = request.form.get(f'arrival_{sid}')
            departure = request.form.get(f'departure_{sid}')
            notes = request.form.get(f'notes_{sid}', '')
            
            existing = Attendance.query.filter_by(
                session_id=session_id, student_id=reg.student_id
            ).first()
            
            if existing:
                existing.status = status
                existing.arrival_time = arrival
                existing.departure_time = departure
                existing.notes = notes
            else:
                att = Attendance(
                    session_id=session_id,
                    student_id=reg.student_id,
                    status=status,
                    arrival_time=arrival,
                    departure_time=departure,
                    notes=notes,
                    entry_method='manual',
                    recorded_by=current_user.id
                )
                db.session.add(att)
            
            # ارسال اعلان غیبت
            if status == 'absent':
                notif = Notification(
                    user_id=1,
                    title=f'غیبت: {reg.student.full_name}',
                    body=f'در جلسه {session.session_number} کلاس {session.class_group.name}',
                    notif_type='attendance'
                )
                db.session.add(notif)
        
        session.status = 'completed'
        db.session.commit()
        flash('حضور و غیاب ثبت شد', 'success')
        return redirect(url_for('attendance.class_attendance', class_id=session.class_id))
    
    # دریافت حضور و غیاب قبلی
    students_data = []
    registrations = session.class_group.registrations.filter_by(status='active').all()
    for reg in registrations:
        att = Attendance.query.filter_by(session_id=session_id, student_id=reg.student_id).first()
        students_data.append({'student': reg.student, 'attendance': att})
    
    return render_template('attendance/session.html', session=session, students=students_data)


@attendance_bp.route('/student/<int:student_id>')
@login_required
def student_attendance(student_id):
    """حضور و غیاب یک هنرجو"""
    from models.student import Student
    from models.attendance import Attendance
    from models.registration import Registration
    
    student = Student.query.get_or_404(student_id)
    registrations = Registration.query.filter_by(student_id=student_id).all()
    
    # آمار کلی
    all_records = Attendance.query.filter_by(student_id=student_id).all()
    total = len(all_records)
    present = sum(1 for r in all_records if r.status == 'present')
    absent = sum(1 for r in all_records if r.status == 'absent')
    late = sum(1 for r in all_records if r.status == 'late')
    percentage = round(present / total * 100, 1) if total > 0 else 0
    
    # آمار هر کلاس
    class_stats = []
    for reg in registrations:
        from models.attendance import Attendance as Att
        from models.classes import ClassSession
        sessions = ClassSession.query.filter_by(class_id=reg.class_id).all()
        session_ids = [s.id for s in sessions]
        class_att = Att.query.filter(Att.session_id.in_(session_ids), Att.student_id == student_id).all() if session_ids else []
        class_total = len(class_att)
        class_present = sum(1 for a in class_att if a.status == 'present')
        class_pct = round(class_present / class_total * 100, 1) if class_total > 0 else 0
        
        class_stats.append({
            'registration': reg,
            'total': class_total,
            'present': class_present,
            'absent': class_total - class_present,
            'percentage': class_pct
        })
    
    return render_template('attendance/student.html',
                         student=student, registrations=registrations,
                         total=total, present=present, absent=absent, late=late,
                         percentage=percentage, class_stats=class_stats)


@attendance_bp.route('/teacher/<int:teacher_id>')
@login_required
def teacher_attendance(teacher_id):
    """حضور و غیاب مدرس"""
    from models.teacher import Teacher
    from models.attendance import TeacherAttendance
    
    teacher = Teacher.query.get_or_404(teacher_id)
    records = TeacherAttendance.query.filter_by(teacher_id=teacher_id).order_by(TeacherAttendance.created_at.desc()).all()
    
    total_hours = sum(r.teaching_hours or 0 for r in records)
    total_sessions = len(records)
    present_count = sum(1 for r in records if r.status == 'present')
    
    return render_template('attendance/teacher.html',
                         teacher=teacher, records=records,
                         total_hours=total_hours, total_sessions=total_sessions,
                         present_count=present_count)


@attendance_bp.route('/report')
@login_required
def report():
    """گزارش حضور و غیاب"""
    from models.classes import ClassGroup
    from models.attendance import Attendance
    
    class_id = request.args.get('class_id', '', type=str)
    
    # آمار کلاس‌ها
    classes = ClassGroup.query.filter_by(status='active').all()
    class_stats = []
    
    for cls in classes:
        sessions = cls.sessions.all()
        session_ids = [s.id for s in sessions]
        
        if session_ids:
            total = Attendance.query.filter(Attendance.session_id.in_(session_ids)).count()
            present = Attendance.query.filter(
                Attendance.session_id.in_(session_ids),
                Attendance.status == 'present'
            ).count()
        else:
            total = 0
            present = 0
        
        rate = round(present / total * 100, 1) if total > 0 else 0
        
        class_stats.append({
            'class': cls,
            'total': total,
            'present': present,
            'absent': total - present,
            'rate': rate
        })
    
    return render_template('attendance/report.html', class_stats=class_stats)


@attendance_bp.route('/bulk', methods=['GET', 'POST'])
@login_required
def bulk_attendance():
    """ثبت حضور و غیاب گروهی"""
    from models.classes import ClassGroup
    
    if request.method == 'POST':
        class_id = int(request.form['class_id'])
        return redirect(url_for('attendance.session_attendance', session_id=request.form.get('session_id')))
    
    classes = ClassGroup.query.filter_by(status='active').all()
    return render_template('attendance/bulk.html', classes=classes)


@attendance_bp.route('/api/class-sessions/<int:class_id>')
@login_required
def get_sessions(class_id):
    """API دریافت جلسات یک کلاس"""
    from models.classes import ClassSession
    sessions = ClassSession.query.filter_by(class_id=class_id).order_by(ClassSession.session_date).all()
    return jsonify([{
        'id': s.id,
        'number': s.session_number,
        'date': s.session_date.isoformat() if s.session_date else '',
        'status': s.status,
        'topic': s.topic or ''
    } for s in sessions])


@attendance_bp.route('/statistics')
@login_required
def statistics():
    """آمار کلی حضور و غیاب"""
    from models.attendance import Attendance
    from models.classes import ClassGroup
    from models.student import Student
    
    today = date.today()
    
    # آمار کلی
    total_records = Attendance.query.count()
    total_present = Attendance.query.filter_by(status='present').count()
    total_absent = Attendance.query.filter_by(status='absent').count()
    total_late = Attendance.query.filter_by(status='late').count()
    
    overall_rate = round(total_present / total_records * 100, 1) if total_records > 0 else 0
    
    # هنرجویان با غیبت زیاد
    from sqlalchemy import func
    absent_students = db.session.query(
        Student.id, Student.first_name, Student.last_name,
        func.count(Attendance.id).label('absent_count')
    ).join(Attendance).filter(
        Attendance.status == 'absent'
    ).group_by(Student.id).order_by(
        func.count(Attendance.id).desc()
    ).limit(10).all()
    
    return render_template('attendance/statistics.html',
                         total_records=total_records,
                         total_present=total_present,
                         total_absent=total_absent,
                         total_late=total_late,
                         overall_rate=overall_rate,
                         absent_students=absent_students)
