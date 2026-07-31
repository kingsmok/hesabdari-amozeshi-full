"""
سیستم مدیریت آموزشگاه - نسخه دسکتاپ
اجرا: python app_desktop.py
نسخه نصب‌کننده: AcademyManager.exe
"""
import sys, os, threading, time, socket, json, platform

# ═══ مسیر اصلی برنامه — سازگار با PyInstaller ═══
if getattr(sys, 'frozen', False):
    # اگر توسط PyInstaller打包 شده
    BASE_DIR = os.path.dirname(sys.executable)
    # فایل‌های داده در کنار اجرایی هستند
    DATA_DIR = BASE_DIR
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    DATA_DIR = BASE_DIR

os.chdir(BASE_DIR)
sys.path.insert(0, BASE_DIR)

PORT = 5000


def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "127.0.0.1"


def is_first_run():
    """بررسی اولین اجرا — دیتابیس هنوز ساخته نشده"""
    db_path = os.path.join(DATA_DIR, 'instance', 'academy.db')
    return not os.path.exists(db_path)


def run_first_time_setup():
    """راه‌اندازی اولیه — ساخت دیتابیس و وارد کردن اطلاعات"""
    try:
        # ایجاد پوشه‌های لازم
        dirs_to_create = [
            'instance', 'backups',
            'static/uploads', 'static/uploads/students',
            'static/uploads/teachers', 'static/uploads/certificates',
            'static/uploads/documents',
        ]
        for d in dirs_to_create:
            os.makedirs(os.path.join(DATA_DIR, d), exist_ok=True)
        
        # ساخت اپلیکیشن و دیتابیس
        from app import create_app
        application = create_app()
        
        with application.app_context():
            # وارد کردن اطلاعات آموزشگاه رهسا
            try:
                from models.course import Field, Course
                if Course.query.count() == 0:
                    # اجرای اسکریپت وارد کردن داده‌ها
                    import import_rahs_data
            except Exception as e:
                print(f"  وارد کردن اطلاعات: {e}")
            
            # ایجاد داده‌های نمونه
            try:
                from models.student import Student
                if Student.query.count() == 0:
                    from utils.demo_data import create_demo_data
                    result = create_demo_data()
                    print(f"  داده‌های نمونه: {result}")
            except Exception as e:
                print(f"  داده‌های نمونه: {e}")
        
        return True
    except Exception as e:
        print(f"  خطا در راه‌اندازی: {e}")
        return False


# ═══ شروع سرور ═══
print("\n" + "=" * 60)
print("  سیستم مدیریت آموزشگاه - Academy Manager Pro")
print("  نسخه ۱.۰.۰")
print("=" * 60)

# بررسی اولین اجرا
if is_first_run():
    print("\n  ✓ اولین اجرا — در حال راه‌اندازی...")
    run_first_time_setup()
    print("  ✓ راه‌اندازی اولیه کامل شد\n")
else:
    print("  ✓ دیتابیس موجود است\n")

print(f"  آدرس محلی: http://localhost:{PORT}")
print(f"  آدرس شبکه: http://{get_local_ip()}:{PORT}")
print(f"  نام کاربری: admin / **رمز حذف شده برای امنیت**")
print("=" * 60)

server_ready = threading.Event()


def start_server():
    from app import create_app
    application = create_app()
    server_ready.set()
    application.run(host='0.0.0.0', port=PORT, debug=False, use_reloader=False, threaded=True)


server_thread = threading.Thread(target=start_server, daemon=True)
server_thread.start()
server_ready.wait(timeout=15)
time.sleep(0.5)
print("  ✓ سرور آماده است!\n")

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QSystemTrayIcon, QMenu, QSplashScreen,
    QStatusBar, QMessageBox
)
from PyQt6.QtCore import Qt, QUrl, QTimer
from PyQt6.QtGui import (
    QIcon, QPixmap, QPainter, QColor, QFont,
    QLinearGradient, QBrush, QPen, QDesktopServices
)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings


class CustomPage(QWebEnginePage):
    def createWindow(self, window_type):
        page = CustomPage(self)
        page.urlChanged.connect(lambda url: QDesktopServices.openUrl(url))
        return page


class TitleBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_win = parent
        self.setFixedHeight(40)
        self.drag_pos = None
        self.setObjectName("titleBar")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 6, 0)
        layout.setSpacing(6)

        logo = QLabel("AM")
        logo.setFixedSize(26, 26)
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo.setStyleSheet(
            "QLabel{background:qlineargradient(x1:0,y1:0,x2:1,y2:1,"
            "stop:0 #00c853,stop:1 #69f0ae);border-radius:6px;"
            "color:white;font-size:11px;font-weight:bold;}"
        )
        layout.addWidget(logo)

        self.title = QLabel("سیستم مدیریت آموزشگاه")
        self.title.setStyleSheet(
            "color:#b0bec5;font-size:12px;font-weight:600;padding-left:6px;"
        )
        layout.addWidget(self.title)
        layout.addStretch()

        self.url_lbl = QLabel(f"localhost:{PORT}")
        self.url_lbl.setStyleSheet(
            "background:rgba(255,255,255,.06);color:#607d8b;"
            "font-size:10px;padding:3px 10px;border-radius:4px;"
            "font-family:Consolas,monospace;"
        )
        layout.addWidget(self.url_lbl)
        layout.addSpacing(6)

        bs = ("QPushButton{border:none;color:#78909c;font-size:15px;"
              "border-radius:4px;min-width:30px;max-width:30px;"
              "min-height:26px;max-height:26px;}"
              "QPushButton:hover{background:rgba(255,255,255,.1);color:#fff;}")
        bc = ("QPushButton{border:none;color:#78909c;font-size:15px;"
              "border-radius:4px;min-width:30px;max-width:30px;"
              "min-height:26px;max-height:26px;}"
              "QPushButton:hover{background:#e74c3c;color:#fff;}")

        buttons = [
            ("\u2139", "اطلاعات شبکه", bs,
             lambda: self.parent_win.web.setUrl(QUrl(f"http://localhost:{PORT}/network-info"))),
            ("\u2013", "حداقل‌سازی", bs, lambda: self.parent_win.showMinimized()),
            ("\u25A1", "بزرگ‌نمایی", bs,
             lambda: self.parent_win.showNormal() if self.parent_win.isMaximized() else self.parent_win.showMaximized()),
            ("\u2715", "بستن", bc, self.parent_win.close),
        ]

        for text, tip, style, fn in buttons:
            btn = QPushButton(text)
            btn.setToolTip(tip)
            btn.setStyleSheet(style)
            btn.clicked.connect(fn)
            layout.addWidget(btn)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.drag_pos = e.globalPosition().toPoint() - self.parent_win.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if self.drag_pos and e.buttons() == Qt.MouseButton.LeftButton:
            self.parent_win.move(e.globalPosition().toPoint() - self.drag_pos)

    def mouseReleaseEvent(self, e):
        self.drag_pos = None

    def mouseDoubleClickEvent(self, e):
        if self.parent_win.isMaximized():
            self.parent_win.showNormal()
        else:
            self.parent_win.showMaximized()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("سیستم مدیریت آموزشگاه - Academy Manager Pro v1.0")
        self.setMinimumSize(1024, 700)
        self.resize(1440, 900)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)

        # آیکون پنجره
        icon_path = os.path.join(BASE_DIR, 'static', 'images', 'icon.ico')
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        central = QWidget()
        central.setObjectName("central")
        self.setCentralWidget(central)
        ml = QVBoxLayout(central)
        ml.setContentsMargins(0, 0, 0, 0)
        ml.setSpacing(0)

        self.title_bar = TitleBar(self)
        ml.addWidget(self.title_bar)

        # نوار ابزار
        tb = QWidget()
        tb.setFixedHeight(38)
        tb.setObjectName("toolbar")
        tbl = QHBoxLayout(tb)
        tbl.setContentsMargins(10, 0, 10, 0)
        tbl.setSpacing(4)

        tbs = ("QPushButton{border:none;background:rgba(255,255,255,.04);"
               "color:#78909c;font-size:15px;border-radius:5px;"
               "min-width:30px;max-width:30px;min-height:26px;max-height:26px;}"
               "QPushButton:hover{background:rgba(255,255,255,.1);color:#fff;}")

        self.btn_back = QPushButton("\u2190")
        self.btn_back.setToolTip("بازگشت")
        self.btn_back.setStyleSheet(tbs)
        tbl.addWidget(self.btn_back)

        self.btn_fwd = QPushButton("\u2192")
        self.btn_fwd.setToolTip("جلو")
        self.btn_fwd.setStyleSheet(tbs)
        tbl.addWidget(self.btn_fwd)

        self.btn_ref = QPushButton("\u21BB")
        self.btn_ref.setToolTip("بازخوانی")
        self.btn_ref.setStyleSheet(tbs)
        tbl.addWidget(self.btn_ref)

        self.btn_home = QPushButton("\u2302")
        self.btn_home.setToolTip("خانه")
        self.btn_home.setStyleSheet(tbs)
        tbl.addWidget(self.btn_home)

        # دکمه مرورگر
        self.btn_browser = QPushButton("\U0001F310")
        self.btn_browser.setToolTip("باز کردن در مرورگر")
        self.btn_browser.setStyleSheet(tbs)
        tbl.addWidget(self.btn_browser)

        tbl.addSpacing(8)

        self.addr = QLabel(f"http://localhost:{PORT}")
        self.addr.setStyleSheet(
            "background:rgba(255,255,255,.05);color:#607d8b;"
            "font-size:10px;padding:5px 12px;border-radius:5px;"
            "font-family:Consolas,monospace;"
        )
        tbl.addWidget(self.addr)
        tbl.addStretch()
        ml.addWidget(tb)

        # وب‌ویو
        self.web = QWebEngineView()
        self.web.setPage(CustomPage(self.web))
        s = self.web.settings()
        s.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        s.setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, True)
        s.setAttribute(QWebEngineSettings.WebAttribute.PluginsEnabled, True)
        ml.addWidget(self.web)

        sb = QStatusBar()
        sb.setFixedHeight(22)
        sb.setObjectName("statusBar")
        sb.showMessage("در حال بارگذاری...")
        ml.addWidget(sb)
        self.status = sb

        # اتصال دکمه‌ها
        self.btn_back.clicked.connect(self.web.back)
        self.btn_fwd.clicked.connect(self.web.forward)
        self.btn_ref.clicked.connect(self.web.reload)
        self.btn_home.clicked.connect(lambda: self.web.setUrl(QUrl(f"http://localhost:{PORT}")))
        self.btn_browser.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl(f"http://localhost:{PORT}"))
        )
        self.web.urlChanged.connect(self._url_changed)
        self.web.loadFinished.connect(self._loaded)

        self._setup_tray()

        self.setStyleSheet("""
            #central{
                background:#0a1628;
                border:1px solid #1a2940;
                border-radius:8px;
            }
            #titleBar{
                background:qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 #0a1628,stop:1 #0d1f3c);
            }
            #toolbar{
                background:#0d1f3c;
                border-bottom:1px solid rgba(255,255,255,.04);
            }
            #statusBar{
                background:#0a1628;
                color:#455a64;
                font-size:10px;
                border-top:1px solid rgba(255,255,255,.04);
            }
            QMenu{
                background:#1e2d42;
                color:#cfd8dc;
                border:1px solid #2a3f55;
                border-radius:6px;
                padding:4px;
            }
            QMenu::item{padding:6px 24px;border-radius:4px;}
            QMenu::item:selected{background:#0d47a1;color:white;}
        """)

        self.web.setUrl(QUrl(f"http://localhost:{PORT}"))

    def _setup_tray(self):
        px = QPixmap(64, 64)
        px.fill(QColor(0, 0, 0, 0))
        p = QPainter(px)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        g = QLinearGradient(0, 0, 64, 64)
        g.setColorAt(0, QColor("#0d47a1"))
        g.setColorAt(1, QColor("#00c853"))
        p.setBrush(QBrush(g))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(0, 0, 64, 64, 12, 12)
        p.setPen(QPen(QColor("white")))
        p.setFont(QFont("Arial", 18, QFont.Weight.Bold))
        p.drawText(px.rect(), Qt.AlignmentFlag.AlignCenter, "AM")
        p.end()

        # آیکون تری
        icon_path = os.path.join(BASE_DIR, 'static', 'images', 'icon.ico')
        if os.path.exists(icon_path):
            tray_icon = QIcon(icon_path)
        else:
            tray_icon = QIcon(px)

        self.tray = QSystemTrayIcon(tray_icon, self)
        self.tray.setToolTip("سیستم مدیریت آموزشگاه - Academy Manager Pro")

        m = QMenu()
        m.addAction("نمایش پنجره", lambda: (self.showNormal(), self.activateWindow()))
        m.addAction("باز کردن در مرورگر", lambda: QDesktopServices.openUrl(QUrl(f"http://localhost:{PORT}")))
        m.addAction("اطلاعات شبکه", lambda: self.web.setUrl(QUrl(f"http://localhost:{PORT}/network-info")))
        m.addSeparator()
        m.addAction("پشتیبان‌گیری", lambda: self.web.setUrl(QUrl(f"http://localhost:{PORT}/panel/backup")))
        m.addSeparator()
        m.addAction("خروج", self._quit)

        self.tray.setContextMenu(m)
        self.tray.activated.connect(
            lambda r: self.showNormal() if r == QSystemTrayIcon.ActivationReason.DoubleClick else None
        )
        self.tray.show()

    def _url_changed(self, url):
        u = url.toString()
        self.addr.setText(u)
        if "network-info" in u:
            self.title_bar.title.setText("اطلاعات شبکه")
        elif "/my" in u:
            self.title_bar.title.setText("پورتال مدرس")
        elif "login" in u:
            self.title_bar.title.setText("ورود به سیستم")
        else:
            self.title_bar.title.setText("سیستم مدیریت آموزشگاه")

    def _loaded(self, ok):
        if ok:
            ip = get_local_ip()
            specs = f"{platform.system()} {platform.release()} | {platform.machine()}"
            self.status.showMessage(f"آماده | IP: {ip} | {specs}")
        else:
            self.status.showMessage("خطا — تلاش مجدد...")
            QTimer.singleShot(3000, self.web.reload)

    def _quit(self):
        reply = QMessageBox.question(
            self, 'خروج',
            'آیا می‌خواهید از برنامه خارج شوید؟',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.tray.hide()
            QApplication.quit()
            os._exit(0)

    def closeEvent(self, event):
        event.ignore()
        self._quit()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setApplicationName("AcademyManager")
    app.setApplicationDisplayName("سیستم مدیریت آموزشگاه")

    # فونت فارسی
    font_path = os.path.join(BASE_DIR, 'static', 'fonts', 'Vazirmatn-Black.woff2')
    if os.path.exists(font_path):
        from PyQt6.QtGui import QFontDatabase
        QFontDatabase.addApplicationFont(font_path)

    app.setFont(QFont("Vazirmatn", 10))

    # صفحه شروع
    px = QPixmap(400, 300)
    px.fill(QColor("#0a1628"))
    p = QPainter(px)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    # لوگو
    g = QLinearGradient(140, 40, 260, 160)
    g.setColorAt(0, QColor("#0d47a1"))
    g.setColorAt(1, QColor("#00c853"))
    p.setBrush(QBrush(g))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawRoundedRect(150, 40, 100, 100, 20, 20)
    p.setPen(QPen(QColor("white")))
    p.setFont(QFont("Arial", 28, QFont.Weight.Bold))
    p.drawText(150, 40, 100, 100, Qt.AlignmentFlag.AlignCenter, "AM")

    # عنوان
    p.setPen(QPen(QColor("#e0e0e0")))
    p.setFont(QFont("Arial", 16, QFont.Weight.Bold))
    p.drawText(0, 170, 400, 30, Qt.AlignmentFlag.AlignCenter, "Academy Manager Pro")

    p.setPen(QPen(QColor("#546e7a")))
    p.setFont(QFont("Arial", 10))
    p.drawText(0, 200, 400, 20, Qt.AlignmentFlag.AlignCenter, "سیستم مدیریت آموزشگاه")
    p.drawText(0, 225, 400, 20, Qt.AlignmentFlag.AlignCenter, "در حال بارگذاری...")

    # نوار پیشرفت
    p.setBrush(QBrush(QColor("#1a2940")))
    p.drawRoundedRect(100, 260, 200, 8, 4, 4)
    p.setBrush(QBrush(QColor("#00c853")))
    p.drawRoundedRect(100, 260, 60, 8, 4, 4)

    p.end()

    splash = QSplashScreen(px)
    splash.show()
    app.processEvents()

    win = MainWindow()
    win.show()
    splash.finish(win)

    sys.exit(app.exec())
