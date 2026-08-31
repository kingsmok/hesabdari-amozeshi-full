"""منطق مشترک ربات‌ها و دریافت پیام بله/تلگرام با Long Polling (بدون وب‌هوک).
پشتیبانی از:
- ثبت‌نام با شماره تلفن (جلوگیری از استفاده شماره دیگران)
- کیبوردهای شیشه‌ای (Reply Keyboard + Inline Keyboard)
- منوی اصلی ربات
"""
from __future__ import annotations

import json
import logging
import re
import threading
import time
from datetime import datetime

import requests

logger = logging.getLogger('bot.services')


def _normalize_phone(value: str) -> str | None:
    digits = re.sub(r'\D', '', value or '')
    if digits.startswith('0098'):
        digits = '0' + digits[4:]
    elif digits.startswith('98') and len(digits) == 12:
        digits = '0' + digits[2:]
    elif len(digits) == 10 and digits.startswith('9'):
        digits = '0' + digits
    return digits if re.fullmatch(r'09\d{9}', digits) else None


def _ensure_bot_user(chat_info: dict, provider: str = 'bale'):
    """ایجاد یا بروزرسانی رکورد کاربر ربات"""
    from models.bot import BotUser

    chat_id = chat_info.get('id')
    if not chat_id:
        return None

    user = BotUser.query.filter_by(chat_id=chat_id).first()
    if not user:
        user = BotUser(
            chat_id=chat_id,
            first_name=chat_info.get('first_name', ''),
            last_name=chat_info.get('last_name', ''),
            username=chat_info.get('username', ''),
            provider=provider,
            last_activity=datetime.utcnow(),
        )
        db_session_add(user)
    else:
        user.first_name = chat_info.get('first_name', user.first_name)
        user.last_name = chat_info.get('last_name', user.last_name)
        user.username = chat_info.get('username', user.username)
        user.last_activity = datetime.utcnow()
        user.provider = provider

    return user


def db_session_add(obj):
    """اضافه کردن به session دیتابیس"""
    from extensions import db
    db.session.add(obj)
    db.session.flush()


def db_session_commit():
    """کامیت session"""
    from extensions import db
    db.session.commit()


# ═══════════════════════════════════════════════════════════════
#  ساخت کیبوردهای ربات (شیشه‌ای / Glass)
# ═══════════════════════════════════════════════════════════════

def build_main_menu_keyboard(provider: str = 'bale') -> dict:
    """ساخت کیبورد اصلی ربات با دکمه‌های شیشه‌ای"""
    if provider == 'bale':
        return {
            'keyboard': [
                [
                    {'text': '📱 ارسال شماره موبایل', 'request_contact': True},
                ],
                [
                    {'text': '📚 کلاس‌های من'},
                    {'text': '💰 مانده شهریه'},
                ],
                [
                    {'text': '📅 برنامه هفتگی'},
                    {'text': '📝 آزمون‌ها'},
                ],
                [
                    {'text': '⚙️ تنظیمات'},
                    {'text': '📞 پشتیبانی'},
                ],
                [
                    {'text': '🔍 جستجوی دوره'},
                    {'text': '📊 کارنامه'},
                ],
            ],
            'resize_keyboard': True,
            'one_time_keyboard': False,
        }
    else:  # telegram
        return {
            'keyboard': [
                [
                    {'text': '📱 ارسال شماره موبایل', 'request_contact': True},
                ],
                [
                    {'text': '📚 کلاس‌های من'},
                    {'text': '💰 مانده شهریه'},
                ],
                [
                    {'text': '📅 برنامه هفتگی'},
                    {'text': '📝 آزمون‌ها'},
                ],
                [
                    {'text': '⚙️ تنظیمات'},
                    {'text': '📞 پشتیبانی'},
                ],
                [
                    {'text': '🔍 جستجوی دوره'},
                    {'text': '📊 کارنامه'},
                ],
            ],
            'resize_keyboard': True,
            'one_time_keyboard': False,
        }


def build_settings_keyboard(provider: str = 'bale') -> dict:
    """کیبورد بخش تنظیمات"""
    return {
        'keyboard': [
            [{'text': '🔔 اعلان‌ها'}],
            [{'text': '🌐 تغییر زبان'}],
            [{'text': '📱 تغییر شماره'}, {'text': '🔙 بازگشت'}],
        ],
        'resize_keyboard': True,
    }


