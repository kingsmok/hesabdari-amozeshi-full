"""
آزمون‌های مرکز پشتیبان‌گیری/بازیابی، نصب دستی بسته به‌روزرسانی و
سازگاری پاسخ سرور واقعی.

اجرا:
    pytest tests/test_backup.py -q
"""
import io
import json
import os
import sqlite3
import sys
import time
import types
import zipfile

import pytest
from flask import Flask

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import license_client                                   # noqa: E402
import license_updater                                  # noqa: E402
from extensions import db                               # noqa: E402
from utils import backup_service                        # noqa: E402
from utils.backup_service import BackupError            # noqa: E402


# ══════════════════════════════════════════════════════════════
#  محیط ایزوله: دیتابیس، پوشه پشتیبان و پوشه آپلود موقت
# ══════════════════════════════════════════════════════════════
@pytest.fixture(autouse=True)
def licensed_state():
    """
    آزمون‌ها نباید به سرور لایسنس وصل شوند؛ یک وضعیت معتبر فقط در حافظه
    تزریق می‌شود تا کنترل‌های عمقی (assert_feature) واقعی اجرا شوند.
    """
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


@pytest.fixture()
def app(tmp_path):
    application = Flask(__name__, root_path=str(tmp_path))
    application.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{tmp_path / 'academy.db'}"
    application.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    application.config['BACKUP_FOLDER'] = str(tmp_path / 'backups')
    application.config['UPLOAD_FOLDER'] = str(tmp_path / 'uploads')
    db.init_app(application)

    with application.app_context():
        db.session.execute(db.text('CREATE TABLE demo (id INTEGER PRIMARY KEY, name TEXT)'))
        db.session.execute(db.text("INSERT INTO demo (name) VALUES ('نسخه اول')"))
        db.session.commit()
        os.makedirs(application.config['UPLOAD_FOLDER'], exist_ok=True)
        with open(os.path.join(application.config['UPLOAD_FOLDER'], 'photo.txt'), 'w',
                  encoding='utf-8') as handle:
            handle.write('عکس هنرجو')
        yield application
        db.session.remove()
        db.engine.dispose()


def _row_count(name_filter=None):
    rows = db.session.execute(db.text('SELECT name FROM demo')).fetchall()
    return [row[0] for row in rows]


# ══════════════════════════════════════════════════════════════
#  ۱) ساخت بسته پشتیبان
# ══════════════════════════════════════════════════════════════
class TestCreateBackup:
    def test_full_backup_contains_database_uploads_and_manifest(self, app):
        info = backup_service.create_backup(kind='full', note='آزمون')
        path = backup_service.safe_backup_path(info['name'])
        assert os.path.isfile(path)

        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            manifest = json.loads(archive.read('manifest.json').decode('utf-8'))
        assert 'database/academy.db' in names
        assert 'uploads/photo.txt' in names
        assert manifest['kind'] == 'full'
        assert manifest['note'] == 'آزمون'
        assert len(manifest['database_sha256']) == 64
        assert manifest['uploads_count'] == 1

    def test_database_only_backup_skips_uploads(self, app):
        info = backup_service.create_backup(kind='database')
        with zipfile.ZipFile(backup_service.safe_backup_path(info['name'])) as archive:
            names = archive.namelist()
        assert 'database/academy.db' in names
        assert not [item for item in names if item.startswith('uploads/')]

    def test_listing_and_stats(self, app):
        backup_service.create_backup(kind='database')
        backup_service.create_backup(kind='database')
        items = backup_service.list_backups()
        stats = backup_service.backup_stats()
        assert len(items) == 2
        assert stats['count'] == 2
        assert stats['total_mb'] >= 0
        assert stats['latest']['name'] == items[0]['name']


