"""Attendance, teacher attendance, and device integration models."""
from datetime import datetime
from extensions import db


VALID_STATUSES = ('present', 'absent', 'late', 'leave')
VALID_METHODS = ('manual', 'fingerprint', 'card', 'rfid', 'face', 'qr', 'api')


class Attendance(db.Model):
    __tablename__ = 'attendances'
    __table_args__ = (
        db.UniqueConstraint('session_id', 'student_id', name='uq_att_session_student'),
        db.Index('ix_att_student', 'student_id'),
        db.Index('ix_att_status', 'status'),
    )

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('class_sessions.id'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)

    status = db.Column(db.String(20), default='present')
    arrival_time = db.Column(db.String(10))
    departure_time = db.Column(db.String(10))
    duration_minutes = db.Column(db.Integer)
    late_minutes = db.Column(db.Integer, default=0)
    leave_reason = db.Column(db.String(200))

    entry_method = db.Column(db.String(20), default='manual')
    device_id = db.Column(db.Integer, db.ForeignKey('attendance_devices.id'))
    device_data = db.Column(db.Text)

    notes = db.Column(db.Text)
    recorded_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    device = db.relationship('AttendanceDevice', backref='student_punches')

    def __repr__(self):
        return f'<Attendance student={self.student_id} session={self.session_id} {self.status}>'


class TeacherAttendance(db.Model):
    __tablename__ = 'teacher_attendances'
    __table_args__ = (
        db.UniqueConstraint('session_id', 'teacher_id', name='uq_tatt_session_teacher'),
    )

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('class_sessions.id'), nullable=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey('teachers.id'), nullable=False)

    status = db.Column(db.String(20), default='present')
    arrival_time = db.Column(db.String(10))
    departure_time = db.Column(db.String(10))
    teaching_hours = db.Column(db.Float, default=0)
    late_minutes = db.Column(db.Integer, default=0)
    notes = db.Column(db.Text)
    entry_method = db.Column(db.String(20), default='manual')
    device_id = db.Column(db.Integer, db.ForeignKey('attendance_devices.id'))

    recorded_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    teacher = db.relationship('Teacher', backref='attendances')
    session = db.relationship('ClassSession', backref='teacher_attendances')


class AttendanceDevice(db.Model):
    """دستگاه حضور و غیاب (اثرانگشت، کارت، RFID، چهره)."""
    __tablename__ = 'attendance_devices'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    code = db.Column(db.String(40), unique=True, nullable=False)
    device_type = db.Column(db.String(30), default='rfid')  # fingerprint, card, rfid, face, mixed
    location = db.Column(db.String(120))
    api_token = db.Column(db.String(64), unique=True, nullable=False, index=True)
    is_active = db.Column(db.Boolean, default=True)
    last_seen_at = db.Column(db.DateTime)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<AttendanceDevice {self.code}>'


class AttendanceCredential(db.Model):
    """شناسه سخت‌افزاری هنرجو/مدرس (کارت، RFID، اثرانگشت)."""
    __tablename__ = 'attendance_credentials'
    __table_args__ = (
        db.UniqueConstraint('uid', name='uq_att_cred_uid'),
    )

    id = db.Column(db.Integer, primary_key=True)
    uid = db.Column(db.String(80), nullable=False, index=True)
    person_type = db.Column(db.String(20), nullable=False)  # student, teacher
    person_id = db.Column(db.Integer, nullable=False)
    method = db.Column(db.String(20), default='card')
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class AttendanceDeviceLog(db.Model):
    """لاگ خام دستگاه برای عیب‌یابی و همگام‌سازی بعدی."""
    __tablename__ = 'attendance_device_logs'

    id = db.Column(db.Integer, primary_key=True)
    device_id = db.Column(db.Integer, db.ForeignKey('attendance_devices.id'))
    uid = db.Column(db.String(80))
    payload = db.Column(db.Text)
    result = db.Column(db.String(40))
    message = db.Column(db.String(300))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    device = db.relationship('AttendanceDevice', backref='logs')