def build_back_keyboard(provider: str = 'bale') -> dict:
    """کیبورد بازگشت"""
    return {
        'keyboard': [
            [{'text': '🔙 بازگشت به منوی اصلی'}],
        ],
        'resize_keyboard': True,
    }


def build_inline_course_buttons(courses: list, provider: str = 'bale') -> dict:
    """دکمه‌های inline برای دوره‌ها"""
    buttons = []
    for c in courses[:10]:
        buttons.append([
            {'text': c.title, 'callback_data': f'course_{c.id}'}
        ])
    return {'inline_keyboard': buttons}


# ═══════════════════════════════════════════════════════════════
#  ارسال پیام با کیبورد
# ═══════════════════════════════════════════════════════════════

def send_bot_message(provider: str, token: str, chat_id, text: str,
                     reply_markup: dict = None, parse_mode: str = None) -> dict:
    """ارسال پیام به ربات بله یا تلگرام"""
    base_url = 'https://tapi.bale.ai' if provider == 'bale' else 'https://api.telegram.org'
    payload = {'chat_id': chat_id, 'text': text}
    if reply_markup:
        payload['reply_markup'] = reply_markup
    if parse_mode:
        payload['parse_mode'] = parse_mode

    response = requests.post(
        f'{base_url}/bot{token}/sendMessage',
        json=payload,
        timeout=15,
    )
    try:
        result = response.json()
    except ValueError:
        result = {'ok': False, 'description': f'HTTP {response.status_code}'}
    if not response.ok:
        result['ok'] = False
    return result


def send_bot_photo(provider: str, token: str, chat_id, photo_url: str,
                   caption: str = '', reply_markup: dict = None) -> dict:
    """ارسال عکس با کیبورد"""
    base_url = 'https://tapi.bale.ai' if provider == 'bale' else 'https://api.telegram.org'
    payload = {'chat_id': chat_id, 'photo': photo_url}
    if caption:
        payload['caption'] = caption
    if reply_markup:
        payload['reply_markup'] = reply_markup

    response = requests.post(
        f'{base_url}/bot{token}/sendPhoto',
        json=payload,
        timeout=15,
    )
    try:
        result = response.json()
    except ValueError:
        result = {'ok': False, 'description': f'HTTP {response.status_code}'}
    return result


def send_bot_document(provider: str, token: str, chat_id, file_path: str,
                      caption: str = '', filename: str = None,
                      timeout: int = 180) -> dict:
    """
    ارسال فایل (سند) به ربات بله یا تلگرام با multipart/form-data.
    سقف حجم در هر دو سرویس ۵۰ مگابایت است.
    """
    import os

    base_url = 'https://tapi.bale.ai' if provider == 'bale' else 'https://api.telegram.org'
    if not os.path.isfile(file_path):
        return {'ok': False, 'description': 'فایل موردنظر پیدا نشد'}

    data = {'chat_id': str(chat_id)}
    if caption:
        data['caption'] = caption[:1024]        # سقف زیرنویس در هر دو سرویس

    try:
        with open(file_path, 'rb') as handle:
            files = {'document': (filename or os.path.basename(file_path), handle,
                                  'application/octet-stream')}
            response = requests.post(
                f'{base_url}/bot{token}/sendDocument',
                data=data, files=files, timeout=timeout,
            )
    except requests.RequestException as exc:
        return {'ok': False, 'description': f'خطای شبکه: {type(exc).__name__}'}

    try:
        result = response.json()
    except ValueError:
        result = {'ok': False, 'description': f'HTTP {response.status_code}'}
    if not response.ok:
        result['ok'] = False
        result.setdefault('description', f'HTTP {response.status_code}')
    return result


def is_backup_admin(bot_user, chat_id) -> bool:
    """
    مدیر پشتیبان‌گیری: کاربری که در پنل «مدیر ربات» شده،
    یا شناسه‌اش در تنظیمات ارسال پشتیبان ثبت شده است.
    """
    if bot_user is not None and getattr(bot_user, 'is_admin_bot', False):
        return True
    try:
        from utils.backup_service import bot_targets
        return str(chat_id) in bot_targets()
    except Exception:
        return False


