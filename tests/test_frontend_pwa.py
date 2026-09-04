"""
آزمون‌های پوسته/موبایل/PWA/چاپ (فاز ۵ رفع ایرادات دیزاین)
════════════════════════════════════════════════════════════
بخشی از این‌ها رفتار واقعی HTTP می‌سنجد (manifest، /offline، /sw.js، کش
استاتیک) و بخشی پایدار‌سازیِ منبع است — همان سبک test_desktop_support.py،
چون برای CSS/JS مینیفای‌شده و تگ‌های <head> نمی‌توان آزمون رفتاری نوشت.

چرا این تست‌ها لازم‌اند؟ ایراداتی که در بازبینی دیزاین گرفته شد همگی
«بی‌صدا» بودند: manifest نام یک مشتری دیگر را داشت، آیکون فقط SVG بود
(پس «افزودن به صفحه اصلی» روی Android/iOS کار نمی‌کرد)، print.css وجود نداشت
و قوانین چاپ در دو فایل تکرار شده بودند تا تغییرشان بی‌اثر بماند.
"""
import json
import os
import pathlib
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from app import create_app                                            # noqa: E402

TEMPLATES = os.path.join(ROOT, 'templates')
STATIC = os.path.join(ROOT, 'static')
ICONS = os.path.join(STATIC, 'images', 'icons')


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding='utf-8') as handle:
        return handle.read()


@pytest.fixture(scope='module')
def test_app():
    app = create_app()
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    return app


@pytest.fixture(scope='module')
def client(test_app):
    # manifest/offline/sw.js عمداً بی‌نیاز از لایسنس و نشست‌اند؛ پس اینجا
    # هیچ اهرمی برای دورزدن نگهبان لازم نیست (خودِ همین تست، همان شرط است)
    return test_app.test_client()


# ══════════════════════════════════════════════════════════════
#  manifest و نصب روی گوشی
# ══════════════════════════════════════════════════════════════
class TestManifest:
    def test_manifest_route_is_public_and_valid(self, client):
        response = client.get('/manifest.webmanifest')
        assert response.status_code == 200, 'manifest نباید به /login یا /license ریدایرکت شود'
        assert 'manifest+json' in response.mimetype
        payload = json.loads(response.data)
        assert payload['display'] == 'standalone'
        assert payload['start_url'] == '/' and payload['scope'] == '/'

    def test_manifest_uses_academy_name_not_hardcoded_client(self, test_app, client):
        from models.system import SystemSettings
        with test_app.app_context():
            settings_obj = SystemSettings.query.first()
            expected = (settings_obj.academy_name if settings_obj else 'سیستم مدیریت آموزشگاه').strip()
        payload = json.loads(client.get('/manifest.webmanifest').data)
        assert payload['name'] == expected
        assert 'رهسا' not in json.dumps(payload, ensure_ascii=False), \
            'نام یک مشتری خاص نباید در manifest همه نصب‌ها باشد'

    def test_manifest_advertises_png_icons(self, client):
        payload = json.loads(client.get('/manifest.webmanifest').data)
        pngs = [icon for icon in payload['icons'] if icon['type'] == 'image/png']
        assert len(pngs) >= 2, 'Android برای نصب، PNG ۱۹۲ و ۵۱۲ می‌خواهد'
        assert any(icon['purpose'] == 'maskable' for icon in pngs)
        sizes = {icon['sizes'] for icon in payload['icons']}
        assert '192x192' in sizes and '512x512' in sizes
        # قفل جهت صفحه، تبلت و دسکتاپ PWA را می‌شکست
        assert 'orientation' not in payload

    def test_all_advertised_icon_files_exist(self, client):
        payload = json.loads(client.get('/manifest.webmanifest').data)
        for icon in payload['icons']:
            path = icon['src'].split('?')[0]
            relative = path[len('/static/'):]
            assert os.path.isfile(os.path.join(STATIC, relative)), f'آیکون اعلام‌شده وجود ندارد: {path}'
            assert client.get(path).status_code == 200

    def test_fallback_static_manifest_is_neutral(self):
        text = read('static', 'manifest.json')
        payload = json.loads(text)
        assert 'رهسا' not in text
        assert any(icon['type'] == 'image/png' for icon in payload['icons'])


