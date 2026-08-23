"""حضور و غیاب دستی + API دستگاه."""
from datetime import date
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, abort
from flask_login import login_required, current_user
from extensions import db, csrf
from models.attendance import (
    Attendance, TeacherAttendance, AttendanceDevice, AttendanceCredential, AttendanceDeviceLog,
)
from models.classes import ClassGroup, ClassSession
from models.student import Student
from models.teacher import Teacher
from models.registration import Registration
from utils.attendance_service import (
    save_session_roster, punch_device, new_device_token, today_stats, session_stats,
)

attendance_bp = Blueprint('attendance', __name__)

STATUS_FA = {
    'present': 'حاضر',
    'absent': 'غایب',
    'late': 'تأخیر',
    'leave': 'مرخصی',
    'scheduled': 'برنامه‌ریزی',
    'completed': 'تکمیل',
    'cancelled': 'لغو',
}


@attendance_bp.app_template_filter('att_status')
def att_status_filter(value):
    return STATUS_FA.get(value, value or '-')


@attendance_bp.route('/')
@login_required
def index():
    classes = ClassGroup.query.filter_by(status='active').order_by(ClassGroup.name).all()
    stats = today_stats()
    today_sessions = ClassSession.query.filter_by(session_date=date.today()).all()
    return render_template(
        'attendance/index.html',
        classes=classes,
        today_sessions=today_sessions,
        **stats,
    )


@attendance_bp.route('/class/<int:class_id>')
@login_required
def class_attendance(class_id):
    class_group = ClassGroup.query.get_or_404(class_id)
    sessions = ClassSession.query.filter_by(class_id=class_id).order_by(ClassSession.session_date).all()
    students = [r.student for r in class_group.registrations.filter_by(status='active').all()]
    return render_template('attendance/class.html', class_group=class_group, sessions=sessions, students=students)


@attendance_bp.route('/session/<int:session_id>', methods=['GET', 'POST'])
@login_required
def session_attendance(session_id):
    session = ClassSession.query.get_or_404(session_id)
    if request.method == 'POST':
        count = save_session_roster(session, request.form, current_user.id)
        db.session.commit()
        flash(f'حضور و غیاب {count} هنرجو ثبت شد', 'success')
        return redirect(url_for('attendance.class_attendance', class_id=session.class_id))

    att_map = {a.student_id: a for a in Attendance.query.filter_by(session_id=session_id).all()}
    students_data = []
    for reg in session.class_group.registrations.filter_by(status='active').all():
        students_data.append({'student': reg.student, 'attendance': att_map.get(reg.student_id)})
    teacher_att = None
    if session.class_group.teacher_id:
        teacher_att = TeacherAttendance.query.filter_by(
            session_id=session_id, teacher_id=session.class_group.teacher_id
        ).first()
    return render_template(
        'attendance/session.html',
        session=session,
        students=students_data,
        teacher_att=teacher_att,
        stats=session_stats(session_id),
    )


@attendance_bp.route('/student/<int:student_id>')
@login_required
def student_attendance(student_id):
    student = Student.query.get_or_404(student_id)
    registrations = Registration.query.filter_by(student_id=student_id).all()
    all_records = Attendance.query.filter_by(student_id=student_id).order_by(Attendance.created_at.desc()).all()
    total = len(all_records)
    present = sum(1 for r in all_records if r.status in ('present', 'late'))
    absent = sum(1 for r in all_records if r.status == 'absent')
    late = sum(1 for r in all_records if r.status == 'late')
    leave = sum(1 for r in all_records if r.status == 'leave')
    percentage = round(present / total * 100, 1) if total else 0

    class_stats = []
    for reg in registrations:
        if not reg.class_id:
            continue
        session_ids = [s.id for s in ClassSession.query.filter_by(class_id=reg.class_id).all()]
        class_att = Attendance.query.filter(
            Attendance.session_id.in_(session_ids), Attendance.student_id == student_id
        ).all() if session_ids else []
        class_total = len(class_att)
        class_present = sum(1 for a in class_att if a.status in ('present', 'late'))
        class_stats.append({
            'registration': reg,
            'total': class_total,
            'present': class_present,
            'absent': sum(1 for a in class_att if a.status == 'absent'),
            'percentage': round(class_present / class_total * 100, 1) if class_total else 0,
        })
    return render_template(
        'attendance/student.html',
        student=student, registrations=registrations, records=all_records[:80],
        total=total, present=present, absent=absent, late=late, leave=leave,
        percentage=percentage, class_stats=class_stats,
    )