# ══════════════════════════════════════════════════════════════
#  ۲) بازیابی
# ══════════════════════════════════════════════════════════════
class TestRestore:
    def test_restore_brings_back_previous_data(self, app):
        info = backup_service.create_backup(kind='full')

        db.session.execute(db.text("UPDATE demo SET name='نسخه دوم'"))
        db.session.commit()
        assert _row_count() == ['نسخه دوم']

        result = backup_service.restore_backup(info['name'])
        assert result['safety_backup'].startswith('safety_')
        assert _row_count() == ['نسخه اول']

    def test_restore_recovers_deleted_upload(self, app):
        info = backup_service.create_backup(kind='full')
        os.remove(os.path.join(app.config['UPLOAD_FOLDER'], 'photo.txt'))

        result = backup_service.restore_backup(info['name'], restore_uploads=True)
        assert result['restored_uploads'] == 1
        assert os.path.isfile(os.path.join(app.config['UPLOAD_FOLDER'], 'photo.txt'))

    def test_safety_backup_is_created_before_restore(self, app):
        info = backup_service.create_backup(kind='database')
        backup_service.restore_backup(info['name'])
        safety = [item for item in backup_service.list_backups() if item['is_safety']]
        assert len(safety) == 1

    def test_tampered_database_is_rejected(self, app):
        info = backup_service.create_backup(kind='database')
        path = backup_service.safe_backup_path(info['name'])

        # دستکاری محتوای دیتابیس داخل بسته، با نگه‌داشتن همان manifest
        with zipfile.ZipFile(path) as archive:
            payload = {name: archive.read(name) for name in archive.namelist()}
        payload['database/academy.db'] = b'NOT-A-DATABASE'
        with zipfile.ZipFile(path, 'w') as archive:
            for name, blob in payload.items():
                archive.writestr(name, blob)

        with pytest.raises(BackupError) as error:
            backup_service.restore_backup(info['name'])
        assert 'هش' in str(error.value)
        assert _row_count() == ['نسخه اول']          # دیتابیس دست‌نخورده مانده است

    def test_corrupt_database_without_hash_is_rejected(self, app):
        info = backup_service.create_backup(kind='database')
        path = backup_service.safe_backup_path(info['name'])
        with zipfile.ZipFile(path) as archive:
            payload = {name: archive.read(name) for name in archive.namelist()}
        manifest = json.loads(payload['manifest.json'].decode('utf-8'))
        manifest.pop('database_sha256')
        payload['manifest.json'] = json.dumps(manifest).encode('utf-8')
        payload['database/academy.db'] = b'NOT-A-DATABASE'
        with zipfile.ZipFile(path, 'w') as archive:
            for name, blob in payload.items():
                archive.writestr(name, blob)

        with pytest.raises(BackupError):
            backup_service.restore_backup(info['name'])
        assert _row_count() == ['نسخه اول']

    def test_zip_slip_member_is_rejected(self, app):
        folder = backup_service.backup_folder()
        evil = os.path.join(folder, 'backup_evil.zip')
        source = backup_service.create_backup(kind='database')
        with zipfile.ZipFile(backup_service.safe_backup_path(source['name'])) as archive:
            payload = {name: archive.read(name) for name in archive.namelist()}
        with zipfile.ZipFile(evil, 'w') as archive:
            for name, blob in payload.items():
                archive.writestr(name, blob)
            archive.writestr('../../evil.txt', 'boom')

        with pytest.raises(BackupError) as error:
            backup_service.restore_backup('backup_evil.zip')
        assert 'خطرناک' in str(error.value)

    def test_path_traversal_name_is_rejected(self, app):
        assert backup_service.safe_backup_path('../../etc/passwd.zip') is None
        assert backup_service.safe_backup_path('report.txt') is None
        with pytest.raises(BackupError):
            backup_service.restore_backup('../../etc/passwd.zip')


# ══════════════════════════════════════════════════════════════
#  ۳) ورود بسته از فایل کاربر، حذف و نگهداری
# ══════════════════════════════════════════════════════════════
class _Upload:
    """جایگزین ساده‌ی FileStorage"""

    def __init__(self, filename, blob):
        self.filename = filename
        self._blob = blob

    def save(self, destination):
        with open(destination, 'wb') as handle:
            handle.write(self._blob)