def handle_backup_command(bot_user, chat_id, provider: str = 'bale') -> str:
    """
    ساخت بسته پشتیبان و ارسال آن در همان گفت‌وگو — فقط برای مدیر ربات.
    برای کاربر عادی هیچ نشانه‌ای از وجود این دستور داده نمی‌شود.
    """
    from models.system import SystemSettings

    if not is_backup_admin(bot_user, chat_id):
        return 'دستور شناخته نشد. برای دیدن منو /start را بفرستید.'

    try:
        from utils.backup_service import (BackupError, KIND_DATABASE, create_backup,
                                          send_backup_to_bot)
    except ImportError:
        return '⛔️ سرویس پشتیبان‌گیری در دسترس نیست.'

    settings = SystemSettings.query.first()
    kind = (getattr(settings, 'backup_bot_kind', '') or KIND_DATABASE) if settings else KIND_DATABASE

    try:
        info = create_backup(kind=kind, note='درخواست از ربات')
        report = send_backup_to_bot(info['name'], targets=[str(chat_id)])
    except BackupError as exc:
        return f'⛔️ {exc}'
    except Exception:
        logger.exception('bot: backup command failed')
        return '⛔️ پشتیبان‌گیری انجام نشد؛ لطفاً از خود نرم‌افزار اقدام کنید.'

    if report['sent']:
        return (f"✅ بسته پشتیبان ساخته و ارسال شد.\n"
                f"نام: {info['name']}\nحجم: {info['size_mb']} مگابایت")
    error = report['failed'][0]['error'] if report['failed'] else 'نامشخص'
    return f'⚠️ بسته ساخته شد ولی ارسال نشد: {error}'


# ═══════════════════════════════════════════════════════════════
#  پردازش دستورات و متن پیام
# ═══════════════════════════════════════════════════════════════

