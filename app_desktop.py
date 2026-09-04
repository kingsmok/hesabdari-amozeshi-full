"""
سیستم مدیریت آموزشگاه - نسخه دسکتاپ (پوسته PyQt6 + QWebEngine)
اجرا: python app_desktop.py
نسخه نصب‌کننده: AcademyManager.exe

اصلاحات این نسخه (بازبینی دیزاین، بخش ۲):
  • چاپ: `window.print()` و `printRequested` به `QPrinter`/`QPrintDialog` وصل شد
         (قبلاً ۱۱ صفحه چاپ‌پسند در نسخه دسکتاپ بی‌کار بودند) + میانبر Ctrl+P
  • دانلود: `downloadRequested` هندل می‌شود و فایل با دیالوگ «ذخیره» در پوشه
         Downloads می‌نشیند (قبلاً خروجی PDF/Excel بی‌صدا نادیده گرفته می‌شد)
  • پورت: اگر ۵۰۰۰ اشغال باشد به پورت بعدی می‌رود و پیام واقعی به کاربر نشان
         داده می‌شود؛ `server_ready` فقط پس از bind موفق set می‌شود
  • قفل تک‌نمونه: اجرای دوم پیام «برنامه باز است» می‌دهد، نه حلقه خطا
  • میزبان: پیش‌فرض 127.0.0.1 و فقط با `--lan` صریح روی شبکه باز می‌شود
  • پنجره: `startSystemMove` + دسته‌های ریسایز + اندازه‌گیری متناسب با صفحه
  • زوم: Ctrl+= / Ctrl+- / Ctrl+0 و دکمه‌های نوار ابزار
  • خروج تمیز: shutdown سرور werkzeug و آزادسازی نشست دیتابیس (به‌جای os._exit
         که ریسک نوشتن ناقص روی SQLite داشت) + گزینه «ادامه در سینی»
  • لاگ: stdout/stderr و خطاهای مهارنشده در logs/desktop-<date>.log نوشته می‌شوند
  • فونت Qt: ثبت .ttf/.otf (woff2 در addApplicationFont پشتیبانی نمی‌شود)
"""
import argparse
import os
import platform
import sys
import threading
import traceback
from datetime import date

# ═══ مسیر اصلی برنامه — سازگار با PyInstaller ═══
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
    DATA_DIR = BASE_DIR
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    DATA_DIR = BASE_DIR

os.chdir(BASE_DIR)
sys.path.insert(0, BASE_DIR)

# بررسی سازگاری نسخه‌ها — پیش از شروع سرور
from startup_checks import ensure_compatible

ensure_compatible()

APP_VERSION = '1.0.0'
PREFERRED_PORT = 5000                 # مقدار واقعی از utils.desktop_support می‌آید

# ── آرگومان‌ها ──
_parser = argparse.ArgumentParser(add_help=False)
_parser.add_argument('--lan', action='store_true', help='روی همه اینترفیس‌ها گوش بده (LAN)')
_parser.add_argument('--port', type=int, default=None)
_parser.add_argument('--no-single-instance', action='store_true')
_ARGS, _REMAINDER = _parser.parse_known_args(sys.argv)

HOST = '0.0.0.0' if _ARGS.lan else '127.0.0.1'
PORT = _ARGS.port or int(os.environ.get('ACADEMY_PORT') or PREFERRED_PORT)

SERVER = None
FLASK_APP = None
SERVER_ERROR = [None]
server_ready = threading.Event()
LOG_PATH = None


# ══════════════════════════════════════════════════════════════════════════
#  لاگ و گزارش خطا — بدون این، پیام خطای مشتری فقط یک پنجره سفید بود
# ══════════════════════════════════════════════════════════════════════════
class _Tee:
    """stdout/stderr را همزمان به ترمینال و فایل لاگ می‌نویسد."""

    def __init__(self, stream, handle):
        self.stream = stream
        self.handle = handle

    def write(self, text):
        try:
            self.stream.write(text)
        except Exception:
            pass
        try:
            self.handle.write(text)
            self.handle.flush()
        except Exception:
            pass
        return len(text)

    def flush(self):
        for target in (self.stream, self.handle):
            try:
                target.flush()
            except Exception:
                pass

    def __getattr__(self, name):
        return getattr(self.stream, name)


def setup_logging():
    global LOG_PATH
    try:
        log_dir = os.path.join(DATA_DIR, 'logs')
        os.makedirs(log_dir, exist_ok=True)
        LOG_PATH = desktop_log_path(DATA_DIR)
        handle = open(LOG_PATH, 'a', encoding='utf-8', buffering=1)
        handle.write(f"\n════════ شروع اجرا (pid {os.getpid()}) ════════\n")
        sys.stdout = _Tee(sys.__stdout__, handle)
        sys.stderr = _Tee(sys.__stderr__, handle)
    except Exception:
        LOG_PATH = None


def _write_crash(text):
    try:
        os.makedirs(os.path.join(DATA_DIR, 'logs'), exist_ok=True)
        with open(os.path.join(DATA_DIR, 'logs', 'desktop-crash.log'), 'a', encoding='utf-8') as fh:
            fh.write(f"\n[{date.today().isoformat()}] {text}\n")
    except Exception:
        pass


def _report_exception(title, exc):
    """چاپ + لاگ خطاهای مهارنشده، تا crash report دستی لازم نباشد."""
    detail = ''.join(traceback.format_exception(type(exc), exc, exc.__traceback__)) \
        if isinstance(exc, BaseException) else traceback.format_exc()
    text = f'{title}: {exc}\n{detail}'
    print(text)
    _write_crash(text)


def install_crash_hook():
    def hook(exc_type, value, tb):
        text = ''.join(traceback.format_exception(exc_type, value, tb))
        print('خطای مهارنشده:\n' + text)
        _write_crash(f'Unhandled\n{text}')
        sys.__excepthook__(exc_type, value, tb)
    sys.excepthook = hook