class TestImportAndRetention:
    def test_import_valid_package(self, app):
        info = backup_service.create_backup(kind='database')
        with open(backup_service.safe_backup_path(info['name']), 'rb') as handle:
            blob = handle.read()
        backup_service.delete_backup(info['name'])

        imported = backup_service.import_backup(_Upload('mybackup.zip', blob))
        assert imported['name'].startswith('backup_imported_')
        assert imported['kind'] == 'database'
        assert len(backup_service.list_backups()) == 1

    def test_import_rejects_non_zip(self, app):
        with pytest.raises(BackupError):
            backup_service.import_backup(_Upload('notes.txt', b'hello'))

    def test_import_rejects_unrelated_zip(self, app):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w') as archive:
            archive.writestr('readme.txt', 'hello')
        with pytest.raises(BackupError):
            backup_service.import_backup(_Upload('other.zip', buffer.getvalue()))
        assert backup_service.list_backups() == []      # فایل نامعتبر باقی نمی‌ماند

    def test_delete_backup(self, app):
        info = backup_service.create_backup(kind='database')
        backup_service.delete_backup(info['name'])
        assert backup_service.list_backups() == []
        with pytest.raises(BackupError):
            backup_service.delete_backup(info['name'])

    def test_prune_keeps_newest_and_never_deletes_safety(self, app):
        names = []
        for index in range(4):
            info = backup_service.create_backup(kind='database', note=str(index))
            # نام‌ها بر اساس زمان مرتب می‌شوند؛ برای قطعیت، دستی تغییر نام می‌دهیم
            folder = backup_service.backup_folder()
            new_name = f'backup_database_2024010{index}_000000.zip'
            os.rename(os.path.join(folder, info['name']), os.path.join(folder, new_name))
            names.append(new_name)
        safety = backup_service.create_backup(kind='database', prefix='safety_')

        removed = backup_service.prune_backups(2)
        remaining = {item['name'] for item in backup_service.list_backups()}
        assert removed == 2
        assert names[-1] in remaining and names[-2] in remaining
        assert names[0] not in remaining
        assert safety['name'] in remaining


# ══════════════════════════════════════════════════════════════
#  ۴) نصب دستی بسته به‌روزرسانی (ZIP)
# ══════════════════════════════════════════════════════════════
def _make_package(folder, files, name='package.zip'):
    path = os.path.join(folder, name)
    with zipfile.ZipFile(path, 'w') as archive:
        for entry, content in files.items():
            archive.writestr(entry, content)
    return path


