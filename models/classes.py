"""Class and session models"""
from datetime import datetime
from extensions import db


class ClassGroup(db.Model):
    """کلاس آموزشی"""
    __tablename__ = 'class_groups'
    
    id = db.Column(db.Integer, primary_key=True)
    class_code = db.Column(db.String(20), unique=True, nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    course_id = db.Column(db.Integer, db.ForeignKey('courses.id'), nullable=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey('teachers.id'))
    assistant_teacher_id = db.Column(db.Integer, db.ForeignKey('teachers.id'))
    room_id = db.Column(db.Integer, db.ForeignKey('rooms.id'))
    
    # Capacity
    max_capacity = db.Column(db.Integer, default=20)
    current_count = db.Column(db.Integer, default=0)
    
    # Schedule
    days_of_week = db.Column(db.String(50))  # JSON: [0,2,4] for sat,mon,wed
    start_time = db.Column(db.String(10))
    end_time = db.Column(db.String(10))
    start_date = db.Column(db.Date)
    end_date = db.Column(db.Date)
    
    # Status
    status = db.Column(db.String(20), default='active')  # active, completed, cancelled, archived
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'))
    notes = db.Column(db.Text)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    
    # Relationships
    teacher = db.relationship('Teacher', foreign_keys=[teacher_id], backref='teaching_classes')
    assistant_teacher = db.relationship('Teacher', foreign_keys=[assistant_teacher_id], backref='assisting_classes')
    room = db.relationship('Room', backref='class_groups')
    branch = db.relationship('Branch', backref='class_groups')
    sessions = db.relationship('ClassSession', backref='class_group', lazy='dynamic', order_by='ClassSession.session_date')
    registrations = db.relationship('Registration', backref='class_group', lazy='dynamic')
    
    @property
    def available_capacity(self):
        return max(0, (self.max_capacity or 0) - (self.current_count or 0))
    
    @property
    def is_full(self):
        return (self.current_count or 0) >= (self.max_capacity or 0)
    
    @property
    def total_sessions_count(self):
        return self.sessions.count()
    
    @property
    def completed_sessions_count(self):
        return self.sessions.filter_by(status='completed').count()
    
    def __repr__(self):
        return f'<ClassGroup {self.class_code}: {self.name}>'


class ClassSession(db.Model):
    """جلسات کلاس"""
    __tablename__ = 'class_sessions'
    
    id = db.Column(db.Integer, primary_key=True)
    class_id = db.Column(db.Integer, db.ForeignKey('class_groups.id'), nullable=False)
    session_number = db.Column(db.Integer)
    session_date = db.Column(db.Date, nullable=False)
    start_time = db.Column(db.String(10))
    end_time = db.Column(db.String(10))
    topic = db.Column(db.String(200))
    description = db.Column(db.Text)
    homework = db.Column(db.Text)
    status = db.Column(db.String(20), default='scheduled')  # scheduled, completed, cancelled, makeup
    cancellation_reason = db.Column(db.String(200))
    substitute_teacher_id = db.Column(db.Integer, db.ForeignKey('teachers.id'))
    notes = db.Column(db.Text)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    substitute_teacher = db.relationship('Teacher', backref='substitute_sessions')
    attendances = db.relationship('Attendance', backref='session', lazy='dynamic')
    
    def __repr__(self):
        return f'<Session #{self.session_number} of Class {self.class_id}>'


class Schedule(db.Model):
    """برنامه هفتگی"""
    __tablename__ = 'schedules'
    
    id = db.Column(db.Integer, primary_key=True)
    class_id = db.Column(db.Integer, db.ForeignKey('class_groups.id'), nullable=False)
    day_of_week = db.Column(db.Integer, nullable=False)  # 0=Saturday to 6=Friday
    start_time = db.Column(db.String(10), nullable=False)
    end_time = db.Column(db.String(10), nullable=False)
    room_id = db.Column(db.Integer, db.ForeignKey('rooms.id'))
    teacher_id = db.Column(db.Integer, db.ForeignKey('teachers.id'))
    
    class_group = db.relationship('ClassGroup', backref='schedules')
    room = db.relationship('Room', backref='schedules')
    teacher = db.relationship('Teacher', backref='schedules')


class Holiday(db.Model):
    """تعطیلات"""
    __tablename__ = 'holidays'
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date)
    holiday_type = db.Column(db.String(20))  # official, emergency, branch
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'))
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    branch = db.relationship('Branch', backref='holidays')


class ClassTransfer(db.Model):
    """انتقال هنرجو بین کلاس‌ها"""
    __tablename__ = 'class_transfers'
    
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    from_class_id = db.Column(db.Integer, db.ForeignKey('class_groups.id'), nullable=False)
    to_class_id = db.Column(db.Integer, db.ForeignKey('class_groups.id'), nullable=False)
    transfer_date = db.Column(db.Date, default=datetime.utcnow)
    reason = db.Column(db.Text)
    fee_change = db.Column(db.Float, default=0)
    approved_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    student = db.relationship('Student', backref='class_transfers')
    from_class = db.relationship('ClassGroup', foreign_keys=[from_class_id])
    to_class = db.relationship('ClassGroup', foreign_keys=[to_class_id])
