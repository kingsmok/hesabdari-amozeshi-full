"""منطق مشترک ربات‌ها و دریافت پیام بله/تلگرام با Long Polling (بدون وب‌هوک).
پشتیبانی از:
- ثبت‌نام با شماره تلفن (جلوگیری از استفاده شماره دیگران)
- کیبوردهای شیشه‌ای (Reply Keyboard + Inline Keyboard)
- منوی اصلی ربات

عملکرد روی هاست (چرا این ماژول این‌طور نوشته شده):
  سرور بله/تلگرام بیرون از هاست است، پس هر فراخوانی API یک RTT کامل هزینه
  دارد. دو چیز قبلاً ربات را روی هاست «خیلی کند» می‌کرد:
    ۱) هر sendMessage یک اتصال TCP+TLS تازه می‌ساخت (handshake دوباره).
    ۲) پردازش همهٔ پیام‌ها پشت‌سرهم در یک ترد انجام می‌شد و اگر ارسال پاسخِ
       حتی یک کاربر شکست می‌خورد (کاربر block کرده / ۴۲۹ flood) کل دسته
       رها می‌شد، ۵ ثانیه خواب می‌رفت و بقیهٔ پیام‌ها هرگز جواب نمی‌گرفتند.
  حالا: Session با pool اتصال، پردازش موازی به تفکیک کاربر، و جداسازی خطای
  هر پیام از بقیه.
"""
from __future__ import annotations

import logging
import os
import queue
import re
import threading
import time
from datetime import datetime

import requests

logger = logging.getLogger('bot.services')

# ═══════════════════════════════════════════════════════════════
#  لایهٔ HTTP مشترک — اتصال پایدار به‌جای handshake برای هر پیام
# ═══════════════════════════════════════════════════════════════

#: (اتصال, خواندن) — اتصال باید کوتاه باشد تا هاستِ با مسیر بد سریع شکست بخورد
DEFAULT_TIMEOUT = (7, 20)

_SESSIONS = threading.local()


def _http_session() -> requests.Session:
    """یک `Session` برای هر ترد، با pool اتصال.

    `requests.post(...)` هر بار اتصال تازه می‌سازد ⇒ روی هاست، به‌ازای هر
    پیام یک TLS handshake اضافه. `Session` اتصال را نگه می‌دارد و پیام‌های
    بعدی روی همان اتصال می‌روند. چون `Session` تضمین thread-safe بودن ندارد،
    به‌جای یک نمونهٔ مشترک، هر ترد نمونهٔ خودش را دارد.
    """
    session = getattr(_SESSIONS, 'session', None)
    if session is None:
        session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=2, pool_maxsize=4, max_retries=0,
        )
        session.mount('https://', adapter)
        session.mount('http://', adapter)
        _SESSIONS.session = session
    return session


def _base_url(provider: str) -> str:
    return 'https://tapi.bale.ai' if provider == 'bale' else 'https://api.telegram.org'


def _call_api(method: str, provider: str, token: str, *,
              json_body: dict = None, data: dict = None, files: dict = None,
              params: dict = None,
              timeout=DEFAULT_TIMEOUT, retry_connect: bool = True) -> dict:
    """فراخوانی یک متد Bot API و برگرداندن پاسخ JSON (همیشه dict با کلید ok).

    تنها در خطای *اتصال* یک بار تلاش مجدد می‌کند؛ خطای خواندن تکرار نمی‌شود
    تا پیام دوباره (دوبار) ارسال نشود.
    """
    url = f'{_base_url(provider)}/bot{token}/{method}'
    attempts = 2 if retry_connect else 1
    for attempt in range(attempts):
        try:
            response = _http_session().request(
                'POST' if (json_body is not None or data or files) else 'GET',
                url, json=json_body, data=data, files=files, params=params,
                timeout=timeout,
            )
        except (requests.ConnectionError, requests.ConnectTimeout) as exc:
            if attempt + 1 < attempts:
                time.sleep(0.4 * (attempt + 1))
                continue
            return {'ok': False, 'description': f'خطای شبکه: {type(exc).__name__}'}
        except requests.RequestException as exc:
            return {'ok': False, 'description': f'خطای شبکه: {type(exc).__name__}'}

        try:
            result = response.json()
        except ValueError:
            result = {'ok': False,
                      'description': f'پاسخ نامعتبر از سرور (HTTP {response.status_code})'}
        if not response.ok:
            result['ok'] = False
            result.setdefault('description', f'HTTP {response.status_code}')
        if not isinstance(result, dict):
            result = {'ok': False, 'description': 'پاسخ نامعتبر از سرور'}
        return result
    return {'ok': False, 'description': 'تلاش برای ارتباط با سرور ناموفق بود'}


