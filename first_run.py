"""
راه‌اندازی اولیه — اجرا در اولین شروع برنامه
ساخت دیتابیس + وارد کردن اطلاعات + داده‌های نمونه
"""
import os
import sys

# مسیر اصلی
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

os.chdir(BASE_DIR)
sys.path.insert(0, BASE_DIR)


def setup():
    print("\n" + "=" * 60)
    print("  راه‌اندازی اولیه سیستم مدیریت آموزشگاه")
    print("=" * 60)

    # ۱) ایجاد پوشه‌ها
    print("\n  [1/4] ایجاد پوشه‌ها...")
    dirs = [
        'instance',
        'backups',
        'static/uploads',
        'static/uploads/students',
        'static/uploads/teachers',
        'static/uploads/certificates',
        'static/uploads/documents',
    ]
    for d in dirs:
        os.makedirs(os.path.join(BASE_DIR, d), exist_ok=True)
        print(f"    ✓ {d}")

    # ۲) ساخت دیتابیس
    print("\n  [2/4] ساخت دیتابیس...")
    from app import create_app
    app = create_app()
    print("    ✓ دیتابیس ساخته شد")

    # ۳) وارد کردن اطلاعات آموزشگاه رهسا
    print("\n  [3/4] وارد کردن اطلاعات آموزشگاه رهسا...")
    with app.app_context():
        try:
            from models.course import Field, Course
            from models.teacher import Teacher

            # بررسی آیا قبلاً وارد شده
            if Course.query.count() == 0:
                # اجرای import_rahs_data
                import import_rahs_data
                print("    ✓ اطلاعات واقعی وارد شد")
            else:
                print("    ✓ اطلاعات قبلاً موجود است")
        except Exception as e:
            print(f"    ⚠ خطا: {e}")

    # ۴) داده‌های نمونه
    print("\n  [4/4] ایجاد داده‌های نمونه...")
    with app.app_context():
        try:
            from models.student import Student
            if Student.query.count() == 0:
                from utils.demo_data import create_demo_data
                result = create_demo_data()
                print(f"    ✓ {result}")
            else:
                print("    ✓ داده‌های نمونه قبلاً موجود است")
        except Exception as e:
            print(f"    ⚠ خطا: {e}")

    print("\n" + "=" * 60)
    print("  ✅ راه‌اندازی اولیه کامل شد!")
    print("=" * 60)
    print("\n  نام کاربری: admin")
    print("  رمز عبور:   admin123")
    print("\n  ⚠ حتماً رمز عبور را تغییر دهید!")
    print("=" * 60)


if __name__ == '__main__':
    setup()
