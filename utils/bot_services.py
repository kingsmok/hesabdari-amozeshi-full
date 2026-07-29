"""منطق مشترک ربات‌ها و دریافت پیام بله با Long Polling (بدون وب‌هوک)."""
from __future__ import annotations

import re
import threading
import time
from datetime import datetime

import requests


def _normalize_phone(value: str) -> str | None:
    digits = re.sub(r'\D', '', value or '')
    if digits.startswith('0098'):
        digits = '0' + digits[4:]
    elif digits.startswith('98') and len(digits) == 12:
        digits = '0' + digits[2:]
    elif len(digits) == 10 and digits.startswith('9'):
        digits = '0' + digits
    return digits if re.fullmatch(r'09\d{9}', digits) else None


def build_academy_bot_response(text: str) -> str:
    """پاسخ ربات تلگرام/بله برای دستورات، موبایل و نام دوره."""
    from models.course import Course
    from models.registration import Registration
    from models.student import Student

    text = (text or '').strip()
    if not text or text in ('/start', '/help'):
        return (
            '🎓 به ربات آموزشگاه خوش آمدید!\n\n'
            '📱 شماره موبایل خود را ارسال کنید تا کلاس‌ها و مانده شهریه را ببینید.\n'
            '📚 نام دوره را ارسال کنید تا اطلاعات دوره نمایش داده شود.\n'
            'مثال: 09121234567 یا حسابداری'
        )

    phone = _normalize_phone(text)
    if phone:
        student = Student.query.filter(
            (Student.mobile == phone) | (Student.mobile2 == phone)
        ).first()
        if not student:
            return '❌ هنرجویی با این شماره موبایل یافت نشد.'

        registrations = Registration.query.filter_by(student_id=student.id, status='active').all()
        if not registrations:
            return f'👤 {student.full_name}\nثبت‌نام فعالی برای شما ثبت نشده است.'

        lines = [f'👤 {student.full_name} ({student.student_code})', '', '📚 کلاس‌های فعال شما:']
        for registration in registrations:
            class_group = registration.class_group
            course = registration.course
            start_time = class_group.start_time if class_group else '-'
            end_time = class_group.end_time if class_group else '-'
            lines.extend([
                f'• {course.title if course else "-"}',
                f'  کلاس: {class_group.name if class_group else "-"}',
                f'  مدرس: {class_group.teacher.full_name if class_group and class_group.teacher else "-"}',
                f'  ساعت: {start_time or "-"} تا {end_time or "-"}',
                f'  مانده شهریه: {(registration.remaining_amount or 0):,.0f} تومان',
            ])
        return '\n'.join(lines)

    course = Course.query.filter(Course.title.contains(text), Course.is_active.is_(True)).first()
    if not course:
        return '🔍 موردی پیدا نشد. نام دوره یا شماره موبایل معتبر ارسال کنید.'

    active_classes = course.classes.filter_by(status='active').all()
    lines = [
        f'📚 دوره: {course.title}',
        f'⏱ مدت دوره: {course.duration_hours or 0} ساعت ({course.total_sessions or 0} جلسه)',
        f'💰 شهریه: {course.total_fee:,.0f} تومان',
    ]
    if course.description:
        lines.extend(['', f'📝 {course.description}'])
    if active_classes:
        lines.extend(['', '🕐 کلاس‌های فعال:'])
        for class_group in active_classes:
            lines.append(
                f'• {class_group.name} | مدرس: '
                f'{class_group.teacher.full_name if class_group.teacher else "-"} | '
                f'ظرفیت: {class_group.available_capacity} نفر'
            )
    return '\n'.join(lines)


def send_bot_message(provider: str, token: str, chat_id, text: str) -> dict:
    base_url = 'https://tapi.bale.ai' if provider == 'bale' else 'https://api.telegram.org'
    response = requests.post(
        f'{base_url}/bot{token}/sendMessage',
        json={'chat_id': chat_id, 'text': text},
        timeout=15,
    )
    try:
        payload = response.json()
    except ValueError:
        payload = {'ok': False, 'description': f'HTTP {response.status_code}'}
    if not response.ok:
        payload['ok'] = False
    return payload


