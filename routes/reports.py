"""Unified accounting, financial, educational and management reports."""
from __future__ import annotations

import json
import re
from datetime import date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode, urlsplit

from flask import (
    Blueprint, abort, flash, jsonify, redirect, render_template, request, url_for,
)
from flask_login import current_user, login_required
from sqlalchemy.exc import IntegrityError

from extensions import db
from license_client import license_required, licensed_section
from utils.access_control import require_permission
from utils.jalali import gregorian_to_jalali, gregorian_to_jalali_obj, parse_jalali_date
from utils.local_time import local_now_naive, local_today
from utils.report_exports import display_value, export_response, selected_columns
from utils.reporting import (
    CATEGORY_LABELS, REPORT_CATALOG, REPORT_STATUS_VALUES, STATUS_LABELS,
    ReportFilters, can_view_report, catalog_for_user, default_date_range,
    run_report, serialise_result, serialise_value,
)

reports_bp = Blueprint('reports', __name__)
MAX_MONEY = Decimal('9999999999999999.99')


def _json_load(value, fallback):
    try:
        parsed = json.loads(value or '')
        return parsed if isinstance(parsed, type(fallback)) else fallback
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback


def _json_payload() -> dict:
    payload = request.get_json(silent=True)
    if isinstance(payload, dict):
        return payload
    return request.form.to_dict(flat=True)


def _safe_return_url(default: str) -> str:
    """Use the referrer for report modals only when it is same-origin."""
    candidate = request.referrer
    if not candidate:
        return default
    parsed = urlsplit(candidate)
    if parsed.scheme in ('http', 'https') and parsed.netloc == request.host:
        return candidate
    if (not parsed.scheme and not parsed.netloc and candidate.startswith('/')
            and not candidate.startswith('//') and '\\' not in candidate):
        return candidate
    return default


def _parse_decimal(value) -> Decimal | None:
    text = str(value if value is not None else '').translate(
        str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789')
    )
    text = text.replace(',', '').replace('٬', '').replace('٫', '.').strip()
    if not text:
        return None
    try:
        parsed = Decimal(text)
        return parsed if parsed.is_finite() else None
    except (InvalidOperation, ValueError):
        return None


def _safe_decimal(value) -> Decimal:
    return _parse_decimal(value) or Decimal('0')


def _require_source_feature(name: str) -> None:
    from license_client import has_feature
    if not has_feature(name):
        abort(403)


def _can_report_action(action: str) -> bool:
    return bool(current_user.is_admin or current_user.has_permission('reports', action))


def _require_report_action(action: str) -> None:
    if not _can_report_action(action):
        abort(403)


def _report_or_404(report_key: str) -> dict:
    meta = REPORT_CATALOG.get(report_key)
    if not meta:
        abort(404)
    if not can_view_report(current_user, meta):
        abort(403)
    return meta


def _report_filters(meta: dict, values, user) -> ReportFilters:
    """Normalise only filters declared by the report's catalogue contract."""
    data = values.to_dict(flat=True) if hasattr(values, 'to_dict') else dict(values or {})
    declared = set(meta.get('filters', ()))
    fields_by_filter = {
        'date': {'date_from', 'date_to'}, 'branch': {'branch_id'},
        'course': {'course_id'}, 'class': {'class_id'},
        'teacher': {'teacher_id'}, 'student': {'student_id'},
        'account': {'account_id'}, 'fiscal': {'fiscal_id'},
        'status': {'status'}, 'q': {'q'},
    }
    allowed_fields = {'page', 'per_page', 'sort', 'direction'}
    for filter_name in declared:
        allowed_fields.update(fields_by_filter.get(filter_name, ()))
    if 'date' in declared:
        allowed_fields.add('compare')
    for field_name in set().union(*fields_by_filter.values(), {'compare'}):
        if field_name not in allowed_fields:
            data.pop(field_name, None)

    if 'date' in declared:
        default_from, default_to = default_date_range()
        # A malformed non-empty boundary must never turn a bounded report into
        # an accidental all-history query.  Blank boundaries remain a valid
        # explicit request for an open-ended report.
        if data.get('date_from') and parse_jalali_date(data['date_from']) is None:
            data['date_from'] = default_from
        if data.get('date_to') and parse_jalali_date(data['date_to']) is None:
            data['date_to'] = default_to

        if meta.get('date_mode') == 'as_of':
            data.pop('date_from', None)
            if not data.get('date_to'):
                data['date_to'] = default_to
        else:
            fiscal_id = data.get('fiscal_id') if 'fiscal' in declared else None
            try:
                fiscal_id = int(fiscal_id) if fiscal_id not in (None, '') else None
            except (TypeError, ValueError):
                fiscal_id = None
            # A selected fiscal period remains authoritative when no explicit
            # boundaries were supplied (including URLs with blank inputs).
            if fiscal_id and not data.get('date_from') and not data.get('date_to'):
                from models.accounting import FiscalPeriod
                period = db.session.get(FiscalPeriod, fiscal_id)
                if period:
                    data['date_from'] = gregorian_to_jalali(period.start_date)
                    data['date_to'] = gregorian_to_jalali(period.end_date)
            if 'date_from' not in data and 'date_to' not in data:
                data['date_from'], data['date_to'] = default_from, default_to

    allowed_statuses = REPORT_STATUS_VALUES.get(meta.get('builder'), ())
    if data.get('status') and data.get('status') not in allowed_statuses:
        data['status'] = ''
    return ReportFilters.from_mapping(data, user)