@attendance_bp.route('/teacher/<int:teacher_id>')
@login_required
def teacher_attendance(teacher_id):
    teacher = Teacher.query.get_or_404(teacher_id)
    records = TeacherAttendance.query.filter_by(teacher_id=teacher_id).order_by(
        TeacherAttendance.created_at.desc()
    ).all()
    total_hours = sum(r.teaching_hours or 0 for r in records)
    present_count = sum(1 for r in records if r.status != 'absent')
    return render_template(
        'attendance/teacher.html',
        teacher=teacher, records=records,
        total_hours=total_hours, total_sessions=len(records), present_count=present_count,
    )


@attendance_bp.route('/report')
@login_required
def report():
    classes = ClassGroup.query.filter_by(status='active').all()
    class_stats = []
    for cls in classes:
        session_ids = [s.id for s in cls.sessions.all()]
        if session_ids:
            total = Attendance.query.filter(Attendance.session_id.in_(session_ids)).count()
            present = Attendance.query.filter(
                Attendance.session_id.in_(session_ids),
                Attendance.status.in_(['present', 'late']),
            ).count()
        else:
            total = present = 0
        class_stats.append({
            'class': cls,
            'total': total,
            'present': present,
            'absent': total - present,
            'rate': round(present / total * 100, 1) if total else 0,
        })
    return render_template('attendance/report.html', class_stats=class_stats)


@attendance_bp.route('/bulk', methods=['GET', 'POST'], endpoint='bulk')
@attendance_bp.route('/bulk-attendance', methods=['GET', 'POST'], endpoint='bulk_attendance')
@login_required
def bulk_attendance():
    if request.method == 'POST':
        class_id = request.form.get('class_id', type=int)
        session_id = request.form.get('session_id', type=int)
        session = ClassSession.query.filter_by(id=session_id, class_id=class_id).first()
        if not session:
            flash('کلاس یا جلسه معتبر نیست', 'danger')
            return redirect(url_for('attendance.bulk'))
        return redirect(url_for('attendance.session_attendance', session_id=session.id))
    classes = ClassGroup.query.filter_by(status='active').all()
    return render_template('attendance/bulk.html', classes=classes)


@attendance_bp.route('/api/class-sessions/<int:class_id>')
@login_required
def get_sessions(class_id):
    sessions = ClassSession.query.filter_by(class_id=class_id).order_by(ClassSession.session_date).all()
    return jsonify([{
        'id': s.id,
        'number': s.session_number,
        'date': s.session_date.isoformat() if s.session_date else '',
        'status': s.status,
        'topic': s.topic or '',
    } for s in sessions])


@attendance_bp.route('/statistics')
@login_required
def statistics():
    total_records = Attendance.query.count()
    total_present = Attendance.query.filter(Attendance.status.in_(['present', 'late'])).count()
    total_absent = Attendance.query.filter_by(status='absent').count()
    total_late = Attendance.query.filter_by(status='late').count()
    overall_rate = round(total_present / total_records * 100, 1) if total_records else 0
    absent_students = db.session.query(
        Student.id, Student.first_name, Student.last_name,
        db.func.count(Attendance.id).label('absent_count')
    ).join(Attendance).filter(
        Attendance.status == 'absent'
    ).group_by(Student.id).order_by(
        db.func.count(Attendance.id).desc()
    ).limit(15).all()
    return render_template(
        'attendance/statistics.html',
        total_records=total_records, total_present=total_present,
        total_absent=total_absent, total_late=total_late,
        overall_rate=overall_rate, absent_students=absent_students,
    )