# ══════════════════════════════════════════════════════════════
#  آیکون‌ها
# ══════════════════════════════════════════════════════════════
class TestIcons:
    REQUIRED = ['icon-48.png', 'icon-96.png', 'icon-144.png', 'icon-168.png', 'icon-192.png',
                'icon-384.png', 'icon-512.png', 'icon-maskable-192.png', 'icon-maskable-512.png',
                'apple-touch-icon.png']

    @pytest.mark.parametrize('name', REQUIRED)
    def test_icon_file_is_square_png_with_right_size(self, name):
        from PIL import Image
        path = os.path.join(ICONS, name)
        assert os.path.isfile(path), f'{name} نبود — «افزودن به صفحه اصلی» بدون PNG کار نمی‌کند'
        with Image.open(path) as image:
            assert image.format == 'PNG'
            match = re.search(r'(\d+)', name)
            if match:
                expected = int(match.group(1))
                assert image.size == (expected, expected), f'{name} باید {expected}×{expected} باشد'
            assert image.size[0] == image.size[1], f'{name} باید مربع باشد'

    def test_favicon_and_ico_exist(self):
        from PIL import Image
        images = os.path.join(ROOT, 'static', 'images')
        with Image.open(os.path.join(images, 'favicon.png')) as handle:
            assert handle.format == 'PNG' and handle.size[0] == handle.size[1]
        assert os.path.isfile(os.path.join(images, 'icon.ico')), 'fallback دسکتاپ'

    def test_mark_does_not_collide_with_ledger_lines(self):
        """تیک نباید به خط آخر بچسبد (در ۴۸px قبلاً یکی می‌شدند و نشان «خط‌خورد» به نظر می‌رسید)."""
        from create_icon import _draw_mark, _gradient_tile
        for size in (48, 96, 192):
            img = _draw_mark(_gradient_tile(size)).convert('RGBA')
            ink = [any(img.getpixel((x, y))[0] > 190 and img.getpixel((x, y))[3] > 160
                       for x in range(size)) for y in range(size)]
            runs, current = [], 0
            for row in ink:
                if row:
                    current += 1
                elif current:
                    runs.append(current)
                    current = 0
            if current:
                runs.append(current)
            assert len(runs) >= 4, f'در {size}px سه خط و تیک باید چهار باند جدا باشند، شد: {runs}'

    def test_maskable_mark_inside_safe_zone(self):
        """ماسکه‌بل: Android فقط مرکز ۶۶٪ را تضمین می‌کند؛ نشان باید داخلش بماند."""
        from create_icon import _draw_mark, _gradient_tile
        for size in (192, 512):
            img = _draw_mark(_gradient_tile(size), safe=0.10).convert('RGBA')
            xs, ys = [], []
            for y in range(size):
                for x in range(size):
                    pixel = img.getpixel((x, y))
                    if pixel[0] > 190 and pixel[3] > 160:
                        xs.append(x)
                        ys.append(y)
            assert xs, 'نشان کشیده نشد'
            low, high = 0.16 * size, 0.84 * size
            assert min(xs) >= low and min(ys) >= low, f'{size}px: نشان از ناحیه امن بیرون زده'
            assert max(xs) <= high and max(ys) <= high, f'{size}px: نشان از ناحیه امن بیرون زده'


# ══════════════════════════════════════════════════════════════
#  service worker / آفلاین
# ══════════════════════════════════════════════════════════════
class TestServiceWorker:
    def test_sw_served_from_root_with_scope_header(self, client):
        response = client.get('/sw.js')
        assert response.status_code == 200
        assert 'javascript' in response.mimetype
        assert response.headers.get('Service-Worker-Allowed') == '/', \
            'SW از /static نمی‌تواند کل اپ را کنترل کند'
        assert 'no-store' in response.headers.get('Cache-Control', '')

    def test_offline_page_is_self_contained(self, client):
        body = client.get('/offline').get_data(as_text=True)
        assert 'دسترسی به سرور ممکن نیست' in body
        assert '<base' not in body and 'layout.html' not in body
        assert 'safe-area-inset' in body, 'صفحه آفلاین هم باید notch را رعایت کند'

    def test_sw_does_not_cache_pages(self):
        source = read('static', 'sw.js')
        navigate = source[source.index("request.mode === 'navigate'"):]
        assert 'fetch(request).catch' in navigate
        assert 'cache.put' not in navigate, 'صفحات مالی نباید از کش سرو شوند'
        assert "method !== 'GET'" in source, 'نوشتن هرگز نباید کش شود'

    def test_layout_registers_worker(self):
        assert 'registerServiceWorker' in read('static', 'js', 'app.js')
        assert "'/sw.js'" in read('static', 'js', 'app.js')


