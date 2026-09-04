"""ابزارهای امن و مستقل از مسیر برای پایش و نگهداری دیتابیس."""
from __future__ import annotations

import os
from datetime import datetime

from sqlalchemy import inspect, text

from extensions import db


def database_backend() -> str:
    return db.engine.url.get_backend_name()


def sqlite_database_path() -> str | None:
    """مسیر واقعی SQLite را از engine فعال می‌خواند، نه از مسیر ثابت پروژه."""
    if database_backend() != 'sqlite':
        return None
    path = db.engine.url.database
    return os.path.abspath(path) if path and path != ':memory:' else None


def database_size_bytes() -> int:
    path = sqlite_database_path()
    if path and os.path.isfile(path):
        return os.path.getsize(path)
    return 0


def collect_table_stats() -> list[dict]:
    """نام و تعداد رکورد جداول را برای SQLite/MySQL/PostgreSQL برمی‌گرداند."""
    inspector = inspect(db.engine)
    preparer = db.engine.dialect.identifier_preparer
    stats = []
    with db.engine.connect() as connection:
        for table_name in sorted(inspector.get_table_names()):
            try:
                quoted = preparer.quote(table_name)
                count = connection.execute(text(f'SELECT COUNT(*) FROM {quoted}')).scalar_one()
                stats.append({'name': table_name, 'count': int(count)})
            except Exception as exc:
                stats.append({'name': table_name, 'count': 0, 'error': str(exc)})
    return stats


def check_database_integrity() -> tuple[bool, str]:
    """بررسی سلامت متناسب با موتور دیتابیس."""
    if database_backend() == 'sqlite':
        row = db.session.execute(text('PRAGMA integrity_check')).first()
        message = str(row[0]) if row else 'بدون پاسخ'
        return message.lower() == 'ok', message

    db.session.execute(text('SELECT 1'))
    return True, 'اتصال و اجرای Query موفق است'


def optimize_database() -> tuple[bool, str]:
    """بهینه‌سازی بدون فرض مسیر ثابت و با پشتیبانی موتور فعال."""
    backend = database_backend()
    if backend == 'sqlite':
        # VACUUM خارج از transaction اجرا می‌شود.
        db.session.remove()
        with db.engine.connect().execution_options(isolation_level='AUTOCOMMIT') as connection:
            connection.execute(text('VACUUM'))
            connection.execute(text('ANALYZE'))
        return True, 'VACUUM و ANALYZE انجام شد'

    if backend == 'postgresql':
        with db.engine.connect().execution_options(isolation_level='AUTOCOMMIT') as connection:
            connection.execute(text('ANALYZE'))
        return True, 'ANALYZE انجام شد'

    # در MySQL آمار optimizer جداول با ANALYZE TABLE به مجوز اضافه نیاز دارد؛
    # برای جلوگیری از توقف کل سیستم، اتصال و metadata بررسی می‌شود.
    collect_table_stats()
    return True, 'ساختار و دسترسی جداول بررسی شد'


def repair_legacy_jalali_dates() -> int:
    """تاریخ‌هایی که قبلاً با سال شمسی داخل ستون میلادی ذخیره شده‌اند اصلاح می‌کند.

    SQLAlchemy تمام ستون‌های Date را میلادی نگه می‌دارد. نسخه‌های قدیمی داده نمونه،
    سال‌هایی مثل ۱۴۰۵ را مستقیماً ذخیره می‌کردند که گزارش‌ها و سررسیدها را خراب می‌کرد.
    """
    from datetime import date
    from sqlalchemy import Date, extract, select, update
    from utils.jalali import jalali_to_gregorian

    repaired = 0
    for table in db.metadata.sorted_tables:
        primary_keys = list(table.primary_key.columns)
        if len(primary_keys) != 1:
            continue
        primary_key = primary_keys[0]
        date_columns = [column for column in table.columns if isinstance(column.type, Date)]
        for column in date_columns:
            rows = db.session.execute(
                select(primary_key, column).where(
                    column.is_not(None),
                    extract('year', column).between(1300, 1500)
                )
            ).all()
            for record_id, value in rows:
                if isinstance(value, str):
                    try:
                        value = date.fromisoformat(value[:10])
                    except ValueError:
                        continue
                if not isinstance(value, date) or not (1300 <= value.year <= 1500):
                    continue
                converted = jalali_to_gregorian(value.year, value.month, value.day)
                if converted:
                    db.session.execute(
                        update(table).where(primary_key == record_id).values({column.name: converted})
                    )
                    repaired += 1
    if repaired:
        db.session.commit()
    return repaired


def sqlite_backup(destination: str) -> None:
    """پشتیبان سازگار SQLite با Backup API؛ فایل ناقص حین تراکنش تولید نمی‌کند."""
    source_path = sqlite_database_path()
    if not source_path:
        raise RuntimeError('پشتیبان فایل در این بخش فقط برای دیتابیس SQLite پشتیبانی می‌شود')

    import sqlite3

    os.makedirs(os.path.dirname(os.path.abspath(destination)), exist_ok=True)
    source = sqlite3.connect(source_path)
    target = sqlite3.connect(destination)
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()


