"""Exams routes"""
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from extensions import db
from utils.form_helpers import get_jalali_date, safe_float, safe_int
from utils.jalali import current_jalali_year
from models.exam import Exam, QuestionBank, ExamResult, Grade
from models.course import Course
from models.classes import ClassGroup
from models.student import Student
from models.user import ActivityLog
from datetime import datetime

exams_bp = Blueprint('exams', __name__)


@exams_bp.route('/')
@login_required
def index():
    page = request.args.get('page', 1, type=int)
    exams = Exam.query.order_by(Exam.created_at.desc()).paginate(page=page, per_page=20)
    return render_template('exams/index.html', exams=exams)


@exams_bp.route('/add', methods=['GET', 'POST'])
@login_required
def add():
    if request.method == 'POST':
        course_id = request.form.get('course_id', type=int)
        class_id = request.form.get('class_id', type=int)
        course = Course.query.filter_by(id=course_id, is_active=True).first() if course_id else None
        class_group = ClassGroup.query.filter_by(id=class_id, status='active').first() if class_id else None
        if not course or (class_group and class_group.course_id != course.id):
            flash('دوره یا کلاس انتخاب‌شده معتبر و هماهنگ نیست', 'danger')
            return redirect(url_for('exams.add'))

        theory_weight = safe_float(request.form.get('theory_weight'), 60)
        practical_weight = safe_float(request.form.get('practical_weight'), 40)
        if round(theory_weight + practical_weight, 5) != 100:
            flash('مجموع وزن نمره نظری و عملی باید ۱۰۰ درصد باشد', 'danger')
            return redirect(url_for('exams.add'))
        total_marks = max(1, safe_float(request.form.get('total_marks'), 100))
        passing_marks = max(0, safe_float(request.form.get('passing_marks'), 50))
        if passing_marks > total_marks:
            flash('نمره قبولی نمی‌تواند بیشتر از نمره کل باشد', 'danger')
            return redirect(url_for('exams.add'))

        last = Exam.query.order_by(Exam.id.desc()).first()
        next_num = (last.id + 1) if last else 1
        code = f'EXM-{current_jalali_year()}-{next_num:03d}'
        
        exam = Exam(
            title=request.form['title'],
            exam_code=code,
            course_id=course.id,
            class_id=class_group.id if class_group else None,
            exam_type=request.form.get('exam_type', 'written'),
            exam_date=get_jalali_date(request.form, 'exam_date') if request.form.get('exam_date') else None,
            start_time=request.form.get('start_time'),
            end_time=request.form.get('end_time'),
            duration_minutes=max(1, safe_int(request.form.get('duration_minutes'), 60)),
            total_marks=total_marks,
            passing_marks=passing_marks,
            theory_weight=theory_weight,
            practical_weight=practical_weight,
            status='draft',
            notes=request.form.get('notes'),
            created_by=current_user.id
        )
        db.session.add(exam)
        db.session.commit()
        
        flash(f'آزمون "{exam.title}" ایجاد شد', 'success')
        return redirect(url_for('exams.view', id=exam.id))
    
    courses = Course.query.filter_by(is_active=True).all()
    classes = ClassGroup.query.filter_by(status='active').all()
    return render_template('exams/add.html', courses=courses, classes=classes)


@exams_bp.route('/<int:id>')
@login_required
def view(id):
    exam = Exam.query.get_or_404(id)
    results = ExamResult.query.filter_by(exam_id=id).all()
    return render_template('exams/view.html', exam=exam, results=results)


@exams_bp.route('/<int:id>/grade', methods=['GET', 'POST'])
@login_required
def grade(id):
    exam = Exam.query.get_or_404(id)
    
    if request.method == 'POST':
        if exam.class_id:
            registrations = exam.class_group.registrations.filter_by(status='active').all()
            existing_by_student = {
                r.student_id: r
                for r in ExamResult.query.filter_by(exam_id=id).all()
            }
            for reg in registrations:
                max_score = exam.total_marks or 100
                theory = max(0, min(safe_float(request.form.get(f'theory_{reg.student_id}')), max_score))
                practical = max(0, min(safe_float(request.form.get(f'practical_{reg.student_id}')), max_score))
                
                total = (theory * (exam.theory_weight or 0) / 100) + (practical * (exam.practical_weight or 0) / 100)
                passed = total >= (exam.passing_marks or 0)
                
                existing = existing_by_student.get(reg.student_id)
                if existing:
                    existing.theory_score = theory
                    existing.practical_score = practical
                    existing.total_score = total
                    existing.is_passed = passed
                else:
                    result = ExamResult(
                        exam_id=id,
                        student_id=reg.student_id,
                        theory_score=theory,
                        practical_score=practical,
                        total_score=total,
                        is_passed=passed,
                        graded_by=current_user.id,
                        graded_at=datetime.utcnow()
                    )
                    db.session.add(result)
        
        exam.status = 'completed'
        db.session.commit()
        flash('نمرات ثبت شد', 'success')
        return redirect(url_for('exams.view', id=id))
    
    students = []
    if exam.class_id:
        registrations = exam.class_group.registrations.filter_by(status='active').all()
        for reg in registrations:
            result = ExamResult.query.filter_by(exam_id=id, student_id=reg.student_id).first()
            students.append({'student': reg.student, 'result': result})
    
    return render_template('exams/grade.html', exam=exam, students=students)


@exams_bp.route('/question-bank')
@login_required
def question_bank():
    page = request.args.get('page', 1, type=int)
    questions = QuestionBank.query.order_by(QuestionBank.created_at.desc()).paginate(page=page, per_page=20)
    return render_template('exams/question_bank.html', questions=questions)


@exams_bp.route('/question-bank/add', methods=['GET', 'POST'])
@login_required
def add_question():
    if request.method == 'POST':
        q = QuestionBank(
            question_text=request.form['question_text'],
            question_type=request.form['question_type'],
            option_a=request.form.get('option_a'),
            option_b=request.form.get('option_b'),
            option_c=request.form.get('option_c'),
            option_d=request.form.get('option_d'),
            correct_answer=request.form.get('correct_answer'),
            course_id=request.form.get('course_id') or None,
            chapter=request.form.get('chapter'),
            difficulty=request.form.get('difficulty', 'medium'),
            marks=max(0, safe_float(request.form.get('marks'), 1)),
            explanation=request.form.get('explanation'),
            created_by=current_user.id
        )
        db.session.add(q)
        db.session.commit()
        flash('سوال اضافه شد', 'success')
        return redirect(url_for('exams.question_bank'))
    
    courses = Course.query.filter_by(is_active=True).all()
    return render_template('exams/add_question.html', courses=courses)


@exams_bp.route('/grades')
@login_required
def grades():
    page = request.args.get('page', 1, type=int)
    class_id = request.args.get('class_id', type=int)
    
    query = Grade.query
    if class_id:
        query = query.filter_by(class_id=class_id)
    
    grades = query.order_by(Grade.created_at.desc()).paginate(page=page, per_page=30)
    classes = ClassGroup.query.filter_by(status='active').all()
    
    return render_template('exams/grades.html', grades=grades, classes=classes, class_id=class_id)


@exams_bp.route('/<int:exam_id>/appeal/<int:result_id>', methods=['POST'])
@login_required
def appeal(exam_id, result_id):
    result = ExamResult.query.filter_by(id=result_id, exam_id=exam_id).first_or_404()
    result.appeal_requested = True
    result.appeal_description = request.form.get('description')
    result.appeal_status = 'pending'
    db.session.commit()
    flash('اعتراض ثبت شد', 'info')
    return redirect(url_for('exams.view', id=exam_id))
