"""
سیستم حقوق و دستمزد
- حقوق ثابت، ساعتی، درصدی، جلسه‌ای، ترکیبی
- محاسبه بر اساس بازه زمانی واقعیِ دوره (نه کل تاریخچه)
- صدور فیش با جلوگیری از تکرار، تأیید/پرداخت/ابطال و ثبت سند صندوق
- کسورات (مساعده/جریمه/بیمه/مالیات) و پاداش/اضافه‌کاری دستی
- هزینه‌های پیشرفته و گزارش‌های مالیاتی/جامع

نکته: کنترل سطح دسترسی از نگهبان سراسری `utils/access_policy.py` انجام می‌شود و
برای عملیات حساس این بخش، دکوراتور موضعی `require_role` هم گذاشته شده است.
"""
from datetime import date, datetime, timedelta

from flask import (Blueprint, abort, flash, jsonify, redirect, render_template,
                   request, url_for)
from flask_login import current_user, login_required
from license_client import license_required, licensed_section
from extensions import db
from utils.access_policy import require_role
from utils.document_numbers import next_document_number
from utils.form_helpers import get_jalali_date, safe_float, safe_int
from utils.jalali import (current_jalali_period, gregorian_to_jalali, jalali_period_bounds,
                          jalali_period_label, normalize_jalali_period, recent_jalali_periods)

payroll_bp = Blueprint('payroll', __name__)


# ═══════════════════════════════════════════
#  ابزارهای مشترک بخش
# ═══════════════════════════════════════════
_CONTRACT_TYPES = {
    'fixed': 'ثابت ماهانه',
    'hourly': 'ساعتی',
    'session': 'جلسه‌ای',
    'percentage': 'درصدی از شهریه',
    'combined': 'ترکیبی (ساعتی + درصدی)',
}

_PERSON_TYPES = {'teacher': 'مدرس', 'employee': 'کارمند', 'manager': 'مدیر'}


def _period_choices(model=None, span=18):
    """گزینه‌های منو دوره: ۱۸ ماه اخیر + دوره‌هایی که فیش دارند."""
    choices = list(recent_jalali_periods(span))
    if model is not None:
        try:
            used = [row[0] for row in db.session.query(model.period).distinct().all() if row[0]]
            for value in used:
                normalized = normalize_jalali_period(value)
                if normalized and normalized not in choices:
                    choices.append(normalized)
            choices.sort(reverse=True)
        except Exception:
            pass
    return choices


def _person_lookup(person_type: str, person_id: int):
    """برگرداندن (نام، شناسه) شخص؛ برای teacher واقعاً به جدول مدرسین وصل می‌شود."""
    from models.teacher import Teacher
    if person_type == 'teacher':
        teacher = Teacher.query.get(person_id)
        return (teacher.full_name if teacher else None), teacher
    # کارمند/مدیر: هنوز مدل Employee وجود ندارد → از حساب کاربری استفاده می‌کنیم
    from models.user import User
    user = User.query.get(person_id)
    return (user.full_name if user else None), user


def _person_name(person_type: str, person_id: int) -> str:
    name, _ = _person_lookup(person_type, person_id)
    return name or f'{_PERSON_TYPES.get(person_type, person_type)} #{person_id}'


def form_value(field, record=None):
    """مقدار یک فیلد فرم: پس از خطا مقدار ارسالی کاربر، در غیر این صورت مقدار رکورد."""
    if request.method == 'POST' and field in request.form:
        return request.form.get(field, '')
    if record is not None:
        value = getattr(record, field, '')
        if isinstance(value, (datetime, date)):
            return gregorian_to_jalali(value)
        return '' if value is None else value
    return ''


def _log(action: str, description: str, entity_type: str = None, entity_id: int = None):
    """ثبت رویدادهای مالی در تاریخچه فعالیت (قبلاً برای حقوق اصلاً لاگ نمی‌شد)."""
    try:
        from models.user import ActivityLog
        db.session.add(ActivityLog(
            user_id=current_user.id, action=action, module='payroll',
            entity_type=entity_type, entity_id=entity_id,
            description=description, ip_address=request.remote_addr,
        ))
    except Exception:
        # لاگ نباید عملیات مالی را شکست بدهد
        pass


def _active_contract(person_type: str, person_id: int, on_or_before: date = None):
    """قرارداد فعالِ معتبر در بازه؛ اگر چند قرارداد بود، جدیدترین را برمی‌دارد."""
    from models.finance import SalaryContract
    query = SalaryContract.query.filter_by(person_type=person_type, person_id=person_id,
                                           is_active=True)
    contract = query.order_by(SalaryContract.created_at.desc(), SalaryContract.id.desc()).first()
    if contract is None:
        return None
    if on_or_before and contract.end_date and contract.end_date < on_or_before:
        return None            # قرارداد منقضی شده برای این دوره اعتبار ندارد
    if contract.start_date and on_or_before and contract.start_date > on_or_before:
        return None
    return contract


def _period_or_400(form_value):
    """اعتبارسنجی دوره؛ خروجی (period_normalized, start, end)."""
    normalized = normalize_jalali_period(form_value)
    if not normalized:
        return None, None, None
    bounds = jalali_period_bounds(normalized)
    if not bounds:
        return None, None, None
    return normalized, bounds[0], bounds[1]


# ═══════════════════════════════════════════
#  داشبورد حقوق و دستمزد
# ═══════════════════════════════════════════
@payroll_bp.route('/payroll')
@license_required
@login_required
@licensed_section('payroll')
def dashboard():
    from models.finance import Payslip, SalaryContract
    from models.teacher import Teacher

    period = normalize_jalali_period(request.args.get('period')) or current_jalali_period()
    period_choices = _period_choices(Payslip)

    teachers = Teacher.query.filter_by(is_active=True).all()
    contracts = SalaryContract.query.order_by(SalaryContract.created_at.desc()).all()
    period_payslips = Payslip.query.filter_by(period=period).order_by(Payslip.created_at.desc()).all()
    recent_payslips = Payslip.query.order_by(Payslip.created_at.desc()).limit(20).all()

    def _sum(statuses, only_period=True):
        query = db.session.query(db.func.sum(Payslip.net_amount))
        if only_period:
            query = query.filter(Payslip.period == period)
        if statuses:
            query = query.filter(Payslip.status.in_(statuses))
        return query.scalar() or 0

    return render_template('payroll/dashboard.html',
                           teachers=teachers, contracts=contracts,
                           period=period, period_choices=period_choices,
                           period_label=jalali_period_label(period),
                           period_payslips=period_payslips,
                           recent_payslips=recent_payslips,
                           period_paid=_sum(['paid']),
                           period_pending=_sum(['draft', 'approved']),
                           total_paid=_sum(['paid'], only_period=False),
                           total_pending=_sum(['draft', 'approved'], only_period=False),
                           person_name=_person_name,
                           contract_types=_CONTRACT_TYPES,
                           person_types=_PERSON_TYPES)


