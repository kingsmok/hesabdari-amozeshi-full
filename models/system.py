"""System settings, Branch, and other system models"""
from datetime import datetime
from extensions import db


class SystemSettings(db.Model):
    """تنظیمات عمومی سیستم"""
    __tablename__ = 'system_settings'
    
    id = db.Column(db.Integer, primary_key=True)
    academy_name = db.Column(db.String(200), default='آموزشگاه')
    academy_code = db.Column(db.String(20))
    license_number = db.Column(db.String(50))
    manager_name = db.Column(db.String(100))
    phone = db.Column(db.String(20))
    fax = db.Column(db.String(20))
    email = db.Column(db.String(100))
    website = db.Column(db.String(100))
    address = db.Column(db.Text)
    logo = db.Column(db.String(300))
    
    # Academic year
    current_year = db.Column(db.String(10))
    current_term = db.Column(db.String(20))
    
    # SMS
    sms_api_key = db.Column(db.String(200))
    sms_provider = db.Column(db.String(50))
    sms_sender = db.Column(db.String(20))
    
    # Payment gateway
    payment_gateway = db.Column(db.String(50))
    payment_api_key = db.Column(db.String(200))
    payment_merchant_id = db.Column(db.String(100))
    
    # Backup
    auto_backup = db.Column(db.Boolean, default=False)
    backup_interval_hours = db.Column(db.Integer, default=24)
    backup_path = db.Column(db.String(300))
    max_backups = db.Column(db.Integer, default=30)
    
    # Telegram Bot
    telegram_bot_token = db.Column(db.String(200))
    telegram_webhook_url = db.Column(db.String(300))
    
    # Bale Messenger Bot
    bale_bot_token = db.Column(db.String(200))
    bale_webhook_url = db.Column(db.String(300))

    # ارسال بسته پشتیبان به ربات بله (برای مدیر)
    backup_bot_enabled = db.Column(db.Boolean, default=False)
    backup_bot_chat_id = db.Column(db.String(200))      # چند شناسه با کاما
    backup_bot_max_mb = db.Column(db.Integer, default=45)
    backup_bot_kind = db.Column(db.String(20), default='database')
    
    # FarazSMS
    farazsms_api_key = db.Column(db.String(200))
    farazsms_sender = db.Column(db.String(20))
    farazsms_pattern_code = db.Column(db.String(50))
    
    # Print
    print_header = db.Column(db.Text)
    print_footer = db.Column(db.Text)
    
    # System messages
    welcome_message = db.Column(db.Text)
    
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Branch(db.Model):
    """شعبه"""
    __tablename__ = 'branches'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    code = db.Column(db.String(20), unique=True, nullable=False)
    manager_name = db.Column(db.String(100))
    phone = db.Column(db.String(20))
    mobile = db.Column(db.String(20))
    email = db.Column(db.String(100))
    address = db.Column(db.Text)
    is_main = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<Branch {self.name}>'


class AcademicYear(db.Model):
    """سال آموزشی"""
    __tablename__ = 'academic_years'
    
    id = db.Column(db.Integer, primary_key=True)
    year_name = db.Column(db.String(20), nullable=False)  # e.g., 1405
    term_name = db.Column(db.String(20))  # بهار, تابستان, پاییز
    start_date = db.Column(db.Date)
    end_date = db.Column(db.Date)
    is_current = db.Column(db.Boolean, default=False)
    is_closed = db.Column(db.Boolean, default=False)
    closed_at = db.Column(db.DateTime)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Message(db.Model):
    """پیامک"""
    __tablename__ = 'messages'
    
    id = db.Column(db.Integer, primary_key=True)
    recipient_type = db.Column(db.String(20))  # student, teacher, parent, custom
    recipient_id = db.Column(db.Integer)
    phone = db.Column(db.String(20))
    message_text = db.Column(db.Text, nullable=False)
    template_id = db.Column(db.Integer, db.ForeignKey('message_templates.id'))
    send_type = db.Column(db.String(20))  # manual, auto_registration, auto_absence, auto_payment, birthday, reminder
    status = db.Column(db.String(20), default='pending')  # pending, sent, failed, delivered
    sent_at = db.Column(db.DateTime)
    delivery_status = db.Column(db.String(50))
    error_message = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))


class MessageTemplate(db.Model):
    """قالب پیامک"""
    __tablename__ = 'message_templates'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    template_text = db.Column(db.Text, nullable=False)
    template_type = db.Column(db.String(30))  # registration, absence, payment, birthday, reminder, general
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class InternalMessage(db.Model):
    """پیام داخلی"""
    __tablename__ = 'internal_messages'
    
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    subject = db.Column(db.String(200))
    body = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    read_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    sender = db.relationship('User', foreign_keys=[sender_id], backref='sent_messages')
    receiver = db.relationship('User', foreign_keys=[receiver_id], backref='received_messages')


class Notification(db.Model):
    """اعلان داخلی"""
    __tablename__ = 'notifications'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    body = db.Column(db.Text)
    notif_type = db.Column(db.String(30))  # payment, registration, attendance, system, task
    reference_type = db.Column(db.String(50))
    reference_id = db.Column(db.Integer)
    is_read = db.Column(db.Boolean, default=False)
    read_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    user = db.relationship('User', backref='notifications')


