"""Contract tests for the unified reporting and search infrastructure."""
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
import json
import re
from types import SimpleNamespace

from license_features import FEATURE_KEYS
from utils.form_helpers import safe_float
from utils.report_exports import (
    csv_bytes, excel_bytes, json_bytes, spreadsheet_safe, write_export_file,
)
from utils.report_scheduler import next_run
from utils.reporting import (
    BUILDERS, CATEGORY_LABELS, COMPOSITE_REPORT_SOURCES, REPORT_CATALOG,
    ReportFilters, _budget_period_bounds, _matches_query, _previous_jalali_month,
    _previous_jalali_year, _query_range,
    can_view_report, normalise_text, run_report,
)
from utils.jalali import gregorian_to_jalali, parse_jalali_date
from utils.local_time import local_now, timezone_name


class _User:
    is_admin = False
    branch_id = 7


class TestReportCatalogue:
    def test_acceptance_matrix_contains_exactly_one_hundred_items(self):
        document = (Path(__file__).resolve().parents[1] / 'REPORTING_FEATURES_FA.md').read_text(encoding='utf-8')
        numbers = [int(value) for value in re.findall(r'(?m)^(\d+)\.', document)]
        assert numbers == list(range(1, 101))

    def test_catalogue_is_comprehensive_and_every_builder_exists(self):
        assert len(REPORT_CATALOG) == 64
        assert len(CATEGORY_LABELS) == 10
        assert len(REPORT_CATALOG) == len(set(REPORT_CATALOG))
        for key, meta in REPORT_CATALOG.items():
            assert meta['title']
            assert meta['description']
            assert meta['category'] in CATEGORY_LABELS
            assert meta['builder'] in BUILDERS
            assert meta['filters']
            assert meta['license_features']
            assert set(meta['license_features']) <= FEATURE_KEYS
            assert set(meta['source_permissions']) <= FEATURE_KEYS

    def test_composite_reports_declare_every_source_contract(self):
        assert set(COMPOSITE_REPORT_SOURCES) <= set(REPORT_CATALOG)
        selector_sources = {
            'course': 'courses', 'class': 'classes', 'teacher': 'teachers',
            'student': 'students', 'account': 'accounting',
            'fiscal': 'accounting',
        }
        for key, meta in REPORT_CATALOG.items():
            required = {
                module for selector, module in selector_sources.items()
                if selector in meta['filters']
            }
            assert required <= set(meta['source_permissions']), key
        for key, modules in COMPOSITE_REPORT_SOURCES.items():
            meta = REPORT_CATALOG[key]
            assert tuple(meta['source_permissions']) == modules
            assert set(modules) <= set(meta['license_features'])
        assert set(REPORT_CATALOG['cash-flow']['source_permissions']) == {
            'accounting', 'finance',
        }
        assert set(REPORT_CATALOG['tax-control-summary']['source_permissions']) == {
            'tax', 'finance', 'payroll', 'teachers',
        }
        assert set(REPORT_CATALOG['teacher-performance']['source_permissions']) == {
            'teachers', 'classes', 'courses', 'registration', 'finance', 'attendance',
        }

    def test_source_and_reporting_view_permissions_are_both_required(self):
        class User:
            is_admin = False
            def __init__(self, permissions):
                self.permissions = permissions
            def has_permission(self, module, action):
                return (module, action) in self.permissions

        finance_meta = REPORT_CATALOG['receipts-payments']
        finance_permissions = {('reports', 'view')} | {
            (module, 'view') for module in finance_meta['source_permissions']
        }
        assert can_view_report(User(finance_permissions), finance_meta,
                               check_license=False)
        assert not can_view_report(
            User(finance_permissions - {('students', 'view')}), finance_meta,
            check_license=False,
        )
        assert not can_view_report(User({('finance', 'view')}), finance_meta,
                                   check_license=False)

        composite_meta = REPORT_CATALOG['course-ranking']
        complete = {
            ('reports', 'view'), ('finance', 'view'),
            ('registration', 'view'), ('courses', 'view'),
        }
        assert can_view_report(User(complete), composite_meta, check_license=False)
        assert not can_view_report(
            User(complete - {('registration', 'view')}),
            composite_meta, check_license=False,
        )

        cash_flow_meta = REPORT_CATALOG['cash-flow']
        assert not can_view_report(User({
            ('reports', 'view'), ('accounting', 'view'),
        }), cash_flow_meta, check_license=False)
        assert can_view_report(User({
            ('reports', 'view'), ('accounting', 'view'), ('finance', 'view'),
        }), cash_flow_meta, check_license=False)

    def test_core_professional_accounting_reports_are_registered(self):
        required = {
            'journal', 'general-ledger', 'subsidiary-ledger', 'detail-ledger',
            'trial-balance-2', 'trial-balance-4', 'trial-balance-6',
            'trial-balance-8', 'balance-sheet', 'profit-loss', 'cash-flow',
            'receivables-aging', 'budget-actual', 'bank-reconciliation',
            'payroll-summary', 'payroll-tax', 'tax-control-summary',
            'statutory-accounts',
        }
        assert required <= set(REPORT_CATALOG)


