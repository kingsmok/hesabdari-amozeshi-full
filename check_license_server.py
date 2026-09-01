"""
ابزار خط فرمان: بررسی ارتباط با سرور لایسنس واقعی
────────────────────────────────────────────────────────────────
این اسکریپت روی همان ویندوزی اجرا می‌شود که نرم‌افزار نصب است و
به‌صورت مستقل (بدون بالا آوردن برنامه) بررسی می‌کند که:

  ۱) سرور در دسترس است و TLS برقرار می‌شود
  ۲) کلید عمومی سرور با کلید هاردکدشده در برنامه یکی است
  ۳) پاسخ verify امضای معتبر دارد و nonce را برمی‌گرداند
  ۴) نام فیلدهای پاسخ با آنچه برنامه انتظار دارد هم‌خوان است

اجرا:
    python check_license_server.py                 (فقط سلامت سرور)
    python check_license_server.py XXXX-XXXX-XXXX  (بررسی یک کلید واقعی)
    python check_license_server.py --raw KEY       (چاپ پاکت خام سرور)
    python check_license_server.py --server https://ls.ariapadideh.ir KEY

خروجی برای ارسال به پشتیبانی مناسب است؛ کلید لایسنس در خروجی
پوشانده می‌شود.
"""
import argparse
import base64
import hashlib
import json
import sys

try:
    import requests
except ImportError:                                     # pragma: no cover
    print('کتابخانه requests نصب نیست: pip install requests')
    sys.exit(2)

import license_client
from license_client import (
    APP_TYPE,
    KEY_FINGERPRINT,
    PRODUCT_SLUG,
    canonical_json,
    current_version,
    get_device_identifier,
    get_device_label,
    normalize_license_key,
    normalize_server_data,
    verify_signature,
)

OK = '[ OK ]'
BAD = '[ !! ]'
INFO = '[ .. ]'


def mask(key):
    key = str(key or '')
    return key[:4] + '…' + key[-4:] if len(key) > 10 else '****'


def fingerprint_of(pem_text):
    """
    اثر انگشت = sha256 بایت‌های DER (SubjectPublicKeyInfo) کلید عمومی.

    این همان قراردادی است که سرور در فیلد key_fingerprint گزارش می‌دهد و
    با ثابت KEY_FINGERPRINT برنامه یکی است. (هشِ رشته‌ی base64 نتیجه‌ی
    متفاوتی می‌دهد و در گذشته باعث گزارش اشتباه «کلیدها یکی نیستند» می‌شد.)
    """
    body = ''.join(
        line.strip() for line in pem_text.splitlines()
        if line.strip() and not line.strip().startswith('-----')
    )
    der = base64.b64decode(body)
    return hashlib.sha256(der).hexdigest()


def check_public_key(server):
    print(f'{INFO} دریافت کلید عمومی از {server}/api/v1/public-key')
    try:
        response = requests.get(f'{server}/api/v1/public-key', timeout=15)
    except requests.RequestException as exc:
        print(f'{BAD} ارتباط برقرار نشد: {type(exc).__name__}: {exc}')
        return False
    print(f'{INFO} HTTP {response.status_code}')
    try:
        payload = response.json()
    except ValueError:
        print(f'{BAD} پاسخ JSON نبود:\n{response.text[:400]}')
        return False

    pem = payload.get('public_key') or payload.get('data', {}).get('public_key') or ''
    server_fingerprint = (payload.get('key_fingerprint')
                          or payload.get('fingerprint')
                          or payload.get('data', {}).get('key_fingerprint') or '')
    if pem:
        computed = fingerprint_of(pem)
        print(f'{INFO} اثر انگشت محاسبه‌شده: {computed}')
        if not server_fingerprint:
            server_fingerprint = computed
    print(f'{INFO} اثر انگشت اعلامی سرور : {server_fingerprint or "—"}')
    print(f'{INFO} اثر انگشت داخل برنامه : {KEY_FINGERPRINT}')

    if server_fingerprint and server_fingerprint.lower() == KEY_FINGERPRINT.lower():
        print(f'{OK} کلید عمومی سرور با کلید هاردکدشده یکی است.')
        return True
    print(f'{BAD} کلید عمومی سرور با کلید داخل برنامه یکی نیست — '
          'یا بیلد قدیمی است یا آدرس سرور اشتباه است.')
    if pem:
        print('\n--- کلید عمومی سرور ---')
        print(pem.strip())
        print('-----------------------\n')
    return False


