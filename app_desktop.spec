# -*- mode: python ; coding: utf-8 -*-
import os

block_cipher = None
base_dir = os.path.dirname(os.path.abspath(SPEC))

a = Analysis(
    ['app_desktop.py'],
    pathex=[base_dir],
    binaries=[],
    datas=[
        (os.path.join(base_dir, 'templates'), 'templates'),
        (os.path.join(base_dir, 'static'), 'static'),
        (os.path.join(base_dir, 'models'), 'models'),
        (os.path.join(base_dir, 'routes'), 'routes'),
        (os.path.join(base_dir, 'utils'), 'utils'),
        (os.path.join(base_dir, 'extensions.py'), '.'),
        (os.path.join(base_dir, 'app.py'), '.'),
        (os.path.join(base_dir, 'config.py'), '.'),
        (os.path.join(base_dir, 'import_rahs_data.py'), '.'),
        (os.path.join(base_dir, 'settings.json'), '.') if os.path.exists(os.path.join(base_dir, 'settings.json')) else ('.', '.'),
        (os.path.join(base_dir, 'first_run.py'), '.') if os.path.exists(os.path.join(base_dir, 'first_run.py')) else ('.', '.'),
        (os.path.join(base_dir, 'README.md'), '.') if os.path.exists(os.path.join(base_dir, 'README.md')) else ('.', '.'),
    ],
    hiddenimports=[
        'flask', 'flask_sqlalchemy', 'flask_login', 'flask_wtf',
        'flask_migrate', 'jdatetime', 'requests', 'reportlab',
        'PyQt6', 'PyQt6.QtWidgets', 'PyQt6.QtCore', 'PyQt6.QtGui',
        'PyQt6.QtWebEngineWidgets', 'PyQt6.QtWebEngineCore',
        'models', 'models.user', 'models.student', 'models.teacher',
        'models.course', 'models.classes', 'models.registration',
        'models.finance', 'models.accounting', 'models.attendance',
        'models.exam', 'models.system',
        'routes', 'routes.auth', 'routes.dashboard', 'routes.students',
        'routes.teachers', 'routes.classes', 'routes.registration',
        'routes.attendance', 'routes.exams', 'routes.finance',
        'routes.accounting', 'routes.settings', 'routes.reports',
        'routes.messaging', 'routes.additional', 'routes.features',
        'routes.features2', 'routes.new_features', 'routes.final',
        'routes.demo', 'routes.settings_panel', 'routes.network_info',
        'routes.payroll', 'routes.tax', 'routes.permissions',
        'routes.teacher_portal', 'routes.setup',
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'numpy', 'scipy', 'pandas',
              'PySide6', 'PySide2', 'PyQt5', 'PyQt4'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,   # <-- folder mode, not single-file
    name='AcademyManager',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,           # <-- no console window (GUI app)
    icon=os.path.join(base_dir, 'static', 'images', 'icon.ico') if os.path.exists(os.path.join(base_dir, 'static', 'images', 'icon.ico')) else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='AcademyManager',
)
