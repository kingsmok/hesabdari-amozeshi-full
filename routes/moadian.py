"""
سامانه مودیان — صورتحساب الکترونیکی

شامل:
- تنظیمات اتصال و هویت مودی
- مدیریت طرف‌حساب‌ها با اعتبارسنجی کد ملی/شناسه ملی
- تعریف کالا و خدمت با شناسه ۱۳ رقمی و پرچم معافیت ارزش افزوده
- صدور صورتحساب با شماره منحصر به فرد مالیاتی ۲۲ کاراکتری
- ارسال به سامانه، استعلام وضعیت و لاگ کامل
"""
from datetime import date, datetime

from flask import (Blueprint, flash, jsonify, redirect, render_template,
                   request, url_for)
from flask_login import current_user, login_required

from extensions import db
from models.tax import (MoadianLog, TaxInvoice, TaxInvoiceItem, TaxParty,
                        TaxServiceItem, TaxSettings)
from utils.form_helpers import form_float, form_int, form_str, get_jalali_date
from utils.iran_tax import (INVOICE_PATTERNS, INVOICE_SUBJECTS, INVOICE_TYPES,
                            generate_tax_number, normalize_digits,
                            parse_tax_number, validate_economic_code,
                            validate_memory_id, validate_party_id,
                            validate_tax_number)
from utils.moadian import MoadianClient

moadian_bp = Blueprint('moadian', __name__)


def _settings():
    return TaxSettings.get()


def _log(invoice, action, result):
    """ثبت لاگ تعامل با سامانه."""
    entry = MoadianLog(
        invoice_id=invoice.id if invoice else None,
        action=action,
        success=bool(result.get('success')),
        http_status=result.get('http_status'),
        request_trace_id=result.get('trace_id'),
        message=(result.get('message') or '')[:4000],
        payload_preview=str(result.get('payload'))[:4000] if result.get('payload') else None,
        created_by=current_user.id if current_user.is_authenticated else None,
    )
    db.session.add(entry)
    return entry


# ═══════════════════════════════════════════
#  داشبورد
# ═══════════════════════════════════════════
@moadian_bp.route('/moadian')
@login_required
def dashboard():
    settings = _settings()
    invoices = TaxInvoice.query.order_by(TaxInvoice.created_at.desc()).limit(10).all()

    def _count(**filters):
        return TaxInvoice.query.filter_by(**filters).count()

    stats = {
        'total': TaxInvoice.query.count(),
        'draft': _count(status='draft'),
        'issued': _count(status='issued'),
        'sent': _count(status='sent'),
        'confirmed': _count(status='confirmed'),
        'rejected': _count(status='rejected'),
    }
    year_start = date(date.today().year, 1, 1)
    sales = TaxInvoice.query.filter(
        TaxInvoice.direction == 'sale', TaxInvoice.invoice_date >= year_start
    ).all()
    stats['sales_amount'] = sum(i.total_amount or 0 for i in sales)
    stats['sales_vat'] = sum(i.total_vat or 0 for i in sales)

    problems = MoadianClient(settings).check_configuration()
    logs = MoadianLog.query.order_by(MoadianLog.created_at.desc()).limit(10).all()

    return render_template('moadian/dashboard.html', settings=settings, stats=stats,
                           invoices=invoices, problems=problems, logs=logs,
                           patterns=INVOICE_PATTERNS)


