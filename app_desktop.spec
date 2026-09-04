# -*- mode: python ; coding: utf-8 -*-
"""
اسپک نسخه دسکتاپ — واگذارشده به `app.spec`

پیش‌تر این فایل یک Analysis مستقل داشت و به‌تدریج از `app.spec` افتاد:
hiddenimports مربوط به `apscheduler`/`pytz`/`tzlocal` و ماژول‌های
`routes.backup_center`، `routes.bot_panel`، `models.bot` در آن نبود — یعنی در
exe دسکتاپ، پشتیبان‌گیری خودکار و پنل ربات می‌توانستند بی‌صدا از کار بیفتند
(`app.py` هنگام اجرا `BackgroundScheduler` را import می‌کند).

اینجا همان `app.spec` اجرا می‌شود تا یک منبع حقیقت بماند:

    pyinstaller --noconfirm --clean app_desktop.spec     # معادل app.spec
"""
import os

_app_spec = os.path.join(SPECPATH, 'app.spec')      # noqa: F821 (تزریق PyInstaller)
with open(_app_spec, encoding='utf-8') as _fh:
    exec(compile(_fh.read(), _app_spec, 'exec'))