def _filter_options(meta: dict) -> dict:
    """Only load selector data required by the current report."""
    filters = set(meta.get('filters', ()))
    options = {'statuses': []}
    if 'branch' in filters:
        from models.system import Branch
        query = Branch.query
        if not current_user.is_admin and current_user.branch_id:
            query = query.filter_by(id=current_user.branch_id)
        options['branches'] = query.order_by(Branch.name).all()
    if 'course' in filters:
        from models.course import Course
        query = Course.query
        if not current_user.is_admin and current_user.branch_id:
            query = query.filter(db.or_(Course.branch_id == current_user.branch_id, Course.branch_id.is_(None)))
        options['courses'] = query.order_by(Course.title).all()
    if 'class' in filters:
        from models.classes import ClassGroup
        query = ClassGroup.query
        if not current_user.is_admin and current_user.branch_id:
            query = query.filter_by(branch_id=current_user.branch_id)
        options['classes'] = query.order_by(ClassGroup.name).all()
    if 'teacher' in filters:
        from models.teacher import Teacher
        query = Teacher.query
        if not current_user.is_admin and current_user.branch_id:
            query = query.filter_by(branch_id=current_user.branch_id)
        options['teachers'] = query.order_by(Teacher.last_name, Teacher.first_name).all()
    if 'student' in filters:
        from models.student import Student
        query = Student.query
        if not current_user.is_admin and current_user.branch_id:
            query = query.filter_by(branch_id=current_user.branch_id)
        options['students'] = query.order_by(Student.last_name, Student.first_name).limit(1500).all()
    if 'account' in filters:
        from models.accounting import Account
        options['accounts'] = Account.query.order_by(Account.code).all()
    if 'fiscal' in filters:
        from models.accounting import FiscalPeriod
        options['fiscal_periods'] = FiscalPeriod.query.order_by(FiscalPeriod.start_date.desc()).all()
    if 'status' in filters:
        options['statuses'] = [
            (value, STATUS_LABELS.get(value, value))
            for value in REPORT_STATUS_VALUES.get(meta.get('builder'), ())
        ]
    return options


def _active_filter_chips(filters: ReportFilters, options: dict,
                         meta: dict | None = None) -> list[tuple[str, str]]:
    chips: list[tuple[str, str]] = []
    if filters.q:
        chips.append(('جستجو', filters.q))
    if filters.date_from:
        chips.append(('از', gregorian_to_jalali(filters.date_from)))
    if filters.date_to:
        chips.append(('تا', gregorian_to_jalali(filters.date_to)))
    selectors = (
        ('branch_id', 'شعبه', 'branches', 'name'),
        ('course_id', 'دوره', 'courses', 'title'),
        ('class_id', 'کلاس', 'classes', 'name'),
        ('teacher_id', 'مدرس', 'teachers', 'full_name'),
        ('student_id', 'هنرجو', 'students', 'full_name'),
        ('account_id', 'حساب', 'accounts', 'name'),
        ('fiscal_id', 'دوره مالی', 'fiscal_periods', 'name'),
    )
    for attribute, label, option_key, display_attribute in selectors:
        selected_id = getattr(filters, attribute)
        if not selected_id:
            continue
        selected = next((item for item in options.get(option_key, []) if item.id == selected_id), None)
        chips.append((label, getattr(selected, display_attribute, str(selected_id))))
    if filters.status:
        status_label = dict(options.get('statuses', [])).get(filters.status, filters.status)
        chips.append(('وضعیت', status_label))
    if filters.compare:
        previous_label = ('ماه قبل' if (meta or {}).get('date_mode') == 'as_of'
                          else 'دوره قبل')
        chips.append(('مقایسه', 'سال قبل' if filters.compare == 'year'
                      else previous_label))
    return chips


def _audit(action: str, report_key: str, description: str) -> None:
    from models.user import ActivityLog
    try:
        db.session.add(ActivityLog(
            user_id=current_user.id, action=action, module='reports',
            entity_type='report', description=description,
            ip_address=str(request.headers.get('X-Forwarded-For', request.remote_addr) or '')
            .split(',')[0].strip()[:50] or None,
        ))
        db.session.commit()
    except Exception:
        db.session.rollback()


@reports_bp.route('/')
@license_required
@login_required
@licensed_section('reports')
@require_permission('reports', 'view')
def index():
    from models.reporting import (
        ReportExportLog, ReportFavorite, ReportPreset, ReportSchedule, ReportSnapshot,
    )

    catalog = catalog_for_user(current_user)
    grouped = OrderedGroups(CATEGORY_LABELS)
    for key, meta in catalog.items():
        grouped.add(meta['category'], meta)

    filters = _report_filters(REPORT_CATALOG['executive-dashboard'], request.args, current_user)
    dashboard = run_report('executive-dashboard', filters, paginate=False)
    visible_keys = list(catalog)
    favorite_keys = {
        item.report_key for item in ReportFavorite.query.filter_by(user_id=current_user.id).all()
        if item.report_key in catalog
    }
    presets = (ReportPreset.query.filter_by(user_id=current_user.id)
               .filter(ReportPreset.report_key.in_(visible_keys))
               .order_by(ReportPreset.updated_at.desc()).limit(12).all())
    schedules = (ReportSchedule.query.filter_by(user_id=current_user.id)
                 .filter(ReportSchedule.report_key.in_(visible_keys))
                 .order_by(ReportSchedule.is_active.desc(), ReportSchedule.next_run_at).limit(12).all())
    snapshots = (ReportSnapshot.query.filter_by(user_id=current_user.id)
                 .filter(ReportSnapshot.report_key.in_(visible_keys))
                 .order_by(ReportSnapshot.created_at.desc()).limit(8).all())
    exports = (ReportExportLog.query.filter_by(user_id=current_user.id)
               .filter(ReportExportLog.report_key.in_(visible_keys))
               .order_by(ReportExportLog.created_at.desc()).limit(8).all())
    start_of_year, today = default_date_range()
    return render_template(
        'reports/index.html', catalog=catalog, grouped_catalog=grouped.items,
        dashboard=dashboard, favorite_keys=favorite_keys, presets=presets,
        schedules=schedules, snapshots=snapshots, exports=exports,
        start_of_year=start_of_year, today=today, filters=filters,
        categories=CATEGORY_LABELS,
    )