# ═══════════════════════════════════════════
#  فیش‌ها (لیست + فیلتر)
# ═══════════════════════════════════════════
@payroll_bp.route('/payroll/payslips')
@login_required
def payslips():
    """لیست کامل فیش‌ها با فیلتر دوره/فرد/وضعیت و صفحه‌بندی."""
    from models.finance import Payslip

    page = request.args.get('page', 1, type=int)
    period = normalize_jalali_period(request.args.get('period')) or ''
    status = request.args.get('status', '')
    period_choices = _period_choices(Payslip)
    person = request.args.get('person', '')

    query = Payslip.query
    if period:
        query = query.filter(Payslip.period == period)
    if status in ('draft', 'approved', 'paid', 'cancelled'):
        query = query.filter(Payslip.status == status)
    person_id = safe_int(person, 0) if person else 0
    if person_id > 0:
        query = query.filter(Payslip.person_id == person_id)

    payslips_page = query.order_by(Payslip.period.desc(), Payslip.id.desc()).paginate(
        page=page, per_page=25, error_out=False)

    totals = {
        'gross': sum(p.gross_amount or 0 for p in payslips_page.items),
        'deductions': sum(p.total_deductions or 0 for p in payslips_page.items),
        'net': sum(p.net_amount or 0 for p in payslips_page.items),
    }

    return render_template('payroll/payslips.html', payslips=payslips_page, period=period,
                           period_choices=period_choices, status=status, person=person,
                           totals=totals, person_name=_person_name, person_types=_PERSON_TYPES)


# ═══════════════════════════════════════════
#  قرارداد حقوقی
# ═══════════════════════════════════════════
@payroll_bp.route('/payroll/contracts')
@login_required
def contracts():
    from models.finance import SalaryContract
    contracts_list = SalaryContract.query.order_by(SalaryContract.created_at.desc()).all()
    return render_template('payroll/contracts.html', contracts=contracts_list,
                           person_name=_person_name, contract_types=_CONTRACT_TYPES,
                           person_types=_PERSON_TYPES, today=date.today())


def _contract_form_kwargs(contract=None):
    """خواندن و اعتبارسنجی فرم قرارداد؛ (values, errors) برمی‌گرداند."""
    from models.teacher import Teacher

    person_type = (request.form.get('person_type') or 'teacher').strip()
    if person_type not in _PERSON_TYPES:
        person_type = 'teacher'

    errors = []
    person_id = safe_int(request.form.get('person_id'), 0)
    if person_id <= 0:
        errors.append('شخص مورد نظر را انتخاب کنید')
    else:
        name, found = _person_lookup(person_type, person_id)
        if not found:
            errors.append('شخص انتخاب‌شده در سیستم وجود ندارد')

    contract_type = (request.form.get('contract_type') or 'fixed').strip()
    if contract_type not in _CONTRACT_TYPES:
        errors.append('نوع قرارداد نامعتبر است')

    amounts = {
        'base_salary': safe_float(request.form.get('base_salary')),
        'hourly_rate': safe_float(request.form.get('hourly_rate')),
        'session_rate': safe_float(request.form.get('session_rate')),
        'percentage_rate': safe_float(request.form.get('percentage_rate')),
        'commission_rate': safe_float(request.form.get('commission_rate')),
        'insurance_amount': safe_float(request.form.get('insurance_amount')),
        'tax_amount': safe_float(request.form.get('tax_amount')),
    }
    for field, value in amounts.items():
        if value < 0:
            errors.append(f'مبلغ «{field}» نمی‌تواند منفی باشد')

    rate_map = {'fixed': 'base_salary', 'hourly': 'hourly_rate', 'session': 'session_rate',
                'percentage': 'percentage_rate', 'combined': 'hourly_rate'}
    needed = 'base_salary' if contract_type == 'combined' else rate_map.get(contract_type)
    if needed and amounts.get(needed, 0) <= 0 and contract_type != 'combined':
        errors.append(f'برای قرارداد {_CONTRACT_TYPES.get(contract_type, contract_type)} '
                      f'مبلغ مربوطه باید بزرگ‌تر از صفر باشد')
    if contract_type == 'combined' and amounts['base_salary'] <= 0 and amounts['hourly_rate'] <= 0:
        errors.append('در قرارداد ترکیبی حداقل یکی از «حقوق پایه» یا «نرخ ساعتی» باید پر شود')

    start_date = get_jalali_date(request.form, 'start_date') if request.form.get('start_date') else None
    end_date = get_jalali_date(request.form, 'end_date') if request.form.get('end_date') else None
    if start_date and end_date and end_date < start_date:
        errors.append('تاریخ پایان نمی‌تواند قبل از تاریخ شروع باشد')

    # قرارداد فعال تکراری برای یک نفر مجاز نیست (مگر در حالت ویرایش)
    if not errors and person_id:
        from models.finance import SalaryContract
        duplicate_query = SalaryContract.query.filter_by(person_type=person_type, person_id=person_id,
                                                          is_active=True)
        if contract is not None:
            duplicate_query = duplicate_query.filter(SalaryContract.id != contract.id)
        if duplicate_query.first():
            errors.append(f'{_person_name(person_type, person_id)} هم‌اکنون قرارداد فعال دارد؛ '
                          'ابتدا آن را غیرفعال یا ویرایش کنید')

    is_active = (request.form.get('is_active') in ('1', 'on', 'true', 'True')
                 if contract is not None else True)

    values = dict(person_type=person_type, person_id=person_id, contract_type=contract_type,
                  start_date=start_date, end_date=end_date, is_active=is_active,
                  notes=(request.form.get('notes') or '').strip() or None, **amounts)
    return values, errors


