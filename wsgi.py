"""WSGI entry point for Linux/shared hosts (Apache/mod_wsgi, Gunicorn, Passenger).

هدف هاست: Python 3.11 — بدون pip خودکار و بدون input().
"""
import os
import sys

# Ensure project root is on path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from app import create_app

application = create_app()
