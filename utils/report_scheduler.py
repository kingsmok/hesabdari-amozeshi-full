"""Generation and delivery of recurring reports."""
from __future__ import annotations

import json
import os
import smtplib
from time import time as unix_time
from datetime import datetime, timedelta
from email.message import EmailMessage
from pathlib import Path

from flask import current_app

from extensions import db
from utils.jalali import gregorian_to_jalali
from utils.local_time import local_now_naive
from utils.report_exports import write_export_file
from utils.reporting import (
    REPORT_CATALOG, REPORT_STATUS_VALUES, ReportFilters, can_view_report,
    default_date_range, run_report,
)


def next_run(moment: datetime, frequency: str, schedule_day: int | None = None) -> datetime:
    """Return the next run; monthly recurrence follows the Jalali calendar."""
    if frequency == 'daily':
        return moment + timedelta(days=1)
    if frequency == 'weekly':
        return moment + timedelta(days=7)
    try:
        import jdatetime
        current = jdatetime.date.fromgregorian(date=moment.date())
        year = current.year + (1 if current.month == 12 else 0)
        month = 1 if current.month == 12 else current.month + 1
        day = max(1, min(int(schedule_day or current.day), 31))
        while day:
            try:
                target = jdatetime.date(year, month, day).togregorian()
                return datetime.combine(target, moment.time())
            except ValueError:
                day -= 1
    except (ImportError, TypeError, ValueError, OverflowError):
        pass
    # Defensive fallback for installations with a missing calendar dependency.
    return moment + timedelta(days=30)


def _filters(schedule) -> dict:
    try:
        value = json.loads(schedule.filters_json or '{}')
        return value if isinstance(value, dict) else {}
    except (TypeError, ValueError):
        return {}


def _send_email(recipient: str, subject: str, body: str, path: Path) -> None:
    host = os.environ.get('SMTP_HOST', '').strip()
    if not host:
        raise RuntimeError('SMTP_HOST برای ارسال ایمیل تنظیم نشده است')
    port = int(os.environ.get('SMTP_PORT', '587'))
    username = os.environ.get('SMTP_USER', '').strip()
    password = os.environ.get('SMTP_PASSWORD', '')
    sender = os.environ.get('SMTP_FROM', username).strip()
    if not sender or not recipient:
        raise RuntimeError('نشانی فرستنده یا گیرنده ایمیل مشخص نیست')
    message = EmailMessage()
    message['From'] = sender
    message['To'] = recipient
    message['Subject'] = subject
    message.set_content(body)
    message.add_attachment(path.read_bytes(), maintype='application', subtype='octet-stream', filename=path.name)
    with smtplib.SMTP(host, port, timeout=30) as smtp:
        if os.environ.get('SMTP_TLS', '1') != '0':
            smtp.starttls()
        if username:
            smtp.login(username, password)
        smtp.send_message(message)


def _deliver_bot(method: str, recipient: str, path: Path, caption: str) -> None:
    from models.system import SystemSettings
    from utils.bot_services import send_bot_document
    settings = SystemSettings.query.first()
    token = ''
    if method == 'bale':
        token = (settings.bale_bot_token or '').strip() if settings else ''
        if not recipient and settings:
            recipient = ((settings.backup_bot_chat_id or '').split(',')[0]).strip()
    else:
        token = (settings.telegram_bot_token or '').strip() if settings else ''
    if not token or not recipient:
        raise RuntimeError('توکن ربات یا شناسه گیرنده تنظیم نشده است')
    response = send_bot_document(method, token, recipient, str(path), caption=caption)
    if not response.get('ok'):
        raise RuntimeError(response.get('description') or 'ارسال فایل به ربات ناموفق بود')


