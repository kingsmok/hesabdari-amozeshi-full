"""ابزارهای امن و مستقل از مسیر برای پایش و نگهداری دیتابیس."""
from __future__ import annotations

import os

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
