"""
سیستم جامع مدیریت آموزشگاه - Academy Manager Pro
نسخه ۱.۰
"""
import os
import time

from flask import Flask, g, render_template, request, url_for
from extensions import db, login_manager, migrate, csrf
from utils.jalali import parse_jalali_date


def create_app():
    # کانفیگ مرکزی: بررسی سازگاری نسخه‌ها + بارگذاری تنظیمات + اعمال روی اپ
    # (قبلاً این‌ها در دو نقطهٔ app.py و config.py جدا انجام می‌شد — SRP/DRY)
    from utils.config_loader import build_config, apply_to_app
    config, paths = build_config()
    app = Flask(__name__)
    apply_to_app(app, config, paths)
    base_dir = paths['base_dir']
    
    # Initialize extensions
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'لطفاً وارد شوید'
    migrate.init_app(app, db)
    csrf.init_app(app)

    # ── لاگ مرکزی (جایگزین print های قبلی) ──────────────────────────────
    from utils.logging_config import configure_app_logging
    configure_app_logging(app)
    _log = app.logger

    # ── هدرهای امنیتی + لاگ درخواست‌ها (هر request: متد/مسیر/کد/زمان) ─────
    @app.before_request
    def _request_started():
        g._request_started = time.monotonic()

    @app.after_request
    def _security_and_access_log(response):
        # هدرهای پایهٔ امنیت؛ CSP عمداً اضافه نشده (قالب‌ها استایل inline دارند
        # و CSP سخت‌گیرانه کل UI را می‌شکند)
        response.headers.setdefault('X-Content-Type-Options', 'nosniff')
        response.headers.setdefault('X-Frame-Options', 'SAMEORIGIN')
        response.headers.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
        response.headers.setdefault('X-Permitted-Cross-Domain-Policies', 'none')
        response.headers.setdefault('Permissions-Policy',
                                    'camera=(), microphone=(), geolocation=()')
        # لاگ گذر درخواست‌های نوشتنی و خطاها (GET های عادی را شلوغ نمی‌کنیم)
        if request.method != 'GET' or response.status_code >= 500:
            duration = None
            try:
                started = getattr(g, '_request_started', None)
                if started is not None:
                    duration = time.monotonic() - started
                _log.info('%s %s -> %s%s',
                          request.method, request.path, response.status_code,
                          f' ({duration * 1000:.0f}ms)' if duration is not None else '')
            except Exception:
                pass
        return response

    # Create upload directories
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(app.config['BACKUP_FOLDER'], exist_ok=True)
    
    # ══ سامانه لایسنس — پیش از ثبت Blueprintها ══
    from license_client import init_license
    init_license(app)
    
    # Register blueprints
    from routes.auth import auth_bp
    from routes.license import license_bp
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
    from routes.backup_center import backup_center_bp
    
    app.register_blueprint(auth_bp)
    app.register_blueprint(license_bp)
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
    app.register_blueprint(backup_center_bp)

    # ══ نگهبان سراسری دسترسی ══
    # فهرست منو به‌تنهایی کنترل دسترسی نیست؛ هر مسیر نوشتن باید در خود مسیر هم
    # بررسی شود. این before_request بر اساس پیشوند مسیر، ماژول لازم را تعیین و
    # در صورت نبود دسترسی، ۴۰۳ (یا redirect با پیام) برمی‌گرداند.
    from utils.access_policy import init_access_guard
    init_access_guard(app)

    # ══ پشتیبان‌گیری خودکار (Backup Scheduler) ══
    # هر ساعت بررسی می‌شود؛ خودِ سرویس بر اساس تنظیمات سیستم
    # (auto_backup / backup_interval_hours / max_backups) تصمیم می‌گیرد.
    _scheduler_off = (os.environ.get('ACADEMY_DISABLE_SCHEDULER') == '1'
                      or app.config.get('DISABLE_SCHEDULER'))
    if not _scheduler_off:
      try:
        from apscheduler.schedulers.background import BackgroundScheduler

        def _scheduled_backup():
            try:
                with app.app_context():
                    from license_client import has_feature
                    if not has_feature('backup'):
                        # تسک زمان‌بندی‌شده‌ی یک بخش قفل‌شده اجرا نمی‌شود
                        app.logger.info('[BACKUP] Skipped — بخش پشتیبان‌گیری در لایسنس فعال نیست')
                        return
                    from utils.backup_service import run_scheduled_backup
                    app.logger.info('[BACKUP] %s', run_scheduled_backup())
            except Exception as exc:                       # noqa: BLE001
                app.logger.exception('[BACKUP] Auto-backup error: %s', exc)

        scheduler = BackgroundScheduler()
        scheduler.add_job(_scheduled_backup, 'interval', hours=1,
                          id='auto_backup', replace_existing=True)
        scheduler.start()
        app.logger.info('[SCHEDULER] Auto-backup scheduler started.')
      except Exception as exc:                             # noqa: BLE001
        app.logger.warning('[SCHEDULER] Scheduler not started: %s', exc)
    else:
        app.logger.info('[SCHEDULER] Skipped (DISABLE_SCHEDULER) — مناسب آزمون‌ها')
    
    # فقط خود endpoint تلگرام از CSRF معاف است؛ فرم‌های مالی و مدیریتی
    # داخل new_features باید همچنان محافظت شوند.
    
    # Favicon
    @app.route('/favicon.ico')
    def favicon():
        from flask import send_from_directory
        return send_from_directory(os.path.join(app.root_path, 'static', 'images'), 'favicon.ico', mimetype='image/x-icon')

    # ─────────── استاتیک نسخه‌دهی‌شده (cache-busting) ───────────
    from functools import lru_cache as _lru_cache

    @_lru_cache(maxsize=512)
    def _asset_version(filename):
        """امضای کوتاه فایل برای ?v= — با تغییر فایل، کش خودبه‌خود می‌سوزد."""
        try:
            path = os.path.join(app.root_path, 'static', filename.replace('\\', os.sep))
            stat = os.stat(path)
            return f'{int(stat.st_mtime)}-{stat.st_size:x}'
        except Exception:
            return str(app.config.get('ASSET_STAMP', '1'))

    @app.template_global()
    def asset(filename, **extra):
        """`url_for('static', ...)` با نسخه خودکار؛ برای CSS/JS/آیکون‌ها."""
        kwargs = {'filename': filename, 'v': _asset_version(filename)}
        kwargs.update(extra)
        return url_for('static', **kwargs)

    # ─────────── PWA: manifest از تنظیمات آموزشگاه ───────────
    @app.route('/manifest.webmanifest')
    def manifest():
        """manifest پویا.

        فایل ایستا `static/manifest.json` نام یک مشتری خاص («آموزشگاه رهسا») را
        هاردکد داشت و فقط یک آیکون SVG معرفی می‌کرد؛ Android برای نصب PNG
        ۱۹۲/۵۱ می‌خواهد و `orientation: portrait` تبلت/دسکتاپ را قفل می‌کرد.
        """
        from flask import jsonify
        from models.system import SystemSettings
        settings_obj = SystemSettings.query.first()
        name = (getattr(settings_obj, 'academy_name', None) or 'سیستم مدیریت آموزشگاه').strip()
        payload = {
            'name': name,
            'short_name': (name[:18] + '…') if len(name) > 18 else name,
            'description': 'نرم‌افزار حسابداری و مدیریت آموزشگاه',
            'start_url': '/',
            'scope': '/',
            'display': 'standalone',
            'background_color': '#0a1628',
            'theme_color': '#0d47a1',
            'dir': 'rtl',
            'lang': 'fa',
            'icons': [
                {'src': asset('images/icons/icon-192.png'), 'sizes': '192x192', 'type': 'image/png', 'purpose': 'any'},
                {'src': asset('images/icons/icon-512.png'), 'sizes': '512x512', 'type': 'image/png', 'purpose': 'any'},
                {'src': asset('images/icons/icon-maskable-192.png'), 'sizes': '192x192', 'type': 'image/png', 'purpose': 'maskable'},
                {'src': asset('images/icons/icon-maskable-512.png'), 'sizes': '512x512', 'type': 'image/png', 'purpose': 'maskable'},
            ],
            'shortcuts': [
                {'name': 'ثبت پرداخت', 'url': '/finance/payments/new', 'description': 'پرداخت شهریه'},
                {'name': 'جستجوی هنرجو', 'url': '/students', 'description': 'لیست هنرجویان'},
            ],
        }
        response = jsonify(payload)
        response.mimetype = 'application/manifest+json'
        response.headers['Cache-Control'] = 'no-cache'
        return response

    # ─────────── PWA: صفحه آفلاین ───────────
    @app.route('/offline')
    def offline():
        """صفحه‌ای که service worker هنگام نبود سرور نشان می‌دهد."""
        return render_template('base/offline.html'), 200

    @app.route('/sw.js')
    def service_worker():
        """سرویس‌ورکر از ریشه: فایل داخل /static فقط می‌تواند همان پوشه را
        کنترل کند، مگر هدر `Service-Worker-Allowed` — پس مسیر جدا و بی‌هدر
        تمیزتر است. همچنین no-cache تا به‌روزرسانی پوسته سریع انجام شود."""
        from flask import make_response, send_from_directory
        response = make_response(send_from_directory(
            os.path.join(app.root_path, 'static'), 'sw.js', mimetype='application/javascript'))
        response.headers['Service-Worker-Allowed'] = '/'
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Content-Type'] = 'application/javascript; charset=utf-8'
        return response

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
        except Exception:
            return str(date) if date else ''
    
    @app.template_filter('jalali_period')
    def jalali_period_filter(value):
        """برچسب خوانا برای دوره شمسی: 1405/06 → شهریور 1405"""
        from utils.jalali import jalali_period_label
        return jalali_period_label(value)

    @app.template_filter('currency')
    def currency_filter(amount):
        if amount is None or amount == '':
            return '0'
        try:
            return '{:,.0f}'.format(float(amount))
        except (TypeError, ValueError):
            # بلعیدن خطا و چاپ «۰» باعث می‌شد باگ قالب (مثل فیلد اشتباه در صفحه
            # قراردادها) بی‌صدا «صفر» نشان بدهد؛ حالا لاگ می‌شود و در حالت DEBUG
            # همان‌جا استثنا می‌دهد
            if app.debug:
                raise
            app.logger.warning('فیلتر currency: مقدار نامعتبر برای مبلغ: %r', amount)
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
    
    # ── مدیریت جامع خطاها: ثبت traceback + صفحهٔ کاربرپسند با کد پیگیری ──
    from utils.error_handling import register_global_handlers
    register_global_handlers(app)

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
        
        # بهینه‌سازی پرفورمنس: دسترسی‌های نقش با یک کوئری؛ قبل از این برای هر
        # آیتم منو (~۱۵ مورد) یک کوئری `has_module_access` زده می‌شد.
        from models.user import Permission, RolePermission
        allowed_modules = {
            row[0]
            for row in db.session.query(Permission.module)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .filter(RolePermission.role_id == current_user.role_id)
            .distinct().all()
        }
        allowed = []
        for menu_key, module in MENU_MAP.items():
            if module is None:
                allowed.append(menu_key)
            elif module in allowed_modules:
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
            from utils.attendance_service import ensure_attendance_indexes
            ensure_attendance_indexes()
            from utils.database_tools import (ensure_accounting_columns, ensure_payroll_columns,
                                              ensure_settings_columns)
            ensure_settings_columns()
            ensure_accounting_columns()
            # ابطال/مرجوعی پرداخت‌ها (فاز B8 بازبینی داده/امنیت)
            from utils.database_tools import ensure_finance_columns
            ensure_finance_columns()
            # ستون‌های گردش‌کار فیش حقوقی + یکتایی «یک فیش برای هر نفر در هر دوره»
            payroll_patch = ensure_payroll_columns()
            if payroll_patch.get('added') or payroll_patch.get('cancelled_duplicates'):
                app.logger.warning(
                    'payroll schema patched: %s column(s) added, %s duplicate payslip(s) cancelled',
                    payroll_patch['added'], payroll_patch['cancelled_duplicates'])
            create_default_data()
            # تکمیل ردیف‌های «نقش × ماژول × اکشن» — تا الزام سطح اکشن در نگهبان،
            # کاربران مجازِ نصب‌های قدیمی را قفل نکند (این کار فقط اضافه می‌کند).
            from utils.access_policy import action_guard_enabled, backfill_role_actions
            if action_guard_enabled():
                added_actions = backfill_role_actions()
                if added_actions:
                    app.logger.info('access policy: %d role-action permission row(s) added',
                                    added_actions)
            # اعمال تنظیمات نصب‌کننده (config.ini): ساخت حساب مدیر و آدرس هاست.
            from utils.installer_config import apply_installer_config
            installer_note = apply_installer_config()
            if installer_note:
                app.logger.info('installer config: %s', installer_note)
            # اصلاح خودکار تاریخ‌های شمسی که در نسخه‌های قدیمی به‌اشتباه
            # مستقیماً در ستون میلادی ذخیره شده بودند (عملیات idempotent است).
            from utils.database_tools import repair_legacy_jalali_dates
            repaired_dates = repair_legacy_jalali_dates()
            if repaired_dates:
                app.logger.warning('%s legacy Jalali date values were repaired', repaired_dates)
            # نگهداری نشست‌ها/لاگ‌های کهنه (رشد بی‌نهایت جدول‌ها متوقف می‌شود)
            from utils.session_maintenance import run_session_maintenance
            app.logger.info('session maintenance: %s', run_session_maintenance(app))
            app._db_initialized = True

        # ربات بله در حالت Long Polling کار می‌کند و به دامنه عمومی/وب‌هوک نیاز ندارد.
        # فقط زمانی راه می‌افتد که لایسنس بخش «اتصالات» را باز کرده باشد.
        def _start_bale_when_licensed():
            try:
                from license_client import get_state
                if not get_state().has_feature('integrations'):
                    return
                with app.app_context():
                    from utils.bot_services import start_bale_polling_if_configured
                    start_bale_polling_if_configured(app)
            except Exception as exc:
                app.logger.info('bale polling not started: %s', exc)

        import threading as _threading
        _threading.Thread(target=_start_bale_when_licensed,
                          name='bale-polling-boot', daemon=True).start()
    
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
