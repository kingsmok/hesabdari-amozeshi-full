"""منطق واحد حضور و غیاب — دستی و دستگاه از همین توابع استفاده می‌کنند."""
from __future__ import annotations

import json
import secrets
from datetime import datetime, date, timedelta

from extensions import db
from models.attendance import (
    Attendance, TeacherAttendance, AttendanceDevice, AttendanceCredential,
    AttendanceDeviceLog, VALID_STATUSES, VALID_METHODS,
)
from models.classes import ClassSession, ClassGroup
from models.registration import Registration
from models.student import Student
from models.teacher import Teacher


def normalize_status(value: str) -> str:
    value = (value or 'absent').strip().lower()
    if value in ('excused', 'مرخصی'):
        return 'leave'
    if value in VALID_STATUSES:
        return value
    return 'absent'


def _parse_hhmm(value: str | None):
    if not value:
        return None
    try:
        parts = value.strip().split(':')
        return int(parts[0]) * 60 + int(parts[1])
    except (ValueError, IndexError, TypeError):
        return None


def compute_late_minutes(session: ClassSession, arrival: str | None) -> int:
    start = _parse_hhmm(session.start_time)
    arr = _parse_hhmm(arrival)
    if start is None or arr is None:
        return 0
    return max(0, arr - start)


def compute_duration(arrival: str | None, departure: str | None) -> int | None:
    a = _parse_hhmm(arrival)
    d = _parse_hhmm(departure)
    if a is None or d is None or d < a:
        return None
    return d - a


def teaching_hours(session: ClassSession, arrival: str | None, departure: str | None) -> float:
    minutes = compute_duration(arrival or session.start_time, departure or session.end_time)
    if minutes is None:
        start = _parse_hhmm(session.start_time)
        end = _parse_hhmm(session.end_time)
        if start is None or end is None or end < start:
            return 0
        minutes = end - start
    return round(minutes / 60.0, 2)


def upsert_student_attendance(
    session: ClassSession,
    student_id: int,
    status: str,
    *,
    arrival=None,
    departure=None,
    notes=None,
    leave_reason=None,
    method='manual',
    device_id=None,
    recorded_by=None,
    device_data=None,
) -> Attendance:
    status = normalize_status(status)
    method = method if method in VALID_METHODS else 'manual'
    late = compute_late_minutes(session, arrival) if status in ('present', 'late') else 0
    if status == 'present' and late >= 10:
        status = 'late'
    row = Attendance.query.filter_by(session_id=session.id, student_id=student_id).first()
    if row is None:
        row = Attendance(session_id=session.id, student_id=student_id)
        db.session.add(row)
    row.status = status
    if arrival:
        row.arrival_time = arrival
    if departure:
        row.departure_time = departure
    row.duration_minutes = compute_duration(row.arrival_time, row.departure_time)
    row.late_minutes = late
    row.notes = notes
    row.leave_reason = leave_reason
    row.entry_method = method
    row.device_id = device_id
    row.device_data = device_data
    if recorded_by:
        row.recorded_by = recorded_by
    return row


def upsert_teacher_attendance(
    session: ClassSession,
    teacher_id: int,
    status: str,
    *,
    arrival=None,
    departure=None,
    notes=None,
    method='manual',
    device_id=None,
    recorded_by=None,
) -> TeacherAttendance:
    status = normalize_status(status)
    row = TeacherAttendance.query.filter_by(session_id=session.id, teacher_id=teacher_id).first()
    if row is None:
        row = TeacherAttendance(session_id=session.id, teacher_id=teacher_id)
        db.session.add(row)
    row.status = status
    if arrival:
        row.arrival_time = arrival
    if departure:
        row.departure_time = departure
    row.late_minutes = compute_late_minutes(session, arrival)
    row.teaching_hours = teaching_hours(session, row.arrival_time, row.departure_time) if status != 'absent' else 0
    row.notes = notes
    row.entry_method = method
    row.device_id = device_id
    if recorded_by:
        row.recorded_by = recorded_by
    return row