def ensure_settings_columns() -> int:
    """
    ستون‌های تازه‌ی جدول تنظیمات را روی نصب‌های قدیمی اضافه می‌کند.
    (SQLite با create_all ستون جدید به جدول موجود اضافه نمی‌کند.)
    خروجی: تعداد ستون‌هایی که واقعاً اضافه شدند.
    """
    alters = [
        "ALTER TABLE system_settings ADD COLUMN backup_bot_enabled BOOLEAN DEFAULT 0",
        "ALTER TABLE system_settings ADD COLUMN backup_bot_chat_id VARCHAR(200)",
        "ALTER TABLE system_settings ADD COLUMN backup_bot_max_mb INTEGER DEFAULT 45",
        "ALTER TABLE system_settings ADD COLUMN backup_bot_kind VARCHAR(20) DEFAULT 'database'",
    ]
    added = 0
    for sql in alters:
        try:
            db.session.execute(text(sql))
            db.session.commit()
            added += 1
        except Exception:
            db.session.rollback()          # ستون از قبل وجود دارد
    return added


def ensure_payroll_columns() -> dict:
    """ستون‌های گردش‌کار فیش حقوقی + یکتایی «یک فیش برای هر نفر در هر دوره».

    نصب‌های قدیمی این ستون‌ها را ندارند و SQLite با create_all آن‌ها را
    اضافه نمی‌کند. ایندکس یکتا بعد از پاک‌سازی تکراری‌ها ساخته می‌شود:
    از فیش‌های تکراریِ همان دوره، فیشِ پرداخت‌شده (یا بزرگ‌ترین id) نگه
    داشته می‌شود و بقیه «ابطال» می‌خورند (حذف فیزیکی نمی‌شوند تا سابقه بماند).
    """
    result = {'added': 0, 'cancelled_duplicates': 0, 'unique_index': False, 'error': None}
    alters = [
        "ALTER TABLE payslips ADD COLUMN approved_at DATETIME",
        "ALTER TABLE payslips ADD COLUMN paid_by INTEGER REFERENCES users (id)",
        "ALTER TABLE payslips ADD COLUMN cashbox_id INTEGER REFERENCES cashboxes (id)",
        "ALTER TABLE payslips ADD COLUMN cancel_reason VARCHAR(255)",
        "ALTER TABLE payslips ADD COLUMN cancelled_at DATETIME",
        "ALTER TABLE payslips ADD COLUMN cancelled_by INTEGER REFERENCES users (id)",
    ]
    for sql in alters:
        try:
            db.session.execute(text(sql))
            db.session.commit()
            result['added'] += 1
        except Exception:
            db.session.rollback()          # ستون از قبل وجود دارد

    # ۱) لغو فیش‌های تکراریِ همان شخص و همان دوره (به‌جز نسخه‌ای که نگه داشته می‌شود)
    try:
        from models.finance import Payslip
        rows = (db.session.query(Payslip.person_type, Payslip.person_id, Payslip.period)
                .filter(Payslip.period.isnot(None))
                .group_by(Payslip.person_type, Payslip.person_id, Payslip.period)
                .having(db.func.count(Payslip.id) > 1).all())
        keep_status_order = {'paid': 0, 'approved': 1, 'draft': 2, 'cancelled': 3}
        for person_type, person_id, period in rows:
            duplicates = (Payslip.query
                          .filter_by(person_type=person_type, person_id=person_id, period=period)
                          .order_by(Payslip.id.desc()).all())
            keep = sorted(duplicates,
                          key=lambda p: (keep_status_order.get(p.status, 4), -p.id))[0]
            for old in duplicates:
                if old.id == keep.id or old.status == 'cancelled':
                    continue
                old.status = 'cancelled'
                old.cancel_reason = 'ابطال خودکار: فیش تکراری برای همین دوره (اصلاح ساختاری)'
                old.cancelled_at = datetime.utcnow()
                result['cancelled_duplicates'] += 1
        if result['cancelled_duplicates']:
            db.session.commit()
    except Exception as exc:                                  # pragma: no cover
        db.session.rollback()
        result['error'] = f'dedupe: {exc}'

    # ۲) ایندکس یکتای جزئی — فقط فیش‌های غیرمبتل به ابطال
    try:
        db.session.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS ux_payslip_person_period "
            "ON payslips (person_type, person_id, period) WHERE status != 'cancelled'"
        ))
        db.session.commit()
        result['unique_index'] = True
    except Exception as exc:                                  # pragma: no cover
        db.session.rollback()
        result['error'] = (result['error'] or '') + f' index: {exc}'
    return result


def ensure_accounting_columns() -> int:
    """ستون‌های تازه جدول دوره مالی (قفل شدن واقعی دوره بسته)."""
    alters = [
        "ALTER TABLE fiscal_periods ADD COLUMN closed_by_user BOOLEAN DEFAULT 0",
        "ALTER TABLE journal_entries ADD COLUMN confirmed_at DATETIME",
        "ALTER TABLE journal_entries ADD COLUMN approved_at DATETIME",
    ]
    added = 0
    for sql in alters:
        try:
            db.session.execute(text(sql))
            db.session.commit()
            added += 1
        except Exception:
            db.session.rollback()
    return added


def ensure_finance_columns() -> int:
    """ستون‌های ابطال/مرجوعیِ پرداخت (`Payment`).

    مدل این فیلدها را داشت ولی هیچ مسیر ابطال وجود نداشت؛ با افزودن
    `cancel_reason`/`refunded_amount`، ابطال هم ردپا می‌گذارد و هم مبلغ
    درست را به صندوق برمی‌گرداند. مثل بقیه مهاجرت‌ها: فقط ADD COLUMN، هیچ
    داده‌ای بازنویسی/حذف نمی‌شود و اجرای دوباره بی‌ضرر است.
    """
    alters = [
        "ALTER TABLE payments ADD COLUMN cancel_reason TEXT",
        "ALTER TABLE payments ADD COLUMN refunded_amount FLOAT DEFAULT 0",
    ]
    added = 0
    for sql in alters:
        try:
            db.session.execute(text(sql))
            db.session.commit()
            added += 1
        except Exception:
            db.session.rollback()
    return added