# ═══════════════════════════════════════════
#  تنظیمات
# ═══════════════════════════════════════════
@moadian_bp.route('/moadian/settings', methods=['GET', 'POST'])
@login_required
def settings_page():
    settings = _settings()

    if request.method == 'POST':
        memory_id = form_str(request.form, 'memory_id').upper()
        if memory_id:
            ok, message = validate_memory_id(memory_id)
            if not ok:
                flash(message, 'error')
                return redirect(url_for('moadian.settings_page'))

        economic_code = normalize_digits(request.form.get('economic_code'))
        if economic_code and not validate_economic_code(economic_code):
            flash('کد اقتصادی باید ۱۲ یا ۱۴ رقم باشد', 'error')
            return redirect(url_for('moadian.settings_page'))

        seller_type = form_str(request.form, 'seller_type') or 'legal'
        seller_tin = normalize_digits(request.form.get('seller_tin'))
        if seller_tin:
            ok, message = validate_party_id(
                seller_tin, 'legal' if seller_type == 'legal' else 'real'
            )
            if not ok:
                flash(f'شناسه فروشنده: {message}', 'error')
                return redirect(url_for('moadian.settings_page'))

        settings.seller_name = form_str(request.form, 'seller_name')
        settings.seller_type = seller_type
        settings.seller_tin = seller_tin
        settings.economic_code = economic_code
        settings.registration_number = form_str(request.form, 'registration_number')
        settings.postal_code = normalize_digits(request.form.get('postal_code'))
        settings.branch_code = form_str(request.form, 'branch_code')
        settings.address = form_str(request.form, 'address')

        settings.moadian_enabled = bool(request.form.get('moadian_enabled'))
        settings.memory_id = memory_id
        settings.client_id = form_str(request.form, 'client_id') or memory_id
        settings.api_base_url = form_str(request.form, 'api_base_url') or settings.api_base_url
        settings.private_key_path = form_str(request.form, 'private_key_path')
        settings.certificate_path = form_str(request.form, 'certificate_path')
        settings.auto_send = bool(request.form.get('auto_send'))
        settings.sandbox_mode = bool(request.form.get('sandbox_mode'))

        settings.vat_rate = form_float(request.form, 'vat_rate', 10)
        settings.education_exempt = bool(request.form.get('education_exempt'))
        settings.default_stuff_id = normalize_digits(request.form.get('default_stuff_id'))

        settings.rent_withholding_rate = form_float(request.form, 'rent_withholding_rate', 10)
        settings.fee_withholding_rate = form_float(request.form, 'fee_withholding_rate', 10)
        settings.salary_year = form_str(request.form, 'salary_year') or settings.salary_year
        settings.salary_monthly_exemption = form_float(request.form, 'salary_monthly_exemption', 0)
        settings.employer_tax_file_code = form_str(request.form, 'employer_tax_file_code')

        db.session.commit()
        flash('تنظیمات مالیاتی ذخیره شد', 'success')
        return redirect(url_for('moadian.settings_page'))

    return render_template('moadian/settings.html', settings=settings)


@moadian_bp.route('/moadian/test-connection', methods=['POST'])
@login_required
def test_connection():
    settings = _settings()
    result = MoadianClient(settings).test_connection()
    _log(None, 'test', result)
    db.session.commit()
    flash(result['message'], 'success' if result['success'] else 'error')
    return redirect(url_for('moadian.settings_page'))


# ═══════════════════════════════════════════
#  ابزار شماره مالیاتی
# ═══════════════════════════════════════════
@moadian_bp.route('/moadian/tax-number-tool', methods=['GET', 'POST'])
@login_required
def tax_number_tool():
    settings = _settings()
    generated = None
    parsed = None
    check = None

    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'generate':
            memory_id = form_str(request.form, 'memory_id').upper() or (settings.memory_id or '')
            serial = form_int(request.form, 'serial', 1)
            issue_date = get_jalali_date(request.form, 'issue_date') or date.today()
            try:
                generated = generate_tax_number(memory_id, issue_date, serial)
                parsed = parse_tax_number(generated)
            except ValueError as exc:
                flash(str(exc), 'error')
        else:
            value = form_str(request.form, 'tax_number')
            ok, message = validate_tax_number(value)
            check = {'value': value, 'ok': ok, 'message': message}
            parsed = parse_tax_number(value)

    return render_template('moadian/tax_number_tool.html', settings=settings,
                           generated=generated, parsed=parsed, check=check)


@moadian_bp.route('/moadian/validate-id')
@login_required
def validate_id_api():
    """اعتبارسنجی زنده کد ملی/شناسه ملی در فرم‌ها."""
    code = request.args.get('code', '')
    party_type = request.args.get('type') or None
    ok, message = validate_party_id(code, party_type)
    return jsonify({'valid': ok, 'message': message})


