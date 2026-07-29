"""Course and related models"""
from datetime import datetime
from extensions import db


class Field(db.Model):
    """رشته آموزشی (e.g., Computer, Accounting)"""
    __tablename__ = 'fields'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    code = db.Column(db.String(20), unique=True, nullable=False)
    description = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    courses = db.relationship('Course', backref='field', lazy='dynamic')
    
    def __repr__(self):
        return f'<Field {self.name}>'


class Course(db.Model):
    """دوره آموزشی (e.g., Python Basics, ICDL)"""
    __tablename__ = 'courses'
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    code = db.Column(db.String(20), unique=True, nullable=False)
    field_id = db.Column(db.Integer, db.ForeignKey('fields.id'), nullable=False)
    
    # Details
    description = db.Column(db.Text)
    duration_hours = db.Column(db.Integer, default=0)
    total_sessions = db.Column(db.Integer, default=0)
    base_fee = db.Column(db.Float, default=0)
    registration_fee = db.Column(db.Float, default=0)
    book_fee = db.Column(db.Float, default=0)
    exam_fee = db.Column(db.Float, default=0)
    certificate_fee = db.Column(db.Float, default=0)
    other_fees = db.Column(db.Float, default=0)
    
    # Standards
    standard_code = db.Column(db.String(50))
    standard_name = db.Column(db.String(200))
    
    # Status
    is_active = db.Column(db.Boolean, default=True)
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'))
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    syllabus = db.relationship('Syllabus', backref='course', lazy='dynamic', order_by='Syllabus.chapter_no')
    classes = db.relationship('ClassGroup', backref='course', lazy='dynamic')
    branch = db.relationship('Branch', backref='courses')
    
    @property
    def total_fee(self):
        return (self.base_fee or 0) + (self.registration_fee or 0) + (self.book_fee or 0) + \
               (self.exam_fee or 0) + (self.certificate_fee or 0) + (self.other_fees or 0)
    
    def __repr__(self):
        return f'<Course {self.title}>'


class Syllabus(db.Model):
    """سرفصل آموزشی"""
    __tablename__ = 'syllabi'
    
    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey('courses.id'), nullable=False)
    chapter_no = db.Column(db.Integer)
    chapter_title = db.Column(db.String(200))
    lesson_title = db.Column(db.String(200))
    hours = db.Column(db.Float)
    description = db.Column(db.Text)
    order = db.Column(db.Integer, default=0)
    
    def __repr__(self):
        return f'<Syllabus {self.chapter_title}>'


class CertificateTemplate(db.Model):
    """قالب مدرک/گواهینامه"""
    __tablename__ = 'certificate_templates'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    cert_type = db.Column(db.String(50))  # completion, proficiency, participation
    level = db.Column(db.String(30))
    template_path = db.Column(db.String(300))
    background_path = db.Column(db.String(300))
    description = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Certificate(db.Model):
    """مدارک صادر شده"""
    __tablename__ = 'certificates'
    
    id = db.Column(db.Integer, primary_key=True)
    serial_number = db.Column(db.String(30), unique=True, nullable=False)
    template_id = db.Column(db.Integer, db.ForeignKey('certificate_templates.id'))
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    registration_id = db.Column(db.Integer, db.ForeignKey('registrations.id'))
    course_id = db.Column(db.Integer, db.ForeignKey('courses.id'))
    issue_date = db.Column(db.Date, default=datetime.utcnow)
    qr_code = db.Column(db.String(200))
    status = db.Column(db.String(20), default='active')  # active, cancelled, reissued
    notes = db.Column(db.Text)
    issued_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    
    student = db.relationship('Student', backref='certificates')
    registration = db.relationship('Registration', backref='certificates')
    template = db.relationship('CertificateTemplate', backref='issued_certificates')
    course = db.relationship('Course', backref='certificates')


class Room(db.Model):
    """اتاق/کلاس فیزیکی"""
    __tablename__ = 'rooms'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    code = db.Column(db.String(20), unique=True)
    capacity = db.Column(db.Integer, default=20)
    facilities = db.Column(db.Text)  # JSON: projector, computers, whiteboard, etc.
    status = db.Column(db.String(20), default='available')  # available, maintenance, reserved
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'))
    notes = db.Column(db.Text)
    
    branch = db.relationship('Branch', backref='rooms')


class Equipment(db.Model):
    """تجهیزات آموزشی"""
    __tablename__ = 'equipment'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    equipment_type = db.Column(db.String(50))
    model = db.Column(db.String(100))
    serial_number = db.Column(db.String(100))
    quantity = db.Column(db.Integer, default=1)
    available_qty = db.Column(db.Integer, default=1)
    status = db.Column(db.String(20), default='available')  # available, broken, repair, retired
    room_id = db.Column(db.Integer, db.ForeignKey('rooms.id'))
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'))
    purchase_date = db.Column(db.Date)
    notes = db.Column(db.Text)
    
    room = db.relationship('Room', backref='equipment')
    branch = db.relationship('Branch', backref='equipment')
