"""Students routes"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from license_client import license_required, licensed_section
from extensions import db
from utils.document_numbers import next_document_number
from utils.form_helpers import get_jalali_date
from utils.jalali import current_jalali_year
from models.student import Student, StudentDocument, WaitingList
from models.registration import Registration
from datetime import datetime
import json

students_bp = Blueprint('students', __name__)


@students_bp.route('/')
@license_required
@login_required
@licensed_section('students')
def index():
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    # Filters
    search = request.args.get('search', '')
    status = request.args.get('status', '')
    category = request.args.get('category', '')
    branch = request.args.get('branch', '')
    
    query = Student.query
    
    if search:
        query = query.filter(
            db.or_(
                Student.first_name.contains(search),
                Student.last_name.contains(search),
                Student.student_code.contains(search),
                Student.national_code.contains(search),
                Student.mobile.contains(search)
            )
        )
    if status:
        query = query.filter_by(status=status)
    if category:
        query = query.filter_by(category=category)
    if branch:
        query = query.filter_by(branch_id=branch)
    
    students = query.order_by(Student.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    return render_template('students/index.html', students=students, 
                         search=search, status=status, category=category)


@students_bp.route('/add', methods=['GET', 'POST'])
@login_required
def add():
    if request.method == 'POST':
        # Generate student code
        code = next_document_number('student')
        
        student = Student(
            student_code=code,
            first_name=request.form['first_name'],
            last_name=request.form['last_name'],
            father_name=request.form.get('father_name'),
            national_code=(request.form.get('national_code') or '').strip() or None,
            birth_certificate_no=request.form.get('birth_certificate_no'),
            birth_date=get_jalali_date(request.form, 'birth_date') if request.form.get('birth_date') else None,
            gender=request.form.get('gender'),
            marital_status=request.form.get('marital_status'),
            education_level=request.form.get('education_level'),
            job=request.form.get('job'),
            workplace=request.form.get('workplace'),
            mobile=request.form['mobile'],
            mobile2=request.form.get('mobile2'),
            phone=request.form.get('phone'),
            email=request.form.get('email'),
            address=request.form.get('address'),
            postal_code=request.form.get('postal_code'),
            emergency_phone=request.form.get('emergency_phone'),
            parent_name=request.form.get('parent_name'),
            parent_mobile=request.form.get('parent_mobile'),
            parent_job=request.form.get('parent_job'),
            parent_relation=request.form.get('parent_relation'),
            referral_source=request.form.get('referral_source'),
            category=request.form.get('category'),
            status='active',
            branch_id=request.form.get('branch_id', 1),
            notes=request.form.get('notes'),
            description=request.form.get('description'),
            created_by=current_user.id
        )
        
        db.session.add(student)
        
        # Log — نقطهٔ مشترک لاگ (DRY)
        from utils.activity_log import log_activity
        log_activity('create', f'ثبت هنرجو: {student.full_name}',
                     module='students', entity_type='student', entity_id=student.id)
        db.session.commit()
        
        flash(f'هنرجو "{student.full_name}" با موفقیت ثبت شد', 'success')
        return redirect(url_for('students.view', id=student.id))
    
    return render_template('students/add.html')


@students_bp.route('/<int:id>')
@login_required
def view(id):
    student = Student.query.get_or_404(id)
    registrations = Registration.query.filter_by(student_id=id).order_by(Registration.created_at.desc()).all()
    documents = StudentDocument.query.filter_by(student_id=id).all()
    
    return render_template('students/view.html', 
                         student=student, 
                         registrations=registrations,
                         documents=documents)


@students_bp.route('/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit(id):
    student = Student.query.get_or_404(id)
    
    if request.method == 'POST':
        student.first_name = request.form['first_name']
        student.last_name = request.form['last_name']
        student.father_name = request.form.get('father_name')
        student.national_code = (request.form.get('national_code') or '').strip() or None
        student.birth_certificate_no = request.form.get('birth_certificate_no')
        student.birth_date = get_jalali_date(request.form, 'birth_date') if request.form.get('birth_date') else None
        student.gender = request.form.get('gender')
        student.marital_status = request.form.get('marital_status')
        student.education_level = request.form.get('education_level')
        student.job = request.form.get('job')
        student.workplace = request.form.get('workplace')
        student.mobile = request.form['mobile']
        student.mobile2 = request.form.get('mobile2')
        student.phone = request.form.get('phone')
        student.email = request.form.get('email')
        student.address = request.form.get('address')
        student.postal_code = request.form.get('postal_code')
        student.emergency_phone = request.form.get('emergency_phone')
        student.parent_name = request.form.get('parent_name')
        student.parent_mobile = request.form.get('parent_mobile')
        student.referral_source = request.form.get('referral_source')
        student.category = request.form.get('category')
        student.status = request.form.get('status')
        student.notes = request.form.get('notes')
        
        # نقطهٔ مشترک لاگ (DRY)
        from utils.activity_log import log_activity
        log_activity('edit', f'ویرایش هنرجو: {student.full_name}',
                     module='students', entity_type='student', entity_id=id)
        db.session.commit()
        
        flash('اطلاعات هنرجو بروزرسانی شد', 'success')
        return redirect(url_for('students.view', id=id))
    
    return render_template('students/edit.html', student=student)


@students_bp.route('/<int:id>/history')
@login_required
def history(id):
    student = Student.query.get_or_404(id)
    registrations = Registration.query.filter_by(student_id=id).order_by(Registration.created_at.desc()).all()
    
    return render_template('students/history.html', student=student, registrations=registrations)


@students_bp.route('/search')
@login_required
def search():
    q = request.args.get('q', '')
    if len(q) < 2:
        return jsonify([])
    
    students = Student.query.filter(
        db.or_(
            Student.first_name.contains(q),
            Student.last_name.contains(q),
            Student.student_code.contains(q),
            Student.mobile.contains(q),
            Student.national_code.contains(q)
        )
    ).limit(20).all()
    
    return jsonify([{
        'id': s.id,
        'code': s.student_code,
        'name': s.full_name,
        'mobile': s.mobile,
        'status': s.status
    } for s in students])


@students_bp.route('/waiting-list')
@login_required
def waiting_list():
    entries = WaitingList.query.filter_by(status='waiting').order_by(WaitingList.priority).all()
    return render_template('students/waiting_list.html', entries=entries)


@students_bp.route('/<int:id>/delete', methods=['POST'])
@login_required
def delete(id):
    student = Student.query.get_or_404(id)
    if student.status == 'withdrawn':
        flash('این هنرجو قبلاً غیرفعال شده است', 'warning')
        return redirect(url_for('students.index'))

    student.status = 'withdrawn'
    affected_class_ids = set()
    for registration in student.registrations.filter_by(status='active').all():
        registration.status = 'withdrawn'
        registration.cancellation_reason = 'غیرفعال شدن پرونده هنرجو'
        registration.cancelled_by = current_user.id
        registration.cancelled_at = datetime.utcnow()
        if registration.class_id:
            affected_class_ids.add(registration.class_id)

    from models.classes import ClassGroup
    db.session.flush()
    for class_id in affected_class_ids:
        class_group = db.session.get(ClassGroup, class_id)
        if class_group:
            class_group.current_count = Registration.query.filter_by(
                class_id=class_id, status='active'
            ).count()
    
    # نقطهٔ مشترک لاگ (DRY)
    from utils.activity_log import log_activity
    log_activity('delete', f'حذف(غیرفعال) هنرجو: {student.full_name}',
                 module='students', entity_type='student', entity_id=id)
    db.session.commit()
    
    flash('هنرجو غیرفعال شد', 'warning')
    return redirect(url_for('students.index'))