# ══════════════════════════════════════════════════════════════
#  نسخه‌دهی استاتیک
# ══════════════════════════════════════════════════════════════
class TestAssetVersioning:
    def test_rendered_pages_are_versioned(self, client):
        body = client.get('/login').get_data(as_text=True)
        assert re.search(r'\.css\?v=[0-9a-fx-]+', body), 'CSS بدون نسخه ⇒ کش کهنه روی موبایل'
        assert 'app.js?v=' in body or 'bootstrap.bundle' in body

    def test_templates_do_not_hardcode_static_urls(self):
        offenders = []
        for base, _dirs, files in os.walk(TEMPLATES):
            for name in files:
                if not name.endswith('.html'):
                    continue
                path = os.path.join(base, name)
                with open(path, encoding='utf-8') as handle:
                    if re.search(r'(href|src)="/static/', handle.read()):
                        offenders.append(os.path.relpath(path, ROOT))
        assert not offenders, f'مسیر هاردکد (زیر path می‌شکند): {offenders}'

    def test_cache_header_on_static(self, client):
        cache = client.get('/static/css/print.css').headers.get('Cache-Control', '')
        assert 'max-age=' in cache, 'بدون SEND_FILE_MAX_AGE_DEFAULT هر بار ۲۰۰KB CSS دانلود می‌شود'

    def test_max_age_is_bounded(self, test_app):
        from datetime import timedelta
        value = test_app.config['SEND_FILE_MAX_AGE_DEFAULT']
        assert isinstance(value, (int, timedelta))
        seconds = value.total_seconds() if isinstance(value, timedelta) else value
        assert 0 < seconds <= 7 * 86400, 'کش بی‌نهایت برای فایل‌های آپلودی خطرناک است'


# ══════════════════════════════════════════════════════════════
#  ورودی عددی (ارقام فارسی + کیبورد موبایل)
# ══════════════════════════════════════════════════════════════
class TestNumericInputs:
    def test_number_inputs_are_converted(self):
        source = read('static', 'js', 'app.js')
        assert "querySelectorAll('input[type=\"number\"]')" in source
        assert "inputmode" in source and 'num-input' in source
        assert 'enterkeyhint' in source, 'کلید «بعدی» بین فیلدهای فرم'

    def test_persian_decimal_separator_survives_typing(self):
        source = read('static', 'js', 'app.js')
        normalizer = source[source.index("document.addEventListener('input'"):]
        normalizer = normalizer[:normalizer.index('}, true);')]
        assert '\\u066B' in normalizer, '٫ باید به نقطه تبدیل شود، نه حذف'

    def test_value_is_never_filled_with_separators(self):
        """parseFloat('1,200') === 1 — اسکریپت‌های inline قالب‌ها را می‌سوزاند."""
        source = read('static', 'js', 'app.js')
        blur = source[source.index("document.addEventListener('blur'"):]
        blur = blur[:blur.index('}, true);')]
        assert 'formatGroupedNumber' not in blur
        assert 'input.value = String(value)' in blur

    def test_ltr_rule_follows_the_conversion(self):
        """بوسترپ RTL فقط روی [type=number] جهت LTR می‌داد؛ با تبدیل به text آن قانون می‌مرد."""
        css = read('templates', 'base', 'layout.html') + read('static', 'css', 'responsive.css')
        assert re.search(r'input\.num-input[^{]*\{[^}]*direction:\s*ltr', css, re.S), \
            'عدد در فیلدِ تبدیل‌شده جهت/ترازش را از دست می‌دهد'

    def test_both_digit_sets_are_mapped(self):
        source = read('static', 'js', 'app.js')
        assert '\\u06f0' in source and '\\u0660' in source, 'فارسی و عربی هر دو'


# ══════════════════════════════════════════════════════════════
#  رفتار واقعی JS (اگر dukpy نصب باشد)
#  این تست‌ها توابع app.js را از فایل بیرون می‌کشند و در یک موتور JS
#  اجرا می‌کنند — تنها راه آزمودن منطق تجزیه عدد فارسی بدون مرورگر.
#  dukpy یک وابستگی توسعه است (نه requirements.txt)؛ نبودش = skip.
# ══════════════════════════════════════════════════════════════
JS_HELPERS = ['FA_DIGITS', 'toLatinDigits', 'parseGroupedNumber', 'formatGroupedNumber',
              'isNumericish', 'initLabelTargets', 'initClickableA11y']


