"""
بوت‌استرپ پیکربندی — نقطهٔ واحد اعمال کانفیگ + لاگر + پوشه‌های داده.
"""
from __future__ import annotations

import os

from utils.config_loader import apply_to_app, build_config
from utils.logging_config import configure_app_logging


def setup(app):
    """کانفیگ کامل و پوشه‌های runtime؛ خروجی: مسیرهای پایه (base_dir)."""
    config, paths = build_config()
    apply_to_app(app, config, paths)
    configure_app_logging(app)
    # پوشه‌هایی که در زمان اجرا نوشته‌شدنی‌اند؛ هر جا هم که باشند ساخته می‌شوند
    for key in ('UPLOAD_FOLDER', 'BACKUP_FOLDER'):
        os.makedirs(app.config[key], exist_ok=True)
    return paths
