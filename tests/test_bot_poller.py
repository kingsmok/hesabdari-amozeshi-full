"""آزمون poller ربات بله — همان چیزهایی که ربات را روی هاست «کند» می‌کرد.

این ماژول شبکهٔ واقعی ندارد: `requests.Session.request` با یک تقلبِ دارای
تأخیر مصنوعی جایگزین می‌شود تا رفتار poller (موازی‌کاری، جداسازی خطا،
عدم تکرار پیام) قابل اندازه‌گیری باشد.
"""
import os
import sys
import threading
import time

import pytest
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault('ACADEMY_DISABLE_SCHEDULER', '1')
os.environ.setdefault('ACADEMY_DISABLE_BALE', '1')

from app import create_app  # noqa: E402


class _Response:
    def __init__(self, payload, ok=True, status_code=200):
        self._payload, self.ok, self.status_code = payload, ok, status_code

    def json(self):
        return self._payload

    def raise_for_status(self):
        if not self.ok:
            raise requests.HTTPError(f'HTTP {self.status_code}')


def _update(update_id, chat_id, text):
    return {'update_id': update_id,
            'message': {'chat': {'id': chat_id, 'first_name': f'u{chat_id}'},
                        'text': text}}


@pytest.fixture(autouse=True)
def licensed_state():
    """نگهبان لایسنس در آزمون به سرور وصل نشود — وضعیت معتبر فقط در حافظه."""
    import license_client
    from license_features import AVAILABLE_FEATURES

    data = {'success': True, 'status': 'SUCCESS',
            'allowed_features': {item['key']: True for item in AVAILABLE_FEATURES}}
    original = license_client.refresh_state

    def _fake_refresh(*_args, **_kwargs):
        return license_client._store_state(license_client.LicenseState(
            status='SUCCESS', message='', data=data, valid=True, source='online'))

    license_client.refresh_state = _fake_refresh
    _fake_refresh()
    yield
    license_client.refresh_state = original
    license_client._store_state(None)


@pytest.fixture(scope='module')
def app():
    application = create_app()
    application.config['TESTING'] = True
    return application


@pytest.fixture
def manager():
    """نمونهٔ مستقل — singleton ماژول بین آزمون‌ها آلوده نمی‌شود."""
    from utils.bot_services import BalePollingManager
    instance = BalePollingManager()
    yield instance
    instance.stop()


class FakeBale:
    """سرور تقلبی بله با تأخیر مصنوعی و آمار فراخوانی‌ها."""

    def __init__(self, updates, latency=0.0, blocked_chats=(), fail_connect_times=0):
        self.updates = updates
        self.latency = latency
        self.blocked_chats = set(blocked_chats)
        self.fail_connect_times = fail_connect_times
        self.sent = []                 # (chat_id, text) به ترتیب ارسال
        self.calls = 0
        self.polls = 0
        self._connect_failures = 0
        self._served_offsets = []
        self._lock = threading.Lock()

    def request(self, method, url, **kwargs):
        # به‌عنوان متد Session نصب می‌شود؛ `self` خودِ FakeBale است

        with self._lock:
            self.calls += 1
        if self.latency:
            time.sleep(self.latency)

        if self.fail_connect_times and self._connect_failures < self.fail_connect_times:
            self._connect_failures += 1
            raise requests.ConnectionError('اتصال برقرار نشد')

        if 'deleteWebhook' in url:
            return _Response({'ok': True})

        if 'getUpdates' in url:
            self.polls += 1
            offset = (kwargs.get('params') or {}).get('offset', 0)
            self._served_offsets.append(offset)
            batch = [u for u in self.updates if u['update_id'] >= offset]
            return _Response({'ok': True, 'result': batch})

        body = kwargs.get('json') or {}
        chat_id = body.get('chat_id')
        if chat_id in self.blocked_chats:
            return _Response({'ok': False, 'error_code': 403,
                              'description': 'bot was blocked by the user'})
        with self._lock:
            self.sent.append((chat_id, body.get('text')))
        return _Response({'ok': True, 'result': {'message_id': 1}})

    def install(self, monkeypatch):
        # هم Session (کد جدید) و هم requests.get/post (کد قدیمی) گرفتن می‌شوند
        # تا هیچ آزمونی ناخواسته به شبکهٔ واقعی نرود.
        monkeypatch.setattr(requests.Session, 'request', self.request)
        monkeypatch.setattr(requests, 'get',
                            lambda url, **kw: self.request('GET', url, **kw))
        monkeypatch.setattr(requests, 'post',
                            lambda url, **kw: self.request('POST', url, **kw))

    def wait_for(self, predicate, timeout=20):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return True
            time.sleep(0.02)
        return False