def _js_source():
    source = read('static', 'js', 'app.js')
    out = []
    for name in JS_HELPERS:
        match = re.search(r'\n(var %s = \{|function %s\()' % (name, name), source)
        assert match, f'{name} در app.js پیدا نشد — نام تابع عوض شده؟'
        start = match.start() + 1
        depth, index = 0, source.index('{', start)
        while True:
            char = source[index]
            if char == '{':
                depth += 1
            elif char == '}':
                depth -= 1
                if depth == 0:
                    break
            index += 1
        out.append(source[start:index + 1])
    return '\n'.join(out)


def test_number_parsing_cases():
    dukpy = pytest.importorskip('dukpy')
    cases = [
        ('۹۰۰۰۰۰۰', '9000000'), ('9,000,000', '9000000'), ('12,50', '12.5'),
        ('1.200,50', '1200.5'), ('1,200.50', '1200.5'), ('۱۲۳٬۴۵۶', '123456'),
        ('45٫5', '45.5'), ('abc', ''), ('', ''), ('-1,500', '-1500'),
        ('۱۲۳۴٫۲۵', '1234.25'), ('1 200 000', '1200000'), ('١٢٣٬٤٥٦', '123456'),
        ('−۵۰۰۰۰۰', '-500000'), ('0', '0'),
    ]
    js = (_js_source() + '\n(function(){var r=[];var c=' + json.dumps(cases, ensure_ascii=False) +
          ';c.forEach(function(p){r.push([p[0],String(parseGroupedNumber(p[0])),p[1]]);});'
          'r.push(["digits",toLatinDigits("۱۲٧٨۹٠"),"127890"]);return JSON.stringify(r);})()')
    rows = json.loads(str(dukpy.evaljs(js)))
    for given, got, want in rows:
        assert got == want, f'parseGroupedNumber({given!r}) = {got!r}، انتظار {want!r}'


def test_label_binding_logic():
    dukpy = pytest.importorskip('dukpy')
    js = _js_source() + r"""
(function () {
    function El(opts) {
        var self = opts || {};
        this.attrs = {}; this.controls = self.controls || []; this.id = self.id || '';
        this.style = {};
        this.type = self.type || 'text'; this.className = self.className || '';
        this.offsetWidth = self.hidden ? 0 : 100; this.offsetHeight = self.hidden ? 0 : 30;
        this.classes = this.className ? this.className.split(' ') : [];
        this.parentNode = self.parent || null;
        var self_ = this;
        this.classList = { contains: function (c) { return self_.classes.indexOf(c) !== -1; } };
    }
    El.prototype.setAttribute = function (k, v) { this.attrs[k] = v; };
    El.prototype.getAttribute = function (k) { return this.attrs[k]; };
    El.prototype.hasAttribute = function (k) { return this.attrs[k] !== undefined; };
    El.prototype.querySelectorAll = function () { return this.controls; };
    El.prototype.closest = function () { return null; };
    El.prototype.addEventListener = function () {};
    var bound = new El({ controls: [new El({ id: 'amount' })] });
    var radios = new El({ controls: [new El({ type: 'radio' }), new El({ type: 'radio' })] });
    var invisible = new El({ controls: [new El({ hidden: true })] });
    var empty = new El({ parent: new El({ controls: [new El({ id: 'solo' })] }) });
    empty.controls = [];
    window.document = { querySelectorAll: function () { return [bound, radios, invisible, empty]; } };
    initLabelTargets();
    return JSON.stringify({
        bound: bound.attrs.for === 'amount',
        radiosUntouched: radios.attrs.for === undefined,
        invisibleUntouched: invisible.attrs.for === undefined,
        siblingBound: !!empty.attrs.for && empty.attrs.for === 'solo'
    });
})()
"""
    res = json.loads(str(dukpy.evaljs('var window = this;' + js)))
    assert res['bound'], 'لیبل پوشاننده باید for بگیرد'
    assert res['radiosUntouched'], 'گروه رادیو نباید دست بخورد'
    assert res['invisibleUntouched'], 'به کنترل مخفی نباید for داد'
    assert res['siblingBound'], 'لیبل خواهرِ تنها کنترل والد باید بسته شود'