def deliver_schedule(schedule, *, advance: bool = True) -> Path:
    """Generate immediately; optionally consume the scheduled occurrence."""
    from models.reporting import ReportExportLog
    from models.system import Notification

    now = local_now_naive()
    path = None
    try:
        meta = REPORT_CATALOG.get(schedule.report_key)
        if not meta:
            raise RuntimeError('گزارش زمان‌بندی‌شده دیگر وجود ندارد')
        owner = schedule.user
        if owner is None or not owner.is_active:
            raise RuntimeError('مالک این زمان‌بندی غیرفعال یا حذف شده است')
        from license_client import has_feature
        if not has_feature('export_data'):
            raise RuntimeError('قابلیت خروجی گرفتن در لایسنس فعال نیست')
        if (not owner.is_admin and
                not owner.has_permission('reports', 'export')):
            raise RuntimeError('مجوز خروجی گرفتن مالک این زمان‌بندی لغو شده است')
        if not can_view_report(owner, meta):
            raise RuntimeError('مجوز مالک برای اجرای این گزارش لغو شده است')
        filter_values = _filters(schedule)
        raw_columns = filter_values.pop('columns', '')
        if isinstance(raw_columns, str):
            column_keys = [key[:80] for key in raw_columns.split(',')[:100] if key]
        elif isinstance(raw_columns, list):
            column_keys = [str(key)[:80] for key in raw_columns[:100] if key]
        else:
            column_keys = []
        if ('date' in meta.get('filters', ()) and
                'date_from' not in filter_values and 'date_to' not in filter_values):
            default_from, default_to = default_date_range()
            if meta.get('date_mode') == 'as_of':
                filter_values['date_to'] = default_to
            else:
                filter_values['date_from'], filter_values['date_to'] = default_from, default_to
        allowed_statuses = REPORT_STATUS_VALUES.get(meta.get('builder'), ())
        if (filter_values.get('status') not in ('', None) and
                filter_values.get('status') not in allowed_statuses):
            filter_values.pop('status', None)
        filters = ReportFilters.from_mapping(filter_values, owner)
        # Report rows contain internal links.  A background task has no request,
        # therefore provide a lightweight local request context for url_for.
        with current_app.test_request_context('/'):
            result = run_report(schedule.report_key, filters, paginate=False)
        folder = Path(current_app.instance_path) / 'report_exports'
        path = write_export_file(result, schedule.export_format, folder, column_keys or None)
        caption = f'گزارش {meta["title"]} — {gregorian_to_jalali(now)} {now:%H:%M}'
        if schedule.delivery_method in ('bale', 'telegram'):
            _deliver_bot(schedule.delivery_method, schedule.recipient or '', path, caption)
        elif schedule.delivery_method == 'email':
            _send_email(schedule.recipient or '', caption, 'گزارش زمان‌بندی‌شده در پیوست قرار دارد.', path)
        exported_rows = len(result['rows'])
        export_log = ReportExportLog(
            user_id=schedule.user_id, report_key=schedule.report_key,
            export_format=schedule.export_format, row_count=exported_rows,
            status='completed', file_name=path.name,
        )
        db.session.add(export_log)
        db.session.flush()
        if schedule.delivery_method == 'internal':
            row_message = f'{exported_rows} ردیف'
            if result['total_rows'] > exported_rows:
                row_message += f' از {result["total_rows"]} نتیجه'
            db.session.add(Notification(
                user_id=schedule.user_id,
                title=f'گزارش «{meta["title"]}» آماده شد',
                body=f'فایل {path.name} با {row_message} ساخته شد.',
                notif_type='report', reference_type='report_export',
                reference_id=export_log.id,
            ))
        schedule.last_run_at = now
        schedule.last_status = 'completed'
        schedule.last_error = None
        if advance:
            schedule.next_run_at = next_run(max(schedule.next_run_at, now), schedule.frequency,
                                            schedule.schedule_day)
        db.session.commit()
        return path
    except Exception as exc:
        db.session.rollback()
        schedule.last_run_at = now
        schedule.last_status = 'failed'
        schedule.last_error = str(exc)[:2000]
        if advance:
            schedule.next_run_at = next_run(max(schedule.next_run_at, now), schedule.frequency,
                                            schedule.schedule_day)
        db.session.add(schedule)
        db.session.add(ReportExportLog(
            user_id=schedule.user_id, report_key=schedule.report_key,
            export_format=schedule.export_format, status='failed',
            file_name=path.name if path and path.exists() else None,
            error_message=str(exc)[:2000],
        ))
        db.session.commit()
        raise


def run_due_report_schedules() -> dict:
    """Claim and run due jobs once, even when multiple app workers are alive."""
    from license_client import has_feature
    if not has_feature('reports') or not has_feature('export_data'):
        return {'due': 0, 'claimed': 0, 'completed': 0, 'failed': []}
    from models.reporting import ReportSchedule
    now = local_now_naive()
    stale_before = now - timedelta(hours=1)
    claimable = db.or_(
        ReportSchedule.last_status.is_(None),
        ReportSchedule.last_status != 'running',
        ReportSchedule.last_run_at.is_(None),
        ReportSchedule.last_run_at < stale_before,
    )
    candidate_ids = [row[0] for row in (db.session.query(ReportSchedule.id).filter(
        ReportSchedule.is_active.is_(True), ReportSchedule.next_run_at <= now, claimable
    ).order_by(ReportSchedule.next_run_at).limit(20).all())]

    completed = 0
    claimed_count = 0
    failures = []
    for schedule_id in candidate_ids:
        # The conditional UPDATE is the cross-worker lock.  A second worker
        # sees zero affected rows after the first one commits its claim.
        claimed = (ReportSchedule.query.filter(
            ReportSchedule.id == schedule_id,
            ReportSchedule.is_active.is_(True),
            ReportSchedule.next_run_at <= now,
            db.or_(
                ReportSchedule.last_status.is_(None),
                ReportSchedule.last_status != 'running',
                ReportSchedule.last_run_at.is_(None),
                ReportSchedule.last_run_at < stale_before,
            ),
        ).update({
            ReportSchedule.last_status: 'running',
            ReportSchedule.last_run_at: now,
        }, synchronize_session=False))
        db.session.commit()
        if not claimed:
            continue
        claimed_count += 1
        schedule = db.session.get(ReportSchedule, schedule_id)
        try:
            deliver_schedule(schedule)
            completed += 1
        except Exception as exc:
            failures.append({'id': schedule_id, 'error': str(exc)})
    _cleanup_old_exports()
    return {'due': len(candidate_ids), 'claimed': claimed_count,
            'completed': completed, 'failed': failures}


def _cleanup_old_exports(days: int = 30) -> None:
    folder = Path(current_app.instance_path) / 'report_exports'
    if not folder.exists():
        return
    cutoff = unix_time() - days * 86400
    removed = []
    for path in folder.iterdir():
        try:
            if path.is_file() and path.stat().st_mtime < cutoff:
                path.unlink()
                removed.append(path.name)
        except OSError:
            continue
    if removed:
        try:
            from models.reporting import ReportExportLog
            for offset in range(0, len(removed), 900):
                (ReportExportLog.query.filter(
                    ReportExportLog.file_name.in_(removed[offset:offset + 900])
                ).update({ReportExportLog.file_name: None}, synchronize_session=False))
            db.session.commit()
        except Exception:
            db.session.rollback()
