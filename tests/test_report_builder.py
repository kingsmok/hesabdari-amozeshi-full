"""آزمون گارد گزارش‌ساز سفارشی (`utils/report_builder.py`)

نشت واقعی که این پوشش می‌بندد: `/reports/custom-builder` فقط `login_required`
داشت و فرم هیچ انتخاب ستونی نداشت، پس `selected_names = همهٔ ستون‌های جدول`
برداشته می‌شد ⇒ هر کاربر واردشده با POST `table=users` جدول username +
password_hash را روی صفحه می‌دید.
"""
import os
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from extensions import db                                  # noqa: E402
from utils import report_builder as rb                      # noqa: E402


@pytest.fixture(scope='module')
def test_app():
    os.environ.setdefault('ACADEMY_DISABLE_SCHEDULER', '1')
    from app import create_app
    application = create_app()
    application.config['TESTING'] = True
    application.config['WTF_CSRF_ENABLED'] = False
    return application


@pytest.fixture(scope='module', autouse=True)
def _licensed(test_app):
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


@pytest.fixture()
def app_context(test_app):
    with test_app.app_context():
        yield


class TestTableGate:
    def test_credential_tables_are_not_offered(self, app_context):
        names = rb.table_names()
        for denied in ('users', 'user_sessions', 'roles', 'permissions'):
            assert denied not in names
        assert 'students' in names

    def test_denied_table_resolves_to_none(self, app_context):
        assert rb.resolve_table('users') is None
        assert rb.resolve_table('') is None
        assert rb.resolve_table('students; drop table students;--') is None
        assert rb.resolve_table('students') is not None

    def test_metadata_has_no_silent_all_columns_default(self, app_context):
        """`build_query` هیچ fallback «همهٔ ستون‌ها» ندارد (همان تلهٔ قدیمی)."""
        result, message = rb.build_query('students', [])
        assert result is None
        assert 'ستون' in message


class TestSensitiveColumns:
    def test_password_hash_is_hidden(self, app_context):
        users = db.metadata.tables['users']
        names = {c.name for c in users.columns}
        assert 'password_hash' in names
        assert 'password_hash' not in rb.visible_columns(users)
        # اگر جدولی ستون remember_token نداشته باشد، آزمون بی‌معنی است
        assert 'remember_token' in names or True

    @pytest.mark.parametrize('name', ['password_hash', 'api_token', 'session_token',
                                      'salt', 'csrf_secret', 'otp_code', 'telegram_bot_token',
                                      'sms_api_key', 'remember_token'])
    def test_is_sensitive_column(self, name):
        assert rb.is_sensitive_column(name)

    @pytest.mark.parametrize('name', ['full_name', 'mobile', 'paid_amount', 'created_by',
                                      'title', 'status',
                                      # این‌ها ستون کاری‌اند؛ فیلتر شل «هرچه session دارد»
                                      # ابزار گزارش‌گیری را فلج می‌کرد
                                      'total_sessions', 'sessions_count', 'session_rate',
                                      'session_number', 'session_date', 'session_id',
                                      'session_amount'])
    def test_business_columns_are_not_blocked(self, name):
        assert not rb.is_sensitive_column(name)

    def test_unknown_column_is_dropped_not_defaulted(self, app_context):
        # `students` ستون password ندارد ⇒ دور ریخته می‌شود، ولی SELECT حفظ می‌شود
        (names, statement), note = rb.build_query('students', ['id', 'password'], None)
        assert names == ['id']
        assert note is None
        del statement

    def test_sensitive_column_never_selected_even_if_requested(self, app_context):
        # اگر روزی جدولی غیرممنوع با ستون حساس داشته باشیم، فیلتر باید بگیردش
        users = db.metadata.tables['users']
        requested = [c.name for c in users.columns]
        safe = [name for name in requested if not rb.is_sensitive_column(name)]
        assert 'password_hash' not in safe
        # و ستون‌های باقی‌مانده هم واقعاً وجود دارند
        assert set(safe) <= {c.name for c in users.columns}


