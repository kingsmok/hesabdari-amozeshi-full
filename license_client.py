"""
سامانه لایسنس نرم‌افزار — حساب داری آموزشگاهی رهسا
────────────────────────────────────────────────────────────────
تمام منطق ارتباط با سرور لایسنس، تایید امضای RSA، کش محلی
وابسته به دستگاه، مهلت آفلاین و قفل بخش‌ها در همین فایل متمرکز است.

قواعد ثابت این ماژول:
  • هیچ کلید لایسنس، نام مشتری یا فهرست دسترسی در کد ثابت نیست؛
    همه از پاسخِ امضاشده‌ی سرور خوانده می‌شود.
  • کلید عمومی هاردکد شده است و در زمان اجرا دانلود نمی‌شود.
  • هیچ تصمیمی پیش از تایید موفق امضا گرفته نمی‌شود.
"""
import base64
import hashlib
import hmac
import json
import logging
import os
import platform
import secrets
import socket
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from functools import wraps

import requests
from cryptography.exceptions import InvalidSignature
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from flask import jsonify, redirect, render_template, request, url_for

from license_features import (
    AVAILABLE_FEATURES,
    FEATURE_LABELS,
    audit_endpoint_coverage,
    feature_for_endpoint,
    is_exempt_endpoint,
)

logger = logging.getLogger('license')


# ══════════════════════════════════════════════════════════════
#  ثابت‌های محصول
# ══════════════════════════════════════════════════════════════
APP_NAME = 'HesabdariRahsa'
PRODUCT_SLUG = 'hesabdari'
PRODUCT_NAME = 'حساب داری آموزشگاهی رهسا'
APP_TYPE = 'desktop_windows'
DEFAULT_SERVER_URL = 'https://ls.ariapadideh.ir'
DEFAULT_CHANNEL = 'stable'

REQUEST_TIMEOUT = 10
RETRY_DELAYS = (1, 2, 4)
DEFAULT_REVALIDATE_MINUTES = 360          # هر ۶ ساعت
DEFAULT_OFFLINE_GRACE_HOURS = 72          # مهلت آفلاین
HEARTBEAT_INTERVAL_SECONDS = 6 * 3600
HEARTBEAT_LOCK_TTL = HEARTBEAT_INTERVAL_SECONDS + 600
CLOCK_DRIFT_TOLERANCE = 300               # ثانیه
TAMPER_LOCK_DELAY_SECONDS = 150           # قفل با تأخیر، نه بلافاصله

LOCK_MESSAGE = 'لایسنس شما معتبر نیست'
CONTACT_MESSAGE = 'برای پیگیری با پشتیبانی تماس بگیرید.'

KEY_FINGERPRINT = '2eb31f539dbbb363b60ccee481fb4dcd0d935bf405f011e7a5f4a566ddbb7b8d'

PUBLIC_KEY_PEM = b"""-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAqYsUyiNH7/EivFpezWjm
eb/5d0VW/szCP2eYM5LH6TslfLildxVGf3TIYTwZz3XuiNhO8LZt7W6j5xjaB4aJ
bRNTKH6VURe7SuvWFnhT8CH3heNLhJxcmfBC1RWrcIxXctOn3PUGyV7baK3DwQst
/rFfcT2GYJZF5inLJAZ4Ix19efdKuhOB64/vkqCFvyVyS1CN+rEp8a9DeNqD6Fvt
YTqG/KR8cdL5zFj2Ti+d689YFExA/95WS7AczY2zocCjMNKGF2OKqqyq41XQ8MHJ
vM7wIE4MUHAXoo5dAaBo2Xb6h68SqKZqUaqUZeLCzXBE+0qIAaOxr7G5w7H4G0Ev
SQIDAQAB
-----END PUBLIC KEY-----"""

# وضعیت‌هایی که یعنی «سرور صریحاً رد کرد» → کش محلی باید پاک شود
REJECT_STATUSES = frozenset({
    'INVALID_KEY', 'INACTIVE', 'EXPIRED', 'DEVICE_MISMATCH',
    'NOT_ACTIVATED', 'PRODUCT_MISMATCH', 'TYPE_MISMATCH', 'APP_TYPE_MISMATCH',
})

# وضعیت‌هایی که یعنی «سقف دستگاه پر است» — کش پاک نمی‌شود ولی برنامه قفل است
LIMIT_STATUSES = frozenset({'ACTIVATION_LIMIT_REACHED', 'LIMIT_REACHED'})

# وضعیت‌های موقتی: کش نباید پاک شود
TRANSIENT_STATUSES = frozenset({'SERVER_ERROR', 'RATE_LIMITED', 'BAD_REQUEST'})