def process_bot_message(text: str, chat_info: dict, contact: dict = None,
                        provider: str = 'bale') -> tuple:
    """
    پردازش پیام ورودی و تولید پاسخ + کیبورد
    Returns: (reply_text, reply_markup)
    """
    from models.bot import BotUser, BotMessage
    from models.course import Course
    from models.registration import Registration
    from models.student import Student

    chat_id = chat_info.get('id')
    text = (text or '').strip()

    # تضمین وجود کاربر
    bot_user = _ensure_bot_user(chat_info, provider)
    if bot_user:
        try:
            db_session_commit()
        except Exception:
            pass

    # لاگ پیام
    try:
        msg_log = BotMessage(
            chat_id=chat_id,
            text=text[:500] if text else '(contact)',
            direction='incoming',
            msg_type='contact' if contact else ('command' if text.startswith('/') else 'text'),
            provider=provider,
        )
        from extensions import db
        db.session.add(msg_log)
        db.session.commit()
    except Exception:
        pass

    # ── اگر شماره تلفن (contact) ارسال شده باشد ──
    if contact:
        phone_number = contact.get('phone_number', '')
        phone = _normalize_phone(phone_number)
        if not phone:
            return ('❌ شماره تلفن نامعتبر است.\nلطفاً شماره موبایل ایرانی معتبر ارسال کنید.', None)

        # بررسی: آیا این شماره قبلاً توسط کاربر دیگری ثبت شده؟
        existing = BotUser.query.filter(
            BotUser.phone == phone,
            BotUser.chat_id != chat_id
        ).first()
        if existing:
            return (
                '⛔️ این شماره تلفن قبلاً توسط کاربر دیگری ثبت شده است.\n'
                'هر کاربر فقط می‌تواند شماره تلفن شخصی خود را ثبت کند.\n\n'
                'در صورت مشکل با پشتیبانی تماس بگیرید.',
                build_main_menu_keyboard(provider)
            )

        # ثبت شماره
        bot_user.phone = phone
        bot_user.is_verified = True

        # تلاش برای اتصال به هنرجو
        student = Student.query.filter(
            (Student.mobile == phone) | (Student.mobile2 == phone)
        ).first()
        if student:
            bot_user.student_id = student.id
            try:
                db_session_commit()
            except Exception:
                pass
            return _build_student_info(student, provider)

        try:
            db_session_commit()
        except Exception:
            pass
        return (
            '✅ شماره تلفن شما با موفقیت ثبت شد!\n\n'
            '📱 شماره: ' + phone + '\n\n'
            '⚠️ هنرجویی با این شماره یافت نشد.\n'
            'لطفاً به دفتر آموزشگاه مراجعه کنید تا اطلاعات شما ثبت شود.',
            build_main_menu_keyboard(provider)
        )

    # ── دستور پشتیبان‌گیری (فقط مدیر ربات) ──
    if text in ('/backup', '/پشتیبان', '📦 پشتیبان‌گیری'):
        return (handle_backup_command(bot_user, chat_id, provider),
                build_main_menu_keyboard(provider))

    # ── دستورات ──
    if text in ('/start', '/help', '🔙 بازگشت به منوی اصلی', '🔙 بازگشت'):
        welcome = _get_welcome_message()
        return (welcome, build_main_menu_keyboard(provider))

    # ── دکمه‌های منوی اصلی ──
    if text == '📱 ارسال شماره موبایل':
        return (
            '📱 لطفاً شماره موبایل خود را با استفاده از دکمه زیر ارسال کنید:\n\n'
            '⚠️ توجه: فقط شماره تلفن شخصی خود را ارسال کنید.\n'
            'استفاده از شماره دیگران ممکن نیست.',
            {
                'keyboard': [
                    [{'text': '📲 اشتراک‌گذاری شماره', 'request_contact': True}],
                    [{'text': '🔙 بازگشت'}],
                ],
                'resize_keyboard': True,
                'one_time_keyboard': True,
            }
        )

    if text == '📚 کلاس‌های من':
        if not bot_user or not bot_user.is_verified:
            return ('⚠️ ابتدا شماره موبایل خود را ثبت کنید.', build_main_menu_keyboard(provider))
        if not bot_user.student_id:
            return ('❌ هنرجویی با شماره شما یافت نشد.\nبه دفتر آموزشگاه مراجعه کنید.',
                    build_main_menu_keyboard(provider))
        student = Student.query.get(bot_user.student_id)
        if student:
            return _build_student_info(student, provider)
        return ('❌ اطلاعات هنرجو یافت نشد.', build_main_menu_keyboard(provider))

    if text == '💰 مانده شهریه':
        if not bot_user or not bot_user.student_id:
            return ('⚠️ ابتدا شماره موبایل خود را ثبت کنید.', build_main_menu_keyboard(provider))
        regs = Registration.query.filter_by(student_id=bot_user.student_id, status='active').all()
        if not regs:
            return ('📭 ثبت‌نام فعالی ندارید.', build_main_menu_keyboard(provider))
        lines = ['💰 مانده شهریه شما:']
        for r in regs:
            lines.append(f'• {r.course.title if r.course else "-"}: {(r.remaining_amount or 0):,.0f} تومان')
        return ('\n'.join(lines), build_back_keyboard(provider))

    if text == '📅 برنامه هفتگی':
        if not bot_user or not bot_user.student_id:
            return ('⚠️ ابتدا شماره موبایل خود را ثبت کنید.', build_main_menu_keyboard(provider))
        regs = Registration.query.filter_by(student_id=bot_user.student_id, status='active').all()
        if not regs:
            return ('📭 کلاسی ندارید.', build_main_menu_keyboard(provider))
        lines = ['📅 برنامه هفتگی شما:']
        for r in regs:
            cg = r.class_group
            if cg:
                lines.append(f'• {cg.name}')
                lines.append(f'  📚 {r.course.title if r.course else "-"}')
                lines.append(f'  👨‍🏫 {cg.teacher.full_name if cg.teacher else "-"}')
                lines.append(f'  🕐 {cg.start_time or "-"} تا {cg.end_time or "-"}')
                lines.append(f'  📆 {cg.days or "-"}')
        return ('\n'.join(lines), build_back_keyboard(provider))

    if text == '📝 آزمون‌ها':
        return ('📝 بخش آزمون‌ها به‌زودی فعال می‌شود.', build_back_keyboard(provider))

    if text == '⚙️ تنظیمات':
        return ('⚙️ تنظیمات حساب کاربری:', build_settings_keyboard(provider))

    if text == '📞 پشتیبانی':
        return (
            '📞 ارتباط با پشتیبانی:\n\n'
            '📱 تلفن: 021-12345678\n'
            '⏰ ساعت پاسخگویی: 8 تا 20\n'
            '💬 یا از منوی اصلی استفاده کنید.',
            build_back_keyboard(provider)
        )

    if text == '🔍 جستجوی دوره':
        courses = Course.query.filter_by(is_active=True).limit(15).all()
        if not courses:
            return ('📚 دوره‌ای فعال نیست.', build_main_menu_keyboard(provider))
        lines = ['🔍 دوره‌های فعال:']
        for c in courses[:10]:
            lines.append(f'• {c.title} — {c.total_fee:,.0f} تومان')
        return ('\n'.join(lines), build_back_keyboard(provider))

    if text == '📊 کارنامه':
        return ('📊 بخش کارنامه به‌زودی فعال می‌شود.', build_back_keyboard(provider))

    if text == '🔔 اعلان‌ها':
        return ('🔔 تنظیمات اعلان‌ها به‌زودی فعال می‌شود.', build_settings_keyboard(provider))

    if text == '🌐 تغییر زبان':
        return ('🌐 زبان فعلی: فارسی', build_settings_keyboard(provider))

    if text == '📱 تغییر شماره':
        if bot_user:
            bot_user.phone = None
            bot_user.is_verified = False
            bot_user.student_id = None
            try:
                db_session_commit()
            except Exception:
                pass
        return (
            '📱 شماره قبلی پاک شد.\nلطفاً شماره جدید خود را ارسال کنید:',
            {
                'keyboard': [
                    [{'text': '📲 اشتراک‌گذاری شماره', 'request_contact': True}],
                ],
                'resize_keyboard': True,
                'one_time_keyboard': True,
            }
        )

    # ── جستجوی نام دوره ──
    course = Course.query.filter(
        Course.title.contains(text), Course.is_active.is_(True)
    ).first()
    if course:
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
            for cg in active_classes:
                lines.append(
                    f'• {cg.name} | مدرس: '
                    f'{cg.teacher.full_name if cg.teacher else "-"} | '
                    f'ظرفیت: {cg.available_capacity} نفر'
                )
        return ('\n'.join(lines), build_main_menu_keyboard(provider))

    # ── جستجوی شماره تلفن ──
    phone = _normalize_phone(text)
    if phone:
        student = Student.query.filter(
            (Student.mobile == phone) | (Student.mobile2 == phone)
        ).first()
        if student:
            return _build_student_info(student, provider)
        return ('❌ هنرجویی با این شماره یافت نشد.', build_main_menu_keyboard(provider))

    # ── پاسخ پیش‌فرض ──
    return (
        '🔍 موردی پیدا نشد.\n\n'
        'از منوی پایین صفحه استفاده کنید یا:\n'
        '• شماره موبایل خود را ارسال کنید\n'
        '• نام دوره را جستجو کنید',
        build_main_menu_keyboard(provider)
    )


