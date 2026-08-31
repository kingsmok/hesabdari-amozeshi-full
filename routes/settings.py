"""Settings routes"""
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from license_client import license_required, licensed_section
from extensions import db
from utils.form_helpers import get_jalali_date, safe_float, safe_int
from models.system import SystemSettings, Branch, AcademicYear
from models.user import User, Role, Permission, RolePermission, ActivityLog
from models.course import Field, Course, Room, CertificateTemplate
from models.finance import ExpenseCategory
from models.system import MessageTemplate
from datetime import datetime

settings_bp = Blueprint('settings', __name__)


@settings_bp.route('/')
@login_required
def index():
    return redirect(url_for('settings.general'))


# ===== General Settings =====
@settings_bp.route('/general', methods=['GET', 'POST'])
@login_required
def general():
    settings = SystemSettings.query.first()
    if not settings:
        settings = SystemSettings()
        db.session.add(settings)
    
    if request.method == 'POST':
        settings.academy_name = request.form.get('academy_name')
        settings.academy_code = request.form.get('academy_code')
        settings.license_number = request.form.get('license_number')
        settings.manager_name = request.form.get('manager_name')
        settings.phone = request.form.get('phone')
        settings.fax = request.form.get('fax')
        settings.email = request.form.get('email')
        settings.website = request.form.get('website')
        settings.address = request.form.get('address')
        settings.current_year = request.form.get('current_year')
        settings.current_term = request.form.get('current_term')
        settings.welcome_message = request.form.get('welcome_message')
        settings.print_header = request.form.get('print_header')
        settings.print_footer = request.form.get('print_footer')
        
        db.session.commit()
        flash('تنظیمات ذخیره شد', 'success')
        return redirect(url_for('settings.general'))
    
    return render_template('settings/general.html', settings=settings)


# ===== Users =====
@settings_bp.route('/users')
@login_required
def users():
    users = User.query.order_by(User.created_at.desc()).all()
    return render_template('settings/users.html', users=users)


@settings_bp.route('/users/add', methods=['GET', 'POST'])
@login_required
def add_user():
    if request.method == 'POST':
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
        flash('کاربر جدید ایجاد شد', 'success')
        return redirect(url_for('settings.users'))
    
    roles = Role.query.all()
    branches = Branch.query.all()
    return render_template('settings/add_user.html', roles=roles, branches=branches)


@settings_bp.route('/users/<int:id>/edit', methods=['GET', 'POST'])
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
        return redirect(url_for('settings.users'))
    
    roles = Role.query.all()
    branches = Branch.query.all()
    return render_template('settings/edit_user.html', user=user, roles=roles, branches=branches)


# ===== Roles =====
@settings_bp.route('/roles')
@login_required
def roles():
    roles = Role.query.all()
    return render_template('settings/roles.html', roles=roles)


@settings_bp.route('/roles/add', methods=['GET', 'POST'])
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
        return redirect(url_for('settings.roles'))
    
    return render_template('settings/add_role.html')


# ===== Branches =====
@settings_bp.route('/branches')
@login_required
def branches():
    branches = Branch.query.all()
    return render_template('settings/branches.html', branches=branches)


@settings_bp.route('/branches/add', methods=['GET', 'POST'])
@login_required
def add_branch():
    if request.method == 'POST':
        branch = Branch(
            name=request.form['name'],
            code=request.form['code'],
            manager_name=request.form.get('manager_name'),
            phone=request.form.get('phone'),
            mobile=request.form.get('mobile'),
            email=request.form.get('email'),
            address=request.form.get('address'),
            is_main='is_main' in request.form
        )
        db.session.add(branch)
        db.session.commit()
        flash('شعبه جدید اضافه شد', 'success')
        return redirect(url_for('settings.branches'))
    
    return render_template('settings/add_branch.html')


# ===== Fields & Courses =====
@settings_bp.route('/fields')
@login_required
def fields():
    fields = Field.query.all()
    return render_template('settings/fields.html', fields=fields)


@settings_bp.route('/fields/add', methods=['POST'])
@login_required
def add_field():
    field = Field(
        name=request.form['name'],
        code=request.form['code'],
        description=request.form.get('description')
    )
    db.session.add(field)
    db.session.commit()
    flash('رشته اضافه شد', 'success')
    return redirect(url_for('settings.fields'))


@settings_bp.route('/courses')
@login_required
def courses():
    courses = Course.query.all()
    return render_template('settings/courses.html', courses=courses)