# ══════════════════════════════════════════════════════════════
#  کنتراست متن (WCAG AA) و توکن‌های رنگ
# ══════════════════════════════════════════════════════════════
class TestContrastTokens:
    LOW_CONTRAST = ('#78909c', '#90a4ae', '#b0bec5')

    def test_no_low_contrast_inline_text_colors(self):
        """این سه خاکستری روی سفید ≈ ۱.۹ تا ۳.۵:۱ بودند — متن «خالی» خوانده نمی‌شد."""
        offenders = []
        for path in pathlib.Path(TEMPLATES).rglob('*.html'):
            text = path.read_text(encoding='utf-8')
            for color in self.LOW_CONTRAST:
                if re.search(r'(?<![-\w])color:\s*' + color, text, re.I):
                    offenders.append((str(path.relative_to(ROOT)), color))
        assert not offenders, f'رنگ متن کم‌کنتراست اینلاین: {offenders[:4]}'

    def test_tokens_exist_in_both_themes(self):
        light = read('static', 'css', 'main.css')
        dark = read('static', 'css', 'theme-dark.css')
        for token in ('--clr-text-muted', '--clr-text-soft', '--clr-text-faint'):
            assert token + ':' in light, f'{token} در :root تعریف نشده'
            assert token + ':' in dark, f'{token} در تم تاریک تعریف نشده ⇒ متن محو می‌شود'
        assert 'var(--clr-text-faint, #607d8b)' in light or '--clr-text-faint' in dark

    def test_var_usages_have_literal_fallback(self):
        """قالب‌های مستقل (گواهی/چاپ) main.css را لینک نمی‌کنند؛ var() بدون
        fallback آنجا بی‌اثر می‌شود و رنگ به ارث می‌رسد."""
        offenders = []
        for path in pathlib.Path(TEMPLATES).rglob('*.html'):
            text = path.read_text(encoding='utf-8')
            for match in re.finditer(r'var\(--clr-text-[a-z]+(?![^)]*,)', text):
                offenders.append((str(path.relative_to(ROOT)), match.group(0)))
        assert not offenders, f'var() بدون مقدار جایگزین: {offenders[:4]}'


# ══════════════════════════════════════════════════════════════
#  چاپ
# ══════════════════════════════════════════════════════════════
class TestPrint:
    def test_print_css_is_single_source(self):
        layout = read('templates', 'base', 'layout.html')
        assert 'css/print.css' in layout, 'قوانین چاپ لینک نشده'
        assert '@media print' not in layout, 'بلوک چاپ اینلاین، print.css را بی‌اثر می‌کند'
        responsive = read('static', 'css', 'responsive.css')
        assert '.sidebar, .top-bar, .mobile-overlay, .no-print' not in responsive, \
            'تکرار قوانین پوسته در دو فایل ⇒ هیچ‌کدام قابل تغییر نبود'

    def test_page_rules_and_colors(self):
        css = read('static', 'css', 'print.css')
        assert '@page' in css and 'print-color-adjust: exact' in css

    def test_only_filter_forms_are_hidden(self):
        css = read('static', 'css', 'print.css')
        assert 'form[method="GET"]' in css
        assert not re.search(r'(?m)^\s*form\s*\{', css), \
            'form{display:none} جدول گزارش‌ها را هم حذف می‌کند'

    def test_print_header_footer_wired_to_settings(self):
        layout = read('templates', 'base', 'layout.html')
        assert 'print_header' in layout and 'print_footer' in layout
        assert 'printHeader' in layout and 'printFooter' in layout
        css = read('static', 'css', 'print.css')
        assert '#printHeader' in css and '.print-brand' in css

    def test_actions_hidden_in_print(self):
        css = read('static', 'css', 'print.css')
        for selector in ('.btn', '.pagination', '.modal', '.mobile-overlay', '.top-bar'):
            assert selector in css, f'{selector} در چاپ پنهان نمی‌شود'

    def test_no_print_class_used_in_templates(self):
        used = 0
        for base, _dirs, files in os.walk(TEMPLATES):
            for name in files:
                if name.endswith('.html'):
                    with open(os.path.join(base, name), encoding='utf-8') as handle:
                        used += handle.read().count('no-print')
        assert used >= 10, 'کلاس no-print باید واقعاً در قالب‌ها به کار رفته باشد'


