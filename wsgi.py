"""WSGI entry point for Linux/shared hosts (Apache/mod_wsgi, Gunicorn, Passenger).

هدف هاست: Python 3.11 — بدون pip خودکار و بدون input().

  • روی VPS:  gunicorn --config gunicorn.conf.py wsgi:application
  • روی Docker: همان ایمیج از app:create_app استفاده می‌کند (معادل است)
"""
import os
import sys
import traceback

# Ensure project root is on path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

try:
    from app import create_app

    application = create_app()
except Exception:
    try:
        _log_dir = os.path.join(BASE_DIR, "logs")
        os.makedirs(_log_dir, exist_ok=True)
        with open(os.path.join(_log_dir, "passenger_error.log"), "a", encoding="utf-8") as _fh:
            _fh.write("=" * 70 + "\n")
            _fh.write(traceback.format_exc())
    except OSError:
        pass
    raise