@settings_bp.route('/courses/add', methods=['GET', 'POST'])
@login_required
def add_course():
    if request.method == 'POST':
        course = Course(
            title=request.form['title'],
            code=request.form['code'],
            field_id=request.form['field_id'],
            description=request.form.get('description'),
            duration_hours=safe_int(request.form.get('duration_hours')),
            total_sessions=safe_int(request.form.get('total_sessions')),
            base_fee=safe_float(request.form.get('base_fee')),
            registration_fee=safe_float(request.form.get('registration_fee')),
            book_fee=safe_float(request.form.get('book_fee')),
            exam_fee=safe_float(request.form.get('exam_fee')),
            certificate_fee=safe_float(request.form.get('certificate_fee')),
            other_fees=safe_float(request.form.get('other_fees')),
            branch_id=request.form.get('branch_id', 1)
        )
        db.session.add(course)
        db.session.commit()
        flash('دوره اضافه شد', 'success')
        return redirect(url_for('settings.courses'))
    
    fields = Field.query.filter_by(is_active=True).all()
    return render_template('settings/add_course.html', fields=fields)


# ===== Rooms =====
@settings_bp.route('/rooms')
@login_required
def rooms():
    rooms = Room.query.all()
    return render_template('settings/rooms.html', rooms=rooms)


@settings_bp.route('/rooms/add', methods=['POST'])
@login_required
def add_room():
    room = Room(
        name=request.form['name'],
        code=request.form['code'],
        capacity=int(request.form.get('capacity', 20)),
        facilities=request.form.get('facilities'),
        branch_id=request.form.get('branch_id', 1)
    )
    db.session.add(room)
    db.session.commit()
    flash('اتاق اضافه شد', 'success')
    return redirect(url_for('settings.rooms'))


# ===== Expense Categories =====
def _expense_category_conflict(name, code=None, exclude_id=None):
    """بررسی تکراری نبودن نام و کد دسته‌بندی."""
    query = ExpenseCategory.query
    if exclude_id is not None:
        query = query.filter(ExpenseCategory.id != exclude_id)

    if query.filter(db.func.lower(ExpenseCategory.name) == name.lower()).first():
        return 'دسته‌بندی دیگری با این نام وجود دارد'

    if code and query.filter(db.func.lower(ExpenseCategory.code) == code.lower()).first():
        return 'دسته‌بندی دیگری با این کد وجود دارد'

    return None


def _category_form_values():
    name = (request.form.get('name') or '').strip()
    code = (request.form.get('code') or '').strip().upper() or None
    description = (request.form.get('description') or '').strip() or None
    return name, code, description


@settings_bp.route('/expense-categories')
@login_required
def expense_categories():
    categories = ExpenseCategory.query.order_by(
        ExpenseCategory.is_active.desc(), ExpenseCategory.name
    ).all()
    return render_template('settings/expense_categories.html', categories=categories)


@settings_bp.route('/expense-categories/pdf')
@login_required
def expense_categories_pdf():
    """فهرست دسته‌بندی‌ها در قالب PDF فارسی."""
    from utils.pdf_helpers import build_table_pdf

    categories = ExpenseCategory.query.order_by(
        ExpenseCategory.is_active.desc(), ExpenseCategory.name
    ).all()
    rows = [
        (
            category.code or '-',
            category.name,
            category.description or '-',
            'فعال' if category.is_active else 'غیرفعال',
            len(category.expenses)
        )
        for category in categories
    ]
    return build_table_pdf(
        'فهرست دسته‌بندی‌های هزینه',
        ['کد', 'نام دسته‌بندی', 'توضیحات', 'وضعیت', 'تعداد هزینه'],
        rows,
        'expense-categories.pdf',
        subtitle=f'تعداد دسته‌بندی‌ها: {len(rows)}',
        landscape_mode=True,
        download=request.args.get('download') == '1'
    )


@settings_bp.route('/expense-categories/add', methods=['POST'])
@login_required
def add_expense_category():
    name, code, description = _category_form_values()
    if not name:
        flash('نام دسته‌بندی هزینه الزامی است', 'danger')
        return redirect(url_for('settings.expense_categories'))

    conflict = _expense_category_conflict(name, code)
    if conflict:
        flash(conflict, 'danger')
        return redirect(url_for('settings.expense_categories'))

    cat = ExpenseCategory(
        name=name,
        code=code,
        description=description,
        is_active=True
    )
    db.session.add(cat)
    db.session.commit()
    flash(f'دسته‌بندی «{name}» اضافه شد', 'success')
    return redirect(url_for('settings.expense_categories'))


