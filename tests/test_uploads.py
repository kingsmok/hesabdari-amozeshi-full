"""آزمون‌های `utils/uploads.py` — گارد مشترک پذیرش فایل اَپلودی

پیش از این، سه نقطهٔ اَپلود (فاکتور هزینهٔ حقوق، ورود بستهٔ پشتیبان، بستهٔ
به‌روزرسانی) هرکدام بخشی از کار را می‌کردند: یکی پسوند را چک می‌کرد ولی سقف حجم
نداشت، یکی `file.save()` بی‌قید و شرط داشت و نام ثابت `package.zip` می‌گذاشت.
این فایل هم منطق مشترک و هم «دیگر هیچ مسیری allowlist محلی ندارد» را قفل می‌کند.
"""
import io
import os
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from utils.uploads import (          # noqa: E402
    ALLOWED_EXT, MAX_SIZE, UnsafeUpload, store_upload,
)

# PNG واقعی (امضا + دادهٔ بی‌ربط) و PDF کوچک
PNG = b'\x89PNG\r\n\x1a\n' + b'\x00' * 48
PDF = b'%PDF-1.4\n' + b'%\n' + b'\x00' * 40
ZIP = b'PK\x03\x04' + b'\x00' * 60


def _fs(filename, blob):
    """FileStorage واقعی (با stream) — همان چیزی که Flask می‌دهد."""
    from werkzeug.datastructures import FileStorage
    return FileStorage(stream=io.BytesIO(blob), filename=filename)


class _StubUpload:
    """فقط `save()` دارد، مثل کدهای قدیمی/استاب‌های تست."""

    def __init__(self, filename, blob):
        self.filename = filename
        self._blob = blob

    def save(self, destination):
        with open(destination, 'wb') as handle:
            handle.write(self._blob)


class TestAllowedExtensions:
    def test_png_is_stored_with_generated_name(self, tmp_path):
        name = store_upload(_fs('فاکتور من.png', PNG), str(tmp_path), kind='expense')
        assert name.endswith('.png') and len(name) > len('.png') + 16
        assert (tmp_path / name).read_bytes().startswith(b'\x89PNG')

    def test_prefix_is_kept_and_uuid_adds_entropy(self, tmp_path):
        first = store_upload(_fs('a.pdf', PDF), str(tmp_path), kind='expense', prefix='inv-')
        second = store_upload(_fs('a.pdf', PDF), str(tmp_path), kind='expense', prefix='inv-')
        assert first.startswith('inv-') and second.startswith('inv-')
        assert first != second, 'دو فایل هم‌نام نباید همدیگر را پوشانده شوند'

    @pytest.mark.parametrize('kind', sorted(ALLOWED_EXT))
    def test_every_kind_has_a_size_cap(self, kind):
        assert MAX_SIZE[kind] > 0

    def test_disallowed_extension_rejected(self, tmp_path):
        with pytest.raises(UnsafeUpload, match='پسوند'):
            store_upload(_fs('shell.php', PNG), str(tmp_path), kind='expense')

    def test_svg_rejected_for_expense(self, tmp_path):
        """SVG می‌تواند اسکریپت داشته باشد؛ اگر یک‌جا render شود خطرناک است."""
        with pytest.raises(UnsafeUpload, match='پسوند'):
            store_upload(_fs('logo.svg', b'<svg xmlns="http://www.w3.org/2000/svg"></svg>'),
                         str(tmp_path), kind='expense')

    def test_double_extension_uses_the_last_one(self, tmp_path):
        with pytest.raises(UnsafeUpload, match='پسوند'):
            store_upload(_fs('x.png.php', PNG), str(tmp_path), kind='expense')
        with pytest.raises(UnsafeUpload, match='پسوند'):
            store_upload(_fs('x.php.png', PNG), str(tmp_path), kind='backup')


class TestPathSafety:
    def test_user_filename_never_reaches_the_disk_path(self, tmp_path):
        for hostile in ('../../evil.png', '..\\..\\evil.png', 'a;b.png', '/etc/passwd.png'):
            name = store_upload(_fs(hostile, PNG), str(tmp_path), kind='expense')
            assert os.sep not in name and '/' not in name and '..' not in name
            assert (tmp_path / name).is_file()
        assert len(list(tmp_path.iterdir())) == 4

    def test_folder_is_created_if_missing(self, tmp_path):
        target = tmp_path / 'deep' / 'nested'
        name = store_upload(_fs('a.png', PNG), str(target), kind='expense')
        assert (target / name).is_file()