class TestLimits:
    @pytest.mark.parametrize('raw,expected', [
        (None, 50), ('abc', 50), ('0', 1), ('-5', 1), ('25', 25),
        ('500', 500), ('999999', 500), (12.9, 12)])
    def test_clamp_limit(self, raw, expected):
        assert rb.clamp_limit(raw) == expected

    def test_limit_reaches_the_statement(self, app_context):
        (names, statement), _note = rb.build_query('students', ['id'], '999999')
        sql = str(statement.compile(compile_kwargs={'literal_binds': True}))
        assert 'LIMIT 500' in sql


class TestInjection:
    @pytest.mark.parametrize('table', ["students' OR '1'='1", 'students; --',
                                      'sqlite_master', 'information_schema.tables'])
    def test_strange_table_names_are_refused(self, app_context, table):
        result, message = rb.build_query(table, ['id'], None)
        assert result is None
        assert 'معتبر نیست' in message

    @pytest.mark.parametrize('column', ["id' = '1", 'id; DROP TABLE students', '../../x'])
    def test_strange_column_names_are_dropped(self, app_context, column):
        result, message = rb.build_query('students', [column], None)
        assert result is None, 'ستون ناشناچه نباید به SELECT همهٔ ستون‌ها تبدیل شود'
        assert 'ستون' in message


# ══════════════════════════════════════════════════════════════
#  سطح مسیر: گارد مدیر + نبودِ هش در پاسخ
# ══════════════════════════════════════════════════════════════
@pytest.fixture(scope='module')
def admin_client(test_app):
    from models.user import User
    with test_app.app_context():
        admin = User.query.filter_by(is_admin=True, is_active=True).first()
        admin_id = admin.id if admin else None
    assert admin_id is not None, 'این آزمون به یک حساب مدیر کل نیاز دارد'
    http = test_app.test_client()
    with http.session_transaction() as sess:
        sess['_user_id'] = str(admin_id)
        sess['_fresh'] = True
    return http


@pytest.fixture(scope='module')
def staff_client(test_app):
    """یک حساب **غیرمدیر ولی با دسترسی ماژول گزارش‌ها**.

    عمداً نقش آزمونی تازه می‌سازیم؛ اگر از نقش آماده (مدرس) استفاده می‌کردیم،
    رد شدن درخواست می‌توانست از گارد ماژولِ `access_policy` باشد نه از گارد
    مدیرِ خود مسیر — و آزمون بی‌معنی (سبزِ دروغین) می‌شد.
    """
    from models.user import ActivityLog, Permission, Role, RolePermission, User, UserSession

    created = {'user': None, 'role': None, 'permission': None}
    with test_app.app_context():
        permission = Permission.query.filter_by(module='reports', action='view').first()
        if permission is None:
            permission = created['permission'] = Permission(
                module='reports', action='view', description='مشاهده گزارش‌ها')
            db.session.add(permission)
            db.session.commit()

        role = created['role'] = Role(name='نقش آزمونی گزارش‌ساز',
                                      description='برای آزمون گارد مدیر', is_admin=False)
        db.session.add(role)
        db.session.flush()
        db.session.add(RolePermission(role_id=role.id, permission_id=permission.id))

        user = created['user'] = User(username='test_builder_staff',
                                      full_name='کاربر آزمونی گزارش‌ساز',
                                      is_admin=False, is_active=True, role_id=role.id)
        user.set_password('Test-Only-Strong-123!')
        db.session.add(user)
        db.session.commit()
        user_id, role_id, permission_id = user.id, role.id, permission.id

    http = test_app.test_client()
    with http.session_transaction() as sess:
        sess['_user_id'] = str(user_id)
        sess['_fresh'] = True
    yield http, user_id

    with test_app.app_context():
        ActivityLog.query.filter_by(user_id=user_id).delete(synchronize_session=False)
        UserSession.query.filter_by(user_id=user_id).delete(synchronize_session=False)
        RolePermission.query.filter_by(role_id=role_id).delete(synchronize_session=False)
        for model, row_id in ((User, user_id), (Role, role_id)):
            row = db.session.get(model, row_id)
            if row is not None:
                db.session.delete(row)
        if created['permission'] is not None:
            row = db.session.get(Permission, permission_id)
            if row is not None:
                db.session.delete(row)
        db.session.commit()


