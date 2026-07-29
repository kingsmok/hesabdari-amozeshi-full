"""پایش ارتباط بین ماژول‌ها و تشخیص ناسازگاری‌های فنی بدون تغییر داده."""
from __future__ import annotations

import os
from datetime import date

from flask import current_app
from sqlalchemy import Date, extract, func, select

from extensions import db


def _check(name, status, message, group='core', detail=None):
    return {
        'name': name,
        'status': status,
        'message': message,
        'group': group,
        'detail': detail,
    }


def _orphan_foreign_keys() -> tuple[int, list[str]]:
    total = 0
    details = []
    for table in db.metadata.sorted_tables:
        for foreign_key in table.foreign_keys:
            parent_table = foreign_key.column.table
            parent_alias = parent_table.alias(
                f'parent_{table.name}_{foreign_key.parent.name}_{parent_table.name}'
            )
            child_column = foreign_key.parent
            parent_column = parent_alias.c[foreign_key.column.name]
            statement = select(func.count()).select_from(
                table.outerjoin(parent_alias, child_column == parent_column)
            ).where(child_column.is_not(None), parent_column.is_(None))
            count = int(db.session.execute(statement).scalar() or 0)
            if count:
                total += count
                details.append(
                    f'{table.name}.{child_column.name} → '
                    f'{parent_table.name}.{foreign_key.column.name}: {count}'
                )
    return total, details


def _legacy_date_count() -> int:
    count = 0
    for table in db.metadata.sorted_tables:
        date_columns = [column for column in table.columns if isinstance(column.type, Date)]
        for column in date_columns:
            count += int(db.session.execute(
                select(func.count()).select_from(table).where(
                    column.is_not(None),
                    extract('year', column).between(1300, 1500)
                )
            ).scalar() or 0)
    return count