@pytest.fixture
def echo_handler(monkeypatch):
    """process_bot_message را با بازگرداندن همان متن جایگزین می‌کند تا
    ترتیب پاسخ‌ها از روی متن قابل تشخیص باشد (بدون درگیرشدن دیتابیس)."""
    from utils import bot_services
    monkeypatch.setattr(
        bot_services, 'process_bot_message',
        lambda text, chat_info, contact=None, provider='bale': (text or '', None),
    )


class TestConnectionReuse:
    def test_same_thread_reuses_one_session(self):
        from utils.bot_services import _http_session
        first, second = _http_session(), _http_session()
        assert first is second
        assert isinstance(first, requests.Session)

    def test_each_thread_has_its_own_session(self):
        from utils.bot_services import _http_session
        seen = {}

        def worker(name):
            seen[name] = id(_http_session())

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(set(seen.values())) == 3, 'Session بین تردها مشترک نباشد'

    def test_call_api_retries_once_on_connection_error(self, monkeypatch):
        from utils import bot_services
        fake = FakeBale([], fail_connect_times=1)
        fake.install(monkeypatch)
        result = bot_services._call_api('getMe', 'bale', 'TOK')
        assert result['ok'] is True
        assert fake.calls == 2, 'بعد از خطای اتصال، یک بار تلاش دوباره'

    def test_429_retry_after_is_parsed(self):
        from utils.bot_services import retry_after_seconds
        assert retry_after_seconds(
            {'ok': False, 'error_code': 429, 'parameters': {'retry_after': 7}}) == 7.0
        assert retry_after_seconds({'ok': False, 'error_code': 403}) == 0.0
        assert retry_after_seconds({'ok': True}) == 0.0


class TestOneBadChatDoesNotStallOthers:
    """باگ اصلی: اگر ارسال پاسخ یک کاربر شکست می‌خورد، کل دسته رها می‌شد
    و بقیهٔ کاربرها هرگز پاسخ نمی‌گرفتند."""

    def test_blocked_user_does_not_block_the_queue(self, app, manager, monkeypatch,
                                                   echo_handler):
        chats = [9001, 9002, 9003, 9004, 9005]
        updates = [_update(500 + i, chat, '/start') for i, chat in enumerate(chats)]
        fake = FakeBale(updates, latency=0.05, blocked_chats={9003})
        fake.install(monkeypatch)

        with app.app_context():
            started, _ = manager.start(app, 'FAKE:TOKEN')
            assert started
            assert fake.wait_for(lambda: len(fake.sent) >= len(chats) - 1)

        answered = {chat for chat, _ in fake.sent}
        assert answered == set(chats) - {9003}, 'همه به‌جز کاربر block‌شده پاسخ گرفتند'
        status = manager.status()
        assert status['failed'] == 1
        assert status['processed'] == len(chats) - 1

    def test_no_duplicate_replies_for_one_batch(self, app, manager, monkeypatch,
                                                echo_handler):
        chats = [9101, 9102, 9103]
        updates = [_update(600 + i, chat, '/start') for i, chat in enumerate(chats)]
        fake = FakeBale(updates, latency=0.05)
        fake.install(monkeypatch)

        with app.app_context():
            manager.start(app, 'FAKE:TOKEN')
            assert fake.wait_for(lambda: len(fake.sent) >= len(chats))
            time.sleep(0.6)          # فرصت برای تکرار احتمالی

        assert len(fake.sent) == len(chats), 'هر پیام دقیقاً یک پاسخ بگیرد'

    def test_per_chat_order_is_preserved(self, app, manager, monkeypatch, echo_handler):
        updates = [_update(700 + i, 9200, f'msg-{i}') for i in range(6)]
        updates += [_update(800 + i, 9201, f'other-{i}') for i in range(6)]
        fake = FakeBale(updates, latency=0.03)
        fake.install(monkeypatch)

        with app.app_context():
            manager.start(app, 'FAKE:TOKEN')
            assert fake.wait_for(lambda: len(fake.sent) >= len(updates))

        for chat in (9200, 9201):
            texts = [text for target, text in fake.sent if target == chat]
            assert texts == sorted(texts, key=lambda t: int(t.rsplit('-', 1)[1])), \
                f'ترتیب پیام‌های کاربر {chat} به هم ریخت: {texts}'


