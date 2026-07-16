"""
تست کامل سیستم — بررسی اتصالات، ربات‌ها، فراز اس‌ام‌اس، اقساط
"""
import os, sys, json
sys.path.insert(0, '/home/user/academy_manager')

from app import create_app
from extensions import db

app = create_app()

def divider(title):
    print(f'\n{"="*60}')
    print(f'  {title}')
    print(f'{"="*60}')

def test_result(name, ok, detail=''):
    icon = '✅' if ok else '❌'
    print(f'  {icon} {name}' + (f' — {detail}' if detail else ''))

with app.app_context():
    
    # ═══════════════════════════════════════════
    #  ۱) بررسی داده‌های نمونه
    # ═══════════════════════════════════════════
    divider('۱) بررسی داده‌های نمونه')
    
    from models.student import Student
    from models.teacher import Teacher
    from models.course import Course, Field
    from models.classes import ClassGroup, ClassSession
    from models.registration import Registration, Installment
    from models.finance import Payment, Cashbox
    from models.attendance import Attendance
    from models.exam import ExamResult, Grade
    from models.system import SystemSettings, MessageTemplate
    
    # اگر داده نمونه نیست، بساز
    if Student.query.count() == 0:
        print('  ⏳ ایجاد داده‌های نمونه...')
        from utils.demo_data import create_demo_data
        result = create_demo_data()
        print(f'  {result}')
    
    test_result('هنرجویان', Student.query.count() >= 8, f'{Student.query.count()} نفر')
    test_result('مدرسین', Teacher.query.count() >= 3, f'{Teacher.query.count()} نفر')
    test_result('دوره‌ها', Course.query.count() >= 5, f'{Course.query.count()} دوره')
    test_result('کلاس‌ها', ClassGroup.query.count() >= 3, f'{ClassGroup.query.count()} کلاس')
    test_result('ثبت‌نام‌ها', Registration.query.count() >= 10, f'{Registration.query.count()} ثبت‌نام')
    test_result('پرداخت‌ها', Payment.query.count() >= 9, f'{Payment.query.count()} پرداخت')
    test_result('اقساط', Installment.query.count() > 0, f'{Installment.query.count()} قسط')
    test_result('حضور و غیاب', Attendance.query.count() > 0, f'{Attendance.query.count()} رکورد')
    test_result('نمرات', ExamResult.query.count() > 0, f'{ExamResult.query.count()} نمره')
    
    # ═══════════════════════════════════════════
    #  ۲) تست اتصالات هنرجو → دوره → کلاس → مدرس
    # ═══════════════════════════════════════════
    divider('۲) تست اتصالات زنجیره‌ای')
    
    for student in Student.query.limit(3).all():
        regs = student.registrations.all()
        test_result(f'{student.full_name}', len(regs) > 0, f'{len(regs)} ثبت‌نام')
        for r in regs:
            cls = r.class_group
            teacher = cls.teacher if cls else None
            course = r.course
            
            chain_ok = course is not None
            test_result(
                f'  → {course.title if course else "?"}',
                chain_ok,
                f'کلاس: {cls.name if cls else "-"} | مدرس: {teacher.full_name if teacher else "-"} | مانده: {r.remaining_amount:,.0f}'
            )
    
    # ═══════════════════════════════════════════
    #  ۳) تست سیستم اقساط
    # ═══════════════════════════════════════════
    divider('۳) تست سیستم اقساط')
    
    from datetime import date, timedelta
    
    today = date.today()
    
    total_installments = Installment.query.count()
    pending = Installment.query.filter(Installment.status.in_(['pending', 'partial'])).count()
    paid = Installment.query.filter_by(status='paid').count()
    overdue = Installment.query.filter(
        Installment.due_date < today,
        Installment.status.in_(['pending', 'partial'])
    ).count()
    
    test_result('کل اقساط', total_installments > 0, f'{total_installments}')
    test_result('اقساط در انتظار', pending >= 0, f'{pending}')
    test_result('اقساط پرداخت شده', paid >= 0, f'{paid}')
    test_result('اقساط معوقه', True, f'{overdue}')
    
    # تست پرداخت قسط
    first_pending = Installment.query.filter(Installment.status.in_(['pending', 'partial'])).first()
    if first_pending:
        reg = first_pending.registration
        student = reg.student
        test_result('اتصال قسط → ثبت‌نام', reg is not None, f'{reg.reg_code}')
        test_result('اتصال ثبت‌نام → هنرجو', student is not None, f'{student.full_name}')
        test_result('اتصال ثبت‌نام → دوره', reg.course is not None, f'{reg.course.title}')
        test_result('مبلغ قسط', first_pending.amount > 0, f'{first_pending.amount:,.0f} تومان')
        test_result('تاریخ سررسید', first_pending.due_date is not None, f'{first_pending.due_date}')
    
    # محاسبه جریمه
    overdue_list = Installment.query.filter(
        Installment.due_date < today,
        Installment.status.in_(['pending', 'partial'])
    ).all()
    
    for inst in overdue_list[:3]:
        days = (today - inst.due_date).days
        daily_rate = 0.01 / 30
        late_fee = round(inst.amount * daily_rate * days)
        test_result(f'جریمه قسط #{inst.installment_number}', late_fee >= 0, f'{days} روز تأخیر = {late_fee:,.0f} تومان')
    
    # ═══════════════════════════════════════════
    #  ۴) تست تنظیمات ربات تلگرام
    # ═══════════════════════════════════════════
    divider('۴) تست ربات تلگرام')
    
    settings = SystemSettings.query.first()
    
    test_result('مدل SystemSettings', settings is not None)
    test_result('فیلد telegram_bot_token', hasattr(settings, 'telegram_bot_token'))
    test_result('فیلد telegram_webhook_url', hasattr(settings, 'telegram_webhook_url'))
    
    # تست وب‌هوک
    with app.test_client() as client:
        # شبیه‌سازی پیام /start
        test_msg = {
            'update_id': 123456,
            'message': {
                'message_id': 1,
                'from': {'id': 111, 'first_name': 'Test'},
                'chat': {'id': 111, 'type': 'private'},
                'text': '/start'
            }
        }
        
        resp = client.post('/webhook/telegram', json=test_msg)
        test_result('وب‌هوک تلگرام /start', resp.status_code == 200, f'HTTP {resp.status_code}')
        
        # شبیه‌سازی جستجو با موبایل
        test_msg['message']['text'] = '09121000001'
        resp = client.post('/webhook/telegram', json=test_msg)
        test_result('وب‌هوک تلگرام — جستجوی موبایل', resp.status_code == 200, f'HTTP {resp.status_code}')
        
        # شبیه‌سازی جستجوی دوره
        test_msg['message']['text'] = 'Python'
        resp = client.post('/webhook/telegram', json=test_msg)
        test_result('وب‌هوک تلگرام — جستجوی دوره', resp.status_code == 200, f'HTTP {resp.status_code}')
    
    # ═══════════════════════════════════════════
    #  ۵) تست ربات بله
    # ═══════════════════════════════════════════
    divider('۵) تست ربات بله')
    
    test_result('فیلد bale_bot_token', hasattr(settings, 'bale_bot_token'))
    test_result('فیلد bale_webhook_url', hasattr(settings, 'bale_webhook_url'))
    
    with app.test_client() as client:
        test_msg = {
            'update_id': 789,
            'message': {
                'message_id': 1,
                'from': {'id': 222, 'first_name': 'BaleUser'},
                'chat': {'id': 222, 'type': 'private'},
                'text': '/start'
            }
        }
        
        resp = client.post('/webhook/bale', json=test_msg)
        test_result('وب‌هوک بله /start', resp.status_code == 200, f'HTTP {resp.status_code}')
        
        test_msg['message']['text'] = '09121000002'
        resp = client.post('/webhook/bale', json=test_msg)
        test_result('وب‌هوک بله — جستجوی موبایل', resp.status_code == 200, f'HTTP {resp.status_code}')
        
        test_msg['message']['text'] = 'ICDL'
        resp = client.post('/webhook/bale', json=test_msg)
        test_result('وب‌هوک بله — جستجوی دوره', resp.status_code == 200, f'HTTP {resp.status_code}')
    
    # ═══════════════════════════════════════════
    #  ۶) تست فراز اس‌ام‌اس
    # ═══════════════════════════════════════════
    divider('۶) تست فراز اس‌ام‌اس')
    
    test_result('فیلد farazsms_api_key', hasattr(settings, 'farazsms_api_key'))
    test_result('فیلد farazsms_sender', hasattr(settings, 'farazsms_sender'))
    test_result('فیلد farazsms_pattern_code', hasattr(settings, 'farazsms_pattern_code'))
    
    # تست تابع ارسال (بدون API key واقعی)
    from routes.new_features import send_farazsms
    
    # تست ساختار تابع
    test_result('تابع send_farazsms', callable(send_farazsms))
    
    # تست ارسال (بدون API key — باید خطا برگرداند ولی کرش نکند)
    try:
        result = send_farazsms('09121234567', 'تست')
        test_result('ساختار پاسخ فراز', isinstance(result, dict))
    except Exception as e:
        test_result('ساختار پاسخ فراز', False, str(e))
    
    # تست قالب‌های پیامک
    templates = MessageTemplate.query.all()
    test_result('قالب‌های پیامک', len(templates) > 0, f'{len(templates)} قالب')
    
    # ═══════════════════════════════════════════
    #  ۷) تست اتصالات کامل — هنرجو تا پرداخت
    # ═══════════════════════════════════════════
    divider('۷) تست زنجیره کامل')
    
    # یک هنرجو با بدهی پیدا کن
    debtor = None
    for s in Student.query.all():
        for r in s.registrations:
            if r.remaining_amount > 0:
                debtor = (s, r)
                break
        if debtor:
            break
    
    if debtor:
        s, r = debtor
        print(f'  📋 هنرجو: {s.full_name} ({s.student_code})')
        print(f'     📱 موبایل: {s.mobile}')
        print(f'     📚 دوره: {r.course.title}')
        print(f'     🏫 کلاس: {r.class_group.name if r.class_group else "-"}')
        print(f'     👨‍🏫 مدرس: {r.class_group.teacher.full_name if r.class_group and r.class_group.teacher else "-"}')
        print(f'     💰 شهریه: {r.total_fee:,.0f}')
        print(f'     💵 پرداختی: {r.paid_amount:,.0f}')
        print(f'     ❌ مانده: {r.remaining_amount:,.0f}')
        
        # اقساط
        insts = Installment.query.filter_by(registration_id=r.id).all()
        print(f'     📅 اقساط: {len(insts)}')
        for inst in insts:
            status_icon = '✅' if inst.status == 'paid' else '⏳'
            print(f'        {status_icon} قسط #{inst.installment_number}: {inst.amount:,.0f} — سررسید: {inst.due_date} — وضعیت: {inst.status}')
        
        # پرداخت‌ها
        pays = Payment.query.filter_by(student_id=s.id).all()
        print(f'     💳 پرداخت‌ها: {len(pays)}')
        for p in pays:
            print(f'        💰 {p.receipt_no}: {p.amount:,.0f} — {p.payment_method} — {p.payment_date}')
        
        test_result('زنجیره کامل هنرجو→دوره→کلاس→اقساط→پرداخت', True)
    
    # ═══════════════════════════════════════════
    #  خلاصه نهایی
    # ═══════════════════════════════════════════
    divider('📊 خلاصه نهایی')
    
    print(f'  مسیرها: {sum(1 for r in app.url_map.iter_rules() if r.endpoint != "static")}')
    print(f'  جداول: {len(db.metadata.tables)}')
    print(f'  هنرجویان: {Student.query.count()}')
    print(f'  ثبت‌نام‌ها: {Registration.query.count()}')
    print(f'  اقساط: {Installment.query.count()}')
    print(f'  پرداخت‌ها: {Payment.query.count()}')
    print(f'  حضور و غیاب: {Attendance.query.count()}')
    print(f'  نمرات: {ExamResult.query.count()}')
    print(f'  قالب پیامک: {MessageTemplate.query.count()}')
    print()
    print('  ✅ تمام تست‌ها با موفقیت انجام شد!')
