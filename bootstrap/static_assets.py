"""سرو فایل‌های استاتیک — فشرده‌سازی و کش ماندگار.

چرا این ماژول لازم بود:
  پیش‌فرض Flask فایل‌های استاتیک را با `direct_passthrough` می‌فرستد، بنابراین
  middleware فشرده‌سازی آن‌ها را رد می‌کرد. نتیجه روی هاست: صفحهٔ اصلی
  ۶۵۴ کیلوبایت CSS/JS **بدون هیچ فشرده‌سازی** دانلود می‌کرد، در حالی که
  همان فایل‌ها با gzip فقط ۲۱۸ کیلوبایت‌اند. `mod_deflate` آپاچی هم روی همهٔ
  هاست‌های اشتراکی روشن نیست و روی VPS (gunicorn/Nginx/Docker) اصلاً آپاچی
  در کار نیست.

  ضمناً `Cache-Control` پیش‌فرض یک روز بود؛ چون آدرس فایل‌ها با `asset()`
  نسخه‌دار می‌شود (`?v=<mtime>-<size>`) می‌توان یک سال و `immutable` کش کرد و
  بازدید دوم عملاً هیچ بایتی دانلود نکند.

فشرده‌سازی یک‌بار به‌ازای هر فایل انجام و در حافظه نگه داشته می‌شود
(نه به‌ازای هر درخواست)، پس هزینهٔ CPU تکراری ندارد.

نکتهٔ ETag: چون بدنهٔ پاسخ بسته به `Accept-Encoding` عوض می‌شود، ETag هم
باید رمزگذاری را بازتاب کند — وگرنه مرورگری که نسخهٔ خام را کش کرده با
`If-None-Match` پاسخ gzip را «تغییر نکرده» می‌گیرد (یا برعکس). به همین دلیل
ETag پیش از ساخت پاسخ محاسبه و به `send_file` داده می‌شود تا خودِ Flask
`304` و `Range` را درست مدیریت کند.

اگر بستهٔ اختیاری `brotli` نصب باشد، `br` بر `gzip` ترجیح داده می‌شود
(روی بستهٔ CSS این پروژه ۲۴٪ کوچک‌تر). چون نیست، gzip جای آن را می‌گیرد
و رفتار برنامه هیچ وابستگی‌ای به حضور آن بسته ندارد.
"""
from __future__ import annotations

import gzip
import os
import threading

from flask import abort, current_app, request, send_from_directory
from werkzeug.security import safe_join

#: Brotli اختیاری است: روی CSS/JS معمولاً ۱۵ تا ۲۰ درصد کوچک‌تر از gzip است،
#: اما بستهٔ `brotli` یک افزونهٔ C است و روی بعضی هاست‌های اشتراکی نصب
#: نمی‌شود. عمداً در requirements.txt نیست؛ اگر نبود، gzip جای آن را می‌گیرد.
try:                                    # pragma: no cover - بسته به محیط
    import brotli as _brotli
except ImportError:                     # pragma: no cover
    _brotli = None

#: کیفیت Brotli؛ ۱۱ بیشترین فشردگی است ولی کند، و چون نتیجه کش می‌شود
#: فقط یک‌بار پرداخت می‌شود.
_BROTLI_QUALITY = 11

#: یک سال — فقط برای فایل‌هایی که آدرسشان نسخه‌دار است
IMMUTABLE_MAX_AGE = 365 * 24 * 3600
#: فایل‌های آپلودی کاربر آدرس نسخه‌دار ندارند؛ کش کوتاه
UPLOAD_MAX_AGE = 3600

#: پسوندهایی که فشرده‌سازی‌شان می‌ارزد (woff2/png و … از قبل فشرده‌اند)
_COMPRESSIBLE_EXT = frozenset({
    '.css', '.js', '.mjs', '.json', '.svg', '.txt', '.map',
    '.webmanifest', '.html', '.xml', '.ico',
})
_MIN_COMPRESS = 1024                 # زیر این، هدر gzip از سودش بیشتر است
_MAX_COMPRESS = 6 * 1024 * 1024
_GZIP_LEVEL = 6

_CACHE: dict = {}                    # (path, mtime_ns, size) -> bytes
_CACHE_LOCK = threading.Lock()
_CACHE_MAX_ENTRIES = 64


def install(app) -> None:
    """جایگزینی view پیش‌فرض `/static/...` با نسخهٔ فشرده‌ساز.

    قانون URL و endpoint دست‌نخورده می‌ماند، پس `url_for('static', ...)`
    و همهٔ قالب‌ها بدون تغییر کار می‌کنند.
    """
    if not app.static_folder:
        return
    app.view_functions['static'] = _static_view