def retry_after_seconds(result: dict) -> float:
    """ثانیهٔ درخواستی سرور در پاسخ ۴۲۹ (محدودیت نرخ) — ۰ اگر نبود."""
    try:
        if int(result.get('error_code') or 0) == 429:
            return float((result.get('parameters') or {}).get('retry_after') or 1)
    except (TypeError, ValueError):
        pass
    return 0.0


# ═══════════════════════════════════════════════════════════════
#  اطلاعات ربات (getMe) — با کش کوتاه
# ═══════════════════════════════════════════════════════════════

_BOT_INFO_TTL = 300                       # ثانیه
_BOT_INFO_CACHE: dict = {}
_BOT_INFO_LOCK = threading.Lock()


def get_bot_info(provider: str, token: str, ttl: int = _BOT_INFO_TTL) -> dict | None:
    """اطلاعات ربات با کش؛ صفحهٔ تنظیمات با هر بار باز شدن به شبکه نمی‌رود.

    پیش از این هر بار که صفحهٔ «ربات بله» باز می‌شد یک getMe با تایم‌اوت ۱۰
    ثانیه روی اتصال تازه زده می‌شد؛ روی هاستی که مسیرش تا سرور بله کند است،
    خودِ صفحه چند ثانیه طول می‌کشید.
    """
    token = (token or '').strip()
    if not token:
        return None
    key = f'{provider}:{token}'
    now = time.monotonic()
    with _BOT_INFO_LOCK:
        cached = _BOT_INFO_CACHE.get(key)
        if cached and now - cached[0] < ttl:
            return cached[1]

    result = _call_api('getMe', provider, token, timeout=(7, 10), retry_connect=False)
    info = result.get('result') if result.get('ok') and isinstance(result.get('result'), dict) else None
    with _BOT_INFO_LOCK:
        _BOT_INFO_CACHE[key] = (now, info)
    return info


def clear_bot_info_cache() -> None:
    """پاک‌کردن کش getMe — بعد از تغییر توکن."""
    with _BOT_INFO_LOCK:
        _BOT_INFO_CACHE.clear()


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
    """ارسال پیام به ربات بله یا تلگرام (روی اتصال پایدار مشترک)."""
    payload = {'chat_id': chat_id, 'text': text}
    if reply_markup:
        payload['reply_markup'] = reply_markup
    if parse_mode:
        payload['parse_mode'] = parse_mode

    result = _call_api('sendMessage', provider, token, json_body=payload)
    wait = retry_after_seconds(result)
    if wait:                        # محدودیت نرخ سرور: صبر و یک تلاش دیگر
        time.sleep(min(wait, 10))
        result = _call_api('sendMessage', provider, token, json_body=payload,
                           retry_connect=False)
    return result


def send_bot_photo(provider: str, token: str, chat_id, photo_url: str,
                   caption: str = '', reply_markup: dict = None) -> dict:
    """ارسال عکس با کیبورد"""
    payload = {'chat_id': chat_id, 'photo': photo_url}
    if caption:
        payload['caption'] = caption
    if reply_markup:
        payload['reply_markup'] = reply_markup

    return _call_api('sendPhoto', provider, token, json_body=payload)