class TestLocalUpdatePackage:
    def test_inspect_reads_version_and_hash(self, tmp_path):
        path = _make_package(str(tmp_path), {
            'VERSION': '1.0.5\n',
            'routes/demo.py': 'print(1)\n',
        })
        report = license_updater.inspect_local_package(path)
        assert report['latest_version'] == '1.0.5'
        assert report['files'] == 2
        assert len(report['sha256']) == 64
        assert report['apply_mode'] == 'full'

    def test_inspect_reads_update_json(self, tmp_path):
        path = _make_package(str(tmp_path), {
            'update.json': json.dumps({'latest_version': '2.0.0',
                                       'release_notes': 'رفع اشکال'}),
            'routes/demo.py': 'x = 1\n',
        })
        report = license_updater.inspect_local_package(path)
        assert report['latest_version'] == '2.0.0'
        assert report['release_notes'] == 'رفع اشکال'

    def test_non_zip_is_rejected(self, tmp_path):
        path = os.path.join(str(tmp_path), 'fake.zip')
        with open(path, 'wb') as handle:
            handle.write(b'not a zip')
        with pytest.raises(RuntimeError):
            license_updater.inspect_local_package(path)

    def test_zip_slip_is_rejected(self, tmp_path):
        path = _make_package(str(tmp_path), {'../evil.py': 'boom'})
        with pytest.raises(RuntimeError) as error:
            license_updater.inspect_local_package(path)
        assert 'خطرناک' in str(error.value)

    def test_wrong_sha256_blocks_install(self, tmp_path, monkeypatch):
        root = tmp_path / 'app'
        root.mkdir()
        monkeypatch.setattr(license_updater, 'app_root', lambda: str(root))
        path = _make_package(str(tmp_path), {'routes/demo.py': 'x = 1\n'})
        with pytest.raises(RuntimeError) as error:
            license_updater.apply_local_package(path, expected_sha256='0' * 64,
                                                make_backup=False)
        assert 'هش' in str(error.value)
        assert not os.path.exists(root / 'routes' / 'demo.py')

    def test_install_writes_files_and_version_but_keeps_customer_data(self, tmp_path, monkeypatch):
        root = tmp_path / 'app'
        (root / 'instance').mkdir(parents=True)
        (root / 'routes').mkdir()
        (root / 'instance' / 'academy.db').write_text('DATA', encoding='utf-8')
        (root / 'settings.json').write_text('{"secret": 1}', encoding='utf-8')
        (root / 'routes' / 'demo.py').write_text('old = True\n', encoding='utf-8')
        (root / 'VERSION').write_text('1.0.1\n', encoding='utf-8')
        monkeypatch.setattr(license_updater, 'app_root', lambda: str(root))

        path = _make_package(str(tmp_path), {
            'VERSION': '1.0.2\n',
            'routes/demo.py': 'old = False\n',
            'instance/academy.db': 'HACKED',
            'settings.json': '{"secret": 999}',
        })
        result = license_updater.apply_local_package(path, make_backup=False)

        assert result['status'] == 'UPDATED'
        assert result['latest_version'] == '1.0.2'
        assert (root / 'routes' / 'demo.py').read_text(encoding='utf-8') == 'old = False\n'
        assert (root / 'VERSION').read_text(encoding='utf-8').strip() == '1.0.2'
        # داده‌های مشتری هرگز بازنویسی نمی‌شوند
        assert (root / 'instance' / 'academy.db').read_text(encoding='utf-8') == 'DATA'
        assert (root / 'settings.json').read_text(encoding='utf-8') == '{"secret": 1}'

    def test_manifest_mode_only_touches_listed_files(self, tmp_path, monkeypatch):
        root = tmp_path / 'app'
        (root / 'routes').mkdir(parents=True)
        (root / 'routes' / 'a.py').write_text('a = 1\n', encoding='utf-8')
        (root / 'routes' / 'b.py').write_text('b = 1\n', encoding='utf-8')
        monkeypatch.setattr(license_updater, 'app_root', lambda: str(root))

        path = _make_package(str(tmp_path), {
            'manifest.json': json.dumps({'files': ['routes/a.py']}),
            'routes/a.py': 'a = 2\n',
            'routes/b.py': 'b = 2\n',
        })
        license_updater.apply_local_package(path, version='1.0.3', make_backup=False)
        assert (root / 'routes' / 'a.py').read_text(encoding='utf-8') == 'a = 2\n'
        assert (root / 'routes' / 'b.py').read_text(encoding='utf-8') == 'b = 1\n'