class TestReportFilters:
    def test_user_facing_reporting_clock_defaults_to_tehran(self, monkeypatch):
        monkeypatch.delenv('APP_TIMEZONE', raising=False)
        assert timezone_name() == 'Asia/Tehran'
        assert local_now().utcoffset() == timedelta(hours=3, minutes=30)
        monkeypatch.setenv('APP_TIMEZONE', 'Not/A-Timezone')
        assert timezone_name() == 'Asia/Tehran'

    def test_persian_jalali_dates_and_branch_scope_are_normalised(self):
        filters = ReportFilters.from_mapping({
            'date_from': '۱۴۰۵/۰۶/۱۱',
            'date_to': '۱۴۰۵/۰۶/۱۲',
            'branch_id': '999',
            'per_page': '5000',
        }, _User())
        assert filters.date_from == date(2026, 9, 2)
        assert filters.date_to == date(2026, 9, 3)
        assert filters.branch_id == 7
        assert filters.forced_branch_id == 7
        assert filters.per_page == 200

    def test_cross_module_drilldowns_follow_view_permissions(self):
        class User:
            is_admin = False
            branch_id = 3

            def has_permission(self, module, action):
                return action == 'view' and module in {'reports', 'finance', 'students'}

        filters = ReportFilters.from_mapping({}, User())
        assert filters.visible_modules == frozenset({'finance', 'students'})

    def test_non_finite_financial_input_is_rejected(self):
        assert safe_float('nan', 0) == 0
        assert safe_float('inf', 0) == 0

    def test_inverted_date_range_is_swapped(self):
        filters = ReportFilters.from_mapping({
            'date_from': '1405/06/12', 'date_to': '1405/06/11'
        })
        assert filters.date_from <= filters.date_to

    def test_explicit_open_date_range_survives_links_and_exports(self):
        filters = ReportFilters.from_mapping({'date_from': '', 'date_to': ''})
        query = filters.as_query_dict(include_paging=False)
        saved = filters.serialisable()
        assert query['date_from'] == saved['date_from'] == ''
        assert query['date_to'] == saved['date_to'] == ''

    def test_persian_search_normalisation(self):
        assert normalise_text('  علي كريمي ۱۲۳  ') == 'علی کریمی 123'
        assert normalise_text('۵٬۰۰۰٬۰۰۰٫۵') == '5000000.5'
        assert _matches_query({'amount': Decimal('5000000.50')}, '۵٬۰۰۰٬۰۰۰')
        assert _matches_query({'date': date(2026, 9, 2)}, '۱۴۰۵/۰۶/۱۱')

    def test_previous_jalali_year_clamps_leap_esfand(self):
        current = parse_jalali_date('1403/12/30')
        assert gregorian_to_jalali(_previous_jalali_year(current)) == '1402/12/29'

    def test_previous_jalali_month_preserves_preferred_day_or_clamps(self):
        current = parse_jalali_date('1405/01/30')
        assert gregorian_to_jalali(_previous_jalali_month(current)) == '1404/12/29'
        current = parse_jalali_date('1405/07/15')
        assert gregorian_to_jalali(_previous_jalali_month(current)) == '1405/06/15'

    def test_datetime_range_includes_the_entire_last_day(self):
        from sqlalchemy import DateTime, column, select
        filters = ReportFilters(date_from=date(2026, 9, 1), date_to=date(2026, 9, 2))
        statement = _query_range(select(column('created_at', DateTime)),
                                 column('created_at', DateTime), filters)
        values = list(statement.compile().params.values())
        assert datetime(2026, 9, 1, 0, 0) in values
        assert datetime(2026, 9, 3, 0, 0) in values

    def test_non_paginated_report_announces_the_export_ceiling(self, monkeypatch):
        key = '__export_ceiling_test__'
        monkeypatch.setitem(REPORT_CATALOG, key, {
            'title': 'آزمون سقف خروجی', 'description': 'آزمون',
            'category': 'accounting', 'builder': key, 'variant': None,
            'filters': ('date',), 'license_features': ('reports',),
        })
        monkeypatch.setitem(BUILDERS, key, lambda filters: {
            'columns': [{'key': 'row', 'label': 'ردیف', 'type': 'number'}],
            'rows': [{'row': index} for index in range(50001)],
            'kpis': [], 'chart': None, 'warnings': [], 'footers': {},
        })

        result = run_report(key, ReportFilters(), paginate=False)
        preview = run_report(key, ReportFilters(per_page=25), paginate=True)

        assert result['total_rows'] == 50001
        assert len(result['rows']) == 50000
        assert any('۵۰٬۰۰۰' in warning for warning in result['warnings'])
        assert len(preview['rows']) == 25
        assert any('۵۰٬۰۰۰' in warning for warning in preview['warnings'])