# ══════════════════════════════════════════════════════════════════════════
#  ابزارها
# ══════════════════════════════════════════════════════════════════════════
# ── کمکی‌های بدون Qt (تست‌پذیر در utils/desktop_support.py) ──
from utils.desktop_support import (                                           # noqa: E402
    PORT_SCAN_LIMIT, desktop_log_path, get_local_ip, pick_port, resolve_logo_path,
    server_error_text, unique_path, wait_until_serving,
)


def is_first_run():
    """بررسی اولین اجرا — دیتابیس هنوز ساخته نشده"""
    return not os.path.exists(os.path.join(DATA_DIR, 'instance', 'academy.db'))


def run_first_time_setup(application=None):
    """راه‌اندازی اولیه — ساخت دیتابیس و وارد کردن اطلاعات"""
    try:
        for d in ('instance', 'backups', 'logs',
                  'static/uploads', 'static/uploads/students',
                  'static/uploads/teachers', 'static/uploads/certificates',
                  'static/uploads/documents'):
            os.makedirs(os.path.join(DATA_DIR, d), exist_ok=True)

        if application is None:
            from app import create_app
            application = create_app()

        with application.app_context():
            try:
                from models.course import Course
                if Course.query.count() == 0:
                    import import_rahs_data        # noqa: F401
            except Exception as e:
                print(f"  وارد کردن اطلاعات: {e}")

            try:
                from models.student import Student
                if Student.query.count() == 0:
                    from utils.demo_data import create_demo_data
                    print(f"  داده‌های نمونه: {create_demo_data()}")
            except Exception as e:
                print(f"  داده‌های نمونه: {e}")
        return True
    except Exception as e:
        _report_exception('خطا در راه‌اندازی اولیه', e)
        return False


def start_server(application, host, port):
    """سرور Flask با werkzeug — تا بتوان هنگام خروج تمیز shutdown کرد.

    `server_ready` بعد از bind موفق set می‌شود (make_server همان‌جا bind
    می‌کند)؛ پیش‌تر پیش از `application.run()` set می‌شد و پیام «آماده» حتی با
    پورت اشغال‌شده چاپ می‌شد.
    """
    global SERVER, FLASK_APP
    FLASK_APP = application
    try:
        from werkzeug.serving import make_server
        SERVER = make_server(host, port, application, threaded=True)
        server_ready.set()
        SERVER.serve_forever()
    except Exception as exc:
        SERVER_ERROR[0] = exc
        server_ready.set()
    finally:
        SERVER = None


def stop_server():
    """بستن آرام سرور و آزادسازی نشست دیتابیس (به‌جای os._exit)."""
    server = SERVER
    if server is not None:
        try:
            worker = threading.Thread(target=server.shutdown, daemon=True)
            worker.start()
            worker.join(5)
            server.server_close()
        except Exception as exc:
            print(f'  بستن سرور: {exc}')
    try:
        if FLASK_APP is not None:
            with FLASK_APP.app_context():
                from extensions import db
                db.session.remove()
    except Exception:
        pass


def read_brand(application=None):
    """نام و لوگوی آموزشگاه برای اسپلش‌اسکرین و نوار عنوان (برندینگ مشتری)."""
    name, logo = 'سیستم مدیریت آموزشگاه', None
    try:
        if application is None:
            from app import create_app
            application = create_app()
        with application.app_context():
            from models.system import SystemSettings
            settings = SystemSettings.query.first()
            if settings is not None:
                name = (settings.academy_name or name).strip()
                logo = settings.logo or None
    except Exception:
        pass
    return name, logo


def _logo_on_disk(logo):
    return resolve_logo_path(logo, DATA_DIR)


# ══════════════════════════════════════════════════════════════════════════
#  Qt
# ══════════════════════════════════════════════════════════════════════════
from PyQt6.QtCore import Qt, QUrl, QTimer, QLockFile, QStandardPaths       # noqa: E402
from PyQt6.QtGui import (                                                   # noqa: E402
    QIcon, QPixmap, QPainter, QColor, QFont, QKeySequence, QLinearGradient,
    QBrush, QPen, QDesktopServices, QFontDatabase, QShortcut,
)
from PyQt6.QtWidgets import (                                               # noqa: E402
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QSystemTrayIcon, QMenu, QSplashScreen,
    QStatusBar, QMessageBox, QFileDialog, QDialog,
)
from PyQt6.QtPrintSupport import QPrinter, QPrintDialog                     # noqa: E402
from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings, QWebEngineProfile   # noqa: E402
from PyQt6.QtWebEngineWidgets import QWebEngineView                        # noqa: E402

MIN_ZOOM, MAX_ZOOM = 0.6, 2.2
RESIZE_MARGIN = 6


def load_qt_fonts():
    """ثبت فونت‌های Qt از فایل‌های `.ttf/.otf` کنار برنامه.

    `QFontDatabase.addApplicationFont` فرمت **woff2 را پشتیبانی نمی‌کند**؛
    پیش‌تر همان `Vazirmatn-Black.woff2` داده می‌شد و بی‌صدا رد می‌شد (فقط وزن
    Black هم بود) ⇒ منوها و دیالوگ‌ها به fallback می‌افتادند.
    """
    font_dir = os.path.join(DATA_DIR, 'static', 'fonts')
    registered = []
    if os.path.isdir(font_dir):
        for filename in sorted(os.listdir(font_dir)):
            if filename.lower().endswith(('.ttf', '.otf')):
                try:
                    if QFontDatabase.addApplicationFont(os.path.join(font_dir, filename)) >= 0:
                        registered.append(filename)
                except Exception:
                    pass
    if registered:
        print('  فونت‌های Qt: ' + ', '.join(registered))
    else:
        print('  ⚠ فونت TTF کنار برنامه نیست؛ برای فارسی‌سازی پوسته، '
              'Vazirmatn-Regular.ttf و Vazirmatn-Bold.ttf را در static/fonts بگذارید')
    return registered