class OrderedGroups:
    def __init__(self, labels):
        self.items = [(key, label, []) for key, label in labels.items()]
        self._lookup = {key: rows for key, _label, rows in self.items}

    def add(self, key, value):
        self._lookup.setdefault(key, []).append(value)


@reports_bp.route('/view/<report_key>')
@login_required
@require_permission('reports', 'view')
def view(report_key):
    meta = _report_or_404(report_key)
    print_mode = request.args.get('print') == '1'
    if print_mode:
        _require_report_action('print')
    filters = _report_filters(meta, request.args, current_user)
    result = run_report(report_key, filters, paginate=not print_mode)
    requested_columns = [
        value[:80] for value in request.args.get('columns', '').split(',')[:100]
        if value
    ]
    print_columns = selected_columns(result, requested_columns or None)
    print_landscape = len(print_columns) > 6
    if print_mode:
        result['columns'] = print_columns
    options = _filter_options(meta)
    from models.reporting import ReportFavorite, ReportPreset
    is_favorite = ReportFavorite.query.filter_by(
        user_id=current_user.id, report_key=report_key
    ).first() is not None
    presets = (ReportPreset.query.filter_by(user_id=current_user.id, report_key=report_key)
               .order_by(ReportPreset.updated_at.desc()).all())
    start_of_year, today = default_date_range()
    audit_action = 'print' if print_mode else 'view'
    audit_label = 'چاپ' if print_mode else 'مشاهده'
    _audit(audit_action, report_key, f'{audit_label} گزارش «{meta["title"]}»')
    query_without_page = urlencode(filters.as_query_dict(include_paging=False))
    return render_template(
        'reports/view.html', report=result, meta=dict(meta, key=report_key),
        filters=filters, options=options, is_favorite=is_favorite,
        presets=presets, start_of_year=start_of_year, today=today,
        query_without_page=query_without_page, print_mode=print_mode,
        print_landscape=print_landscape,
        active_filter_chips=_active_filter_chips(filters, options, meta),
    )


@reports_bp.route('/api/run/<report_key>')
@login_required
@require_permission('reports', 'view')
def api_run(report_key):
    meta = _report_or_404(report_key)
    filters = _report_filters(meta, request.args, current_user)
    return jsonify(serialise_result(run_report(report_key, filters)))


@reports_bp.route('/export/<report_key>/<export_format>')
@login_required
@require_permission('reports', 'view')
def export(report_key, export_format):
    _require_report_action('export')
    _require_source_feature('export_data')
    meta = _report_or_404(report_key)
    if export_format not in ('csv', 'xlsx', 'json', 'pdf'):
        abort(404)
    filters = _report_filters(meta, request.args, current_user)
    result = run_report(report_key, filters, paginate=False)
    raw_columns = request.args.get('columns', '')
    keys = [
        key[:80] for key in raw_columns.split(',')[:100]
        if re.fullmatch(r'[A-Za-z0-9_]{1,80}', key)
    ] or None

    from models.reporting import ReportExportLog
    try:
        if export_format == 'pdf':
            from utils.pdf_helpers import build_table_pdf
            columns = selected_columns(result, keys)
            headers = [column['label'] for column in columns]
            pdf_source = result['rows'][:5000]
            rows = [[display_value(row.get(column['key']), column.get('type', 'text'))
                     for column in columns] for row in pdf_source]
            filename = f'{report_key}-{local_now_naive():%Y%m%d-%H%M}.pdf'
            subtitle = f'تعداد ردیف: {len(rows)}'
            if result['total_rows'] > len(rows):
                subtitle += f' (از {result["total_rows"]} ردیف؛ برای خروجی کامل از Excel استفاده کنید)'
            if filters.date_from or filters.date_to:
                date_from_label = (
                    request.args.get('date_from') if 'date_from' in request.args
                    else gregorian_to_jalali(filters.date_from)
                ) or 'ابتدا'
                date_to_label = (
                    request.args.get('date_to') if 'date_to' in request.args
                    else gregorian_to_jalali(filters.date_to)
                ) or 'انتها'
                subtitle += f' | بازه: {date_from_label} تا {date_to_label}'
            response = build_table_pdf(
                meta['title'], headers, rows, filename, subtitle=subtitle,
                landscape_mode=len(columns) > 5,
                download=request.args.get('download', '1') == '1',
            )
            db.session.add(ReportExportLog(
                user_id=current_user.id, report_key=report_key,
                export_format='pdf', row_count=len(rows), file_name=None,
            ))
            db.session.commit()
            _audit('export', report_key, f'خروجی PDF گزارش «{meta["title"]}» با {len(rows)} ردیف')
            return response
        response = export_response(result, export_format, keys)
        db.session.add(ReportExportLog(
            user_id=current_user.id, report_key=report_key,
            export_format=export_format, row_count=len(result['rows']),
            file_name=None,
        ))
        db.session.commit()
        _audit('export', report_key, f'خروجی {export_format.upper()} گزارش «{meta["title"]}»')
        return response
    except Exception as exc:
        db.session.rollback()
        try:
            db.session.add(ReportExportLog(
                user_id=current_user.id, report_key=report_key,
                export_format=export_format, status='failed', error_message=str(exc)[:1000],
            ))
            db.session.commit()
        except Exception:
            db.session.rollback()
        raise