def save_session_roster(session: ClassSession, form, user_id: int) -> int:
    """ثبت فرم دستی جلسه؛ یک تراکنش برای کل کلاس."""
    regs = session.class_group.registrations.filter_by(status='active').all()
    count = 0
    for reg in regs:
        sid = str(reg.student_id)
        upsert_student_attendance(
            session,
            reg.student_id,
            form.get(f'status_{sid}', 'absent'),
            arrival=form.get(f'arrival_{sid}') or None,
            departure=form.get(f'departure_{sid}') or None,
            notes=form.get(f'notes_{sid}') or None,
            leave_reason=form.get(f'leave_{sid}') or None,
            method='manual',
            recorded_by=user_id,
        )
        count += 1

    if session.class_group.teacher_id:
        upsert_teacher_attendance(
            session,
            session.class_group.teacher_id,
            form.get('teacher_status', 'present'),
            arrival=form.get('teacher_arrival') or None,
            departure=form.get('teacher_departure') or None,
            notes=form.get('teacher_notes') or None,
            method='manual',
            recorded_by=user_id,
        )
    session.status = 'completed'
    return count


def find_today_session_for_student(student_id: int, when: datetime) -> ClassSession | None:
    regs = Registration.query.filter_by(student_id=student_id, status='active').all()
    class_ids = [r.class_id for r in regs if r.class_id]
    if not class_ids:
        return None
    sessions = ClassSession.query.filter(
        ClassSession.class_id.in_(class_ids),
        ClassSession.session_date == when.date(),
        ClassSession.status != 'cancelled',
    ).all()
    if not sessions:
        return None
    now_min = when.hour * 60 + when.minute
    best = None
    best_delta = 10**9
    for sess in sessions:
        start = _parse_hhmm(sess.start_time)
        end = _parse_hhmm(sess.end_time)
        if start is None:
            return sess
        window_start = start - 60
        window_end = (end if end is not None else start + 180) + 60
        if window_start <= now_min <= window_end:
            delta = abs(now_min - start)
            if delta < best_delta:
                best, best_delta = sess, delta
    return best or sessions[0]


def find_today_session_for_teacher(teacher_id: int, when: datetime) -> ClassSession | None:
    classes = ClassGroup.query.filter_by(teacher_id=teacher_id, status='active').all()
    class_ids = [c.id for c in classes]
    if not class_ids:
        return None
    return ClassSession.query.filter(
        ClassSession.class_id.in_(class_ids),
        ClassSession.session_date == when.date(),
        ClassSession.status != 'cancelled',
    ).order_by(ClassSession.start_time).first()


def resolve_person(identifier: str):
    ident = (identifier or '').strip()
    if not ident:
        return None, None
    cred = AttendanceCredential.query.filter_by(uid=ident, is_active=True).first()
    if cred:
        return cred.person_type, cred.person_id
    student = Student.query.filter(
        db.or_(Student.student_code == ident, Student.national_code == ident, Student.mobile == ident)
    ).first()
    if student:
        return 'student', student.id
    teacher = Teacher.query.filter(
        db.or_(Teacher.teacher_code == ident, Teacher.national_code == ident, Teacher.mobile == ident)
    ).first()
    if teacher:
        return 'teacher', teacher.id
    return None, None