class BalePollingManager:
    """مدیر تک‌نمونه برای Long Polling بله در نسخه وب و دسکتاپ."""

    def __init__(self):
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._stop_event: threading.Event | None = None
        self._token = ''
        self._state = 'stopped'
        self._last_update_at: datetime | None = None
        self._last_error = ''
        self._offset = 0

    def start(self, app, token: str) -> tuple[bool, str]:
        token = (token or '').strip()
        if not token:
            return False, 'توکن ربات بله تنظیم نشده است'

        with self._lock:
            if self._thread and self._thread.is_alive() and self._token == token:
                return True, 'دریافت خودکار پیام‌های بله از قبل فعال است'

            if self._stop_event:
                self._stop_event.set()

            stop_event = threading.Event()
            self._stop_event = stop_event
            self._token = token
            self._offset = 0
            self._state = 'starting'
            self._last_error = ''
            self._thread = threading.Thread(
                target=self._poll_loop,
                args=(app, token, stop_event),
                name='bale-long-polling',
                daemon=True,
            )
            self._thread.start()
        return True, 'دریافت خودکار پیام‌های بله فعال شد'

    def stop(self) -> None:
        with self._lock:
            if self._stop_event:
                self._stop_event.set()
            self._state = 'stopped'
            self._token = ''

    def status(self) -> dict:
        running = bool(self._thread and self._thread.is_alive() and self._state in ('starting', 'running'))
        return {
            'running': running,
            'state': self._state,
            'last_update_at': self._last_update_at,
            'last_error': self._last_error,
            'offset': self._offset,
        }

    def _poll_loop(self, app, token: str, stop_event: threading.Event) -> None:
        base_url = f'https://tapi.bale.ai/bot{token}'
        try:
            # getUpdates و webhook هم‌زمان قابل استفاده نیستند؛ وب‌هوک قبلی حذف می‌شود.
            requests.post(f'{base_url}/deleteWebhook', timeout=10)
        except requests.RequestException:
            # حلقه ادامه می‌دهد و خطای واقعی getUpdates در وضعیت نمایش داده می‌شود.
            pass

        self._state = 'running'
        offset = 0
        while not stop_event.is_set():
            try:
                response = requests.get(
                    f'{base_url}/getUpdates',
                    params={'offset': offset, 'limit': 50, 'timeout': 20},
                    timeout=27,
                )
                response.raise_for_status()
                payload = response.json()
                if not payload.get('ok'):
                    raise RuntimeError(payload.get('description') or 'پاسخ نامعتبر از API بله')

                for update in payload.get('result') or []:
                    update_id = int(update.get('update_id', 0))
                    offset = max(offset, update_id + 1)
                    self._offset = offset
                    message = update.get('message') or update.get('edited_message')
                    if not message or not message.get('text') or not message.get('chat'):
                        continue

                    with app.app_context():
                        answer = build_academy_bot_response(message.get('text', ''))
                    result = send_bot_message('bale', token, message['chat']['id'], answer)
                    if not result.get('ok'):
                        raise RuntimeError(result.get('description') or 'ارسال پاسخ بله ناموفق بود')
                    self._last_update_at = datetime.utcnow()

                self._last_error = ''
            except (requests.RequestException, ValueError, RuntimeError, KeyError) as exc:
                self._last_error = str(exc)
                self._state = 'error'
                if stop_event.wait(5):
                    break
                self._state = 'running'

        if self._stop_event is stop_event:
            self._state = 'stopped'


bale_polling_manager = BalePollingManager()


def start_bale_polling_if_configured(app) -> None:
    """در شروع برنامه، polling را فقط در صورت وجود توکن فعال می‌کند."""
    from models.system import SystemSettings

    settings = SystemSettings.query.first()
    if settings and settings.bale_bot_token:
        bale_polling_manager.start(app, settings.bale_bot_token)