class Ticket(db.Model):
    """تیکت پشتیبانی"""
    __tablename__ = 'tickets'
    
    id = db.Column(db.Integer, primary_key=True)
    ticket_number = db.Column(db.String(20), unique=True, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    subject = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    priority = db.Column(db.String(20), default='medium')  # low, medium, high, urgent
    status = db.Column(db.String(20), default='open')  # open, in_progress, resolved, closed
    assigned_to = db.Column(db.Integer, db.ForeignKey('users.id'))
    resolved_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    user = db.relationship('User', foreign_keys=[user_id], backref='tickets')
    assignee = db.relationship('User', foreign_keys=[assigned_to], backref='assigned_tickets')
    responses = db.relationship('TicketResponse', backref='ticket', lazy='dynamic')


class TicketResponse(db.Model):
    """پاسخ تیکت"""
    __tablename__ = 'ticket_responses'
    
    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey('tickets.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    response_text = db.Column(db.Text, nullable=False)
    attachment = db.Column(db.String(300))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    user = db.relationship('User', backref='ticket_responses')


class Complaint(db.Model):
    """شکایات"""
    __tablename__ = 'complaints'
    
    id = db.Column(db.Integer, primary_key=True)
    complaint_number = db.Column(db.String(20), unique=True)
    complainant_name = db.Column(db.String(100))
    complainant_phone = db.Column(db.String(20))
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'))
    subject = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    status = db.Column(db.String(20), default='new')  # new, investigating, resolved, closed
    response = db.Column(db.Text)
    resolved_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    resolved_at = db.Column(db.DateTime)
    
    student = db.relationship('Student', backref='complaints')


class Survey(db.Model):
    """نظرسنجی"""
    __tablename__ = 'surveys'
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    survey_type = db.Column(db.String(30))  # teacher, course, service, general
    target_id = db.Column(db.Integer)  # teacher_id or course_id
    questions = db.Column(db.Text)  # JSON
    is_active = db.Column(db.Boolean, default=True)
    start_date = db.Column(db.Date)
    end_date = db.Column(db.Date)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class SurveyResponse(db.Model):
    """پاسخ نظرسنجی"""
    __tablename__ = 'survey_responses'
    
    id = db.Column(db.Integer, primary_key=True)
    survey_id = db.Column(db.Integer, db.ForeignKey('surveys.id'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'))
    answers = db.Column(db.Text)  # JSON
    score = db.Column(db.Float)
    comment = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    survey = db.relationship('Survey', backref='responses')
    student = db.relationship('Student', backref='survey_responses')


class SystemGoal(db.Model):
    """اهداف آموزشگاه"""
    __tablename__ = 'system_goals'
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    goal_type = db.Column(db.String(30))  # enrollment, revenue, satisfaction
    target_value = db.Column(db.Float)
    current_value = db.Column(db.Float, default=0)
    period = db.Column(db.String(20))  # monthly, quarterly, yearly
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'))
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    branch = db.relationship('Branch', backref='goals')


class DocumentSequence(db.Model):
    """شماره‌گذار اسناد — جانشین الگوی شکننده «id آخرین رکورد + یک».

    یک ردیف به‌ازای هر (kind, year) و یک شمارنده monotonic که با SELECT … FOR UPDATE
    (روی SQLite: UPDATE … RETURNING نیست، پس با حلقه retry روی تعارض UNIQUE کار می‌کنیم)
    افزایش می‌یابد. حذف رکورد، Restore یا دو کاربر همزمان دیگر شماره تکراری نمی‌سازد.
    """
    __tablename__ = 'document_sequences'

    id = db.Column(db.Integer, primary_key=True)
    kind = db.Column(db.String(30), nullable=False, index=True)   # payslip, expense, payment, voucher…
    year = db.Column(db.String(4), nullable=False, default='-')   # سال شمسی؛ '-' برای بدون سال
    next_no = db.Column(db.Integer, nullable=False, default=1)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('kind', 'year', name='uq_doc_sequence_kind_year'),
    )

    def __repr__(self):
        return f'<DocumentSequence {self.kind}/{self.year} → {self.next_no}>'


class TaxRule(db.Model):
    """قواعد مالیات حقوق و نرخ بیمه، به تفکیک سال.

    طبق قانون بودجه، اعداد هر سال تغییر می‌کند؛ برای اینکه به‌جای ویرایش کد،
    مدیر از «تنظیمات مالیاتی» سال جدید را ثبت کند. اگر ردیفی برای سالی وجود
    نداشته باشد، مقادیر پیش‌فرض ۱۴۰۵ (ماده ۱ قانون بودجه ۱۴۰۵) اعمال می‌شود.
    """
    __tablename__ = 'tax_rules'

    id = db.Column(db.Integer, primary_key=True)
    year = db.Column(db.String(4), nullable=False, unique=True)      # '1405'
    monthly_exemption = db.Column(db.Float, default=40000000)        # معافیت ماهانه (تومان)
    brackets = db.Column(db.Text)                                     # JSON: [{"from":..,"to":..,"rate":0.10}]
    insurance_employee_rate = db.Column(db.Float, default=0.07)      # سهم کارمند
    insurance_employer_rate = db.Column(db.Float, default=0.23)      # سهم کارفرما
    note = db.Column(db.String(255))
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by = db.Column(db.Integer, db.ForeignKey('users.id'))

    def __repr__(self):
        return f'<TaxRule {self.year}>'
