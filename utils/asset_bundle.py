"""بسته‌بندی فایل‌های CSS/JS — کم‌کردن تعداد درخواست‌ها روی هاست.

صفحهٔ اصلی ۲۰ منبع استاتیک دارد که ۸ تای آن‌ها CSS و ۵ تای آن‌ها JS است.
روی HTTP/1.1 (که اکثر هاست‌های اشتراکی همان‌اند) هر منبع یک رفت‌وبرگشت کامل
هزینه دارد؛ با RTT صد میلی‌ثانیه‌ای، فقط همین رفت‌وبرگشت‌ها بیش از یک ثانیه
به بار نخست صفحه اضافه می‌کنند.

این ماژول در زمان بوت، فایل‌ها را در `static/gen/` به هم می‌چسباند:
  • انگشت‌اثر از (نام، mtime، اندازه) منابع ساخته می‌شود؛ با تغییر هر فایل
    منبع، بستهٔ تازه ساخته می‌شود ⇒ هرگز کهنه نمی‌ماند و نیاز به «بیلد دستی»
    نیست.
  • اگر پوشه قابل نوشتن نباشد (نصب PyInstaller، هاست فقط‌خواندنی) یا ساخت
    شکست بخورد، `None` برمی‌گرداند و قالب‌ها به همان فایل‌های جدا برمی‌گردند.
  • `ACADEMY_ASSET_BUNDLE=0` کلاً خاموشش می‌کند.

ترتیب الحاق دقیقاً همان ترتیب `<link>`/`<script>` در layout است تا
آبشار CSS و ترتیب اجرای JS عوض نشود.
"""
from __future__ import annotations

import hashlib
import os
import re

GEN_DIR = 'gen'

#: ترتیب دقیقاً مطابق templates/base/layout.html
CSS_HEAD_SOURCES = (
    'css/bootstrap.rtl.min.css',
    'css/bootstrap-icons.min.css',
    'css/animations.css',
    'css/jalali-picker.css',
    'css/searchable-select.css',
    'css/responsive.css',
)
#: print.css با media="print" بود؛ داخل بسته با @media print پیچیده می‌شود تا
#: هم جایگاهش در آبشار حفظ شود و هم فقط در چاپ اعمال شود.
CSS_PRINT_SOURCE = 'css/print.css'
CSS_TAIL_SOURCES = (
    'css/main.css',
    'css/theme-dark.css',
)
JS_SOURCES = (
    'js/bootstrap.bundle.min.js',
    'js/ui-core.js',
    'js/app.js',
    'js/jalali-picker.js',
    'js/searchable-select.js',
)

_SOURCEMAP_RE = re.compile(r'^//[#@]\s*sourceMappingURL=.*$', re.MULTILINE)


# ══════════════════════════════════════════════════════════════
#  API عمومی
# ══════════════════════════════════════════════════════════════

def ensure_bundles(app) -> dict:
    """ساخت بسته‌ها در زمان بوت؛ نتیجه در `app.extensions['asset_bundles']`."""
    bundles = {'css': None, 'js': None}
    app.extensions['asset_bundles'] = bundles

    if os.environ.get('ACADEMY_ASSET_BUNDLE', '1').strip().lower() in ('0', 'false', 'no', 'off'):
        return bundles
    if not app.static_folder:
        return bundles

    gen_dir = os.path.join(app.static_folder, GEN_DIR)
    try:
        os.makedirs(gen_dir, exist_ok=True)
        # تست نوشتن — روی هاست/PyInstaller ممکن است فقط‌خواندنی باشد
        probe = os.path.join(gen_dir, '.write-probe')
        with open(probe, 'w', encoding='utf-8') as handle:
            handle.write('ok')
        os.remove(probe)
    except OSError:
        app.logger.info('asset bundle: پوشهٔ %s قابل نوشتن نیست؛ فایل‌های جدا سرو می‌شوند',
                        GEN_DIR)
        return bundles

    static_root = app.static_folder
    try:
        bundles['css'] = _build(app, gen_dir, 'app.css', _css_parts(static_root))
        bundles['js'] = _build(app, gen_dir, 'app.js', _js_parts(static_root))
        _prune(gen_dir, {bundles['css'], bundles['js']})
    except OSError as exc:
        app.logger.warning('asset bundle: ساخت بسته ناموفق (%s)؛ فایل‌های جدا سرو می‌شوند', exc)
        bundles = {'css': None, 'js': None}
        app.extensions['asset_bundles'] = bundles
    return bundles


