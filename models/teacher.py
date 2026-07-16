"""Teacher models"""
from datetime import datetime
from extensions import db


class Teacher(db.Model):
    __tablename__ = 'teachers'
    
    id = db.Column(db.Integer, primary_key=True)
    teacher_code = db.Column(db.String(20), unique=True, nullable=False, index=True)
    
    # Personal info
    first_name = db.Column(db.String(50), nullable=False)
    last_name = db.Column(db.String(50), nullable=False)
    father_name = db.Column(db.String(50))
    national_code = db.Column(db.String(10), unique=True, index=True)
    birth_date = db.Column(db.Date)
    photo = db.Column(db.String(200))
    
    # Contact
    mobile = db.Column(db.String(20), nullable=False)
    phone = db.Column(db.String(20))
    email = db.Column(db.String(100))
    address = db.Column(db.Text)
    
    # Professional info
    specialization = db.Column(db.String(200))
    education = db.Column(db.String(100))
    experience_years = db.Column(db.Integer)
    skills = db.Column(db.Text)  # JSON list
    level = db.Column(db.String(20), default='intermediate')  # beginner, intermediate, professional, master
    
    # Contract
    contract_type = db.Column(db.String(20))  # hourly, percentage, fixed, session
    hourly_rate = db.Column(db.Float, default=0)
    percentage_rate = db.Column(db.Float, default=0)
    fixed_salary = db.Column(db.Float, default=0)
    session_rate = db.Column(db.Float, default=0)
    contract_start = db.Column(db.Date)
    contract_end = db.Column(db.Date)
    
    # Status
    is_active = db.Column(db.Boolean, default=True)
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'))
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))  # اتصال به حساب کاربری
    notes = db.Column(db.Text)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    branch = db.relationship('Branch', backref='teachers')
    documents = db.relationship('TeacherDocument', backref='teacher', lazy='dynamic')
    courses = db.relationship('TeacherCourse', backref='teacher', lazy='dynamic')
    evaluations = db.relationship('TeacherEvaluation', backref='teacher', lazy='dynamic')
    
    @property
    def full_name(self):
        return f'{self.first_name} {self.last_name}'
    
    @property
    def active_classes(self):
        from models.classes import ClassGroup
        return ClassGroup.query.filter_by(teacher_id=self.id, status='active').all()
    
    def __repr__(self):
        return f'<Teacher {self.teacher_code}: {self.full_name}>'


class TeacherDocument(db.Model):
    __tablename__ = 'teacher_documents'
    
    id = db.Column(db.Integer, primary_key=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey('teachers.id'), nullable=False)
    doc_type = db.Column(db.String(50), nullable=False)
    file_path = db.Column(db.String(300), nullable=False)
    file_name = db.Column(db.String(200))
    description = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class TeacherCourse(db.Model):
    __tablename__ = 'teacher_courses'
    
    id = db.Column(db.Integer, primary_key=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey('teachers.id'), nullable=False)
    course_id = db.Column(db.Integer, db.ForeignKey('courses.id'), nullable=False)
    proficiency_level = db.Column(db.String(20))  # beginner, intermediate, advanced
    
    course = db.relationship('Course', backref='teacher_courses')


class TeacherEvaluation(db.Model):
    __tablename__ = 'teacher_evaluations'
    
    id = db.Column(db.Integer, primary_key=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey('teachers.id'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'))
    class_id = db.Column(db.Integer, db.ForeignKey('class_groups.id'))
    teaching_quality = db.Column(db.Integer)  # 1-5
    punctuality = db.Column(db.Integer)  # 1-5
    behavior = db.Column(db.Integer)  # 1-5
    overall_satisfaction = db.Column(db.Integer)  # 1-5
    comment = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    student = db.relationship('Student', backref='teacher_evaluations')
