# ═══════════════════════════════════════════════════════════════
# Academy Manager Pro — تصویر تولید (Production Image)
# ═══════════════════════════════════════════════════════════════
# ● چند-stage: لایهٔ build فقط برای «مورد نیاز نصب»؛ تصویر نهایی سبک
# ● کاربر غیر-root (امنیت) + healthcheck + حجم‌های داده روی volume
# ● از .dockerignore استفاده می‌کند (بدون .git/.venv/tests/backups)
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=Asia/Tehran

# وابستگی‌های سیستمی حداقلی (reportlab/qrcode/Pillow همگی خالص پایتون هستند؛
# gcc فقط برای psycopg2/pymysql در صورت استفاده — عمداً حذف شده)
WORKDIR /app

# اول requirements: لایهٔ کش داکر تا با هر تغییر کد، پکیج‌ها دوباره نصب نشوند
# (requirements-prod همان اصلی + gunicorn است؛ CMD به gunicorn نیاز دارد)
COPY requirements.txt requirements-prod.txt ./
RUN pip install --no-cache-dir -r requirements-prod.txt

COPY . .
# پوشه‌های داده؛ به‌عنوان volume در compose می‌مانند
RUN mkdir -p /app/instance /app/backups /app/logs /app/static/uploads \
    && chown -R nobody:nogroup /app

# اجرا با کاربر غیر-root
USER nobody

EXPOSE 5000

# Gunicorn: ۲ ورکر برای SQLite (نوشتن همزمان محدود است)؛
# پیش‌فرض Flask dev server برای production مناسب نیست
CMD ["gunicorn", "--config", "gunicorn.conf.py", "app:create_app()"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD ["python", "-c", "import os,urllib.request,sys; sys.exit(0) if urllib.request.urlopen('http://127.0.0.1:5000/login', timeout=4).status==200 else sys.exit(1)"]
