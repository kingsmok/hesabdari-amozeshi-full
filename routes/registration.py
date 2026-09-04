"""Registration routes"""
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from license_client import license_required, licensed_section
from extensions import db
from utils.document_numbers import next_document_number
from utils.form_helpers import get_jalali_date, safe_float, safe_int
from utils.jalali import current_jalali_year
from utils.payments import build_receipt_no
from models.registration import Registration, Installment
from models.student import Student
from models.course import Course
from models.classes import ClassGroup
from models.finance import Payment, DiscountCode
from models.user import ActivityLog
from datetime import datetime, timedelta

registration_bp = Blueprint('registration', __name__)


@registration_bp.route('/')
@license_required
@login_required
@licensed_section('registration')
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
        student_id = request.form.get('student_id', type=int)
        course_id = request.form.get('course_id', type=int)
        class_id = request.form.get('class_id', type=int)
        student = Student.query.filter_by(id=student_id, status='active').first() if student_id else None
        course = Course.query.filter_by(id=course_id, is_active=True).first() if course_id else None
        class_group = ClassGroup.query.filter_by(id=class_id, status='active').first() if class_id else None

        if not student or not course:
            flash('هنرجو یا دوره انتخاب‌شده معتبر نیست', 'danger')
            return redirect(url_for('registration.add'))
        if class_group and class_group.course_id != course.id:
            flash('کلاس انتخاب‌شده متعلق به این دوره نیست', 'danger')
            return redirect(url_for('registration.add'))
        if class_group and class_group.is_full:
            flash('ظرفیت کلاس انتخاب‌شده تکمیل است', 'danger')
            return redirect(url_for('registration.add'))
        duplicate = Registration.query.filter_by(
            student_id=student.id, course_id=course.id, status='active'
        ).first()
        if duplicate:
            flash(f'این هنرجو قبلاً ثبت‌نام فعال {duplicate.reg_code} را در این دوره دارد', 'warning')
            return redirect(url_for('registration.view', id=duplicate.id))

        code = next_document_number('registration')
        base_fee = safe_float(request.form.get('base_fee')) or course.total_fee
        
        reg = Registration(
            reg_code=code,
            student_id=student.id,
            course_id=course.id,
            class_id=class_group.id if class_group else None,
            teacher_id=(class_group.teacher_id if class_group else request.form.get('teacher_id', type=int)),
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
            dc = DiscountCode.query.filter_by(code=reg.discount_code.strip(), is_active=True).first()
            today = datetime.utcnow().date()
            discount_valid = bool(
                dc and
                (not dc.valid_from or dc.valid_from <= today) and
                (not dc.valid_until or dc.valid_until >= today) and
                (dc.max_uses is None or (dc.used_count or 0) < dc.max_uses)
            )
            if discount_valid:
                reg.discount_type = dc.discount_type
                reg.discount_value = dc.discount_value
                dc.used_count = (dc.used_count or 0) + 1
            else:
                flash('کد تخفیف نامعتبر، منقضی یا به سقف استفاده رسیده است', 'danger')
                return redirect(url_for('registration.add'))
        
        reg.calculate_fees()
        
        # محاسبه مبلغ قابل پرداخت به مدرس
        if reg.teacher_payment_type == 'percentage':
            reg.teacher_payment_amount = reg.total_fee * (reg.teacher_payment_value / 100)
        elif reg.teacher_payment_type == 'fixed':
            reg.teacher_payment_amount = reg.teacher_payment_value
        else:
            reg.teacher_payment_amount = reg.teacher_payment_value
        
        initial_payment = safe_float(request.form.get('initial_payment'))
        if initial_payment < 0 or initial_payment > reg.total_fee:
            flash('پرداخت اولیه نمی‌تواند منفی یا بیشتر از شهریه نهایی باشد', 'danger')
            return redirect(url_for('registration.add'))

        # ابتدا ثبت‌نام flush می‌شود تا پرداخت اولیه حتماً به registration_id متصل باشد.
        db.session.add(reg)
        db.session.flush()

        if initial_payment > 0:
            reg.paid_amount = initial_payment
            reg.remaining_amount = reg.total_fee - initial_payment
            
            # شماره رسید از همان توالی مستندات (`PAY-1405-00042`)؛ قالب قدیمی
            # `PAY-<زمان>-<uuid>` بود که هم با بقیه سیستم فرق داشت و هم با ۲۶
            # کاراکتر از طول ستون (String(20)) بیرون می‌زد
            receipt_num = build_receipt_no()
            payment_method = request.form.get('payment_method', 'cash')
            payment = Payment(
                receipt_no=receipt_num,
                student_id=reg.student_id,
                registration_id=reg.id,
                amount=initial_payment,
                payment_method=payment_method,
                payment_date=datetime.utcnow().date(),
                description=f'پرداخت اولیه ثبت‌نام {code}',
                status='confirmed',
                branch_id=reg.branch_id,
                created_by=current_user.id
            )
            db.session.add(payment)

            # اتصال پرداخت به صندوق از همان یارد مشترک: سهم نقدی (شامل
            # پرداخت ترکیبی) + ثبت `cashbox_id` تا ابطال/مرجوعی بعداً قابل
            # محاسبه باشد.
            from utils.payments import cash_portion, settle_cashbox
            db.session.flush()
            ok, message = settle_cashbox(
                payment, cash_portion(payment), f'پرداخت اولیه {code}',
                user_id=current_user.id, direction='in')
            if not ok:
                db.session.rollback()
                flash(message, 'danger')
                return redirect(url_for('registration.add'))

        if class_group:
            class_group.current_count = Registration.query.filter_by(
                class_id=class_group.id, status='active'
            ).count()
        
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
    if reg.status != 'active':
        flash('این ثبت‌نام قبلاً از حالت فعال خارج شده است', 'warning')
        return redirect(url_for('registration.view', id=id))

    reg.status = 'withdrawn'
    reg.cancellation_reason = request.form.get('reason')
    reg.cancelled_by = current_user.id
    reg.cancelled_at = datetime.utcnow()
    
    # Update class count
    if reg.class_id:
        class_group = ClassGroup.query.get(reg.class_id)
        if class_group:
            class_group.current_count = Registration.query.filter_by(
                class_id=class_group.id, status='active'
            ).count()
    
    db.session.commit()
    flash('ثبت‌نام لغو شد', 'warning')
    return redirect(url_for('registration.view', id=id))


@registration_bp.route('/<int:id>/installments', methods=['GET', 'POST'])
@login_required
def installments(id):
    reg = Registration.query.get_or_404(id)
    
    if request.method == 'POST':
        count = request.form.get('count', 3, type=int)
        first_date = get_jalali_date(request.form, 'first_date')
        existing_count = Installment.query.filter_by(registration_id=id).count()

        if not count or not (1 <= count <= 24):
            flash('تعداد اقساط باید بین ۱ تا ۲۴ باشد', 'danger')
            return redirect(url_for('registration.installments', id=id))
        if not first_date:
            flash('تاریخ اولین قسط معتبر نیست', 'danger')
            return redirect(url_for('registration.installments', id=id))
        if (reg.remaining_amount or 0) <= 0:
            flash('این ثبت‌نام مانده قابل تقسیط ندارد', 'warning')
            return redirect(url_for('registration.view', id=id))
        if existing_count:
            flash('برای این ثبت‌نام قبلاً برنامه اقساط ایجاد شده است', 'warning')
            return redirect(url_for('registration.view', id=id))

        amount = round(reg.remaining_amount / count)
        for i in range(count):
            due = first_date + timedelta(days=30 * i)
            installment_amount = amount if i < count - 1 else round(reg.remaining_amount - amount * (count - 1))
            inst = Installment(
                registration_id=id,
                installment_number=i + 1,
                amount=installment_amount,
                due_date=due,
                status='pending'
            )
            db.session.add(inst)
        
        db.session.commit()
        flash(f'{count} قسط ایجاد شد', 'success')
        return redirect(url_for('registration.view', id=id))
    
    installments = Installment.query.filter_by(registration_id=id).all()
    return render_template('registration/installments.html', reg=reg, installments=installments)