@reports_bp.route('/api/favorites/<report_key>', methods=['POST', 'DELETE'])
@login_required
@require_permission('reports', 'view')
def favorite(report_key):
    _report_or_404(report_key)
    from models.reporting import ReportFavorite
    query = ReportFavorite.query.filter_by(user_id=current_user.id, report_key=report_key)
    item = query.first()
    if request.method == 'DELETE':
        if item:
            db.session.delete(item)
        db.session.commit()
        return jsonify({'ok': True, 'favorite': False})

    # POST means "ensure favorite", not "toggle".  Besides being retry-safe,
    # this prevents two delayed clicks/tabs from accidentally undoing each
    # other.  The uniqueness constraint remains the final concurrency guard.
    if not item:
        db.session.add(ReportFavorite(user_id=current_user.id, report_key=report_key))
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            if query.first() is None:
                raise
    return jsonify({'ok': True, 'favorite': True})


@reports_bp.route('/api/presets', methods=['GET', 'POST'])
@login_required
@require_permission('reports', 'view')
def presets():
    from models.reporting import ReportPreset
    if request.method == 'GET':
        key = request.args.get('report_key', '')
        query = ReportPreset.query.filter_by(user_id=current_user.id)
        if key:
            _report_or_404(key)
            query = query.filter_by(report_key=key)
        else:
            query = query.filter(ReportPreset.report_key.in_(list(catalog_for_user(current_user))))
        return jsonify({'items': [{
            'id': p.id, 'name': p.name, 'report_key': p.report_key,
            'filters': _json_load(p.filters_json, {}),
            'columns': _json_load(p.columns_json, []), 'favorite': p.is_favorite,
        } for p in query.order_by(ReportPreset.updated_at.desc()).all()]})

    payload = _json_payload()
    report_key = str(payload.get('report_key') or '')
    meta = _report_or_404(report_key)
    name = str(payload.get('name') or '').strip()[:120]
    if not name:
        return jsonify({'ok': False, 'error': 'نام نما الزامی است'}), 400
    filters = payload.get('filters', {})
    if isinstance(filters, str):
        filters = _json_load(filters, {})
    if not isinstance(filters, dict):
        return jsonify({'ok': False, 'error': 'ساختار فیلترها معتبر نیست'}), 400
    filters = _report_filters(meta, filters, current_user).serialisable()
    columns = payload.get('columns', [])
    if isinstance(columns, str):
        columns = [part for part in columns.split(',') if part]
    if not isinstance(columns, list):
        return jsonify({'ok': False, 'error': 'ساختار ستون‌ها معتبر نیست'}), 400
    columns = [
        str(value)[:80] for value in columns[:100]
        if re.fullmatch(r'[A-Za-z0-9_]{1,80}', str(value))
    ]
    preset_query = ReportPreset.query.filter_by(
        user_id=current_user.id, report_key=report_key, name=name
    )
    preset = preset_query.first() or ReportPreset(
        user_id=current_user.id, report_key=report_key, name=name
    )
    filters_json = json.dumps(filters, ensure_ascii=False)
    columns_json = json.dumps(columns, ensure_ascii=False)
    is_favorite = str(payload.get('is_favorite', '')).lower() in ('1', 'true', 'on')

    def assign_values(target):
        target.filters_json = filters_json
        target.columns_json = columns_json
        target.is_favorite = is_favorite

    assign_values(preset)
    db.session.add(preset)
    try:
        db.session.commit()
    except IntegrityError:
        # A same-name save can race in another tab.  Re-load the winning row
        # and apply this request instead of surfacing a uniqueness-error page.
        db.session.rollback()
        preset = preset_query.first()
        if preset is None:
            raise
        assign_values(preset)
        db.session.commit()
    return jsonify({'ok': True, 'id': preset.id, 'name': preset.name})


@reports_bp.route('/api/presets/<int:preset_id>', methods=['DELETE'])
@login_required
@require_permission('reports', 'view')
def delete_preset(preset_id):
    from models.reporting import ReportPreset
    preset = ReportPreset.query.filter_by(id=preset_id, user_id=current_user.id).first_or_404()
    db.session.delete(preset)
    db.session.commit()
    return jsonify({'ok': True})


@reports_bp.route('/presets/<int:preset_id>/apply')
@login_required
@require_permission('reports', 'view')
def apply_preset(preset_id):
    from models.reporting import ReportPreset
    preset = ReportPreset.query.filter_by(id=preset_id, user_id=current_user.id).first_or_404()
    _report_or_404(preset.report_key)
    filters = _json_load(preset.filters_json, {})
    if preset.columns_json:
        columns = _json_load(preset.columns_json, [])
        columns = [str(value)[:80] for value in columns[:100]
                   if re.fullmatch(r'[A-Za-z0-9_]{1,80}', str(value))]
        if columns:
            filters['columns'] = ','.join(columns)
    return redirect(url_for('reports.view', report_key=preset.report_key) + '?' + urlencode(filters))


@reports_bp.route('/exports/<int:export_id>/download')
@login_required
@require_permission('reports', 'view')
def download_scheduled_export(export_id):
    _require_report_action('export')
    _require_source_feature('export_data')
    import os
    from flask import current_app, send_from_directory
    from models.reporting import ReportExportLog
    item = ReportExportLog.query.filter_by(
        id=export_id, user_id=current_user.id
    ).first_or_404()
    _report_or_404(item.report_key)
    filename = os.path.basename(item.file_name or '')
    folder = os.path.join(current_app.instance_path, 'report_exports')
    if not filename or not os.path.isfile(os.path.join(folder, filename)):
        abort(404)
    return send_from_directory(folder, filename, as_attachment=True, download_name=filename)