# ═══════════════════════════════════════════
#  طرف‌حساب‌ها
# ═══════════════════════════════════════════
@moadian_bp.route('/moadian/parties')
@login_required
def parties():
    role = request.args.get('role', '')
    search = request.args.get('q', '').strip()
    query = TaxParty.query
    if role:
        query = query.filter(TaxParty.party_role.in_([role, 'both']))
    if search:
        query = query.filter(db.or_(
            TaxParty.name.contains(search),
            TaxParty.national_id.contains(search),
        ))
    items = query.order_by(TaxParty.name).all()
    invalid_count = TaxParty.query.filter_by(is_verified=False).count()
    return render_template('moadian/parties.html', parties=items, role=role,
                           q=search, invalid_count=invalid_count)


@moadian_bp.route('/moadian/parties/add', methods=['GET', 'POST'])
@moadian_bp.route('/moadian/parties/<int:party_id>/edit', methods=['GET', 'POST'])
@login_required
def party_form(party_id=None):
    party = TaxParty.query.get_or_404(party_id) if party_id else None

    if request.method == 'POST':
        party_type = form_str(request.form, 'party_type') or 'real'
        national_id = normalize_digits(request.form.get('national_id'))

        verified, message = True, 'مصرف‌کننده نهایی — نیازی به شناسه نیست'
        if party_type != 'consumer':
            verified, message = validate_party_id(national_id, party_type)
            if not verified and not request.form.get('force_save'):
                flash(f'{message} — برای ذخیره با شناسه نامعتبر، گزینه «ذخیره اجباری» را بزنید', 'error')
                return render_template('moadian/party_form.html', party=party,
                                       form=request.form, error=message)

        economic_code = normalize_digits(request.form.get('economic_code'))
        if economic_code and not validate_economic_code(economic_code):
            flash('کد اقتصادی باید ۱۲ یا ۱۴ رقم باشد', 'error')
            return render_template('moadian/party_form.html', party=party,
                                   form=request.form, error='کد اقتصادی نامعتبر')

        if party is None:
            party = TaxParty()
            db.session.add(party)

        party.name = form_str(request.form, 'name')
        party.party_role = form_str(request.form, 'party_role') or 'customer'
        party.party_type = party_type
        party.national_id = national_id
        party.economic_code = economic_code
        party.registration_number = form_str(request.form, 'registration_number')
        party.postal_code = normalize_digits(request.form.get('postal_code'))
        party.phone = normalize_digits(request.form.get('phone'))
        party.province = form_str(request.form, 'province')
        party.city = form_str(request.form, 'city')
        party.address = form_str(request.form, 'address')
        party.student_id = form_int(request.form, 'student_id') or None
        party.is_verified = verified
        party.verify_message = message
        party.is_active = bool(request.form.get('is_active', 'on'))
        party.notes = form_str(request.form, 'notes')

        db.session.commit()
        flash('طرف حساب ذخیره شد', 'success')
        return redirect(url_for('moadian.parties'))

    return render_template('moadian/party_form.html', party=party, form=None, error=None)


@moadian_bp.route('/moadian/parties/revalidate', methods=['POST'])
@login_required
def revalidate_parties():
    """اعتبارسنجی مجدد همه شناسه‌ها — مفید پس از ورود داده انبوه."""
    fixed = invalid = 0
    for party in TaxParty.query.all():
        if party.party_type == 'consumer':
            party.is_verified, party.verify_message = True, 'مصرف‌کننده نهایی'
            continue
        ok, message = validate_party_id(party.national_id, party.party_type)
        party.is_verified, party.verify_message = ok, message
        if ok:
            fixed += 1
        else:
            invalid += 1
    db.session.commit()
    flash(f'{fixed} شناسه معتبر و {invalid} شناسه نامعتبر شناسایی شد', 'info')
    return redirect(url_for('moadian.parties'))


@moadian_bp.route('/moadian/parties/import-students', methods=['POST'])
@login_required
def import_students_as_parties():
    """ساخت طرف‌حساب از هنرجویان دارای کد ملی (برای صدور صورتحساب)."""
    from models.student import Student

    created = 0
    existing = {p.student_id for p in TaxParty.query.filter(TaxParty.student_id.isnot(None))}
    for student in Student.query.filter(Student.national_code.isnot(None)).all():
        if student.id in existing:
            continue
        ok, message = validate_party_id(student.national_code, 'real')
        db.session.add(TaxParty(
            name=student.full_name,
            party_role='customer',
            party_type='real',
            national_id=normalize_digits(student.national_code),
            phone=getattr(student, 'mobile', None),
            student_id=student.id,
            is_verified=ok,
            verify_message=message,
        ))
        created += 1
    db.session.commit()
    flash(f'{created} هنرجو به فهرست طرف‌حساب‌های مالیاتی اضافه شد', 'success')
    return redirect(url_for('moadian.parties'))


