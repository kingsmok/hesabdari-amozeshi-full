"""
داده‌های پیش‌فرض نصب تازه — نقش‌ها، دسترسی‌ها، تنظیمات، شعبه، دسته‌های هزینه.
(انتقال مستقیم از app.py؛ رفتار بدون تغییر، فقط مسئولیت جدا شد.)
"""
from __future__ import annotations

from extensions import db


def create_default_data() -> None:
    """ایجاد دادهٔ پایه فقط در نصب خالی (idempotent)."""
    import models.user
    import models.student
    import models.teacher
    import models.course
    import models.classes
    import models.registration
    import models.finance
    import models.accounting
    import models.attendance
    import models.exam
    import models.system

    from models.user import Permission, Role, RolePermission
    from models.system import Branch, SystemSettings

    # ── نقش‌های پیش‌فرض ────────────────────────────────────────────────
    if Role.query.count() == 0:
        roles_data = [
            {'name': 'مدیر کل', 'description': 'دسترسی کامل به تمام بخش‌ها', 'is_admin': True},
            {'name': 'مدیر آموزشگاه', 'description': 'مدیریت آموزشی و مالی', 'is_admin': False},
            {'name': 'منشی', 'description': 'ثبت‌نام، هنرجو، حضور و غیاب', 'is_admin': False},
            {'name': 'حسابدار', 'description': 'فقط بخش مالی و حسابداری', 'is_admin': False},
            {'name': 'مدرس', 'description': 'حضور و غیاب کلاس‌های خود', 'is_admin': False},
            {'name': 'مسئول آموزش', 'description': 'کلاس‌ها، آزمون‌ها، مدرسین', 'is_admin': False},
        ]
        db.session.add_all(Role(**rd) for rd in roles_data)
        db.session.commit()

        default_perms = {
            'مدیر آموزشگاه': {
                'students': ['view', 'create', 'edit', 'delete'],
                'registration': ['view', 'create', 'edit', 'delete'],
                'classes': ['view', 'create', 'edit', 'delete'],
                'teachers': ['view', 'create', 'edit'],
                'attendance': ['view', 'create', 'edit'],
                'exams': ['view', 'create', 'edit'],
                'courses': ['view', 'create', 'edit'],
                'finance': ['view'], 'reports': ['view'],
                'messaging': ['view', 'create'],
                'certificates': ['view', 'create'],
            },
            'منشی': {
                'students': ['view', 'create', 'edit'],
                'registration': ['view', 'create'],
                'classes': ['view'],
                'attendance': ['view', 'create', 'edit'],
                'courses': ['view'],
                'messaging': ['view', 'create'],
            },
            'حسابدار': {
                'finance': ['view', 'create', 'edit', 'delete'],
                'accounting': ['view', 'create', 'edit', 'delete'],
                'payroll': ['view', 'create', 'edit'],
                'tax': ['view', 'create'], 'reports': ['view'],
            },
            'مدرس': {
                'attendance': ['view', 'create', 'edit'],
                'exams': ['view', 'create', 'edit'],
                'classes': ['view'], 'students': ['view'],
            },
            'مسئول آموزش': {
                'classes': ['view', 'create', 'edit', 'delete'],
                'teachers': ['view', 'create', 'edit'],
                'exams': ['view', 'create', 'edit'],
                'courses': ['view', 'create', 'edit'],
                'attendance': ['view', 'create', 'edit'],
                'students': ['view'], 'registration': ['view'],
            },
        }
        for role_name, modules in default_perms.items():
            role = Role.query.filter_by(name=role_name).first()
            if not role:
                continue
            for module, actions in modules.items():
                for action in actions:
                    perm = Permission.query.filter_by(module=module,
                                                      action=action).first()
                    if not perm:
                        perm = Permission(module=module, action=action,
                                          description=f'{action} {module}')
                        db.session.add(perm)
                        db.session.flush()
                    db.session.add(RolePermission(role_id=role.id,
                                                  permission_id=perm.id))
        db.session.commit()

    # NOTE: مدیر پیش‌فرض عمداً ساخته نمی‌شود (امنیت)؛ ویزارد /setup یا
    # config.ini نصب‌کننده حساب مدیر را می‌سازند.

    # ── تنظیمات سیستم ──────────────────────────────────────────────────
    if SystemSettings.query.count() == 0:
        db.session.add(SystemSettings(
            academy_name='آموزشگاه نمونه', academy_code='AC-001',
            phone='021-12345678', address='تهران، خیابان ولیعصر',
            current_year='1405', current_term='بهار'))
        db.session.commit()

    # ── شعبهٔ اصلی ─────────────────────────────────────────────────────
    if Branch.query.count() == 0:
        db.session.add(Branch(name='شعبه مرکزی', code='BR-001',
                              address='آدرس شعبه مرکزی', phone='021-12345678',
                              is_main=True))
        db.session.commit()

    # ── دسته‌های پایهٔ هزینه ───────────────────────────────────────────
    from models.finance import ExpenseCategory
    if ExpenseCategory.query.count() == 0:
        db.session.add_all([
            ExpenseCategory(name=name, code=code, is_active=True)
            for name, code in (
                ('اجاره', 'EXP-01'), ('حقوق و دستمزد', 'EXP-02'),
                ('قبوض و خدمات', 'EXP-03'), ('تجهیزات و ملزومات', 'EXP-04'),
                ('تبلیغات', 'EXP-05'), ('تعمیر و نگهداری', 'EXP-06'),
                ('حمل و نقل', 'EXP-07'), ('سایر هزینه‌ها', 'EXP-99'),
            )
        ])
        db.session.commit()