# ══════════════════════════════════════════════════════════════
#  ۵) سازگاری با نام‌گذاری‌های سرور واقعی
# ══════════════════════════════════════════════════════════════
class TestServerCompatibility:
    def test_status_aliases_map_to_internal_vocabulary(self):
        normalize = license_client.normalize_server_data
        assert normalize({'status': 'valid'})['status'] == 'SUCCESS'
        assert normalize({'status': 'ACTIVE'})['status'] == 'SUCCESS'
        assert normalize({'status': 'ok'})['status'] == 'SUCCESS'
        assert normalize({'status': 'not_found'})['status'] == 'INVALID_KEY'
        assert normalize({'status': 'suspended'})['status'] == 'INACTIVE'
        assert normalize({'status': 'max_devices'})['status'] == 'ACTIVATION_LIMIT_REACHED'
        assert normalize({'status': 'device_not_activated'})['status'] == 'NOT_ACTIVATED'

    def test_rejected_statuses_stay_rejected(self):
        normalize = license_client.normalize_server_data
        for raw in ('revoked', 'license_expired', 'hardware_mismatch', 'wrong_product'):
            assert normalize({'status': raw})['status'] in license_client.REJECT_STATUSES

    def test_feature_list_becomes_dictionary(self):
        data = license_client.normalize_server_data({
            'status': 'valid',
            'features': ['students', 'finance'],
        })
        assert data['allowed_features'] == {'students': True, 'finance': True}
        state = license_client.LicenseState('SUCCESS', '', data=data, valid=True)
        assert state.has_feature('students') is True
        assert state.has_feature('payroll') is False       # پیش‌فرض بسته

    def test_feature_dict_with_string_flags(self):
        data = license_client.normalize_server_data({
            'allowed_features': {'students': 'yes', 'exams': 'no', 'finance': 1},
        })
        assert data['allowed_features'] == {'students': True, 'exams': False, 'finance': True}

    def test_field_aliases(self):
        data = license_client.normalize_server_data({
            'status': 'VALID',
            'customer_name': 'آموزشگاه نمونه',
            'expiry_date': '2027-01-01T00:00:00Z',
            'max_devices': 3,
            'trial': 'true',
            'grace_hours': 48,
            'recheck_minutes': 120,
        })
        state = license_client.LicenseState('SUCCESS', '', data=data, valid=True)
        assert state.client_name == 'آموزشگاه نمونه'
        assert state.expires_at.startswith('2027-01-01')
        assert state.max_activations == 3
        assert state.is_trial is True
        assert state.offline_grace_hours == 48
        assert state.revalidate_minutes == 120

    def test_existing_field_names_win_over_aliases(self):
        data = license_client.normalize_server_data({
            'allowed_features': {'students': True},
            'features': ['payroll'],
        })
        assert data['allowed_features'] == {'students': True}

    def test_success_flag_is_derived_from_status_when_missing(self):
        assert license_client.normalize_server_data({'status': 'ACTIVE'})['success'] is True
        assert license_client.normalize_server_data({'status': 'EXPIRED'})['success'] is False
        assert license_client.normalize_server_data({'success': 'true'})['status'] == 'SUCCESS'

    def test_unknown_status_is_left_untouched(self):
        data = license_client.normalize_server_data({'status': 'SOMETHING_NEW'})
        assert data['status'] == 'SOMETHING_NEW'
        assert data['success'] is False


# ══════════════════════════════════════════════════════════════
#  ۶) پشتیبان خودکار بر اساس تنظیمات
# ══════════════════════════════════════════════════════════════
class TestScheduledBackup:
    @staticmethod
    def _fake_settings_module(monkeypatch, **attributes):
        """جایگزینی موقت models.system تا تنظیمات دلخواه خوانده شود."""
        module = types.ModuleType('models.system')
        settings = type('SystemSettingsRow', (), attributes)()
        module.SystemSettings = type(
            'SystemSettings', (),
            {'query': type('Query', (), {'first': staticmethod(lambda: settings)})()},
        )
        monkeypatch.setitem(sys.modules, 'models.system', module)

    def test_disabled_when_settings_off(self, app, monkeypatch):
        self._fake_settings_module(monkeypatch, auto_backup=False,
                                   backup_interval_hours=24, max_backups=10)
        assert 'غیرفعال' in backup_service.run_scheduled_backup()
        assert backup_service.list_backups() == []

    def test_creates_backup_when_due(self, app, monkeypatch):
        self._fake_settings_module(monkeypatch, auto_backup=True,
                                   backup_interval_hours=24, max_backups=10)
        message = backup_service.run_scheduled_backup()
        assert 'ساخته شد' in message
        assert len(backup_service.list_backups()) == 1

        # بلافاصله دوباره اجرا شود → نباید بسته جدیدی بسازد
        assert 'نرسیده' in backup_service.run_scheduled_backup()
        assert len(backup_service.list_backups()) == 1

    def test_respects_max_backups(self, app, monkeypatch):
        self._fake_settings_module(monkeypatch, auto_backup=True,
                                   backup_interval_hours=1, max_backups=2)
        folder = backup_service.backup_folder()
        for _ in range(4):
            backup_service.run_scheduled_backup()
            # کهنه کردن مصنوعی زمان فایل‌ها تا اجرای بعدی «سررسید» شود
            old_time = time.time() - 10 * 3600
            for item in os.listdir(folder):
                os.utime(os.path.join(folder, item), (old_time, old_time))
        assert len(backup_service.list_backups()) == 2


