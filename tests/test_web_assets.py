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
    from utils.asset_bundle import _SOURCEMAP_RE
    path = os.path.join(app.static_folder, relative.replace('/', os.sep))
    with open(path, encoding='utf-8') as handle:
        return _SOURCEMAP_RE.sub('', handle.read())


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

        monkeypatch.setattr(asset_bundle.os, 'makedirs', _boom)
        assert asset_bundle.ensure_bundles(app) == {'css': None, 'js': None}


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
