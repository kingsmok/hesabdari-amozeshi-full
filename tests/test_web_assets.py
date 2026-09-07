"""آزمون سرو استاتیک و بسته‌بندی CSS/JS — همان‌چه صفحه را روی هاست کند می‌کرد.

پیش از این: ۲۰ منبع استاتیک، ۶۵۴KB بدون هیچ فشرده‌سازی، کش یک‌روزه.
حالا: ۸ منبع، ~۱۶۰KB با gzip، کش یک‌سالهٔ immutable.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault('ACADEMY_DISABLE_SCHEDULER', '1')
os.environ.setdefault('ACADEMY_DISABLE_BALE', '1')

from app import create_app  # noqa: E402


# ── ابزارها ───────────────────────────────────────────────────────
def _source(app, relative):
    """متن یک منبع استاتیک، با همان تبدیلی که بسته‌ساز رویش اعمال می‌کند."""
    from utils.asset_bundle import _SOURCEMAP_RE, _rebase_urls
    path = os.path.join(app.static_folder, relative.replace('/', os.sep))
    with open(path, encoding='utf-8') as handle:
        text = _SOURCEMAP_RE.sub('', handle.read())
    return _rebase_urls(text, relative)


def _wrapped(app, relative, wrap):
    text = _source(app, relative)
    return f'@media print {{\n{text}\n}}' if wrap else text


def _bundle_body(app, kind):
    relative = app.extensions['asset_bundles'][kind]
    path = os.path.join(app.static_folder, relative.replace('/', os.sep))
    with open(path, encoding='utf-8') as handle:
        return handle.read()


def _render_layout(app):
    """base/layout.html مستقیم رندر می‌شود — صفحهٔ لاگین layout جدا دارد."""
    from flask import render_template
    with app.test_request_context('/'):
        return render_template('base/layout.html')


def _get(client, path, gzip=True, headers=None):
    extra = {'Accept-Encoding': 'gzip'} if gzip else {}
    extra.update(headers or {})
    return client.get(path, headers=extra)


@pytest.fixture(scope='module')
def app():
    application = create_app()
    application.config['TESTING'] = True
    return application


@pytest.fixture
def client(app):
    return app.test_client()


# ══════════════════════════════════════════════════════════════
class TestStaticCompression:
    def test_css_is_gzipped(self, client):
        response = _get(client, '/static/css/main.css')
        assert response.status_code == 200
        assert response.headers.get('Content-Encoding') == 'gzip'
        assert 'Accept-Encoding' in response.headers.get('Vary', '')

    def test_gzip_actually_shrinks_the_payload(self, client):
        import gzip as _gzip
        response = _get(client, '/static/css/bootstrap.rtl.min.css')
        raw = _gzip.decompress(response.data)
        assert len(response.data) < len(raw) * 0.25, \
            f'bootstrap باید دست‌کم ۷۵٪ کوچک شود: {len(response.data)} از {len(raw)}'

    def test_without_accept_encoding_served_raw(self, client):
        response = _get(client, '/static/css/main.css', gzip=False)
        assert response.headers.get('Content-Encoding') is None
        assert response.data.startswith(b'/*') or b'{' in response.data

    def test_already_compressed_files_are_not_gzipped(self, client):
        for path in ('/static/fonts/Vazirmatn-Regular.woff2',
                     '/static/images/icons/icon-192.png'):
            response = _get(client, path)
            assert response.status_code == 200
            assert response.headers.get('Content-Encoding') is None, \
                f'{path} از قبل فشرده است؛ gzip دوباره فقط CPU هدر می‌دهد'

    def test_small_file_is_not_gzipped(self, client):
        response = _get(client, '/static/images/favicon.svg')
        assert response.status_code == 200
        assert response.headers.get('Content-Encoding') is None

    def test_compressed_bytes_are_reused_not_recomputed(self, client):
        from bootstrap import static_assets
        before = static_assets.cache_stats()['entries']
        for _ in range(3):
            _get(client, '/static/css/main.css')
        after = static_assets.cache_stats()
        assert after['entries'] <= before + 1, 'هر درخواست دوباره فشرده می‌کند'


# ══════════════════════════════════════════════════════════════
class TestStaticCachePolicy:
    def test_versioned_assets_are_immutable(self, client):
        cache_control = _get(client, '/static/css/main.css').headers.get('Cache-Control', '')
        assert 'public' in cache_control
        assert 'max-age=31536000' in cache_control
        assert 'immutable' in cache_control

    def test_uploads_are_not_immutable(self, client, app):
        """عکس هنرجو آدرس نسخه‌دار ندارد؛ کش یک‌ساله یعنی عکس عوض‌شده دیده نشود."""
        uploads = os.path.join(app.static_folder, 'uploads')
        os.makedirs(uploads, exist_ok=True)
        probe = os.path.join(uploads, '_cache_policy_probe.txt')
        with open(probe, 'w', encoding='utf-8') as handle:
            handle.write('x' * 2048)
        try:
            response = _get(client, '/static/uploads/_cache_policy_probe.txt')
            assert response.status_code == 200
            cache_control = response.headers.get('Cache-Control', '')
            assert 'immutable' not in cache_control
            assert 'max-age=31536000' not in cache_control
            assert 'max-age=3600' in cache_control
        finally:
            os.remove(probe)

    def test_conditional_request_returns_304(self, client):
        first = _get(client, '/static/css/main.css')
        etag = first.headers['ETag']
        second = _get(client, '/static/css/main.css', headers={'If-None-Match': etag})
        assert second.status_code == 304
        assert second.headers['ETag'] == etag

    def test_etag_separates_gzip_and_raw(self, client):
        """وگرنه مرورگری که نسخهٔ خام را کش کرده، پاسخ gzip را ۳۰۴ می‌گیرد."""
        gz = _get(client, '/static/css/main.css').headers['ETag']
        raw = _get(client, '/static/css/main.css', gzip=False).headers['ETag']
        assert gz != raw

    def test_html_is_not_cached(self, client):
        response = client.get('/login')
        assert response.status_code == 200
        assert 'no-cache' in response.headers.get('Cache-Control', '')

    def test_missing_file_is_404(self, client):
        assert _get(client, '/static/css/no-such-file.css').status_code == 404

    def test_path_traversal_is_rejected(self, client):
        response = client.get('/static/../settings.json',
                              headers={'Accept-Encoding': 'gzip'})
        assert response.status_code == 404


# ══════════════════════════════════════════════════════════════
class TestAssetBundle:
    def test_bundles_built_at_boot(self, app):
        bundles = app.extensions['asset_bundles']
        assert bundles['css'] and bundles['js'], bundles
        for relative in bundles.values():
            assert os.path.isfile(
                os.path.join(app.static_folder, relative.replace('/', os.sep)))

    def test_css_bundle_is_exactly_the_sources_in_layout_order(self, app):
        """محتوای بسته = الحاق منابع به همان ترتیب layout (نه بیشتر، نه کمتر)."""
        from utils.asset_bundle import (CSS_HEAD_SOURCES, CSS_PRINT_SOURCE,
                                        CSS_TAIL_SOURCES)
        order = list(CSS_HEAD_SOURCES) + [CSS_PRINT_SOURCE] + list(CSS_TAIL_SOURCES)
        expected = '\n'.join(
            _wrapped(app, name, wrap=(name == CSS_PRINT_SOURCE)).strip('\n')
            for name in order
        ) + '\n'
        assert _bundle_body(app, 'css') == expected

    def test_js_bundle_keeps_execution_order(self, app):
        from utils.asset_bundle import JS_SOURCES
        expected = '\n;\n'.join(
            _source(app, name).strip('\n') for name in JS_SOURCES) + '\n'
        assert _bundle_body(app, 'js') == expected

    def test_print_css_is_scoped_to_print_media(self, app):
        body = _bundle_body(app, 'css')
        assert '@media print {' in body, 'print.css باید فقط در چاپ اعمال شود'
        assert body.count('{') == body.count('}'), 'آکولادهای بسته نامتوازن است'

    def test_sourcemap_comments_are_stripped(self, app):
        assert 'sourceMappingURL' not in _bundle_body(app, 'js')

    def test_layout_emits_one_css_and_one_js_tag(self, app):
        body = _render_layout(app)
        assert f"/static/{app.extensions['asset_bundles']['css']}" in body
        assert f"/static/{app.extensions['asset_bundles']['js']}" in body
        # فایل‌های جدا نباید هم‌زمان لینک شوند (دوبار دانلود)
        assert '/static/css/main.css' not in body
        assert '/static/js/app.js' not in body

    def test_bundling_reduces_asset_count(self, app):
        import re
        body = _render_layout(app)
        links = set(re.findall(r'(?:href|src)="(/static/[^"?]+\.(?:css|js))"', body))
        assert len(links) <= 4, f'باید ۲ فایل بسته باشد، نه {len(links)}: {sorted(links)}'

    def test_fingerprint_follows_content(self):
        from utils.asset_bundle import _fingerprint
        assert _fingerprint([('a.css', 'body{color:red}')]) != \
               _fingerprint([('a.css', 'body{color:blue}')])

    def test_old_bundles_are_pruned(self, app):
        gen_dir = os.path.join(app.static_folder, 'gen')
        stale = os.path.join(gen_dir, 'app.deadbeefdead.css')
        with open(stale, 'w', encoding='utf-8') as handle:
            handle.write('/* کهنگی */')
        from utils.asset_bundle import _prune
        _prune(gen_dir, {app.extensions['asset_bundles']['css'],
                         app.extensions['asset_bundles']['js']})
        assert not os.path.exists(stale)


# ══════════════════════════════════════════════════════════════
class TestBundleCanBeDisabled:
    def test_env_flag_falls_back_to_separate_files(self, monkeypatch):
        monkeypatch.setenv('ACADEMY_ASSET_BUNDLE', '0')
        application = create_app()
        application.config['TESTING'] = True
        assert application.extensions['asset_bundles'] == {'css': None, 'js': None}

        body = _render_layout(application)
        assert '/static/css/main.css' in body
        assert '/static/js/app.js' in body
        assert '/static/gen/' not in body

    def test_unwritable_static_falls_back_quietly(self, app, monkeypatch):
        """روی نصب PyInstaller پوشهٔ static فقط‌خواندنی است؛ بوت نباید بشکند."""
        from utils import asset_bundle

        def _boom(*_args, **_kwargs):
            raise OSError('read-only file system')

        # `ensure_bundles` روی خودِ app می‌نویسد؛ این fixture بین تست‌های این
        # ماژول مشترک است، پس مقدار اصلی را برمی‌گردانیم تا تست‌های بعدی
        # بسته‌ها را None نبینند.
        original = dict(app.extensions['asset_bundles'])
        monkeypatch.setattr(asset_bundle.os, 'makedirs', _boom)
        try:
            assert asset_bundle.ensure_bundles(app) == {'css': None, 'js': None}
        finally:
            app.extensions['asset_bundles'] = original


# ══════════════════════════════════════════════════════════════
class TestFileLock:
    def test_lock_serialises_two_processes(self, tmp_path):
        """دو پردازه هم‌زمان داخل بخش قفل‌شده نباشند (ریشهٔ کرش بوت چندورکری)."""
        import subprocess
        import textwrap

        repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        script = textwrap.dedent(f'''
            import sys, os, time
            sys.path.insert(0, {repo!r})
            from utils.file_lock import file_lock
            marker = {str(tmp_path / 'inside')!r}
            with file_lock({str(tmp_path / 'test.lock')!r}, timeout=20) as got:
                assert got, 'قفل گرفته نشد'
                overlap = os.path.exists(marker)
                open(marker, 'w').write(str(os.getpid()))
                print('OVERLAP' if overlap else 'EXCLUSIVE', flush=True)
                time.sleep(0.6)
                os.remove(marker)
        ''')
        procs = [subprocess.Popen([sys.executable, '-c', script],
                                  stdout=subprocess.PIPE, text=True)
                 for _ in range(2)]
        results = [proc.communicate(timeout=60)[0].strip() for proc in procs]
        assert all(proc.returncode == 0 for proc in procs), results
        assert results.count('EXCLUSIVE') == 2, f'هم‌پوشانی داشت: {results}'

    def test_lock_can_be_taken_again_after_release(self, tmp_path):
        from utils.file_lock import file_lock
        path = str(tmp_path / 'again.lock')
        with file_lock(path) as first:
            assert first is True
        with file_lock(path) as second:
            assert second is True

    def test_unwritable_path_degrades_without_lock(self):
        from utils.file_lock import file_lock
        with file_lock('/proc/definitely-not-writable/x.lock') as acquired:
            assert acquired is False


# ══════════════════════════════════════════════════════════════
class TestBundleRelativeUrls:
    """بسته در `static/gen/` است، یک سطح عمیق‌تر از جای اصلی منابع.

    آدرس نسبیِ `url("fonts/bootstrap-icons.woff2")` که در `static/css/` درست
    بود، از `static/gen/` به مسیری حل می‌شود که وجود ندارد — یعنی فونت
    آیکون‌ها ۴۰۴ می‌داد و هر آیکون خالی نمایش داده می‌شد.
    """

    def test_every_relative_url_in_the_bundle_resolves(self, app):
        import re
        from urllib.parse import urljoin
        relative = app.extensions['asset_bundles']['css']
        bundle_url_path = f'/static/{relative}'
        body = _bundle_body(app, 'css')
        urls = re.findall(r'url\(\s*[\'"]?([^\'")]+)[\'"]?\s*\)', body)
        relative_urls = [u for u in urls
                         if not u.startswith(('/', 'http:', 'https:', 'data:', '#'))]
        assert relative_urls, 'انتظار می‌رفت بسته آدرس نسبی داشته باشد'
        for url in relative_urls:
            resolved = urljoin(bundle_url_path, url.split('?')[0])
            on_disk = os.path.join(app.static_folder,
                                   resolved[len('/static/'):].replace('/', os.sep))
            assert os.path.isfile(on_disk), \
                f'{url} از دید بسته به {resolved} حل می‌شود که وجود ندارد'

    def test_icon_font_is_served_at_the_url_the_bundle_points_to(self, client, app):
        """همان کاری که مرورگر می‌کند: آدرس را از بسته بردار، حل کن، درخواست بده."""
        import re
        from urllib.parse import urljoin
        bundle_url_path = f"/static/{app.extensions['asset_bundles']['css']}"
        body = _bundle_body(app, 'css')
        matches = re.findall(r'url\(\s*[\'"]?([^\'")]*bootstrap-icons\.woff2[^\'")]*'
                             r')[\'"]?\s*\)', body)
        assert matches, 'فونت آیکون‌ها در بسته پیدا نشد'
        resolved = urljoin(bundle_url_path, matches[0])
        response = _get(client, resolved)
        assert response.status_code == 200, \
            f'{resolved} → {response.status_code}؛ آیکون‌ها خالی نمایش داده می‌شدند'
        assert len(response.data) > 100_000, 'فونت آیکون‌ها ناقص سرو شد'

    def test_rebasing_leaves_absolute_and_data_urls_alone(self):
        from utils.asset_bundle import _rebase_urls
        source = ('a{background:url(/static/x.png)}\n'
                  'b{background:url(https://e.com/y.png)}\n'
                  'c{background:url(data:image/png;base64,AAA)}\n'
                  'd{background:url(#frag)}')
        assert _rebase_urls(source, 'css/z.css') == source

    def test_rebasing_prefixes_the_source_directory(self):
        from utils.asset_bundle import _rebase_urls
        assert _rebase_urls("a{src:url('fonts/x.woff2')}", 'css/z.css') == \
            "a{src:url('../css/fonts/x.woff2')}"
        # پرس‌وجو (کوئری) باید سر جایش بماند
        assert _rebase_urls('a{src:url(f.woff2?v=1)}', 'fonts/z.css') == \
            'a{src:url(../fonts/f.woff2?v=1)}'


# ══════════════════════════════════════════════════════════════
class TestBrotli:
    """`brotli` اختیاری است؛ نبودنش نباید چیزی را بشکند."""

    def test_brotli_is_preferred_when_the_browser_supports_it(self, client):
        from bootstrap import static_assets
        if static_assets._brotli is None:
            pytest.skip('بستهٔ اختیاری brotli نصب نیست')
        response = _get(client, '/static/css/bootstrap.rtl.min.css',
                        headers={'Accept-Encoding': 'gzip, deflate, br'})
        assert response.headers.get('Content-Encoding') == 'br'

    def test_brotli_payload_is_smaller_than_gzip(self, client):
        import brotli as _brotli
        import gzip as _gzip
        path = '/static/css/bootstrap.rtl.min.css'
        br = _get(client, path, headers={'Accept-Encoding': 'br'})
        gz = _get(client, path, headers={'Accept-Encoding': 'gzip'})
        assert len(br.data) < len(gz.data), \
            f'brotli {len(br.data)} باید کوچک‌تر از gzip {len(gz.data)} باشد'
        assert _brotli.decompress(br.data) == _gzip.decompress(gz.data), \
            'بدنهٔ باز شده باید یکسان باشد'

    def test_etag_separates_brotli_and_gzip(self, client):
        from bootstrap import static_assets
        if static_assets._brotli is None:
            pytest.skip('بستهٔ اختیاری brotli نصب نیست')
        path = '/static/css/main.css'
        br = _get(client, path, headers={'Accept-Encoding': 'br'}).headers['ETag']
        gz = _get(client, path, headers={'Accept-Encoding': 'gzip'}).headers['ETag']
        assert br != gz, 'وگرنه مرورگر نسخهٔ gzip کش‌شده را برای br تایید می‌کند'

    def test_without_the_package_it_falls_back_to_gzip(self, client, monkeypatch):
        """مهم‌ترین تضمین: روی هاستی که brotli نصب نمی‌شود، برنامه کار می‌کند."""
        from bootstrap import static_assets
        monkeypatch.setattr(static_assets, '_brotli', None)
        response = _get(client, '/static/css/bootstrap.rtl.min.css',
                        headers={'Accept-Encoding': 'gzip, deflate, br'})
        assert response.status_code == 200
        assert response.headers.get('Content-Encoding') == 'gzip', \
            'سرور نباید br بفرستد وقتی نمی‌تواند تولیدش کند'

    def test_identity_is_never_brotli(self, client):
        response = _get(client, '/static/css/main.css', gzip=False)
        assert response.headers.get('Content-Encoding') is None


# ══════════════════════════════════════════════════════════════
class TestBootPriming:
    def test_prime_warms_the_cache_before_any_request(self, tmp_path):
        from bootstrap import static_assets
        target = tmp_path / 'probe.css'
        target.write_text('body{color:red;margin:0}\n' * 200, encoding='utf-8')
        before = static_assets.cache_stats()['entries']
        assert static_assets.prime([str(target)]) > 0
        assert static_assets.cache_stats()['entries'] > before

    def test_boot_precompresses_both_bundles(self):
        """بستهٔ CSS با brotli نیم ثانیه CPU می‌برد؛ نباید سهم اولین کاربر باشد."""
        from bootstrap import static_assets
        with static_assets._CACHE_LOCK:
            static_assets._CACHE.clear()
        fresh = create_app()
        fresh.config['TESTING'] = True
        expected = 2 * (2 if static_assets._brotli else 1)
        assert static_assets.cache_stats()['entries'] == expected, \
            'انتظار gzip+br برای هر دو بسته بود'

    def test_priming_is_idempotent(self, app):
        from bootstrap import static_assets
        paths = [os.path.join(app.static_folder, rel.replace('/', os.sep))
                 for rel in app.extensions['asset_bundles'].values()]
        first = static_assets.prime(paths)
        entries = static_assets.cache_stats()['entries']
        assert static_assets.prime(paths) == first
        assert static_assets.cache_stats()['entries'] == entries

    def test_missing_paths_are_ignored(self):
        from bootstrap import static_assets
        assert static_assets.prime(['/nope/absent.css', None] ) >= 0


# ══════════════════════════════════════════════════════════════
class TestFontPreload:
    """۵ وزن فونت ≈ ۲۵۰KB، بزرگ‌ترین بخش بارِ هر صفحه.

    این وزن‌ها را خودِ چیدمان پایه لازم دارد، پس هر صفحه‌ای به همه‌شان نیاز
    دارد. preload باعث می‌شود دانلودشان با دانلود CSS موازی شود، نه بعدش.
    """

    WEIGHTS = ('Regular', 'Medium', 'SemiBold', 'Bold', 'ExtraBold')
    NUMERIC = {'Regular': 400, 'Medium': 500, 'SemiBold': 600,
               'Bold': 700, 'ExtraBold': 800}

    def test_layout_preloads_every_weight(self, app):
        body = _render_layout(app)
        for weight in self.WEIGHTS:
            assert f'/static/fonts/Vazirmatn-{weight}.woff2' in body

    def test_preloaded_files_exist(self, app):
        for weight in self.WEIGHTS:
            path = os.path.join(app.static_folder, 'fonts', f'Vazirmatn-{weight}.woff2')
            assert os.path.isfile(path), f'{path} نیست'

    def test_preload_urls_have_no_cache_busting_query(self, app):
        """@font-face آدرس بدون ?v= اعلام می‌کند؛ با ?v= هر فایل دو بار دانلود می‌شد."""
        import re
        body = _render_layout(app)
        found = re.findall(r'<link rel="preload" as="font"[^>]*?href="([^"]+)"', body)
        assert len(found) == len(self.WEIGHTS), found
        for href in found:
            assert '?' not in href, f'{href} کوئری دارد و با @font-face یکی نمی‌شود'

    def test_every_preloaded_weight_is_still_used_by_the_css(self, app):
        import re
        css = _bundle_body(app, 'css')
        for name, number in self.NUMERIC.items():
            assert re.search(rf'font-weight:\s*{number}\b', css), \
                f'وزن {name} ({number}) دیگر در CSS استفاده نمی‌شود؛ ' \
                f'preload آن ۵۰KB هدر است و باید از layout حذف شود'