def send_bot_document(provider: str, token: str, chat_id, file_path: str,
                      caption: str = '', filename: str = None,
                      timeout: int = 180) -> dict:
    """
    ارسال فایل (سند) به ربات بله یا تلگرام با multipart/form-data.
    سقف حجم در هر دو سرویس ۵۰ مگابایت است.
    """
    if not os.path.isfile(file_path):
        return {'ok': False, 'description': 'فایل موردنظر پیدا نشد'}

    data = {'chat_id': str(chat_id)}
    if caption:
        data['caption'] = caption[:1024]        # سقف زیرنویس در هر دو سرویس

    try:
        with open(file_path, 'rb') as handle:
            files = {'document': (filename or os.path.basename(file_path), handle,
                                  'application/octet-stream')}
            return _call_api('sendDocument', provider, token, data=data, files=files,
                             timeout=(7, timeout))
    except OSError as exc:
        return {'ok': False, 'description': f'خواندن فایل ممکن نشد: {type(exc).__name__}'}


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

    # تضمین وجود کاربر + لاگ پیام، در یک کامیت (کامیت روی SQLite یعنی fsync؛
    # دو کامیت برای هر پیام روی هاست با دیسک کند دو برابر زمان می‌برد)
    bot_user = _ensure_bot_user(chat_info, provider)
    try:
        from extensions import db
        db.session.add(BotMessage(
            chat_id=chat_id,
            text=text[:500] if text else '(contact)',
            direction='incoming',
            msg_type='contact' if contact else ('command' if text.startswith('/') else 'text'),
            provider=provider,
        ))
        db.session.commit()
    except Exception:
        try:
            from extensions import db
            db.session.rollback()
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
    """مدیر تک‌نمونه برای Long Polling بله در نسخه وب و دسکتاپ.

    معماری:
      یک ترد «دریافت» فقط getUpdates را صدا می‌زند و پیام‌ها را بین چند ترد
      «پردازش» تقسیم می‌کند. تقسیم بر اساس chat_id است تا ترتیب پیام‌های هر
      کاربر حفظ شود، ولی کاربرهای مختلف هم‌زمان سرویس بگیرند. پیش از این همه
      چیز در یک ترد پشت‌سرهم بود: با ۵۰ پیامِ تلنبارشده، آخرین کاربر تا
      پایان کارِ ۴۹ نفر قبلی منتظر می‌ماند.
    """

    #: تعداد تردهای پردازش؛ با ACADEMY_BALE_WORKERS قابل تغییر (۱ = پشت‌سرهم)
    DEFAULT_WORKERS = 3
    #: سقف پیام در هر getUpdates
    BATCH_LIMIT = 50
    #: ثانیه‌های long-poll سمت سرور و تایم‌اوت خواندن سمت ما
    LONG_POLL = 20
    LONG_POLL_TIMEOUT = (7, 30)
    #: بیشترین فاصلهٔ بین تلاش‌ها پس از خطای پیاپی getUpdates
    MAX_BACKOFF = 30

    def __init__(self):
        self._lock = threading.Lock()
        self._pending_lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._stop_event: threading.Event | None = None
        self._token = ''
        self._state = 'stopped'
        self._last_update_at: datetime | None = None
        self._last_error = ''
        self._offset = 0
        # آمار — برای دیدن وضعیت واقعی روی هاست از همان پنل
        self._processed = 0
        self._failed = 0
        self._latency_sum = 0.0
        self._latency_count = 0
        self._pending = 0

    # ── چرخهٔ زندگی ────────────────────────────────────────────────
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
            # صف‌های اجرا قبلی با آن ترد مرده‌اند؛ شمارندهٔ انتظار صفر می‌شود
            with self._pending_lock:
                self._pending = 0
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
            'workers': self.worker_count(),
            'processed': self._processed,
            'failed': self._failed,
            'pending': self._pending,
            'avg_latency_ms': (int(self._latency_sum / self._latency_count * 1000)
                               if self._latency_count else 0),
        }

    @classmethod
    def worker_count(cls) -> int:
        """تعداد تردهای پردازش (از محیط؛ حداقل ۱)."""
        raw = os.environ.get('ACADEMY_BALE_WORKERS', '').strip()
        try:
            return max(1, int(raw)) if raw else cls.DEFAULT_WORKERS
        except ValueError:
            return cls.DEFAULT_WORKERS

    # ── آمار داخلی ─────────────────────────────────────────────────
    def _note_result(self, ok: bool, elapsed: float) -> None:
        with self._pending_lock:
            self._pending -= 1
        if ok:
            self._processed += 1
            self._latency_sum += elapsed
            self._latency_count += 1
            self._last_update_at = datetime.utcnow()
        else:
            self._failed += 1

    def _note_error(self, message: str) -> None:
        """ثبت خطا بدون متوقف‌کردن حلقهٔ دریافت."""
        self._last_error = message
        logger.warning('bale: %s', message)

    # ── ترد دریافت ─────────────────────────────────────────────────
    def _poll_loop(self, app, token: str, stop_event: threading.Event) -> None:
        workers = self._spawn_workers(app, token, stop_event)
        try:
            self._fetch_loop(app, token, stop_event, workers)
        finally:
            self._shutdown_workers(workers, stop_event)
            if self._stop_event is stop_event:
                self._state = 'stopped'

    def _fetch_loop(self, app, token: str, stop_event: threading.Event,
                    workers: list) -> None:
        """فقط دریافت؛ پردازش را به تردهای کارگر می‌سپارد."""
        _call_api('deleteWebhook', 'bale', token, timeout=(7, 10), retry_connect=False)

        self._state = 'running'
        offset = 0
        failures = 0
        while not stop_event.is_set():
            payload = _call_api(
                'getUpdates', 'bale', token,
                params={'offset': offset, 'limit': self.BATCH_LIMIT,
                        'timeout': self.LONG_POLL},
                timeout=self.LONG_POLL_TIMEOUT,
            )
            if not payload.get('ok'):
                failures += 1
                self._note_error(payload.get('description') or 'پاسخ نامعتبر از API بله')
                self._state = 'error'
                # backoff نمایی: خطای گذرای شبکه نباید هر ۵ ثانیه تکرار شود و
                # خطای ماندگار هم نباید CPU/پهنای باند هاست را بسوزاند
                if stop_event.wait(min(self.MAX_BACKOFF, 1.5 ** failures)):
                    break
                self._state = 'running'
                continue

            failures = 0
            self._last_error = ''
            updates = payload.get('result') or []
            if not updates:
                continue

            # تأیید دسته پیش از پردازش: اگر پردازش یک پیام بمیرد، کل دسته
            # دوباره از سر گرفته نمی‌شود (پیام تکراری/گم‌شده نمی‌دهد)
            try:
                offset = max(offset, max(int(u.get('update_id', 0)) for u in updates) + 1)
            except (TypeError, ValueError):
                offset = max(offset, len(updates))
            self._offset = offset

            for update in updates:
                self._dispatch(update, workers)

    def _dispatch(self, update: dict, workers: list) -> None:
        """سپردن یک پیام به کارگرِ همان کاربر (ترتیب هر کاربر حفظ می‌شود)."""
        message = update.get('message') or update.get('edited_message') or {}
        chat_id = (message.get('chat') or {}).get('id')
        if chat_id is None:
            return
        with self._pending_lock:
            self._pending += 1
        workers[abs(hash(chat_id)) % len(workers)].put(update)

    # ── تردهای پردازش ──────────────────────────────────────────────
    def _spawn_workers(self, app, token: str,
                       stop_event: threading.Event) -> list:
        workers = []
        for index in range(self.worker_count()):
            work_queue: queue.Queue = queue.Queue()
            thread = threading.Thread(
                target=self._worker_loop,
                args=(app, token, stop_event, work_queue),
                name=f'bale-handler-{index}',
                daemon=True,
            )
            thread.start()
            workers.append(work_queue)
        return workers

    def _worker_loop(self, app, token: str, stop_event: threading.Event,
                     work_queue: queue.Queue) -> None:
        while not stop_event.is_set():
            try:
                update = work_queue.get(timeout=0.5)
            except queue.Empty:
                continue
            self._handle_update(app, token, update)
        # هنگام توقف، پیام‌های مانده در صف دور ریخته می‌شوند تا شمارندهٔ
        # «در انتظار» بادکرده باقی نماند
        while True:
            try:
                work_queue.get_nowait()
            except queue.Empty:
                return
            with self._pending_lock:
                self._pending -= 1

    def _shutdown_workers(self, workers: list, stop_event: threading.Event) -> None:
        stop_event.set()
        for work_queue in workers:
            work_queue.put(None)

    def _handle_update(self, app, token: str, update: dict) -> None:
        """پردازش یک پیام؛ هر خطا فقط همان پیام را از کار می‌اندازد."""
        if update is None:
            return
        started = time.monotonic()
        message = update.get('message') or update.get('edited_message') or {}
        chat_info = message.get('chat') or {}
        chat_id = chat_info.get('id')
        if chat_id is None:
            with self._pending_lock:
                self._pending -= 1
            return

        ok = False
        try:
            with app.app_context():
                reply_text, reply_markup = process_bot_message(
                    message.get('text', ''), chat_info,
                    contact=message.get('contact'), provider='bale',
                )
            result = send_bot_message('bale', token, chat_id, reply_text,
                                      reply_markup=reply_markup)
            ok = bool(result.get('ok'))
            if not ok:
                # کاربر block کرده، چت وجود ندارد، flood و … — هیچ‌کدام نباید
                # بقیهٔ صف را متوقف کند
                self._note_error(f'ارسال پاسخ به {chat_id} ناموفق: '
                                 f'{result.get("description") or "نامشخص"}')
        except Exception as exc:                          # noqa: BLE001
            self._note_error(f'پردازش پیام {chat_id} ناموفق: {type(exc).__name__}: {exc}')
            logger.exception('bale: update handling failed for chat %s', chat_id)
        finally:
            self._note_result(ok, time.monotonic() - started)


bale_polling_manager = BalePollingManager()


def start_bale_polling_if_configured(app) -> None:
    """در شروع برنامه، polling را فقط در صورت وجود توکن فعال می‌کند."""
    from models.system import SystemSettings

    settings = SystemSettings.query.first()
    if settings and settings.bale_bot_token:
        bale_polling_manager.start(app, settings.bale_bot_token)
