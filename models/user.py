"""User and Role models"""
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from extensions import db, login_manager


class Role(db.Model):
    __tablename__ = 'roles'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    description = db.Column(db.String(200))
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    users = db.relationship('User', backref=db.backref('role', lazy='joined'), lazy='dynamic')
    permissions = db.relationship('RolePermission', backref='role', lazy='dynamic')
    
    def __repr__(self):
        return f'<Role {self.name}>'


class Permission(db.Model):
    __tablename__ = 'permissions'
    
    id = db.Column(db.Integer, primary_key=True)
    module = db.Column(db.String(50), nullable=False)  # e.g., 'students', 'finance'
    action = db.Column(db.String(20), nullable=False)   # view, create, edit, delete, print, export
    description = db.Column(db.String(200))
    
    def __repr__(self):
        return f'<Permission {self.module}.{self.action}>'


class RolePermission(db.Model):
    __tablename__ = 'role_permissions'
    
    id = db.Column(db.Integer, primary_key=True)
    role_id = db.Column(db.Integer, db.ForeignKey('roles.id'), nullable=False)
    permission_id = db.Column(db.Integer, db.ForeignKey('permissions.id'), nullable=False)
    
    permission = db.relationship('Permission', backref='role_permissions')


class User(UserMixin, db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    full_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100))
    phone = db.Column(db.String(20))
    avatar = db.Column(db.String(200))
    role_id = db.Column(db.Integer, db.ForeignKey('roles.id'))
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'))
    is_active = db.Column(db.Boolean, default=True)
    is_admin = db.Column(db.Boolean, default=False)
    last_login = db.Column(db.DateTime)
    last_ip = db.Column(db.String(50))
    login_count = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    branch = db.relationship('Branch', backref=db.backref('users', lazy='dynamic'), lazy='joined')
    activities = db.relationship('ActivityLog', backref='user', lazy='dynamic')
    sessions = db.relationship('UserSession', backref='user', lazy='dynamic')
    
    @property
    def is_blocked(self):
        """حساب صریحاً غیرفعال شده است؟

        ستون `is_active` در نصب‌های قدیمی (یا بعد از `ALTER TABLE ... ADD COLUMN`
        بدون default) می‌تواند NULL باشد؛ NULL یعنی «فعال» تا مهاجرت ناقص،
        کل سیستم را قفل نکند. فقط False/0 صریح مسدود محسوب می‌شود.
        """
        return self.is_active is not None and not self.is_active

    @property
    def is_authenticated(self):
        """سرابرِ `UserMixin.is_authenticated` — و یک تله مهم.

        در Flask-Login این متد `return self.is_active` است و چون در این مدل
        `is_active` یک **ستون دیتابیس** است، مقدارش مستقیم به «احراز هویت»
        تبدیل می‌شد: یعنی هر سطر با `is_active = NULL` (ردیف‌های قدیمی) باعث
        می‌شد کاربر وسط کار ناشناس شود و بی‌دلیل به صفحه ورود بپرد. پس اینجا
        وضعیت را خودمان و با قاعده بالا («NULL = فعال») گزارش می‌کنیم.
        """
        return not self.is_blocked

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def _role_perm_pairs(self):
        """مجموعه (module, action) نقش — یک کوئری در هر درخواست."""
        if not self.role_id:
            return set()
        cache_attr = f'_role_perms_{self.role_id}'
        try:
            from flask import g, has_request_context
            if has_request_context():
                cached = getattr(g, cache_attr, None)
                if cached is not None:
                    return cached
        except Exception:
            pass
        from models.user import Permission, RolePermission
        pairs = {
            (module, action)
            for module, action in db.session.query(Permission.module, Permission.action)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .filter(RolePermission.role_id == self.role_id)
            .all()
        }
        try:
            from flask import g, has_request_context
            if has_request_context():
                setattr(g, cache_attr, pairs)
        except Exception:
            pass
        return pairs

    def has_permission(self, module, action):
        if self.is_admin:
            return True
        return (module, action) in self._role_perm_pairs()
    
    def has_module_access(self, module):
        """بررسی دسترسی به یک ماژول (هر عملیاتی)"""
        if self.is_admin:
            return True
        return any(mod == module for mod, _action in self._role_perm_pairs())
    
    def __repr__(self):
        return f'<User {self.username}>'


class UserSession(db.Model):
    __tablename__ = 'user_sessions'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    ip_address = db.Column(db.String(50))
    user_agent = db.Column(db.String(300))
    login_at = db.Column(db.DateTime, default=datetime.utcnow)
    logout_at = db.Column(db.DateTime)
    is_active = db.Column(db.Boolean, default=True)


class ActivityLog(db.Model):
    __tablename__ = 'activity_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    # باگ: ستون nullable=False بود ولی رویدادهای امنیتیِ «کاربر ناشناس»
    # (مثل قفل شدن بعد از تلاش ناموفق ورود با نام کاربری اشتباه) با
    # user_id=None ثبت می‌شدند و به IntegrityError می‌خوردند؛ حالا
    # برای رویدادهای سیستمی/ناشناس مجاز است.
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    action = db.Column(db.String(50), nullable=False)  # create, edit, delete, view, login, logout
    module = db.Column(db.String(50))
    entity_type = db.Column(db.String(50))
    entity_id = db.Column(db.Integer)
    description = db.Column(db.Text)
    ip_address = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    
    def __repr__(self):
        return f'<ActivityLog {self.action} by {self.user_id}>'


@login_manager.user_loader
def load_user(user_id):
    try:
        user = db.session.get(User, int(user_id))
    except (ValueError, TypeError):
        return None
    # حساب غیرفعال/مسدود باید بی‌درنگ از دسترس بیفتد. پیش‌تر `is_active` فقط جلوی
    # «ورود» را می‌گرفت و کاربرِ غیرفعال‌شده با کوکی Remember-Me تا ۱۴ روز کارش
    # ادامه می‌داد (بازبینی امنیت، بند A3 — ابطال نشست).
    # توجه: در نصب‌های قدیمی ستون ممکن است NULL باشد؛ NULL یعنی «فعال» (رفتار
    # پیش‌فرض ستون) تا کسی به‌خاطر مهاجرت ناقص از سیستم بیرون نیفتد.
    return None if (user is None or user.is_blocked) else user
