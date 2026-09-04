"""پذیرش یکنواخت فایل اَپلودی (اِعمال سه کنترلی که پیش‌تر هر مسیر
به‌تنهایی و ناقص داشت)

سه نقطهٔ اَپلود در برنامه هست: فاکتور هزینهٔ حقوق، ورود بسته پشتیبان، و بستهٔ
به‌روزرسانی. هر سه باید این‌ها را داشته باشند:

۱) فقط پسوند مجاز؛
۲) اندازهٔ سقف‌دار، با توقفِ **حین خواندن** (نه بعد از ذخیرهٔ کل فایل روی دیسک؛
   `MAX_CONTENT_LENGTH` فقط ۵۰ مگ را اجازه می‌دهد و برای یک تصویر فاکتور زیاد است
   و برای بستهٔ آپدیت کم);
۳) نامِ بی‌خطر روی دیسک: فایل با uuid ذخیره می‌شود تا نامِ کاربر (که ممکن است
   `../../` یا `;.php` داشته باشد) هرگز در مسیر نهایی ظاهر نشود.

فایل‌ها روی دیسک با همان پسوندِ مجاز ذخیره می‌شوند؛ سرویس آن‌ها هم فقط از مسیر
`static/uploads/**` انجام می‌شود، پس نیازی به تغییر MIME در پاسخ نیست. برای
رد کردن فایل‌های «تقلبی» (مثلاً `.png` که واقعاً HTML است) امضای اولِ فایل
(SIGNATURES) هم بررسی می‌شود — این جلوی بسیاری از بارگذاری‌های مخرب با پسوند
دروغین را می‌گیرد.
"""
import os
import uuid

# سقف هر نوع، بر حسب بایت (فایل بزرگ‌تر از این، حین خواندن رد می‌شود)
MAX_SIZE = {
    'expense': 8 * 1024 * 1024,      # فاکتور هزینه (تصویر/PDF)
    'backup': 512 * 1024 * 1024,     # بسته پشتیبان ورودی
    'package': 400 * 1024 * 1024,    # بسته به‌روزرسانی
}

ALLOWED_EXT = {
    'expense': {'.pdf', '.jpg', '.jpeg', '.png', '.webp'},
    'backup': {'.zip'},
    'package': {'.zip'},
}

# امضای مجاز اول فایل؛ خالی یعنی بررسی امضا نمی‌شود
SIGNATURES = {
    '.pdf': (b'%PDF-',),
    '.jpg': (b'\xff\xd8\xff',),
    '.jpeg': (b'\xff\xd8\xff',),
    '.png': (b'\x89PNG\r\n\x1a\n',),
    '.webp': None,        # RIFF....WEBP — بررسی در _matches_signature
    '.gif': (b'GIF8',),
    '.zip': (b'PK\x03\x04', b'PK\x05\x06', b'PK\x07\x08'),
}

CHUNK = 64 * 1024


class UnsafeUpload(Exception):
    """اَپلود مردود (پیام آن برای کاربر نشان داده می‌شود)."""


def _matches_signature(ext: str, head: bytes) -> bool:
    expected = SIGNATURES.get(ext)
    if expected is None:
        if ext == '.webp':
            return head[:4] == b'RIFF' and head[8:12] == b'WEBP'
        return True
    return any(head.startswith(sig) for sig in expected)


def _safe_ext(filename: str, allowed: set) -> str:
    base = os.path.basename(filename or '')
    ext = os.path.splitext(base)[1].lower()
    if ext not in allowed:
        raise UnsafeUpload(f'پسوند فایل مجاز نیست ({ext or "بدون پسوند"}).')
    return ext


def store_upload(file_storage, folder: str, kind: str, prefix: str = '') -> str:
    """ذخیرهٔ امن یک فایل اَپلودی و برگرداندن **نام** فایل ساخته‌شده.

    مسیر نهایی `os.path.join(folder, name)` است و نام از uuid می‌آید، پس هرچه
    کاربر در `filename` فرستاده (شامل `../` یا `;` یا پسوند دوبل) هرگز در مسیر
    نمی‌نشیند؛ فقط پسوندِ سفیدلیست‌شده از آن الگو برداشته می‌شود.

    دو حالت پذیرش:
    - شیء دارای `.stream` (FileStorage واقعی): chunk‌به‌chunk خوانده و **حین
      نوشتن** از سقف حجم رد می‌شود؛
    - شیء فقط-`save()` (استاب‌ها/کدهای قدیمی): اول ذخیره، بعد بررسی اندازه و
      امضا؛ مردودها پاک می‌شوند.
    """
    if file_storage is None or not getattr(file_storage, 'filename', None):
        raise UnsafeUpload('فایل انتخاب نشده است.')
    ext = _safe_ext(file_storage.filename, ALLOWED_EXT[kind])
    limit = MAX_SIZE.get(kind, MAX_SIZE['expense'])
    os.makedirs(folder, exist_ok=True)
    name = f'{prefix}{uuid.uuid4().hex}{ext}'
    abs_path = os.path.join(folder, name)
    try:
        if hasattr(file_storage, 'stream'):
            _stream_to(file_storage, abs_path, ext, limit)
        else:
            _save_then_check(file_storage, abs_path, ext, limit)
    except UnsafeUpload:
        _silent_remove(abs_path)
        raise
    except Exception as exc:                      # noqa: BLE001
        _silent_remove(abs_path)
        raise UnsafeUpload(f'ذخیره فایل ناموفق بود: {exc}') from exc
    return name


def _stream_to(file_storage, abs_path: str, ext: str, limit: int) -> None:
    written = 0
    checked = False
    file_storage.stream.seek(0)
    with open(abs_path, 'wb') as out:
        while True:
            chunk = file_storage.stream.read(CHUNK)
            if not chunk:
                break
            if not checked:
                if not _matches_signature(ext, chunk):
                    raise UnsafeUpload('محتوای فایل با پسوندش هم‌خوانی ندارد.')
                checked = True
            written += len(chunk)
            if written > limit:
                raise UnsafeUpload(
                    f'حجم فایل از مجاز ({limit // (1024 * 1024)}MB) بیشتر است.')
            out.write(chunk)
    if not written:
        raise UnsafeUpload('فایل خالی است.')


def _save_then_check(file_storage, abs_path: str, ext: str, limit: int) -> None:
    file_storage.save(abs_path)
    size = os.path.getsize(abs_path)
    if not size:
        raise UnsafeUpload('فایل خالی است.')
    if size > limit:
        raise UnsafeUpload(
            f'حجم فایل از مجاز ({limit // (1024 * 1024)}MB) بیشتر است.')
    with open(abs_path, 'rb') as handle:
        head = handle.read(16)
    if not _matches_signature(ext, head):
        raise UnsafeUpload('محتوای فایل با پسوندش هم‌خوانی ندارد.')


def _silent_remove(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass
    try:
        os.remove(path)
    except OSError:
        pass