class TestContentSniffing:
    def test_spoofed_png_rejected(self, tmp_path):
        with pytest.raises(UnsafeUpload, match='هم‌خوانی'):
            store_upload(_fs('evil.png', b'<html><body>hi</body></html>' * 8),
                         str(tmp_path), kind='expense')
        assert list(tmp_path.iterdir()) == [], 'فایل مردود نباید روی دیسک بماند'

    def test_zip_signature_required_for_package(self, tmp_path):
        with pytest.raises(UnsafeUpload, match='هم‌خوانی'):
            store_upload(_fs('notes.zip', b'not a zip at all' * 4), str(tmp_path), kind='package')
        assert store_upload(_fs('ok.zip', ZIP), str(tmp_path), kind='package')

    def test_webp_checked_after_riff_header(self, tmp_path):
        bogus = b'RIFF\x00\x00\x00\x00AWVE' + b'\x00' * 24
        with pytest.raises(UnsafeUpload, match='هم‌خوانی'):
            store_upload(_fs('x.webp', bogus), str(tmp_path), kind='expense')
        good = b'RIFF\x00\x00\x00\x00WEBP' + b'\x00' * 24
        assert store_upload(_fs('x.webp', good), str(tmp_path), kind='expense')


class TestSizeLimits:
    def test_oversize_rejected_while_streaming(self, tmp_path, monkeypatch):
        monkeypatch.setitem(MAX_SIZE, 'expense', 1024)
        with pytest.raises(UnsafeUpload, match='حجم'):
            store_upload(_fs('big.png', PNG + b'\x00' * 40_000), str(tmp_path), kind='expense')
        assert list(tmp_path.iterdir()) == []

    def test_stub_upload_path_enforces_the_same_limits(self, tmp_path, monkeypatch):
        """مسیر `save()`-only هم باید همان سه کنترل را داشته باشد."""
        monkeypatch.setitem(MAX_SIZE, 'expense', 1024)
        with pytest.raises(UnsafeUpload, match='حجم'):
            store_upload(_StubUpload('big.png', PNG + b'\x00' * 40_000),
                         str(tmp_path), kind='expense')
        assert list(tmp_path.iterdir()) == []
        with pytest.raises(UnsafeUpload, match='پسوند'):
            store_upload(_StubUpload('a.txt', b'x' * 10), str(tmp_path), kind='expense')
        with pytest.raises(UnsafeUpload, match='هم‌خوانی'):
            store_upload(_StubUpload('a.png', b'html' * 10), str(tmp_path), kind='expense')
        assert store_upload(_StubUpload('ok.png', PNG), str(tmp_path), kind='expense')


class TestEmptyAndMissing:
    def test_none_rejected(self, tmp_path):
        with pytest.raises(UnsafeUpload, match='انتخاب نشده'):
            store_upload(None, str(tmp_path), kind='expense')

    def test_blank_filename_rejected(self, tmp_path):
        with pytest.raises(UnsafeUpload, match='انتخاب نشده'):
            store_upload(_fs('', PNG), str(tmp_path), kind='expense')

    def test_empty_file_rejected(self, tmp_path):
        with pytest.raises(UnsafeUpload, match='خالی'):
            store_upload(_fs('a.png', b''), str(tmp_path), kind='expense')


class TestCallersUseTheSharedGate:
    """رجرسون: هیچ مسیر آپلودی نباید دوباره allowlist محلی بسازد."""

    FILES = {
        'routes/payroll.py': ('ALLOWED_EXPENSE_EXTENSIONS',),
        'routes/license.py': ("endswith('.zip')",),
        'utils/backup_service.py': ("endswith('.zip')",),
    }

    @pytest.mark.parametrize('rel,forbidden', sorted(FILES.items()))
    def test_no_inline_allowlist_left(self, rel, forbidden):
        with open(os.path.join(REPO_ROOT, rel), encoding='utf-8') as handle:
            source = handle.read()
        for needle in forbidden:
            for number, line in enumerate(source.splitlines(), 1):
                stripped = line.strip()
                if stripped.startswith('#'):
                    continue
                assert needle not in line, f'{rel}:{number} هنوز {needle} دارد'

    ACCEPTING = ('store_upload', 'import_backup')   # import_backup خودش به گارد می‌رسد

    def test_every_upload_site_goes_through_store_upload(self):
        """هر `request.files.get(...)` باید به `store_upload` برسد (مستقیم یا از
        راه `backup_service.import_backup`)؛ وگرنه گارد دور زده شده است."""
        roots = [os.path.join(REPO_ROOT, 'routes'), os.path.join(REPO_ROOT, 'utils')]
        sites = []
        for root in roots:
            for name in sorted(os.listdir(root)):
                if not name.endswith('.py'):
                    continue
                path = os.path.join(root, name)
                with open(path, encoding='utf-8') as handle:
                    lines = handle.read().splitlines()
                for number, line in enumerate(lines, 1):
                    if 'request.files.get(' not in line or line.strip().startswith('#'):
                        continue
                    window = '\n'.join(lines[number - 1:number + 14])
                    sites.append((name, number, any(tok in window for tok in self.ACCEPTING)))
        assert sites, 'هیچ نقطهٔ آپلودی پیدا نشد؟'
        unguarded = [f'{name}:{line}' for name, line, ok in sites if not ok]
        assert not unguarded, f'بدون گارد مشترک: {unguarded}'