@reports_bp.route('/api/snapshots', methods=['POST'])
@login_required
@require_permission('reports', 'view')
def snapshot():
    from models.reporting import ReportSnapshot
    payload = _json_payload()
    report_key = str(payload.get('report_key') or '')
    meta = _report_or_404(report_key)
    raw_filters = payload.get('filters', {})
    if isinstance(raw_filters, str):
        raw_filters = _json_load(raw_filters, {})
    if not isinstance(raw_filters, dict):
        return jsonify({'ok': False, 'error': 'ساختار فیلترها معتبر نیست'}), 400
    filters = _report_filters(meta, raw_filters, current_user)
    result = run_report(report_key, filters, paginate=False)
    item = ReportSnapshot(
        user_id=current_user.id, report_key=report_key,
        title=(str(payload.get('title') or '').strip()[:180] or meta['title']),
        filters_json=json.dumps(filters.serialisable(), ensure_ascii=False),
        metrics_json=json.dumps([
            {**metric, 'value': serialise_value(metric.get('value'))}
            for metric in result['kpis']
        ], ensure_ascii=False),
        row_count=result['total_rows'],
    )
    db.session.add(item)
    db.session.commit()
    return jsonify({'ok': True, 'id': item.id})


@reports_bp.route('/snapshots/<int:snapshot_id>/apply')
@login_required
@require_permission('reports', 'view')
def apply_snapshot(snapshot_id):
    from models.reporting import ReportSnapshot
    item = ReportSnapshot.query.filter_by(id=snapshot_id, user_id=current_user.id).first_or_404()
    _report_or_404(item.report_key)
    filters = _json_load(item.filters_json, {})
    location = url_for('reports.view', report_key=item.report_key)
    return redirect(location + (('?' + urlencode(filters)) if filters else ''))


@reports_bp.route('/builder')
@login_required
@require_permission('reports', 'view')
def builder():
    """Safe no-code report builder backed by the vetted report catalogue."""
    from models.system import Branch
    branches = Branch.query.order_by(Branch.name).all()
    if not current_user.is_admin and current_user.branch_id:
        branches = [item for item in branches if item.id == current_user.branch_id]
    return render_template(
        'reports/builder.html', catalog=catalog_for_user(current_user),
        categories=CATEGORY_LABELS, branches=branches,
        start_of_year=default_date_range()[0], today=default_date_range()[1],
    )


@reports_bp.route('/schedules', methods=['GET', 'POST'])
@login_required
@require_permission('reports', 'view')
def schedules():
    from models.reporting import ReportSchedule
    if request.method == 'POST':
        _require_report_action('export')
        _require_source_feature('export_data')
        payload = _json_payload()
        report_key = str(payload.get('report_key') or '')
        meta = _report_or_404(report_key)
        name = str(payload.get('name') or '').strip()[:120]
        if not name:
            flash('نام زمان‌بندی الزامی است', 'danger')
            return redirect(_safe_return_url(url_for('reports.index')))
        frequency = str(payload.get('frequency') or 'monthly')
        export_format = str(payload.get('export_format') or 'xlsx')
        delivery = str(payload.get('delivery_method') or 'internal')
        if frequency not in ('daily', 'weekly', 'monthly'):
            frequency = 'monthly'
        if export_format not in ('xlsx', 'csv', 'json'):
            export_format = 'xlsx'
        if delivery not in ('internal', 'bale', 'telegram', 'email'):
            delivery = 'internal'
        raw_run_date = str(payload.get('run_date') or '').strip()
        run_date = parse_jalali_date(raw_run_date) if raw_run_date else local_today()
        run_time = str(payload.get('run_time') or '08:00')
        if run_date is None:
            flash('تاریخ اولین اجرا معتبر نیست', 'danger')
            return redirect(_safe_return_url(url_for('reports.schedules')))
        try:
            parts = run_time.split(':')
            if len(parts) != 2:
                raise ValueError
            hour, minute = (int(parts[0]), int(parts[1]))
            next_run = datetime.combine(run_date, time(hour, minute))
        except (ValueError, TypeError):
            flash('ساعت اجرای گزارش معتبر نیست', 'danger')
            return redirect(_safe_return_url(url_for('reports.schedules')))
        run_jalali = gregorian_to_jalali_obj(run_date)
        schedule_day = run_jalali.day if run_jalali else None
        now = local_now_naive()
        if next_run <= now:
            next_run = _future_schedule(next_run, frequency, schedule_day, now)
        raw_filters = payload.get('filters', {})
        if isinstance(raw_filters, str):
            try:
                raw_filters = json.loads(raw_filters or '{}')
            except (TypeError, ValueError, json.JSONDecodeError):
                raw_filters = None
        if not isinstance(raw_filters, dict):
            flash('فیلترهای زمان‌بندی معتبر نیستند', 'danger')
            return redirect(_safe_return_url(url_for('reports.schedules')))
        allowed_filter_keys = {
            'date_from', 'date_to', 'branch_id', 'course_id', 'class_id',
            'teacher_id', 'student_id', 'account_id', 'fiscal_id', 'status',
            'q', 'sort', 'direction', 'compare', 'per_page', 'columns',
        }
        clean_filters = {}
        for key, value in raw_filters.items():
            if key not in allowed_filter_keys:
                continue
            if key == 'columns':
                candidates = value if isinstance(value, list) else str(value or '').split(',')
                value = ','.join(
                    str(item)[:80] for item in candidates[:100]
                    if re.fullmatch(r'[A-Za-z0-9_]{1,80}', str(item))
                )
            if isinstance(value, (str, int, float, bool)):
                clean_filters[key] = str(value)[:500]
        column_spec = clean_filters.pop('columns', '')
        supplied_date_keys = {'date_from', 'date_to'} & set(clean_filters)
        clean_filters = _report_filters(meta, clean_filters, current_user).serialisable()
        # If no date was supplied, keep the schedule dynamic: the worker will
        # inject the then-current Jalali year/date on every occurrence.
        if not supplied_date_keys:
            clean_filters.pop('date_from', None)
            clean_filters.pop('date_to', None)
        if column_spec:
            clean_filters['columns'] = column_spec
        raw_filters = json.dumps(clean_filters, ensure_ascii=False)
        recipient = str(payload.get('recipient') or '').strip()[:250] or None
        if delivery == 'internal':
            recipient = None
        if delivery in ('telegram', 'email') and not recipient:
            flash('برای این روش تحویل، گیرنده الزامی است', 'danger')
            return redirect(_safe_return_url(url_for('reports.schedules')))
        if delivery == 'email':
            from email.utils import parseaddr
            address = parseaddr(recipient)[1]
            if address != recipient or '@' not in address or address.startswith('@') or address.endswith('@'):
                flash('نشانی ایمیل گیرنده معتبر نیست', 'danger')
                return redirect(_safe_return_url(url_for('reports.schedules')))
        schedule = ReportSchedule(
            user_id=current_user.id, name=name, report_key=report_key,
            filters_json=raw_filters, export_format=export_format,
            frequency=frequency, schedule_day=schedule_day, delivery_method=delivery,
            recipient=recipient, next_run_at=next_run,
        )
        db.session.add(schedule)
        db.session.commit()
        flash('زمان‌بندی گزارش ذخیره شد', 'success')
        return redirect(_safe_return_url(url_for('reports.index')))

    items = (ReportSchedule.query.filter_by(user_id=current_user.id)
             .order_by(ReportSchedule.is_active.desc(), ReportSchedule.next_run_at).all())
    return render_template('reports/schedules.html', schedules=items,
                           catalog=catalog_for_user(current_user), today=default_date_range()[1])