def app_font():
    """قلم مناسب پوسته، با fallback به Tahoma/DejaVu (مک/لینوکس Tahoma ندارند)."""
    try:
        families = set(QFontDatabase.families())
    except Exception:
        families = set()
    for family in ('Vazirmatn', 'IRANSans', 'IRANYekan', 'Tahoma', 'DejaVu Sans', 'Arial'):
        if family in families or family == 'Arial':
            font = QFont(family, 10)
            font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
            return font
    return QFont('Arial', 10)


class CustomPage(QWebEnginePage):
    """پنجره‌های جدید به مرورگر سیستم؛ پیام‌های کنسول JS به فایل لاگ."""

    def createWindow(self, window_type):
        page = CustomPage(self)
        page.urlChanged.connect(lambda url: QDesktopServices.openUrl(url))
        return page

    def javaScriptConsoleMessage(self, level, message, line, source):
        if 'favicon' in message:
            return
        print(f'  [JS] {message} ({source}:{line})')


class ResizeGrip(QWidget):
    """نوار باریک دور پنجره frameless — با startSystemResize ریسایز می‌شود.

    FramelessWindowHint به‌تنهایی یعنی «لبه‌ای برای کشیدن نیست» و کاربر روی
    لپ‌تاپ‌های کوچک گیر می‌کرد.
    """

    SPECS = {
        'left': (Qt.CursorShape.SizeHorCursor, Qt.Edge.LeftEdge),
        'right': (Qt.CursorShape.SizeHorCursor, Qt.Edge.RightEdge),
        'top': (Qt.CursorShape.SizeVerCursor, Qt.Edge.TopEdge),
        'bottom': (Qt.CursorShape.SizeVerCursor, Qt.Edge.BottomEdge),
        'tl': (Qt.CursorShape.SizeFDiagCursor, Qt.Edge.LeftEdge | Qt.Edge.TopEdge),
        'br': (Qt.CursorShape.SizeFDiagCursor, Qt.Edge.RightEdge | Qt.Edge.BottomEdge),
        'tr': (Qt.CursorShape.SizeBDiagCursor, Qt.Edge.RightEdge | Qt.Edge.TopEdge),
        'bl': (Qt.CursorShape.SizeBDiagCursor, Qt.Edge.LeftEdge | Qt.Edge.BottomEdge),
    }

    def __init__(self, window, edge):
        super().__init__(window)
        self.window_ref = window
        cursor, edges = self.SPECS[edge]
        self.edges = edges
        self.edge = edge
        self.setCursor(cursor)

    def mousePressEvent(self, event):
        handle = self.window_ref.windowHandle()
        if handle is not None and event.button() == Qt.MouseButton.LeftButton:
            handle.startSystemResize(self.edges)
            event.accept()
        else:
            super().mousePressEvent(event)