@attendance_bp.route('/devices', methods=['GET', 'POST'])
@login_required
def devices():
    if not current_user.is_admin:
        abort(403)
    if request.method == 'POST':
        name = (request.form.get('name') or '').strip()
        code = (request.form.get('code') or '').strip().upper()
        if not name or not code:
            flash('نام و کد دستگاه الزامی است', 'danger')
            return redirect(url_for('attendance.devices'))
        if AttendanceDevice.query.filter_by(code=code).first():
            flash('این کد دستگاه تکراری است', 'danger')
            return redirect(url_for('attendance.devices'))
        device = AttendanceDevice(
            name=name,
            code=code,
            device_type=request.form.get('device_type') or 'rfid',
            location=request.form.get('location'),
            api_token=new_device_token(),
            is_active=True,
        )
        db.session.add(device)
        db.session.commit()
        flash(f'دستگاه ثبت شد. توکن را در دستگاه ذخیره کنید: {device.api_token}', 'success')
        return redirect(url_for('attendance.devices'))
    items = AttendanceDevice.query.order_by(AttendanceDevice.created_at.desc()).all()
    creds = AttendanceCredential.query.order_by(AttendanceCredential.id.desc()).limit(50).all()
    logs = AttendanceDeviceLog.query.order_by(AttendanceDeviceLog.created_at.desc()).limit(40).all()
    students = Student.query.filter_by(status='active').order_by(Student.last_name).limit(400).all()
    teachers = Teacher.query.filter_by(is_active=True).all()
    return render_template(
        'attendance/devices.html',
        devices=items, credentials=creds, logs=logs,
        students=students, teachers=teachers,
    )


@attendance_bp.route('/devices/<int:id>/toggle', methods=['POST'])
@login_required
def toggle_device(id):
    if not current_user.is_admin:
        abort(403)
    device = AttendanceDevice.query.get_or_404(id)
    device.is_active = not device.is_active
    db.session.commit()
    flash('وضعیت دستگاه تغییر کرد', 'success')
    return redirect(url_for('attendance.devices'))


@attendance_bp.route('/credentials', methods=['POST'])
@login_required
def add_credential():
    if not current_user.is_admin:
        abort(403)
    uid = (request.form.get('uid') or '').strip()
    person_type = request.form.get('person_type')
    person_id = request.form.get('person_id', type=int)
    if not uid or person_type not in ('student', 'teacher') or not person_id:
        flash('شناسه کارت و شخص معتبر نیست', 'danger')
        return redirect(url_for('attendance.devices'))
    if AttendanceCredential.query.filter_by(uid=uid).first():
        flash('این UID قبلاً ثبت شده', 'danger')
        return redirect(url_for('attendance.devices'))
    db.session.add(AttendanceCredential(
        uid=uid,
        person_type=person_type,
        person_id=person_id,
        method=request.form.get('method') or 'card',
        is_active=True,
    ))
    db.session.commit()
    flash('کارت / RFID به پرونده متصل شد', 'success')
    return redirect(url_for('attendance.devices'))


@attendance_bp.route('/device/punch', methods=['POST'])
@csrf.exempt
def device_punch():
    """
    API دستگاه:
    POST /attendance/device/punch
    Header: X-Device-Token: <token>
    JSON: {"uid": "CARD123", "event": "in"|"out", "method": "rfid"}
    """
    token = request.headers.get('X-Device-Token') or request.args.get('token') or ''
    device = AttendanceDevice.query.filter_by(api_token=token, is_active=True).first()
    if not device:
        return jsonify({'ok': False, 'error': 'unauthorized_device'}), 401
    data = request.get_json(silent=True) or request.form.to_dict()
    uid = (data.get('uid') or data.get('identifier') or data.get('card') or '').strip()
    if not uid:
        return jsonify({'ok': False, 'error': 'uid_required'}), 400
    result = punch_device(
        device,
        uid,
        event=(data.get('event') or 'in').lower(),
        method=data.get('method') or device.device_type or 'rfid',
        raw=data,
    )
    db.session.commit()
    return jsonify(result), (200 if result.get('ok') else 422)
