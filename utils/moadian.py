"""
کلاینت اتصال به سامانه مودیان سازمان امور مالیاتی

جریان استاندارد ارسال صورتحساب (API v2):
    1) GET  /nonce?timeToLive=30            → دریافت nonce
    2) ساخت JWS (RS256 + x5c + sigT) از {nonce, clientId} → توکن Bearer
    3) GET  /server-information             → دریافت کلید عمومی سرور
    4) امضای JSON صورتحساب به صورت JWS
    5) رمزنگاری JWS با JWE (RSA-OAEP-256 / A256GCM)
    6) POST /invoice  با بسته [{payload, header:{requestTraceId, fiscalId}}]
    7) GET  /inquiry-by-reference-id        → استعلام وضعیت

نکات پیاده‌سازی:
- در «حالت آزمایشی» (sandbox) هیچ درخواست شبکه‌ای ارسال نمی‌شود و پاسخ شبیه‌سازی
  می‌شود تا آموزشگاه بتواند قبل از دریافت گواهی امضا، کل جریان را تست کند.
- امضا و رمزنگاری به کتابخانه cryptography نیاز دارد؛ در نبود آن پیام فارسی روشن
  برگردانده می‌شود و برنامه از کار نمی‌افتد.
"""
from __future__ import annotations

import base64
import json
import os
import uuid
from datetime import datetime, timezone

import requests

DEFAULT_BASE_URL = 'https://tp.tax.gov.ir/requestsmanager/api/v2'
REQUEST_TIMEOUT = 25


class MoadianError(Exception):
    """خطای قابل نمایش به کاربر در تعامل با سامانه مودیان."""


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode('ascii')


def _json_bytes(payload) -> bytes:
    return json.dumps(payload, ensure_ascii=False, separators=(',', ':')).encode('utf-8')


def _load_crypto():
    try:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        from cryptography.x509 import load_pem_x509_certificate, load_der_x509_certificate
        return {
            'hashes': hashes,
            'serialization': serialization,
            'padding': padding,
            'AESGCM': AESGCM,
            'load_pem_x509_certificate': load_pem_x509_certificate,
            'load_der_x509_certificate': load_der_x509_certificate,
        }
    except ImportError as exc:  # pragma: no cover - وابسته به محیط نصب
        raise MoadianError(
            'برای امضای دیجیتال صورتحساب، بسته cryptography نصب نیست. '
            'دستور نصب: pip install cryptography'
        ) from exc


# ═══════════════════════════════════════════════════════════════
#  تبدیل صورتحساب داخلی به ساختار JSON سامانه مودیان
# ═══════════════════════════════════════════════════════════════
def _epoch_millis(value) -> int:
    if value is None:
        value = datetime.utcnow()
    if hasattr(value, 'timetuple') and not hasattr(value, 'hour'):
        value = datetime(value.year, value.month, value.day)
    return int(value.replace(tzinfo=timezone.utc).timestamp() * 1000)


