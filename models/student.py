"""Student and related models"""
from datetime import datetime
from extensions import db


class Student(db.Model):
    __tablename__ = 'students'
    
    id = db.Column(db.Integer, primary_key=True)
    student_code = db.Column(db.String(20), unique=True, nullable=False, index=True)
    
    # Personal info
    first_name = db.Column(db.String(50), nullable=False)
    last_name = db.Column(db.String(50), nullable=False)
    father_name = db.Column(db.String(50))
    national_code = db.Column(db.String(10), unique=True, index=True)
    birth_certificate_no = db.Column(db.String(20))
    birth_date = db.Column(db.Date)
    gender = db.Column(db.String(10))  # male, female
    photo = db.Column(db.String(200))
    marital_status = db.Column(db.String(20))
    education_level = db.Column(db.String(50))
    job = db.Column(db.String(100))
    workplace = db.Column(db.String(200))
    
    # Contact info
    mobile = db.Column(db.String(20), nullable=False)
    mobile2 = db.Column(db.String(20))
    phone = db.Column(db.String(20))
    email = db.Column(db.String(100))
    address = db.Column(db.Text)
    postal_code = db.Column(db.String(10))
    emergency_phone = db.Column(db.String(20))
    
    # Parent info (for minors)
    parent_name = db.Column(db.String(100))
    parent_mobile = db.Column(db.String(20))
    parent_job = db.Column(db.String(100))
    parent_relation = db.Column(db.String(20))
    
    # Referral source
    referral_source = db.Column(db.String(50))  # instagram, friend, website, phone, ad
    referrer_student_id = db.Column(db.Integer, db.ForeignKey('students.id'))
    
    # Status
    status = db.Column(db.String(20), default='active')  # active, graduated, withdrawn, suspended, transferred
    category = db.Column(db.String(30))  # teen, adult, special, corporate, vip
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'))
    
    # Notes
    notes = db.Column(db.Text)
    description = db.Column(db.Text)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    
    # Relationships
    branch = db.relationship('Branch', backref='students')
    documents = db.relationship('StudentDocument', backref='student', lazy='dynamic')
    registrations = db.relationship('Registration', backref='student', lazy='dynamic')
    attendances = db.relationship('Attendance', backref='student', lazy='dynamic')
    grades = db.relationship('Grade', backref='student', lazy='dynamic')
    payments = db.relationship('Payment', backref='student', lazy='dynamic')
    
    @property
    def full_name(self):
        return f'{self.first_name} {self.last_name}'
    
    @property
    def active_registrations(self):
        return self.registrations.filter_by(status='active').all()
    
    def __repr__(self):
        return f'<Student {self.student_code}: {self.full_name}>'


class StudentDocument(db.Model):
    __tablename__ = 'student_documents'
    
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    doc_type = db.Column(db.String(50), nullable=False)  # national_card, birth_cert, photo, diploma, contract, receipt
    file_path = db.Column(db.String(300), nullable=False)
    file_name = db.Column(db.String(200))
    file_size = db.Column(db.Integer)
    description = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    uploaded_by = db.Column(db.Integer, db.ForeignKey('users.id'))


class StudentStatusHistory(db.Model):
    __tablename__ = 'student_status_history'
    
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    old_status = db.Column(db.String(20))
    new_status = db.Column(db.String(20))
    reason = db.Column(db.Text)
    changed_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class WaitingList(db.Model):
    __tablename__ = 'waiting_list'
    
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    course_id = db.Column(db.Integer, db.ForeignKey('courses.id'), nullable=False)
    class_id = db.Column(db.Integer, db.ForeignKey('class_groups.id'))
    priority = db.Column(db.Integer, default=1)
    status = db.Column(db.String(20), default='waiting')  # waiting, notified, enrolled, cancelled
    request_date = db.Column(db.DateTime, default=datetime.utcnow)
    notes = db.Column(db.Text)
    
    student = db.relationship('Student', backref='waiting_entries')
    course = db.relationship('Course', backref='waiting_entries')