# ═══════════════════════════════════════════
#  کالا و خدمات
# ═══════════════════════════════════════════
@moadian_bp.route('/moadian/items', methods=['GET', 'POST'])
@login_required
def service_items():
    settings = _settings()

    if request.method == 'POST':
        item_id = form_int(request.form, 'item_id')
        item = TaxServiceItem.query.get(item_id) if item_id else TaxServiceItem()
        if not item_id:
            db.session.add(item)

        item.title = form_str(request.form, 'title')
        item.stuff_id = normalize_digits(request.form.get('stuff_id'))
        item.unit = form_str(request.form, 'unit') or 'عدد'
        item.unit_price = form_float(request.form, 'unit_price')
        item.is_service = bool(request.form.get('is_service'))
        item.vat_exempt = bool(request.form.get('vat_exempt'))
        rate_value = request.form.get('vat_rate', '').strip()
        item.vat_rate = float(rate_value) if rate_value else None
        item.exempt_reason = form_str(request.form, 'exempt_reason')
        item.course_id = form_int(request.form, 'course_id') or None
        item.is_active = bool(request.form.get('is_active', 'on'))

        db.session.commit()
        flash('کالا/خدمت ذخیره شد', 'success')
        return redirect(url_for('moadian.service_items'))

    from models.course import Course
    items = TaxServiceItem.query.order_by(TaxServiceItem.title).all()
    courses = Course.query.order_by(Course.title).all()
    return render_template('moadian/items.html', items=items, courses=courses, settings=settings)


@moadian_bp.route('/moadian/items/<int:item_id>/delete', methods=['POST'])
@login_required
def delete_service_item(item_id):
    item = TaxServiceItem.query.get_or_404(item_id)
    item.is_active = False
    db.session.commit()
    flash('کالا/خدمت غیرفعال شد', 'warning')
    return redirect(url_for('moadian.service_items'))


@moadian_bp.route('/moadian/items/seed-courses', methods=['POST'])
@login_required
def seed_items_from_courses():
    """ساخت خودکار خدمت برای دوره‌های آموزشی با پرچم معافیت."""
    from models.course import Course

    settings = _settings()
    existing = {i.course_id for i in TaxServiceItem.query.filter(TaxServiceItem.course_id.isnot(None))}
    created = 0
    for course in Course.query.all():
        if course.id in existing:
            continue
        db.session.add(TaxServiceItem(
            title=f'خدمات آموزشی — {course.title}',
            stuff_id=settings.default_stuff_id,
            unit='دوره',
            unit_price=float(course.base_fee or 0),
            is_service=True,
            vat_exempt=bool(settings.education_exempt),
            exempt_reason='معافیت خدمات آموزشی' if settings.education_exempt else None,
            course_id=course.id,
        ))
        created += 1
    db.session.commit()
    flash(f'{created} خدمت آموزشی از دوره‌ها ساخته شد', 'success')
    return redirect(url_for('moadian.service_items'))


# ═══════════════════════════════════════════
#  صورتحساب‌ها
# ═══════════════════════════════════════════
@moadian_bp.route('/moadian/invoices')
@login_required
def invoices():
    direction = request.args.get('direction', '')
    status = request.args.get('status', '')
    page = request.args.get('page', 1, type=int)

    query = TaxInvoice.query
    if direction:
        query = query.filter_by(direction=direction)
    if status:
        query = query.filter_by(status=status)

    pagination = query.order_by(TaxInvoice.invoice_date.desc(),
                                TaxInvoice.id.desc()).paginate(page=page, per_page=25)
    return render_template('moadian/invoices.html', pagination=pagination,
                           direction=direction, status=status,
                           patterns=INVOICE_PATTERNS,
                           statuses=TaxInvoice.STATUS_LABELS)


def _next_invoice_number(direction):
    prefix = 'INV' if direction == 'sale' else 'PUR'
    last = TaxInvoice.query.filter_by(direction=direction).order_by(TaxInvoice.id.desc()).first()
    return f'{prefix}-{((last.id if last else 0) + 1):06d}'


