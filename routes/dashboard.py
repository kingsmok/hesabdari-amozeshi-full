"""Dashboard routes — role-specific dashboards"""
from datetime import datetime, timedelta, date
from flask import Blueprint, render_template, redirect, url_for
from flask_login import login_required, current_user
from extensions import db

dashboard_bp = Blueprint('dashboard', __name__)


@dashboard_bp.route('/')
@login_required
def index():
    """داشبورد بر اساس نقش کاربر"""
    if current_user.is_admin:
        return admin_dashboard()
    
    role_name = current_user.role.name if current_user.role else ''
    
    if 'مدرس' in role_name:
        return teacher_dashboard()
    elif 'منشی' in role_name or 'ثبت‌نام' in role_name:
        return secretary_dashboard()
    elif 'حسابدار' in role_name:
        return accountant_dashboard()
    elif 'آموزش' in role_name:
        return education_dashboard()
    else:
        return admin_dashboard()


def admin_dashboard():
    """داشبورد مدیر کل"""
    from models.student import Student
    from models.teacher import Teacher
    from models.classes import ClassGroup
    from models.registration import Registration
    from models.finance import Payment, Expense, Cashbox
    from models.user import ActivityLog
    
    today = datetime.utcnow()
    month_start = today.replace(day=1)
    
    stats = {
        'total_students': Student.query.filter_by(status='active').count(),
        'total_teachers': Teacher.query.filter_by(is_active=True).count(),
        'active_classes': ClassGroup.query.filter_by(status='active').count(),
        'total_registrations': Registration.query.filter_by(status='active').count(),
    }
    
    month_income = db.session.query(db.func.sum(Payment.amount)).filter(
        Payment.payment_date >= month_start.date(), Payment.status == 'confirmed'
    ).scalar() or 0
    
    month_expenses = db.session.query(db.func.sum(Expense.amount)).filter(
        Expense.expense_date >= month_start.date(), Expense.status == 'confirmed'
    ).scalar() or 0
    
    cashbox = Cashbox.query.first()
    stats['month_income'] = month_income
    stats['month_expenses'] = month_expenses
    stats['month_profit'] = month_income - month_expenses
    stats['cashbox_balance'] = cashbox.balance if cashbox else 0
    
    recent_regs = Registration.query.order_by(Registration.created_at.desc()).limit(10).all()
    recent_activities = ActivityLog.query.order_by(ActivityLog.created_at.desc()).limit(15).all()
    
    today_weekday = (today.weekday() + 2) % 7
    today_classes = ClassGroup.query.filter(
        ClassGroup.status == 'active',
        ClassGroup.days_of_week.contains(str(today_weekday))
    ).all()
    
    from models.registration import Installment
    overdue_count = Installment.query.filter(
        Installment.due_date < today.date(),
        Installment.status.in_(['pending', 'partial'])
    ).count()
    
    return render_template('dashboard/admin.html',
                         stats=stats, recent_regs=recent_regs,
                         recent_activities=recent_activities,
                         today_classes=today_classes, overdue_count=overdue_count)


def teacher_dashboard():
    """داشبورد مدرس"""
    from models.teacher import Teacher
    from models.classes import ClassGroup
    from models.attendance import TeacherAttendance
    
    # پیدا کردن مدرس مرتبط با کاربر
    teacher = Teacher.query.filter_by(user_id=current_user.id, is_active=True).first()
    if teacher is None:
        teacher = Teacher.query.filter_by(user_id=current_user.id).first()
    
    today = datetime.utcnow()
    today_weekday = (today.weekday() + 2) % 7
    
    my_classes = []
    if teacher:
        my_classes = ClassGroup.query.filter_by(teacher_id=teacher.id, status='active').all()
    
    today_classes = [c for c in my_classes if c.days_of_week and str(today_weekday) in c.days_of_week]
    
    total_students = sum(c.current_count or 0 for c in my_classes)
    total_sessions = sum(c.completed_sessions_count for c in my_classes)
    
    return render_template('dashboard/teacher.html',
                         teacher=teacher, my_classes=my_classes,
                         today_classes=today_classes,
                         total_students=total_students,
                         total_sessions=total_sessions)


def secretary_dashboard():
    """داشبورد منشی"""
    from models.student import Student
    from models.registration import Registration
    from models.classes import ClassGroup
    
    today = datetime.utcnow()
    month_start = today.replace(day=1)
    
    today_regs = Registration.query.filter(
        db.func.date(Registration.created_at) == today.date()
    ).count()
    
    month_regs = Registration.query.filter(
        Registration.created_at >= month_start
    ).count()
    
    active_students = Student.query.filter_by(status='active').count()
    active_classes = ClassGroup.query.filter_by(status='active').count()
    
    recent_regs = Registration.query.order_by(Registration.created_at.desc()).limit(10).all()
    
    return render_template('dashboard/secretary.html',
                         today_regs=today_regs, month_regs=month_regs,
                         active_students=active_students, active_classes=active_classes,
                         recent_regs=recent_regs)


def accountant_dashboard():
    """داشبورد حسابدار"""
    from models.finance import Payment, Expense, Cashbox
    
    today = datetime.utcnow()
    month_start = today.replace(day=1)
    
    month_income = db.session.query(db.func.sum(Payment.amount)).filter(
        Payment.payment_date >= month_start.date(), Payment.status == 'confirmed'
    ).scalar() or 0
    
    month_expenses = db.session.query(db.func.sum(Expense.amount)).filter(
        Expense.expense_date >= month_start.date(), Expense.status == 'confirmed'
    ).scalar() or 0
    
    cashbox = Cashbox.query.first()
    
    recent_payments = Payment.query.order_by(Payment.created_at.desc()).limit(10).all()
    
    from models.registration import Registration
    debtors = Registration.query.filter(
        Registration.remaining_amount > 0, Registration.status == 'active'
    ).order_by(Registration.remaining_amount.desc()).limit(10).all()
    
    return render_template('dashboard/accountant.html',
                         month_income=month_income, month_expenses=month_expenses,
                         month_profit=month_income - month_expenses,
                         cashbox=cashbox, recent_payments=recent_payments,
                         debtors=debtors)


def education_dashboard():
    """داشبورد مسئول آموزش"""
    from models.classes import ClassGroup
    from models.teacher import Teacher
    from models.course import Course
    from models.exam import Exam
    
    active_classes = ClassGroup.query.filter_by(status='active').count()
    active_teachers = Teacher.query.filter_by(is_active=True).count()
    active_courses = Course.query.filter_by(is_active=True).count()
    
    today_classes = ClassGroup.query.filter_by(status='active').all()
    
    return render_template('dashboard/education.html',
                         active_classes=active_classes,
                         active_teachers=active_teachers,
                         active_courses=active_courses,
                         today_classes=today_classes)
