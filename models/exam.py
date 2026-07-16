"""Exam and grading models"""
from datetime import datetime
from extensions import db


class Exam(db.Model):
    """آزمون"""
    __tablename__ = 'exams'
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    exam_code = db.Column(db.String(20), unique=True)
    course_id = db.Column(db.Integer, db.ForeignKey('courses.id'), nullable=False)
    class_id = db.Column(db.Integer, db.ForeignKey('class_groups.id'))
    
    exam_type = db.Column(db.String(20))  # written, practical, oral, online, combined
    exam_date = db.Column(db.Date)
    start_time = db.Column(db.String(10))
    end_time = db.Column(db.String(10))
    duration_minutes = db.Column(db.Integer)
    total_marks = db.Column(db.Float, default=100)
    passing_marks = db.Column(db.Float, default=50)
    
    # Theory/Practical weights
    theory_weight = db.Column(db.Float, default=60)
    practical_weight = db.Column(db.Float, default=40)
    
    status = db.Column(db.String(20), default='draft')  # draft, scheduled, in_progress, completed
    notes = db.Column(db.Text)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    
    # Relationships
    course = db.relationship('Course', backref='exams')
    class_group = db.relationship('ClassGroup', backref='exams')
    questions = db.relationship('ExamQuestion', backref='exam', lazy='dynamic')
    results = db.relationship('ExamResult', backref='exam', lazy='dynamic')
    
    def __repr__(self):
        return f'<Exam {self.title}>'


class QuestionBank(db.Model):
    """بانک سوالات"""
    __tablename__ = 'question_bank'
    
    id = db.Column(db.Integer, primary_key=True)
    question_text = db.Column(db.Text, nullable=False)
    question_type = db.Column(db.String(20), nullable=False)  # multiple_choice, true_false, descriptive, fill_blank
    
    # Multiple choice options
    option_a = db.Column(db.Text)
    option_b = db.Column(db.Text)
    option_c = db.Column(db.Text)
    option_d = db.Column(db.Text)
    correct_answer = db.Column(db.String(10))
    
    # Metadata
    course_id = db.Column(db.Integer, db.ForeignKey('courses.id'))
    chapter = db.Column(db.String(100))
    difficulty = db.Column(db.String(20))  # easy, medium, hard, very_hard
    marks = db.Column(db.Float, default=1)
    explanation = db.Column(db.Text)
    
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    
    course = db.relationship('Course', backref='questions')


class ExamQuestion(db.Model):
    """سوالات آزمون"""
    __tablename__ = 'exam_questions'
    
    id = db.Column(db.Integer, primary_key=True)
    exam_id = db.Column(db.Integer, db.ForeignKey('exams.id'), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey('question_bank.id'))
    question_text = db.Column(db.Text, nullable=False)
    question_type = db.Column(db.String(20))
    option_a = db.Column(db.Text)
    option_b = db.Column(db.Text)
    option_c = db.Column(db.Text)
    option_d = db.Column(db.Text)
    correct_answer = db.Column(db.String(10))
    marks = db.Column(db.Float, default=1)
    order = db.Column(db.Integer)
    
    question = db.relationship('QuestionBank', backref='exam_questions')


class ExamResult(db.Model):
    """نتیجه آزمون"""
    __tablename__ = 'exam_results'
    
    id = db.Column(db.Integer, primary_key=True)
    exam_id = db.Column(db.Integer, db.ForeignKey('exams.id'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    
    theory_score = db.Column(db.Float, default=0)
    practical_score = db.Column(db.Float, default=0)
    total_score = db.Column(db.Float, default=0)
    is_passed = db.Column(db.Boolean)
    answers = db.Column(db.Text)  # JSON
    
    # Appeal
    appeal_requested = db.Column(db.Boolean, default=False)
    appeal_description = db.Column(db.Text)
    appeal_result = db.Column(db.Text)
    appeal_status = db.Column(db.String(20))  # none, pending, reviewed
    
    graded_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    graded_at = db.Column(db.DateTime)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    student = db.relationship('Student', backref='exam_results')


class Grade(db.Model):
    """نمرات و کارنامه"""
    __tablename__ = 'grades'
    
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    registration_id = db.Column(db.Integer, db.ForeignKey('registrations.id'))
    course_id = db.Column(db.Integer, db.ForeignKey('courses.id'))
    class_id = db.Column(db.Integer, db.ForeignKey('class_groups.id'))
    
    midterm_score = db.Column(db.Float)
    final_score = db.Column(db.Float)
    practical_score = db.Column(db.Float)
    project_score = db.Column(db.Float)
    attendance_score = db.Column(db.Float)
    total_score = db.Column(db.Float)
    letter_grade = db.Column(db.String(5))
    is_passed = db.Column(db.Boolean)
    
    attendance_percentage = db.Column(db.Float)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    registration = db.relationship('Registration', backref='grades')
    course = db.relationship('Course', backref='grades')
    class_group = db.relationship('ClassGroup', backref='grades')