# ══════════════════════════════════════════════════════════════
#  ۷) ارسال بسته پشتیبان به ربات بله
# ══════════════════════════════════════════════════════════════
class _Settings:
    academy_name = 'آموزشگاه نمونه'
    bale_bot_token = 'TOKEN-123'
    backup_bot_enabled = True
    backup_bot_chat_id = '111, 222'
    backup_bot_max_mb = 45
    backup_bot_kind = 'database'
    auto_backup = False
    backup_interval_hours = 24
    max_backups = 10


class TestBotDelivery:
    @staticmethod
    def _patch_settings(monkeypatch, **overrides):
        settings = _Settings()
        for key, value in overrides.items():
            setattr(settings, key, value)
        monkeypatch.setattr(backup_service, '_settings_row', lambda: settings)
        return settings

    @staticmethod
    def _capture_sender(monkeypatch, ok=True, description=''):
        calls = []

        def _fake_send(provider, token, chat_id, file_path, caption='', filename=None,
                       timeout=180):
            calls.append({'provider': provider, 'token': token, 'chat_id': chat_id,
                          'file_path': file_path, 'caption': caption,
                          'filename': filename})
            return {'ok': ok, 'description': description}

        module = types.ModuleType('utils.bot_services')
        module.send_bot_document = _fake_send
        monkeypatch.setitem(sys.modules, 'utils.bot_services', module)
        return calls

    def test_targets_come_from_settings_and_bot_admins(self, app, monkeypatch):
        self._patch_settings(monkeypatch)
        monkeypatch.setattr(backup_service, 'BotUser', None, raising=False)
        targets = backup_service.bot_targets()
        assert targets == ['111', '222']          # جدول ربات در این آزمون خالی است

    def test_send_uses_bale_endpoint_with_caption(self, app, monkeypatch):
        self._patch_settings(monkeypatch)
        calls = self._capture_sender(monkeypatch)
        info = backup_service.create_backup(kind='database', note='ارسال آزمایشی')

        report = backup_service.send_backup_to_bot(info['name'])

        assert report['sent'] == ['111', '222']
        assert report['failed'] == []
        assert len(calls) == 2
        assert calls[0]['provider'] == 'bale'
        assert calls[0]['token'] == 'TOKEN-123'
        assert calls[0]['filename'] == info['name']
        caption = calls[0]['caption']
        assert 'آموزشگاه نمونه' in caption
        assert info['name'] in caption
        assert 'ارسال آزمایشی' in caption

    def test_failed_target_is_reported_not_raised(self, app, monkeypatch):
        self._patch_settings(monkeypatch)
        self._capture_sender(monkeypatch, ok=False, description='chat not found')
        info = backup_service.create_backup(kind='database')

        report = backup_service.send_backup_to_bot(info['name'])
        assert report['sent'] == []
        assert [item['error'] for item in report['failed']] == ['chat not found'] * 2

    def test_missing_token_is_rejected(self, app, monkeypatch):
        self._patch_settings(monkeypatch, bale_bot_token='')
        info = backup_service.create_backup(kind='database')
        with pytest.raises(BackupError) as error:
            backup_service.send_backup_to_bot(info['name'])
        assert 'توکن' in str(error.value)

    def test_missing_target_is_rejected(self, app, monkeypatch):
        self._patch_settings(monkeypatch, backup_bot_chat_id='')
        info = backup_service.create_backup(kind='database')
        with pytest.raises(BackupError) as error:
            backup_service.send_backup_to_bot(info['name'])
        assert 'مقصد' in str(error.value)

    def test_oversized_package_is_rejected(self, app, monkeypatch):
        self._patch_settings(monkeypatch, backup_bot_max_mb=1)
        calls = self._capture_sender(monkeypatch)
        info = backup_service.create_backup(kind='database')
        path = backup_service.safe_backup_path(info['name'])
        with open(path, 'ab') as handle:                 # بزرگ‌کردن مصنوعی بسته
            handle.write(b'0' * (2 * 1024 * 1024))

        with pytest.raises(BackupError) as error:
            backup_service.send_backup_to_bot(info['name'])
        assert 'سقف' in str(error.value)
        assert calls == []                               # هیچ آپلودی انجام نشده است

    def test_hard_limit_caps_configured_value(self, app, monkeypatch):
        self._patch_settings(monkeypatch, backup_bot_max_mb=500)
        status = backup_service.bot_delivery_status()
        assert status['max_mb'] == 500                   # مقدار خام تنظیمات
        # ولی هنگام ارسال، سقف سرویس (۵۰ مگابایت) اعمال می‌شود
        assert backup_service.BOT_HARD_LIMIT_MB == 50

    def test_delivery_status_reports_readiness(self, app, monkeypatch):
        self._patch_settings(monkeypatch)
        status = backup_service.bot_delivery_status()
        assert status['ready'] is True
        assert status['targets_count'] == 2

        self._patch_settings(monkeypatch, bale_bot_token='')
        assert backup_service.bot_delivery_status()['ready'] is False

    def test_locked_license_blocks_delivery(self, app, monkeypatch):
        """کنترل مستقل در عمق سرویس: بخش پشتیبان‌گیری قفل باشد، ارسال انجام نمی‌شود."""
        from license_client import FeatureLocked, LicenseState

        self._patch_settings(monkeypatch)
        calls = self._capture_sender(monkeypatch)
        info = backup_service.create_backup(kind='database')

        license_client._store_state(LicenseState(
            status='SUCCESS', message='', valid=True, source='online',
            data={'allowed_features': {'backup': False}}))
        with pytest.raises(FeatureLocked):
            backup_service.send_backup_to_bot(info['name'])
        assert calls == []

    def test_scheduled_backup_sends_when_enabled(self, app, monkeypatch):
        settings = self._patch_settings(monkeypatch, auto_backup=True)
        module = types.ModuleType('models.system')
        module.SystemSettings = type(
            'SystemSettings', (),
            {'query': type('Query', (), {'first': staticmethod(lambda: settings)})()})
        monkeypatch.setitem(sys.modules, 'models.system', module)
        calls = self._capture_sender(monkeypatch)

        message = backup_service.run_scheduled_backup()
        assert 'ارسال شد' in message
        assert len(calls) == 2                           # دو مقصد تنظیم‌شده
        # بسته‌ی ارسالی «فقط دیتابیس» است تا حجم کم بماند
        assert all('database' in call['filename'] for call in calls)

    def test_scheduled_backup_survives_bot_failure(self, app, monkeypatch):
        settings = self._patch_settings(monkeypatch, auto_backup=True,
                                        bale_bot_token='')
        module = types.ModuleType('models.system')
        module.SystemSettings = type(
            'SystemSettings', (),
            {'query': type('Query', (), {'first': staticmethod(lambda: settings)})()})
        monkeypatch.setitem(sys.modules, 'models.system', module)

        message = backup_service.run_scheduled_backup()
        assert 'ساخته شد' in message                     # پشتیبان انجام شده
        assert 'ارسال به ربات انجام نشد' in message
        assert backup_service.list_backups()             # فایل سر جایش است