STATUS_HINTS = {
    'INVALID_KEY': 'کلید لایسنس در سامانه ثبت نشده است. ' + CONTACT_MESSAGE,
    'INACTIVE': 'لایسنس این نرم‌افزار غیرفعال شده است. ' + CONTACT_MESSAGE,
    'EXPIRED': 'اعتبار لایسنس به پایان رسیده است؛ لطفاً نسبت به تمدید اقدام کنید.',
    'DEVICE_MISMATCH': 'این لایسنس روی دستگاه دیگری فعال است. ابتدا آن دستگاه را آزاد کنید.',
    'ACTIVATION_LIMIT_REACHED': 'سقف تعداد دستگاه‌های مجاز پر شده است. یکی از دستگاه‌ها را آزاد کنید.',
    'LIMIT_REACHED': 'سقف تعداد دستگاه‌های مجاز پر شده است. یکی از دستگاه‌ها را آزاد کنید.',
    'APP_TYPE_MISMATCH': 'نوع نرم‌افزار با لایسنس هم‌خوانی ندارد. ' + CONTACT_MESSAGE,
    'PRODUCT_MISMATCH': 'این لایسنس برای محصول دیگری صادر شده است. ' + CONTACT_MESSAGE,
    'TYPE_MISMATCH': 'نوع لایسنس با این نسخه هم‌خوانی ندارد. ' + CONTACT_MESSAGE,
    'NOT_ACTIVATED': 'لایسنس هنوز روی این دستگاه فعال نشده است.',
    'RATE_LIMITED': 'درخواست‌ها بیش از حد مجاز است؛ چند دقیقه دیگر دوباره تلاش می‌شود.',
    'SERVER_ERROR': 'سرور لایسنس موقتاً پاسخ نمی‌دهد.',
    'BAD_REQUEST': 'درخواست ارسالی ناقص بود. ' + CONTACT_MESSAGE,
}


# ══════════════════════════════════════════════════════════════
#  استثناها
# ══════════════════════════════════════════════════════════════
class LicenseError(Exception):
    """خطای پایه سامانه لایسنس"""


class ServerUnreachable(LicenseError):
    """سرور لایسنس در دسترس نیست (شبکه، DNS یا تایم‌اوت)"""


class SignatureError(LicenseError):
    """امضای پاسخ نامعتبر است یا پاسخ تازه نیست (حمله بازپخش)"""


class FeatureLocked(LicenseError):
    """این بخش در لایسنس مشتری خریداری نشده است"""

    def __init__(self, feature=''):
        super().__init__(LOCK_MESSAGE)
        self.feature = feature


# ══════════════════════════════════════════════════════════════
#  پیکربندی — از همان مکانیزم settings.json برنامه خوانده می‌شود
# ══════════════════════════════════════════════════════════════
def _license_config():
    """بخش license از settings.json (با مقادیر پیش‌فرض امن)"""
    try:
        from config import load_config
        return load_config().get('license', {}) or {}
    except Exception:
        return {}


def server_url():
    url = (_license_config().get('server_url') or DEFAULT_SERVER_URL).strip()
    return url.rstrip('/')


def update_channel():
    return (_license_config().get('channel') or DEFAULT_CHANNEL).strip()


def auto_update_enabled():
    return bool(_license_config().get('auto_update', True))


# ══════════════════════════════════════════════════════════════
#  فاز ۳ — شناسه دستگاه
# ══════════════════════════════════════════════════════════════
_device_id_cache = None
_device_lock = threading.Lock()


def _desktop_identifier():
    """قفل سخت‌افزاری: MAC + نام سیستم + معماری پردازنده."""
    mac = uuid.getnode()
    # اگر بیت multicast روشن باشد یعنی MAC تصادفی است → قابل اتکا نیست
    mac_str = f'{mac:012x}' if not (mac >> 40) % 2 else 'no-mac'
    raw = f'{mac_str}|{socket.gethostname()}|{platform.machine()}'
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def get_device_identifier():
    """شناسه پایدار دستگاه — در هر اجرا همان مقدار قبلی."""
    global _device_id_cache
    with _device_lock:
        if _device_id_cache is None:
            _device_id_cache = _desktop_identifier()
        return _device_id_cache


def get_device_label():
    """نام قابل خواندن دستگاه برای نمایش در پنل مدیریت."""
    try:
        return f'{socket.gethostname()} — {platform.system()} {platform.release()}'[:120]
    except Exception:
        return 'دستگاه ناشناس'


# ══════════════════════════════════════════════════════════════
#  فاز ۲ — تایید امضای RSA-2048 / SHA-256 / PKCS#1 v1.5
# ══════════════════════════════════════════════════════════════
def canonical_json(payload):
    """باید مو‌به‌مو با سرور یکی باشد؛ هر تفاوتی امضا را باطل می‌کند."""
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def _load_public_key():
    return serialization.load_pem_public_key(PUBLIC_KEY_PEM)


