"""
سیستم جامع مدیریت آموزشگاه - Academy Manager Pro
نسخه ۱.۰
"""
import os
import sys
from flask import Flask
from extensions import db, login_manager, migrate, csrf
from utils.jalali import parse_jalali_date, gregorian_to_jalali


def create_app():
    app = Flask(__name__)
    
    # مسیر اصلی — سازگار با PyInstaller
    if getattr(sys, 'frozen', False):
        base_dir = os.path.dirname(sys.executable)
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Configuration — بهینه‌سازی شده برای داده‌های بزرگ
    from config import load_config, get_database_uri, get_engine_options
    config = load_config()
    
    app.config['SECRET_KEY'] = 'academy-manager-secret-key-2026'
    app.config['SQLALCHEMY_DATABASE_URI'] = get_database_uri(config)
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = get_engine_options(config)
    app.config['UPLOAD_FOLDER'] = os.path.join(base_dir, 'static', 'uploads')
    app.config['BACKUP_FOLDER'] = os.path.join(base_dir, 'backups')
    app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB max
    
    # Initialize extensions
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'لطفاً وارد شوید'
    migrate.init_app(app, db)
    csrf.init_app(app)
    
    # Create upload directories
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(app.config['BACKUP_FOLDER'], exist_ok=True)
    
    # Register blueprints
    from routes.auth import auth_bp
    from routes.dashboard import dashboard_bp
    from routes.students import students_bp
    from routes.teachers import teachers_bp
    from routes.classes import classes_bp
    from routes.registration import registration_bp
    from routes.attendance import attendance_bp
    from routes.exams import exams_bp
    from routes.finance import finance_bp
    from routes.accounting import accounting_bp
    from routes.settings import settings_bp
    from routes.reports import reports_bp
    from routes.messaging import messaging_bp
    from routes.additional import certificates_bp, complaints_bp, surveys_bp, tickets_bp, goals_bp, analytics_bp
    from routes.features import features_bp
    from routes.features2 import features2_bp
    from routes.new_features import new_features_bp
    from routes.final import final_bp
    from routes.demo import demo_bp
    from routes.settings_panel import settings_panel_bp
    from routes.network_info import network_bp
    from routes.setup import setup_bp
    from routes.payroll import payroll_bp
    from routes.tax import tax_bp
    from routes.permissions import perms_bp
    from routes.teacher_portal import teacher_bp
    from routes.bot_panel import bot_panel_bp
    
    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(students_bp, url_prefix='/students')
    app.register_blueprint(teachers_bp, url_prefix='/teachers')
    app.register_blueprint(classes_bp, url_prefix='/classes')
    app.register_blueprint(registration_bp, url_prefix='/registration')
    app.register_blueprint(attendance_bp, url_prefix='/attendance')
    app.register_blueprint(exams_bp, url_prefix='/exams')
    app.register_blueprint(finance_bp, url_prefix='/finance')
    app.register_blueprint(accounting_bp, url_prefix='/accounting')
    app.register_blueprint(settings_bp, url_prefix='/settings')
    app.register_blueprint(reports_bp, url_prefix='/reports')
    app.register_blueprint(messaging_bp, url_prefix='/messaging')
    app.register_blueprint(certificates_bp, url_prefix='/certificates')
    app.register_blueprint(complaints_bp, url_prefix='/complaints')
    app.register_blueprint(surveys_bp, url_prefix='/surveys')
    app.register_blueprint(tickets_bp, url_prefix='/tickets')
    app.register_blueprint(goals_bp, url_prefix='/goals')
    app.register_blueprint(analytics_bp, url_prefix='/analytics')
    app.register_blueprint(features_bp)
    app.register_blueprint(features2_bp)
    app.register_blueprint(new_features_bp)
    app.register_blueprint(final_bp)
    app.register_blueprint(demo_bp)
    app.register_blueprint(settings_panel_bp, url_prefix='/panel')
    app.register_blueprint(network_bp)
    app.register_blueprint(setup_bp)
    app.register_blueprint(payroll_bp)
    app.register_blueprint(tax_bp)
    app.register_blueprint(perms_bp, url_prefix='/perms')
    app.register_blueprint(teacher_bp)
    app.register_blueprint(bot_panel_bp)
    
    # ══ پشتیبان‌گیری خودکار (Backup Scheduler) ══
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from routes.features import perform_backup
        
        def _scheduled_backup():
            try:
                with app.app_context():
                    from routes.features import perform_backup
                    result = perform_backup()
                    print('[BACKUP] Auto-backup completed:', result)
            except Exception as exc:
                print('[BACKUP] Auto-backup error:', exc)
        
        scheduler = BackgroundScheduler()
        # اجرای اولیه بعد از ۱ دقیقه (برای تست) و سپس هر ۲۴ ساعت پیش‌فرض
        # کاربر می‌تواند از /settings/backup بازه را تغییر دهد
        scheduler.add_job(_scheduled_backup, 'interval', hours=24, id='auto_backup', replace_existing=True)
        scheduler.start()
        print('[SCHEDULER] Auto-backup scheduler started.')
    except Exception as exc:
        print('[SCHEDULER] Scheduler not started:', exc)
    
    # فقط خود endpoint تلگرام از CSRF معاف است؛ فرم‌های مالی و مدیریتی
    # داخل new_features باید همچنان محافظت شوند.
    
    # Favicon
    @app.route('/favicon.ico')
    def favicon():
        from flask import send_from_directory
        return send_from_directory(os.path.join(app.root_path, 'static', 'images'), 'favicon.ico', mimetype='image/x-icon')

    # Context processors
    @app.context_processor
    def inject_globals():
        from models.system import SystemSettings
        settings_obj = SystemSettings.query.first()
        return {
            'system_settings': settings_obj,
            'app_name': settings_obj.academy_name if settings_obj else 'سیستم مدیریت آموزشگاه',
        }
    
    # Jinja2 filters
    @app.template_filter('from_json')
    def from_json_filter(value):
        """تبدیل JSON رشته به شی پایتون"""
        import json
        try:
            return json.loads(value) if value else []
        except (json.JSONDecodeError, TypeError):
            return []

    @app.template_filter('to_jalali')
    def to_jalali_filter(date):
        """تبدیل تاریخ میلادی به شمسی — فرمت: 1405/01/16"""
        if date is None:
            return ''
        try:
            import jdatetime
            # اگر datetime بود، تبدیل به date
            if hasattr(date, 'date'):
                date = date.date()
            # اگر رشته بود، تبدیل کن
            if isinstance(date, str):
                from datetime import datetime as dt
                try:
                    date = dt.strptime(date[:10], '%Y-%m-%d').date()
                except:
                    return date
            j = jdatetime.date.fromgregorian(date=date)
            return f'{j.year}/{j.month:02d}/{j.day:02d}'
        except Exception as e:
            return str(date) if date else ''
    
    @app.template_filter('currency')
    def currency_filter(amount):
        if amount is None:
            return '0'
        try:
            return '{:,.0f}'.format(float(amount))
        except:
            return '0'
    
    @app.template_filter('to_jalali_full')
    def to_jalali_full_filter(date):
        """تبدیل تاریخ به شمسی با نام ماه — مثال: ۱۶ فروردین ۱۴۰۵"""
        if date is None:
            return ''
        try:
            import jdatetime
            if hasattr(date, 'date'):
                date = date.date()
            if isinstance(date, str):
                from datetime import datetime as dt
                try:
                    date = dt.strptime(date[:10], '%Y-%m-%d').date()
                except:
                    return date
            j = jdatetime.date.fromgregorian(date=date)
            months = ['', 'فروردین', 'اردیبهشت', 'خرداد', 'تیر', 'مرداد', 'شهریور',
                      'مهر', 'آبان', 'آذر', 'دی', 'بهمن', 'اسفند']
            return f'{j.day} {months[j.month]} {j.year}'
        except:
            return str(date) if date else ''
            return str(date)
    
    # تابع کمکی تبدیل تاریخ شمسی به میلادی در route ها
    @app.template_global()
    def parse_jalali(date_str):
        return parse_jalali_date(date_str)
    
    @app.template_global()
    def can_edit(module='settings'):
        """آیا کاربر می‌تواند ویرایش کند؟"""
        from flask_login import current_user
        if not current_user.is_authenticated:
            return False
        if current_user.is_admin:
            return True
        return current_user.has_permission(module, 'edit')
    
    @app.template_global()
    def can_delete(module='settings'):
        """آیا کاربر می‌تواند حذف کند؟"""
        from flask_login import current_user
        if not current_user.is_authenticated:
            return False
        if current_user.is_admin:
            return True
        return current_user.has_permission(module, 'delete')
    
    @app.template_global()
    def can_create(module='settings'):
        """آیا کاربر می‌تواند ایجاد کند؟"""
        from flask_login import current_user
        if not current_user.is_authenticated:
            return False
        if current_user.is_admin:
            return True
        return current_user.has_permission(module, 'create')
    
    @app.template_global()
    def is_admin():
        """آیا کاربر مدیر کل است؟"""
        from flask_login import current_user
        return current_user.is_authenticated and current_user.is_admin
    
    @app.template_global()
    def get_user_menu_items():
        """دریافت منوهای قابل نمایش برای کاربر فعلی"""
        from flask_login import current_user
        if not current_user.is_authenticated:
            return []
        
        MENU_MAP = {
            'dashboard': None,
            'students': 'students',
            'registration': 'registration',
            'courses': 'courses',
            'classes': 'classes',
            'teachers': 'teachers',
            'attendance': 'attendance',
            'exams': 'exams',
            'finance': 'finance',
            'accounting': 'accounting',
            'payroll': 'payroll',
            'tax': 'tax',
            'reports': 'reports',
            'messaging': 'messaging',
            'settings': 'settings',
            'certificates': 'certificates',
            'analytics': 'reports',
        }
        
        if current_user.is_admin:
            return list(MENU_MAP.keys())
        
        allowed = []
        for menu_key, module in MENU_MAP.items():
            if module is None:
                allowed.append(menu_key)
            elif current_user.has_module_access(module):
                allowed.append(menu_key)
        
        return allowed
    
    # بهینه‌سازی: فقط یکبار اجرا شود
    with app.app_context():
        if not hasattr(app, '_db_initialized'):
            # ابتدا تمام مدل‌ها رو import کن
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
            import models.bot
            
            db.create_all()
            create_default_data()
            # اصلاح خودکار تاریخ‌های شمسی که در نسخه‌های قدیمی به‌اشتباه
            # مستقیماً در ستون میلادی ذخیره شده بودند (عملیات idempotent است).
            from utils.database_tools import repair_legacy_jalali_dates
            repaired_dates = repair_legacy_jalali_dates()
            if repaired_dates:
                app.logger.warning('%s legacy Jalali date values were repaired', repaired_dates)
            app._db_initialized = True

        # ربات بله در حالت Long Polling کار می‌کند و به دامنه عمومی/وب‌هوک نیاز ندارد.
        from utils.bot_services import start_bale_polling_if_configured
        start_bale_polling_if_configured(app)
    
    return app