def call(server, path, payload, raw=False):
    body = dict(payload)
    body['nonce'] = license_client.secrets.token_hex(16)
    url = f'{server}{path}'
    print(f'{INFO} POST {url}')
    try:
        response = requests.post(url, json=body,
                                 headers={'Content-Type': 'application/json',
                                          'User-Agent': f'{PRODUCT_SLUG}/{current_version()}'},
                                 timeout=15)
    except requests.RequestException as exc:
        print(f'{BAD} ارتباط برقرار نشد: {type(exc).__name__}: {exc}')
        return None
    print(f'{INFO} HTTP {response.status_code}')
    try:
        envelope = response.json()
    except ValueError:
        print(f'{BAD} پاسخ JSON نبود:\n{response.text[:600]}')
        return None

    if raw:
        print('\n--- پاکت خام سرور ---')
        print(json.dumps(envelope, ensure_ascii=False, indent=2))
        print('---------------------\n')

    if not isinstance(envelope, dict) or not isinstance(envelope.get('data'), dict):
        print(f'{BAD} ساختار پاکت درست نیست؛ باید {{data, signature, ...}} باشد.')
        return None

    print(f"{INFO} الگوریتم امضا: {envelope.get('signature_algorithm') or '—'}")
    print(f"{INFO} اثر انگشت کلید در پاکت: {envelope.get('key_fingerprint') or '—'}")
    print(f'{INFO} JSON کانونیکال (۱۲۰ کاراکتر اول):')
    print('      ' + canonical_json(envelope['data'])[:120])

    if verify_signature(envelope):
        print(f'{OK} امضای پاسخ معتبر است.')
    else:
        print(f'{BAD} امضای پاسخ معتبر نیست — برنامه چنین پاسخی را نمی‌پذیرد.')
        return envelope

    if envelope['data'].get('nonce') != body['nonce']:
        print(f'{BAD} nonce برنگشته یا متفاوت است — برنامه پاسخ را رد می‌کند.')
    else:
        print(f'{OK} nonce درست بازگردانده شد.')
    return envelope


def report_fields(envelope):
    data = envelope.get('data') or {}
    normalized = normalize_server_data(data)
    print('\n--- فیلدهای پاسخ ---')
    print(f"  status خام            : {data.get('status')}")
    print(f"  status پس از ترجمه    : {normalized.get('status')}")
    print(f"  success               : {normalized.get('success')}")
    print(f"  client_name           : {normalized.get('client_name') or '—'}")
    print(f"  expires_at            : {normalized.get('expires_at') or '—'}")
    print(f"  max_activations       : {normalized.get('max_activations')}")
    print(f"  current_activations   : {normalized.get('current_activations')}")
    print(f"  revalidate_minutes    : {normalized.get('revalidate_minutes')}")
    print(f"  offline_grace_hours   : {normalized.get('offline_grace_hours')}")
    features = normalized.get('allowed_features') or {}
    enabled = sorted(key for key, value in features.items() if value)
    print(f'  allowed_features      : {len(features)} کلید، {len(enabled)} فعال')
    if enabled:
        print('      ' + '، '.join(enabled))
    if not features:
        print(f'{BAD} هیچ بخشی در پاسخ فعال نیست — همه‌ی منوها قفل خواهند بود.')
    print(f"  message               : {normalized.get('message') or '—'}")
    print('--------------------\n')


def main():
    parser = argparse.ArgumentParser(description='بررسی ارتباط با سرور لایسنس')
    parser.add_argument('license_key', nargs='?', help='کلید لایسنس واقعی برای آزمون verify')
    parser.add_argument('--server', default=None, help='آدرس سرور (پیش‌فرض: تنظیمات برنامه)')
    parser.add_argument('--raw', action='store_true', help='چاپ پاکت خام پاسخ')
    parser.add_argument('--activate', action='store_true',
                        help='در صورت NOT_ACTIVATED، فعال‌سازی واقعی هم انجام شود')
    args = parser.parse_args()

    server = (args.server or license_client.server_url()).rstrip('/')
    print('═' * 62)
    print(f'  محصول      : {PRODUCT_SLUG} / {APP_TYPE} / نسخه {current_version()}')
    print(f'  سرور       : {server}')
    print(f'  شناسه دستگاه: {get_device_identifier()}')
    print(f'  نام دستگاه  : {get_device_label()}')
    print('═' * 62)

    key_ok = check_public_key(server)
    print()

    if not args.license_key:
        print(f'{INFO} کلیدی داده نشد؛ فقط سلامت سرور بررسی شد.')
        return 0 if key_ok else 1

    key = normalize_license_key(args.license_key)
    print(f'{INFO} بررسی کلید {mask(key)}')
    payload = {
        'license_key': key,
        'device_identifier': get_device_identifier(),
        'product': PRODUCT_SLUG,
        'app_type': APP_TYPE,
        'current_version': current_version(),
    }
    envelope = call(server, '/api/v1/verify', payload, raw=args.raw)
    if not envelope:
        return 1
    report_fields(envelope)

    status = normalize_server_data(envelope['data']).get('status')
    if status == 'NOT_ACTIVATED' and args.activate:
        from license_features import AVAILABLE_FEATURES
        print(f'{INFO} انجام فعال‌سازی واقعی روی همین دستگاه…')
        payload['device_label'] = get_device_label()
        payload['available_features'] = AVAILABLE_FEATURES
        envelope = call(server, '/api/v1/activate', payload, raw=args.raw)
        if envelope:
            report_fields(envelope)
    elif status == 'NOT_ACTIVATED':
        print(f'{INFO} این کلید روی این دستگاه فعال نشده است؛ '
              'برای فعال‌سازی واقعی گزینه --activate را اضافه کنید.')

    return 0


if __name__ == '__main__':
    sys.exit(main())
