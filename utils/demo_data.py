"""
سیستم داده نمونه — تست کامل تمام اتصالات
"""
from datetime import datetime, timedelta
from extensions import db
from utils.jalali import jalali_to_gregorian


def jdate(year, month, day):
    """تاریخ شمسی داده نمونه را به تاریخ میلادی قابل ذخیره تبدیل می‌کند."""
    return jalali_to_gregorian(year, month, day)


def create_demo_data():
    """ایجاد داده‌های نمونه برای تست کامل سیستم"""
    from models.student import Student
    from models.teacher import Teacher
    from models.course import Course, Field, Syllabus, Room
    from models.classes import ClassGroup, ClassSession
    from models.registration import Registration, Installment
    from models.finance import Payment, Cashbox, CashboxTransaction, ExpenseCategory
    from models.attendance import Attendance, TeacherAttendance
    from models.exam import Exam, ExamResult, Grade, QuestionBank
    from models.system import Branch, AcademicYear, MessageTemplate
    from models.user import Role
    
    if Student.query.count() > 0:
        return 'داده‌های نمونه قبلاً ایجاد شده‌اند'
    
    results = []
    
    # ═══ ۱) شعبه ═══
    branch = Branch.query.first()
    
    # ═══ ۲) رشته‌ها ═══
    f_computer = Field(name='کامپیوتر', code='CS', description='دوره‌های کامپیوتر و برنامه‌نویسی')
    f_accounting = Field(name='حسابداری', code='ACC', description='دوره‌های حسابداری')
    f_english = Field(name='زبان انگلیسی', code='ENG', description='دوره‌های زبان')
    f_graphic = Field(name='گرافیک', code='GRF', description='دوره‌های طراحی و گرافیک')
    db.session.add_all([f_computer, f_accounting, f_english, f_graphic])
    db.session.flush()
    results.append('۴ رشته آموزشی')
    
    # ═══ ۳) دوره‌ها + سرفصل ═══
    c_python = Course(
        title='Python مقدماتی', code='CRS-0001', field_id=f_computer.id,
        description='آموزش مبانی برنامه‌نویسی پایتون', duration_hours=40, total_sessions=16,
        base_fee=8000000, registration_fee=500000, book_fee=200000, exam_fee=300000,
        is_active=True, branch_id=branch.id
    )
    c_icdl = Course(
        title='ICDL', code='CRS-0002', field_id=f_computer.id,
        description='مهارت‌های هفت‌گانه کامپیوتر', duration_hours=60, total_sessions=24,
        base_fee=6000000, registration_fee=500000, exam_fee=300000,
        is_active=True, branch_id=branch.id
    )
    c_accounting = Course(
        title='حسابداری مقدماتی', code='CRS-0003', field_id=f_accounting.id,
        description='مبانی حسابداری و دفترداری', duration_hours=50, total_sessions=20,
        base_fee=7000000, registration_fee=500000, book_fee=300000,
        is_active=True, branch_id=branch.id
    )
    c_photoshop = Course(
        title='Photoshop', code='CRS-0004', field_id=f_graphic.id,
        description='آموزش فتوشاپ از مبتدی تا پیشرفته', duration_hours=30, total_sessions=12,
        base_fee=5000000, registration_fee=400000,
        is_active=True, branch_id=branch.id
    )
    c_english = Course(
        title='English Pre-Intermediate', code='CRS-0005', field_id=f_english.id,
        description='زبان انگلیسی سطح پیش‌متوسط', duration_hours=48, total_sessions=24,
        base_fee=9000000, registration_fee=600000, book_fee=400000,
        is_active=True, branch_id=branch.id
    )
    db.session.add_all([c_python, c_icdl, c_accounting, c_photoshop, c_english])
    db.session.flush()
    
    # سرفصل‌های Python
    syl_data = [
        (c_python.id, 1, 'آشنایی با Python', 'نصب و راه‌اندازی', 2),
        (c_python.id, 2, 'متغیرها و انواع داده', 'String, Integer, Float', 3),
        (c_python.id, 3, 'ساختارهای کنترلی', 'if, for, while', 4),
        (c_python.id, 4, 'توابع', 'def, return, arguments', 3),
        (c_python.id, 5, 'لیست و دیکشنری', 'List, Dict, Tuple', 3),
        (c_python.id, 6, 'کار با فایل', 'read, write, CSV', 2),
    ]
    for cid, ch, title, lesson, h in syl_data:
        db.session.add(Syllabus(course_id=cid, chapter_no=ch, chapter_title=title, lesson_title=lesson, hours=h, order=ch))
    results.append('۵ دوره + ۶ سرفصل')
    
    # ═══ ۴) مدرسین ═══
    t_ahmadi = Teacher(
        teacher_code='TEC-1405-001', first_name='علی', last_name='احمدی',
        national_code='0012345678', mobile='09121111111', email='ahmadi@test.com',
        specialization='Python, Django, پایگاه داده', education='کارشناسی ارشد کامپیوتر',
        experience_years=8, level='professional', contract_type='hourly',
        hourly_rate=500000, is_active=True, branch_id=branch.id,
        user_id=2  # اتصال به کاربر مدرس
    )
    t_rezaei = Teacher(
        teacher_code='TEC-1405-002', first_name='مریم', last_name='رضایی',
        national_code='0012345679', mobile='09122222222', email='rezaei@test.com',
        specialization='ICDL, Office, Windows', education='کارشناسی IT',
        experience_years=5, level='professional', contract_type='session',
        session_rate=400000, is_active=True, branch_id=branch.id
    )
    t_karimi = Teacher(
        teacher_code='TEC-1405-003', first_name='حسن', last_name='کریمی',
        national_code='0012345680', mobile='09123333333', email='karimi@test.com',
        specialization='حسابداری، مالیات، بیمه', education='کارشناسی حسابداری',
        experience_years=10, level='master', contract_type='percentage',
        percentage_rate=40, is_active=True, branch_id=branch.id
    )
    db.session.add_all([t_ahmadi, t_rezaei, t_karimi])
    db.session.flush()
    results.append('۳ مدرس')
    
    # ═══ ۵) اتاق‌ها ═══
    r1 = Room(name='کلاس ۱۰۱', code='R-101', capacity=20, branch_id=branch.id)
    r2 = Room(name='کلاس ۱۰۲', code='R-102', capacity=15, branch_id=branch.id)
    r3 = Room(name='کارگاه کامپیوتر', code='R-201', capacity=12, branch_id=branch.id)
    db.session.add_all([r1, r2, r3])
    db.session.flush()
    results.append('۳ اتاق')
    
    # ═══ ۶) کلاس‌ها ═══
    cls_python = ClassGroup(
        class_code='PY-1405-01', name='Python گروه ۱', course_id=c_python.id,
        teacher_id=t_ahmadi.id, room_id=r3.id, max_capacity=12, current_count=0,
        days_of_week='[0, 2]', start_time='16:00', end_time='18:00',
        start_date=jdate(1405, 1, 16), end_date=jdate(1405, 3, 15),
        status='active', branch_id=branch.id
    )
    cls_icdl = ClassGroup(
        class_code='ICDL-1405-01', name='ICDL گروه ۱', course_id=c_icdl.id,
        teacher_id=t_rezaei.id, room_id=r1.id, max_capacity=15, current_count=0,
        days_of_week='[1, 3]', start_time='10:00', end_time='12:00',
        start_date=jdate(1405, 1, 17), end_date=jdate(1405, 4, 15),
        status='active', branch_id=branch.id
    )
    cls_accounting = ClassGroup(
        class_code='ACC-1405-01', name='حسابداری گروه ۱', course_id=c_accounting.id,
        teacher_id=t_karimi.id, room_id=r2.id, max_capacity=20, current_count=0,
        days_of_week='[0, 3]', start_time='14:00', end_time='16:00',
        start_date=jdate(1405, 2, 1), end_date=jdate(1405, 5, 1),
        status='active', branch_id=branch.id
    )
    db.session.add_all([cls_python, cls_icdl, cls_accounting])
    db.session.flush()
    results.append('۳ کلاس')
    
    # ═══ ۷) هنرجویان ═══
    students_data = [
        ('ST-1405-00001', 'محمد', 'رضایی', '0021111111', '09121000001', 'male', 'adult'),
        ('ST-1405-00002', 'زهرا', 'محمدی', '0021111112', '09121000002', 'female', 'adult'),
        ('ST-1405-00003', 'علی', 'حسنی', '0021111113', '09121000003', 'male', 'teen'),
        ('ST-1405-00004', 'فاطمه', 'علوی', '0021111114', '09121000004', 'female', 'adult'),
        ('ST-1405-00005', 'امیر', 'کاظمی', '0021111115', '09121000005', 'male', 'adult'),
        ('ST-1405-00006', 'نسرین', 'جعفری', '0021111116', '09121000006', 'female', 'adult'),
        ('ST-1405-00007', 'رضا', 'نوری', '0021111117', '09121000007', 'male', 'teen'),
        ('ST-1405-00008', 'سارا', 'صادقی', '0021111118', '09121000008', 'female', 'adult'),
    ]
    
    students = []
    for code, fn, ln, nc, mob, gen, cat in students_data:
        s = Student(
            student_code=code, first_name=fn, last_name=ln,
            national_code=nc, mobile=mob, gender=gen, category=cat,
            status='active', branch_id=branch.id,
            referral_source=['instagram', 'friend', 'website', 'phone'][hash(code) % 4]
        )
        students.append(s)
        db.session.add(s)
    db.session.flush()
    results.append('۸ هنرجو')
    
    # ═══ ۸) ثبت‌نام — اتصال هنرجو به دوره و کلاس ═══
    registrations_data = [
        (students[0], c_python, cls_python, t_ahmadi, 9000000, 5000000),  # محمد → Python
        (students[1], c_python, cls_python, t_ahmadi, 9000000, 3000000),  # زهرا → Python
        (students[2], c_python, cls_python, t_ahmadi, 9000000, 9000000),  # علی → Python (تسویه)
        (students[3], c_icdl, cls_icdl, t_rezaei, 7100000, 4000000),      # فاطمه → ICDL
        (students[4], c_icdl, cls_icdl, t_rezaei, 7100000, 2000000),      # امیر → ICDL
        (students[5], c_accounting, cls_accounting, t_karimi, 8100000, 5000000),  # نسرین → حسابداری
        (students[6], c_photoshop, None, None, 5400000, 5400000),          # رضا → Photoshop (تسویه)
        (students[7], c_english, None, None, 10000000, 0),                 # سارا → English (بدون پرداخت)
        # ثبت‌نام دوم — یک هنرجو در ۲ دوره
        (students[0], c_icdl, cls_icdl, t_rezaei, 7100000, 7100000),      # محمد → ICDL هم
        (students[1], c_accounting, cls_accounting, t_karimi, 8100000, 2000000),  # زهرا → حسابداری هم
    ]
    
    regs = []
    for i, (student, course, cls, teacher, fee, paid) in enumerate(registrations_data):
        reg_code = f'REG-1405-{i+1:05d}'
        reg = Registration(
            reg_code=reg_code, student_id=student.id, course_id=course.id,
            class_id=cls.id if cls else None, teacher_id=teacher.id if teacher else None,
            registration_date=jdate(1405, 1, 10 + i),
            start_date=cls.start_date if cls else jdate(1405, 1, 16),
            base_fee=fee, total_fee=fee, paid_amount=paid, remaining_amount=fee - paid,
            status='active', branch_id=branch.id
        )
        reg.calculate_fees()
        regs.append(reg)
        db.session.add(reg)
        db.session.flush()  # برای گرفتن reg.id
        
        # بروزرسانی ظرفیت کلاس
        if cls:
            cls.current_count = (cls.current_count or 0) + 1
        
        # ثبت پرداخت اولیه
        if paid > 0:
            pay = Payment(
                receipt_no=f'PAY-1405-{i+1:05d}', student_id=student.id,
                registration_id=reg.id, amount=paid, payment_method='cash',
                payment_date=jdate(1405, 1, 10 + i),
                description=f'پرداخت اولیه ثبت‌نام {reg_code}',
                status='confirmed', branch_id=branch.id
            )
            db.session.add(pay)
    
    db.session.flush()
    results.append('۱۰ ثبت‌نام')
    
    # ═══ ۹) اقساط ═══
    for reg in regs:
        if reg.remaining_amount > 0:
            count = 3
            inst_amount = reg.remaining_amount / count
            for j in range(count):
                inst = Installment(
                    registration_id=reg.id, installment_number=j + 1,
                    amount=round(inst_amount),
                    due_date=jdate(1405, 2, 1) + timedelta(days=30 * j),
                    status='pending'
                )
                db.session.add(inst)
    results.append('اقساط ایجاد شد')
    
    # ═══ ۱۰) صندوق ═══
    if Cashbox.query.count() == 0:
        cashbox = Cashbox(name='صندوق اصلی', code='CASH-01', balance=0, branch_id=branch.id)
        db.session.add(cashbox)
        db.session.flush()
        
        total_paid = sum(r.paid_amount for r in regs)
        cashbox.balance = total_paid
        db.session.add(CashboxTransaction(
            cashbox_id=cashbox.id, trans_type='in', amount=total_paid,
            description='موجودی اولیه از ثبت‌نام‌های نمونه',
            balance_after=total_paid
        ))
    results.append('صندوق')
    
    # ═══ ۱۱) دسته‌بندی هزینه ═══
    if ExpenseCategory.query.count() == 0:
        cats = [
            ExpenseCategory(name='اجاره', code='EXP-01'),
            ExpenseCategory(name='حقوق', code='EXP-02'),
            ExpenseCategory(name='تجهیزات', code='EXP-03'),
            ExpenseCategory(name='تبلیغات', code='EXP-04'),
            ExpenseCategory(name='قبوض', code='EXP-05'),
        ]
        db.session.add_all(cats)
    results.append('دسته‌بندی هزینه')
    
    # ═══ ۱۲) جلسات کلاس Python ═══
    for i in range(8):
        session_date = jdate(1405, 1, 16) + timedelta(days=2 * i)
        session = ClassSession(
            class_id=cls_python.id, session_number=i + 1,
            session_date=session_date, start_time='16:00', end_time='18:00',
            topic=['آشنایی با Python', 'متغیرها', 'حلقه‌ها', 'توابع', 'لیست‌ها', 'دیکشنری', 'فایل‌ها', 'پروژه'][i],
            status='completed' if i < 6 else 'scheduled'
        )
        db.session.add(session)
    db.session.flush()
    
    # حضور و غیاب جلسات قبلی
    python_sessions = ClassSession.query.filter_by(class_id=cls_python.id).filter(
        ClassSession.status == 'completed'
    ).all()
    
    for sess in python_sessions:
        for reg in cls_python.registrations.filter_by(status='active').all():
            import random
            status = random.choices(['present', 'absent', 'late'], weights=[80, 10, 10])[0]
            att = Attendance(
                session_id=sess.id, student_id=reg.student_id,
                status=status,
                arrival_time='16:00' if status != 'absent' else None,
                departure_time='18:00' if status == 'present' else None,
                entry_method='manual'
            )
            db.session.add(att)
    results.append('جلسات + حضور و غیاب')
    
    # ═══ ۱۳) آزمون + نمرات ═══
    exam = Exam(
        title='آزمون میان‌ترم Python', exam_code='EXM-1405-001',
        course_id=c_python.id, class_id=cls_python.id,
        exam_type='written', exam_date=jdate(1405, 2, 15),
        duration_minutes=90, total_marks=100, passing_marks=50,
        theory_weight=60, practical_weight=40, status='completed'
    )
    db.session.add(exam)
    db.session.flush()
    
    # بانک سوالات
    questions_data = [
        ('Python چیست؟', 'multiple_choice', 'زبان برنامه‌نویسی', 'سیستم‌عامل', 'وبسایت', 'سخت‌افزار', 'a', 'easy'),
        ('خروجی print(2+3) چیست؟', 'multiple_choice', '5', '23', 'Error', 'None', 'a', 'easy'),
        ('کدام یک نوع داده معتبر است؟', 'multiple_choice', 'int', 'number', 'digit', 'figure', 'a', 'medium'),
        ('توابع با def تعریف می‌شوند', 'true_false', None, None, None, None, 'a', 'easy'),
        ('len([1,2,3]) برابر است با ...', 'fill_blank', None, None, None, None, '3', 'medium'),
    ]
    for qt, qtype, a, b, c, d, correct, diff in questions_data:
        db.session.add(QuestionBank(
            question_text=qt, question_type=qtype,
            option_a=a, option_b=b, option_c=c, option_d=d,
            correct_answer=correct, course_id=c_python.id,
            difficulty=diff, marks=20
        ))
    
    # نمرات
    import random
    for reg in cls_python.registrations.filter_by(status='active').all():
        theory = random.randint(40, 95)
        practical = random.randint(50, 100)
        total = (theory * 0.6) + (practical * 0.4)
        
        db.session.add(ExamResult(
            exam_id=exam.id, student_id=reg.student_id,
            theory_score=theory, practical_score=practical,
            total_score=round(total, 1), is_passed=total >= 50,
            graded_at=datetime.utcnow()
        ))
        
        db.session.add(Grade(
            student_id=reg.student_id, registration_id=reg.id,
            course_id=c_python.id, class_id=cls_python.id,
            midterm_score=round(total, 1), total_score=round(total, 1),
            is_passed=total >= 50, attendance_percentage=85
        ))
    results.append('آزمون + نمرات')
    
    # ═══ ۱۴) قالب پیامک ═══
    templates_data = [
        ('ثبت‌نام', 'سلام {نام} عزیز، ثبت‌نام شما در دوره {دوره} با موفقیت انجام شد. کد: {کد}', 'registration'),
        ('یادآوری کلاس', 'سلام {نام}، کلاس شما فردا ساعت {ساعت} برگزار می‌شود.', 'reminder'),
        ('غیبت', 'سلام {نام}، شما در جلسه امروز غایب بودید.', 'absence'),
        ('یادآوری قسط', 'سلام {نام}، قسط شما به مبلغ {مبلغ} در تاریخ {تاریخ} سررسید می‌شود.', 'payment'),
        ('تولد', '🎉 {نام} عزیز، تولدت مبارک! آرزوی موفقیت برای شما داریم.', 'birthday'),
    ]
    for name, text, ttype in templates_data:
        db.session.add(MessageTemplate(name=name, template_text=text, template_type=ttype))
    results.append('قالب پیامک')
    
    # ═══ ۱۵) کاربر مدرس ═══
    from models.user import User, Role
    teacher_role = Role.query.filter_by(name='مدرس').first()
    if teacher_role:
        existing = User.query.filter_by(username='ahmadi').first()
        if not existing:
            teacher_user = User(username='ahmadi', full_name='علی احمدی', role_id=teacher_role.id, is_active=True)
            teacher_user.set_password('123456')
            db.session.add(teacher_user)
            db.session.flush()
            t_ahmadi.user_id = teacher_user.id
            results.append('کاربر مدرس')
    
    db.session.commit()
    
    return '✅ ' + ' | '.join(results)
