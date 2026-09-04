"""
ماتریس «نقش × مسیر» — الزام سطح اکشن (فاز ۷ / بند P2 بازبینی امنیت)
════════════════════════════════════════════════════════════════════
پیش‌تر `ENFORCE_ACTION_FOR_WRITES = False` بود، چون نصب‌های موجود برای بیشتر
نقش‌ها فقط ردیف `view` داشتند و الزام اکشن، کاربران مجاز را قفل می‌کرد.
حالا `backfill_role_actions()` در بوت همان ردیف‌ها را می‌سازد (فقط اضافه، هرگز
حذف نه) و الزام روشن است ⇒ معنی «فقط ببیند» در ویرایش دسترسی نقش، واقعی است.

نکته آزمون: نقش آزمونی **بعد از بوت** ساخته می‌شود، پس backfill به آن دست
نمی‌زند و می‌توان ردیف‌ها را دانه‌دانه کنترل کرد.
دیتابیس توسعه؛ همه ردیف‌های آزمونی در پایان پاک می‌شوند.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app                      # noqa: E402
from extensions import db                       # noqa: E402
from models.user import Permission, Role, RolePermission, User  # noqa: E402


@pytest.fixture(scope='module')
def test_app():
    app = create_app()
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    return app


@pytest.fixture(scope='module', autouse=True)
def licensed_state(test_app):
    import license_client
    from license_features import AVAILABLE_FEATURES

    data = {'success': True, 'status': 'SUCCESS', 'client_name': 'آموزشگاه آزمون',
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


@pytest.fixture
def staff(test_app):
    """یک نقش آزمونی + یک کاربر غیرادمین با همان نقش (پاک می‌شوند)."""
    tag = 'actx'
    created = {'perms': [], 'rps': []}
    with test_app.app_context():
        role = Role(name=f'نقش آزمونی {tag}', description='آزمون نگهبان')
        db.session.add(role)
        db.session.flush()
        role_id = role.id
        user = User(username=f'usr_{tag}', full_name='کاربر آزمون اکشن', is_admin=False,
                    is_active=True, role_id=role_id)
        user.set_password('Action-Test-123!')
        db.session.add(user)
        db.session.flush()
        user_id = user.id
        db.session.commit()

    def grant(module, *actions):
        with test_app.app_context():
            for action in actions:
                perm = Permission.query.filter_by(module=module, action=action).first()
                if perm is None:
                    perm = Permission(module=module, action=action,
                                      description=f'{action} {module} (آزمون)')
                    db.session.add(perm)
                    db.session.flush()
                    created['perms'].append(perm.id)
                rp = RolePermission(role_id=role_id, permission_id=perm.id)
                db.session.add(rp)
                db.session.flush()
                created['rps'].append(rp.id)
            db.session.commit()

    yield {'role_id': role_id, 'user_id': user_id, 'grant': grant, 'tag': tag}

    with test_app.app_context():
        db.session.execute(db.text('DELETE FROM role_permissions WHERE role_id = :r'), {'r': role_id})
        for perm_id in created['perms']:
            db.session.execute(db.text('DELETE FROM permissions WHERE id = :p'), {'p': perm_id})
        from models.user import ActivityLog, UserSession
        ActivityLog.query.filter_by(user_id=user_id).delete(synchronize_session=False)
        UserSession.query.filter_by(user_id=user_id).delete(synchronize_session=False)
        db.session.execute(db.text('DELETE FROM users WHERE id = :i'), {'i': user_id})
        db.session.execute(db.text('DELETE FROM roles WHERE id = :i'), {'i': role_id})
        db.session.commit()


def _as(test_app, user_id):
    client = test_app.test_client()
    with client.session_transaction() as sess:
        sess['_user_id'] = str(user_id)
        sess['_fresh'] = True
    return client


class TestActionMatrix:
    def test_view_only_role_cannot_write(self, test_app, staff):
        staff['grant']('students', 'view')
        client = _as(test_app, staff['user_id'])
        # XHR ⇒ پاسخ JSON با 403 (قابل ادعا در تست)
        response = client.post('/students/add', json={'first_name': 'x'},
                               headers={'X-Requested-With': 'XMLHttpRequest'})
        assert response.status_code == 403, 'نگهبان باید «create» را بخواهد'
        assert response.get_json()['ok'] is False

    def test_create_action_opens_the_write(self, test_app, staff):
        staff['grant']('students', 'view', 'create')
        client = _as(test_app, staff['user_id'])
        response = client.post('/students/add', json={'first_name': 'x'},
                               headers={'X-Requested-With': 'XMLHttpRequest'})
        assert response.status_code != 403, 'با ردیف create نباید دسترسی رد شود'

    def test_delete_needs_delete_or_edit(self, test_app, staff):
        staff['grant']('students', 'view', 'create')
        client = _as(test_app, staff['user_id'])
        denied = client.post('/students/delete/1', json={},
                             headers={'X-Requested-With': 'XMLHttpRequest'})
        assert denied.status_code == 403, 'حذف با دسترسی create نباید باز شود'
        staff['grant']('students', 'edit')
        allowed = client.post('/students/delete/1', json={},
                              headers={'X-Requested-With': 'XMLHttpRequest'})
        assert allowed.status_code != 403

    def test_read_paths_ignore_action_layer(self, test_app, staff):
        staff['grant']('students', 'view')
        client = _as(test_app, staff['user_id'])
        assert client.get('/students/').status_code != 403

    def test_admin_role_bypasses_everything(self, test_app, staff):
        client = _as(test_app, staff['user_id'])
        assert client.post('/students/delete/1', json={},
                           headers={'X-Requested-With': 'XMLHttpRequest'}).status_code == 403
        with test_app.app_context():
            user = db.session.get(User, staff['user_id'])
            user.is_admin = True
            db.session.commit()
        response = client.post('/finance/payments/add', json={},
                               headers={'X-Requested-With': 'XMLHttpRequest'})
        assert response.status_code in (200, 302, 400), response.status_code

    def test_role_without_any_module_is_blocked(self, test_app, staff):
        client = _as(test_app, staff['user_id'])
        response = client.get('/finance/payments',
                              headers={'X-Requested-With': 'XMLHttpRequest'})
        assert response.status_code == 403, 'نقش بی‌ردیف نباید صندوق را ببیند'


class TestActionBackfill:
    def test_backfill_completes_missing_actions(self, test_app, staff):
        from utils.access_policy import backfill_role_actions
        staff['grant']('students', 'view')
        with test_app.app_context():
            added = backfill_role_actions()
            assert added >= 3, 'کم‌وبیش create/edit/delete باید افزوده شود'
            actions = {perm.action for rp, perm in
                       db.session.query(RolePermission, Permission).join(
                           Permission, RolePermission.permission_id == Permission.id).filter(
                           RolePermission.role_id == staff['role_id'],
                           Permission.module == 'students').all()}
            assert {'view', 'create', 'edit', 'delete'} <= actions
            # ماژول دیگر نقش دست‌نخورده می‌ماند
            other = db.session.query(RolePermission).join(
                Permission, RolePermission.permission_id == Permission.id).filter(
                RolePermission.role_id == staff['role_id'],
                Permission.module == 'finance').count()
            assert other == 0
        # و بعد از تکمیل، نوشتن باز می‌شود
        client = _as(test_app, staff['user_id'])
        assert client.post('/students/add', json={'first_name': 'x'},
                           headers={'X-Requested-With': 'XMLHttpRequest'}).status_code != 403

    def test_backfill_is_idempotent(self, test_app, staff):
        from utils.access_policy import backfill_role_actions
        staff['grant']('classes', 'view')
        with test_app.app_context():
            backfill_role_actions()
            second = backfill_role_actions()
            assert second == 0, 'اجرای دوباره نباید ردیف تکراری بسازد'
            rows = db.session.query(RolePermission).join(
                Permission, RolePermission.permission_id == Permission.id).filter(
                RolePermission.role_id == staff['role_id'],
                Permission.module == 'classes').count()
            assert rows == 4, rows

    def test_admin_roles_are_left_alone(self, test_app):
        from utils.access_policy import backfill_role_actions
        with test_app.app_context():
            role = Role.query.filter_by(is_admin=True).first()
            if role is None:
                pytest.skip('نقش ادمینی در این دیتابیس نیست')
            before = RolePermission.query.filter_by(role_id=role.id).count()
            backfill_role_actions()
            after = RolePermission.query.filter_by(role_id=role.id).count()
            assert after == before


class TestUpgradeHasNoRegression:
    """دعوی اصلی: روشن‌شدن الزام اکشن، نصب موجود را قفل نمی‌کند."""

    def test_after_backfill_every_module_allows_all_write_actions(self, test_app):
        from utils.access_policy import BACKFILL_ACTIONS, backfill_role_actions
        with test_app.app_context():
            backfill_role_actions()
            pairs = {}
            for rp, perm in db.session.query(RolePermission, Permission).join(
                    Permission, RolePermission.permission_id == Permission.id).all():
                pairs.setdefault(rp.role_id, set()).add(perm.module)
            admin_roles = {r.id for r in Role.query.filter_by(is_admin=True).all()}
            checked = 0
            for role_id, modules in pairs.items():
                if role_id in admin_roles:
                    continue
                for module in modules:
                    user = User.query.filter_by(role_id=role_id, is_active=True).first()
                    if user is None:
                        # خود نقش را با یک کاربر موقتِ لحظه‌ای نمی‌سازیم؛ کافی است
                        # ردیف‌ها مستقیم چک شوند
                        for action in BACKFILL_ACTIONS:
                            count = db.session.query(RolePermission).join(
                                Permission, RolePermission.permission_id == Permission.id).filter(
                                RolePermission.role_id == role_id,
                                Permission.module == module,
                                Permission.action == action).count()
                            assert count >= 1, f'role={role_id} module={module} action={action}'
                        checked += 1
                        continue
                    for action in BACKFILL_ACTIONS:
                        assert user.has_permission(module, action), \
                            f'کاربر {user.username} در {module} اکشن {action} را ندارد'
                    checked += 1
        assert checked >= 0

    def test_reads_follow_only_the_module_tier(self, test_app, staff):
        """«view» برای باز شدن صفحه کافی است؛ نبودش ⇒ رد (302 به داشبورد)."""
        staff['grant']('students', 'view')
        client = _as(test_app, staff['user_id'])
        assert client.get('/students/').status_code == 200
        denied = client.get('/finance/payments')
        assert denied.status_code == 302 and '/finance' not in (denied.headers.get('Location') or '')


class TestSupportEscapeHatch:
    def test_env_var_disables_action_layer(self, test_app, monkeypatch):
        from utils.access_policy import resolve_policy
        monkeypatch.setenv('ACADEMY_DISABLE_ACTION_GUARD', '1')
        assert resolve_policy('/students/add', 'POST') == ('module', 'students')
        monkeypatch.delenv('ACADEMY_DISABLE_ACTION_GUARD')
        assert resolve_policy('/students/add', 'POST') == ('action:create', 'students')