def _static_view(filename: str):
    root = current_app.static_folder
    path = safe_join(root, filename) if root else None
    if not path or not os.path.isfile(path):
        abort(404)

    try:
        stat = os.stat(path)
    except OSError:
        abort(404)

    encoding = _negotiate_encoding()
    compress_ok = encoding is not None and _worth_compressing(filename, stat.st_size)
    # ETag باید رمزگذاری را بازتاب کند (توضیح در docstring ماژول)
    suffix = _ETAG_SUFFIX[encoding] if compress_ok else 'raw'
    etag = f'{int(stat.st_mtime)}-{stat.st_size}-{suffix}'

    response = send_from_directory(root, filename, conditional=True, etag=etag)
    _apply_cache_policy(response, filename)
    if compress_ok:
        _compress(response, path, stat, encoding)
    return response


def _apply_cache_policy(response, filename: str) -> None:
    """فایل‌های نسخه‌دار یک سال کش می‌شوند؛ آپلودها یک ساعت."""
    response.cache_control.public = True
    if filename.replace('\\', '/').startswith('uploads/'):
        response.cache_control.max_age = UPLOAD_MAX_AGE
        return
    response.cache_control.max_age = IMMUTABLE_MAX_AGE
    response.cache_control.immutable = True


_ETAG_SUFFIX = {'br': 'br', 'gzip': 'gz'}


def _accepted_encodings() -> set:
    header = (request.headers.get('Accept-Encoding') or '').lower()
    return {part.split(';')[0].strip() for part in header.split(',')}


def _negotiate_encoding() -> str | None:
    """بالاترین رمزگذاری مشترک بین مرورگر و سرور.

    اگر `brotli` نصب نباشد، `br` هرگز پیشنهاد نمی‌شود تا مرورگر پاسخی
    نگیرد که نتواند باز کند.
    """
    accepted = _accepted_encodings()
    if _brotli is not None and 'br' in accepted:
        return 'br'
    if 'gzip' in accepted:
        return 'gzip'
    return None


def _worth_compressing(filename: str, size: int) -> bool:
    if os.path.splitext(filename)[1].lower() not in _COMPRESSIBLE_EXT:
        return False
    return _MIN_COMPRESS <= size <= _MAX_COMPRESS


def _compress(response, path: str, stat, encoding: str) -> None:
    if response.status_code != 200:      # ۳۰۴/۲۰۶ بدنهٔ قابل فشرده‌سازی ندارند
        return
    if response.headers.get('Content-Encoding'):
        return
    compressed = _compressed_bytes(path, stat.st_mtime_ns, stat.st_size, encoding)
    if compressed is None or len(compressed) >= stat.st_size - 64:
        return                            # سودی نداشت؛ خام بفرست

    response.direct_passthrough = False
    response.set_data(compressed)
    response.headers['Content-Encoding'] = encoding
    response.headers['Content-Length'] = str(len(compressed))
    vary = response.headers.get('Vary', '')
    if 'Accept-Encoding' not in vary:
        response.headers['Vary'] = (vary + ', Accept-Encoding').lstrip(', ')


def _compressed_bytes(path: str, mtime_ns: int, size: int,
                      encoding: str = 'gzip') -> bytes | None:
    """نسخهٔ فشردهٔ فایل، یک‌بار محاسبه و سپس از حافظه."""
    key = (path, mtime_ns, size, encoding)
    with _CACHE_LOCK:
        cached = _CACHE.get(key)
    if cached is not None:
        return cached

    try:
        with open(path, 'rb') as handle:
            raw = handle.read()
    except OSError:
        return None
    if encoding == 'br' and _brotli is not None:
        compressed = _brotli.compress(raw, quality=_BROTLI_QUALITY)
    else:
        compressed = gzip.compress(raw, compresslevel=_GZIP_LEVEL)

    with _CACHE_LOCK:
        if len(_CACHE) >= _CACHE_MAX_ENTRIES:
            _CACHE.clear()                 # ساده و کافی: چند مگ بیشتر نیست
        _CACHE[key] = compressed
    return compressed


def prime(paths) -> int:
    """فشرده‌سازی پیش‌دستانه در زمان بالا آمدن برنامه.

    Brotli با کیفیت ۱۱ روی بستهٔ CSS نزدیک به نیم ثانیه CPU می‌برد. اگر در
    زمان درخواست انجام شود، اولین بازدیدکنندهٔ پس از هر بار اجرا آن را
    می‌پردازد و صفحه‌اش نیم ثانیه دیرتر می‌آید. چون نتیجه در حافظه کش می‌شود،
    همین یک‌بار در زمان بوت کافی است.
    """
    count = 0
    encodings = ('gzip', 'br') if _brotli is not None else ('gzip',)
    for path in paths or ():
        if not isinstance(path, str) or not path:
            continue                      # بسته‌سازی خاموش بود؛ چیزی نیست
        try:
            stat = os.stat(path)
        except OSError:
            continue
        if not _worth_compressing(os.path.basename(path), stat.st_size):
            continue
        for encoding in encodings:
            if _compressed_bytes(path, stat.st_mtime_ns, stat.st_size, encoding):
                count += 1
    return count


def cache_stats() -> dict:
    """برای تست/عارضه‌یابی: چند فایل فشرده در حافظه است."""
    with _CACHE_LOCK:
        return {'entries': len(_CACHE),
                'bytes': sum(len(value) for value in _CACHE.values())}
