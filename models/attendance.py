"""Attendance models"""
from datetime import datetime
from extensions import db


class Attendance(db.Model):
    """حضور و غیاب"""
    __tablename__ = 'attendances'
    
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('class_sessions.id'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    
    status = db.Column(db.String(20), default='present')  # present, absent, late, leave
    arrival_time = db.Column(db.String(10))
    departure_time = db.Column(db.String(10))
    duration_minutes = db.Column(db.Integer)
    late_minutes = db.Column(db.Integer, default=0)
    leave_reason = db.Column(db.String(200))
    
    # Auto attendance
    entry_method = db.Column(db.String(20))  # manual, fingerprint, card, rfid, face
    device_data = db.Column(db.Text)
    
    notes = db.Column(db.Text)
    recorded_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<Attendance Student:{self.student_id} Session:{self.session_id} - {self.status}>'


class TeacherAttendance(db.Model):
    """حضور و غیاب مدرس"""
    __tablename__ = 'teacher_attendances'
    
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('class_sessions.id'), nullable=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey('teachers.id'), nullable=False)
    
    status = db.Column(db.String(20), default='present')  # present, absent, late
    arrival_time = db.Column(db.String(10))
    departure_time = db.Column(db.String(10))
    teaching_hours = db.Column(db.Float, default=0)
    late_minutes = db.Column(db.Integer, default=0)
    notes = db.Column(db.Text)
    
    recorded_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    teacher = db.relationship('Teacher', backref='attendances')
    session = db.relationship('ClassSession', backref='teacher_attendances')
