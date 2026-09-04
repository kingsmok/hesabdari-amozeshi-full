"""پیکربندی Gunicorn برای میزبانی تولید — Academy Manager Pro

نکات مهم برای این پروژه:
  • SQLite هم‌زمانی نوشتن محدودی دارد ⇒ ورکرها را زیاد نکنید (۲ کافی است).
  • APScheduler پشتیبان‌گیری در هر ورکر بالا می‌آید؛ `ACADEMY_DISABLE_SCHEDULER=1`
    را روی همهٔ ورکرها به‌جز یکی (یا همه) بگذارید — این‌جا همه خاموش شده و
    اجرای پشتیبان به CRON هاست سپرده می‌شود.
  • `timeout=120` برای گزارش‌های سنگین (PDF/Excel) — زیر آن ورکر کُشته می‌شود.
"""
import multiprocessing
import os

bind = '0.0.0.0:5000'
# SQLite ⇒ ۲ ورکر؛ برای MySQL/PostgreSQL می‌توانید تا (CPU×2)+1 بالا ببرید
workers = int(os.environ.get('GUNICORN_WORKERS', 2))
worker_class = 'gthread'
threads = int(os.environ.get('GUNICORN_THREADS', 4))
timeout = int(os.environ.get('GUNICORN_TIMEOUT', 120))
graceful_timeout = 30
keepalive = 5
max_requests = 1000          # راه‌اندازی مجدد تدریجی (جلوگیری از نشت تدریجی)
max_requests_jitter = 100
accesslog = '-'              # در Docker به stdout (لاگ متمرکز)
errorlog = '-'
loglevel = os.environ.get('GUNICORN_LOG_LEVEL', 'info')

# زمان‌بند داخلی در همهٔ ورکرها خاموش می‌شود؛ پشتیبان‌گیری خودکار را CRON اجرا کند
if 'ACADEMY_DISABLE_SCHEDULER' not in os.environ:
    os.environ['ACADEMY_DISABLE_SCHEDULER'] = '1'

def on_starting(server):
    server.log.info('Academy Manager Pro — gunicorn starting (workers=%s)', workers)
