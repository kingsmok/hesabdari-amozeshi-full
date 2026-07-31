"""مدل‌های ربات تلگرام و بله"""
from datetime import datetime
from extensions import db


class BotUser(db.Model):
    """کاربران ربات — ارتباط chat_id با شماره تلفن"""
    __tablename__ = 'bot_users'

    id = db.Column(db.Integer, primary_key=True)
    chat_id = db.Column(db.BigInteger, unique=True, nullable=False, index=True)
    phone = db.Column(db.String(20), index=True)
    first_name = db.Column(db.String(100))
    last_name = db.Column(db.String(100))
    username = db.Column(db.String(100))  # @username
    language = db.Column(db.String(10), default='fa')
    provider = db.Column(db.String(20), default='bale')  # bale یا telegram
    is_verified = db.Column(db.Boolean, default=False)  # شماره تلفن تأیید شده
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=True)
    is_blocked = db.Column(db.Boolean, default=False)
    is_admin_bot = db.Column(db.Boolean, default=False)  # مدیر ربات
    last_activity = db.Column(db.DateTime)
    joined_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # رابطه با هنرجو
    student = db.relationship('Student', backref='bot_accounts', lazy=True)

    def __repr__(self):
        return f'<BotUser chat_id={self.chat_id} phone={self.phone}>'

    @property
    def full_name(self):
        parts = [self.first_name or '', self.last_name or '']
        return ' '.join(p for p in parts if p) or f'کاربر {self.chat_id}'


class BotMessage(db.Model):
    """لاگ پیام‌های ربات"""
    __tablename__ = 'bot_messages'

    id = db.Column(db.Integer, primary_key=True)
    chat_id = db.Column(db.BigInteger, index=True)
    message_id = db.Column(db.BigInteger)
    direction = db.Column(db.String(10))  # incoming یا outgoing
    text = db.Column(db.Text)
    msg_type = db.Column(db.String(30))  # text, contact, callback, command
    provider = db.Column(db.String(20), default='bale')
    is_group_message = db.Column(db.Boolean, default=False)
    sent_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship(
        'BotUser',
        backref=db.backref('messages', lazy='dynamic'),
        foreign_keys=[chat_id],
        primaryjoin="BotMessage.chat_id == BotUser.chat_id",
        viewonly=True,
    )


class BotKeyboard(db.Model):
    """تعریف کیبوردهای ربات"""
    __tablename__ = 'bot_keyboards'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.String(200))
    keyboard_type = db.Column(db.String(20), default='reply')  # reply یا inline
    buttons = db.Column(db.Text)  # JSON — لیست ردیف‌ها
    is_active = db.Column(db.Boolean, default=True)
    provider = db.Column(db.String(20), default='both')  # bale, telegram, both
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class BotBroadcast(db.Model):
    """لاگ پیام‌های گروهی"""
    __tablename__ = 'bot_broadcasts'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200))
    message_text = db.Column(db.Text, nullable=False)
    target_type = db.Column(db.String(30))  # all, verified, students, specific
    provider = db.Column(db.String(20), default='both')
    total_recipients = db.Column(db.Integer, default=0)
    sent_count = db.Column(db.Integer, default=0)
    failed_count = db.Column(db.Integer, default=0)
    status = db.Column(db.String(20), default='pending')  # pending, sending, completed, failed
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime)

    creator = db.relationship('User', backref='broadcasts')
