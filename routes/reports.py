"""Reports routes"""
from flask import Blueprint, render_template, request
from flask_login import login_required
from license_client import license_required, licensed_section
from extensions import db
from models.student import Student
from models.teacher import Teacher
from models.classes import ClassGroup
from models.registration import Registration, Installment
from models.finance import Payment, Expense, Cashbox, ExpenseCategory
from models.course import Course
from datetime import datetime, timedelta

reports_bp = Blueprint('reports', __name__)


@reports_bp.route('/')
@license_required
@login_required
@licensed_section('reports')
def index():
    return render_template('reports/index.html')


@reports_bp.route('/students')
@login_required
def student_report():
    status = request.args.get('status', '')
    category = request.args.get('category', '')
    
    query = Student.query
    if status:
        query = query.filter_by(status=status)
    if category:
        query = query.filter_by(category=category)
    
    students = query.all()
    
    stats = {
        'total': len(students),
        'active': sum(1 for s in students if s.status == 'active'),
        'graduated': sum(1 for s in students if s.status == 'graduated'),
        'withdrawn': sum(1 for s in students if s.status == 'withdrawn'),
    }
    
    return render_template('reports/students.html', students=students, stats=stats, status=status, category=category)


@reports_bp.route('/financial')
@login_required
def financial_report():
    # دوازده ماه اخیر — با تقویم شمسیِ خودِ سیستم.
    # پیش‌تر `today - timedelta(days=30*i)` بود: هم ماه‌ها جابه‌جا می‌شدند
    # (۳۰×۱۲ ≠ ۳۶۵)، هم برش‌ها میلادی بود و هم برچسب نمودار `2026-09` — یعنی
    # کاربر ۱۲ سبد می‌دید که به ماه‌های خودش نمی‌خورد.
    from utils.jalali import jalali_months_back
    monthly_data = []
    for period, month_start, month_end in jalali_months_back(12):
        income = db.session.query(db.func.sum(Payment.amount)).filter(
            Payment.payment_date >= month_start,
            Payment.payment_date <= month_end,
            Payment.status == 'confirmed'
        ).scalar() or 0
        
        expense = db.session.query(db.func.sum(Expense.amount)).filter(
            Expense.expense_date >= month_start,
            Expense.expense_date <= month_end,
            Expense.status == 'confirmed'
        ).scalar() or 0
        
        monthly_data.append({
            'month': period,
            'income': income,
            'expense': expense,
            'profit': income - expense
        })
    
    # Top courses by registration
    courses = db.session.query(
        Course.title, db.func.count(Registration.id)
    ).join(Registration).group_by(Course.title).order_by(
        db.func.count(Registration.id).desc()
    ).limit(10).all()
    
    # Debtors
    debtors = Registration.query.filter(
        Registration.remaining_amount > 0,
        Registration.status == 'active'
    ).order_by(Registration.remaining_amount.desc()).limit(20).all()
    
    return render_template('reports/financial.html', 
                         monthly_data=monthly_data, 
                         courses=courses,
                         debtors=debtors)


@reports_bp.route('/attendance')
@login_required
def attendance_report():
    from models.attendance import Attendance
    
    # Attendance rate per class
    classes = ClassGroup.query.filter_by(status='active').all()
    class_stats = []
    for cls in classes:
        from models.attendance import Attendance
        from models.classes import ClassSession
        
        total_att = Attendance.query.join(ClassSession).filter(
            ClassSession.class_id == cls.id
        ).count()
        present_att = Attendance.query.join(ClassSession).filter(
            ClassSession.class_id == cls.id,
            Attendance.status == 'present'
        ).count()
        
        rate = (present_att / total_att * 100) if total_att > 0 else 0
        class_stats.append({
            'class': cls,
            'total': total_att,
            'present': present_att,
            'rate': round(rate, 1)
        })
    
    return render_template('reports/attendance.html', class_stats=class_stats)


@reports_bp.route('/teachers')
@login_required
def teacher_report():
    teachers = Teacher.query.filter_by(is_active=True).all()
    
    teacher_stats = []
    for t in teachers:
        classes = ClassGroup.query.filter_by(teacher_id=t.id, status='active').count()
        students = db.session.query(db.func.count(Registration.id)).join(ClassGroup).filter(
            ClassGroup.teacher_id == t.id,
            Registration.status == 'active'
        ).scalar() or 0
        
        teacher_stats.append({
            'teacher': t,
            'classes': classes,
            'students': students
        })
    
    return render_template('reports/teachers.html', teacher_stats=teacher_stats)


@reports_bp.route('/enrollment')
@login_required
def enrollment_report():
    today = datetime.utcnow()
    
    # Enrollment by month
    monthly = []
    for i in range(5, -1, -1):
        d = today - timedelta(days=30*i)
        count = Registration.query.filter(
            db.extract('year', Registration.created_at) == d.year,
            db.extract('month', Registration.created_at) == d.month
        ).count()
        monthly.append({'month': d.strftime('%Y-%m'), 'count': count})
    
    # By field
    by_field = db.session.query(
        db.func.count(Registration.id), Course.title
    ).join(Course).group_by(Course.title).order_by(
        db.func.count(Registration.id).desc()
    ).limit(10).all()
    
    # By referral source
    by_referral = db.session.query(
        Student.referral_source, db.func.count(Student.id)
    ).group_by(Student.referral_source).all()
    
    return render_template('reports/enrollment.html', 
                         monthly=monthly, by_field=by_field, by_referral=by_referral)


@reports_bp.route('/installments')
@login_required
def installment_report():
    today = datetime.utcnow()
    
    overdue = Installment.query.filter(
        Installment.due_date < today.date(),
        Installment.status.in_(['pending', 'partial'])
    ).order_by(Installment.due_date).all()
    
    upcoming = Installment.query.filter(
        Installment.due_date >= today.date(),
        Installment.due_date <= (today + timedelta(days=30)).date(),
        Installment.status == 'pending'
    ).order_by(Installment.due_date).all()
    
    return render_template('reports/installments.html', overdue=overdue, upcoming=upcoming)


@reports_bp.route('/profit-loss')
@login_required
def profit_loss():
    today = datetime.utcnow()
    year_start = today.replace(month=1, day=1)
    
    total_income = db.session.query(db.func.sum(Payment.amount)).filter(
        Payment.payment_date >= year_start.date(),
        Payment.status == 'confirmed'
    ).scalar() or 0
    
    total_expenses = db.session.query(db.func.sum(Expense.amount)).filter(
        Expense.expense_date >= year_start.date(),
        Expense.status == 'confirmed'
    ).scalar() or 0
    
    # Expense breakdown
    expense_breakdown = db.session.query(
        db.func.sum(Expense.amount), ExpenseCategory.name
    ).join(ExpenseCategory).filter(
        Expense.expense_date >= year_start.date()
    ).group_by(ExpenseCategory.name).all()
    
    return render_template('reports/profit_loss.html',
                         total_income=total_income,
                         total_expenses=total_expenses,
                         profit=total_income - total_expenses,
                         expense_breakdown=expense_breakdown)