def _future_schedule(moment: datetime, frequency: str, schedule_day: int | None,
                     now: datetime | None = None) -> datetime:
    """Find the first future occurrence without iterating through years."""
    from utils.report_scheduler import next_run
    now = now or local_now_naive()
    if frequency == 'daily':
        candidate = datetime.combine(now.date(), moment.time())
        return candidate if candidate > now else candidate + timedelta(days=1)
    if frequency == 'weekly':
        days = (moment.weekday() - now.weekday()) % 7
        candidate = datetime.combine(now.date() + timedelta(days=days), moment.time())
        return candidate if candidate > now else candidate + timedelta(days=7)
    try:
        import jdatetime
        current = jdatetime.date.fromgregorian(date=now.date())
        day = max(1, min(int(schedule_day or current.day), 31))
        while day:
            try:
                target = jdatetime.date(current.year, current.month, day).togregorian()
                candidate = datetime.combine(target, moment.time())
                return candidate if candidate > now else next_run(candidate, 'monthly', schedule_day)
            except ValueError:
                day -= 1
    except (ImportError, TypeError, ValueError, OverflowError):
        pass
    return next_run(now, frequency, schedule_day)


@reports_bp.route('/schedules/<int:schedule_id>/toggle', methods=['POST'])
@login_required
@require_permission('reports', 'view')
def toggle_schedule(schedule_id):
    from models.reporting import ReportSchedule
    item = ReportSchedule.query.filter_by(id=schedule_id, user_id=current_user.id).first_or_404()
    if not item.is_active:
        _require_report_action('export')
        _require_source_feature('export_data')
        _report_or_404(item.report_key)
    item.is_active = not item.is_active
    db.session.commit()
    flash('وضعیت زمان‌بندی تغییر کرد', 'success')
    return redirect(_safe_return_url(url_for('reports.schedules')))


@reports_bp.route('/schedules/<int:schedule_id>/run', methods=['POST'])
@login_required
@require_permission('reports', 'view')
def run_schedule(schedule_id):
    _require_report_action('export')
    _require_source_feature('export_data')
    from models.reporting import ReportSchedule
    item = ReportSchedule.query.filter_by(id=schedule_id, user_id=current_user.id).first_or_404()
    _report_or_404(item.report_key)
    now = local_now_naive()
    stale_before = now - timedelta(hours=1)
    claimed = (ReportSchedule.query.filter(
        ReportSchedule.id == item.id,
        ReportSchedule.user_id == current_user.id,
        db.or_(
            ReportSchedule.last_status.is_(None),
            ReportSchedule.last_status != 'running',
            ReportSchedule.last_run_at.is_(None),
            ReportSchedule.last_run_at < stale_before,
        ),
    ).update({
        ReportSchedule.last_status: 'running',
        ReportSchedule.last_run_at: now,
    }, synchronize_session=False))
    db.session.commit()
    if not claimed:
        flash('این گزارش هم‌اکنون در حال اجرا است', 'warning')
        return redirect(_safe_return_url(url_for('reports.schedules')))
    item = db.session.get(ReportSchedule, schedule_id)
    try:
        from utils.report_scheduler import deliver_schedule
        # A preview run must not postpone a future scheduled occurrence.  An
        # overdue occurrence, however, is consumed so it cannot run twice.
        deliver_schedule(item, advance=not item.next_run_at or item.next_run_at <= now)
        flash('گزارش ساخته و تحویل شد', 'success')
    except Exception:
        flash('اجرای گزارش ناموفق بود؛ جزئیات خطا در وضعیت زمان‌بندی ثبت شد', 'danger')
    return redirect(_safe_return_url(url_for('reports.schedules')))


@reports_bp.route('/schedules/<int:schedule_id>/delete', methods=['POST'])
@login_required
@require_permission('reports', 'view')
def delete_schedule(schedule_id):
    from models.reporting import ReportSchedule
    ReportSchedule.query.filter_by(id=schedule_id, user_id=current_user.id).first_or_404()
    stale_before = local_now_naive() - timedelta(hours=1)
    deleted = (ReportSchedule.query.filter(
        ReportSchedule.id == schedule_id,
        ReportSchedule.user_id == current_user.id,
        db.or_(
            ReportSchedule.last_status.is_(None),
            ReportSchedule.last_status != 'running',
            ReportSchedule.last_run_at.is_(None),
            ReportSchedule.last_run_at < stale_before,
        ),
    ).delete(synchronize_session=False))
    db.session.commit()
    if not deleted:
        flash('زمان‌بندی در حال اجرا را نمی‌توان حذف کرد', 'warning')
        return redirect(_safe_return_url(url_for('reports.schedules')))
    flash('زمان‌بندی حذف شد', 'success')
    return redirect(_safe_return_url(url_for('reports.schedules')))