class TestThroughput:
    def test_users_are_served_concurrently(self, app, manager, monkeypatch, echo_handler):
        chats = list(range(9300, 9312))          # ۱۲ کاربر
        updates = [_update(900 + i, chat, '/start') for i, chat in enumerate(chats)]
        fake = FakeBale(updates, latency=0.15)   # هر ارسال ۱۵۰ms
        fake.install(monkeypatch)

        started = time.monotonic()
        with app.app_context():
            manager.start(app, 'FAKE:TOKEN')
            assert fake.wait_for(lambda: len(fake.sent) >= len(chats))
        elapsed = time.monotonic() - started

        serial_floor = len(chats) * 0.15         # اگر پشت‌سرهم بود
        assert len(fake.sent) == len(chats)
        assert elapsed < serial_floor * 0.75, \
            f'{len(chats)} پیام در {elapsed:.2f}s — موازی پردازش نشد (سری: {serial_floor:.2f}s)'

    def test_worker_count_is_configurable(self, monkeypatch):
        from utils.bot_services import BalePollingManager
        monkeypatch.setenv('ACADEMY_BALE_WORKERS', '5')
        assert BalePollingManager.worker_count() == 5
        monkeypatch.setenv('ACADEMY_BALE_WORKERS', 'not-a-number')
        assert BalePollingManager.worker_count() == BalePollingManager.DEFAULT_WORKERS
        monkeypatch.setenv('ACADEMY_BALE_WORKERS', '0')
        assert BalePollingManager.worker_count() == 1, 'حداقل یک کارگر'


class TestStatus:
    def test_status_reports_poller_health(self, app, manager, monkeypatch, echo_handler):
        fake = FakeBale([_update(950, 9400, '/start')])
        fake.install(monkeypatch)

        with app.app_context():
            manager.start(app, 'FAKE:TOKEN')
            assert fake.wait_for(lambda: manager.status()['processed'] >= 1)
            status = manager.status()

        for key in ('running', 'state', 'last_update_at', 'last_error', 'offset',
                    'workers', 'processed', 'failed', 'pending', 'avg_latency_ms'):
            assert key in status, f'کلید {key} در وضعیت poller نیست'
        assert status['running'] is True
        assert status['offset'] == 951
        assert status['pending'] == 0

    def test_stop_marks_poller_stopped(self, app, manager, monkeypatch, echo_handler):
        fake = FakeBale([])
        fake.install(monkeypatch)
        with app.app_context():
            manager.start(app, 'FAKE:TOKEN')
            assert fake.wait_for(lambda: manager.status()['running'])
        manager.stop()
        assert manager.status()['running'] is False


class TestSendHelpers:
    def test_send_message_returns_api_error_without_raising(self, monkeypatch):
        from utils.bot_services import send_bot_message
        fake = FakeBale([], blocked_chats={1})
        fake.install(monkeypatch)
        result = send_bot_message('bale', 'TOK', 1, 'سلام')
        assert result['ok'] is False
        assert 'blocked' in result['description']

    def test_send_document_missing_file(self):
        from utils.bot_services import send_bot_document
        result = send_bot_document('bale', 'TOK', 1, '/no/such/file.zip')
        assert result['ok'] is False