def bundle_url(kind: str) -> str | None:
    """مسیر بسته نسبت به static/ — یا None اگر ساخته نشده باشد."""
    from flask import current_app
    return (current_app.extensions.get('asset_bundles') or {}).get(kind)


# ══════════════════════════════════════════════════════════════
#  داخلی
# ══════════════════════════════════════════════════════════════

def _css_parts(static_root: str) -> list:
    """[(نام, متن)] با حفظ ترتیب آبشار layout."""
    parts = [(name, _read(static_root, name, wrap_print=False)) for name in CSS_HEAD_SOURCES]
    parts.append((CSS_PRINT_SOURCE, _read(static_root, CSS_PRINT_SOURCE, wrap_print=True)))
    parts.extend((name, _read(static_root, name, wrap_print=False)) for name in CSS_TAIL_SOURCES)
    return parts


def _js_parts(static_root: str) -> list:
    return [(name, _read(static_root, name, wrap_print=False)) for name in JS_SOURCES]


def _read(static_root: str, relative: str, wrap_print: bool) -> str:
    path = os.path.join(static_root, relative.replace('/', os.sep))
    with open(path, encoding='utf-8') as handle:
        text = handle.read()
    # نقشهٔ منبعِ هر قطعه پس از الحاق بی‌معناست و در DevTools خطای ۴۰۴ می‌دهد
    text = _SOURCEMAP_RE.sub('', text)
    if wrap_print:
        text = '@media print {\n' + text + '\n}'
    return text


def _fingerprint(parts: list) -> str:
    """اثر انگشت محتوا — نه mtime پوشه، نه نام هاست."""
    digest = hashlib.sha1()
    for name, text in parts:
        digest.update(name.encode('utf-8'))
        digest.update(text.encode('utf-8'))
    return digest.hexdigest()[:12]


def _build(app, gen_dir: str, basename: str, parts: list) -> str | None:
    missing = [name for name, text in parts if not text]
    if missing:
        app.logger.warning('asset bundle: منبع %s خالی/ناپدید بود؛ بستهٔ %s ساخته نشد',
                           missing, basename)
        return None

    stem, ext = os.path.splitext(basename)
    filename = f'{stem}.{_fingerprint(parts)}{ext}'
    target = os.path.join(gen_dir, filename)
    if not os.path.isfile(target):
        separator = '\n;\n' if ext == '.js' else '\n'
        body = separator.join(text.strip('\n') for _name, text in parts) + '\n'
        tmp = target + '.part'
        with open(tmp, 'w', encoding='utf-8') as handle:
            handle.write(body)
        os.replace(tmp, target)          # جایگزینی اتمی — نیمه‌نویس دیده نمی‌شود
        app.logger.info('asset bundle: %s ساخته شد (%d KB، %d منبع)',
                                filename, len(body) // 1024, len(parts))
    return f'{GEN_DIR}/{filename}'


def _prune(gen_dir: str, keep: set) -> None:
    """پاک‌کردن بسته‌های قدیمی تا پوشهٔ static بزرگ نشود."""
    for name in os.listdir(gen_dir):
        if not (name.startswith('app.') and name.endswith(('.css', '.js'))):
            continue
        if f'{GEN_DIR}/{name}' in keep:
            continue
        try:
            os.remove(os.path.join(gen_dir, name))
        except OSError:
            pass
