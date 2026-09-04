"""
آزمون‌های کمکی‌های پوسته دسکتاپ (`utils/desktop_support.py`)

پوسته Qt در محیط تست نصب نیست، ولی سه باگ واقعی دسکتاپ (پورت اشغال، لوگوی
نمایش‌داده‌نشده، بازنویسی فایل دانلودی) در همین تابع‌های بدون-Qt زندگی
می‌کنند؛ پس اینجا آزموده می‌شوند. `app_desktop.py` فقط آن‌ها را صدا می‌زند.
"""
import os
import socket
import sys
import threading
from datetime import date

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.desktop_support import (                                        # noqa: E402
    desktop_log_path, get_local_ip, is_port_free, pick_port, resolve_logo_path,
    server_error_text, unique_path, wait_until_serving,
)


@pytest.fixture
def busy_port():
    """پورتی که واقعاً اشغال است."""
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    sock.listen(1)
    port = sock.getsockname()[1]
    yield port
    sock.close()


class TestPorts:
    def test_is_port_free_false_for_occupied(self, busy_port):
        assert is_port_free(busy_port) is False

    def test_pick_port_skips_occupied(self, busy_port):
        chosen = pick_port(busy_port)
        assert chosen is not None
        assert chosen > busy_port, 'باید به پورت بعدی برود'
        assert chosen <= busy_port + 40

    def test_pick_port_keeps_free_port(self, busy_port):
        free = pick_port(busy_port)
        assert pick_port(free) == free

    def test_pick_port_gives_up_after_limit(self, busy_port):
        # بازه‌ای به طول ۱ که پورت اولش اشغال است: limit=0 → None
        assert pick_port(busy_port, limit=0) is None

    def test_server_error_text_is_actionable(self):
        message = server_error_text(OSError('[Errno 98] Address already in use'), 5000)
        assert '5000' in message and '--port 5001' in message
        assert 'None' not in server_error_text(None, 5000)


class TestServing:
    def test_wait_until_serving_false_fast_when_error_set(self, busy_port):
        assert wait_until_serving(busy_port, timeout=2, error=RuntimeError('boom')) is False

    def test_wait_until_serving_times_out_when_nothing_listens(self, busy_port):
        # پورت اشغال است ولی HTTP پاسخ نمی‌دهد → اتصال برقرار می‌شود و
        # urlopen timeout می‌گیرد؛ باید False برگردد، نه that ابدی بلوکه
        assert wait_until_serving(busy_port, timeout=1.5) is False

    def test_wait_until_serving_true_on_any_http_response(self):
        server = socket.socket()
        server.bind(('127.0.0.1', 0))
        server.listen(1)
        port = server.getsockname()[1]

        def _answer_once():
            connection, _ = server.accept()
            connection.recv(4096)
            connection.sendall(b'HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok')
            connection.close()

        thread = threading.Thread(target=_answer_once, daemon=True)
        thread.start()
        try:
            assert wait_until_serving(port, timeout=5) is True
        finally:
            thread.join(timeout=2)
            server.close()


class TestLogo:
    def test_relative_and_uploads_paths(self, tmp_path):
        (tmp_path / 'static' / 'uploads').mkdir(parents=True)
        target = tmp_path / 'static' / 'uploads' / 'logo.png'
        target.write_bytes(b'\x89PNG')
        assert resolve_logo_path('static/uploads/logo.png', str(tmp_path)) == str(target)
        assert resolve_logo_path('/static/uploads/logo.png', str(tmp_path)) == str(target)
        assert resolve_logo_path('logo.png', str(tmp_path / 'static' / 'uploads')) == str(target)

    def test_remote_and_missing_and_traversal(self, tmp_path):
        assert resolve_logo_path('https://cdn/x.png', str(tmp_path)) is None
        assert resolve_logo_path(None, str(tmp_path)) is None
        assert resolve_logo_path('', str(tmp_path)) is None
        assert resolve_logo_path('../../etc/passwd', str(tmp_path)) is None
        assert resolve_logo_path('nope.png', str(tmp_path)) is None

    def test_directory_is_not_a_logo(self, tmp_path):
        (tmp_path / 'logo').mkdir()
        assert resolve_logo_path('logo', str(tmp_path)) is None


class TestDownloads:
    def test_unique_path_avoids_overwrite(self, tmp_path):
        first = unique_path(str(tmp_path), 'snd.pdf')
        assert first.endswith('snd.pdf') and not os.path.exists(first)
        open(first, 'wb').close()
        second = unique_path(str(tmp_path), 'snd.pdf')
        assert second != first and '(1)' in second
        open(second, 'wb').close()
        assert '(2)' in unique_path(str(tmp_path), 'snd.pdf')

    def test_unique_path_sanitizes_name(self, tmp_path):
        path = unique_path(str(tmp_path), '../../evil.txt')
        assert os.path.basename(path) == 'evil.txt'
        assert path.startswith(str(tmp_path))

    def test_empty_filename_falls_back(self, tmp_path):
        assert unique_path(str(tmp_path), '   ').endswith('download')


class TestMisc:
    def test_log_path_is_daily(self, tmp_path):
        path = desktop_log_path(str(tmp_path), date(2026, 9, 3))
        assert path == str(tmp_path / 'logs' / 'desktop-2026-09-03.log')

    def test_get_local_ip_returns_ipv4(self):
        ip = get_local_ip()
        parts = ip.split('.')
        assert len(parts) == 4 and all(part.isdigit() for part in parts)


class TestShellSource:
    """کنترل‌های ایمنی روی خود `app_desktop.py` (بدون اجرای Qt)."""

    @pytest.fixture(scope='class')
    def source(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(root, 'app_desktop.py'), encoding='utf-8') as fh:
            return fh.read()

    def test_does_not_bind_on_all_interfaces_by_default(self, source):
        assert "HOST = '0.0.0.0' if _ARGS.lan else '127.0.0.1'" in source
        assert "make_server(host, port" in source
        # باید با make_server سرور ساخته شود تا shutdown ممکن باشد، نه application.run
        assert "application.run(host=" not in source

    def test_print_and_download_are_handled(self, source):
        assert 'downloadRequested' in source and 'QPrintDialog' in source
        assert 'printRequested' in source

    def test_no_hard_exit(self, source):
        assert 'os._exit(0)' not in source, 'خروج باید با stop_server و quit تمیز باشد'

    def test_server_ready_set_after_bind(self, source):
        assert source.index('SERVER = make_server') < source.index('server_ready.set()')

    def test_fonts_use_ttf_not_woff2(self, source):
        assert "endswith(('.ttf', '.otf'))" in source
        assert "'Vazirmatn-Black.woff2'" not in source, 'woff2 در addApplicationFont کار نمی‌کند'

    def test_single_instance_lock(self, source):
        assert 'QLockFile' in source and 'tryLock' in source

    def test_zoom_shortcuts(self, source):
        for combo in ('Ctrl+P', 'Ctrl+=', 'Ctrl+-', 'Ctrl+0'):
            assert combo in source

    def test_splash_uses_academy_brand(self, source):
        assert 'read_brand(' in source and 'set_brand(' in source


class TestDesktopSpec:
    def test_app_desktop_spec_delegates_to_app_spec(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(root, 'app_desktop.spec'), encoding='utf-8') as fh:
            text = fh.read()
        assert "app.spec" in text and 'exec(compile(' in text
        assert 'Analysis(' not in text, 'نباید دوباره Analysis مستقل داشته باشد (واگرایی spec‌ها)'