@reports_bp.route('/budgets', methods=['GET', 'POST'])
@login_required
@require_permission('reports', 'view')
def budgets():
    _require_source_feature('finance')
    _require_source_feature('accounting')
    if (not current_user.is_admin and
            (not current_user.has_permission('finance', 'view')
             or not current_user.has_permission('accounting', 'view'))):
        abort(403)
    from models.accounting import Account
    from models.finance import ExpenseCategory
    from models.reporting import ReportBudget
    from models.system import Branch
    if request.method == 'POST':
        if not current_user.is_admin and not current_user.has_permission('finance', 'create'):
            abort(403)
        branch_id = request.form.get('branch_id', type=int)
        if not current_user.is_admin and current_user.branch_id:
            branch_id = current_user.branch_id
        amount = _safe_decimal(request.form.get('amount'))
        title = request.form.get('title', '').strip()
        fiscal_year = str(request.form.get('fiscal_year') or '').translate(
            str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789')
        ).strip()
        period = request.form.get('period', 'year')
        period_no = request.form.get('period_no', type=int)
        if period == 'year':
            period_no = None
        budget_type = request.form.get('budget_type', 'expense')
        account_id = request.form.get('account_id', type=int)
        category_id = request.form.get('expense_category_id', type=int)
        account = db.session.get(Account, account_id) if account_id else None
        valid_branch = not branch_id or db.session.get(Branch, branch_id) is not None
        valid_account = not account_id or account is not None
        valid_category = not category_id or db.session.get(ExpenseCategory, category_id) is not None
        account_kind = (account.account_type or
                        (account.group.account_type if account and account.group else '')) if account else ''
        valid_sources = (not (account_id and category_id) and
                         not (category_id and budget_type != 'expense') and
                         not (account and account_kind not in (budget_type, '')))
        if (not title or amount <= 0 or amount > MAX_MONEY or not (fiscal_year.isdigit() and 1300 <= int(fiscal_year) <= 1600)
                or period not in ('year', 'quarter', 'month')
                or (period == 'quarter' and period_no not in range(1, 5))
                or (period == 'month' and period_no not in range(1, 13))
                or budget_type not in ('revenue', 'expense') or not valid_branch
                or not valid_account or not valid_category or not valid_sources):
            flash('سال، عنوان، مبلغ و سرفصل معتبر برای بودجه الزامی است', 'danger')
        else:
            db.session.add(ReportBudget(
                fiscal_year=fiscal_year, period=period, period_no=period_no, title=title[:160],
                budget_type=budget_type, amount=amount,
                branch_id=branch_id, account_id=account_id,
                expense_category_id=category_id,
                notes=request.form.get('notes', '').strip()[:2000] or None,
                created_by=current_user.id,
            ))
            db.session.commit()
            flash('بودجه ثبت شد', 'success')
        return redirect(url_for('reports.budgets'))
    query = ReportBudget.query
    if not current_user.is_admin and current_user.branch_id:
        # A NULL branch is an organisation-wide aggregate budget, not a copy
        # inherited by every branch.  Keep branch workspaces strictly isolated.
        query = query.filter(ReportBudget.branch_id == current_user.branch_id)
    branch_query = Branch.query.filter_by(is_active=True)
    if not current_user.is_admin and current_user.branch_id:
        branch_query = branch_query.filter_by(id=current_user.branch_id)
    return render_template('reports/budgets.html', budgets=query.order_by(ReportBudget.fiscal_year.desc()).all(),
                           branches=branch_query.order_by(Branch.name).all(),
                           accounts=Account.query.filter_by(is_active=True).order_by(Account.code).all(),
                           categories=ExpenseCategory.query.filter_by(is_active=True).order_by(ExpenseCategory.name).all(),
                           current_year=default_date_range()[0].split('/')[0])


@reports_bp.route('/budgets/<int:budget_id>/delete', methods=['POST'])
@login_required
@require_permission('reports', 'view')
def delete_budget(budget_id):
    _require_source_feature('finance')
    _require_source_feature('accounting')
    from models.reporting import ReportBudget
    item = ReportBudget.query.get_or_404(budget_id)
    if not current_user.is_admin and (
            not current_user.has_permission('finance', 'view')
            or not current_user.has_permission('accounting', 'view')
            or not current_user.has_permission('finance', 'delete')
            or (current_user.branch_id and item.branch_id != current_user.branch_id)):
        abort(403)
    db.session.delete(item)
    db.session.commit()
    flash('ردیف بودجه حذف شد', 'success')
    return redirect(url_for('reports.budgets'))