# ══════════════════════════════════════════════════════════════
#  خوانایی موبایل و دسترس‌پذیری
# ══════════════════════════════════════════════════════════════
class TestMobileReadability:
    def test_mobile_table_font_size_is_readable(self):
        responsive = read('static', 'css', 'responsive.css')
        assert '--table-fs: 14px' in responsive
        # مصرف‌کننده متغیر می‌تواند در main.css باشد (CSS اینلاین layout به آنجا
        # منتقل شده) — مهم همین جفت شدن است، نه محل فایل
        skin = read('templates', 'base', 'layout.html') + read('static', 'css', 'main.css')
        assert 'var(--table-fs' in skin, 'قانون موبایل باید از متغیر بخواند وگرنه قانون پایه می‌برند'

    def test_wrapped_tables_have_scroll_style(self):
        source = read('static', 'js', 'app.js')
        assert 'table-wrap-mobile' in source
        assert '.table-wrap-mobile' in read('static', 'css', 'responsive.css')
        assert "table.closest('td, th')" in source, 'جدول تودرتو نباید پیچیده شود'

    def test_user_menu_scrolls_on_mobile(self):
        responsive = read('static', 'css', 'responsive.css')
        assert 'max-height: min(62dvh, 420px)' in responsive

    def test_search_dropdown_below_modals(self):
        layout = read('templates', 'base', 'layout.html')
        assert 'z-index: 1060' not in layout, 'دراپ‌داون جستجو روی مودال (۱۰۵۵) می‌نشست'

    def test_viewport_units_use_dvh(self):
        skin = read('templates', 'base', 'layout.html') + read('static', 'css', 'main.css')
        assert 'min-height: 100dvh' in skin and 'height: 100dvh' in skin
        assert 'height: 100vh;' not in skin, '۱۰۰vh روی موبایل نوار آدرس را حساب می‌کند'

    def test_reduced_motion_guard(self):
        assert 'prefers-reduced-motion: reduce' in read('static', 'css', 'animations.css')

    def test_layout_css_is_extracted_and_cacheable(self):
        """۵۷۵ خط CSS داخل <style> ⇒ در هر navigation دوباره دانلود/پارس.

        پس باید در main.css باشد و theme-dark.css هم بعد از آن لینک شود تا
        حالت تاریک واقعاً قوانین پوسته را ببرد.
        """
        layout = read('templates', 'base', 'layout.html')
        assert '<style>' not in layout, 'CSS اینلاین باید در static/css/main.css باشد'
        assert "asset('css/main.css')" in layout and "asset('css/theme-dark.css')" in layout
        assert layout.index("asset('css/main.css')") < layout.index("asset('css/theme-dark.css')"), \
            'ترتیب لینک‌ها: theme-dark بعد از main'
        assert len(read('static', 'css', 'main.css').splitlines()) > 400
        assert 'body.dark-mode' not in read('static', 'css', 'animations.css'), \
            'قوانین تاریک نباید میان انیمیشن‌ها (زودتر از پوسته) بمانند'
        assert 'body.dark-mode' in read('static', 'css', 'theme-dark.css')

    def test_font_preload_urls_match_font_face(self):
        """preload با آدرس نسخه‌دار (?v=) با URL خودِ @font-face جور نیست ⇒ دو بار دانلود."""
        layout = read('templates', 'base', 'layout.html')
        face = read('static', 'fonts', 'Vazirmatn-font-face.css')
        preloaded = re.findall(
            r"""rel="preload"[^>]*href="\{\{\s*url_for\('static',\s*filename='([^']+)'""", layout)
        assert preloaded, 'پریلود وزن‌های پراستفاده حذف شده'
        for path in preloaded:
            name = os.path.basename(path)
            assert name in face, f'{name} در @font-face نیست ⇒ پریلود بی‌مصرف است'
            assert f"asset('{path}')" not in layout, 'پریلود فونت نباید ?v= بگیرد'

    def test_no_comment_only_css_rules(self):
        """قانونی که فقط کامنت داخلش بود (top-icon-btn) باید واقعاً پر شده باشد."""
        offenders = []
        for base, _dirs, files in os.walk(os.path.join(ROOT, 'static', 'css')):
            for name in files:
                if not name.endswith('.css') or '.min.' in name:
                    continue
                path = os.path.join(base, name)
                with open(path, encoding='utf-8') as handle:
                    text = re.sub(r'/\*.*?\*/', '', handle.read(), flags=re.S)
                # بلوک انتخاب‌گرِ خالی (نه @media/@supports که بدنه دارند)
                for match in re.finditer(r'([^{}@;/]+)\s*\{\s*\}', text):
                    selector = match.group(1).strip().splitlines()[-1].strip()
                    if selector:
                        offenders.append((os.path.relpath(path, ROOT), selector[:60]))
        assert not offenders, f'قانون خالی CSS: {offenders[:4]}'
