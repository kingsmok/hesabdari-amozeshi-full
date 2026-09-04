"""Registration and enrollment models"""
from datetime import datetime
from extensions import db


class Registration(db.Model):
    """ثبت‌نام"""
    __tablename__ = 'registrations'
    
    id = db.Column(db.Integer, primary_key=True)
    reg_code = db.Column(db.String(20), unique=True, nullable=False, index=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    course_id = db.Column(db.Integer, db.ForeignKey('courses.id'), nullable=False)
    class_id = db.Column(db.Integer, db.ForeignKey('class_groups.id'))
    teacher_id = db.Column(db.Integer, db.ForeignKey('teachers.id'))
    
    # Dates
    registration_date = db.Column(db.Date, default=datetime.utcnow)
    start_date = db.Column(db.Date)
    end_date = db.Column(db.Date)
    
    # Fee
    base_fee = db.Column(db.Float, default=0)
    discount_type = db.Column(db.String(20))  # percentage, fixed, code
    discount_value = db.Column(db.Float, default=0)
    discount_amount = db.Column(db.Float, default=0)
    discount_code = db.Column(db.String(30))
    total_fee = db.Column(db.Float, default=0)
    paid_amount = db.Column(db.Float, default=0)
    remaining_amount = db.Column(db.Float, default=0)
    
    # Status
    status = db.Column(db.String(20), default='active')  # active, completed, withdrawn, frozen, transferred
    is_reserved = db.Column(db.Boolean, default=False)
    
    # Contract
    contract_file = db.Column(db.String(300))
    signature_student = db.Column(db.Text)  # Base64
    signature_parent = db.Column(db.Text)
    signature_academy = db.Column(db.Text)
    
    # Teacher payment
    teacher_payment_type = db.Column(db.String(20))  # percentage, fixed, hourly, session
    teacher_payment_value = db.Column(db.Float, default=0)  # مقدار (درصد یا مبلغ)
    teacher_payment_amount = db.Column(db.Float, default=0)  # مبلغ محاسبه شده
    
    # Notes
    notes = db.Column(db.Text)
    cancellation_reason = db.Column(db.Text)
    
    # Meta
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    cancelled_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    cancelled_at = db.Column(db.DateTime)
    
    # Relationships
    course = db.relationship('Course', backref='registrations')
    teacher = db.relationship('Teacher', backref='registrations')
    branch = db.relationship('Branch', backref='registrations')
    installments = db.relationship('Installment', backref='registration', lazy='dynamic')
    payments = db.relationship('Payment', backref='registration', lazy='dynamic')
    
    def calculate_fees(self):
        """Calculate total fee with discount"""
        self.discount_amount = self.discount_amount or 0
        self.paid_amount = self.paid_amount or 0
        self.discount_value = self.discount_value or 0
        
        if self.discount_type == 'percentage':
            self.discount_amount = (self.base_fee or 0) * (self.discount_value / 100)
        elif self.discount_type == 'fixed':
            self.discount_amount = self.discount_value
        
        self.total_fee = (self.base_fee or 0) - self.discount_amount
        self.remaining_amount = self.total_fee - self.paid_amount
        return self.total_fee
    
    def __repr__(self):
        return f'<Registration {self.reg_code}>'


class Installment(db.Model):
    """اقساط"""
    __tablename__ = 'installments'
    
    id = db.Column(db.Integer, primary_key=True)
    registration_id = db.Column(db.Integer, db.ForeignKey('registrations.id'), nullable=False)
    installment_number = db.Column(db.Integer)
    amount = db.Column(db.Float, nullable=False)
    due_date = db.Column(db.Date, nullable=False)
    paid_date = db.Column(db.Date)
    paid_amount = db.Column(db.Float, default=0)
    status = db.Column(db.String(20), default='pending')  # pending, paid, overdue, partial
    late_fee = db.Column(db.Float, default=0)
    late_days = db.Column(db.Integer, default=0)
    reminder_sent = db.Column(db.Boolean, default=False)
    notes = db.Column(db.Text)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    @property
    def remaining(self):
        # ردیف‌های قدیمی می‌توانند late_fee/paid_amount تهی داشته باشند؛
        # قبلاً همین باعث ۵۰۰ در صفحه اقساط می‌شد
        return (self.amount or 0) + (self.late_fee or 0) - (self.paid_amount or 0)
    
    def __repr__(self):
        return f'<Installment #{self.installment_number} - {self.amount}>'


class ClassScheduleOverride(db.Model):
    """تغییر زمان جلسه"""
    __tablename__ = 'class_schedule_overrides'
    
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('class_sessions.id'), nullable=False)
    original_date = db.Column(db.Date)
    new_date = db.Column(db.Date)
    new_start_time = db.Column(db.String(10))
    new_end_time = db.Column(db.String(10))
    reason = db.Column(db.Text)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
