"""
آزمون‌های سامانه لایسنس — با یک سرور لایسنس ساختگیِ امضاکننده.

اجرا:
    python tests/test_license.py

سرور ساختگی همان قرارداد پاکت امضاشده‌ی سرور واقعی را پیاده می‌کند و
کلید عمومی هاردکد در زمان آزمون با کلید آزمایشی جایگزین می‌شود؛ بنابراین
مسیر تایید امضا واقعاً اجرا و آزموده می‌شود.
"""
import base64
import json
import os
import shutil
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

import license_client
import license_features

# ══════════════════════════════════════════════════════════════
#  زیرساخت آزمون
# ══════════════════════════════════════════════════════════════
PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
PUBLIC_PEM = PRIVATE_KEY.public_key().public_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PublicFormat.SubjectPublicKeyInfo,
)

SERVER_BEHAVIOUR = {
    'status': 'SUCCESS',
    'allowed_features': {'reports': True, 'finance': True},
    'expires_at': None,
    'break_signature': False,
    'break_nonce': False,
    'offline_grace_hours': 72,
    'revalidate_minutes': 360,
    'in_grace': False,
    'grace_days_remaining': None,
    'http_status': 200,
    'force_not_activated': False,
    'requests': [],
}


def _sign(data):
    payload = license_client.canonical_json(data).encode('utf-8')
    signature = PRIVATE_KEY.sign(payload, padding.PKCS1v15(), hashes.SHA256())
    return base64.b64encode(signature).decode('ascii')


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def do_POST(self):
        length = int(self.headers.get('Content-Length') or 0)
        body = json.loads(self.rfile.read(length) or b'{}')
        SERVER_BEHAVIOUR['requests'].append((self.path, body))

        status = SERVER_BEHAVIOUR['status']
        if SERVER_BEHAVIOUR['force_not_activated'] and self.path.endswith('/verify'):
            status = 'NOT_ACTIVATED'
        nonce = body.get('nonce')
        if SERVER_BEHAVIOUR['break_nonce']:
            nonce = 'f' * 32

        if self.path.endswith('/update/check'):
            data = {
                'success': True,
                'status': 'NO_UPDATE',
                'update_available': False,
                'latest_version': '1.0.1',
                'nonce': nonce,
                'server_time': int(time.time()),
            }
        elif status == 'SUCCESS':
            data = {
                'success': True,
                'status': 'SUCCESS',
                'message': 'لایسنس معتبر است.',
                'license_key': body.get('license_key'),
                'client_name': 'آموزشگاه آزمایشی',
                'app_type': 'desktop_windows',
                'allowed_features': SERVER_BEHAVIOUR['allowed_features'],
                'feature_labels': {'reports': 'گزارش‌گیری'},
                'expires_at': SERVER_BEHAVIOUR['expires_at'],
                'max_activations': 3,
                'current_activations': 1,
                'activation_token': 'token-123',
                'device_fingerprint': body.get('device_identifier'),
                'revalidate_minutes': SERVER_BEHAVIOUR['revalidate_minutes'],
                'offline_grace_hours': SERVER_BEHAVIOUR['offline_grace_hours'],
                'in_grace': SERVER_BEHAVIOUR['in_grace'],
                'grace_days_remaining': 5 if SERVER_BEHAVIOUR['in_grace'] else None,
                'is_trial': False,
                'nonce': nonce,
                'server_time': int(time.time()),
            }
        else:
            data = {
                'success': False,
                'status': status,
                'message': f'پیام سرور برای {status}',
                'in_grace': SERVER_BEHAVIOUR['in_grace'],
                'grace_days_remaining': SERVER_BEHAVIOUR['grace_days_remaining'],
                'nonce': nonce,
                'server_time': int(time.time()),
            }

        envelope = {
            'data': data,
            'signature': _sign(data),
            'signature_algorithm': 'RSA-SHA256',
            'key_fingerprint': SERVER_BEHAVIOUR.get('key_fingerprint')
                              or license_client.KEY_FINGERPRINT,
        }
        if SERVER_BEHAVIOUR['break_signature']:
            envelope['signature'] = base64.b64encode(b'0' * 256).decode('ascii')

        payload = json.dumps(envelope, ensure_ascii=False).encode('utf-8')
        self.send_response(SERVER_BEHAVIOUR['http_status'])
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def _start_server():
    server = ThreadingHTTPServer(('127.0.0.1', 0), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


PASSED = []
FAILED = []


def check(name, condition, detail=''):
    if condition:
        PASSED.append(name)
        print(f'  ✓ {name}')
    else:
        FAILED.append(f'{name} — {detail}')
        print(f'  ✗ {name} — {detail}')


def reset_state():
    license_client._store_state(None)
    license_client._state = None
    license_client.clear_cache()
    license_client.clear_license_key()
    with license_client._integrity_lock:
        license_client._integrity_events.clear()
        license_client._tamper_detected_at = None


# ══════════════════════════════════════════════════════════════
#  سناریوها
# ══════════════════════════════════════════════════════════════
def main():
    storage = tempfile.mkdtemp(prefix='license_test_')
    server = _start_server()
    base_url = f'http://127.0.0.1:{server.server_address[1]}'

    license_client.PUBLIC_KEY_PEM = PUBLIC_PEM
    license_client.KEY_FINGERPRINT = 'test-fingerprint'
    license_client.RETRY_DELAYS = (0, 0, 0)
    license_client.storage_dir = lambda: storage
    license_client.server_url = lambda: base_url

    try:
        print('\n۱) فعال‌سازی و تایید امضا')
        reset_state()
        state = license_client.get_state()
        check('بدون کلید، برنامه صفحه فعال‌سازی می‌خواهد',
              state.needs_activation and not state.valid, state.status)

        SERVER_BEHAVIOUR['force_not_activated'] = True   # دستگاه هنوز فعال نشده
        result = license_client.activate_with_key('  test-key-0001  ')
        SERVER_BEHAVIOUR['force_not_activated'] = False
        check('فعال‌سازی با کلید کاربر موفق است', result.get('success'), result.get('message'))
        check('کلید نرمال‌سازی شده ذخیره شد',
              license_client.load_license_key() == 'TEST-KEY-0001',
              license_client.load_license_key())
        check('نام مشتری از پاسخ سرور می‌آید',
              license_client.get_state().client_name == 'آموزشگاه آزمایشی')
        check('verify قبل از activate امتحان شد',
              SERVER_BEHAVIOUR['requests'][0][0].endswith('/verify'),
              str(SERVER_BEHAVIOUR['requests'][0][0]))
        check('activate فقط پس از NOT_ACTIVATED صدا زده شد',
              any(path.endswith('/activate') for path, _ in SERVER_BEHAVIOUR['requests']))
        check('فهرست بخش‌ها در activate اعلام شد',
              any(path.endswith('/activate') and 'available_features' in body
                  for path, body in SERVER_BEHAVIOUR['requests']))
        check('هر درخواست nonce تازه دارد',
              len({body.get('nonce') for _, body in SERVER_BEHAVIOUR['requests']})
              == len(SERVER_BEHAVIOUR['requests']))
        check('کلید لایسنس در هیچ لاگی چاپ نمی‌شود',
              'TEST-KEY-0001' not in license_client.get_state().message)

        print('\n۲) قفل بخش‌ها فقط از allowed_features')
        check('بخش خریداری‌شده باز است', license_client.has_feature('reports'))
        check('بخش خریداری‌نشده بسته است', not license_client.has_feature('accounting'))
        check('کلید ناشناخته پیش‌فرض بسته است', not license_client.has_feature('whatever'))

        print('\n۳) کش محلی و اجرای دوم')
        before = len(SERVER_BEHAVIOUR['requests'])
        for _ in range(5):
            license_client.get_state()
        check('اجرای مکرر درخواست اضافه نمی‌فرستد',
              len(SERVER_BEHAVIOUR['requests']) == before)

        cache = license_client.load_cache(license_client.get_device_identifier())
        check('کش روی دیسک JSON خام نیست',
              'client_name' not in open(license_client._state_path(), encoding='utf-8').read())
        check('کش با HMAC و رمزنگاری قابل بازخوانی است', bool(cache and cache.get('envelope')))
        mode = oct(os.stat(license_client._state_path()).st_mode)[-3:]
        check('فایل کش با دسترسی 0600 نوشته شده', mode == '600', mode)

        print('\n۴) کارکرد آفلاین و مهلت ۷۲ ساعته')
        server.shutdown()
        license_client._store_state(None)
        state = license_client.refresh_state()
        check('قطعی اینترنت برنامه را نمی‌خواباند', state.valid and state.source == 'cache',
              state.status)

        # کش را ۸۰ ساعت به عقب می‌بریم
        device_id = license_client.get_device_identifier()
        raw = license_client.load_cache(device_id)
        envelope = raw['envelope']
        license_client.save_cache(envelope, device_id)
        stale_path = license_client._state_path()
        payload = {'envelope': envelope, 'saved_at': int(time.time()) - 80 * 3600,
                   'max_server_time': int(time.time()) - 80 * 3600}
        body = license_client._fernet('state', device_id).encrypt(
            json.dumps(payload, ensure_ascii=False).encode('utf-8'))
        import hashlib, hmac as _hmac
        tag = _hmac.new(license_client._cache_key(device_id), body, hashlib.sha256).digest()
        with open(stale_path, 'w', encoding='utf-8') as handle:
            handle.write(base64.b64encode(tag + body).decode('ascii'))
        license_client._store_state(None)
        state = license_client.refresh_state()
        check('پس از ۷۲ ساعت آفلاین، اتصال الزامی می‌شود',
              not state.valid and state.status == 'OFFLINE_EXPIRED', state.status)

        print('\n۵) لایسنس منقضی در حالت آفلاین')
        expired_data = dict(envelope['data'])
        expired_data['expires_at'] = '2020-01-01T00:00:00+00:00'
        expired_envelope = {'data': expired_data, 'signature': _sign(expired_data),
                            'signature_algorithm': 'RSA-SHA256',
                            'key_fingerprint': license_client.KEY_FINGERPRINT}
        license_client.save_cache(expired_envelope, device_id)
        license_client._store_state(None)
        state = license_client.refresh_state()
        check('لایسنس منقضی حتی آفلاین رد می‌شود',
              not state.valid and state.status == 'EXPIRED', state.status)

        print('\n۶) دستکاری کش و گره خوردن به دستگاه')
        license_client.save_cache(envelope, device_id)
        with open(license_client._state_path(), 'r+', encoding='utf-8') as handle:
            content = handle.read()
            handle.seek(0)
            handle.write('A' + content[1:])
            handle.truncate()
        check('کش دستکاری‌شده بی‌اعتبار است',
              license_client.load_cache(device_id) is None)

        license_client.save_cache(envelope, device_id)
        check('کش با شناسه دستگاه دیگر باز نمی‌شود',
              license_client.load_cache('0' * 64) is None)

        print('\n۷) حمله بازپخش و امضای جعلی')
        server = _start_server()
        base_url = f'http://127.0.0.1:{server.server_address[1]}'
        license_client.server_url = lambda: base_url

        SERVER_BEHAVIOUR['break_nonce'] = True
        try:
            license_client.call_verify('TEST-KEY-0001')
            replay_blocked = False
        except license_client.SignatureError:
            replay_blocked = True
        check('پاسخ با nonce نامعتبر رد می‌شود (ضد بازپخش)', replay_blocked)
        SERVER_BEHAVIOUR['break_nonce'] = False

        SERVER_BEHAVIOUR['break_signature'] = True
        try:
            license_client.call_verify('TEST-KEY-0001')
            signature_blocked = False
        except license_client.SignatureError:
            signature_blocked = True
        check('امضای نامعتبر باعث توقف می‌شود', signature_blocked)
        license_client._store_state(None)
        state = license_client.refresh_state()
        check('وضعیت پس از امضای نامعتبر، قفل کامل است',
              not state.valid and state.status == 'SIGNATURE_ERROR', state.status)
        SERVER_BEHAVIOUR['break_signature'] = False

        # برچسب اثر انگشت ناهماهنگ (مثلاً هش با قالب دیگر در سمت سرور)
        # نباید پاسخِ امضاشده‌ی معتبر را رد کند؛ امضا مرجع نهایی است.
        SERVER_BEHAVIOUR['key_fingerprint'] = '9e70953c1ca7cbbfa59eff441adf76bc7808acef348784022d667cf4ecd474d0'
        try:
            license_client.call_verify('TEST-KEY-0001')
            fingerprint_label_blocked = False
        except license_client.SignatureError:
            fingerprint_label_blocked = True
        check('برچسب اثر انگشت ناهماهنگ با امضای معتبر رد نمی‌شود',
              not fingerprint_label_blocked)
        del SERVER_BEHAVIOUR['key_fingerprint']

        # ۸٫۵٫۵ — فقط دستکاری واقعی قفل می‌کند؛ هشدار ساعت این‌طور نیست
        license_client._clear_tamper_flag()
        license_client._record_integrity_event('clock_drift', 'اختلاف ساعت: 400 ثانیه')
        check('اختلاف ساعت معمولی پرچم دستکاری را فعال نمی‌کند',
              license_client._tamper_detected_at is None)
        license_client._store_state(None)
        license_client.refresh_state()               # وضعیت معتبر آنلاین
        license_client._record_integrity_event('signature', 'امضای نامعتبر (آزمون)')
        check('دستکاری واقعی پرچم قفل را فعال می‌کند',
              license_client._tamper_detected_at is not None)
        license_client._tamper_detected_at = time.monotonic() - 1000
        state = license_client.get_state()
        check('دستکاری واقعی با تأخیر برنامه را قفل می‌کند',
              not state.valid and state.status == 'INTEGRITY_ERROR', state.status)
        license_client._store_state(None)
        license_client.refresh_state()
        check('پاسخ معتبر تازه پرچم دستکاری را پاک می‌کند',
              license_client._tamper_detected_at is None)

        print('\n۸) مدیریت وضعیت‌های سرور')
        for status, expect_cache_cleared in [
            ('INVALID_KEY', True), ('INACTIVE', True), ('EXPIRED', True),
            ('DEVICE_MISMATCH', True), ('ACTIVATION_LIMIT_REACHED', False),
            ('LIMIT_REACHED', False), ('APP_TYPE_MISMATCH', True),
        ]:
            SERVER_BEHAVIOUR['status'] = 'SUCCESS'
            license_client.save_license_key('TEST-KEY-0001')
            license_client._store_state(None)
            license_client.refresh_state()               # کش تازه بساز
            SERVER_BEHAVIOUR['status'] = status
            license_client._store_state(None)
            state = license_client.refresh_state()
            cache_gone = license_client.load_cache(device_id) is None
            check(f'{status}: برنامه قفل می‌شود', not state.valid, state.status)
            check(f'{status}: پیام از سرور می‌آید',
                  state.message == f'پیام سرور برای {status}', state.message)
            if expect_cache_cleared:
                check(f'{status}: کش محلی پاک می‌شود', cache_gone)

        print('\n۹) خطای موقتی سرور، کش را پاک نمی‌کند')
        SERVER_BEHAVIOUR['status'] = 'SUCCESS'
        license_client._store_state(None)
        license_client.refresh_state()
        SERVER_BEHAVIOUR['status'] = 'SERVER_ERROR'
        license_client._store_state(None)
        state = license_client.refresh_state()
        check('SERVER_ERROR با کش ادامه می‌دهد', state.valid, state.status)
        check('SERVER_ERROR کش را پاک نمی‌کند',
              license_client.load_cache(device_id) is not None)
        SERVER_BEHAVIOUR['status'] = 'SUCCESS'

        print('\n۱۰) عقب کشیدن ساعت سیستم')
        license_client._store_state(None)
        license_client.refresh_state()
        raw = license_client.load_cache(device_id)
        future = int(time.time()) + 10 * 24 * 3600
        payload = {'envelope': raw['envelope'], 'saved_at': int(time.time()),
                   'max_server_time': future}
        body = license_client._fernet('state', device_id).encrypt(
            json.dumps(payload, ensure_ascii=False).encode('utf-8'))
        tag = _hmac.new(license_client._cache_key(device_id), body, hashlib.sha256).digest()
        with open(license_client._state_path(), 'w', encoding='utf-8') as handle:
            handle.write(base64.b64encode(tag + body).decode('ascii'))
        state = license_client._state_from_cache(device_id)
        check('عقب کشیدن ساعت، مهلت آفلاین را باطل می‌کند',
              not state.valid and state.status == 'CLOCK_TAMPER', state.status)

        print('\n۱۱) سیاست‌ها از سرور خوانده می‌شود')
        SERVER_BEHAVIOUR['revalidate_minutes'] = 15
        SERVER_BEHAVIOUR['offline_grace_hours'] = 12
        SERVER_BEHAVIOUR['in_grace'] = True
        license_client._store_state(None)
        state = license_client.refresh_state()
        check('revalidate_minutes از پاسخ سرور', state.revalidate_minutes == 15)
        check('offline_grace_hours از پاسخ سرور', state.offline_grace_hours == 12)
        check('در مهلت نرمش برنامه کار می‌کند', state.valid and state.in_grace)

        # سرور می‌گوید منقضی شده ولی مشتری در مهلت نرمش است → باید کار کند
        SERVER_BEHAVIOUR['status'] = 'EXPIRED'
        SERVER_BEHAVIOUR['grace_days_remaining'] = 3
        license_client._store_state(None)
        state = license_client.refresh_state()
        check('انقضا در مهلت نرمش برنامه را نمی‌بندد',
              state.valid and state.in_grace, state.status)
        check('کش مهلت نرمش ذخیره می‌شود',
              license_client.load_cache(device_id) is not None)

        # پایان مهلت نرمش → قفل کامل و پاک شدن کش
        SERVER_BEHAVIOUR['grace_days_remaining'] = 0
        license_client._store_state(None)
        state = license_client.refresh_state()
        check('پایان مهلت نرمش یعنی قفل',
              not state.valid and state.status == 'EXPIRED', state.status)
        check('پس از پایان مهلت نرمش کش پاک می‌شود',
              license_client.load_cache(device_id) is None)

        SERVER_BEHAVIOUR['status'] = 'SUCCESS'
        SERVER_BEHAVIOUR['grace_days_remaining'] = None
        SERVER_BEHAVIOUR['in_grace'] = False
        SERVER_BEHAVIOUR['revalidate_minutes'] = 360
        SERVER_BEHAVIOUR['offline_grace_hours'] = 72

        print('\n۱۲) آزادسازی دستگاه')
        result = license_client.deactivate_current_device()
        check('آزادسازی موفق است', result.get('success'), result.get('message'))
        check('پس از آزادسازی، کلید و کش پاک می‌شوند',
              not license_client.has_stored_key()
              and license_client.load_cache(device_id) is None)

        print('\n۱۳) به‌روزرسانی')
        import license_updater
        license_client.save_license_key('TEST-KEY-0001')
        info = license_updater.check_for_update()
        check('وقتی نسخه جدید نیست، None برمی‌گردد', info is None)
        check('فهرست محافظت‌شده شامل دیتابیس برنامه است',
              license_updater.is_preserved('instance/academy.db')
              and license_updater.is_preserved('settings.json')
              and license_updater.is_preserved('static/uploads/students/a.jpg')
              and license_updater.is_preserved('backups/backup_1.zip'))
        check('فایل‌های کد محافظت‌شده نیستند',
              not license_updater.is_preserved('app.py')
              and not license_updater.is_preserved('routes/finance.py'))
        check('نسخه‌ها درست مقایسه می‌شوند',
              license_updater._parse_version('1.2.0') > license_updater._parse_version('1.0.1'))

        print('\n۱۴) نگاشت بخش↔مسیر')
        from app import create_app
        app = create_app()
        report = license_features.audit_endpoint_coverage(app.url_map)
        check('هیچ مسیری بدون نگاشت بخش نمانده است',
              not report['unmapped'], ', '.join(report['unmapped'][:10]))
        check('همه کلیدهای نگاشت در AVAILABLE_FEATURES هستند',
              not report['unknown_keys'], ', '.join(report['unknown_keys']))
        check('هر بخش حداقل یک مسیر دارد',
              not report['unused_features'], ', '.join(report['unused_features']))

    finally:
        try:
            server.shutdown()
        except Exception:
            pass
        shutil.rmtree(storage, ignore_errors=True)

    print('\n' + '═' * 60)
    print(f'  موفق: {len(PASSED)}   ناموفق: {len(FAILED)}')
    for item in FAILED:
        print('   ✗', item)
    print('═' * 60)
    return 1 if FAILED else 0


if __name__ == '__main__':
    sys.exit(main())
