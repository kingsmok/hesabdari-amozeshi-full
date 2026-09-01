"""Passenger WSGI entry for cPanel / shared hosting (Python 3.11)."""
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# قبل از import برنامه علامت هاست را می‌گذاریم تا startup_checks
# هرگز pip یا input() را روی Passenger اجرا نکند.
os.environ.setdefault("PASSENGER_APP_ENV", os.environ.get("PASSENGER_APP_ENV", "production"))

from app import create_app

application = create_app()
