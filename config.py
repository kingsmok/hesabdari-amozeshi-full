"""
تنظیمات سیستم — پشتیبانی از SQLite, MySQL, PostgreSQL
بهینه‌سازی شده برای داده‌های بزرگ
"""
import os
import sys
import json

# مسیر اصلی — سازگار با PyInstaller
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

CONFIG_FILE = os.path.join(BASE_DIR, 'settings.json')


def load_config():
    """بارگذاری تنظیمات از فایل"""
    default = {
        'database': {
            'type': 'sqlite',  # sqlite, mysql, postgresql
            'sqlite_path': 'instance/academy.db',
            'mysql_host': 'localhost',
            'mysql_port': 3306,
            'mysql_user': 'root',
            'mysql_password': '',
            'mysql_database': 'academy_manager',
            'postgresql_host': 'localhost',
            'postgresql_port': 5432,
            'postgresql_user': 'postgres',
            'postgresql_password': '',
            'postgresql_database': 'academy_manager',
            'pool_size': 10,
            'max_overflow': 20,
            'pool_recycle': 3600,
        },
        'server': {
            'host': '0.0.0.0',
            'port': 5000,
            'debug': False,
        },
        'app': {
            'name': 'آموزشگاه نمونه',
            'version': '1.0.0',
            'page_size': 25,  # تعداد ردیف در هر صفحه
        }
    }
    
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                saved = json.load(f)
            for key in default:
                if key in saved:
                    if isinstance(default[key], dict):
                        default[key].update(saved[key])
                    else:
                        default[key] = saved[key]
        except:
            pass
    
    return default


def save_config(config):
    """ذخیره تنظیمات"""
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


def get_database_uri(config=None):
    """ساخت URI اتصال دیتابیس"""
    if config is None:
        config = load_config()
    
    db = config['database']
    db_type = db.get('type', 'sqlite')
    
    if db_type == 'postgresql':
        return f"postgresql://{db['postgresql_user']}:{db['postgresql_password']}@{db['postgresql_host']}:{db['postgresql_port']}/{db['postgresql_database']}"
    
    elif db_type == 'mysql':
        return f"mysql+pymysql://{db['mysql_user']}:{db['mysql_password']}@{db['mysql_host']}:{db['mysql_port']}/{db['mysql_database']}?charset=utf8mb4"
    
    else:  # sqlite
        db_path = db.get('sqlite_path', 'instance/academy.db')
        if not os.path.isabs(db_path):
            db_path = os.path.join(BASE_DIR, db_path)
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        return f'sqlite:///{db_path}'


def get_engine_options(config=None):
    """تنظیمات موتور دیتابیس برای عملکرد بهتر"""
    if config is None:
        config = load_config()
    
    db = config['database']
    db_type = db.get('type', 'sqlite')
    
    options = {}
    
    if db_type == 'postgresql':
        options = {
            'pool_size': db.get('pool_size', 10),
            'max_overflow': db.get('max_overflow', 20),
            'pool_recycle': db.get('pool_recycle', 3600),
            'pool_pre_ping': True,
            'echo': False,
        }
    elif db_type == 'mysql':
        options = {
            'pool_size': db.get('pool_size', 10),
            'max_overflow': db.get('max_overflow', 20),
            'pool_recycle': db.get('pool_recycle', 3600),
            'pool_pre_ping': True,
        }
    else:  # sqlite
        options = {
            'connect_args': {'check_same_thread': False},
        }
    
    return options


def test_database_connection(config=None):
    """تست اتصال دیتابیس"""
    if config is None:
        config = load_config()
    
    db = config['database']
    db_type = db.get('type', 'sqlite')
    
    if db_type == 'postgresql':
        try:
            import psycopg2
            conn = psycopg2.connect(
                host=db['postgresql_host'],
                port=int(db['postgresql_port']),
                user=db['postgresql_user'],
                password=db['postgresql_password'],
                database=db['postgresql_database'],
                connect_timeout=5
            )
            conn.close()
            return True, 'اتصال به PostgreSQL موفق بود'
        except ImportError:
            return False, 'psycopg2 نصب نیست. اجرا کنید: pip install psycopg2-binary'
        except Exception as e:
            return False, f'خطا: {str(e)}'
    
    elif db_type == 'mysql':
        try:
            import pymysql
            conn = pymysql.connect(
                host=db['mysql_host'],
                port=int(db['mysql_port']),
                user=db['mysql_user'],
                password=db['mysql_password'],
                database=db['mysql_database'],
                connect_timeout=5
            )
            conn.close()
            return True, 'اتصال به MySQL موفق بود'
        except ImportError:
            return False, 'pymysql نصب نیست: pip install pymysql'
        except Exception as e:
            return False, f'خطا: {str(e)}'
    
    else:
        db_path = db.get('sqlite_path', 'instance/academy.db')
        if not os.path.isabs(db_path):
            db_path = os.path.join(BASE_DIR, db_path)
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        return True, f'SQLite: {db_path}'


def create_database_if_not_exists(config=None):
    """ساخت دیتابیس اگر وجود نداشت"""
    if config is None:
        config = load_config()
    
    db = config['database']
    db_type = db.get('type', 'sqlite')
    
    if db_type == 'postgresql':
        try:
            import psycopg2
            from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
            conn = psycopg2.connect(
                host=db['postgresql_host'],
                port=int(db['postgresql_port']),
                user=db['postgresql_user'],
                password=db['postgresql_password'],
                connect_timeout=5
            )
            conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
            cursor = conn.cursor()
            cursor.execute(f"SELECT 1 FROM pg_database WHERE datname = '{db['postgresql_database']}'")
            exists = cursor.fetchone()
            if not exists:
                cursor.execute(f'CREATE DATABASE "{db["postgresql_database"]}" WITH ENCODING = \'UTF8\'')
            conn.close()
            return True, f"PostgreSQL database '{db['postgresql_database']}' ready"
        except Exception as e:
            return False, str(e)
    
    elif db_type == 'mysql':
        try:
            import pymysql
            conn = pymysql.connect(
                host=db['mysql_host'],
                port=int(db['mysql_port']),
                user=db['mysql_user'],
                password=db['mysql_password'],
                connect_timeout=5
            )
            cursor = conn.cursor()
            cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{db['mysql_database']}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
            conn.commit()
            conn.close()
            return True, f"MySQL database '{db['mysql_database']}' ready"
        except Exception as e:
            return False, str(e)
    
    return True, 'SQLite - no creation needed'
