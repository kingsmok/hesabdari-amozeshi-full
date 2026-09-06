"""قفل فایل بین‌پروسه‌ای — برای کارهایی که فقط یک پردازه باید انجام دهد.

چرا لازم شد:
  با `gunicorn --workers 2` هر دو ورکر هم‌زمان `create_app()` را اجرا می‌کنند
  و هر دو `db.create_all()` و `create_default_data()` را صدا می‌زنند. روی نصب
  تازه، یکی از آن‌ها با `UNIQUE constraint failed: users.username` (یا
  «table already exists») می‌میرد و gunicorn مجبور است ورکر را دوباره بالا
  بیاورد ⇒ شروع کند و لرزان روی هاست.

`flock`/`msvcrt` انتخاب شده چون با مرگ پردازه **خودبه‌خود** آزاد می‌شود؛
قفل‌های مبتنی بر `O_CREAT|O_EXCL` بعد از crash تا ابد می‌مانند.
"""
from __future__ import annotations

import contextlib
import os
import time

try:
    import fcntl
except ImportError:                     # Windows
    fcntl = None
try:
    import msvcrt
except ImportError:                     # POSIX
    msvcrt = None


@contextlib.contextmanager
def file_lock(path: str, timeout: float = 60.0, poll: float = 0.05):
    """قفل انحصاری روی `path` تا پایان بلوک `with`.

    اگر قفل گرفتن ممکن نباشد (پوشه فقط‌خواندنی، پلتفرم بدون fcntl/msvcrt)
    بی‌صدا بدون قفل ادامه می‌دهد — بدترین حالت همان رفتار قبلی است، نه خرابی.
    اگر تا `timeout` آزاد نشد هم ادامه می‌دهد (بوت هرگز hang نمی‌شود).
    """
    handle = None
    try:
        os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
        handle = open(path, 'a+')
    except OSError:
        yield False
        return

    acquired = False
    try:
        if fcntl is not None:
            deadline = time.monotonic() + timeout
            while True:
                try:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    acquired = True
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        break
                    time.sleep(poll)
        elif msvcrt is not None:
            deadline = time.monotonic() + timeout
            while True:
                try:
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                    acquired = True
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        break
                    time.sleep(poll)
        yield acquired
    finally:
        try:
            if acquired and fcntl is not None:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        try:
            handle.close()               # msvcrt هم با بستن فایل آزاد می‌شود
        except OSError:
            pass
