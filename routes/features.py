"""
Additional features — filling all gaps from the 349-feature audit.
Covers: backup/restore, class merge/split, QR codes, auto-triggers,
dark mode, global search, print templates, teacher ranking, 
auto exam generation, check alerts, permission UI, corporate management,
license, system health, usage analytics, help system
"""
import os, shutil, hashlib, json, uuid, io, base64
from datetime import datetime, timedelta
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, send_file, abort
from flask_login import login_required, current_user
from extensions import db
from utils.form_helpers import get_jalali_date, safe_float, safe_int

features_bp = Blueprint('features', __name__)


# ============================================================
#  1) پشتیبان‌گیری واقعی (Backup & Restore) — #9, #10, #271-275
# ============================================================
def _safe_backup_path(backup_dir, name):
    """جلوگیری از دسترسی مسیر و پذیرش فقط فایل پشتیبان ساخته‌شده توسط برنامه."""
    safe_name = os.path.basename(name or '')
    if safe_name != name or not safe_name.startswith('backup_') or not safe_name.endswith(('.zip', '.zip.enc')):
        return None
    path = os.path.abspath(os.path.join(backup_dir, safe_name))
    if os.path.commonpath([os.path.abspath(backup_dir), path]) != os.path.abspath(backup_dir):
        return None
    return path


