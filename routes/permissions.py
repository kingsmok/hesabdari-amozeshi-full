"""
سیستم مدیریت کاربران و دسترسی‌های دقیق
- ایجاد کاربر با نقش مشخص
- تخصیص دسترسی ماژول به ماژول
- کنترل سطح دسترسی: مشاهده/ایجاد/ویرایش/حذف/چاپ/خروجی
- محدودیت شعبه
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from extensions import db
from models.user import User, Role, Permission, RolePermission
from models.system import Branch

perms_bp = Blueprint('perms', __name__)


# لیست ماژول‌ها و دسترسی‌های قابل تخصیص
MODULES = {
    'students': {'name': 'هنرجویان', 'icon': 'bi-people'},
    'registration': {'name': 'ثبت‌نام', 'icon': 'bi-pencil-square'},
    'classes': {'name': 'کلاس‌ها', 'icon': 'bi-easel2'},
    'teachers': {'name': 'مدرسین', 'icon': 'bi-person-workspace'},
    'attendance': {'name': 'حضور و غیاب', 'icon': 'bi-clipboard2-check'},
    'exams': {'name': 'آزمون و نمرات', 'icon': 'bi-journal-text'},
    'courses': {'name': 'دوره‌ها', 'icon': 'bi-journal-richtext'},
    'finance': {'name': 'مالی و شهریه', 'icon': 'bi-cash-stack'},
    'accounting': {'name': 'حسابداری', 'icon': 'bi-calculator'},
    'payroll': {'name': 'حقوق و دستمزد', 'icon': 'bi-cash-coin'},
    'tax': {'name': 'مالیات', 'icon': 'bi-percent'},
    'reports': {'name': 'گزارش‌ها', 'icon': 'bi-file-earmark-bar-graph'},
    'messaging': {'name': 'پیام‌رسانی', 'icon': 'bi-chat-dots'},
    'settings': {'name': 'تنظیمات', 'icon': 'bi-gear'},
    'certificates': {'name': 'گواهینامه‌ها', 'icon': 'bi-award'},
}

ACTIONS = {
    'view': {'name': 'مشاهده', 'icon': 'bi-eye', 'color': '#1565c0'},
    'create': {'name': 'ایجاد', 'icon': 'bi-plus-circle', 'color': '#2e7d32'},
    'edit': {'name': 'ویرایش', 'icon': 'bi-pencil', 'color': '#e65100'},
    'delete': {'name': 'حذف', 'icon': 'bi-trash3', 'color': '#c62828'},
    'print': {'name': 'چاپ', 'icon': 'bi-printer', 'color': '#7b1fa2'},
    'export': {'name': 'خروجی', 'icon': 'bi-download', 'color': '#00838f'},
}


# ═══════════════════════════════════════════
#  مدیریت نقش‌ها
# ═══════════════════════════════════════════
@perms_bp.route('/roles')
@login_required
def roles_list():
    roles = Role.query.all()
    return render_template('perms/roles_list.html', roles=roles)


@perms_bp.route('/roles/add', methods=['GET', 'POST'])
@login_required
def add_role():
    if request.method == 'POST':
        role = Role(
            name=request.form['name'],
            description=request.form.get('description'),
            is_admin='is_admin' in request.form
        )
        db.session.add(role)
        db.session.commit()
        flash('نقش جدید ایجاد شد', 'success')
        return redirect(url_for('perms.edit_role_permissions', role_id=role.id))
    return render_template('perms/add_role.html')


@perms_bp.route('/roles/<int:role_id>/permissions', methods=['GET', 'POST'])
@login_required
def edit_role_permissions(role_id):
    """ویرایش دسترسی‌های یک نقش"""
    role = Role.query.get_or_404(role_id)
    
    if request.method == 'POST':
        # حذف دسترسی‌های قبلی
        RolePermission.query.filter_by(role_id=role_id).delete()
        
        # اضافه کردن دسترسی‌های جدید
        for module_key in MODULES:
            for action_key in ACTIONS:
                field_name = f'perm_{module_key}_{action_key}'
                if request.form.get(field_name):
                    # پیدا کردن یا ساخت permission
                    perm = Permission.query.filter_by(
                        module=module_key, action=action_key
                    ).first()
                    if not perm:
                        perm = Permission(
                            module=module_key,
                            action=action_key,
                            description=f'{ACTIONS[action_key]["name"]} {MODULES[module_key]["name"]}'
                        )
                        db.session.add(perm)
                        db.session.flush()
                    
                    rp = RolePermission(role_id=role_id, permission_id=perm.id)
                    db.session.add(rp)
        
        db.session.commit()
        flash('دسترسی‌ها بروزرسانی شد', 'success')
        return redirect(url_for('perms.roles_list'))
    
    # دریافت دسترسی‌های فعلی
    current_perms = set()
    for rp in RolePermission.query.filter_by(role_id=role_id).all():
        if rp.permission:
            current_perms.add(f'{rp.permission.module}_{rp.permission.action}')
    
    return render_template('perms/edit_permissions.html',
                         role=role, modules=MODULES, actions=ACTIONS,
                         current_perms=current_perms)


@perms_bp.route('/roles/<int:role_id>/delete', methods=['POST'])
@login_required
def delete_role(role_id):
    role = Role.query.get_or_404(role_id)
    if role.is_admin:
        flash('نقش مدیر کل قابل حذف نیست', 'error')
        return redirect(url_for('perms.roles_list'))
    
    RolePermission.query.filter_by(role_id=role_id).delete()
    db.session.delete(role)
    db.session.commit()
    flash('نقش حذف شد', 'success')
    return redirect(url_for('perms.roles_list'))


@perms_bp.route('/roles/<int:role_id>/copy', methods=['POST'])
@login_required
def copy_role(role_id):
    """کپی نقش"""
    original = Role.query.get_or_404(role_id)
    
    new_role = Role(
        name=f'{original.name} (کپی)',
        description=original.description,
        is_admin=False
    )
    db.session.add(new_role)
    db.session.flush()
    
    # کپی دسترسی‌ها
    for rp in RolePermission.query.filter_by(role_id=role_id).all():
        new_rp = RolePermission(role_id=new_role.id, permission_id=rp.permission_id)
        db.session.add(new_rp)
    
    db.session.commit()
    flash(f'نقش "{original.name}" کپی شد', 'success')
    return redirect(url_for('perms.edit_role_permissions', role_id=new_role.id))


# ═══════════════════════════════════════════
#  مدیریت کاربران
# ═══════════════════════════════════════════
@perms_bp.route('/users')
@login_required
def users_list():
    users = User.query.order_by(User.created_at.desc()).all()
    roles = Role.query.all()
    return render_template('perms/users_list.html', users=users, roles=roles)


@perms_bp.route('/users/add', methods=['GET', 'POST'])
@login_required
def add_user():
    if request.method == 'POST':
        # بررسی تکراری نبودن نام کاربری
        existing = User.query.filter_by(username=request.form['username']).first()
        if existing:
            flash('این نام کاربری قبلاً ثبت شده', 'error')
            return redirect(url_for('perms.add_user'))
        
        user = User(
            username=request.form['username'],
            full_name=request.form['full_name'],
            email=request.form.get('email'),
            phone=request.form.get('phone'),
            role_id=request.form.get('role_id'),
            branch_id=request.form.get('branch_id') or None,
            is_active=True,
            is_admin='is_admin' in request.form
        )
        user.set_password(request.form['password'])
        db.session.add(user)
        db.session.commit()
        flash(f'کاربر "{user.full_name}" ایجاد شد', 'success')
        return redirect(url_for('perms.users_list'))
    
    roles = Role.query.all()
    branches = Branch.query.all()
    return render_template('perms/add_user.html', roles=roles, branches=branches)


@perms_bp.route('/users/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit_user(id):
    user = User.query.get_or_404(id)
    
    if request.method == 'POST':
        user.full_name = request.form['full_name']
        user.email = request.form.get('email')
        user.phone = request.form.get('phone')
        user.role_id = request.form.get('role_id')
        user.branch_id = request.form.get('branch_id') or None
        user.is_active = 'is_active' in request.form
        user.is_admin = 'is_admin' in request.form
        
        if request.form.get('password'):
            user.set_password(request.form['password'])
        
        db.session.commit()
        flash('کاربر بروزرسانی شد', 'success')
        return redirect(url_for('perms.users_list'))
    
    roles = Role.query.all()
    branches = Branch.query.all()
    return render_template('perms/edit_user.html', user=user, roles=roles, branches=branches)


@perms_bp.route('/users/<int:id>/delete', methods=['POST'])
@login_required
def delete_user(id):
    user = User.query.get_or_404(id)
    if user.id == current_user.id:
        flash('نمی‌توانید خودتان را حذف کنید', 'error')
        return redirect(url_for('perms.users_list'))
    
    user.is_active = False
    db.session.commit()
    flash('کاربر غیرفعال شد', 'success')
    return redirect(url_for('perms.users_list'))


@perms_bp.route('/users/<int:id>/reset-password', methods=['POST'])
@login_required
def reset_password(id):
    user = User.query.get_or_404(id)
    new_pass = request.form.get('new_password', '123456')
    user.set_password(new_pass)
    db.session.commit()
    flash(f'رمز کاربر "{user.full_name}" تغییر کرد', 'success')
    return redirect(url_for('perms.edit_user', id=id))


# ═══════════════════════════════════════════
#  بررسی دسترسی (decorator)
# ═══════════════════════════════════════════
def check_permission(module, action):
    """بررسی دسترسی کاربر فعلی"""
    from flask import abort
    if current_user.is_admin:
        return True
    if current_user.has_permission(module, action):
        return True
    abort(403)