# ══════════════════════════════════════════════════════════════
#  مسیر واقعی: فاکتور هزینهٔ حقوق باید از همین گارد رد شود
# ══════════════════════════════════════════════════════════════
@pytest.fixture(scope='module')
def live_app():
    os.environ.setdefault('ACADEMY_DISABLE_SCHEDULER', '1')
    from app import create_app
    application = create_app()
    application.config['TESTING'] = True
    application.config['WTF_CSRF_ENABLED'] = False
    return application


@pytest.fixture(scope='module', autouse=True)
def _licensed(live_app):
    """بدون وضعیت لایسنس معتبر، مسیرهای پولی redirect می‌شوند و آزمون بی‌معنی است."""
    import license_client
    from license_features import AVAILABLE_FEATURES

    data = {'success': True, 'status': 'SUCCESS',
            'allowed_features': {item['key']: True for item in AVAILABLE_FEATURES}}
    original = license_client.refresh_state

    def _fake(*_a, **_k):
        return license_client._store_state(license_client.LicenseState(
            status='SUCCESS', message='', data=data, valid=True, source='online'))

    license_client.refresh_state = _fake
    _fake()
    yield
    license_client.refresh_state = original
    license_client._store_state(None)


@pytest.fixture(scope='module')
def live_client(live_app):
    """حساب مدیر کل — در نبودش ساخته و در پایان پاک می‌شود (ایزولیشن کامل)."""
    from extensions import db
    from models.user import ActivityLog, Role, User

    created_id = None
    with live_app.app_context():
        admin = User.query.filter_by(is_admin=True, is_active=True).first()
        admin_id = admin.id if admin else None
        if admin_id is None:
            role = Role.query.filter_by(is_admin=True).first() or Role.query.first()
            created = User(username='test_upload_admin', full_name='مدیر آزمون آپلود',
                           is_admin=True, is_active=True,
                           role_id=role.id if role else None)
            created.set_password('Test-Only-Strong-123!')
            db.session.add(created)
            db.session.commit()
            admin_id = created.id
            created_id = created.id

    http = live_app.test_client()
    with http.session_transaction() as sess:
        sess['_user_id'] = str(admin_id)
        sess['_fresh'] = True
    yield http

    if created_id is not None:
        with live_app.app_context():
            row = db.session.get(User, created_id)
            if row is not None:
                ActivityLog.query.filter_by(user_id=created_id).delete(synchronize_session=False)
                db.session.delete(row)
                db.session.commit()


class TestPayrollAttachmentRoute:
    UPLOADS = os.path.join(REPO_ROOT, 'static', 'uploads', 'expenses')

    def _post(self, client, blob, filename='invoice.png'):
        from io import BytesIO
        with client.application.app_context():
            from extensions import db
            from models.finance import ExpenseCategory
            category = ExpenseCategory.query.filter_by(is_active=True).first()
            if category is None:
                category = ExpenseCategory(name='دسته آزمونی آپلود', code='UPLD')
                db.session.add(category)
                db.session.commit()
            category_id = category.id
        return client.post('/expenses/advanced/add', data={
            'category_id': str(category_id), 'amount': '1500000',
            'description': 'آزمون گارد آپلود', 'payment_method': 'cash',
            'attachment': (BytesIO(blob), filename),
        }, content_type='multipart/form-data')

    def _list_dir(self):
        return set(os.listdir(self.UPLOADS)) if os.path.isdir(self.UPLOADS) else set()

    def test_spoofed_invoice_is_refused_and_nothing_hits_the_disk(self, live_client):
        before = self._list_dir()
        resp = self._post(live_client, b'<html><script>alert(1)</script></html>')
        assert resp.status_code == 400
        assert 'هم‌خوانی ندارد' in resp.get_data(as_text=True) or \
            'پذیرفته نشد' in resp.get_data(as_text=True)
        assert self._list_dir() == before, 'فایل مردود نباید روی دیسک بماند'

    def test_real_invoice_is_stored_with_generated_name(self, live_app, live_client):
        """پذیرش فاکتور واقعی: یک فایل با نام uuid، و پاک‌سازی کامل در پایان."""
        from extensions import db
        from models.finance import Expense
        before = self._list_dir()
        resp = self._post(live_client, PNG)
        assert resp.status_code in (200, 302), resp.status_code
        created = []
        with live_app.app_context():
            row = Expense.query.filter(Expense.attachment.isnot(None),
                                      Expense.attachment.like('%/expenses/%')) \
                .order_by(Expense.id.desc()).first()
            if row is not None:
                created.append((row.id, row.attachment))
        assert created, 'فاکتور ذخیره نشد'
        expense_id, attachment = created[0]
        try:
            new_files = self._list_dir() - before
            assert len(new_files) == 1, f'دقیقاً یک فایل انتظار است: {new_files}'
            stored = next(iter(new_files))
            assert attachment.replace('\\', '/').endswith(stored)
            assert not stored.startswith('invoice'), 'نام کاربر نباید در مسیر بنشیند'
        finally:
            with live_app.app_context():
                row = db.session.get(Expense, expense_id)
                if row is not None:
                    db.session.delete(row)
                    db.session.commit()
            path = os.path.join(self.UPLOADS, stored)
            if os.path.isfile(path):
                os.remove(path)