@reports_bp.route('/reconciliations', methods=['GET', 'POST'])
@login_required
@require_permission('reports', 'view')
def reconciliations():
    _require_source_feature('finance')
    if not current_user.is_admin and not current_user.has_permission('finance', 'view'):
        abort(403)
    from models.finance import BankAccount, Cashbox
    from models.reporting import AccountReconciliation
    if request.method == 'POST':
        if not current_user.is_admin and not current_user.has_permission('finance', 'create'):
            abort(403)
        kind = request.form.get('account_kind', 'cashbox')
        cashbox_id = request.form.get('cashbox_id', type=int)
        bank_id = request.form.get('bank_account_id', type=int)
        cashbox = db.session.get(Cashbox, cashbox_id) if kind == 'cashbox' and cashbox_id else None
        bank = db.session.get(BankAccount, bank_id) if kind == 'bank' and bank_id else None
        if not current_user.is_admin and current_user.branch_id:
            if cashbox and cashbox.branch_id != current_user.branch_id:
                abort(403)
            if bank and bank.branch_id not in (None, current_user.branch_id):
                abort(403)
        obj = cashbox or bank
        raw_date = str(request.form.get('reconciliation_date') or '').strip()
        reconciliation_date = parse_jalali_date(raw_date) if raw_date else local_today()
        if not obj:
            flash('حساب موردنظر انتخاب نشده است', 'danger')
        elif reconciliation_date is None:
            flash('تاریخ مغایرت‌گیری معتبر نیست', 'danger')
        else:
            system_balance = _safe_decimal(obj.balance)
            statement = _parse_decimal(request.form.get('statement_balance'))
            if statement is None:
                flash('مانده واقعی باید یک عدد معتبر باشد', 'danger')
            elif abs(statement) > MAX_MONEY or abs(system_balance) > MAX_MONEY:
                flash('مانده واردشده خارج از محدوده مجاز است', 'danger')
            else:
                db.session.add(AccountReconciliation(
                    account_kind=kind, cashbox_id=cashbox.id if cashbox else None,
                    bank_account_id=bank.id if bank else None,
                    reconciliation_date=reconciliation_date,
                    system_balance=system_balance, statement_balance=statement,
                    difference=statement-system_balance,
                    notes=request.form.get('notes', '').strip()[:2000] or None,
                    created_by=current_user.id,
                ))
                db.session.commit()
                flash('مغایرت‌گیری ثبت شد', 'success')
        return redirect(url_for('reports.reconciliations'))
    query = AccountReconciliation.query
    cashbox_query = Cashbox.query.filter_by(is_active=True)
    bank_query = BankAccount.query.filter_by(is_active=True)
    if not current_user.is_admin and current_user.branch_id:
        branch_scope = Cashbox.branch_id == current_user.branch_id
        bank_scope = db.or_(BankAccount.branch_id == current_user.branch_id,
                            BankAccount.branch_id.is_(None))
        cashbox_query = cashbox_query.filter(branch_scope)
        bank_query = bank_query.filter(bank_scope)
        # History must retain reconciliations of accounts deactivated later;
        # only the creation selectors themselves are limited to active ones.
        # Join the scoped accounts instead of materialising a potentially huge
        # IN list (important for SQLite installations with parameter limits).
        query = (query
                 .outerjoin(Cashbox,
                            AccountReconciliation.cashbox_id == Cashbox.id)
                 .outerjoin(BankAccount,
                            AccountReconciliation.bank_account_id == BankAccount.id)
                 .filter(db.or_(
                     db.and_(AccountReconciliation.cashbox_id.is_not(None),
                             branch_scope),
                     db.and_(AccountReconciliation.bank_account_id.is_not(None),
                             bank_scope),
                 )))
    return render_template('reports/reconciliations.html', reconciliations=query.order_by(AccountReconciliation.reconciliation_date.desc()).all(),
                           cashboxes=cashbox_query.order_by(Cashbox.name).all(),
                           bank_accounts=bank_query.order_by(BankAccount.bank_name).all(),
                           today=default_date_range()[1])


@reports_bp.route('/reconciliations/<int:item_id>/resolve', methods=['POST'])
@login_required
@require_permission('reports', 'view')
def resolve_reconciliation(item_id):
    _require_source_feature('finance')
    from models.reporting import AccountReconciliation
    item = db.session.get(AccountReconciliation, item_id)
    if item is None:
        abort(404)
    if not current_user.is_admin and (not current_user.has_permission('finance', 'view')
                                      or not current_user.has_permission('finance', 'edit')):
        abort(403)
    if not current_user.is_admin and current_user.branch_id:
        account = item.cashbox or item.bank_account
        if account is None:
            abort(404)
        allowed_branches = ((current_user.branch_id,) if item.account_kind == 'cashbox'
                            else (None, current_user.branch_id))
        if account.branch_id not in allowed_branches:
            abort(403)
    values = {
        AccountReconciliation.status: 'resolved',
        AccountReconciliation.resolved_by: current_user.id,
        AccountReconciliation.resolved_at: local_now_naive(),
    }
    notes = request.form.get('notes', '').strip()[:2000]
    if notes:
        values[AccountReconciliation.notes] = notes
    updated = (AccountReconciliation.query.filter(
        AccountReconciliation.id == item_id,
        AccountReconciliation.status == 'open',
    ).update(values, synchronize_session=False))
    db.session.commit()
    flash('مغایرت رفع‌شده علامت خورد' if updated else 'این مغایرت قبلاً رفع شده است',
          'success' if updated else 'info')
    return redirect(url_for('reports.reconciliations'))


# Backward-compatible routes now point to the single reporting engine.
def _legacy_redirect(key):
    query = request.args.to_dict(flat=True)
    location = url_for('reports.view', report_key=key)
    return redirect(location + (('?' + urlencode(query)) if query else ''))


@reports_bp.route('/students')
@login_required
def student_report(): return _legacy_redirect('students')


@reports_bp.route('/financial')
@login_required
def financial_report(): return _legacy_redirect('executive-dashboard')


@reports_bp.route('/attendance')
@login_required
def attendance_report(): return _legacy_redirect('attendance')


@reports_bp.route('/teachers')
@login_required
def teacher_report(): return _legacy_redirect('teacher-performance')


@reports_bp.route('/enrollment')
@login_required
def enrollment_report(): return _legacy_redirect('enrollments')


@reports_bp.route('/installments')
@login_required
def installment_report(): return _legacy_redirect('installments-overdue')


@reports_bp.route('/profit-loss')
@login_required
def profit_loss(): return _legacy_redirect('profit-loss')
