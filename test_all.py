"""بررسی فنی غیرمخرب سیستم و ارتباط بین ماژول‌ها.

اجرا:
    python test_all.py

این اسکریپت درخواست خارجی ارسال نمی‌کند و داده‌ای حذف نمی‌کند.
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import create_app


def main() -> int:
    app = create_app()
    failures = []

    with app.app_context():
        from extensions import db
        from utils.system_diagnostics import run_system_diagnostics
        from utils.sms_service import normalize_iran_mobile
        from utils.bot_services import build_academy_bot_response

        report = run_system_diagnostics()
        print('=' * 70)
        print(' گزارش بررسی فنی و ارتباطات نرم‌افزار')
        print('=' * 70)

        group_names = {
            'core': 'هسته',
            'database': 'دیتابیس',
            'relations': 'ارتباط اطلاعات',
            'storage': 'فایل و PDF',
            'connections': 'اتصالات خارجی',
        }
        for group, title in group_names.items():
            print(f'\n[{title}]')
            for check in report['checks']:
                if check['group'] != group:
                    continue
                icon = {'ok': '✅', 'warning': '⚠️', 'error': '❌', 'info': 'ℹ️'}[check['status']]
                print(f" {icon} {check['name']}: {check['message']}")
                if check['status'] == 'error':
                    failures.append(check['name'])

        # قراردادهای پایه سرویس‌ها
        assert normalize_iran_mobile('+98 912 123 4567') == '09121234567'
        assert normalize_iran_mobile('شماره نامعتبر') is None
        assert build_academy_bot_response('/start')
        assert db.session.execute(db.text('SELECT 1')).scalar() == 1

        required_endpoints = {
            'settings_panel.diagnostics',
            'certificates.issue',
            'certificates.pdf',
            'finance.expenses_pdf',
            'settings.expense_categories_pdf',
            'settings_panel.start_bale_polling',
            'settings_panel.farazsms_config',
        }
        endpoints = {rule.endpoint for rule in app.url_map.iter_rules()}
        missing = sorted(required_endpoints - endpoints)
        if missing:
            failures.extend(missing)
            print(f'\n❌ مسیرهای مفقود: {", ".join(missing)}')

        summary = report['summary']
        print('\n' + '-' * 70)
        print(
            f"نتیجه: {summary['ok']} سالم | {summary['warning']} هشدار | "
            f"{summary['error']} خطا | {summary['info']} اطلاع‌رسانی"
        )

    if failures:
        print(f'❌ بررسی با {len(failures)} خطای فنی پایان یافت.')
        return 1
    print('✅ تمام بررسی‌های الزامی با موفقیت انجام شد.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