def build_invoice_payload(invoice, settings) -> dict:
    """ساخت دیکشنری صورتحساب مطابق قالب header/body/payments سامانه مودیان."""
    party = invoice.party
    is_export = str(invoice.pattern) == '7'

    header = {
        'taxid': invoice.tax_number,
        'indatim': _epoch_millis(invoice.invoice_date),
        'indati2m': _epoch_millis(invoice.invoice_date),
        'inty': int(invoice.invoice_type or 1),
        'inno': invoice.invoice_number,
        'irtaxid': None,
        'inp': int(invoice.subject or 1),
        'ins': int(invoice.pattern or 1),
        'tins': settings.seller_tin,
        'tob': 2 if (settings.seller_type or 'legal') == 'legal' else 1,
        'bid': (party.national_id if party else None),
        'tinb': (party.national_id if party else None),
        'sbc': settings.branch_code or None,
        'bpc': (party.postal_code if party else None),
        'bbc': None,
        'ft': None,
        'bpn': None,
        'scln': settings.registration_number or None,
        'scc': settings.economic_code or None,
        'crn': (party.economic_code if party else None),
        'cdcn': None,
        'cdcd': None,
        'tprdis': round(invoice.total_before_discount or 0),
        'tdis': round(invoice.total_discount or 0),
        'tadis': round((invoice.total_taxable or 0) + (invoice.total_exempt or 0)),
        'tvam': round(invoice.total_vat or 0),
        'todam': round(invoice.other_taxes or 0),
        'tbill': round(invoice.total_amount or 0),
        'setm': None,
        'cap': None,
        'insp': None,
        'tvop': None,
        'tax17': None,
    }
    if is_export:
        # الگوی صادرات: اطلاعات خریدار داخلی الزامی نیست، ارز و نرخ برابری درج می‌شود
        header['bid'] = None
        header['tinb'] = None
        header['cfee'] = None
        header['crate'] = invoice.exchange_rate or 1
        header['cui'] = invoice.currency or 'USD'

    body = []
    for index, item in enumerate(invoice.items.order_by('row_number').all(), start=1):
        body.append({
            'sstid': item.stuff_id or settings.default_stuff_id,
            'sstt': item.title,
            'mu': item.unit,
            'am': item.quantity or 0,
            'fee': round(item.unit_price or 0),
            'cfee': None,
            'cut': None,
            'exr': invoice.exchange_rate if is_export else None,
            'ssrv': round(item.gross_amount or 0),
            'sscv': None,
            'prdis': round(item.gross_amount or 0),
            'dis': round(item.discount or 0),
            'adis': round(item.net_amount or 0),
            'vra': float(item.vat_rate or 0),
            'vam': round(item.vat_amount or 0),
            'odt': None,
            'odr': None,
            'odam': round(item.other_tax or 0),
            'olt': None,
            'olr': None,
            'olam': None,
            'consfee': None,
            'spro': None,
            'bros': None,
            'tcpbs': None,
            'cop': None,
            'vop': None,
            'bsrn': index,
            'tsstam': round(item.total_amount or 0),
        })

    return {'header': header, 'body': body, 'payments': []}