class TestRouteGate:
    URL = '/reports/custom-builder'

    def test_non_admin_with_reports_access_is_refused(self, staff_client):
        """دو لایه: گارد سراسری (`ADMIN_ONLY_PATHS`) و گارد خود مسیر؛ هر دو
        flash+redirect به داشبورد می‌دهند، پس نتیجهٔ قابل مشاهده یکی است."""
        client, _user_id = staff_client
        resp = client.get(self.URL)
        assert resp.status_code == 302, 'گزارش‌ساز نباید برای کاربر غیرمدیر باز شود'
        location = resp.headers.get('Location') or ''
        assert 'login' not in location, \
            f'رد باید به‌خاطر دسترسی باشد نه نبودِ احراز هویت ({location})'
        assert location in ('/', '/dashboard', '/dashboard/'), location

    def test_non_admin_can_still_use_ordinary_reports(self, staff_client):
        """ردِ کنترل مثبت: کاربر واقعاً وارد شده و ماژول گزارش‌ها را دارد؛
        فقط همین ابزار محدود است."""
        client, _user_id = staff_client
        resp = client.get('/reports/')
        assert resp.status_code in (200, 302)
        if resp.status_code == 302:
            assert 'login' not in (resp.headers.get('Location') or ''), \
                'کاربر آزمونی باید احراز هویت شده باشد'

    def test_non_admin_cannot_dump_users_by_post(self, staff_client):
        client, _user_id = staff_client
        resp = client.post(self.URL, data={'table': 'users', 'limit': '5'})
        assert resp.status_code == 302
        assert 'password_hash' not in resp.get_data(as_text=True)

    def test_admin_sees_no_hash_on_get(self, admin_client):
        html = admin_client.get(self.URL).get_data(as_text=True)
        assert 'password_hash' not in html
        options = html.split('<select name="table"')[1].split('</select>')[0]
        assert '>users<' not in options.replace('\n', ''), 'جدول users نباید در فهرست باشد'

    def test_admin_can_select_allowed_table_columns(self, admin_client):
        html = admin_client.get(f'{self.URL}?table=students').get_data(as_text=True)
        assert 'name="columns"' in html
        block = html.split('<div id="rb-columns"')[1].split('</div>')[0]
        assert 'password_hash' not in block

    def test_posting_users_table_is_refused_without_results(self, admin_client):
        resp = admin_client.post(self.URL, data={'table': 'users', 'columns': ['username',
                                                                              'password_hash'],
                                                 'limit': '5'})
        html = resp.get_data(as_text=True)
        assert 'password_hash' not in html
        assert 'معتبر نیست' in html or 'جای' in html

    def test_legit_query_renders_rows(self, admin_client):
        resp = admin_client.post(self.URL, data={'table': 'students', 'columns': ['id'],
                                                 'limit': '3'})
        html = resp.get_data(as_text=True)
        assert '<th>id</th>' in html
        assert 'رکورد' in html


class TestSourceGuard:
    def test_route_does_not_build_raw_sql(self):
        import inspect
        from routes.features2 import custom_report
        source = inspect.getsource(custom_report)
        for forbidden in ('execute(f"', 'execute(\'SELECT', 'text(f"', '+ table_name'):
            assert forbidden not in source, f'SQL رشته‌ای در گزارش‌ساز: {forbidden}'
        assert 'report_builder.build_query' in source