@moadian_bp.route('/moadian/invoices/new', methods=['GET', 'POST'])
@login_required
def new_invoice():
    settings = _settings()

    if request.method == 'POST':
        direction = form_str(request.form, 'direction') or 'sale'
        pattern = form_str(request.form, 'pattern') or '1'
        invoice_type = form_str(request.form, 'invoice_type') or '1'
        party_id = form_int(request.form, 'party_id') or None

        if INVOICE_PATTERNS.get(pattern, {}).get('requires_buyer') and invoice_type == '1' and not party_id:
            flash('برای صورتحساب نوع اول، انتخاب خریدار الزامی است', 'error')
            return redirect(url_for('moadian.new_invoice'))

        party = TaxParty.query.get(party_id) if party_id else None
        invoice = TaxInvoice(
            invoice_number=form_str(request.form, 'invoice_number') or _next_invoice_number(direction),
            direction=direction,
            invoice_date=get_jalali_date(request.form, 'invoice_date') or date.today(),
            pattern=pattern,
            invoice_type=invoice_type,
            subject=form_str(request.form, 'subject') or '1',
            party_id=party_id,
            party_name_snapshot=party.name if party else 'مصرف‌کننده نهایی',
            currency=form_str(request.form, 'currency') or 'IRR',
            exchange_rate=form_float(request.form, 'exchange_rate', 1) or 1,
            description=form_str(request.form, 'description'),
            status='draft',
            created_by=current_user.id,
        )
        db.session.add(invoice)
        db.session.flush()

        titles = request.form.getlist('item_title[]')
        stuff_ids = request.form.getlist('item_stuff_id[]')
        units = request.form.getlist('item_unit[]')
        quantities = request.form.getlist('item_quantity[]')
        prices = request.form.getlist('item_price[]')
        discounts = request.form.getlist('item_discount[]')
        exempts = request.form.getlist('item_exempt[]')
        rates = request.form.getlist('item_vat_rate[]')

        def _value(collection, index, default=''):
            return collection[index] if index < len(collection) else default

        def _float(collection, index, default=0.0):
            try:
                return float(_value(collection, index) or default)
            except ValueError:
                return default

        row = 0
        for index, title in enumerate(titles):
            if not title.strip():
                continue
            row += 1
            exempt = _value(exempts, index, '0') in ('1', 'on', 'true')
            item = TaxInvoiceItem(
                invoice_id=invoice.id,
                row_number=row,
                title=title.strip(),
                stuff_id=normalize_digits(_value(stuff_ids, index)) or settings.default_stuff_id,
                unit=_value(units, index, 'عدد') or 'عدد',
                quantity=_float(quantities, index, 1),
                unit_price=_float(prices, index),
                discount=_float(discounts, index),
                vat_exempt=exempt,
                vat_rate=0 if exempt else _float(rates, index, settings.vat_rate or 0),
            )
            db.session.add(item)

        if row == 0:
            db.session.rollback()
            flash('حداقل یک ردیف کالا/خدمت وارد کنید', 'error')
            return redirect(url_for('moadian.new_invoice'))

        db.session.flush()
        invoice.recalculate(settings.vat_rate or 0)
        db.session.commit()

        flash(f'صورتحساب {invoice.invoice_number} ثبت شد', 'success')
        return redirect(url_for('moadian.view_invoice', invoice_id=invoice.id))

    parties_list = TaxParty.query.filter_by(is_active=True).order_by(TaxParty.name).all()
    items_list = TaxServiceItem.query.filter_by(is_active=True).order_by(TaxServiceItem.title).all()
    return render_template('moadian/invoice_form.html', settings=settings,
                           parties=parties_list, service_items=items_list,
                           patterns=INVOICE_PATTERNS, types=INVOICE_TYPES,
                           subjects=INVOICE_SUBJECTS,
                           suggested_number=_next_invoice_number('sale'))


