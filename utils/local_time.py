"""Application-local clock helpers.

Database audit timestamps in the legacy application remain UTC. User-facing
report cut-offs and recurring schedules, however, are entered in Iran local
time and therefore use a single explicit timezone instead of the host clock.
"""
from __future__ import annotations

import os
from datetime import date, datetime

import pytz


DEFAULT_TIMEZONE = 'Asia/Tehran'


def timezone_name() -> str:
    candidate = os.environ.get('APP_TIMEZONE', DEFAULT_TIMEZONE).strip() or DEFAULT_TIMEZONE
    try:
        pytz.timezone(candidate)
        return candidate
    except pytz.UnknownTimeZoneError:
        return DEFAULT_TIMEZONE


def local_timezone():
    return pytz.timezone(timezone_name())


def local_now() -> datetime:
    """Return an aware datetime in the configured application timezone."""
    return datetime.now(local_timezone())


def local_now_naive() -> datetime:
    """Return local wall time for the application's existing naive DB columns."""
    return local_now().replace(tzinfo=None)


def local_today() -> date:
    return local_now().date()