# ═══════════════════════════════════════════════════════════════
#  کلاینت
# ═══════════════════════════════════════════════════════════════
class MoadianClient:
    """کلاینت سبک سامانه مودیان با پشتیبانی از حالت آزمایشی."""

    def __init__(self, settings):
        self.settings = settings
        self.base_url = (settings.api_base_url or DEFAULT_BASE_URL).rstrip('/')
        self.client_id = (settings.client_id or settings.memory_id or '').strip()
        self.sandbox = bool(settings.sandbox_mode)

    # ── بررسی پیش‌نیازها ────────────────────────────────────────
    def check_configuration(self) -> list[str]:
        """فهرست ایرادهای پیکربندی را برمی‌گرداند (خالی = آماده ارسال)."""
        problems = []
        if not self.settings.memory_id:
            problems.append('شناسه یکتای حافظه مالیاتی تنظیم نشده است')
        if not self.settings.seller_tin:
            problems.append('شناسه ملی/کد ملی فروشنده تنظیم نشده است')
        if not self.client_id:
            problems.append('Client ID (شناسه مودی) تنظیم نشده است')
        if not self.sandbox:
            for path, label in (
                (self.settings.private_key_path, 'فایل کلید خصوصی'),
                (self.settings.certificate_path, 'فایل گواهی امضا'),
            ):
                if not path:
                    problems.append(f'{label} انتخاب نشده است')
                elif not os.path.isfile(path):
                    problems.append(f'{label} در مسیر «{path}» یافت نشد')
        return problems

    # ── امضا و رمزنگاری ────────────────────────────────────────
    def _private_key(self):
        crypto = _load_crypto()
        with open(self.settings.private_key_path, 'rb') as handle:
            return crypto['serialization'].load_pem_private_key(handle.read(), password=None)

    def _certificate_b64(self) -> str:
        with open(self.settings.certificate_path, 'rb') as handle:
            raw = handle.read()
        if b'-----BEGIN' in raw:
            body = b''.join(
                line.strip() for line in raw.splitlines()
                if line.strip() and not line.strip().startswith(b'-----')
            )
            return body.decode('ascii')
        return base64.b64encode(raw).decode('ascii')

    def create_jws(self, payload: dict) -> str:
        """امضای JWS با RS256 و هدر x5c/sigT طبق سند سازمان."""
        crypto = _load_crypto()
        header = {
            'alg': 'RS256',
            'x5c': [self._certificate_b64()],
            'sigT': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
            'typ': 'jose',
            'crit': ['sigT'],
            'cty': 'text/plain',
        }
        protected = _b64url(_json_bytes(header))
        body = _b64url(_json_bytes(payload))
        signing_input = f'{protected}.{body}'.encode('ascii')
        signature = self._private_key().sign(
            signing_input,
            crypto['padding'].PKCS1v15(),
            crypto['hashes'].SHA256(),
        )
        return f'{protected}.{body}.{_b64url(signature)}'

    def create_jwe(self, plaintext: str, server_key_b64: str, kid: str) -> str:
        """رمزنگاری JWE با RSA-OAEP-256 و A256GCM."""
        crypto = _load_crypto()
        public_key = crypto['serialization'].load_der_public_key(
            base64.b64decode(server_key_b64)
        )
        header = {'alg': 'RSA-OAEP-256', 'enc': 'A256GCM', 'kid': kid}
        protected = _b64url(_json_bytes(header))

        cek = os.urandom(32)
        encrypted_key = public_key.encrypt(
            cek,
            crypto['padding'].OAEP(
                mgf=crypto['padding'].MGF1(algorithm=crypto['hashes'].SHA256()),
                algorithm=crypto['hashes'].SHA256(),
                label=None,
            ),
        )
        iv = os.urandom(12)
        sealed = crypto['AESGCM'](cek).encrypt(
            iv, plaintext.encode('utf-8'), protected.encode('ascii')
        )
        ciphertext, tag = sealed[:-16], sealed[-16:]
        return '.'.join([
            protected, _b64url(encrypted_key), _b64url(iv),
            _b64url(ciphertext), _b64url(tag),
        ])

    # ── فراخوانی‌های HTTP ──────────────────────────────────────
    def get_nonce(self, ttl: int = 30) -> str:
        response = requests.get(
            f'{self.base_url}/nonce', params={'timeToLive': ttl}, timeout=REQUEST_TIMEOUT
        )
        response.raise_for_status()
        data = response.json()
        nonce = data.get('nonce')
        if not nonce:
            raise MoadianError('پاسخ nonce سامانه معتبر نیست')
        return nonce

    def get_token(self) -> str:
        nonce = self.get_nonce()
        return self.create_jws({'nonce': nonce, 'clientId': self.client_id})

    def get_server_information(self, token: str) -> dict:
        response = requests.get(
            f'{self.base_url}/server-information',
            headers={'Authorization': f'Bearer {token}', 'accept': '*/*'},
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        return response.json()

    def test_connection(self) -> dict:
        """تست اتصال؛ در حالت آزمایشی فقط پیکربندی بررسی می‌شود."""
        problems = self.check_configuration()
        if problems:
            return {'success': False, 'message': ' | '.join(problems)}
        if self.sandbox:
            return {
                'success': True,
                'message': 'حالت آزمایشی فعال است؛ پیکربندی کامل و آماده ارسال شبیه‌سازی‌شده است',
            }
        try:
            token = self.get_token()
            info = self.get_server_information(token)
            keys = info.get('publicKeys') or []
            return {
                'success': True,
                'message': f'اتصال برقرار شد — زمان سرور: {info.get("serverTime")} | تعداد کلید عمومی: {len(keys)}',
            }
        except MoadianError as exc:
            return {'success': False, 'message': str(exc)}
        except requests.RequestException as exc:
            return {'success': False, 'message': f'خطای ارتباط با سامانه: {exc}'}
        except Exception as exc:  # noqa: BLE001 - نمایش خطای ناشناخته به کاربر
            return {'success': False, 'message': f'خطای غیرمنتظره: {exc}'}

    def send_invoice(self, invoice) -> dict:
        """ارسال یک صورتحساب و بازگرداندن نتیجه استاندارد‌شده."""
        problems = self.check_configuration()
        if problems:
            return {'success': False, 'message': ' | '.join(problems), 'http_status': None}

        payload = build_invoice_payload(invoice, self.settings)
        trace_id = uuid.uuid4().hex[:32]

        if self.sandbox:
            return {
                'success': True,
                'message': 'ارسال شبیه‌سازی‌شده در حالت آزمایشی انجام شد (بدون تماس با سرور سازمان)',
                'http_status': 200,
                'uid': invoice.tax_number,
                'reference_number': f'SANDBOX-{trace_id[:12].upper()}',
                'trace_id': trace_id,
                'payload': payload,
                'sandbox': True,
            }

        try:
            token = self.get_token()
            info = self.get_server_information(token)
            keys = info.get('publicKeys') or []
            if not keys:
                raise MoadianError('کلید عمومی سرور دریافت نشد')
            server_key = keys[0]

            jws = self.create_jws(payload)
            jwe = self.create_jwe(jws, server_key.get('key'), server_key.get('id'))

            body = [{
                'payload': jwe,
                'header': {'requestTraceId': trace_id, 'fiscalId': self.client_id},
            }]
            response = requests.post(
                f'{self.base_url}/invoice',
                headers={
                    'Authorization': f'Bearer {token}',
                    'Content-Type': 'application/json',
                    'requestTraceId': trace_id,
                    'timestamp': str(int(datetime.now(timezone.utc).timestamp() * 1000)),
                },
                data=_json_bytes(body),
                timeout=REQUEST_TIMEOUT,
            )
            result = {}
            try:
                result = response.json()
            except ValueError:
                result = {'raw': response.text[:500]}

            first = result[0] if isinstance(result, list) and result else result
            success = response.status_code < 300 and not (
                isinstance(first, dict) and first.get('error')
            )
            return {
                'success': success,
                'message': json.dumps(first, ensure_ascii=False)[:900],
                'http_status': response.status_code,
                'uid': (first or {}).get('uid') if isinstance(first, dict) else None,
                'reference_number': (first or {}).get('referenceNumber') if isinstance(first, dict) else None,
                'trace_id': trace_id,
                'payload': payload,
            }
        except MoadianError as exc:
            return {'success': False, 'message': str(exc), 'http_status': None,
                    'trace_id': trace_id, 'payload': payload}
        except requests.RequestException as exc:
            return {'success': False, 'message': f'خطای ارتباط با سامانه: {exc}',
                    'http_status': None, 'trace_id': trace_id, 'payload': payload}
        except Exception as exc:  # noqa: BLE001
            return {'success': False, 'message': f'خطای غیرمنتظره: {exc}',
                    'http_status': None, 'trace_id': trace_id, 'payload': payload}

    def inquiry(self, reference_number: str) -> dict:
        """استعلام وضعیت صورتحساب بر اساس شماره مرجع."""
        if self.sandbox:
            return {'success': True, 'message': 'حالت آزمایشی: وضعیت شبیه‌سازی‌شده SUCCESS',
                    'status': 'SUCCESS'}
        try:
            token = self.get_token()
            response = requests.get(
                f'{self.base_url}/inquiry-by-reference-id',
                params={'referenceNumber': reference_number},
                headers={'Authorization': f'Bearer {token}'},
                timeout=REQUEST_TIMEOUT,
            )
            data = response.json() if response.content else {}
            first = data[0] if isinstance(data, list) and data else data
            status = (first or {}).get('data', {}).get('status') if isinstance(first, dict) else None
            return {
                'success': response.status_code < 300,
                'message': json.dumps(first, ensure_ascii=False)[:900],
                'status': status,
                'http_status': response.status_code,
            }
        except Exception as exc:  # noqa: BLE001
            return {'success': False, 'message': f'خطای استعلام: {exc}', 'status': None}