def create_default_data():
    """Create default admin user and system settings"""
    # ابتدا تمام مدل‌ها رو import کن
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
    
    from models.user import User, Role, Permission, RolePermission
    from models.system import SystemSettings, Branch
    
    # Create default roles
    if Role.query.count() == 0:
        roles_data = [
            {'name': 'مدیر کل', 'description': 'دسترسی کامل به تمام بخش‌ها', 'is_admin': True},
            {'name': 'مدیر آموزشگاه', 'description': 'مدیریت آموزشی و مالی', 'is_admin': False},
            {'name': 'منشی', 'description': 'ثبت‌نام، هنرجو، حضور و غیاب', 'is_admin': False},
            {'name': 'حسابدار', 'description': 'فقط بخش مالی و حسابداری', 'is_admin': False},
            {'name': 'مدرس', 'description': 'حضور و غیاب کلاس‌های خود', 'is_admin': False},
            {'name': 'مسئول آموزش', 'description': 'کلاس‌ها، آزمون‌ها، مدرسین', 'is_admin': False},
        ]
        
        for rd in roles_data:
            role = Role(**rd)
            db.session.add(role)
        db.session.commit()
        
        # تنظیم دسترسی‌های پیش‌فرض
        default_perms = {
            'مدیر آموزشگاه': {
                'students': ['view', 'create', 'edit', 'delete'],
                'registration': ['view', 'create', 'edit', 'delete'],
                'classes': ['view', 'create', 'edit', 'delete'],
                'teachers': ['view', 'create', 'edit'],
                'attendance': ['view', 'create', 'edit'],
                'exams': ['view', 'create', 'edit'],
                'courses': ['view', 'create', 'edit'],
                'finance': ['view'],
                'reports': ['view'],
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
                'tax': ['view', 'create'],
                'reports': ['view'],
            },
            'مدرس': {
                'attendance': ['view', 'create', 'edit'],
                'exams': ['view', 'create', 'edit'],
                'classes': ['view'],
                'students': ['view'],
            },
            'مسئول آموزش': {
                'classes': ['view', 'create', 'edit', 'delete'],
                'teachers': ['view', 'create', 'edit'],
                'exams': ['view', 'create', 'edit'],
                'courses': ['view', 'create', 'edit'],
                'attendance': ['view', 'create', 'edit'],
                'students': ['view'],
                'registration': ['view'],
            },
        }
        
        for role_name, modules in default_perms.items():
            role = Role.query.filter_by(name=role_name).first()
            if not role:
                continue
            for module, actions in modules.items():
                for action in actions:
                    perm = Permission.query.filter_by(module=module, action=action).first()
                    if not perm:
                        perm = Permission(module=module, action=action, description=f'{action} {module}')
                        db.session.add(perm)
                        db.session.flush()
                    rp = RolePermission(role_id=role.id, permission_id=perm.id)
                    db.session.add(rp)
        
        db.session.commit()
    
    # NOTE: Default admin creation removed for security. Use setup wizard (setup.py) to create first admin.
    # Create default system settings
    if SystemSettings.query.count() == 0:
        settings_obj = SystemSettings(
            academy_name='آموزشگاه نمونه',
            academy_code='AC-001',
            phone='021-12345678',
            address='تهران، خیابان ولیعصر',
            current_year='1405',
            current_term='بهار'
        )
        db.session.add(settings_obj)
        db.session.commit()
    
    # Create main branch
    if Branch.query.count() == 0:
        branch = Branch(
            name='شعبه مرکزی',
            code='BR-001',
            address='آدرس شعبه مرکزی',
            phone='021-12345678',
            is_main=True
        )
        db.session.add(branch)
        db.session.commit()

    # دسته‌بندی‌های پایه هزینه برای نصب‌های جدید
    from models.finance import ExpenseCategory
    if ExpenseCategory.query.count() == 0:
        default_expense_categories = [
            ('اجاره', 'EXP-01'),
            ('حقوق و دستمزد', 'EXP-02'),
            ('قبوض و خدمات', 'EXP-03'),
            ('تجهیزات و ملزومات', 'EXP-04'),
            ('تبلیغات', 'EXP-05'),
            ('تعمیر و نگهداری', 'EXP-06'),
            ('حمل و نقل', 'EXP-07'),
            ('سایر هزینه‌ها', 'EXP-99'),
        ]
        db.session.add_all([
            ExpenseCategory(name=name, code=code, is_active=True)
            for name, code in default_expense_categories
        ])
        db.session.commit()


if __name__ == '__main__':
    app = create_app()
    # reloader چند پردازه می‌سازد و برای Long Polling بله مناسب نیست.
    app.run(debug=False, host='0.0.0.0', port=5000, use_reloader=False)
