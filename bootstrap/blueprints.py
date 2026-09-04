"""
ثبت بلوپرینت‌ها — یک «رجیستری داده‌محور» به‌جای ۶۰ خط import/register تکراری.
هر آیتم: (نام ماژول، نام/نام‌های Blueprint، پیشوند URL یا None).
"""
from __future__ import annotations

import importlib

#: (module, attr names, url_prefix)
REGISTRY: tuple[tuple[str, tuple[str, ...], str | None], ...] = (
    ('routes.auth', ('auth_bp',), None),
    ('routes.license', ('license_bp',), None),
    ('routes.dashboard', ('dashboard_bp',), None),
    ('routes.students', ('students_bp',), '/students'),
    ('routes.teachers', ('teachers_bp',), '/teachers'),
    ('routes.classes', ('classes_bp',), '/classes'),
    ('routes.registration', ('registration_bp',), '/registration'),
    ('routes.attendance', ('attendance_bp',), '/attendance'),
    ('routes.exams', ('exams_bp',), '/exams'),
    ('routes.finance', ('finance_bp',), '/finance'),
    ('routes.accounting', ('accounting_bp',), '/accounting'),
    ('routes.settings', ('settings_bp',), '/settings'),
    ('routes.reports', ('reports_bp',), '/reports'),
    ('routes.messaging', ('messaging_bp',), '/messaging'),
    ('routes.additional', ('certificates_bp', 'complaints_bp', 'surveys_bp',
                           'tickets_bp', 'goals_bp', 'analytics_bp'), None),
    ('routes.features', ('features_bp',), None),
    ('routes.features2', ('features2_bp',), None),
    ('routes.new_features', ('new_features_bp',), None),
    ('routes.final', ('final_bp',), None),
    ('routes.demo', ('demo_bp',), None),
    ('routes.settings_panel', ('settings_panel_bp',), '/panel'),
    ('routes.network_info', ('network_bp',), None),
    ('routes.setup', ('setup_bp',), None),
    ('routes.payroll', ('payroll_bp',), None),
    ('routes.tax', ('tax_bp',), None),
    ('routes.permissions', ('perms_bp',), '/perms'),
    ('routes.teacher_portal', ('teacher_bp',), None),
    ('routes.bot_panel', ('bot_panel_bp',), None),
    ('routes.backup_center', ('backup_center_bp',), None),
)

#: پیشوندهای جداگانهٔ شش بلوپرینت «additional» (هرکدام مسیر خودش را دارد)
_ADDITIONAL_PREFIXES = {
    'certificates_bp': '/certificates',
    'complaints_bp': '/complaints',
    'surveys_bp': '/surveys',
    'tickets_bp': '/tickets',
    'goals_bp': '/goals',
    'analytics_bp': '/analytics',
}


def register_all(app) -> None:
    """ثبت یک‌جای همهٔ بلوپرینت‌ها با پیشوند صحیح (ترتیب = ترتیب قدیمی app.py)."""
    for module_path, attrs, prefix in REGISTRY:
        module = importlib.import_module(module_path)
        for attr in attrs:
            blueprint = getattr(module, attr)
            if attr in _ADDITIONAL_PREFIXES:
                app.register_blueprint(blueprint,
                                       url_prefix=_ADDITIONAL_PREFIXES[attr])
            elif prefix:
                app.register_blueprint(blueprint, url_prefix=prefix)
            else:
                app.register_blueprint(blueprint)