def _get_welcome_message() -> str:
    """دریافت پیام خوش‌آمدگویی"""
    from models.system import SystemSettings
    settings = SystemSettings.query.first()
    if settings and settings.welcome_message:
        return settings.welcome_message

    return (
        '🎓 به ربات آموزشگاه خوش آمدید!\n\n'
        '📱 برای مشاهده اطلاعات خود:\n'
        '1️⃣ دکمه «📱 ارسال شماره موبایل» را بزنید\n'
        '2️⃣ شماره تلفن خود را ارسال کنید\n\n'
        '⚠️ توجه مهم: فقط شماره تلفن شخصی خود را ارسال کنید.\n'
        'امکان ثبت شماره تلفن فرد دیگر وجود ندارد.\n\n'
        '📚 یا نام دوره مورد نظر را جستجو کنید.'
    )


def _build_student_info(student, provider: str = 'bale') -> tuple:
    """ساخت اطلاعات هنرجو"""
    from models.registration import Registration

    regs = Registration.query.filter_by(student_id=student.id, status='active').all()
    if not regs:
        return (
            f'👤 {student.full_name}\nثبت‌نام فعالی برای شما ثبت نشده است.',
            build_main_menu_keyboard(provider)
        )

    lines = [f'👤 {student.full_name} ({student.student_code})', '', '📚 کلاس‌های فعال شما:']
    for registration in registrations_safe(regs):
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
    return ('\n'.join(lines), build_main_menu_keyboard(provider))


def registrations_safe(regs):
    """Helper for iteration"""
    return regs


def build_academy_bot_response(text: str) -> str:
    """تابع سازگاری — پاسخ ساده بدون کیبورد (برای نسخه قدیمی)"""
    reply_text, _ = process_bot_message(text, {'id': 0})
    return reply_text


# ═══════════════════════════════════════════════════════════════
#  مدیریت Long Polling بله
# ═══════════════════════════════════════════════════════════════

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
            requests.post(f'{base_url}/deleteWebhook', timeout=10)
        except requests.RequestException:
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
                    if not message or not message.get('chat'):
                        continue

                    with app.app_context():
                        chat_info = message.get('chat', {})
                        text = message.get('text', '')
                        contact = message.get('contact')

                        reply_text, reply_markup = process_bot_message(
                            text, chat_info, contact=contact, provider='bale'
                        )

                    result = send_bot_message('bale', token, chat_info['id'],
                                              reply_text, reply_markup=reply_markup)
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