def punch_device(device: AttendanceDevice, identifier: str, event: str = 'in', method: str = 'rfid', raw=None):
    now = datetime.now()
    hhmm = now.strftime('%H:%M')
    person_type, person_id = resolve_person(identifier)
    log = AttendanceDeviceLog(
        device_id=device.id,
        uid=identifier,
        payload=json.dumps(raw, ensure_ascii=False) if raw is not None else None,
    )
    db.session.add(log)
    device.last_seen_at = now

    if not person_type:
        log.result = 'unknown'
        log.message = 'شناسه در سیستم ثبت نشده'
        return {'ok': False, 'error': 'unknown_identifier'}

    if person_type == 'student':
        session = find_today_session_for_student(person_id, now)
        if not session:
            log.result = 'no_session'
            log.message = 'جلسه‌ای برای امروز پیدا نشد'
            return {'ok': False, 'error': 'no_session_today'}
        if event == 'out':
            row = Attendance.query.filter_by(session_id=session.id, student_id=person_id).first()
            if row:
                row.departure_time = hhmm
                row.duration_minutes = compute_duration(row.arrival_time, hhmm)
            else:
                upsert_student_attendance(session, person_id, 'present', arrival=hhmm, departure=hhmm, method=method, device_id=device.id)
        else:
            upsert_student_attendance(session, person_id, 'present', arrival=hhmm, method=method, device_id=device.id)
        student = db.session.get(Student, person_id)
        log.result = 'ok'
        log.message = f'{student.full_name if student else person_id} — جلسه {session.session_number}'
        return {
            'ok': True,
            'person_type': 'student',
            'name': student.full_name if student else '',
            'session_id': session.id,
            'event': event,
            'time': hhmm,
        }

    session = find_today_session_for_teacher(person_id, now)
    if not session:
        log.result = 'no_session'
        log.message = 'جلسه‌ای برای مدرس امروز نیست'
        return {'ok': False, 'error': 'no_session_today'}
    if event == 'out':
        row = TeacherAttendance.query.filter_by(session_id=session.id, teacher_id=person_id).first()
        if row:
            row.departure_time = hhmm
            row.teaching_hours = teaching_hours(session, row.arrival_time, hhmm)
        else:
            upsert_teacher_attendance(session, person_id, 'present', arrival=hhmm, departure=hhmm, method=method, device_id=device.id)
    else:
        upsert_teacher_attendance(session, person_id, 'present', arrival=hhmm, method=method, device_id=device.id)
    teacher = db.session.get(Teacher, person_id)
    log.result = 'ok'
    log.message = f'{teacher.full_name if teacher else person_id}'
    return {
        'ok': True,
        'person_type': 'teacher',
        'name': teacher.full_name if teacher else '',
        'session_id': session.id,
        'event': event,
        'time': hhmm,
    }


def new_device_token() -> str:
    return secrets.token_hex(24)


def ensure_attendance_indexes():
    """SQLite create_all ستون جدید به جدول قدیمی اضافه نمی‌کند."""
    alters = [
        "ALTER TABLE attendances ADD COLUMN device_id INTEGER",
        "ALTER TABLE attendances ADD COLUMN updated_at DATETIME",
        "ALTER TABLE teacher_attendances ADD COLUMN entry_method VARCHAR(20)",
        "ALTER TABLE teacher_attendances ADD COLUMN device_id INTEGER",
    ]
    for sql in alters:
        try:
            db.session.execute(db.text(sql))
            db.session.commit()
        except Exception:
            db.session.rollback()
    statements = [
        'CREATE UNIQUE INDEX IF NOT EXISTS uq_att_session_student ON attendances(session_id, student_id)',
        'CREATE UNIQUE INDEX IF NOT EXISTS uq_tatt_session_teacher ON teacher_attendances(session_id, teacher_id)',
    ]
    for sql in statements:
        try:
            db.session.execute(db.text(sql))
            db.session.commit()
        except Exception:
            db.session.rollback()


def session_stats(session_id: int) -> dict:
    rows = Attendance.query.filter_by(session_id=session_id).all()
    return {
        'total': len(rows),
        'present': sum(1 for r in rows if r.status in ('present', 'late')),
        'absent': sum(1 for r in rows if r.status == 'absent'),
        'late': sum(1 for r in rows if r.status == 'late'),
        'leave': sum(1 for r in rows if r.status == 'leave'),
    }


def today_stats(today: date | None = None) -> dict:
    today = today or date.today()
    session_ids = [s.id for s in ClassSession.query.filter_by(session_date=today).all()]
    if not session_ids:
        return {'today_total': 0, 'today_present': 0, 'today_absent': 0}
    q = Attendance.query.filter(Attendance.session_id.in_(session_ids))
    total = q.count()
    present = q.filter(Attendance.status.in_(['present', 'late'])).count()
    absent = q.filter_by(status='absent').count()
    return {'today_total': total, 'today_present': present, 'today_absent': absent}