def verify_signature(envelope):
    """تایید امضای پاکت پاسخ سرور. هر تصمیمی فقط پس از True شدن این تابع."""
    if not isinstance(envelope, dict):
        return False
    data = envelope.get('data')
    signature = envelope.get('signature')
    if not isinstance(data, dict) or not signature:
        return False
    fingerprint = envelope.get('key_fingerprint')
    if fingerprint and fingerprint != KEY_FINGERPRINT:
        logger.warning('license: key fingerprint mismatch')
        return False
    try:
        key = _load_public_key()
        key.verify(
            base64.b64decode(signature),
            canonical_json(data).encode('utf-8'),
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
        return True
    except (InvalidSignature, ValueError, TypeError):
        return False


# ══════════════════════════════════════════════════════════════
#  محل ذخیره‌سازی — بیرون از پوشه برنامه تا با به‌روزرسانی پاک نشود
# ══════════════════════════════════════════════════════════════
def storage_dir():
    base = os.environ.get('LOCALAPPDATA') or os.environ.get('APPDATA') or os.path.expanduser('~')
    folder = os.path.join(base, APP_NAME, 'license')
    os.makedirs(folder, exist_ok=True)
    return folder


def _state_path():
    return os.path.join(storage_dir(), 'state.dat')


def _key_path():
    return os.path.join(storage_dir(), 'license.dat')


def _heartbeat_lock_path():
    return os.path.join(storage_dir(), 'heartbeat.lock')


def _harden(path):
    """فقط کاربر جاری بتواند بخواند/بنویسد."""
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def _fernet(purpose, device_id):
    """کلید رمزنگاری از شناسه دستگاه مشتق می‌شود → کپی فایل روی دستگاه دیگر بی‌فایده است."""
    material = hashlib.sha256(f'{APP_NAME}|{purpose}|{device_id}'.encode('utf-8')).digest()
    return Fernet(base64.urlsafe_b64encode(material))


def _cache_key(device_id):
    return hashlib.sha256(f'{APP_NAME}|{device_id}'.encode('utf-8')).digest()


# ══════════════════════════════════════════════════════════════
#  فاز ۱٫۵ — ذخیره‌ی رمزنگاری‌شده‌ی کلید لایسنس
# ══════════════════════════════════════════════════════════════
def normalize_license_key(raw):
    """فاصله‌های اضافی حذف، حروف بزرگ، خط تیره‌ها حفظ."""
    if not raw:
        return ''
    value = str(raw).strip().upper()
    return ''.join(value.split())


def save_license_key(key):
    device_id = get_device_identifier()
    token = _fernet('key', device_id).encrypt(normalize_license_key(key).encode('utf-8'))
    path = _key_path()
    with open(path, 'wb') as handle:
        handle.write(token)
    _harden(path)


def load_license_key():
    device_id = get_device_identifier()
    try:
        with open(_key_path(), 'rb') as handle:
            token = handle.read()
    except OSError:
        return None
    try:
        return _fernet('key', device_id).decrypt(token).decode('utf-8')
    except (InvalidToken, ValueError):
        # فایل روی دستگاه دیگری ساخته شده یا دستکاری شده است
        _record_integrity_event('key_store', 'کلید ذخیره‌شده قابل بازگشایی نیست')
        return None


def clear_license_key():
    try:
        os.remove(_key_path())
    except OSError:
        pass


def has_stored_key():
    return os.path.exists(_key_path())


# ══════════════════════════════════════════════════════════════
#  فاز ۴ — کش محلی مهرشده با HMAC و رمزنگاری‌شده با شناسه دستگاه
# ══════════════════════════════════════════════════════════════
def save_cache(envelope, device_id, server_time=None):
    """کش را رمزنگاری و با HMAC مهر می‌کند تا دستکاری دستی قابل تشخیص باشد."""
    previous = load_cache(device_id) or {}
    seen = max(
        int(previous.get('max_server_time') or 0),
        int(server_time or 0),
        int(time.time()),
    )
    payload = {
        'envelope': envelope,
        'saved_at': int(time.time()),
        'max_server_time': seen,
    }
    body = _fernet('state', device_id).encrypt(
        json.dumps(payload, ensure_ascii=False).encode('utf-8')
    )
    tag = hmac.new(_cache_key(device_id), body, hashlib.sha256).digest()
    blob = base64.b64encode(tag + body).decode('ascii')
    path = _state_path()
    with open(path, 'w', encoding='utf-8') as handle:
        handle.write(blob)
    _harden(path)


def load_cache(device_id):
    try:
        with open(_state_path(), encoding='utf-8') as handle:
            raw = base64.b64decode(handle.read())
    except (OSError, ValueError):
        return None
    if len(raw) <= 32:
        return None
    tag, body = raw[:32], raw[32:]
    expected = hmac.new(_cache_key(device_id), body, hashlib.sha256).digest()
    if not hmac.compare_digest(tag, expected):
        _record_integrity_event('cache_hmac', 'مهر کش محلی معتبر نیست')
        return None
    try:
        return json.loads(_fernet('state', device_id).decrypt(body).decode('utf-8'))
    except (InvalidToken, ValueError):
        _record_integrity_event('cache_decrypt', 'کش محلی قابل بازگشایی نیست')
        return None


def clear_cache():
    try:
        os.remove(_state_path())
    except OSError:
        pass


# ══════════════════════════════════════════════════════════════
#  فاز ۸٫۵٫۵ — ثبت بی‌صدای رویدادهای دستکاری
# ══════════════════════════════════════════════════════════════
_integrity_events = []
_integrity_lock = threading.Lock()
_tamper_detected_at = None


def _record_integrity_event(kind, detail):
    """رویداد دستکاری فقط لاگ و صف می‌شود؛ به کاربر چیزی گفته نمی‌شود."""
    global _tamper_detected_at
    with _integrity_lock:
        _integrity_events.append({'kind': kind, 'detail': detail, 'at': int(time.time())})
        del _integrity_events[:-20]
        if _tamper_detected_at is None:
            _tamper_detected_at = time.monotonic()
    logger.warning('license integrity event: %s — %s', kind, detail)


def _pending_integrity_events():
    with _integrity_lock:
        return list(_integrity_events)


def _flush_integrity_events():
    with _integrity_lock:
        _integrity_events.clear()


def _tamper_locked():
    """پس از تشخیص دستکاری، قفل با تأخیر اعمال می‌شود نه بلافاصله."""
    with _integrity_lock:
        detected = _tamper_detected_at
    return detected is not None and (time.monotonic() - detected) >= TAMPER_LOCK_DELAY_SECONDS


# ══════════════════════════════════════════════════════════════
#  ارتباط با سرور لایسنس
# ══════════════════════════════════════════════════════════════
def _headers():
    return {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
        'User-Agent': f'{PRODUCT_SLUG}-client/{current_version()}',
    }


def _check_server_clock(data):
    """اختلاف بیش از ۳۰۰ ثانیه بین ساعت سیستم و سرور هشدار دارد."""
    server_time = data.get('server_time')
    if not server_time:
        return
    try:
        drift = abs(int(server_time) - int(time.time()))
    except (TypeError, ValueError):
        return
    if drift > CLOCK_DRIFT_TOLERANCE:
        _record_integrity_event(
            'clock_drift', f'اختلاف ساعت سیستم با سرور: {drift} ثانیه'
        )


def _call(path, payload, timeout=REQUEST_TIMEOUT, attempts=3):
    """
    یک درخواست امضاشده به سرور لایسنس.
    خروجی: پاکت کامل (envelope) — فقط پس از تایید امضا و تطبیق nonce.
    """
    nonce = secrets.token_hex(16)
    body = dict(payload)
    body['nonce'] = nonce
    events = _pending_integrity_events()
    if events:
        body['integrity_events'] = events

    url = f'{server_url()}{path}'
    last_error = None

    for index in range(attempts):
        try:
            response = requests.post(url, json=body, headers=_headers(), timeout=timeout)
        except requests.RequestException as exc:
            last_error = f'خطای شبکه: {type(exc).__name__}'
        else:
            envelope = None
            try:
                envelope = response.json()
            except ValueError:
                envelope = None

            if isinstance(envelope, dict) and isinstance(envelope.get('data'), dict):
                if not verify_signature(envelope):
                    _record_integrity_event('signature', f'امضای پاسخ {path} نامعتبر است')
                    raise SignatureError('امضای سرور نامعتبر است')
                data = envelope['data']
                if data.get('nonce') != nonce:
                    _record_integrity_event('replay', f'nonce پاسخ {path} تطبیق ندارد')
                    raise SignatureError('پاسخ تازه نیست — احتمال حمله‌ی بازپخش')
                _check_server_clock(data)
                _flush_integrity_events()
                return envelope

            last_error = f'پاسخ نامعتبر سرور (HTTP {response.status_code})'

        if index < len(RETRY_DELAYS):
            time.sleep(RETRY_DELAYS[index])

    raise ServerUnreachable(last_error or 'ارتباط با سرور لایسنس برقرار نشد')


def _base_payload(license_key):
    return {
        'license_key': license_key,
        'device_identifier': get_device_identifier(),
    }


def call_activate(license_key):
    payload = _base_payload(license_key)
    payload.update({
        'app_type': APP_TYPE,
        'product': PRODUCT_SLUG,
        'device_label': get_device_label(),
        'available_features': AVAILABLE_FEATURES,
    })
    return _call('/api/v1/activate', payload)


def call_verify(license_key):
    return _call('/api/v1/verify', _base_payload(license_key))


def call_heartbeat(license_key):
    payload = _base_payload(license_key)
    payload['app_type'] = APP_TYPE
    payload['product'] = PRODUCT_SLUG
    return _call('/api/v1/heartbeat', payload)


def call_deactivate(license_key):
    return _call('/api/v1/deactivate', _base_payload(license_key))


# ══════════════════════════════════════════════════════════════
#  وضعیت لایسنس — همیشه از داده‌ی امضاشده ساخته می‌شود
# ══════════════════════════════════════════════════════════════
def _parse_expires_at(value):
    if not value:
        return None
    try:
        text = str(value).strip().replace('Z', '+00:00')
        moment = datetime.fromisoformat(text)
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment


class LicenseState:
    """
    وضعیت جاری لایسنس. تمام مقادیر از `envelope['data']`ی می‌آید که
    امضایش تایید شده است — هیچ پرچم بولیِ محاسبه‌شده در جای دیگر.
    """

    def __init__(self, status, message, data=None, valid=False, source='none',
                 needs_activation=False, transient=False):
        self.status = status
        self.message = message
        self.data = data if isinstance(data, dict) else {}
        self.valid = bool(valid)
        self.source = source
        self.needs_activation = bool(needs_activation)
        self.transient = bool(transient)
        self.checked_at = time.time()
        self.checked_monotonic = time.monotonic()

    # ── داده‌های نمایشی (همه از سرور) ────────────────────────
    @property
    def client_name(self):
        return self.data.get('client_name') or ''

    @property
    def expires_at(self):
        return self.data.get('expires_at')

    @property
    def max_activations(self):
        return self.data.get('max_activations')

    @property
    def current_activations(self):
        return self.data.get('current_activations')

    @property
    def is_trial(self):
        return bool(self.data.get('is_trial'))

    @property
    def in_grace(self):
        return bool(self.data.get('in_grace'))

    @property
    def grace_days_remaining(self):
        return self.data.get('grace_days_remaining')

    @property
    def feature_labels(self):
        labels = dict(FEATURE_LABELS)
        server_labels = self.data.get('feature_labels')
        if isinstance(server_labels, dict):
            labels.update({str(k): str(v) for k, v in server_labels.items()})
        return labels

    @property
    def allowed_features(self):
        features = self.data.get('allowed_features')
        return features if isinstance(features, dict) else {}

    @property
    def revalidate_minutes(self):
        try:
            value = int(self.data.get('revalidate_minutes') or DEFAULT_REVALIDATE_MINUTES)
        except (TypeError, ValueError):
            value = DEFAULT_REVALIDATE_MINUTES
        return max(5, value)

    @property
    def offline_grace_hours(self):
        try:
            value = int(self.data.get('offline_grace_hours') or DEFAULT_OFFLINE_GRACE_HOURS)
        except (TypeError, ValueError):
            value = DEFAULT_OFFLINE_GRACE_HOURS
        return max(0, value)

    @property
    def force_recheck(self):
        return bool(self.data.get('force_recheck'))

    def has_feature(self, name):
        """پیش‌فرض همیشه بسته است؛ فقط مقدار True در پاسخ امضاشده باز می‌کند."""
        if not self.valid:
            return False
        return bool(self.allowed_features.get(name, False))

    def as_dict(self):
        return {
            'status': self.status,
            'message': self.message,
            'valid': self.valid,
            'source': self.source,
            'needs_activation': self.needs_activation,
            'client_name': self.client_name,
            'expires_at': self.expires_at,
            'in_grace': self.in_grace,
            'grace_days_remaining': self.grace_days_remaining,
            'is_trial': self.is_trial,
            'max_activations': self.max_activations,
            'current_activations': self.current_activations,
            'allowed_features': self.allowed_features,
            'feature_labels': self.feature_labels,
            'checked_at': int(self.checked_at),
        }


_state = None
_state_lock = threading.Lock()
_refresh_lock = threading.RLock()
_background_refresh = None


def _store_state(state):
    global _state
    with _state_lock:
        _state = state
    return state


def _no_key_state():
    return LicenseState(
        status='NO_KEY',
        message='برای استفاده از نرم‌افزار، کلید لایسنس خود را وارد کنید.',
        needs_activation=True,
    )


def _state_from_data(data, envelope, device_id):
    """ساخت وضعیت از پاسخ زنده‌ی سرور (امضا و nonce قبلاً تایید شده)."""
    status = str(data.get('status') or ('SUCCESS' if data.get('success') else 'SERVER_ERROR'))
    message = data.get('message') or STATUS_HINTS.get(status, '')

    if data.get('success') and status == 'SUCCESS':
        save_cache(envelope, device_id, server_time=data.get('server_time'))
        return LicenseState(status=status, message=message or 'لایسنس معتبر است.',
                            data=data, valid=True, source='online')

    if status in REJECT_STATUSES:
        # ابطال از سمت سرور → کش کهنه نباید برنامه را زنده نگه دارد
        clear_cache()
        return LicenseState(
            status=status,
            message=message or STATUS_HINTS.get(status, LOCK_MESSAGE),
            data=data,
            needs_activation=(status == 'NOT_ACTIVATED'),
        )

    if status in LIMIT_STATUSES:
        return LicenseState(status=status, message=message or STATUS_HINTS[status], data=data)

    # SERVER_ERROR / RATE_LIMITED / BAD_REQUEST و هر وضعیت ناشناخته → موقتی
    logger.warning('license: transient server status %s', status)
    return _state_from_cache(device_id, fallback_status=status,
                             fallback_message=message or STATUS_HINTS.get(status, ''))


def _state_from_cache(device_id, fallback_status='OFFLINE', fallback_message=''):
    """
    تصمیم‌گیری آفلاین. کش فقط وقتی معتبر است که:
      امضا دوباره تایید شود، به همین دستگاه گره خورده باشد،
      مهلت آفلاین تمام نشده باشد، تاریخ انقضا نگذشته باشد و
      ساعت سیستم عقب کشیده نشده باشد.
    """
    cache = load_cache(device_id)
    if not cache:
        return LicenseState(
            status=fallback_status if fallback_status != 'OFFLINE' else 'OFFLINE_NO_CACHE',
            message=fallback_message or 'برای بررسی لایسنس، اتصال به اینترنت لازم است.',
            transient=True,
        )

    envelope = cache.get('envelope')
    if not verify_signature(envelope):
        _record_integrity_event('cache_signature', 'امضای کش محلی معتبر نیست')
        clear_cache()
        return LicenseState(status='SIGNATURE_ERROR',
                            message='اعتبارسنجی لایسنس ناموفق بود. ' + CONTACT_MESSAGE)

    data = envelope.get('data') or {}

    if data.get('device_fingerprint') and data['device_fingerprint'] != device_id:
        _record_integrity_event('cache_device', 'کش متعلق به دستگاه دیگری است')
        clear_cache()
        return LicenseState(status='DEVICE_MISMATCH',
                            message=STATUS_HINTS['DEVICE_MISMATCH'])

    saved_at = int(cache.get('saved_at') or 0)
    max_server_time = int(cache.get('max_server_time') or saved_at)
    now = int(time.time())

    # ── ۸٫۵٫۳ تشخیص عقب کشیدن ساعت ───────────────────────────
    if now + CLOCK_DRIFT_TOLERANCE < max_server_time:
        _record_integrity_event('clock_rollback', 'ساعت سیستم عقب کشیده شده است')
        return LicenseState(
            status='CLOCK_TAMPER',
            message='برای ادامه‌ی کار، اتصال به اینترنت لازم است.',
        )

    # ── انقضای لایسنس حتی در حالت آفلاین ─────────────────────
    expires_at = _parse_expires_at(data.get('expires_at'))
    if expires_at and datetime.now(timezone.utc) > expires_at and not data.get('in_grace'):
        clear_cache()
        return LicenseState(status='EXPIRED', message=STATUS_HINTS['EXPIRED'], data=data)

    # ── مهلت آفلاین ──────────────────────────────────────────
    state_for_policy = LicenseState(status='CACHE', message='', data=data)
    grace_seconds = state_for_policy.offline_grace_hours * 3600
    if grace_seconds and now - saved_at > grace_seconds:
        hours = state_for_policy.offline_grace_hours
        return LicenseState(
            status='OFFLINE_EXPIRED',
            message=f'بیش از {hours} ساعت است لایسنس بررسی نشده است؛ '
                    'لطفاً برنامه را به اینترنت متصل کنید.',
            data=data,
        )

    message = 'اتصال به سرور لایسنس برقرار نشد؛ برنامه با اعتبارسنجی قبلی کار می‌کند.'
    return LicenseState(status='SUCCESS', message=fallback_message or message,
                        data=data, valid=True, source='cache')


def refresh_state(force_online=True):
    """
    اعتبارسنجی کامل: همیشه اول verify، و فقط در صورت NOT_ACTIVATED
    فراخوانی activate (تا فعال‌سازی‌ها بی‌دلیل سوخته نشوند).
    """
    with _refresh_lock:
        device_id = get_device_identifier()
        license_key = load_license_key()

        if not license_key:
            clear_cache()
            return _store_state(_no_key_state())

        if not force_online:
            return _store_state(_state_from_cache(device_id))

        try:
            envelope = call_verify(license_key)
        except SignatureError as exc:
            clear_cache()
            logger.warning('license: %s', exc)
            return _store_state(LicenseState(
                status='SIGNATURE_ERROR',
                message='امضای سرور نامعتبر است. ' + CONTACT_MESSAGE,
            ))
        except ServerUnreachable as exc:
            logger.info('license: server unreachable (%s) — falling back to cache', exc)
            return _store_state(_state_from_cache(device_id))

        data = envelope['data']

        # هنوز روی این دستگاه فعال نشده → مسیر activate
        if str(data.get('status')) == 'NOT_ACTIVATED':
            try:
                envelope = call_activate(license_key)
                data = envelope['data']
            except SignatureError as exc:
                clear_cache()
                logger.warning('license: %s', exc)
                return _store_state(LicenseState(
                    status='SIGNATURE_ERROR',
                    message='امضای سرور نامعتبر است. ' + CONTACT_MESSAGE,
                ))
            except ServerUnreachable as exc:
                logger.info('license: activation postponed (%s)', exc)
                return _store_state(_state_from_cache(device_id))

        return _store_state(_state_from_data(data, envelope, device_id))


def _needs_revalidation(state):
    if state.force_recheck:
        return True
    age = time.monotonic() - state.checked_monotonic
    if state.valid:
        return age > state.revalidate_minutes * 60
    # وضعیت‌های موقتی زودتر دوباره بررسی می‌شوند
    return age > 300 if state.transient else age > 900


def _spawn_background_refresh():
    """به‌روزرسانی وضعیت در پس‌زمینه تا درخواست کاربر معطل نماند."""
    global _background_refresh
    with _state_lock:
        if _background_refresh is not None and _background_refresh.is_alive():
            return

        def _worker():
            try:
                refresh_state()
            except Exception:
                logger.exception('license: background refresh failed')

        _background_refresh = threading.Thread(
            target=_worker, name='license-refresh', daemon=True
        )
        _background_refresh.start()


def get_state(force=False):
    """وضعیت جاری لایسنس (کش‌شده در حافظه؛ در هر درخواست به سرور زنگ نمی‌زند)."""
    with _state_lock:
        state = _state

    if state is None:
        return refresh_state()

    if force:
        return refresh_state()

    if _needs_revalidation(state):
        if state.valid:
            _spawn_background_refresh()   # stale-while-revalidate
        else:
            return refresh_state()

    # دستکاری تشخیص داده شده → قفل با تأخیر و بی‌صدا
    if state.valid and _tamper_locked():
        return _store_state(LicenseState(
            status='INTEGRITY_ERROR',
            message='اعتبارسنجی لایسنس ناموفق بود. ' + CONTACT_MESSAGE,
        ))

    return state


def license_is_valid():
    return get_state().valid


def license_reason():
    return get_state().message


def has_feature(name):
    """
    آیا این بخش برای مشتریِ در حال اجرا باز است؟
    تنها مرجع: allowed_features در پاسخ امضاشده.
    """
    return get_state().has_feature(name)


def assert_feature(name):
    """نسخه‌ی سرویسی: در عمق منطق برنامه صدا زده می‌شود، نه فقط در لایه‌ی مسیر."""
    if not has_feature(name):
        raise FeatureLocked(name)


# ══════════════════════════════════════════════════════════════
#  عملیات صفحه‌ی فعال‌سازی
# ══════════════════════════════════════════════════════════════
def activate_with_key(raw_key):
    """
    فعال‌سازی با کلیدی که کاربر وارد کرده است.
    خروجی: dict با کلیدهای success و message (پیام مستقیماً از سرور).
    """
    key = normalize_license_key(raw_key)
    if not key:
        return {'success': False, 'message': 'کلید لایسنس را وارد کنید.'}

    device_id = get_device_identifier()

    # اول verify؛ اگر این کلید قبلاً روی همین دستگاه فعال شده باشد،
    # یک فعال‌سازی بی‌دلیل سوخته نمی‌شود.
    try:
        envelope = call_verify(key)
        data = envelope['data']
        if str(data.get('status')) == 'NOT_ACTIVATED':
            envelope = call_activate(key)
            data = envelope['data']
    except SignatureError:
        return {'success': False,
                'message': 'امضای سرور نامعتبر است. ' + CONTACT_MESSAGE}
    except ServerUnreachable:
        return {'success': False, 'server_unreachable': True,
                'message': 'ارتباط با سرور برقرار نشد. اتصال اینترنت را بررسی کنید.'}

    if data.get('success') and str(data.get('status')) == 'SUCCESS':
        save_license_key(key)
        save_cache(envelope, device_id, server_time=data.get('server_time'))
        _store_state(LicenseState(status='SUCCESS', message=data.get('message') or 'لایسنس فعال شد.',
                                  data=data, valid=True, source='online'))
        return {'success': True, 'message': data.get('message') or 'لایسنس با موفقیت فعال شد.',
                'client_name': data.get('client_name') or ''}

    status = str(data.get('status') or '')
    message = data.get('message') or STATUS_HINTS.get(status) or 'کلید معتبر نیست.'
    _store_state(LicenseState(status=status or 'INVALID_KEY', message=message, data=data,
                              needs_activation=True))
    return {'success': False, 'status': status, 'message': message}


def deactivate_current_device():
    """آزادسازی این دستگاه تا مشتری بتواند لایسنس را جای دیگری ببرد."""
    key = load_license_key()
    if not key:
        return {'success': False, 'message': 'کلید لایسنسی روی این دستگاه ذخیره نشده است.'}
    try:
        envelope = call_deactivate(key)
    except SignatureError:
        return {'success': False, 'message': 'امضای سرور نامعتبر است. ' + CONTACT_MESSAGE}
    except ServerUnreachable:
        return {'success': False,
                'message': 'ارتباط با سرور برقرار نشد. اتصال اینترنت را بررسی کنید.'}

    data = envelope['data']
    if data.get('success'):
        clear_cache()
        clear_license_key()
        _store_state(_no_key_state())
        return {'success': True, 'message': data.get('message') or 'لایسنس این دستگاه آزاد شد.'}
    return {'success': False, 'message': data.get('message') or 'آزادسازی انجام نشد.'}


# ══════════════════════════════════════════════════════════════
#  فاز ۱٫۳ — ضربان دوره‌ای
# ══════════════════════════════════════════════════════════════
def _heartbeat_slot_is_free():
    """در استقرار چندworker فقط یک پروسه ضربان بفرستد."""
    path = _heartbeat_lock_path()
    now = time.time()
    try:
        if os.path.exists(path) and now - os.path.getmtime(path) < HEARTBEAT_LOCK_TTL:
            with open(path, encoding='utf-8') as handle:
                owner = handle.read().strip()
            if owner and owner != str(os.getpid()):
                return False
        with open(path, 'w', encoding='utf-8') as handle:
            handle.write(str(os.getpid()))
        _harden(path)
        return True
    except OSError:
        return True


def _heartbeat_loop():
    while True:
        time.sleep(HEARTBEAT_INTERVAL_SECONDS)
        try:
            if not _heartbeat_slot_is_free():
                continue
            key = load_license_key()
            if not key:
                continue
            envelope = call_heartbeat(key)
            data = envelope['data']
            status = str(data.get('status') or '')
            if data.get('success') and status == 'SUCCESS':
                save_cache(envelope, get_device_identifier(), server_time=data.get('server_time'))
                _store_state(LicenseState(status=status, message=data.get('message') or '',
                                          data=data, valid=True, source='online'))
            elif status in REJECT_STATUSES:
                clear_cache()
                _store_state(LicenseState(status=status,
                                          message=data.get('message') or STATUS_HINTS.get(status, LOCK_MESSAGE),
                                          data=data))
        except (LicenseError, requests.RequestException) as exc:
            # شکست ضربان نباید برنامه را ببندد؛ فقط لاگ می‌شود
            logger.info('license heartbeat failed: %s', exc)
        except Exception:
            logger.exception('license heartbeat error')


def start_heartbeat():
    thread = threading.Thread(target=_heartbeat_loop, name='license-heartbeat', daemon=True)
    thread.start()
    return thread


# ══════════════════════════════════════════════════════════════
#  نسخه‌ی جاری برنامه
# ══════════════════════════════════════════════════════════════
def app_root():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def current_version():
    try:
        with open(os.path.join(app_root(), 'VERSION'), encoding='utf-8') as handle:
            value = handle.read().strip()
        return value or '1.0.1'
    except OSError:
        return '1.0.1'


# ══════════════════════════════════════════════════════════════
#  فاز ۶ و ۷ — لایه‌ی محافظت از مسیرها
# ══════════════════════════════════════════════════════════════
def _wants_json():
    if request.is_json:
        return True
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return True
    accept = request.accept_mimetypes
    return accept['application/json'] > accept['text/html']


def locked_response():
    """قفل بخش: کد ۲۰۰ و فقط یک جمله به‌جای محتوا — نه ۴۰۳، نه مخفی‌کاری."""
    if _wants_json():
        return jsonify({'ok': False, 'message': LOCK_MESSAGE}), 200
    return render_template('license/locked.html', message=LOCK_MESSAGE), 200


def unlicensed_response(state=None):
    """پاسخ وقتی خودِ لایسنس معتبر نیست."""
    state = state or get_state()
    if state.needs_activation:
        if _wants_json():
            return jsonify({'ok': False, 'status': state.status, 'message': state.message}), 403
        return redirect(url_for('license.activate'))
    if _wants_json():
        return jsonify({'ok': False, 'status': state.status, 'message': state.message}), 403
    return render_template('license/blocked.html', state=state, reason=state.message), 403


def license_required(func):
    """قفل لایسنس روی یک مسیر مشخص (نقطه‌ی کنترل مستقل از نگهبان سراسری)."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        state = get_state()
        if not state.valid:
            return unlicensed_response(state)
        return func(*args, **kwargs)
    return wrapper


def licensed_section(name):
    """
    قفل بخش با الگوی «پیام به‌جای محتوا».
    مسیر همچنان ۲۰۰ برمی‌گرداند تا منو و لینک‌ها نشکنند.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if has_feature(name):
                return func(*args, **kwargs)
            return locked_response()
        return wrapper
    return decorator


# ══════════════════════════════════════════════════════════════
#  فاز ۷ — تزریق به برنامه
# ══════════════════════════════════════════════════════════════
_audit_done = False


def _required_update_block():
    """پیام به‌روزرسانی اجباریِ انجام‌نشده (در غیر این صورت None)."""
    try:
        from license_updater import required_update_message
        return required_update_message()
    except Exception:
        return None


def _log_endpoint_audit(app):
    """گزارش پوشش نگاشت بخش↔مسیر (یک‌بار، در اولین درخواست)."""
    global _audit_done
    if _audit_done:
        return
    _audit_done = True
    try:
        report = audit_endpoint_coverage(app.url_map)
    except Exception:
        return
    if report['unmapped']:
        app.logger.warning('license: %s endpoint(s) بدون نگاشت بخش: %s',
                           len(report['unmapped']), ', '.join(report['unmapped'][:20]))
    if report['unknown_keys']:
        app.logger.warning('license: کلید بخش ناشناخته در نگاشت: %s',
                           ', '.join(report['unknown_keys']))


def init_license(app):
    """
    راه‌اندازی سامانه لایسنس روی برنامه.
    باید داخل create_app و پیش از ثبت Blueprintها صدا زده شود.
    """
    config = _license_config()
    app.config['LICENSE_SERVER_URL'] = config.get('server_url') or DEFAULT_SERVER_URL
    app.config['LICENSE_PRODUCT'] = PRODUCT_SLUG
    app.config['LICENSE_APP_TYPE'] = APP_TYPE
    app.config['LICENSE_CHANNEL'] = update_channel()
    app.config['LICENSE_AUTO_UPDATE'] = auto_update_enabled()
    app.config['APP_VERSION'] = current_version()

    @app.before_request
    def _license_guard():
        """نگهبان سراسری: لایسنس، سپس قفل بخش."""
        _log_endpoint_audit(app)

        endpoint = request.endpoint
        if is_exempt_endpoint(endpoint):
            return None

        state = get_state()
        if not state.valid:
            return unlicensed_response(state)

        # به‌روزرسانی اجباریِ انجام‌نشده → برنامه نباید ادامه دهد
        blocking = _required_update_block()
        if blocking:
            if _wants_json():
                return jsonify({'ok': False, 'status': 'UPDATE_REQUIRED',
                                'message': blocking}), 403
            return render_template('license/blocked.html', state=state,
                                   reason=blocking), 403

        feature = feature_for_endpoint(endpoint)
        if feature and not state.has_feature(feature):
            return locked_response()
        return None

    @app.context_processor
    def _inject_license_state():
        state = get_state()
        return {
            'license_state': state,
            'license_lock_message': LOCK_MESSAGE,
            'app_version': current_version(),
        }

    # اعتبارسنجی اولیه و بررسی به‌روزرسانی — بدون بلاک‌کردن بالا آمدن برنامه
    def _startup_worker():
        try:
            state = refresh_state()
        except Exception:
            app.logger.exception('license: startup validation failed')
            return
        if not state.valid:
            app.logger.warning('license: startup state=%s', state.status)
            return
        if not app.config['LICENSE_AUTO_UPDATE']:
            return
        try:
            from license_updater import check_and_apply_update
            check_and_apply_update(silent=True)
        except Exception:
            app.logger.exception('به‌روزرسانی ناموفق بود')
            # برنامه باید با نسخه فعلی به کار خود ادامه دهد

    threading.Thread(target=_startup_worker, name='license-startup', daemon=True).start()
    start_heartbeat()
    app.logger.info('license: subsystem initialised (product=%s)', PRODUCT_SLUG)
    return app