class TestReportExports:
    @staticmethod
    def _result():
        return {
            'meta': {'key': 'sample', 'title': 'گزارش نمونه'},
            'generated_at': datetime(2026, 9, 2, 12, 30),
            'columns': [
                {'key': 'name', 'label': 'نام', 'type': 'text'},
                {'key': 'amount', 'label': 'مبلغ', 'type': 'money'},
                {'key': 'date', 'label': 'تاریخ', 'type': 'date'},
            ],
            'rows': [{'name': 'آزمایش', 'amount': Decimal('1250000'),
                      'date': date(2026, 9, 2)}],
        }

    def test_csv_is_excel_compatible_utf8_bom(self):
        data = csv_bytes(self._result())
        assert data.startswith(b'\xef\xbb\xbf')
        assert 'آزمایش'.encode() in data
        assert '1,250,000'.encode() in data

    def test_excel_is_a_valid_zip_workbook(self):
        data = excel_bytes(self._result())
        assert data.startswith(b'PK')
        assert len(data) > 1000

    def test_json_keeps_machine_values_and_persian_metadata(self):
        data = json_bytes(self._result())
        payload = json.loads(data)
        assert 'گزارش نمونه'.encode() in data
        assert 'آزمایش'.encode() in data
        assert payload['columns'][1]['type'] == 'money'
        assert payload['rows'][0]['amount'] == 1250000.0
        assert payload['total_rows'] == payload['exported_rows'] == 1

    def test_json_replaces_non_finite_numbers_with_null(self):
        poisoned = self._result()
        poisoned['rows'][0]['amount'] = Decimal('NaN')
        poisoned['chart'] = {'series': [float('inf')]}
        data = json_bytes(poisoned)
        payload = json.loads(data)
        assert payload['rows'][0]['amount'] is None
        assert payload['chart']['series'][0] is None
        assert b'NaN' not in data and b'Infinity' not in data

    def test_spreadsheet_formula_injection_is_neutralised(self):
        assert spreadsheet_safe('=HYPERLINK("bad")').startswith("'=")
        assert spreadsheet_safe('@SUM(A1:A2)').startswith("'@")
        assert spreadsheet_safe('متن عادی') == 'متن عادی'
        poisoned = self._result()
        poisoned['rows'][0]['amount'] = '=1+1'
        assert b"'=1+1" in csv_bytes(poisoned)

    def test_concurrent_scheduled_exports_get_unique_names(self, tmp_path):
        first = write_export_file(self._result(), 'json', tmp_path)
        second = write_export_file(self._result(), 'json', tmp_path)
        assert first != second
        assert first.exists() and second.exists()


class TestBudgetPeriods:
    def test_jalali_month_has_exact_inclusive_boundaries(self):
        item = SimpleNamespace(fiscal_year='1405', period='month', period_no=6)
        start, end = _budget_period_bounds(item)
        assert gregorian_to_jalali(start) == '1405/06/01'
        assert gregorian_to_jalali(end) == '1405/06/31'

    def test_fourth_quarter_crosses_to_next_jalali_year(self):
        item = SimpleNamespace(fiscal_year='1405', period='quarter', period_no=4)
        start, end = _budget_period_bounds(item)
        assert gregorian_to_jalali(start) == '1405/10/01'
        assert gregorian_to_jalali(end) in ('1405/12/29', '1405/12/30')


class TestReportScheduling:
    def test_daily_and_weekly_next_run(self):
        moment = datetime(2026, 9, 2, 8, 0)
        assert next_run(moment, 'daily') == datetime(2026, 9, 3, 8, 0)
        assert next_run(moment, 'weekly') == datetime(2026, 9, 9, 8, 0)

    def test_jalali_month_end_is_clamped_without_permanent_day_drift(self):
        moment = datetime.combine(parse_jalali_date('1404/11/30'), datetime.min.time()).replace(hour=8)
        esfand = next_run(moment, 'monthly', schedule_day=30)
        assert gregorian_to_jalali(esfand) == '1404/12/29'
        farvardin = next_run(esfand, 'monthly', schedule_day=30)
        assert gregorian_to_jalali(farvardin) == '1405/01/30'