@moadian_bp.route('/moadian/invoices/<int:invoice_id>')
@login_required
def view_invoice(invoice_id):
    invoice = TaxInvoice.query.get_or_404(invoice_id)
    settings = _settings()
    parsed = parse_tax_number(invoice.tax_number) if invoice.tax_number else None
    logs = invoice.logs.order_by(MoadianLog.created_at.desc()).all()
    return render_template('moadian/invoice_view.html', invoice=invoice, settings=settings,
                           parsed=parsed, logs=logs, patterns=INVOICE_PATTERNS,
                           types=INVOICE_TYPES, subjects=INVOICE_SUBJECTS)


@moadian_bp.route('/moadian/invoices/<int:invoice_id>/issue', methods=['POST'])
@login_required
def issue_invoice(invoice_id):
    """صدور نهایی: تخصیص شماره منحصر به فرد مالیاتی ۲۲ کاراکتری."""
    invoice = TaxInvoice.query.get_or_404(invoice_id)
    settings = _settings()

    if invoice.tax_number:
        flash('این صورتحساب قبلاً شماره مالیاتی گرفته است', 'warning')
        return redirect(url_for('moadian.view_invoice', invoice_id=invoice.id))

    ok, message = validate_memory_id(settings.memory_id)
    if not ok:
        flash(f'{message} — ابتدا در تنظیمات، شناسه حافظه را ثبت کنید', 'error')
        return redirect(url_for('moadian.view_invoice', invoice_id=invoice.id))

    serial = (settings.last_serial or 0) + 1
    try:
        invoice.tax_number = generate_tax_number(settings.memory_id, invoice.invoice_date, serial)
    except ValueError as exc:
        flash(str(exc), 'error')
        return redirect(url_for('moadian.view_invoice', invoice_id=invoice.id))

    invoice.internal_serial = serial
    invoice.memory_id = settings.memory_id
    invoice.status = 'issued'
    invoice.recalculate(settings.vat_rate or 0)
    settings.last_serial = serial
    db.session.commit()

    flash(f'شماره مالیاتی صادر شد: {invoice.tax_number}', 'success')
    if settings.auto_send:
        return redirect(url_for('moadian.send_invoice', invoice_id=invoice.id))
    return redirect(url_for('moadian.view_invoice', invoice_id=invoice.id))


@moadian_bp.route('/moadian/invoices/<int:invoice_id>/send', methods=['GET', 'POST'])
@login_required
def send_invoice(invoice_id):
    invoice = TaxInvoice.query.get_or_404(invoice_id)
    settings = _settings()

    if invoice.direction != 'sale':
        flash('فقط صورتحساب فروش به سامانه مودیان ارسال می‌شود', 'error')
        return redirect(url_for('moadian.view_invoice', invoice_id=invoice.id))
    if not invoice.tax_number:
        flash('ابتدا صورتحساب را صادر کنید تا شماره مالیاتی بگیرد', 'error')
        return redirect(url_for('moadian.view_invoice', invoice_id=invoice.id))

    result = MoadianClient(settings).send_invoice(invoice)
    _log(invoice, 'send', result)

    if result['success']:
        invoice.status = 'sent'
        invoice.moadian_uid = result.get('uid')
        invoice.moadian_reference = result.get('reference_number')
        invoice.moadian_status = 'SENT'
        invoice.sent_at = datetime.utcnow()
    else:
        invoice.status = 'rejected'
        invoice.moadian_status = 'ERROR'
    invoice.moadian_message = (result.get('message') or '')[:4000]
    db.session.commit()

    flash(result['message'], 'success' if result['success'] else 'error')
    return redirect(url_for('moadian.view_invoice', invoice_id=invoice.id))


@moadian_bp.route('/moadian/invoices/<int:invoice_id>/inquiry', methods=['POST'])
@login_required
def inquiry_invoice(invoice_id):
    invoice = TaxInvoice.query.get_or_404(invoice_id)
    if not invoice.moadian_reference:
        flash('این صورتحساب هنوز شماره مرجع ندارد', 'error')
        return redirect(url_for('moadian.view_invoice', invoice_id=invoice.id))

    result = MoadianClient(_settings()).inquiry(invoice.moadian_reference)
    _log(invoice, 'inquiry', result)

    status = (result.get('status') or '').upper()
    if status == 'SUCCESS':
        invoice.status = 'confirmed'
        invoice.confirmed_at = datetime.utcnow()
    elif status in ('FAILED', 'ERROR'):
        invoice.status = 'rejected'
    invoice.moadian_status = status or invoice.moadian_status
    invoice.moadian_message = (result.get('message') or '')[:4000]
    db.session.commit()

    flash(result['message'], 'success' if result['success'] else 'error')
    return redirect(url_for('moadian.view_invoice', invoice_id=invoice.id))


