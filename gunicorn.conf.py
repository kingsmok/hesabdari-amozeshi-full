"""پیکربندی Gunicorn برای میزبانی تولید — Academy Manager Pro

نکات مهم برای این پروژه:
  • SQLite هم‌زمانی نوشتن محدودی دارد ⇒ ورکرها را زیاد نکنید (۲ کافی است).
  • APScheduler پشتیبان‌گیری در هر ورکر بالا می‌آید؛ `ACADEMY_DISABLE_SCHEDULER=1`
    را روی همهٔ ورکرها به‌جز یکی (یا همه) بگذارید — این‌جا همه خاموش شده و
    اجرای پشتیبان به CRON هاست سپرده می‌شود.
  • `timeout=120` برای گزارش‌های سنگین (PDF/Excel) — زیر آن ورکر کُشته می‌شود.
"""
import os

bind = '0.0.0.0:5000'


def _default_workers():
    """SQLite ⇒ حداکثر ۲؛ روی RAM کم فقط ۱ تا OOM/۵۰۰ ندهد."""
    try:
        from utils.runtime_profile import is_low_resource
        if is_low_resource():
            return 1
    except Exception:
        pass
    return 2


workers = int(os.environ.get('GUNICORN_WORKERS', _default_workers()))
worker_class = 'gthread'
_default_threads = 2 if workers == 1 else 4
threads = int(os.environ.get('GUNICORN_THREADS', _default_threads))
timeout = int(os.environ.get('GUNICORN_TIMEOUT', 120))
graceful_timeout = 30
keepalive = 5
max_requests = int(os.environ.get('GUNICORN_MAX_REQUESTS', 400 if workers == 1 else 1000))
max_requests_jitter = 50
accesslog = '-'              # در Docker به stdout (لاگ متمرکز)
errorlog = '-'
loglevel = os.environ.get('GUNICORN_LOG_LEVEL', 'info')

# زمان‌بند داخلی در همهٔ ورکرها خاموش می‌شود؛ پشتیبان‌گیری خودکار را CRON اجرا کند
if 'ACADEMY_DISABLE_SCHEDULER' not in os.environ:
    os.environ['ACADEMY_DISABLE_SCHEDULER'] = '1'

def on_starting(server):
    server.log.info('Academy Manager Pro — gunicorn starting (workers=%s)', workers)
