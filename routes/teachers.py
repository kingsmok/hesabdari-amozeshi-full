"""Teachers routes"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from license_client import license_required, licensed_section
from extensions import db
from utils.document_numbers import next_document_number
from utils.form_helpers import get_jalali_date, safe_float, safe_int
from utils.jalali import current_jalali_year
from models.teacher import Teacher, TeacherDocument, TeacherEvaluation
from datetime import datetime

teachers_bp = Blueprint('teachers', __name__)


@teachers_bp.route('/')
@license_required
@login_required
@licensed_section('teachers')
def index():
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '')
    
    query = Teacher.query
    if search:
        query = query.filter(
            db.or_(
                Teacher.first_name.contains(search),
                Teacher.last_name.contains(search),
                Teacher.teacher_code.contains(search),
                Teacher.specialization.contains(search)
            )
        )
    
    teachers = query.order_by(Teacher.created_at.desc()).paginate(page=page, per_page=20)
    return render_template('teachers/index.html', teachers=teachers, search=search)


@teachers_bp.route('/add', methods=['GET', 'POST'])
@login_required
def add():
    if request.method == 'POST':
        code = next_document_number('teacher', width=3)
        
        teacher = Teacher(
            teacher_code=code,
            first_name=request.form['first_name'],
            last_name=request.form['last_name'],
            father_name=request.form.get('father_name'),
            national_code=request.form.get('national_code'),
            birth_date=get_jalali_date(request.form, 'birth_date') if request.form.get('birth_date') else None,
            mobile=request.form['mobile'],
            phone=request.form.get('phone'),
            email=request.form.get('email'),
            address=request.form.get('address'),
            specialization=request.form.get('specialization'),
            education=request.form.get('education'),
            experience_years=safe_int(request.form.get('experience_years')),
            skills=request.form.get('skills'),
            level=request.form.get('level', 'intermediate'),
            contract_type=request.form.get('contract_type'),
            hourly_rate=safe_float(request.form.get('hourly_rate')),
            percentage_rate=safe_float(request.form.get('percentage_rate')),
            fixed_salary=safe_float(request.form.get('fixed_salary')),
            session_rate=safe_float(request.form.get('session_rate')),
            contract_start=get_jalali_date(request.form, 'contract_start') if request.form.get('contract_start') else None,
            contract_end=get_jalali_date(request.form, 'contract_end') if request.form.get('contract_end') else None,
            branch_id=request.form.get('branch_id', 1),
            is_active=True,
            notes=request.form.get('notes')
        )
        
        db.session.add(teacher)
        
        # نقطهٔ مشترک لاگ (DRY)
        from utils.activity_log import log_activity
        log_activity('create', f'ثبت مدرس: {teacher.full_name}',
                     module='teachers', entity_type='teacher', entity_id=teacher.id)
        db.session.commit()
        
        flash(f'مدرس "{teacher.full_name}" ثبت شد', 'success')
        return redirect(url_for('teachers.view', id=teacher.id))
    
    return render_template('teachers/add.html')


@teachers_bp.route('/<int:id>')
@login_required
def view(id):
    teacher = Teacher.query.get_or_404(id)
    classes = teacher.active_classes
    evaluations = TeacherEvaluation.query.filter_by(teacher_id=id).order_by(TeacherEvaluation.created_at.desc()).limit(20).all()
    documents = TeacherDocument.query.filter_by(teacher_id=id).all()
    
    return render_template('teachers/view.html', teacher=teacher, classes=classes,
                         evaluations=evaluations, documents=documents)


@teachers_bp.route('/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit(id):
    teacher = Teacher.query.get_or_404(id)
    
    if request.method == 'POST':
        teacher.first_name = request.form['first_name']
        teacher.last_name = request.form['last_name']
        teacher.father_name = request.form.get('father_name')
        teacher.national_code = request.form.get('national_code')
        teacher.mobile = request.form['mobile']
        teacher.phone = request.form.get('phone')
        teacher.email = request.form.get('email')
        teacher.address = request.form.get('address')
        teacher.specialization = request.form.get('specialization')
        teacher.education = request.form.get('education')
        teacher.experience_years = safe_int(request.form.get('experience_years'))
        teacher.skills = request.form.get('skills')
        teacher.level = request.form.get('level')
        teacher.contract_type = request.form.get('contract_type')
        teacher.hourly_rate = safe_float(request.form.get('hourly_rate'))
        teacher.percentage_rate = safe_float(request.form.get('percentage_rate'))
        teacher.fixed_salary = safe_float(request.form.get('fixed_salary'))
        teacher.session_rate = safe_float(request.form.get('session_rate'))
        teacher.is_active = 'is_active' in request.form
        teacher.notes = request.form.get('notes')
        
        db.session.commit()
        flash('اطلاعات مدرس بروزرسانی شد', 'success')
        return redirect(url_for('teachers.view', id=id))
    
    return render_template('teachers/edit.html', teacher=teacher)


@teachers_bp.route('/<int:id>/schedule')
@login_required
def schedule(id):
    teacher = Teacher.query.get_or_404(id)
    return render_template('teachers/schedule.html', teacher=teacher)


@teachers_bp.route('/search')
@login_required
def search():
    q = request.args.get('q', '')
    if len(q) < 2:
        return jsonify([])
    
    teachers = Teacher.query.filter(
        db.or_(
            Teacher.first_name.contains(q),
            Teacher.last_name.contains(q),
            Teacher.teacher_code.contains(q)
        ),
        Teacher.is_active == True
    ).limit(20).all()
    
    return jsonify([{
        'id': t.id,
        'code': t.teacher_code,
        'name': t.full_name,
        'specialization': t.specialization or ''
    } for t in teachers])