@settings_bp.route('/expense-categories/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit_expense_category(id):
    cat = ExpenseCategory.query.get_or_404(id)
    if request.method == 'POST':
        name, code, description = _category_form_values()
        if not name:
            flash('نام دسته‌بندی هزینه الزامی است', 'danger')
            return redirect(url_for('settings.edit_expense_category', id=id))

        conflict = _expense_category_conflict(name, code, exclude_id=id)
        if conflict:
            flash(conflict, 'danger')
            return redirect(url_for('settings.edit_expense_category', id=id))

        cat.name = name
        cat.code = code
        cat.description = description
        cat.is_active = 'is_active' in request.form
        db.session.commit()
        flash(f'دسته‌بندی «{name}» بروزرسانی شد', 'success')
        return redirect(url_for('settings.expense_categories'))

    categories = ExpenseCategory.query.order_by(
        ExpenseCategory.is_active.desc(), ExpenseCategory.name
    ).all()
    return render_template('settings/expense_categories.html', categories=categories, edit_cat=cat)


@settings_bp.route('/expense-categories/<int:id>/delete', methods=['POST'])
@login_required
def delete_expense_category(id):
    cat = ExpenseCategory.query.get_or_404(id)

    # دسته‌بندی استفاده‌شده یا والد را حذف نمی‌کنیم تا سوابق مالی خراب نشوند.
    if cat.expenses:
        flash('این دسته‌بندی در هزینه‌های ثبت‌شده استفاده شده و قابل حذف نیست؛ می‌توانید آن را غیرفعال کنید', 'danger')
    elif cat.children:
        flash('این دسته‌بندی دارای زیر‌دسته است و تا زمان حذف یا انتقال زیر‌دسته‌ها قابل حذف نیست', 'danger')
    else:
        name = cat.name
        db.session.delete(cat)
        db.session.commit()
        flash(f'دسته‌بندی «{name}» حذف شد', 'success')
    return redirect(url_for('settings.expense_categories'))


# ===== SMS Settings =====
@settings_bp.route('/sms', methods=['GET', 'POST'])
@login_required
def sms():
    """تنظیمات قدیمی پیامک به پنل اتصال واقعی منتقل شده است."""
    if request.method == 'POST':
        settings = SystemSettings.query.first()
        settings.sms_api_key = (request.form.get('sms_api_key') or '').strip()
        settings.sms_provider = request.form.get('sms_provider') or 'farazsms'
        settings.sms_sender = (request.form.get('sms_sender') or '').strip()
        if settings.sms_provider == 'farazsms':
            settings.farazsms_api_key = settings.sms_api_key
            settings.farazsms_sender = settings.sms_sender
        db.session.commit()
    return redirect(url_for('settings_panel.farazsms_config'))


# ===== Backup Settings =====
@settings_bp.route('/backup', methods=['GET', 'POST'])
@license_required
@login_required
@licensed_section('backup')
def backup():
    settings = SystemSettings.query.first()
    
    if request.method == 'POST':
        settings.auto_backup = 'auto_backup' in request.form
        settings.backup_interval_hours = int(request.form.get('backup_interval_hours', 24))
        settings.backup_path = request.form.get('backup_path')
        settings.max_backups = int(request.form.get('max_backups', 30))
        db.session.commit()
        flash('تنظیمات پشتیبان‌گیری ذخیره شد', 'success')
        return redirect(url_for('settings.backup'))
    
    return render_template('settings/backup.html', settings=settings)


# ===== Activity Log =====
@settings_bp.route('/logs')
@login_required
def logs():
    page = request.args.get('page', 1, type=int)
    logs = ActivityLog.query.order_by(ActivityLog.created_at.desc()).paginate(page=page, per_page=50)
    return render_template('settings/logs.html', logs=logs)


# ===== Message Templates =====
@settings_bp.route('/message-templates')
@login_required
def message_templates():
    templates = MessageTemplate.query.all()
    return render_template('settings/message_templates.html', templates=templates)


@settings_bp.route('/message-templates/add', methods=['POST'])
@login_required
def add_message_template():
    tmpl = MessageTemplate(
        name=request.form['name'],
        template_text=request.form['template_text'],
        template_type=request.form.get('template_type')
    )
    db.session.add(tmpl)
    db.session.commit()
    flash('قالب پیامک اضافه شد', 'success')
    return redirect(url_for('settings.message_templates'))


# ===== Academic Year =====
@settings_bp.route('/academic-year')
@login_required
def academic_year():
    years = AcademicYear.query.order_by(AcademicYear.year_name.desc()).all()
    return render_template('settings/academic_year.html', years=years)


@settings_bp.route('/academic-year/add', methods=['POST'])
@login_required
def add_academic_year():
    year = AcademicYear(
        year_name=request.form['year_name'],
        term_name=request.form.get('term_name'),
        start_date=get_jalali_date(request.form, 'start_date') if request.form.get('start_date') else None,
        end_date=get_jalali_date(request.form, 'end_date') if request.form.get('end_date') else None,
        is_current='is_current' in request.form
    )
    db.session.add(year)
    db.session.commit()
    flash('سال آموزشی اضافه شد', 'success')
    return redirect(url_for('settings.academic_year'))


# ===== Certificate Templates =====
@settings_bp.route('/cert-templates')
@login_required
def cert_templates():
    templates = CertificateTemplate.query.all()
    return render_template('settings/cert_templates.html', templates=templates)
