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
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def has_permission(self, module, action):
        if self.is_admin:
            return True
        from models.user import RolePermission, Permission
        perm = db.session.query(RolePermission).join(Permission).filter(
            RolePermission.role_id == self.role_id,
            Permission.module == module,
            Permission.action == action
        ).first()
        return perm is not None
    
    def has_module_access(self, module):
        """بررسی دسترسی به یک ماژول (هر عملیاتی)"""
        if self.is_admin:
            return True
        from models.user import RolePermission, Permission
        perm = db.session.query(RolePermission).join(Permission).filter(
            RolePermission.role_id == self.role_id,
            Permission.module == module
        ).first()
        return perm is not None
    
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
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
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
    # ادامه می‌داد (بازبینی امنیت، بند A3 — ابطال نشست)
    if user is None or not getattr(user, 'is_active', True):
        return None
    return user
