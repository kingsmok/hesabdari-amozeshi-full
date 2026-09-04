"""Extensions - avoid circular imports"""
import sqlite3

from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFProtect
from sqlalchemy import event
from sqlalchemy.engine import Engine

db = SQLAlchemy()
login_manager = LoginManager()
migrate = Migrate()
csrf = CSRFProtect()


@event.listens_for(Engine, 'connect')
def _tune_sqlite_connection(dbapi_connection, connection_record):
    """حالت WAL روی SQLite؛ روی MySQL/PostgreSQL هیچ کاری نمی‌کند.

    با حالت پیش‌فرض (rollback journal)، هر خوانندهٔ طولانی نوشتن را قفل می‌کند و
    برنامه با «database is locked» جواب کاربر را می‌دهد — اینجا نوشتن‌ها از
    پشتیبان‌گیری خودکار و درخواست‌های همزمان می‌آید. WAL خواندن و نوشتن را
    همزمان ممکن می‌کند و `busy_timeout` (در config) منتظر ماندن را کامل می‌کند.

    پشتیبان‌گیری با این حالت امن است: `utils.database_tools.sqlite_backup` از
    Backup API استفاده می‌کند، نه کپی فایل، پس محتوای WAL هم داخل بسته می‌نشیند.
    """
    if not isinstance(dbapi_connection, sqlite3.Connection):
        return
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute('PRAGMA journal_mode=WAL')
        cursor.execute('PRAGMA synchronous=NORMAL')
    except Exception:
        # دیتابیسی که WAL را پشتیبانی نمی‌کند (شبکه‌های فایل قدیمی) نباید
        # باعث شود برنامه بالا نیاید؛ همان حالت قبلی ادامه می‌یابد.
        pass
    finally:
        cursor.close()
