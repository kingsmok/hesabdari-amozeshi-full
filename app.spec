# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller specification — Hesabdari Rahsa (Flask backend + PyQt6 desktop shell)

Build:      pyinstaller --noconfirm --clean app.spec
Output:     dist/AcademyManager/AcademyManager.exe   (onedir layout)

Design notes
------------
* onedir (NOT onefile): the Flask app writes to instance/, backups/ and
  static/uploads/ next to the executable, and the auto-updater patches
  individual files in place. A single-file bundle would unpack to a temp
  folder on every run and break both.
* templates/ and static/ are shipped as real folders so Jinja and the
  updater can see (and replace) them.
* console=False: the PyQt6 window is the only user interface.
"""
import os

# ── Paths ────────────────────────────────────────────────────────────────
BASE_DIR = SPECPATH                                        # noqa: F821 (injected by PyInstaller)
ENTRY_SCRIPT = os.path.join(BASE_DIR, 'app_desktop.py')
ICON_FILE = os.path.join(BASE_DIR, 'static', 'images', 'icon.ico')

APP_NAME = 'AcademyManager'


def data_file(relative, target='.'):
    """Include an optional file only when it exists (keeps the build reproducible)."""
    absolute = os.path.join(BASE_DIR, relative)
    return (absolute, target) if os.path.exists(absolute) else None


def data_tree(relative):
    """Include a whole folder, preserving its name inside the bundle."""
    absolute = os.path.join(BASE_DIR, relative)
    return (absolute, relative.replace('\\', '/')) if os.path.isdir(absolute) else None


# ── Data files shipped next to the executable ────────────────────────────
datas = [item for item in (
    # Flask needs these two as real directories
    data_tree('templates'),
    data_tree('static'),

    # Application packages (imported dynamically by blueprints / services)
    data_tree('models'),
    data_tree('routes'),
    data_tree('utils'),
    # Composition root's bootstrapping modules (bootstrap/*, imported lazily
    # inside create_app — PyInstaller's static analysis may miss them)
    data_tree('bootstrap'),

    # Top level modules the desktop shell imports at runtime
    data_file('app.py'),
    data_file('config.py'),
    data_file('extensions.py'),
    data_file('first_run.py'),
    data_file('import_rahs_data.py'),

    # License + auto-update subsystem
    data_file('license_client.py'),
    data_file('license_features.py'),
    data_file('license_updater.py'),
    data_file('check_license_server.py'),

    # Metadata / defaults
    data_file('VERSION'),
    data_file('config.ini'),          # written by the installer; optional in dev
    # NOTE: settings.json is deliberately NOT bundled - it is per installation
    #       and is generated at first launch from config.ini + defaults.
    data_file('README.md'),
) if item]


# ── Hidden imports ───────────────────────────────────────────────────────
# Flask extensions and Qt modules are resolved at runtime, so PyInstaller's
# static analysis cannot always find them.
hiddenimports = [
    # Flask stack
    'flask', 'flask_sqlalchemy', 'flask_login', 'flask_wtf', 'flask_migrate',
    'flask_babel', 'wtforms', 'werkzeug', 'werkzeug.security',
    'jinja2', 'jinja2.ext', 'itsdangerous', 'click', 'blinker',
    'sqlalchemy', 'sqlalchemy.dialects.sqlite', 'sqlalchemy.dialects.sqlite.pysqlite',
    'sqlalchemy.sql.default_comparator',

    # PyQt6 (desktop shell + embedded browser)
    'PyQt6', 'PyQt6.QtCore', 'PyQt6.QtGui', 'PyQt6.QtWidgets',
    'PyQt6.QtNetwork', 'PyQt6.QtPrintSupport',
    'PyQt6.QtWebEngineCore', 'PyQt6.QtWebEngineWidgets', 'PyQt6.QtWebChannel',
    'PyQt6.sip',

    # Third-party runtime dependencies
    'jdatetime', 'dateutil', 'requests', 'chardet',
    'reportlab', 'reportlab.pdfbase', 'reportlab.pdfbase.ttfonts',
    'arabic_reshaper', 'bidi', 'bidi.algorithm',
    'openpyxl', 'qrcode', 'PIL', 'PIL.Image',
    'apscheduler', 'apscheduler.schedulers.background',
    'apscheduler.triggers.interval', 'pytz', 'tzlocal', 'six',

    # Cryptography — used for license signature verification and sealed cache
    'cryptography', 'cryptography.fernet',
    'cryptography.hazmat.primitives.hashes',
    'cryptography.hazmat.primitives.serialization',
    'cryptography.hazmat.primitives.asymmetric.padding',
    'cryptography.hazmat.backends.openssl',

    # Standard library modules imported lazily by the app
    'configparser', 'sqlite3', 'zipfile', 'hashlib', 'hmac', 'secrets',

    # Application modules
    'app', 'config', 'extensions', 'first_run',
    'license_client', 'license_features', 'license_updater',
]

# Blueprints, models and services are imported by name inside create_app(),
# so collect every module of these packages explicitly.
for package in ('routes', 'models', 'utils', 'bootstrap'):
    package_dir = os.path.join(BASE_DIR, package)
    if not os.path.isdir(package_dir):
        continue
    hiddenimports.append(package)
    for filename in sorted(os.listdir(package_dir)):
        if filename.endswith('.py') and not filename.startswith('__'):
            hiddenimports.append(f'{package}.{filename[:-3]}')


# ── Analysis ─────────────────────────────────────────────────────────────
a = Analysis(                                              # noqa: F821
    [ENTRY_SCRIPT],
    pathex=[BASE_DIR],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Keep the bundle small and avoid Qt binding conflicts
    excludes=[
        'tkinter', 'matplotlib', 'numpy', 'scipy', 'pandas', 'IPython',
        'PySide2', 'PySide6', 'PyQt5', 'pytest',
        # Optional server-side database drivers (config.py imports them lazily
        # inside try/except ImportError - the desktop edition uses SQLite).
        'psycopg2', 'psycopg2-binary', 'pymysql',
    ],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)                           # noqa: F821

exe = EXE(                                                 # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,          # onedir: binaries live in COLLECT
    name=APP_NAME,
    # PyInstaller >= 6 puts the payload in "_internal" by default. The whole
    # application (config.py, first_run.py, app_desktop.py, the updater and the
    # installer) resolves its paths from dirname(sys.executable), so keep the
    # classic FLAT onedir layout: templates/, static/, instance/, config.ini
    # all live next to AcademyManager.exe.
    contents_directory='.',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,                      # UPX corrupts some Qt6 DLLs — keep it off
    console=False,                  # hide the Windows console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=ICON_FILE if os.path.exists(ICON_FILE) else None,
)

coll = COLLECT(                                            # noqa: F821
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name=APP_NAME,
)