class TestBroadcastDoesNotBlockRequest:
    """پیام گروهی باید در پس‌زمینه برود؛ وگرنه روی هاست درخواست timeout می‌شود."""

    @pytest.fixture
    def logged_in(self, app):
        from extensions import db
        from models.user import Role, User, UserSession

        app.config['WTF_CSRF_ENABLED'] = False
        with app.app_context():
            role = Role.query.filter_by(is_admin=True).first()
            user = User(username='bcast_tester', full_name='آزمون ارسال گروهی',
                        role_id=role.id if role else None, is_admin=True)
            user.set_password('Bcast-Test-123!')
            db.session.add(user)
            db.session.commit()
            user_id = user.id

        client = app.test_client()
        response = client.post('/login', data={'username': 'bcast_tester',
                                               'password': 'Bcast-Test-123!'})
        assert response.status_code in (302, 303), 'ورود آزمونی باید موفق باشد'

        yield client

        with app.app_context():
            from models.bot import BotBroadcast, BotUser
            BotBroadcast.query.filter_by(created_by=user_id).delete(synchronize_session=False)
            BotUser.query.filter(BotUser.chat_id.between(97000, 97100)).delete(
                synchronize_session=False)
            UserSession.query.filter_by(user_id=user_id).delete(synchronize_session=False)
            row = db.session.get(User, user_id)
            if row is not None:
                db.session.delete(row)
            db.session.commit()

    def _make_recipients(self, app, count):
        from extensions import db
        from models.bot import BotUser
        from models.system import SystemSettings
        with app.app_context():
            for i in range(count):
                db.session.add(BotUser(chat_id=97000 + i, first_name=f'r{i}',
                                       provider='bale', is_verified=True))
            settings = SystemSettings.query.first()
            settings.bale_bot_token = 'FAKE:BROADCAST'
            db.session.commit()

    def test_post_returns_immediately_and_completes_in_background(
            self, app, logged_in, monkeypatch):
        from routes import bot_panel
        monkeypatch.setattr(bot_panel, 'BROADCAST_INTERVAL', 0)   # آزمون را کند نکند

        with app.app_context():
            from models.bot import BotUser
            preexisting = BotUser.query.filter_by(is_blocked=False).count()

        self._make_recipients(app, 8)
        fake = FakeBale([], latency=0.02)
        fake.install(monkeypatch)

        started = time.monotonic()
        response = logged_in.post('/bot-panel/broadcast', data={
            'message_text': 'سلام از آزمون', 'target_type': 'all',
            'provider': 'bale', 'title': 'آزمون'}, follow_redirects=False)
        elapsed = time.monotonic() - started

        assert response.status_code in (302, 303)
        assert elapsed < 0.5, f'درخواست ارسال گروهی {elapsed:.2f}s باز ماند (باید فوری برگردد)'

        from extensions import db
        from models.bot import BotBroadcast
        with app.app_context():
            record = BotBroadcast.query.order_by(BotBroadcast.id.desc()).first()
            broadcast_id = record.id
            assert record.total_recipients == preexisting + 8
            assert record.status == 'sending', 'ارسال باید در پس‌زمینه ادامه داشته باشد'

        deadline = time.monotonic() + 30
        with app.app_context():
            record = db.session.get(BotBroadcast, broadcast_id)
            while time.monotonic() < deadline and record.status != 'completed':
                db.session.refresh(record)
                time.sleep(0.05)
            assert record.status == 'completed'
            assert record.sent_count == record.total_recipients
            assert record.failed_count == 0

        mine = {chat for chat, _ in fake.sent if 97000 <= chat <= 97007}
        assert mine == set(range(97000, 97008))

    def test_bale_settings_page_renders_without_network(self, app, logged_in, monkeypatch):
        """صفحهٔ تنظیمات بله نباید برای getMe معطل شبکه بماند."""
        from utils.bot_services import clear_bot_info_cache
        clear_bot_info_cache()
        calls = {'n': 0}

        def fake_request(self, method, url, **kwargs):
            calls['n'] += 1
            if 'getMe' in url:
                return _Response({'ok': True, 'result': {'id': 1, 'username': 'testbot'}})
            return _Response({'ok': True})

        monkeypatch.setattr(requests.Session, 'request', fake_request)
        with app.app_context():
            from models.system import SystemSettings
            SystemSettings.query.first().bale_bot_token = 'FAKE:PAGE'
            from extensions import db
            db.session.commit()

        first = logged_in.get('/panel/bale')
        second = logged_in.get('/panel/bale')
        assert first.status_code == second.status_code == 200
        body = second.data.decode('utf-8')
        assert 'testbot' in body
        assert 'میانگین زمان پاسخ' in body
        assert calls['n'] == 1, f'getMe باید کش شود؛ {calls["n"]} بار صدا زده شد'


class TestRealSocketReuse:
    """مسیر واقعی HTTP روی سوکت واقعی — نه mock.

    monkeypatch فقط لایهٔ انتقال را تقلید می‌کند؛ این آزمون بررسی می‌کند که
    `requests.Session` واقعاً اتصال را نگه می‌دارد (keep-alive) و تایم‌اوت
    دو‌بخشی (اتصال، خواندن) روی سوکت واقعی کار می‌کند.
    """

    @pytest.fixture
    def local_api(self):
        import json as _json
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

        stats = {'requests': 0, 'connections': 0}

        class Handler(BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.1'
            timeout = 2                     # اتصال بی‌کارِ keep-alive بسته شود

            def log_message(self, *_args):
                pass

            def _send(self, payload):
                body = _json.dumps(payload).encode()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self):
                stats['requests'] += 1
                length = int(self.headers.get('Content-Length') or 0)
                self.rfile.read(length)
                if self.path.endswith('/getMe'):
                    return self._send({'ok': True, 'result': {'id': 7, 'username': 'realbot'}})
                return self._send({'ok': True, 'result': {'message_id': 1}})

            do_GET = do_POST

        class Server(ThreadingHTTPServer):
            daemon_threads = True

            def get_request(self):
                stats['connections'] += 1
                return super().get_request()

        server = Server(('127.0.0.1', 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            yield f'http://127.0.0.1:{server.server_address[1]}', stats
        finally:
            server.shutdown()
            server.server_close()

    def test_api_calls_share_one_tcp_connection(self, local_api, monkeypatch):
        from utils import bot_services
        base_url, stats = local_api
        monkeypatch.setattr(bot_services, '_base_url', lambda provider: base_url)
        bot_services.clear_bot_info_cache()

        assert bot_services.send_bot_message('bale', 'TOK', 42, 'سلام')['ok'] is True
        assert bot_services.get_bot_info('bale', 'TOK') == {'id': 7, 'username': 'realbot'}
        assert bot_services.get_bot_info('bale', 'TOK') == {'id': 7, 'username': 'realbot'}

        assert stats['requests'] == 2, 'getMe دوم باید از کش بیاید'
        assert stats['connections'] == 1, \
            f'هر فراخوانی اتصال تازه ساخت ({stats["connections"]} اتصال) — pool کار نمی‌کند'