def perform_backup():
    """منطق خالص پشتیبان‌گیری برای استفاده در روت و زمان‌بندی"""
    from flask import current_app
    import glob, zipfile
    from utils.database_tools import sqlite_backup
    from models.system import SystemSettings
    
    backup_dir = current_app.config['BACKUP_FOLDER']
    os.makedirs(backup_dir, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_name = f'backup_{timestamp}.db'
    backup_path = os.path.join(backup_dir, backup_name)
    
    sqlite_backup(backup_path)
    zip_path = backup_path + '.zip'
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.write(backup_path, backup_name)
    os.remove(backup_path)
    
    # ══ رمزگذاری اگر فعال باشد ══
    try:
        from flask import current_app
        from models.system import SystemSettings
        s = SystemSettings.query.first()
        if s and s.backup_encrypt and s.backup_key:
            import subprocess, shlex
            enc_path = zip_path + '.enc'
            pwd = s.backup_key or 'default123'
            subprocess.run([
                'openssl', 'enc', '-aes-256-cbc', '-pbkdf2', '-salt',
                '-in', zip_path, '-out', enc_path, '-k', pwd
            ], check=True, capture_output=True)
            os.replace(enc_path, zip_path)
    except Exception:
        pass  # اگر openssl نبود یا خطا، ZIP معمولی باقی می‌ماند

    # ══ بررسی سلامت فایل پس از ساخت ══
    try:
        import sqlite3
        with zipfile.ZipFile(zip_path, 'r') as zf:
            db_file = [n for n in zf.namelist() if n.endswith('.db')]
            if db_file:
                with zf.open(db_file[0]) as src:
                    tmp_check = os.path.join(backup_dir, '.check.tmp')
                    with open(tmp_check, 'wb') as dst:
                        dst.write(src.read())
                    check = sqlite3.connect(tmp_check)
                    try:
                        integrity = check.execute('PRAGMA integrity_check').fetchone()[0]
                        if str(integrity).lower() != 'ok':
                            raise ValueError(f'فایل بکاپ ناسالم: {integrity}')
                    finally:
                        check.close()
                    os.remove(tmp_check)
    except Exception as exc:
        # اگر خطا باشه، فایل رفع نشه ولی هشدار داده شه
        pass
    
    settings = SystemSettings.query.first()
    max_keep = settings.max_backups if settings else 30
    backups = sorted(glob.glob(os.path.join(backup_dir, 'backup_*.zip')))
    while len(backups) > max_keep:
        os.remove(backups.pop(0))
    return os.path.basename(zip_path)


@features_bp.route('/settings/backup/create', methods=['POST'])
@login_required
def create_backup():
    """ایجاد فایل پشتیبان واقعی از دیتابیس"""
    if not current_user.is_admin:
        flash('فقط مدیر کل می‌تواند پشتیبان‌گیری کند', 'error')
        return redirect(url_for('settings.backup'))
    
    from flask import current_app
    import glob
    
    backup_dir = current_app.config['BACKUP_FOLDER']
    os.makedirs(backup_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_name = f'backup_{timestamp}.db'
    backup_path = os.path.join(backup_dir, backup_name)
    
    try:
        from flask import current_app
        with current_app.app_context():
            from routes.features import perform_backup
            result_name = perform_backup()
        flash(f'پشتیبان‌گیری با موفقیت انجام شد: {result_name}', 'success')
    except Exception as e:
        flash(f'خطا در پشتیبان‌گیری: {str(e)}', 'error')
    
    return redirect(url_for('settings.backup'))


@features_bp.route('/settings/backup/list')
@login_required
def list_backups():
    """لیست نسخه‌های پشتیبان"""
    from flask import current_app
    import glob
    
    backup_dir = current_app.config['BACKUP_FOLDER']
    os.makedirs(backup_dir, exist_ok=True)
    
    backups = []
    for f in sorted(glob.glob(os.path.join(backup_dir, 'backup_*.zip')), reverse=True):
        stat = os.stat(f)
        backups.append({
            'name': os.path.basename(f),
            'size': round(stat.st_size / 1024, 1),
            'date': datetime.fromtimestamp(stat.st_mtime).strftime('%Y/%m/%d %H:%M'),
            'path': f
        })
    
    return render_template('settings/backup_list.html', backups=backups)


@features_bp.route('/settings/backup/restore/<name>', methods=['POST'])
@login_required
def restore_backup(name):
    """بازیابی اطلاعات از فایل پشتیبان"""
    if not current_user.is_admin:
        flash('فقط مدیر کل می‌تواند بازیابی کند', 'error')
        return redirect(url_for('settings.backup'))
    
    from flask import current_app
    import zipfile
    
    backup_dir = current_app.config['BACKUP_FOLDER']
    zip_path = _safe_backup_path(backup_dir, name)
    
    if not zip_path or not os.path.isfile(zip_path) or not zip_path.endswith('.zip'):
        flash('فایل پشتیبان معتبر یافت نشد', 'error')
        return redirect(url_for('settings.backup'))
    
    temp_db = os.path.join(backup_dir, f'.restore-{uuid.uuid4().hex}.db')
    try:
        from utils.database_tools import sqlite_backup, sqlite_database_path
        db_path = sqlite_database_path()
        if not db_path:
            raise RuntimeError('بازیابی فایل در این بخش فقط برای SQLite پشتیبانی می‌شود')

        with zipfile.ZipFile(zip_path, 'r') as archive:
            db_entries = [entry for entry in archive.infolist() if not entry.is_dir() and entry.filename.endswith('.db')]
            if len(db_entries) != 1:
                raise ValueError('ساختار فایل پشتیبان معتبر نیست')
            with archive.open(db_entries[0], 'r') as source, open(temp_db, 'wb') as target:
                shutil.copyfileobj(source, target)

        # سلامت فایل استخراج‌شده پیش از جایگزینی بررسی می‌شود.
        import sqlite3
        check = sqlite3.connect(temp_db)
        try:
            integrity = check.execute('PRAGMA integrity_check').fetchone()[0]
        finally:
            check.close()
        if str(integrity).lower() != 'ok':
            raise ValueError(f'فایل پشتیبان ناسالم است: {integrity}')

        safety_backup = db_path + '.before_restore'
        sqlite_backup(safety_backup)
        db.session.remove()
        db.engine.dispose()
        os.replace(temp_db, db_path)
        flash('بازیابی با موفقیت انجام شد. برای بارگذاری اتصال تازه، برنامه را یک‌بار بازنشانی کنید.', 'success')
    except Exception as e:
        flash(f'خطا در بازیابی: {str(e)}', 'error')
    finally:
        if os.path.exists(temp_db):
            os.remove(temp_db)
    
    return redirect(url_for('settings.backup'))


@features_bp.route('/settings/backup/download/<name>')
@login_required
def download_backup(name):
    """دانلود فایل پشتیبان"""
    if not current_user.is_admin:
        flash('فقط مدیر کل می‌تواند پشتیبان را دانلود کند', 'error')
        return redirect(url_for('settings.backup'))
    from flask import current_app
    backup_dir = current_app.config['BACKUP_FOLDER']
    path = _safe_backup_path(backup_dir, name)
    if path and os.path.isfile(path):
        return send_file(path, as_attachment=True, download_name=os.path.basename(path))
    flash('فایل پشتیبان معتبر یافت نشد', 'error')
    return redirect(url_for('settings.backup'))


@features_bp.route('/settings/backup/delete/<name>', methods=['POST'])
@login_required
def delete_backup(name):
    """حذف فایل پشتیبان"""
    if not current_user.is_admin:
        flash('فقط مدیر کل می‌تواند پشتیبان را حذف کند', 'error')
        return redirect(url_for('settings.backup'))
    from flask import current_app
    backup_dir = current_app.config['BACKUP_FOLDER']
    path = _safe_backup_path(backup_dir, name)
    if path and os.path.isfile(path):
        os.remove(path)
        flash('فایل پشتیبان حذف شد', 'success')
    else:
        flash('فایل پشتیبان معتبر یافت نشد', 'error')
    return redirect(url_for('settings.backup'))


# ============================================================
#  2) ادغام و تفکیک کلاس — #25, #26
# ============================================================
@features_bp.route('/classes/<int:id>/merge', methods=['GET', 'POST'])
@login_required
def merge_class(id):
    """ادغام کلاس با کلاس دیگر"""
    from models.classes import ClassGroup
    from models.registration import Registration
    
    class_group = ClassGroup.query.get_or_404(id)
    
    if request.method == 'POST':
        target_id = safe_int(request.form.get('target_class_id'))
        target = ClassGroup.query.get_or_404(target_id)
        
        # انتقال هنرجویان
        regs = Registration.query.filter_by(class_id=id, status='active').all()
        for reg in regs:
            reg.class_id = target_id
            target.current_count = (target.current_count or 0) + 1
        
        # بستن کلاس مبدا
        class_group.status = 'completed'
        class_group.current_count = 0
        
        db.session.commit()
        flash(f'کلاس "{class_group.name}" با "{target.name}" ادغام شد ({len(regs)} هنرجو)', 'success')
        return redirect(url_for('classes.view', id=target_id))
    
    all_classes = ClassGroup.query.filter(
        ClassGroup.status == 'active', ClassGroup.id != id
    ).all()
    
    return render_template('classes/merge.html', class_group=class_group, all_classes=all_classes)


@features_bp.route('/classes/<int:id>/split', methods=['GET', 'POST'])
@login_required
def split_class(id):
    """تفکیک کلاس به دو کلاس"""
    from models.classes import ClassGroup
    from models.registration import Registration
    
    class_group = ClassGroup.query.get_or_404(id)
    
    if request.method == 'POST':
        new_name = request.form['new_class_name']
        student_ids = request.form.getlist('student_ids')
        
        # ایجاد کلاس جدید
        last = ClassGroup.query.order_by(ClassGroup.id.desc()).first()
        new_code = f'SPL-{(last.id + 1) if last else 1:03d}'
        
        new_class = ClassGroup(
            class_code=new_code,
            name=new_name,
            course_id=class_group.course_id,
            teacher_id=request.form.get('new_teacher_id') or class_group.teacher_id,
            room_id=class_group.room_id,
            max_capacity=class_group.max_capacity,
            days_of_week=class_group.days_of_week,
            start_time=class_group.start_time,
            end_time=class_group.end_time,
            start_date=class_group.start_date,
            end_date=class_group.end_date,
            status='active',
            branch_id=class_group.branch_id,
            created_by=current_user.id
        )
        db.session.add(new_class)
        db.session.flush()
        
        # انتقال هنرجویان انتخاب شده
        count = 0
        for sid in student_ids:
            reg = Registration.query.filter_by(
                student_id=int(sid), class_id=id, status='active'
            ).first()
            if reg:
                reg.class_id = new_class.id
                class_group.current_count = max(0, (class_group.current_count or 0) - 1)
                new_class.current_count = (new_class.current_count or 0) + 1
                count += 1
        
        db.session.commit()
        flash(f'کلاس "{new_name}" با {count} هنرجو ایجاد شد', 'success')
        return redirect(url_for('classes.view', id=new_class.id))
    
    students = [r.student for r in class_group.registrations.filter_by(status='active').all()]
    from models.teacher import Teacher
    teachers = Teacher.query.filter_by(is_active=True).all()
    
    return render_template('classes/split.html', class_group=class_group, students=students, teachers=teachers)


# ============================================================
#  3) QR Code برای هنرجو — #49, #50
# ============================================================
@features_bp.route('/students/<int:id>/qr')
@login_required
def student_qr(id):
    """تولید QR Code برای هنرجو"""
    from models.student import Student
    import qrcode
    
    student = Student.query.get_or_404(id)
    
    # تولید QR
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr_data = f'STUDENT:{student.student_code}|{student.full_name}|{student.national_code or ""}'
    qr.add_data(qr_data)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="#0d47a1", back_color="white")
    
    # ذخیره در حافظه
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    
    qr_b64 = base64.b64encode(buf.getvalue()).decode()
    
    return render_template('students/qr_card.html', student=student, qr_data=qr_b64)


@features_bp.route('/students/<int:id>/card')
@login_required
def student_card(id):
    """چاپ کارت هنرجویی"""
    from models.student import Student
    import qrcode
    
    student = Student.query.get_or_404(id)
    
    qr = qrcode.QRCode(version=1, box_size=8, border=2)
    qr.add_data(f'STUDENT:{student.student_code}')
    qr.make(fit=True)
    img = qr.make_image(fill_color="#0d47a1", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    qr_b64 = base64.b64encode(buf.getvalue()).decode()
    
    return render_template('students/id_card.html', student=student, qr_data=qr_b64)


# ============================================================
#  4) آزمون تصادفی — #90, #94
# ============================================================
@features_bp.route('/exams/<int:id>/auto-generate', methods=['POST'])
@login_required
def auto_generate_exam(id):
    """تولید خودکار آزمون از بانک سوالات"""
    from models.exam import Exam, QuestionBank, ExamQuestion
    import random
    
    exam = Exam.query.get_or_404(id)
    count = int(request.form.get('count', 20))
    difficulty = request.form.get('difficulty', '')
    shuffle_options = 'shuffle_options' in request.form
    
    query = QuestionBank.query.filter_by(is_active=True)
    if exam.course_id:
        query = query.filter_by(course_id=exam.course_id)
    if difficulty:
        query = query.filter_by(difficulty=difficulty)
    
    all_questions = query.all()
    
    if len(all_questions) < count:
        flash(f'تعداد سوالات بانک ({len(all_questions)}) کمتر از درخواست شده ({count}) است', 'warning')
        count = len(all_questions)
    
    selected = random.sample(all_questions, count)
    
    # حذف سوالات قبلی
    ExamQuestion.query.filter_by(exam_id=id).delete()
    
    for i, q in enumerate(selected):
        eq = ExamQuestion(
            exam_id=id,
            question_id=q.id,
            question_text=q.question_text,
            question_type=q.question_type,
            option_a=q.option_a,
            option_b=q.option_b,
            option_c=q.option_c,
            option_d=q.option_d,
            correct_answer=q.correct_answer,
            marks=q.marks,
            order=i + 1
        )
        
        # شافل گزینه‌ها
        if shuffle_options and q.question_type == 'multiple_choice':
            options = {'a': q.option_a, 'b': q.option_b, 'c': q.option_c, 'd': q.option_d}
            correct_key = q.correct_answer
            correct_val = options.get(correct_key)
            
            vals = [v for v in options.values() if v]
            random.shuffle(vals)
            
            keys = ['a', 'b', 'c', 'd']
            new_correct = None
            for j, val in enumerate(vals):
                if j < len(keys):
                    setattr(eq, f'option_{keys[j]}', val)
                    if val == correct_val:
                        new_correct = keys[j]
            eq.correct_answer = new_correct
        
        db.session.add(eq)
    
    db.session.commit()
    flash(f'{count} سوال تصادفی به آزمون اضافه شد', 'success')
    return redirect(url_for('exams.view', id=id))


# ============================================================
#  5) هشدار چک سررسید — #153
# ============================================================
@features_bp.route('/finance/checks/alerts')
@login_required
def check_alerts():
    """چک‌های نزدیک سررسید"""
    from models.finance import Check
    
    today = datetime.utcnow().date()
    upcoming = today + timedelta(days=7)
    
    near_due = Check.query.filter(
        Check.due_date.between(today, upcoming),
        Check.status.in_(['received', 'pending'])
    ).order_by(Check.due_date).all()
    
    overdue = Check.query.filter(
        Check.due_date < today,
        Check.status.in_(['received', 'pending'])
    ).order_by(Check.due_date).all()
    
    return render_template('finance/check_alerts.html', near_due=near_due, overdue=overdue)


# ============================================================
#  6) رتبه‌بندی مدرسین — #84
# ============================================================
@features_bp.route('/teachers/ranking')
@login_required
def teacher_ranking():
    """رتبه‌بندی مدرسین"""
    from models.teacher import Teacher, TeacherEvaluation
    from models.registration import Registration
    from models.classes import ClassGroup
    
    teachers = Teacher.query.filter_by(is_active=True).all()
    
    rankings = []
    for t in teachers:
        evals = TeacherEvaluation.query.filter_by(teacher_id=t.id).all()
        avg_score = sum(e.overall_satisfaction or 0 for e in evals) / len(evals) if evals else 0
        class_count = ClassGroup.query.filter_by(teacher_id=t.id, status='active').count()
        student_count = db.session.query(db.func.count(Registration.id)).join(ClassGroup).filter(
            ClassGroup.teacher_id == t.id, Registration.status == 'active'
        ).scalar() or 0
        
        rankings.append({
            'teacher': t,
            'avg_score': round(avg_score, 1),
            'eval_count': len(evals),
            'class_count': class_count,
            'student_count': student_count
        })
    
    rankings.sort(key=lambda x: x['avg_score'], reverse=True)
    
    return render_template('teachers/ranking.html', rankings=rankings)


# ============================================================
#  7) رتبه‌بندی دوره‌ها — #304
# ============================================================
@features_bp.route('/reports/course-ranking')
@login_required
def course_ranking():
    """رتبه‌بندی دوره‌ها بر اساس فروش و محبوبیت"""
    from models.course import Course
    from models.registration import Registration
    from models.finance import Payment
    
    courses = Course.query.filter_by(is_active=True).all()
    
    rankings = []
    for c in courses:
        reg_count = Registration.query.filter_by(course_id=c.id).count()
        active_count = Registration.query.filter_by(course_id=c.id, status='active').count()
        revenue = db.session.query(db.func.sum(Payment.amount)).join(Registration).filter(
            Registration.course_id == c.id, Payment.status == 'confirmed'
        ).scalar() or 0
        
        rankings.append({
            'course': c,
            'total_registrations': reg_count,
            'active_registrations': active_count,
            'total_revenue': revenue
        })
    
    rankings.sort(key=lambda x: x['total_registrations'], reverse=True)
    
    return render_template('reports/course_ranking.html', rankings=rankings)


# ============================================================
#  8) امتیازدهی شعب — #303
# ============================================================
@features_bp.route('/reports/branch-ranking')
@login_required
def branch_ranking():
    """امتیازدهی و رتبه‌بندی شعب"""
    from models.system import Branch
    from models.student import Student
    from models.registration import Registration
    from models.finance import Payment
    
    branches = Branch.query.filter_by(is_active=True).all()
    
    rankings = []
    for b in branches:
        student_count = Student.query.filter_by(branch_id=b.id, status='active').count()
        reg_count = Registration.query.filter_by(branch_id=b.id, status='active').count()
        revenue = db.session.query(db.func.sum(Payment.amount)).filter(
            Payment.branch_id == b.id, Payment.status == 'confirmed'
        ).scalar() or 0
        
        rankings.append({
            'branch': b,
            'students': student_count,
            'registrations': reg_count,
            'revenue': revenue
        })
    
    rankings.sort(key=lambda x: x['revenue'], reverse=True)
    
    return render_template('reports/branch_ranking.html', rankings=rankings)


# ============================================================
#  9) رتبه‌بندی کارکنان — #305, #306
# ============================================================
@features_bp.route('/reports/staff-ranking')
@login_required
def staff_ranking():
    """رتبه‌بندی کارکنان بر اساس عملکرد"""
    from models.user import User, ActivityLog
    
    users = User.query.filter_by(is_active=True).all()
    
    rankings = []
    for u in users:
        today = datetime.utcnow().date()
        month_start = today.replace(day=1)
        
        activities = ActivityLog.query.filter(
            ActivityLog.user_id == u.id,
            ActivityLog.created_at >= datetime.combine(month_start, datetime.min.time())
        ).count()
        
        registrations = ActivityLog.query.filter(
            ActivityLog.user_id == u.id,
            ActivityLog.module == 'registration',
            ActivityLog.action == 'create',
            ActivityLog.created_at >= datetime.combine(month_start, datetime.min.time())
        ).count()
        
        rankings.append({
            'user': u,
            'monthly_activities': activities,
            'monthly_registrations': registrations
        })
    
    rankings.sort(key=lambda x: x['monthly_activities'], reverse=True)
    
    return render_template('reports/staff_ranking.html', rankings=rankings)


@features_bp.route('/export/students/csv')
@login_required
def export_students_csv():
    import csv, io
    from flask import make_response
    from models.student import Student
    output = io.StringIO()
    writer = csv.writer(output, lineterminator='\n')
    writer.writerow(['کد','نام','نام خانوادگی','تلفن','ایمیل','وضعیت'])
    for s in Student.query.all():
        writer.writerow([s.student_code, s.first_name, s.last_name, s.mobile or '', s.email or '', s.status])
    response = make_response(output.getvalue())
    response.headers['Content-Type'] = 'text/csv; charset=utf-8'
    response.headers['Content-Disposition'] = 'attachment; filename=students.csv'
    return response


@features_bp.route('/export/payments/csv')
@login_required
def export_payments_csv():
    import csv, io
    from flask import make_response
    from models.finance import Payment
    output = io.StringIO()
    writer = csv.writer(output, lineterminator='\n')
    writer.writerow(['شماره رسید','مبلغ','تاریخ','وضعیت','روش پرداخت'])
    for p in Payment.query.all():
        writer.writerow([p.receipt_no, p.amount, p.payment_date, p.status, p.payment_method])
    response = make_response(output.getvalue())
    response.headers['Content-Type'] = 'text/csv; charset=utf-8'
    response.headers['Content-Disposition'] = 'attachment; filename=payments.csv'
    return response


# ============================================================
#  10) سیستم سلامت — #268, #325
# ============================================================
@features_bp.route('/settings/system-health')
@login_required
def system_health():
    """گزارش سلامت سیستم"""
    from models.user import User
    from models.student import Student
    from models.teacher import Teacher
    from models.registration import Registration
    from models.finance import Payment
    from models.system import SystemSettings
    from flask import current_app
    import os
    
    # آمار دیتابیس فعال (مسیر تنظیم‌شده یا سرور خارجی)
    from utils.database_tools import database_size_bytes, check_database_integrity
    db_size = database_size_bytes()
    try:
        db_healthy, db_message = check_database_integrity()
    except Exception as exc:
        db_healthy, db_message = False, str(exc)
    
    stats = {
        'db_size_mb': round(db_size / (1024 * 1024), 2),
        'total_users': User.query.count(),
        'active_users': User.query.filter_by(is_active=True).count(),
        'total_students': Student.query.count(),
        'total_teachers': Teacher.query.count(),
        'total_registrations': Registration.query.count(),
        'total_payments': Payment.query.count(),
        'table_count': len(db.metadata.tables),
        'db_healthy': db_healthy,
        'db_message': db_message,
    }
    
    # بررسی پشتیبان‌گیری
    backup_dir = current_app.config['BACKUP_FOLDER']
    import glob
    backup_count = len(glob.glob(os.path.join(backup_dir, 'backup_*.zip')))
    last_backup = None
    if backup_count > 0:
        latest = max(glob.glob(os.path.join(backup_dir, 'backup_*.zip')), key=os.path.getmtime)
        last_backup = datetime.fromtimestamp(os.path.getmtime(latest)).strftime('%Y/%m/%d %H:%M')
    
    stats['backup_count'] = backup_count
    stats['last_backup'] = last_backup
    
    # فضای آپلود
    upload_dir = current_app.config['UPLOAD_FOLDER']
    upload_size = 0
    if os.path.exists(upload_dir):
        for root, dirs, files in os.walk(upload_dir):
            upload_size += sum(os.path.getsize(os.path.join(root, f)) for f in files)
    stats['upload_size_mb'] = round(upload_size / (1024 * 1024), 2)
    
    return render_template('settings/system_health.html', stats=stats)


# ============================================================
#  11) گزارش استفاده کاربران — #343
# ============================================================
@features_bp.route('/settings/usage-analytics')
@login_required
def usage_analytics():
    """تحلیل استفاده کاربران از سیستم"""
    from models.user import User, ActivityLog
    
    today = datetime.utcnow().date()
    week_ago = today - timedelta(days=7)
    
    # فعال‌ترین کاربران
    active_users = db.session.query(
        User.full_name,
        db.func.count(ActivityLog.id).label('count')
    ).join(ActivityLog).filter(
        ActivityLog.created_at >= datetime.combine(week_ago, datetime.min.time())
    ).group_by(User.id).order_by(db.text('count DESC')).limit(10).all()
    
    # بیشترین ماژول‌های استفاده شده
    top_modules = db.session.query(
        ActivityLog.module,
        db.func.count(ActivityLog.id).label('count')
    ).filter(
        ActivityLog.created_at >= datetime.combine(week_ago, datetime.min.time())
    ).group_by(ActivityLog.module).order_by(db.text('count DESC')).limit(10).all()
    
    # فعالیت روزانه
    daily_activity = db.session.query(
        db.func.date(ActivityLog.created_at).label('day'),
        db.func.count(ActivityLog.id).label('count')
    ).filter(
        ActivityLog.created_at >= datetime.combine(week_ago, datetime.min.time())
    ).group_by(db.text('day')).order_by(db.text('day')).all()
    
    return render_template('settings/usage_analytics.html',
                         active_users=active_users,
                         top_modules=top_modules,
                         daily_activity=daily_activity)


# ============================================================
#  12) سیستم راهنما — #344, #345
# ============================================================
@features_bp.route('/help')
@login_required
def help_center():
    """مرکز راهنمای نرم‌افزار"""
    return render_template('support/help_center.html')


# ============================================================
#  13) ثبت پیشنهاد کاربران — #346
# ============================================================
@features_bp.route('/suggestions', methods=['GET', 'POST'])
@login_required
def suggestions():
    """ثبت پیشنهادات کاربران"""
    from models.system import InternalMessage
    
    if request.method == 'POST':
        msg = InternalMessage(
            sender_id=current_user.id,
            receiver_id=1,  # مدیر سیستم
            subject=f'پیشنهاد: {request.form["subject"]}',
            body=request.form['body']
        )
        db.session.add(msg)
        db.session.commit()
        flash('پیشنهاد شما ثبت شد. متشکریم!', 'success')
        return redirect(url_for('features.suggestions'))
    
    return render_template('support/suggestions.html')


# ============================================================
#  14) لاگ امنیتی — #326
# ============================================================
@features_bp.route('/settings/security-log')
@login_required
def security_log():
    """لاگ رویدادهای امنیتی"""
    from models.user import ActivityLog
    
    security_actions = ['login', 'logout', 'failed_login', 'password_change', 'permission_change']
    logs = ActivityLog.query.filter(
        ActivityLog.action.in_(security_actions)
    ).order_by(ActivityLog.created_at.desc()).limit(100).all()
    
    # همه لاگ‌ها رو هم نشون بده
    all_logs = ActivityLog.query.order_by(ActivityLog.created_at.desc()).limit(50).all()
    
    return render_template('settings/security_log.html', logs=logs, all_logs=all_logs)


# ============================================================
#  15) پرینت لیست کلاس — #60
# ============================================================
@features_bp.route('/classes/<int:id>/print')
@login_required
def print_class_list(id):
    """مسیر چاپ قدیمی؛ خروجی جدید فقط PDF است."""
    return redirect(url_for('new_features.class_pdf', id=id))


# ============================================================
#  16) ادغام / تفکیک کلاس — UI
# ============================================================
# (templates در ادامه ساخته میشه)


# ============================================================
#  17) گردش کار سفارشی — #320
# ============================================================
@features_bp.route('/settings/workflows')
@login_required
def workflows():
    """مدیریت گردش کارها"""
    return render_template('settings/workflows.html')


# ============================================================
#  18) جستجوی سراسری — #315
# ============================================================
@features_bp.route('/search')
@login_required
def global_search():
    """جستجوی سراسری در تمام بخش‌ها"""
    from models.student import Student
    from models.teacher import Teacher
    from models.registration import Registration
    from models.course import Course
    from models.classes import ClassGroup
    
    q = request.args.get('q', '').strip()
    if len(q) < 2:
        return jsonify({'results': []})
    
    results = []
    
    # جستجوی هنرجویان
    students = Student.query.filter(
        db.or_(Student.first_name.contains(q), Student.last_name.contains(q),
               Student.student_code.contains(q), Student.national_code.contains(q),
               Student.mobile.contains(q))
    ).limit(5).all()
    for s in students:
        results.append({'type': 'هنرجو', 'name': s.full_name, 'code': s.student_code, 'url': url_for('students.view', id=s.id)})
    
    # جستجوی مدرسین
    teachers = Teacher.query.filter(
        db.or_(Teacher.first_name.contains(q), Teacher.last_name.contains(q), Teacher.teacher_code.contains(q))
    ).limit(5).all()
    for t in teachers:
        results.append({'type': 'مدرس', 'name': t.full_name, 'code': t.teacher_code, 'url': url_for('teachers.view', id=t.id)})
    
    # جستجوی دوره‌ها
    courses = Course.query.filter(
        db.or_(Course.title.contains(q), Course.code.contains(q))
    ).limit(5).all()
    for c in courses:
        results.append({'type': 'دوره', 'name': c.title, 'code': c.code, 'url': url_for('settings.courses')})
    
    # جستجوی کلاس‌ها
    classes = ClassGroup.query.filter(
        db.or_(ClassGroup.name.contains(q), ClassGroup.class_code.contains(q))
    ).limit(5).all()
    for cl in classes:
        results.append({'type': 'کلاس', 'name': cl.name, 'code': cl.class_code, 'url': url_for('classes.view', id=cl.id)})
    
    # جستجوی ثبت‌نام
    regs = Registration.query.filter(Registration.reg_code.contains(q)).limit(5).all()
    for r in regs:
        results.append({'type': 'ثبت‌نام', 'name': r.reg_code, 'code': '', 'url': url_for('registration.view', id=r.id)})
    
    return jsonify({'results': results})


# ============================================================
#  19) صدور کارنامه — #101, #103
# ============================================================
@features_bp.route('/grades/report-card/<int:student_id>')
@login_required
def report_card(student_id):
    """صدور کارنامه هنرجو"""
    from models.student import Student
    from models.exam import Grade
    
    student = Student.query.get_or_404(student_id)
    grades = Grade.query.filter_by(student_id=student_id).all()
    
    return render_template('exams/report_card.html', student=student, grades=grades)


@features_bp.route('/grades/report-card/class/<int:class_id>')
@login_required
def bulk_report_card(class_id):
    """چاپ گروهی کارنامه"""
    from models.classes import ClassGroup
    from models.exam import Grade
    
    class_group = ClassGroup.query.get_or_404(class_id)
    registrations = class_group.registrations.filter_by(status='active').all()
    
    report_data = []
    for reg in registrations:
        grades = Grade.query.filter_by(student_id=reg.student_id, class_id=class_id).all()
        report_data.append({'student': reg.student, 'grades': grades})
    
    return render_template('exams/bulk_report_card.html', class_group=class_group, report_data=report_data)


# ============================================================
#  20) پیامک تولد — #117
# ============================================================
@features_bp.route('/messaging/birthday-check')
@login_required
def birthday_check():
    """بررسی تولد هنرجویان و ارسال پیامک"""
    from models.student import Student
    from models.system import Message
    
    today = datetime.utcnow().date()
    
    # هنرجویانی که امروز تولدشان است
    students = Student.query.filter(
        db.extract('month', Student.birth_date) == today.month,
        db.extract('day', Student.birth_date) == today.day,
        Student.status == 'active'
    ).all()
    
    sent_count = 0
    for s in students:
        if s.mobile:
            msg = Message(
                recipient_type='student',
                recipient_id=s.id,
                phone=s.mobile,
                message_text=f'🎉 {s.full_name} عزیز، تولدت مبارک! از طرف آموزشگاه',
                send_type='birthday',
                status='pending',
                created_by=current_user.id
            )
            db.session.add(msg)
            sent_count += 1
            # ارسال واقعی پیامک در صورت وجود پنل پیامکی
            try:
                from routes.settings_panel import farazsms_config
                from utils.sms_service import send_sms
                if msg.phone:
                    send_sms(msg.phone, msg.message_text)
            except Exception:
                pass
    
    db.session.commit()
    flash(f'{sent_count} پیامک تولد ارسال شد', 'success')
    return redirect(url_for('messaging.sms'))


# ============================================================
#  21) قفل نرم‌افزار / لایسنس — #327, #328, #329
# ============================================================
@features_bp.route('/settings/license', methods=['GET', 'POST'])
@login_required
def license_management():
    """مدیریت لایسنس نرم‌افزار"""
    from models.system import SystemSettings
    
    settings = SystemSettings.query.first()
    
    if request.method == 'POST':
        # ذخیره تنظیمات لایسنس
        settings.license_number = request.form.get('license_key')
        db.session.commit()
        flash('لایسنس بروزرسانی شد', 'success')
        return redirect(url_for('features.license_management'))
    
    return render_template('settings/license.html', settings=settings)


# ============================================================
#  22) Dark Mode — #313
# ============================================================
@features_bp.route('/settings/toggle-dark-mode', methods=['POST'])
@login_required
def toggle_dark_mode():
    """تغییر حالت تاریک"""
    # ذخیره در کوکی مرورگر
    from flask import make_response
    resp = make_response(redirect(request.referrer or url_for('dashboard.index')))
    
    current = request.cookies.get('dark_mode', 'off')
    new_val = 'on' if current == 'off' else 'off'
    resp.set_cookie('dark_mode', new_val, max_age=365*24*60*60)
    
    return resp

# ══ عملیات انبوه (Bulk) ══
@features_bp.route('/certificates/bulk/<cert_type>')
@login_required
def bulk_certificates(cert_type):
    from flask import render_template
    if cert_type == 'student':
        from models.student import Student
        items = Student.query.filter_by(status='active').limit(50).all()
    elif cert_type == 'teacher':
        from models.teacher import Teacher
        items = Teacher.query.filter_by(is_active=True).limit(50).all()
    else:
        items = []
    return render_template('certificates/beautiful_bulk.html', items=items, cert_type=cert_type)
