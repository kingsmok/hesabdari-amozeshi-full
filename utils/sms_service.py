"""اتصال واقعی و یکپارچه پنل پیامکی فراز (IranPayamak Public API)."""
from __future__ import annotations

import re
from typing import Mapping

import requests

BASE_URL = 'https://api.iranpayamak.com/ws/v1'


def normalize_iran_mobile(value: str) -> str | None:
    """شماره موبایل را به فرمت 09xxxxxxxxx مورد قبول پنل تبدیل می‌کند."""
    value = str(value or '').translate(str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789'))
    digits = re.sub(r'\D', '', value)
    if digits.startswith('0098'):
        digits = '0' + digits[4:]
    elif digits.startswith('98') and len(digits) == 12:
        digits = '0' + digits[2:]
    elif len(digits) == 10 and digits.startswith('9'):
        digits = '0' + digits
    return digits if re.fullmatch(r'09\d{9}', digits) else None


def _headers(api_key: str) -> dict:
    return {
        'Accept': 'application/json',
        'Api-Key': api_key,
        'Content-Type': 'application/json',
    }


def _result(response: requests.Response) -> dict:
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    success = response.status_code in (200, 201) and payload.get('status') == 'success'
    messages = payload.get('messages') or payload.get('message')
    if isinstance(messages, list):
        messages = '، '.join(str(item) for item in messages)
    error = None if success else (messages or f'خطای HTTP {response.status_code}')
    return {
        'ok': success,
        'status_code': response.status_code,
        'provider_id': payload.get('data'),
        'error': error,
        'raw': payload,
    }


def check_farazsms_connection(api_key: str) -> dict:
    """اعتبار کلید را بدون ارسال پیامک و کسر اعتبار بررسی می‌کند."""
    api_key = (api_key or '').strip()
    if not api_key:
        return {'ok': False, 'error': 'کلید API وارد نشده است'}
    try:
        response = requests.get(
            f'{BASE_URL}/account/balance', headers=_headers(api_key), timeout=15
        )
        result = _result(response)
        if result['ok']:
            data = result['raw'].get('data') or {}
            result['balance_amount'] = data.get('balanceAmount')
            result['balance_count'] = data.get('balanceCount')
        return result
    except requests.RequestException as exc:
        return {'ok': False, 'error': f'خطا در ارتباط با پنل: {exc}'}


def send_farazsms(
    settings,
    phone: str,
    message: str,
    *,
    pattern_code: str | None = None,
    pattern_values: Mapping[str, object] | None = None,
) -> dict:
    """ارسال ساده یا پترن با API رسمی فعلی پنل فراز."""
    if not settings or not settings.farazsms_api_key:
        return {'ok': False, 'error': 'پنل پیامکی تنظیم نشده است'}
    if not settings.farazsms_sender:
        return {'ok': False, 'error': 'شماره فرستنده تنظیم نشده است'}

    mobile = normalize_iran_mobile(phone)
    if not mobile:
        return {'ok': False, 'error': 'شماره موبایل معتبر نیست'}

    code = (pattern_code or '').strip()
    try:
        if code:
            endpoint = f'{BASE_URL}/sms/pattern'
            payload = {
                'code': code,
                'attributes': {key: str(value) for key, value in (pattern_values or {}).items()},
                'recipient': mobile,
                'line_number': settings.farazsms_sender,
                'number_format': 'english',
            }
        else:
            if not (message or '').strip():
                return {'ok': False, 'error': 'متن پیامک خالی است'}
            endpoint = f'{BASE_URL}/sms/simple'
            payload = {
                'text': message.strip(),
                'line_number': settings.farazsms_sender,
                'recipients': [mobile],
                'number_format': 'english',
            }

        response = requests.post(
            endpoint,
            json=payload,
            headers=_headers(settings.farazsms_api_key),
            timeout=20,
        )
        return _result(response)
    except requests.RequestException as exc:
        return {'ok': False, 'error': f'خطا در ارسال پیامک: {exc}'}


def send_configured_sms(phone: str, message: str, **kwargs) -> dict:
    from models.system import SystemSettings

    return send_farazsms(SystemSettings.query.first(), phone, message, **kwargs)