def run_system_diagnostics() -> dict:
    """اجرای بررسی‌های سبک؛ هیچ درخواست خارجی یا تغییر دیتابیسی انجام نمی‌دهد."""
    checks = []

    # دیتابیس و schema
    try:
        from utils.database_tools import (
            check_database_integrity, collect_table_stats, database_backend,
            database_size_bytes,
        )
        healthy, message = check_database_integrity()
        table_stats = collect_table_stats()
        checks.append(_check(
            'اتصال و سلامت دیتابیس', 'ok' if healthy else 'error',
            f'{database_backend()} — {message}', 'database'
        ))
        checks.append(_check(
            'ساختار جداول', 'ok' if len(table_stats) == len(db.metadata.tables) else 'warning',
            f'{len(table_stats)} جدول فعال از {len(db.metadata.tables)} مدل ثبت‌شده', 'database'
        ))
        checks.append(_check(
            'حجم دیتابیس', 'ok', f'{database_size_bytes() / (1024 * 1024):.2f} مگابایت', 'database'
        ))
    except Exception as exc:
        checks.append(_check('اتصال و سلامت دیتابیس', 'error', str(exc), 'database'))
        table_stats = []

    try:
        orphan_count, orphan_details = _orphan_foreign_keys()
        checks.append(_check(
            'ارتباط کلیدهای خارجی', 'ok' if orphan_count == 0 else 'error',
            'هیچ رکورد یتیمی پیدا نشد' if orphan_count == 0 else f'{orphan_count} ارتباط شکسته پیدا شد',
            'relations', orphan_details
        ))
    except Exception as exc:
        checks.append(_check('ارتباط کلیدهای خارجی', 'error', str(exc), 'relations'))

    legacy_dates = _legacy_date_count()
    checks.append(_check(
        'سازگاری تاریخ‌های شمسی', 'ok' if legacy_dates == 0 else 'error',
        'تمام تاریخ‌ها به‌صورت میلادی استاندارد ذخیره شده‌اند' if legacy_dates == 0
        else f'{legacy_dates} تاریخ قدیمی با سال شمسی داخل دیتابیس باقی مانده است',
        'relations'
    ))

    # زنجیره کلاس و ثبت‌نام
    from models.classes import ClassGroup
    from models.registration import Registration
    capacity_mismatches = []
    for class_group in ClassGroup.query.all():
        actual = Registration.query.filter_by(class_id=class_group.id, status='active').count()
        if (class_group.current_count or 0) != actual:
            capacity_mismatches.append(
                f'{class_group.class_code}: مقدار ثبت‌شده {class_group.current_count or 0}، مقدار واقعی {actual}'
            )
    checks.append(_check(
        'اتصال ثبت‌نام به ظرفیت کلاس', 'ok' if not capacity_mismatches else 'warning',
        'ظرفیت همه کلاس‌ها با ثبت‌نام‌های فعال هماهنگ است' if not capacity_mismatches
        else f'{len(capacity_mismatches)} کلاس نیاز به همگام‌سازی ظرفیت دارد',
        'relations', capacity_mismatches
    ))

    invalid_financial = Registration.query.filter(
        (Registration.total_fee < 0) |
        (Registration.paid_amount < 0) |
        (Registration.remaining_amount < -1)
    ).count()
    from models.finance import Payment
    payment_mismatches = []
    for registration in Registration.query.all():
        payment_total = db.session.query(func.sum(Payment.amount)).filter(
            Payment.registration_id == registration.id,
            Payment.status == 'confirmed'
        ).scalar() or 0
        if abs(float(payment_total) - float(registration.paid_amount or 0)) > 1:
            payment_mismatches.append(
                f'{registration.reg_code}: پرداخت‌ها {payment_total:,.0f}، مقدار ثبت‌نام {(registration.paid_amount or 0):,.0f}'
            )
    financial_problem_count = invalid_financial + len(payment_mismatches)
    checks.append(_check(
        'ارتباط شهریه، پرداخت و مانده', 'ok' if financial_problem_count == 0 else 'warning',
        'مبالغ ثبت‌نام با رسیدهای تأییدشده هماهنگ است' if financial_problem_count == 0
        else f'{financial_problem_count} ناسازگاری مالی نیاز به بررسی دارد',
        'relations', payment_mismatches
    ))

    from models.course import Certificate
    duplicate_certificates = db.session.query(
        Certificate.registration_id, func.count(Certificate.id)
    ).filter(
        Certificate.registration_id.isnot(None),
        Certificate.status.in_(['active', 'reissued'])
    ).group_by(Certificate.registration_id).having(func.count(Certificate.id) > 1).count()
    checks.append(_check(
        'ارتباط ثبت‌نام و گواهینامه', 'ok' if duplicate_certificates == 0 else 'warning',
        'برای هر ثبت‌نام حداکثر یک گواهینامه معتبر وجود دارد' if duplicate_certificates == 0
        else f'{duplicate_certificates} ثبت‌نام دارای گواهینامه معتبر تکراری است',
        'relations'
    ))

    # فایل‌ها و PDF
    paths = {
        'پوشه آپلود': current_app.config['UPLOAD_FOLDER'],
        'پوشه پشتیبان': current_app.config['BACKUP_FOLDER'],
    }
    for label, path in paths.items():
        try:
            os.makedirs(path, exist_ok=True)
            writable = os.access(path, os.W_OK)
            checks.append(_check(
                label, 'ok' if writable else 'error',
                'قابل نوشتن' if writable else 'مجوز نوشتن وجود ندارد', 'storage', path
            ))
        except OSError as exc:
            checks.append(_check(label, 'error', str(exc), 'storage', path))

    font_dir = os.path.join(current_app.static_folder, 'fonts')
    missing_fonts = [
        name for name in ('DejaVuSans.ttf', 'DejaVuSans-Bold.ttf')
        if not os.path.isfile(os.path.join(font_dir, name))
    ]
    checks.append(_check(
        'موتور PDF فارسی', 'ok' if not missing_fonts else 'error',
        'فونت‌های PDF فارسی آماده‌اند' if not missing_fonts else f'فونت‌های مفقود: {", ".join(missing_fonts)}',
        'storage'
    ))

    # تنظیمات و سرویس‌ها (بدون تماس شبکه)
    from models.system import Branch, SystemSettings
    from models.user import User
    settings = SystemSettings.query.first()
    checks.append(_check(
        'تنظیمات پایه نرم‌افزار', 'ok' if settings and Branch.query.count() else 'error',
        'تنظیمات و شعبه اصلی موجود است' if settings and Branch.query.count() else 'تنظیمات یا شعبه تعریف نشده است',
        'core'
    ))
    checks.append(_check(
        'کاربر مدیر فعال', 'ok' if User.query.filter_by(is_admin=True, is_active=True).count() else 'error',
        'مدیر فعال موجود است' if User.query.filter_by(is_admin=True, is_active=True).count() else 'هیچ مدیر فعالی وجود ندارد',
        'core'
    ))

    from utils.bot_services import bale_polling_manager
    bale_status = bale_polling_manager.status()
    checks.append(_check(
        'ربات بله',
        'ok' if bale_status['running'] else ('warning' if settings and settings.bale_bot_token else 'info'),
        'Long Polling فعال است' if bale_status['running'] else (
            'توکن موجود است ولی Long Polling متوقف است' if settings and settings.bale_bot_token else 'تنظیم نشده'
        ),
        'connections', bale_status.get('last_error') or None
    ))
    checks.append(_check(
        'ربات تلگرام', 'ok' if settings and settings.telegram_bot_token else 'info',
        'توکن تنظیم شده است' if settings and settings.telegram_bot_token else 'تنظیم نشده', 'connections'
    ))
    sms_ready = bool(settings and settings.farazsms_api_key and settings.farazsms_sender)
    checks.append(_check(
        'پنل پیامکی', 'ok' if sms_ready else 'info',
        'API Key و خط فرستنده تنظیم شده‌اند' if sms_ready else 'تنظیم نشده یا ناقص است', 'connections'
    ))

    summary = {
        'ok': sum(check['status'] == 'ok' for check in checks),
        'warning': sum(check['status'] == 'warning' for check in checks),
        'error': sum(check['status'] == 'error' for check in checks),
        'info': sum(check['status'] == 'info' for check in checks),
        'total': len(checks),
    }
    return {'checks': checks, 'summary': summary, 'generated_at': date.today()}


def repair_safe_consistency_issues() -> dict:
    """فقط اصلاحات قطعی و بدون حذف اطلاعات را اعمال می‌کند."""
    from models.classes import ClassGroup
    from models.registration import Registration
    from utils.database_tools import repair_legacy_jalali_dates

    repaired_dates = repair_legacy_jalali_dates()
    synced_classes = 0
    for class_group in ClassGroup.query.all():
        actual = Registration.query.filter_by(class_id=class_group.id, status='active').count()
        if (class_group.current_count or 0) != actual:
            class_group.current_count = actual
            synced_classes += 1
    if synced_classes:
        db.session.commit()
    return {'dates': repaired_dates, 'classes': synced_classes}