@payroll_bp.route('/payroll/contracts/add', methods=['GET', 'POST'])
@login_required
@require_role('payroll', 'create')
def add_contract():
    from models.finance import SalaryContract
    from models.teacher import Teacher

    teachers = Teacher.query.filter_by(is_active=True).all()

    if request.method == 'POST':
        values, errors = _contract_form_kwargs()
        if errors:
            for message in errors:
                flash(message, 'danger')
            return render_template('payroll/add_contract.html', teachers=teachers,
                                   contract_types=_CONTRACT_TYPES, person_name=_person_name,
                                   person_types=_PERSON_TYPES, contract=None,
                                   form_value=form_value), 400

        contract = SalaryContract(**values)
        db.session.add(contract)
        _log('create', f'ثبت قرارداد حقوقی برای {_person_name(values["person_type"], values["person_id"])}',
             'salary_contract')
        db.session.commit()
        flash('قرارداد حقوقی ثبت شد', 'success')
        return redirect(url_for('payroll.contracts'))

    return render_template('payroll/add_contract.html', teachers=teachers, contract=None,
                           contract_types=_CONTRACT_TYPES, person_name=_person_name,
                           person_types=_PERSON_TYPES, form_value=form_value)


@payroll_bp.route('/payroll/contracts/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@require_role('payroll', 'edit')
def edit_contract(id):
    """ویرایش قرارداد — قبلاً قرارداد فقط قابل ساخت بود و هیچ راه ویرایش نداشت."""
    from models.finance import SalaryContract
    from models.teacher import Teacher

    contract = SalaryContract.query.get_or_404(id)
    teachers = Teacher.query.filter_by(is_active=True).all()

    if request.method == 'POST':
        values, errors = _contract_form_kwargs(contract)
        if errors:
            for message in errors:
                flash(message, 'danger')
            return render_template('payroll/edit_contract.html', teachers=teachers,
                                   contract=contract, contract_types=_CONTRACT_TYPES,
                                   person_name=_person_name, person_types=_PERSON_TYPES,
                                   form_value=form_value), 400
        for field, value in values.items():
            setattr(contract, field, value)
        _log('edit', f'ویرایش قرارداد شماره {contract.id}', 'salary_contract', contract.id)
        db.session.commit()
        flash('قرارداد به‌روزرسانی شد', 'success')
        return redirect(url_for('payroll.contracts'))

    return render_template('payroll/edit_contract.html', teachers=teachers, contract=contract,
                           contract_types=_CONTRACT_TYPES, person_name=_person_name,
                           person_types=_PERSON_TYPES, form_value=form_value)


@payroll_bp.route('/payroll/contracts/<int:id>/toggle', methods=['POST'])
@login_required
@require_role('payroll', 'edit')
def toggle_contract(id):
    """فعال/غیرفعال کردن قرارداد (به‌جای حذف، تا سوابق فیش‌ها سالم بماند)."""
    from models.finance import SalaryContract
    contract = SalaryContract.query.get_or_404(id)
    contract.is_active = not contract.is_active
    _log('edit', f'{"فعال" if contract.is_active else "غیرفعال"} کردن قرارداد شماره {contract.id}',
         'salary_contract', contract.id)
    db.session.commit()
    flash('وضعیت قرارداد تغییر کرد', 'success')
    return redirect(request.referrer or url_for('payroll.contracts'))


# ═══════════════════════════════════════════
#  محاسبه حقوق
# ═══════════════════════════════════════════
def _compute_period_amounts(contract, teacher, period_start, period_end):
    """مقادیر یک دوره برای یک مدرس — همه‌چیز در بازه تاریخ فیلتر می‌شود."""
    from models.attendance import TeacherAttendance
    from models.classes import ClassGroup, ClassSession
    from models.registration import Registration

    amounts = {
        'base': contract.base_salary or 0,
        'teaching_hours': 0.0,
        'teaching_amount': 0.0,
        'sessions_count': 0,
        'session_amount': 0.0,
        'commission_amount': 0.0,
        'detail': {},
    }
    kind = contract.contract_type

    def hours_in_period() -> float:
        rows = (db.session.query(db.func.sum(TeacherAttendance.teaching_hours))
                .join(ClassSession, TeacherAttendance.session_id == ClassSession.id)
                .filter(TeacherAttendance.teacher_id == teacher.id,
                        ClassSession.session_date >= period_start,
                        ClassSession.session_date <= period_end)
                .scalar())
        return float(rows or 0)

    def sessions_in_period() -> int:
        return (db.session.query(db.func.count(ClassSession.id))
                .join(ClassGroup, ClassSession.class_id == ClassGroup.id)
                .filter(ClassGroup.teacher_id == teacher.id,
                        ClassSession.status == 'completed',
                        ClassSession.session_date >= period_start,
                        ClassSession.session_date <= period_end)
                .scalar()) or 0

    def tuition_in_period() -> float:
        """مبلغ پرداخت‌شدهٔ ثبت‌نام‌های این مدرس، فقط در بازه دوره."""
        from models.finance import Payment
        return float(db.session.query(db.func.sum(Payment.amount))
                     .join(Registration, Payment.registration_id == Registration.id)
                     .filter(Registration.teacher_id == teacher.id,
                             Payment.status == 'confirmed',
                             Payment.payment_date >= period_start,
                             Payment.payment_date <= period_end)
                     .scalar() or 0)

    if kind in ('hourly', 'combined'):
        amounts['teaching_hours'] = hours_in_period()
        amounts['teaching_amount'] = amounts['teaching_hours'] * (contract.hourly_rate or 0)
        amounts['detail']['hours'] = amounts['teaching_hours']

    if kind == 'session':
        amounts['sessions_count'] = sessions_in_period()
        amounts['session_amount'] = amounts['sessions_count'] * (contract.session_rate or 0)
        amounts['detail']['sessions'] = amounts['sessions_count']

    if kind in ('percentage', 'combined'):
        total_fee = tuition_in_period()
        amounts['commission_amount'] = total_fee * ((contract.percentage_rate or 0) / 100.0)
        amounts['detail']['tuition'] = total_fee

    # پورسانت فروش (فیلد commission_rate) — تا پیش از این اصلاً استفاده نمی‌شد
    if contract.commission_rate:
        sold_in_period = (db.session.query(db.func.sum(Registration.total_fee))
                          .filter(Registration.teacher_id == teacher.id,
                                  Registration.registration_date >= period_start,
                                  Registration.registration_date <= period_end)
                          .scalar()) or 0
        amounts['commission_amount'] += float(sold_in_period) * (contract.commission_rate / 100.0)

    return amounts


def _recalculate_payslip(payslip) -> None:
    """بازمحاسبه جمع‌ها و کسورات یک فیش (منبع یکتا برای همه مسیرهای ویرایش)."""
    gross = ((payslip.base_amount or 0) + (payslip.teaching_amount or 0)
             + (payslip.session_amount or 0) + (payslip.commission_amount or 0)
             + (payslip.bonus or 0) + (payslip.overtime or 0))
    deductions = ((payslip.deductions or 0) + (payslip.insurance or 0) + (payslip.tax or 0)
                  + (payslip.penalty or 0))
    payslip.gross_amount = gross
    payslip.total_deductions = deductions
    payslip.net_amount = gross - deductions


@payroll_bp.route('/payroll/calculate', methods=['GET', 'POST'])
@login_required
@require_role('payroll', 'create')
def calculate():
    """محاسبه خودکار حقوق بر اساس نوع قرارداد، در بازه زمانی دوره."""
    from models.teacher import Teacher
    from models.finance import Payslip

    preview = request.form.get('preview') == '1' or request.args.get('preview') == '1'
    replace_drafts = request.form.get('replace_drafts') == '1'

    teachers = Teacher.query.filter_by(is_active=True).all()

    from models.finance import SalaryContract
    contract_by_teacher = {}
    for contract in SalaryContract.query.filter_by(person_type='teacher', is_active=True).all():
        contract_by_teacher.setdefault(contract.person_id, contract)

    if request.method == 'POST':
        period, period_start, period_end = _period_or_400(request.form.get('period'))
        if not period:
            flash('قالب دوره نامعتبر است؛ نمونه درست: ۱۴۰۵/۰۶', 'danger')
            return render_template('payroll/calculate.html', teachers=teachers,
                                   contract_types=_CONTRACT_TYPES,
                                   contract_by_teacher=contract_by_teacher,
                                   period=request.form.get('period') or '',
                                   period_choices=_period_choices(),
                                   default_period=current_jalali_period()), 400

        teacher_ids = [safe_int(value, 0) for value in request.form.getlist('teacher_ids')]
        teacher_ids = [value for value in teacher_ids if value > 0]
        if not teacher_ids:
            flash('حداقل یک مدرس را انتخاب کنید', 'danger')
            return render_template('payroll/calculate.html', teachers=teachers,
                                   contract_types=_CONTRACT_TYPES,
                                   contract_by_teacher=contract_by_teacher,
                                   period=period, period_choices=_period_choices(),
                                   default_period=current_jalali_period()), 400

        results = []
        for tid in teacher_ids:
            teacher = Teacher.query.get(tid)
            if not teacher:
                results.append({'teacher_id': tid, 'name': f'مدرس #{tid}', 'error': 'مدرس یافت نشد'})
                continue

            contract = _active_contract('teacher', tid, period_end)
            if not contract:
                results.append({'teacher_id': tid, 'name': teacher.full_name,
                                'error': 'قرارداد فعال معتبری برای این دوره وجود ندارد'})
                continue

            amounts = _compute_period_amounts(contract, teacher, period_start, period_end)
            insurance = contract.insurance_amount or 0
            tax = contract.tax_amount or 0

            gross = (amounts['base'] + amounts['teaching_amount'] + amounts['session_amount']
                     + amounts['commission_amount'])
            net = gross - (insurance + tax)

            existing = Payslip.query.filter_by(person_type='teacher', person_id=tid,
                                               period=period).first()
            if existing and existing.status == 'paid':
                results.append({'teacher_id': tid, 'name': teacher.full_name,
                                'error': f'فیش {existing.payslip_number} پرداخت شده و قابل بازمحاسبه نیست'})
                continue
            if existing and existing.status == 'approved' and not replace_drafts:
                results.append({'teacher_id': tid, 'name': teacher.full_name,
                                'error': f'فیش {existing.payslip_number} تأیید شده است؛ '
                                         'برای بازمحاسبه گزینه «جایگزینی فیش‌های تأییدنشده» را فعال کنید'})
                continue
            if existing and existing.status != 'draft' and not replace_drafts:
                results.append({'teacher_id': tid, 'name': teacher.full_name,
                                'error': f'برای این دوره فیش {existing.payslip_number} صادر شده است'})
                continue

            results.append({
                'teacher_id': tid,
                'name': teacher.full_name,
                'contract_type': contract.contract_type,
                'contract_label': _CONTRACT_TYPES.get(contract.contract_type, contract.contract_type),
                'base_amount': amounts['base'],
                'teaching_hours': amounts['teaching_hours'],
                'teaching_amount': amounts['teaching_amount'],
                'sessions_count': amounts['sessions_count'],
                'session_amount': amounts['session_amount'],
                'commission_amount': amounts['commission_amount'],
                'insurance': insurance,
                'tax': tax,
                'gross': gross,
                'net': net,
                'replaces': existing.payslip_number if existing else None,
            })

        if preview:
            return render_template('payroll/calculate.html', teachers=teachers,
                                   contract_types=_CONTRACT_TYPES,
                                   contract_by_teacher=contract_by_teacher,
                                   period=period, period_choices=_period_choices(),
                                   default_period=current_jalali_period(), results=results,
                                   preview=True,
                                   period_label=jalali_period_label(period),
                                   gregorian_window=f'{period_start:%Y/%m/%d} تا {period_end:%Y/%m/%d}')

        issued = replaced = skipped = 0
        for row in results:
            if row.get('error'):
                skipped += 1
                continue
            existing = (Payslip.query.filter_by(person_type='teacher', person_id=row['teacher_id'],
                                                 period=period).first())
            payslip = existing or Payslip(
                payslip_number=next_document_number('payslip'),
                person_type='teacher', person_id=row['teacher_id'], period=period,
                created_by=current_user.id,
            )
            payslip.base_amount = row['base_amount']
            payslip.teaching_hours = row['teaching_hours']
            payslip.teaching_amount = row['teaching_amount']
            payslip.sessions_count = row['sessions_count']
            payslip.session_amount = row['session_amount']
            payslip.commission_amount = row['commission_amount']
            payslip.insurance = row['insurance']
            payslip.tax = row['tax']
            payslip.status = 'draft'
            payslip.notes = (f'محاسبه خودکار دوره {period} — '
                             f'{row["contract_label"]} — بازه {period_start:%Y/%m/%d} تا {period_end:%Y/%m/%d}')
            _recalculate_payslip(payslip)
            if existing is None:
                db.session.add(payslip)
                issued += 1
            else:
                replaced += 1

        if issued or replaced:
            _log('create', f'صدور {issued} و به‌روزرسانی {replaced} فیش حقوقی دوره {period}',
                 'payslip')
        db.session.commit()
        message = f'{issued} فیش صادر شد'
        if replaced:
            message += f' و {replaced} فیش بازمحاسبه شد'
        if skipped:
            message += f' — {skipped} مورد رد شد (تکراری یا بدون قرارداد)'
        flash(message, 'success' if (issued or replaced) else 'warning')
        return redirect(url_for('payroll.dashboard', period=period))

    return render_template('payroll/calculate.html', teachers=teachers,
                           contract_types=_CONTRACT_TYPES,
                           contract_by_teacher=contract_by_teacher,
                           period=current_jalali_period(),
                           period_choices=_period_choices(),
                           default_period=current_jalali_period())


# ═══════════════════════════════════════════
#  فیش حقوقی — نمایش، ویرایش، تأیید، پرداخت، ابطال
# ═══════════════════════════════════════════
@payroll_bp.route('/payroll/payslip/<int:id>')
@login_required
def view_payslip(id):
    from models.finance import Payslip
    from models.system import SystemSettings

    payslip = Payslip.query.get_or_404(id)
    if not current_user.is_admin:
        module = 'payroll' if current_user.has_module_access('payroll') else None
        # مدرس می‌تواند فیش خودش را ببیند (پورتال مدرس)
        from models.teacher import Teacher
        mine = Teacher.query.filter_by(user_id=current_user.id).first()
        allowed_self = bool(mine and payslip.person_type == 'teacher' and payslip.person_id == mine.id)
        if not (module or allowed_self):
            abort(403)

    settings = SystemSettings.query.first()
    cashboxes = []
    try:
        from models.finance import Cashbox
        cashboxes = Cashbox.query.filter_by(is_active=True).order_by(Cashbox.name).all()
    except Exception:
        pass
    return render_template('payroll/view_payslip.html', payslip=payslip,
                           person_name=_person_name(payslip.person_type, payslip.person_id),
                           contract_label=_CONTRACT_TYPES, cashboxes=cashboxes,
                           period_label=jalali_period_label(payslip.period),
                           today=date.today(),
                           can_edit=current_user.is_admin or current_user.has_permission('payroll', 'edit'),
                           settings=settings)


@payroll_bp.route('/payroll/payslip/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@require_role('payroll', 'edit')
def edit_payslip(id):
    """ویرایش فیش پیش‌نویس/تأییدنشده: پاداش، اضافه‌کاری، مساعده، جریمه، بیمه و مالیات."""
    from models.finance import Payslip
    payslip = Payslip.query.get_or_404(id)

    if payslip.status == 'paid':
        flash('فیش پرداخت‌شده قابل ویرایش نیست؛ ابتدا آن را ابطال کنید', 'danger')
        return redirect(url_for('payroll.view_payslip', id=id))

    if request.method == 'POST':
        payslip.base_amount = safe_float(request.form.get('base_amount'))
        payslip.teaching_hours = safe_float(request.form.get('teaching_hours'))
        payslip.teaching_amount = safe_float(request.form.get('teaching_amount'))
        payslip.sessions_count = safe_int(request.form.get('sessions_count'))
        payslip.session_amount = safe_float(request.form.get('session_amount'))
        payslip.commission_amount = safe_float(request.form.get('commission_amount'))
        payslip.bonus = safe_float(request.form.get('bonus'))
        payslip.overtime = safe_float(request.form.get('overtime'))
        payslip.deductions = safe_float(request.form.get('deductions'))
        payslip.insurance = safe_float(request.form.get('insurance'))
        payslip.tax = safe_float(request.form.get('tax'))
        payslip.penalty = safe_float(request.form.get('penalty'))
        payslip.notes = (request.form.get('notes') or '').strip() or None
        _recalculate_payslip(payslip)
        _log('edit', f'ویرایش فیش {payslip.payslip_number}', 'payslip', payslip.id)
        db.session.commit()
        flash('فیش حقوقی به‌روزرسانی شد', 'success')
        return redirect(url_for('payroll.view_payslip', id=id))

    return render_template('payroll/edit_payslip.html', payslip=payslip,
                           person_name=_person_name(payslip.person_type, payslip.person_id))


@payroll_bp.route('/payroll/payslip/<int:id>/approve', methods=['POST'])
@login_required
@require_role('payroll', 'edit')
def approve_payslip(id):
    from models.finance import Payslip
    payslip = Payslip.query.get_or_404(id)
    if payslip.status not in ('draft',):
        flash('فقط فیش پیش‌نویس قابل تأیید است', 'warning')
        return redirect(url_for('payroll.view_payslip', id=id))
    if (payslip.net_amount or 0) < 0:
        flash('خالص فیش منفی است؛ ابتدا کسورات را اصلاح کنید', 'danger')
        return redirect(url_for('payroll.view_payslip', id=id))

    payslip.status = 'approved'
    payslip.approved_by = current_user.id
    payslip.approved_at = datetime.utcnow()
    _log('approve', f'تأیید فیش {payslip.payslip_number} ({_person_name(payslip.person_type, payslip.person_id)})',
         'payslip', payslip.id)
    db.session.commit()
    flash('فیش حقوقی تأیید شد', 'success')
    return redirect(url_for('payroll.view_payslip', id=id))


@payroll_bp.route('/payroll/payslip/<int:id>/pay', methods=['POST'])
@login_required
@require_role('payroll', 'edit')
def pay_payslip(id):
    """پرداخت فیش: فقط از وضعیت approved، یک‌بار، با کنترل موجودی و انتخاب صندوق."""
    from models.finance import Payslip, Cashbox, CashboxTransaction, get_or_create_main_cashbox

    payslip = Payslip.query.get_or_404(id)
    if payslip.status == 'paid':
        flash(f'این فیش قبلاً در {payslip.paid_date} پرداخت شده است؛ پرداخت دوباره انجام نمی‌شود', 'warning')
        return redirect(url_for('payroll.view_payslip', id=id))
    if payslip.status == 'cancelled':
        flash('فیش ابطال‌شده قابل پرداخت نیست', 'danger')
        return redirect(url_for('payroll.view_payslip', id=id))
    if payslip.status != 'approved':
        # پرداخت فقط از وضعیت تأییدشده — جلوگیری از پرداخت فیشی که هنوز بررسی نشده
        flash('ابتدا فیش را تأیید کنید؛ پرداخت فقط برای فیش تأییدشده ممکن است', 'danger')
        return redirect(url_for('payroll.view_payslip', id=id))

    amount = payslip.net_amount or 0
    if amount <= 0:
        flash('مبلغ قابل پرداخت باید بزرگ‌تر از صفر باشد', 'danger')
        return redirect(url_for('payroll.view_payslip', id=id))

    cashbox_id = safe_int(request.form.get('cashbox_id'), 0)
    if cashbox_id > 0:
        cashbox = Cashbox.query.filter_by(id=cashbox_id, is_active=True).first()
        if cashbox is None:
            flash('صندوق انتخاب‌شده معتبر نیست', 'danger')
            return redirect(url_for('payroll.view_payslip', id=id))
    else:
        cashbox = get_or_create_main_cashbox()

    if cashbox is not None and amount > (cashbox.balance or 0):
        flash(f'موجودی صندوق «{cashbox.name}» برای پرداخت {amount:,.0f} تومان کافی نیست '
              f'(موجودی: {(cashbox.balance or 0):,.0f})', 'danger')
        return redirect(url_for('payroll.view_payslip', id=id))

    payslip.status = 'paid'
    payslip.paid_date = (get_jalali_date(request.form, 'paid_date')
                         or get_jalali_date(request.form, 'payment_date')
                         or date.today())
    payslip.paid_by = current_user.id

    if cashbox is not None:
        cashbox.balance = (cashbox.balance or 0) - amount
        db.session.add(CashboxTransaction(
            cashbox_id=cashbox.id, trans_type='out', amount=amount,
            description=f'پرداخت حقوق {payslip.payslip_number} — '
                        f'{_person_name(payslip.person_type, payslip.person_id)}',
            reference_type='salary', reference_id=payslip.id,
            balance_after=cashbox.balance, created_by=current_user.id,
        ))
        payslip.cashbox_id = cashbox.id

    _log('pay', f'پرداخت فیش {payslip.payslip_number} مبلغ {amount:,.0f} تومان '
                f'از صندوق {cashbox.name if cashbox else "—"}', 'payslip', payslip.id)
    db.session.commit()
    flash('حقوق پرداخت شد و از صندوق کسر گردید', 'success')
    return redirect(url_for('payroll.view_payslip', id=id))


@payroll_bp.route('/payroll/payslip/<int:id>/cancel', methods=['POST'])
@login_required
@require_role('payroll', 'edit')
def cancel_payslip(id):
    """ابطال فیش؛ اگر پرداخت شده باشد مبلغ به صندوق برمی‌گردد."""
    from models.finance import Payslip, Cashbox, CashboxTransaction

    payslip = Payslip.query.get_or_404(id)
    if payslip.status == 'cancelled':
        flash('این فیش قبلاً ابطال شده است', 'warning')
        return redirect(url_for('payroll.view_payslip', id=id))

    reason = (request.form.get('reason') or '').strip() or 'بدون دلیل'
    reversed_amount = 0
    if payslip.status == 'paid' and payslip.cashbox_id:
        amount = payslip.net_amount or 0
        cashbox = Cashbox.query.get(payslip.cashbox_id)
        if cashbox is not None:
            cashbox.balance = (cashbox.balance or 0) + amount
            db.session.add(CashboxTransaction(
                cashbox_id=cashbox.id, trans_type='in', amount=amount,
                description=f'بازگشت پرداخت فیش لغوشده {payslip.payslip_number}',
                reference_type='salary', reference_id=payslip.id,
                balance_after=cashbox.balance, created_by=current_user.id,
            ))
            reversed_amount = amount

    payslip.status = 'cancelled'
    payslip.cancel_reason = reason
    payslip.cancelled_at = datetime.utcnow()
    payslip.cancelled_by = current_user.id
    payslip.cashbox_id = None
    payslip.paid_date = None

    _log('delete', f'ابطال فیش {payslip.payslip_number} — {reason}'
           + (f' (بازگشت {reversed_amount:,.0f} تومان به صندوق)' if reversed_amount else ''),
         'payslip', payslip.id)
    db.session.commit()
    flash('فیش ابطال شد' + (' و مبلغ به صندوق بازگشت' if reversed_amount else ''), 'warning')
    return redirect(url_for('payroll.view_payslip', id=id))


# ═══════════════════════════════════════════
#  مالیات
# ═══════════════════════════════════════════
@payroll_bp.route('/payroll/tax')
@login_required
def tax_report():
    """گزارش مالیاتی — با محاسبه پلکانی به‌جای عدد دستی قرارداد."""
    from models.finance import Payslip

    period = normalize_jalali_period(request.args.get('period')) or ''
    period_choices = _period_choices(Payslip)
    query = Payslip.query.filter(Payslip.status != 'cancelled')
    if period:
        query = query.filter(Payslip.period == period)
    payslips = query.order_by(Payslip.created_at.desc()).all()

    try:
        from utils.tax_rules import calculate_salary_tax_monthly, get_rule
    except Exception:                                  # pragma: no cover
        calculate_salary_tax_monthly = None

    rule = get_rule(period.split('/')[0]) if (period and calculate_salary_tax_monthly) else None
    rows = []
    totals = {'gross': 0.0, 'tax': 0.0, 'insurance': 0.0, 'net': 0.0, 'suggested_tax': 0.0}
    for p in payslips:
        suggested = 0.0
        if calculate_salary_tax_monthly is not None:
            # مبنای حقوق: ناخالص منهای بیمه سهم کارمند، به‌صورت ماهانه
            taxable_month = (p.gross_amount or 0) - (p.insurance or 0)
            suggested, _ = calculate_salary_tax_monthly(max(0.0, taxable_month),
                                                         (p.period or '').split('/')[0])
        diff = suggested - (p.tax or 0)
        rows.append({'payslip': p, 'name': _person_name(p.person_type, p.person_id),
                     'suggested_tax': suggested, 'difference': diff})
        totals['gross'] += p.gross_amount or 0
        totals['tax'] += p.tax or 0
        totals['insurance'] += p.insurance or 0
        totals['net'] += p.net_amount or 0
        totals['suggested_tax'] += suggested

    return render_template('payroll/tax_report.html', payslips=rows, period=period,
                           period_choices=period_choices,
                           period_label=jalali_period_label(period),
                           totals=totals, rule=rule,
                           has_calculator=calculate_salary_tax_monthly is not None)


# ═══════════════════════════════════════════
#  هزینه‌های پیشرفته
# ═══════════════════════════════════════════
@payroll_bp.route('/expenses/advanced')
@login_required
def advanced_expenses():
    """مدیریت پیشرفته هزینه‌ها (فیلتر + تفکیک + دانلود پیوست)."""
    from models.finance import Expense, ExpenseCategory

    category_id = request.args.get('category_id', type=int)
    parsed_from = get_jalali_date(request.args, 'date_from') if request.args.get('date_from') else None
    parsed_to = get_jalali_date(request.args, 'date_to') if request.args.get('date_to') else None

    query = Expense.query
    if category_id:
        query = query.filter_by(category_id=category_id)
    if parsed_from:
        query = query.filter(Expense.expense_date >= parsed_from)
    if parsed_to:
        query = query.filter(Expense.expense_date <= parsed_to)

    page = request.args.get('page', 1, type=int)
    expenses_page = query.order_by(Expense.expense_date.desc(), Expense.id.desc()).paginate(
        page=page, per_page=25, error_out=False)
    categories = ExpenseCategory.query.filter_by(is_active=True).order_by(ExpenseCategory.name).all()

    total = db.session.query(db.func.sum(Expense.amount))
    if category_id:
        total = total.filter(Expense.category_id == category_id)
    if parsed_from:
        total = total.filter(Expense.expense_date >= parsed_from)
    if parsed_to:
        total = total.filter(Expense.expense_date <= parsed_to)
    total = total.scalar() or 0

    by_category = []
    for cat in categories:
        amount_query = db.session.query(db.func.sum(Expense.amount)).filter(
            Expense.category_id == cat.id)
        if parsed_from:
            amount_query = amount_query.filter(Expense.expense_date >= parsed_from)
        if parsed_to:
            amount_query = amount_query.filter(Expense.expense_date <= parsed_to)
        amount = amount_query.scalar() or 0
        if amount:
            by_category.append({'name': cat.name, 'amount': amount})
    by_category.sort(key=lambda item: item['amount'], reverse=True)

    return render_template('payroll/advanced_expenses.html',
                           expenses=expenses_page, categories=categories,
                           total=total, by_category=by_category,
                           category_id=(str(category_id) if category_id else ''),
                           date_from=request.args.get('date_from', ''),
                           date_to=request.args.get('date_to', ''))


# پسوند/حجم مجاز فاکتور هزینه در `utils/uploads.py` (kind='expense') تعریف است


@payroll_bp.route('/expenses/advanced/add', methods=['GET', 'POST'])
@login_required
@require_role('finance', 'create')
def add_advanced_expense():
    """ثبت هزینه پیشرفته — با اعتبارسنجی مبلغ و محدودیت پسوند فایل."""
    import os

    from models.finance import Expense, ExpenseCategory, get_or_create_main_cashbox

    categories = ExpenseCategory.query.filter_by(is_active=True).order_by(ExpenseCategory.name).all()

    if request.method == 'POST':
        category_id = request.form.get('category_id', type=int)
        category = ExpenseCategory.query.filter_by(id=category_id, is_active=True).first() if category_id else None
        amount = safe_float(request.form.get('amount'))
        deduct_from_cashbox = request.form.get('from_cashbox') == '1'

        if not category:
            flash('لطفاً یک دسته‌بندی هزینه فعال انتخاب کنید', 'danger')
            return render_template('payroll/add_expense.html', categories=categories,
                                   form=request.form, today=date.today()), 400
        if amount <= 0:
            flash('مبلغ هزینه باید بیشتر از صفر باشد', 'danger')
            return render_template('payroll/add_expense.html', categories=categories,
                                   form=request.form, today=date.today()), 400

        expense = Expense(
            expense_number=next_document_number('expense'),
            category_id=category.id,
            amount=amount,
            description=(request.form.get('description') or '').strip() or None,
            expense_date=get_jalali_date(request.form, 'expense_date') if request.form.get('expense_date') else date.today(),
            payment_method=request.form.get('payment_method'),
            paid_to=(request.form.get('paid_to') or '').strip() or None,
            branch_id=request.form.get('branch_id', 1),
            status='confirmed',
            created_by=current_user.id,
        )

        # آپلود فاکتور: پسوند/حجم/امضا و نام‌گذاری همه در utils/uploads.py
        attachment_path = None
        file = request.files.get('attachment')
        if file and file.filename:
            from utils.uploads import UnsafeUpload, store_upload
            try:
                saved = store_upload(file, os.path.join('static', 'uploads', 'expenses'),
                                     kind='expense', prefix='inv-')
            except UnsafeUpload as exc:
                flash(f'فاکتور پذیرفته نشد: {exc}', 'danger')
                return render_template('payroll/add_expense.html', categories=categories,
                                       form=request.form, today=date.today()), 400
            attachment_path = os.path.join('static', 'uploads', 'expenses', saved)
        expense.attachment = attachment_path

        db.session.add(expense)

        if deduct_from_cashbox:
            cashbox = get_or_create_main_cashbox()
            if cashbox is not None:
                if amount > (cashbox.balance or 0):
                    flash('موجودی صندوق برای این هزینه کافی نیست', 'danger')
                    return render_template('payroll/add_expense.html', categories=categories,
                                           form=request.form), 400
                db.session.flush()
                cashbox.balance = (cashbox.balance or 0) - amount
                from models.finance import CashboxTransaction
                db.session.add(CashboxTransaction(
                    cashbox_id=cashbox.id, trans_type='out', amount=amount,
                    description=f'هزینه {expense.expense_number} — {category.name}',
                    reference_type='expense', reference_id=expense.id,
                    balance_after=cashbox.balance, created_by=current_user.id,
                ))
                expense.cashbox_id = cashbox.id

        _log('create', f'ثبت هزینه {expense.expense_number} مبلغ {amount:,.0f} تومان '
                        f'در دسته «{category.name}»', 'expense')
        db.session.commit()
        flash(f'هزینه «{category.name}» به مبلغ {amount:,.0f} تومان ثبت شد', 'success')
        return redirect(url_for('payroll.advanced_expenses'))

    return render_template('payroll/add_expense.html', categories=categories,
                           today=date.today(), form={})


@payroll_bp.route('/expenses/<int:id>/attachment')
@login_required
def expense_attachment(id):
    """دانلود فاکتور هزینه — قبلاً فایل ذخیره می‌شد ولی هیچ راه دسترسی نداشت."""
    import os
    from flask import current_app, send_file
    from models.finance import Expense

    expense = Expense.query.get_or_404(id)
    if not expense.attachment or not os.path.isfile(expense.attachment):
        abort(404)
    return send_file(expense.attachment, as_attachment=True,
                     download_name=os.path.basename(expense.attachment))


@payroll_bp.route('/expenses/categories')
@login_required
def expense_categories():
    """مسیر قدیمی؛ مدیریت دسته‌بندی‌ها اکنون از یک صفحه واحد انجام می‌شود."""
    return redirect(url_for('settings.expense_categories'))


@payroll_bp.route('/expenses/categories/add', methods=['POST'])
@login_required
@require_role('finance', 'create')
def add_expense_category():
    """سازگاری با فرم نسخه‌های قدیمی برنامه."""
    from models.finance import ExpenseCategory

    name = (request.form.get('name') or '').strip()
    code = (request.form.get('code') or '').strip().upper() or None
    if not name:
        flash('نام دسته‌بندی هزینه الزامی است', 'danger')
        return redirect(url_for('settings.expense_categories'))

    duplicate = ExpenseCategory.query.filter(db.func.lower(ExpenseCategory.name) == name.lower()).first()
    duplicate_code = code and ExpenseCategory.query.filter(db.func.lower(ExpenseCategory.code) == code.lower()).first()
    if duplicate or duplicate_code:
        flash('نام یا کد دسته‌بندی تکراری است', 'danger')
        return redirect(url_for('settings.expense_categories'))

    cat = ExpenseCategory(
        name=name, code=code,
        description=(request.form.get('description') or '').strip() or None,
        is_active=True,
    )
    db.session.add(cat)
    db.session.commit()
    flash(f'دسته‌بندی «{name}» اضافه شد', 'success')
    return redirect(url_for('settings.expense_categories'))


# ═══════════════════════════════════════════
#  گزارش مالی جامع
# ═══════════════════════════════════════════
@payroll_bp.route('/reports/comprehensive')
@login_required
def comprehensive_report():
    """گزارش مالی جامع — همه پنجره‌ها بر اساس ماه شمسی."""
    from models.finance import Payment, Expense, Payslip
    from models.registration import Registration
    from models.finance import SalaryContract
    from models.teacher import Teacher

    period = normalize_jalali_period(request.args.get('period')) or current_jalali_period()
    bounds = jalali_period_bounds(period)
    if not bounds:
        period = current_jalali_period()
        bounds = jalali_period_bounds(period)
    month_start, month_end = bounds
    period_choices = _period_choices(Payslip)

    income = db.session.query(db.func.sum(Payment.amount)).filter(
        Payment.payment_date >= month_start,
        Payment.payment_date <= month_end,
        Payment.status == 'confirmed'
    ).scalar() or 0

    expenses = db.session.query(db.func.sum(Expense.amount)).filter(
        Expense.expense_date >= month_start,
        Expense.expense_date <= month_end,
        Expense.status == 'confirmed'
    ).scalar() or 0

    salary_row = db.session.query(
        db.func.coalesce(db.func.sum(Payslip.net_amount), 0),
        db.func.coalesce(db.func.sum(Payslip.tax), 0),
        db.func.coalesce(db.func.sum(Payslip.insurance), 0),
    ).filter(Payslip.period == period, Payslip.status != 'cancelled').first()
    salaries, taxes, insurance = (salary_row or (0, 0, 0))

    total_debt = db.session.query(db.func.sum(Registration.remaining_amount)).filter(
        Registration.remaining_amount > 0,
        Registration.status == 'active'
    ).scalar() or 0

    monthly = db.session.query(
        Payslip.period,
        db.func.sum(Payslip.net_amount),
        db.func.sum(Payslip.tax),
    ).filter(Payslip.status != 'cancelled').group_by(Payslip.period).order_by(Payslip.period.desc()).limit(6).all()

    return render_template('payroll/comprehensive_report.html',
                           period=period, period_choices=period_choices,
                           period_label=jalali_period_label(period),
                           month_start=month_start, month_end=month_end,
                           income=income, expenses=expenses,
                           salaries=salaries, taxes=taxes, insurance=insurance,
                           total_debt=total_debt,
                           profit=income - expenses - salaries,
                           monthly=[{'period': row[0], 'net': row[1] or 0, 'tax': row[2] or 0}
                                    for row in monthly])
