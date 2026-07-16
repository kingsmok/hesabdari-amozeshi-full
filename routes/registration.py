"""Registration routes"""
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from extensions import db
from utils.form_helpers import get_jalali_date, safe_float, safe_int
from models.registration import Registration, Installment
from models.student import Student
from models.course import Course
from models.classes import ClassGroup
from models.finance import Payment, DiscountCode
from models.user import ActivityLog
from datetime import datetime, timedelta

registration_bp = Blueprint('registration', __name__)


@registration_bp.route('/')
@login_required
def index():
    page = request.args.get('page', 1, type=int)
    status = request.args.get('status', '')
    search = request.args.get('search', '')
    
    query = Registration.query
    if status:
        query = query.filter_by(status=status)
    if search:
        query = query.join(Student).filter(
            db.or_(
                Student.first_name.contains(search),
                Student.last_name.contains(search),
                Registration.reg_code.contains(search)
            )
        )
    
    registrations = query.order_by(Registration.created_at.desc()).paginate(page=page, per_page=20)
    return render_template('registration/index.html', registrations=registrations, status=status, search=search)


@registration_bp.route('/add', methods=['GET', 'POST'])
@login_required
def add():
    if request.method == 'POST':
        last = Registration.query.order_by(Registration.id.desc()).first()
        next_num = (last.id + 1) if last else 1
        code = f'REG-1405-{next_num:05d}'
        
        course = Course.query.get(request.form['course_id'])
        base_fee = safe_float(request.form.get('base_fee')) or (course.total_fee if course else 0)
        
        reg = Registration(
            reg_code=code,
            student_id=request.form['student_id'],
            course_id=request.form['course_id'],
            class_id=request.form.get('class_id') or None,
            teacher_id=request.form.get('teacher_id') or None,
            registration_date=datetime.utcnow().date(),
            start_date=get_jalali_date(request.form, 'start_date') if request.form.get('start_date') else None,
            base_fee=base_fee,
            discount_type=request.form.get('discount_type'),
            discount_value=safe_float(request.form.get('discount_value')),
            discount_code=request.form.get('discount_code'),
            status='active',
            is_reserved='is_reserved' in request.form,
            branch_id=request.form.get('branch_id', 1),
            notes=request.form.get('notes'),
            teacher_payment_type=request.form.get('teacher_payment_type'),
            teacher_payment_value=safe_float(request.form.get('teacher_payment_value')),
            created_by=current_user.id
        )
        
        # Apply discount code
        if reg.discount_code:
            dc = DiscountCode.query.filter_by(code=reg.discount_code, is_active=True).first()
            if dc:
                reg.discount_type = dc.discount_type
                reg.discount_value = dc.discount_value
                dc.used_count = (dc.used_count or 0) + 1
        
        reg.calculate_fees()
        
        # محاسبه مبلغ قابل پرداخت به مدرس
        if reg.teacher_payment_type == 'percentage':
            reg.teacher_payment_amount = reg.total_fee * (reg.teacher_payment_value / 100)
        elif reg.teacher_payment_type == 'fixed':
            reg.teacher_payment_amount = reg.teacher_payment_value
        else:
            reg.teacher_payment_amount = reg.teacher_payment_value
        
        # Initial payment
        initial_payment = safe_float(request.form.get('initial_payment'))
        if initial_payment > 0:
            reg.paid_amount = initial_payment
            reg.remaining_amount = reg.total_fee - initial_payment
            
            # شماره رسید یکتا با timestamp
            import uuid
            receipt_num = f'PAY-{datetime.now().strftime("%Y%m%d%H%M%S")}-{uuid.uuid4().hex[:4].upper()}'
            
            payment = Payment(
                receipt_no=receipt_num,
                student_id=reg.student_id,
                amount=initial_payment,
                payment_method=request.form.get('payment_method', 'cash'),
                payment_date=datetime.utcnow().date(),
                description=f'پرداخت اولیه ثبت‌نام {code}',
                branch_id=reg.branch_id,
                created_by=current_user.id
            )
            db.session.add(payment)
        
        # Update class count
        if reg.class_id:
            class_group = ClassGroup.query.get(reg.class_id)
            if class_group:
                class_group.current_count = (class_group.current_count or 0) + 1
        
        db.session.add(reg)
        
        log = ActivityLog(
            user_id=current_user.id, action='create', module='registration',
            entity_type='registration',
            description=f'ثبت‌نام: {reg.reg_code}',
            ip_address=request.remote_addr
        )
        db.session.add(log)
        db.session.commit()
        
        flash(f'ثبت‌نام {reg.reg_code} با موفقیت انجام شد', 'success')
        return redirect(url_for('registration.view', id=reg.id))
    
    students = Student.query.filter_by(status='active').order_by(Student.last_name).all()
    courses = Course.query.filter_by(is_active=True).all()
    classes = ClassGroup.query.filter_by(status='active').all()
    
    return render_template('registration/add.html', students=students, courses=courses, classes=classes)


@registration_bp.route('/<int:id>')
@login_required
def view(id):
    reg = Registration.query.get_or_404(id)
    payments = Payment.query.filter_by(registration_id=id).order_by(Payment.payment_date.desc()).all()
    installments = Installment.query.filter_by(registration_id=id).order_by(Installment.installment_number).all()
    
    return render_template('registration/view.html', reg=reg, payments=payments, installments=installments)


@registration_bp.route('/quick', methods=['GET', 'POST'])
@login_required
def quick():
    """Quick registration for reception"""
    if request.method == 'POST':
        # Similar to add but simplified
        return redirect(url_for('registration.add'))
    
    students = Student.query.filter_by(status='active').order_by(Student.last_name).all()
    classes = ClassGroup.query.filter_by(status='active').all()
    return render_template('registration/quick.html', students=students, classes=classes)


@registration_bp.route('/<int:id>/cancel', methods=['POST'])
@login_required
def cancel(id):
    reg = Registration.query.get_or_404(id)
    reg.status = 'withdrawn'
    reg.cancellation_reason = request.form.get('reason')
    reg.cancelled_by = current_user.id
    reg.cancelled_at = datetime.utcnow()
    
    # Update class count
    if reg.class_id:
        class_group = ClassGroup.query.get(reg.class_id)
        if class_group:
            class_group.current_count = max(0, (class_group.current_count or 0) - 1)
    
    db.session.commit()
    flash('ثبت‌نام لغو شد', 'warning')
    return redirect(url_for('registration.view', id=id))


@registration_bp.route('/<int:id>/installments', methods=['GET', 'POST'])
@login_required
def installments(id):
    reg = Registration.query.get_or_404(id)
    
    if request.method == 'POST':
        count = int(request.form.get('count', 3))
        first_date = get_jalali_date(request.form, 'first_date')
        amount = reg.remaining_amount / count
        
        for i in range(count):
            due = first_date + timedelta(days=30 * i)
            inst = Installment(
                registration_id=id,
                installment_number=i + 1,
                amount=round(amount),
                due_date=due,
                status='pending'
            )
            db.session.add(inst)
        
        db.session.commit()
        flash(f'{count} قسط ایجاد شد', 'success')
        return redirect(url_for('registration.view', id=id))
    
    installments = Installment.query.filter_by(registration_id=id).all()
    return render_template('registration/installments.html', reg=reg, installments=installments)