class TitleBar(QWidget):
    """نوار عنوان سفارشی — کشیدن با startSystemMove تا Snap ویندوز کار کند."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_win = parent
        self.drag_pos = None
        self._system_move = False
        self.setFixedHeight(40)
        self.setObjectName("titleBar")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 6, 0)
        layout.setSpacing(6)

        self.logo_lbl = QLabel("AM")
        self.logo_lbl.setFixedSize(26, 26)
        self.logo_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.logo_lbl.setStyleSheet(
            "QLabel{background:qlineargradient(x1:0,y1:0,x2:1,y2:1,"
            "stop:0 #00c853,stop:1 #69f0ae);border-radius:6px;"
            "color:white;font-size:11px;font-weight:bold;}"
        )
        layout.addWidget(self.logo_lbl)

        self.title = QLabel("سیستم مدیریت آموزشگاه")
        self.title.setStyleSheet("color:#cfd8dc;font-size:12px;font-weight:600;padding-left:6px;")
        layout.addWidget(self.title)
        layout.addStretch()

        self.url_lbl = QLabel(f"localhost:{PORT}")
        self.url_lbl.setStyleSheet(
            "background:rgba(255,255,255,.06);color:#90a4ae;"
            "font-size:10px;padding:3px 10px;border-radius:4px;"
            "font-family:Consolas,monospace;"
        )
        layout.addWidget(self.url_lbl)
        layout.addSpacing(6)

        small = ("QPushButton{border:none;color:#90a4ae;font-size:15px;"
                 "border-radius:4px;min-width:30px;max-width:30px;"
                 "min-height:26px;max-height:26px;}"
                 "QPushButton:hover{background:rgba(255,255,255,.1);color:#fff;}")
        danger = small.replace("background:rgba(255,255,255,.1)", "background:#e74c3c")

        buttons = [
            ("\U0001F5A8", "چاپ صفحه فعلی (Ctrl+P)", small, lambda: self.parent_win.print_current_page()),
            ("\u2139", "اطلاعات شبکه", small,
             lambda: self.parent_win.web.setUrl(QUrl(self.parent_win.url_for('/network-info')))),
            ("\u2013", "حداقل‌سازی", small, lambda: self.parent_win.showMinimized()),
            ("\u25A1", "بزرگ‌نمایی", small,
             lambda: self.parent_win.showNormal() if self.parent_win.isMaximized()
             else self.parent_win.showMaximized()),
            ("\u2715", "بستن", danger, lambda: self.parent_win.request_close()),
        ]

        for text, tip, style, slot in buttons:
            btn = QPushButton(text)
            btn.setToolTip(tip)
            btn.setStyleSheet(style)
            btn.clicked.connect(slot)
            layout.addWidget(btn)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            handle = self.parent_win.windowHandle()
            self._system_move = bool(handle is not None and handle.startSystemMove())
            if not self._system_move:
                self.drag_pos = (event.globalPosition().toPoint()
                                 - self.parent_win.frameGeometry().topLeft())
        else:
            self._system_move = False

    def mouseMoveEvent(self, event):
        if self._system_move or self.drag_pos is None:
            return
        if event.buttons() == Qt.MouseButton.LeftButton:
            self.parent_win.move(event.globalPosition().toPoint() - self.drag_pos)

    def mouseReleaseEvent(self, event):
        self.drag_pos = None
        self._system_move = False

    def mouseDoubleClickEvent(self, event):
        if self.parent_win.isMaximized():
            self.parent_win.showNormal()
        else:
            self.parent_win.showMaximized()

    def set_brand(self, name, logo_path=None):
        if name:
            self.title.setText(name)
        if logo_path:
            pixmap = QPixmap(logo_path)
            if not pixmap.isNull():
                self.logo_lbl.setText('')
                self.logo_lbl.setPixmap(pixmap.scaled(
                    24, 24, Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation))
                self.logo_lbl.setStyleSheet("QLabel{border:none;background:transparent;}")


class MainWindow(QMainWindow):
    def __init__(self, brand_name=None, brand_logo=None):
        super().__init__()
        self.zoom = 1.0
        self._load_failures = 0
        self._brand_title = brand_name or "سیستم مدیریت آموزشگاه"
        self._printer = None
        self.setWindowTitle(f"{self._brand_title} — Academy Manager Pro v{APP_VERSION}")

        # اندازه شروع: پنجره نباید از صفحه بیرون بزند (روی ۱۳۶۶×۷۶۸ با اسکیل
        # ۱۲۵٪، resize ثابت ۱۴۴۰×۹۰۰ یعنی بیرون‌زدگی + نبود لبه ریسایز)
        screen = QApplication.primaryScreen()
        area = screen.availableGeometry() if screen is not None else None
        if area is not None:
            self.setMinimumSize(min(880, area.width() - 32), min(560, area.height() - 32))
            width = min(1440, area.width() - 40)
            height = min(900, area.height() - 40)
            self.resize(width, height)
            self.move(area.center().x() - width // 2, area.center().y() - height // 2)
            self._start_maximized = area.width() <= 1500 or area.height() <= 880
        else:
            self.setMinimumSize(880, 560)
            self.resize(1440, 900)
            self._start_maximized = False

        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        icon_path = os.path.join(BASE_DIR, 'static', 'images', 'icon.ico')
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        central = QWidget()
        central.setObjectName("central")
        self.setCentralWidget(central)
        box = QVBoxLayout(central)
        box.setContentsMargins(RESIZE_MARGIN, RESIZE_MARGIN, RESIZE_MARGIN, RESIZE_MARGIN)
        box.setSpacing(0)

        self.title_bar = TitleBar(self)
        self.title_bar.set_brand(brand_name, _logo_on_disk(brand_logo))
        box.addWidget(self.title_bar)

        # نوار ابزار
        toolbar = QWidget()
        toolbar.setFixedHeight(38)
        toolbar.setObjectName("toolbar")
        tools = QHBoxLayout(toolbar)
        tools.setContentsMargins(10, 0, 10, 0)
        tools.setSpacing(4)

        button_style = (
            "QPushButton{border:none;background:rgba(255,255,255,.04);color:#90a4ae;"
            "font-size:15px;border-radius:5px;min-width:30px;max-width:30px;"
            "min-height:26px;max-height:26px;}"
            "QPushButton:hover{background:rgba(255,255,255,.1);color:#fff;}"
            "QPushButton:disabled{color:#455a64;}")

        def tool_button(text, tip, slot=None):
            btn = QPushButton(text)
            btn.setToolTip(tip)
            btn.setStyleSheet(button_style)
            if slot is not None:
                btn.clicked.connect(slot)
            tools.addWidget(btn)
            return btn

        self.btn_back = tool_button("\u2190", "بازگشت", self._go_back)
        self.btn_fwd = tool_button("\u2192", "جلو", self._go_forward)
        self.btn_ref = tool_button("\u21BB", "بازخوانی", lambda: self.web.reload())
        self.btn_home = tool_button("\u2302", "خانه", lambda: self.web.setUrl(QUrl(self.url_for('/'))))
        tools.addSpacing(6)
        self.btn_zoom_out = tool_button("\u2212", "کوچک‌نمایی (Ctrl+-)", lambda: self.set_zoom(self.zoom - 0.1))
        self.btn_zoom_in = tool_button("+", "بزرگ‌نمایی (Ctrl+=)", lambda: self.set_zoom(self.zoom + 0.1))
        self.btn_print = tool_button("\U0001F5A8", "چاپ این صفحه (Ctrl+P)", self.print_current_page)
        tools.addSpacing(8)

        self.addr = QLabel(self.url_for('/'))
        self.addr.setStyleSheet(
            "background:rgba(255,255,255,.05);color:#90a4ae;font-size:10px;"
            "padding:5px 12px;border-radius:5px;font-family:Consolas,monospace;")
        tools.addWidget(self.addr)
        tools.addStretch()
        box.addWidget(toolbar)

        # وب‌ویو
        self.web = QWebEngineView()
        self.page = CustomPage(self.web)
        self.web.setPage(self.page)
        settings = self.web.settings()
        # PrintPreviewEnabled از Qt WebEngine (حدود Qt 6.5+) حذف شده است؛
        # بنابراین فقط attributeهایی را فعال می‌کنیم که در نسخه نصب‌شده وجود دارند.
        web_attribute = getattr(QWebEngineSettings, 'WebAttribute', None)
        for name in (
                'JavascriptEnabled',
                'LocalStorageEnabled',
                'PluginsEnabled',
                'PrintPreviewEnabled',  # فقط در نسخه‌های قدیمی وجود دارد
                'FullScreenSupportEnabled',
        ):
            attribute = getattr(web_attribute, name, None) if web_attribute is not None else None
            if attribute is None:
                continue
            try:
                settings.setAttribute(attribute, True)
            except Exception:
                pass
        box.addWidget(self.web)

        status = QStatusBar()
        status.setFixedHeight(22)
        status.setObjectName("statusBar")
        status.showMessage("در حال بارگذاری...")
        box.addWidget(status)
        self.status = status

        # رویدادها
        self.web.urlChanged.connect(self._url_changed)
        self.web.loadFinished.connect(self._loaded)
        self.web.printFinished.connect(self._on_print_finished)
        try:      # interfaceChanged در برخی نسخه‌های Qt6 وجود ندارد
            self.web.history().currentItemChanged.connect(self._refresh_nav_buttons)
        except Exception:
            pass

        profile = self.page.profile() or QWebEngineProfile.defaultProfile()
        profile.downloadRequested.connect(self._on_download)
        self.page.printRequested.connect(self.print_current_page)

        for sequence, slot in (
            ("Ctrl+P", self.print_current_page),
            ("Ctrl+=", lambda: self.set_zoom(self.zoom + 0.1)),
            ("Ctrl++", lambda: self.set_zoom(self.zoom + 0.1)),
            ("Ctrl+-", lambda: self.set_zoom(self.zoom - 0.1)),
            ("Ctrl+0", lambda: self.set_zoom(1.0)),
            ("F5", lambda: self.web.reload()),
            ("Ctrl+R", lambda: self.web.reload()),
            ("Ctrl+W", self.hide),
        ):
            shortcut = QShortcut(QKeySequence(sequence), self)
            shortcut.setContext(Qt.ShortcutContext.WindowWithChildrenContext)
            shortcut.activated.connect(slot)

        self._grips = {}
        for edge in ResizeGrip.SPECS:
            grip = ResizeGrip(self, edge)
            grip.show()
            grip.raise_()
            self._grips[edge] = grip

        self._setup_tray()

        self.setStyleSheet("""
            #central{background:#0a1628;border:1px solid #1a2940;border-radius:8px;}
            #titleBar{background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #0a1628,stop:1 #0d1f3c);}
            #toolbar{background:#0d1f3c;border-bottom:1px solid rgba(255,255,255,.04);}
            #statusBar{background:#0a1628;color:#78909c;font-size:10px;
                       border-top:1px solid rgba(255,255,255,.04);}
            QMenu{background:#1e2d42;color:#cfd8dc;border:1px solid #2a3f55;border-radius:6px;padding:4px;}
            QMenu::item{padding:6px 24px;border-radius:4px;}
            QMenu::item:selected{background:#0d47a1;color:white;}
            QToolTip{background:#1e2d42;color:#cfd8dc;border:1px solid #2a3f55;}
        """)

        self.web.setUrl(QUrl(self.url_for('/')))

    # ══════════════════ کمکی ══════════════════
    def url_for(self, path=''):
        """روی LAN هم 127.0.0.1 درست است؛ آدرس شبکه فقط برای بقیه دستگاه‌هاست."""
        return f"http://127.0.0.1:{PORT}{path}"

    def network_url(self):
        return f"http://{get_local_ip()}:{PORT}"

    def _go_back(self):
        if self.web.history().canGoBack():
            self.web.back()

    def _go_forward(self):
        if self.web.history().canGoForward():
            self.web.forward()

    def _refresh_nav_buttons(self, *_ignored):
        try:
            history = self.web.history()
            self.btn_back.setEnabled(history.canGoBack())
            self.btn_fwd.setEnabled(history.canGoForward())
        except Exception:
            pass

    def resizeEvent(self, event):
        super().resizeEvent(event)
        width, height = self.width(), self.height()
        for edge, grip in getattr(self, '_grips', {}).items():
            if edge == 'top':
                grip.setGeometry(RESIZE_MARGIN, 0, width - 2 * RESIZE_MARGIN, RESIZE_MARGIN)
            elif edge == 'bottom':
                grip.setGeometry(RESIZE_MARGIN, height - RESIZE_MARGIN,
                                 width - 2 * RESIZE_MARGIN, RESIZE_MARGIN)
            elif edge == 'left':
                grip.setGeometry(0, RESIZE_MARGIN, RESIZE_MARGIN, height - 2 * RESIZE_MARGIN)
            elif edge == 'right':
                grip.setGeometry(width - RESIZE_MARGIN, RESIZE_MARGIN,
                                 RESIZE_MARGIN, height - 2 * RESIZE_MARGIN)
            elif edge == 'tl':
                grip.setGeometry(0, 0, 14, 14)
            elif edge == 'tr':
                grip.setGeometry(width - 14, 0, 14, 14)
            elif edge == 'bl':
                grip.setGeometry(0, height - 14, 14, 14)
            elif edge == 'br':
                grip.setGeometry(width - 14, height - 14, 14, 14)

    def set_zoom(self, value):
        self.zoom = max(MIN_ZOOM, min(MAX_ZOOM, round(value, 2)))
        self.web.setZoomFactor(self.zoom)
        self.status.showMessage(f"زوم: {int(self.zoom * 100)}٪ — Ctrl+0 برای بازگشت", 4000)

    # ══════════════════ چاپ ══════════════════
    def print_current_page(self):
        """`window.print()` (سیگنال printRequested) و Ctrl+P هر دو اینجا می‌آیند."""
        if self._printer is None:
            self._printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        dialog = QPrintDialog(self._printer, self)
        dialog.setWindowTitle("چاپ")
        if dialog.exec() != int(QDialog.DialogCode.Accepted):
            return
        self.status.showMessage("در حال آماده‌سازی چاپ...")
        try:
            self.web.print(self._printer)
        except Exception as exc:
            _report_exception('چاپ ناموفق', exc)
            QMessageBox.warning(self, "چاپ", f"چاپ انجام نشد:\n{exc}")

    def _on_print_finished(self, successful):
        if successful:
            self.status.showMessage("چاپ انجام شد", 5000)
        else:
            QMessageBox.warning(
                self, "چاپ",
                "چاپ انجام نشد. اگر پرینتری نصب نیست «Microsoft Print to PDF» را انتخاب کنید "
                "تا فایل PDF ذخیره شود.")

    # ══════════════════ دانلود ══════════════════
    def _on_download(self, download):
        try:
            suggested = (download.suggestedFileName() or download.downloadFileName()
                         or 'download.pdf')
            target_dir = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DownloadLocation)
            if not target_dir:
                target_dir = os.path.join(os.path.expanduser('~'), 'Downloads')
            os.makedirs(target_dir, exist_ok=True)

            default_name = unique_path(target_dir, suggested)
            path, _selected = QFileDialog.getSaveFileName(
                self, "ذخیره فایل", default_name, "همه فایل‌ها (*)")
            if not path:
                download.cancel()
                self.status.showMessage("دانلود لغو شد", 4000)
                return
            if os.path.isdir(path):
                path = os.path.join(path, suggested)

            download.setPath(path)
            download.accept()
            download.finished.connect(lambda state, saved=path: self._download_done(state, saved))
            download.interrupted.connect(
                lambda error: self.status.showMessage(f"دانلود ناتمام ماند: {error}", 6000))
        except Exception as exc:
            _report_exception('خطا در دانلود', exc)
            try:
                download.cancel()
            except Exception:
                pass

    def _download_done(self, state, path):
        # DownloadState.Finished == 0 (در نسخه‌های مختلف Qt نام کلاس فرق می‌کند)
        finished = int(getattr(state, 'value', state)) == 0
        name = os.path.basename(path)
        if not finished:
            self.status.showMessage("دانلود لغو یا ناتمام ماند", 5000)
            return
        self.status.showMessage(f"✓ ذخیره شد: {name}", 8000)
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Information)
        box.setWindowTitle("دانلود کامل شد")
        box.setText(f"«{name}» ذخیره شد.\n{os.path.dirname(path)}")
        open_folder = box.addButton("باز کردن پوشه", QMessageBox.ButtonRole.ActionRole)
        box.addButton("باشه", QMessageBox.ButtonRole.AcceptRole)
        box.exec()
        if box.clickedButton() is open_folder:
            QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(path)))

    # ══════════════════ وضعیت بارگذاری ══════════════════
    def _url_changed(self, url):
        address = url.toString()
        self.addr.setText(address)
        current = self.title_bar.title.text()
        if "network-info" in address:
            self.title_bar.title.setText("اطلاعات شبکه")
        elif "/my" in address:
            self.title_bar.title.setText("پورتال مدرس")
        elif "login" in address:
            self.title_bar.title.setText("ورود به سیستم")
        elif current in ("اطلاعات شبکه", "پورتال مدرس", "ورود به سیستم"):
            self.title_bar.title.setText(self._brand_title)
        self._refresh_nav_buttons()

    def _loaded(self, ok):
        if ok:
            self._load_failures = 0
            mode = "شبکه (LAN)" if HOST == '0.0.0.0' else "فقط این سیستم"
            self.status.showMessage(
                f"آماده | {self.url_for('/')} | دسترسی: {mode} | "
                f"{platform.system()} {platform.release()} | {platform.machine()}")
            return

        self._load_failures += 1
        if self._load_failures < 4:
            self.status.showMessage(f"خطا در بارگذاری — تلاش مجدد ({self._load_failures}/3)...")
            QTimer.singleShot(1500, lambda: self.web.setUrl(QUrl(self.url_for('/'))))
            return

        # سه بار نشد: به‌جای حلقه بی‌پایای reload، پیام واقعی + راهنما
        self._load_failures = 0
        reason = server_error_text(SERVER_ERROR[0], PORT)
        self.status.showMessage("سرور در دسترس نیست")
        print(f"  ✗ {reason}")
        self.web.setHtml(f"""<!DOCTYPE html><html dir="rtl"><head><meta charset="utf-8">
            <style>
              body{{font-family:Tahoma,Vazirmatn,sans-serif;background:#0a1628;color:#cfd8dc;
                    margin:0;display:flex;align-items:center;justify-content:center;height:100vh}}
              .box{{max-width:660px;padding:28px 32px;background:#0d1f3c;border:1px solid #1a2940;
                    border-radius:12px}}
              h1{{font-size:19px;margin:0 0 10px}}
              p{{line-height:2;font-size:13px;color:#ef9a9a}}
              code{{background:rgba(255,255,255,.07);padding:2px 6px;border-radius:4px;color:#e0e0e0}}
              ul{{font-size:13px;color:#b0bec5;line-height:2.1}}
            </style></head><body><div class="box">
            <h1>&#9888; سرور داخلی برنامه بالا نیامد</h1>
            <p>{reason}</p>
            <ul>
              <li>اگر پورت <code>{PORT}</code> اشغال است، برنامه را با
                  <code>--port {PORT + 1}</code> اجرا کنید.</li>
              <li>اگر نسخه دیگری از برنامه باز است، آن را ببندید (قفل تک‌نمونه فعال است).</li>
              <li>لاگ: <code>{LOG_PATH or os.path.join('logs', 'desktop.log')}</code></li>
            </ul>
            </div></body></html>""")
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Critical)
        box.setWindowTitle("سرور اجرا نشد")
        box.setText("سرور داخلی برنامه بالا نیامد.\n\n" + reason)
        log_button = None
        if LOG_PATH:
            log_button = box.addButton("باز کردن لاگ", QMessageBox.ButtonRole.ActionRole)
        retry = box.addButton("تلاش دوباره", QMessageBox.ButtonRole.RetryRole)
        box.addButton("خروج", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        clicked = box.clickedButton()
        if log_button is not None and clicked is log_button:
            QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(LOG_PATH)))
            self._load_failures = 3
            QTimer.singleShot(2000, lambda: self.web.setUrl(QUrl(self.url_for('/'))))
        elif clicked is retry:
            self.web.setUrl(QUrl(self.url_for('/')))
        else:
            self._force_quit = True
            self._really_quit()

    # ══════════════════ سینی system ══════════════════
    def _setup_tray(self):
        pixmap = QPixmap(64, 64)
        pixmap.fill(QColor(0, 0, 0, 0))
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        gradient = QLinearGradient(0, 0, 64, 64)
        gradient.setColorAt(0, QColor("#0d47a1"))
        gradient.setColorAt(1, QColor("#00c853"))
        painter.setBrush(QBrush(gradient))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(0, 0, 64, 64, 12, 12)
        painter.setPen(QPen(QColor("white")))
        painter.setFont(QFont("Arial", 18, QFont.Weight.Bold))
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "AM")
        painter.end()

        icon_path = os.path.join(BASE_DIR, 'static', 'images', 'icon.ico')
        self.tray = QSystemTrayIcon(QIcon(icon_path) if os.path.exists(icon_path) else QIcon(pixmap), self)
        self.tray.setToolTip(self._brand_title)

        menu = QMenu()
        menu.addAction("نمایش پنجره", self._show_window)
        menu.addAction("باز کردن در مرورگر",
                       lambda: QDesktopServices.openUrl(QUrl(self.url_for('/'))))
        menu.addAction("چاپ صفحه فعلی", self.print_current_page)
        menu.addSeparator()
        menu.addAction("زوم ۱۰۰٪", lambda: self.set_zoom(1.0))
        menu.addAction("بزرگ‌نمایی", lambda: (self.showNormal(), self.showMaximized()))
        menu.addAction("مخفی شدن در سینی", self.hide)
        menu.addSeparator()
        menu.addAction("پشتیبان‌گیری", lambda: self.web.setUrl(QUrl(self.url_for('/panel/backup'))))
        menu.addAction("اطلاعات شبکه", lambda: self.web.setUrl(QUrl(self.url_for('/network-info'))))
        menu.addSeparator()
        menu.addAction("خروج از برنامه", self._quit_from_tray)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._tray_activated)
        self.tray.show()

    def _show_window(self):
        self.showNormal()
        self.activateWindow()
        self.raise_()

    def _tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._show_window()
        elif reason == QSystemTrayIcon.ActivationReason.Trigger:
            if self.isVisible() and not self.isMinimized():
                self.hide()
            else:
                self._show_window()

    def _quit_from_tray(self):
        self._force_quit = True
        self._really_quit()

    # ══════════════════ خروج ══════════════════
    def request_close(self):
        """بستن پنجره: سینی یا خروج؟ (قبلاً هر بار دیالوگ «خروج؟» می‌آمد و
        با os._exit سرور و اسکژولر نیمه‌بسته می‌ماندند)"""
        if getattr(self, '_force_quit', False):
            self._really_quit()
            return
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle("خروج")
        box.setText("برنامه بسته شود یا در سینی system ادامه دهد؟")
        box.setInformativeText("با «ادامه در سینی» سرور روشن می‌ماند؛ "
                              "ربات و پشتیبان‌گیری خودکار کار می‌کنند.")
        quit_button = box.addButton("خروج از برنامه", QMessageBox.ButtonRole.AcceptRole)
        hide_button = box.addButton("ادامه در سینی", QMessageBox.ButtonRole.DestructiveRole)
        box.addButton("انصراف", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(hide_button if self.tray.isVisible() else quit_button)
        box.exec()
        choice = box.clickedButton()
        if choice is quit_button:
            self._really_quit()
        elif choice is hide_button:
            self.hide()

    def _really_quit(self):
        self.status.showMessage("در حال بستن سرور...")
        QApplication.processEvents()
        stop_server()
        if self.tray is not None:
            self.tray.hide()
        QApplication.instance().quit()

    def closeEvent(self, event):
        if getattr(self, '_force_quit', False):
            event.accept()
            return
        event.ignore()
        self.request_close()


# ══════════════════════════════════════════════════════════════════════════
def main():
    global PORT
    setup_logging()
    install_crash_hook()

    print("\n" + "=" * 60)
    print("  سیستم مدیریت آموزشگاه - Academy Manager Pro")
    print(f"  نسخه {APP_VERSION}")
    print("=" * 60)

    argv = [sys.argv[0]] + list(_REMAINDER[1:])
    app = QApplication(argv)
    app.setApplicationName("AcademyManager")
    app.setApplicationDisplayName("سیستم مدیریت آموزشگاه")
    app.setOrganizationName("AcademyManager")
    app.setQuitOnLastWindowClosed(False)      # بستن پنجره ≠ خروج؛ سینی زنده بماند

    # ── قفل تک‌نمونه ──
    os.makedirs(os.path.join(DATA_DIR, 'logs'), exist_ok=True)
    lock = QLockFile(os.path.join(DATA_DIR, 'logs', 'single-instance.lock'))
    lock.setStaleLockTime(0)
    acquired = True
    if not _ARGS.no_single_instance:
        acquired = lock.tryLock(100)
    if not acquired:
        message = ("نسخه دیگری از برنامه در حال اجراست.\n\n"
                   "اگر پنجره‌ای نمی‌بینید، آیکون سینی system را بررسی کنید "
                   "(یا Task Manager را).")
        print('  ' + message.replace('\n', ' '))
        box = QMessageBox()
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("برنامه در حال اجراست")
        box.setText(message)
        box.addButton("باشه", QMessageBox.ButtonRole.AcceptRole)
        box.exec()
        return 0

    load_qt_fonts()
    app.setFont(app_font())

    # ── پورت آزاد ──
    chosen = pick_port(PORT)
    if chosen is None:
        print(f"  ✗ هیچ پورت آزادی از {PORT} تا {PORT + PORT_SCAN_LIMIT} پیدا نشد")
        _write_crash('no free port')
        QMessageBox.critical(None, "پورت آزاد نیست",
                             f"پورت‌های {PORT} تا {PORT + PORT_SCAN_LIMIT} اشغال‌اند.\n"
                             "با --port یک پورت دیگر بدهید.")
        lock.unlock()
        return 1
    if chosen != PORT:
        print(f"  ⚠ پورت {PORT} اشغال بود؛ سراغ {chosen} می‌رویم")
        PORT = chosen

    print(f"  آدرس محلی: http://127.0.0.1:{PORT}")
    if HOST == '0.0.0.0':
        print(f"  آدرس شبکه: http://{get_local_ip()}:{PORT}  (حالت --lan)")
    else:
        print("  دسترسی شبکه: خاموش (با --lan فعال می‌شود)")
    print("  نام کاربری: admin / **رمز حذف شده برای امنیت**")
    print("=" * 60)

    # ── اپلیکیشن (یک‌بار) + اولین اجرا ──
    try:
        from app import create_app
        application = create_app()
    except Exception as exc:
        _report_exception('ساخت اپلیکیشن ناموفق', exc)
        QMessageBox.critical(None, "خطای راه‌اندازی",
                             f"برنامه بالا نیامد:\n{exc}\n\nلاگ: {LOG_PATH or 'logs/'}")
        lock.unlock()
        return 1

    if is_first_run():
        print("\n  ✓ اولین اجرا — در حال راه‌اندازی...")
        run_first_time_setup(application)
        print("  ✓ راه‌اندازی اولیه کامل شد\n")
    else:
        print("  ✓ دیتابیس موجود است\n")

    brand_name, brand_logo = read_brand(application)

    thread = threading.Thread(target=start_server, args=(application, HOST, PORT), daemon=True)
    thread.start()
    if not server_ready.wait(timeout=25):
        _report_exception('سرور شروع نشد', SERVER_ERROR[0] or RuntimeError('timeout'))
    serving = wait_until_serving(PORT, error=SERVER_ERROR[0])
    if serving:
        print("  ✓ سرور آماده است!\n")
    else:
        print("  ⚠ " + server_error_text(SERVER_ERROR[0], PORT) + "\n")

    # ── اسپلش ──
    splash_pixmap = QPixmap(400, 300)
    splash_pixmap.fill(QColor("#0a1628"))
    painter = QPainter(splash_pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    logo_path = _logo_on_disk(brand_logo)
    logo_pixmap = QPixmap(logo_path) if logo_path else QPixmap()
    if not logo_pixmap.isNull():
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor("#ffffff")))
        painter.drawRoundedRect(150, 40, 100, 100, 20, 20)
        painter.setClipRect(150, 40, 100, 100)
        painter.drawPixmap(150, 40, 100, 100, logo_pixmap.scaled(
            100, 100, Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation))
        painter.setClipping(False)
    else:
        gradient = QLinearGradient(140, 40, 260, 160)
        gradient.setColorAt(0, QColor("#0d47a1"))
        gradient.setColorAt(1, QColor("#00c853"))
        painter.setBrush(QBrush(gradient))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(150, 40, 100, 100, 20, 20)
        painter.setPen(QPen(QColor("white")))
        painter.setFont(QFont("Arial", 28, QFont.Weight.Bold))
        painter.drawText(150, 40, 100, 100, Qt.AlignmentFlag.AlignCenter, "AM")

    painter.setPen(QPen(QColor("#e0e0e0")))
    painter.setFont(QFont("Arial", 16, QFont.Weight.Bold))
    painter.drawText(0, 170, 400, 30, Qt.AlignmentFlag.AlignCenter, "Academy Manager Pro")
    painter.setPen(QPen(QColor("#90a4ae")))
    painter.setFont(QFont("Arial", 10))
    painter.drawText(0, 200, 400, 20, Qt.AlignmentFlag.AlignCenter, brand_name or "سیستم مدیریت آموزشگاه")
    painter.drawText(0, 225, 400, 20, Qt.AlignmentFlag.AlignCenter, "در حال بارگذاری...")
    painter.setBrush(QBrush(QColor("#1a2940")))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(100, 260, 200, 8, 4, 4)
    painter.setBrush(QBrush(QColor("#00c853")))
    painter.drawRoundedRect(100, 260, 60, 8, 4, 4)
    painter.end()

    splash = QSplashScreen(splash_pixmap)
    splash.show()
    app.processEvents()

    window = MainWindow(brand_name, brand_logo)
    window.show()
    if window._start_maximized:
        window.showMaximized()
    splash.finish(window)

    code = app.exec()
    stop_server()
    if lock is not None and acquired:
        lock.unlock()
    return code


if __name__ == '__main__':
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as exc:
        _report_exception('خطای بحرانی', exc)
        try:
            QMessageBox.critical(None, "خطا",
                                 f"برنامه با خطا متوقف شد:\n{exc}\n\nلاگ: {LOG_PATH or 'logs/'}")
        except Exception:
            pass
        sys.exit(1)