# ══════════════════════════════════════════════════════════════
#  ۸) دستور «پشتیبان» داخل خود ربات بله
# ══════════════════════════════════════════════════════════════
class _BotUser:
    def __init__(self, is_admin_bot=False):
        self.is_admin_bot = is_admin_bot


class TestBotCommand:
    @staticmethod
    def _prepare(monkeypatch, ok=True):
        from utils import bot_services

        settings = _Settings()
        monkeypatch.setattr(backup_service, '_settings_row', lambda: settings)
        module = types.ModuleType('models.system')
        module.SystemSettings = type(
            'SystemSettings', (),
            {'query': type('Query', (), {'first': staticmethod(lambda: settings)})()})
        monkeypatch.setitem(sys.modules, 'models.system', module)

        calls = []

        def _fake_send(provider, token, chat_id, file_path, caption='', filename=None,
                       timeout=180):
            calls.append(chat_id)
            return {'ok': ok, 'description': '' if ok else 'chat not found'}

        sender = types.ModuleType('utils.bot_services')
        sender.send_bot_document = _fake_send
        monkeypatch.setitem(sys.modules, 'utils.bot_services', sender)
        return bot_services, calls

    def test_admin_gets_backup_in_chat(self, app, monkeypatch):
        bot_services, calls = self._prepare(monkeypatch)
        reply = bot_services.handle_backup_command(_BotUser(is_admin_bot=True), 999)
        assert 'ارسال شد' in reply
        assert calls == ['999']                      # فقط به همان گفت‌وگو
        assert len(backup_service.list_backups()) == 1

    def test_chat_id_listed_in_settings_is_also_admin(self, app, monkeypatch):
        bot_services, calls = self._prepare(monkeypatch)
        reply = bot_services.handle_backup_command(_BotUser(is_admin_bot=False), 111)
        assert 'ارسال شد' in reply
        assert calls == ['111']

    def test_normal_user_gets_no_hint_and_no_backup(self, app, monkeypatch):
        bot_services, calls = self._prepare(monkeypatch)
        reply = bot_services.handle_backup_command(_BotUser(is_admin_bot=False), 777)
        assert 'پشتیبان' not in reply                # هیچ نشانه‌ای از وجود دستور
        assert calls == []
        assert backup_service.list_backups() == []

    def test_send_failure_is_reported_politely(self, app, monkeypatch):
        bot_services, _calls = self._prepare(monkeypatch, ok=False)
        reply = bot_services.handle_backup_command(_BotUser(is_admin_bot=True), 999)
        assert 'ارسال نشد' in reply
        assert 'chat not found' in reply

    def test_locked_license_gives_safe_message(self, app, monkeypatch):
        from license_client import LicenseState

        bot_services, calls = self._prepare(monkeypatch)
        license_client._store_state(LicenseState(
            status='SUCCESS', message='', valid=True, source='online',
            data={'allowed_features': {'backup': False}}))
        reply = bot_services.handle_backup_command(_BotUser(is_admin_bot=True), 999)
        assert reply.startswith('⛔️')
        assert calls == []


def test_database_integrity_of_generated_package(app, tmp_path):
    """بسته ساخته‌شده باید یک دیتابیس SQLite سالم و قابل خواندن باشد."""
    info = backup_service.create_backup(kind='database')
    extract = tmp_path / 'extract'
    extract.mkdir()
    with zipfile.ZipFile(backup_service.safe_backup_path(info['name'])) as archive:
        archive.extract('database/academy.db', str(extract))
    connection = sqlite3.connect(str(extract / 'database' / 'academy.db'))
    try:
        assert connection.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert connection.execute('SELECT name FROM demo').fetchone()[0] == 'نسخه اول'
    finally:
        connection.close()