@moadian_bp.route('/moadian/invoices/<int:invoice_id>/cancel', methods=['POST'])
@login_required
def cancel_invoice(invoice_id):
    invoice = TaxInvoice.query.get_or_404(invoice_id)
    invoice.status = 'cancelled'
    invoice.subject = '3'  # ابطالی
    db.session.commit()
    flash('صورتحساب ابطال شد', 'warning')
    return redirect(url_for('moadian.view_invoice', invoice_id=invoice.id))


@moadian_bp.route('/moadian/invoices/<int:invoice_id>/print')
@login_required
def print_invoice(invoice_id):
    invoice = TaxInvoice.query.get_or_404(invoice_id)
    settings = _settings()
    return render_template('moadian/invoice_print.html', invoice=invoice,
                           settings=settings, patterns=INVOICE_PATTERNS)


@moadian_bp.route('/moadian/invoices/<int:invoice_id>/payload')
@login_required
def invoice_payload(invoice_id):
    """نمایش JSON نهایی ارسالی به سامانه — برای عیب‌یابی."""
    from utils.moadian import build_invoice_payload
    invoice = TaxInvoice.query.get_or_404(invoice_id)
    return jsonify(build_invoice_payload(invoice, _settings()))


@moadian_bp.route('/moadian/invoices/from-payment/<int:payment_id>', methods=['POST'])
@login_required
def invoice_from_payment(payment_id):
    """تولید صورتحساب فروش از یک پرداخت شهریه."""
    from models.finance import Payment
    from models.student import Student

    payment = Payment.query.get_or_404(payment_id)
    settings = _settings()

    existing = TaxInvoice.query.filter_by(payment_id=payment.id).first()
    if existing:
        flash('برای این پرداخت قبلاً صورتحساب صادر شده است', 'warning')
        return redirect(url_for('moadian.view_invoice', invoice_id=existing.id))

    student = Student.query.get(payment.student_id)
    party = TaxParty.query.filter_by(student_id=payment.student_id).first()
    if party is None and student is not None:
        ok, message = validate_party_id(student.national_code, 'real')
        party = TaxParty(
            name=student.full_name, party_role='customer', party_type='real',
            national_id=normalize_digits(student.national_code),
            student_id=student.id, is_verified=ok, verify_message=message,
        )
        db.session.add(party)
        db.session.flush()

    exempt = bool(settings.education_exempt)
    invoice = TaxInvoice(
        invoice_number=_next_invoice_number('sale'),
        direction='sale',
        invoice_date=payment.payment_date or date.today(),
        pattern='1',
        invoice_type='1' if (party and party.is_verified) else '2',
        subject='1',
        party_id=party.id if party else None,
        party_name_snapshot=party.name if party else 'مصرف‌کننده نهایی',
        payment_id=payment.id,
        registration_id=payment.registration_id,
        description=f'بابت رسید پرداخت {payment.receipt_no}',
        status='draft',
        created_by=current_user.id,
    )
    db.session.add(invoice)
    db.session.flush()

    db.session.add(TaxInvoiceItem(
        invoice_id=invoice.id, row_number=1,
        title='شهریه خدمات آموزشی',
        stuff_id=settings.default_stuff_id,
        unit='دوره', quantity=1,
        unit_price=float(payment.amount or 0),
        vat_exempt=exempt,
        vat_rate=0 if exempt else (settings.vat_rate or 0),
    ))
    db.session.flush()
    invoice.recalculate(settings.vat_rate or 0)
    db.session.commit()

    flash('صورتحساب از روی پرداخت ساخته شد', 'success')
    return redirect(url_for('moadian.view_invoice', invoice_id=invoice.id))


@moadian_bp.route('/moadian/logs')
@login_required
def logs():
    page = request.args.get('page', 1, type=int)
    pagination = MoadianLog.query.order_by(MoadianLog.created_at.desc()).paginate(page=page, per_page=40)
    return render_template('moadian/logs.html', pagination=pagination)
