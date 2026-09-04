"""
آزمون ابطال/مرجوعی پرداخت و پنجره‌های «ماه جاری» (بازبینی امنیت/داده — B7 و B8)
════════════════════════════════════════════════════════════════════════
B8: مدل `Payment` فیلدهای `status='cancelled'`، `cancelled_by` و `cancelled_at`
را داشت ولی هیچ مسیر ابطال/مرجوعی وجود نداشت ⇒ تنها راه اصلاح یک اشتباه،
ویرایش دستی دیتابیس بود و مانده ثبت‌نام/اقساط هم بازمحاسبه نمی‌شد.

B7: آمار «ماه جاری» با `today.replace(day=1)` پنجره میلادی می‌ساخت؛ امروز
۱۴۰۵/۰۶/۱۲ بود ولی پنجره از ۲۰۲۶-۰۹-۰۱ (= ۱۴۰۵/۰۶/۱۰) شروع می‌شد ⇒ ۹ روز
اول شهریور از آمار بیرون می‌ماند و پرداخت ۷ میلیونیِ ۱۴۰۵/۰۶/۰۱ در داشبورد
مالی دیده نمی‌شد.

دیتابیس توسعه؛ همه ردیف‌های آزمونی در پایان پاک می‌شوند.
"""
import os
import re
import sys
from datetime import date, datetime, timedelta

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app                                   # noqa: E402
from extensions import db                                    # noqa: E402
from models.course import Course, Field                              # noqa: E402
from models.finance import Cashbox, CashboxTransaction, Payment  # noqa: E402
from models.registration import Installment, Registration      # noqa: E402
from models.student import Student                             # noqa: E402


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


@pytest.fixture(scope='module')
def admin_id(test_app):
    """شناسه یک حساب مدیر کل — در دیتابیس تازه‌نصب مدیری نیست (ویزارد /setup
    آن را می‌سازد)، پس در صورت نبود موقتاً ساخته و در پایان پاک می‌شود.

    نکته‌ای که ارزش دانستن دارد: `yield` باید بیرون از `app_context()` باشد.
    اگر context باز بماند، همان SELECT اول یک تراکنشِ خواندن SQLite را باز
    نگه می‌دارد و نوشتنِ بقیهٔ تست‌ها (با اتصال دیگر) تا انقضای مهلت شلوغی،
    «database is locked» می‌شود — فقط روی دیتابیسی که مدیر دارد، چون شاخهٔ
    «ساخت کاربر جدید» با commit اتصال را آزاد می‌کند.
    """
    from models.user import User, Role
    with test_app.app_context():
        admin = User.query.filter_by(is_admin=True, is_active=True).first()
        existing_id = admin.id if admin is not None else None
        created_id = None
        if existing_id is None:
            role = Role.query.filter_by(is_admin=True).first() or Role.query.first()
            created = User(username='test_root_admin_fin', full_name='مدیر آزمون مالی',
                           is_admin=True, is_active=True,
                           role_id=role.id if role else None)
            created.set_password('Test-Only-Strong-123!')
            db.session.add(created)
            db.session.commit()
            created_id = created.id
    yield existing_id or created_id
    if created_id is not None:
        with test_app.app_context():
            row = db.session.get(User, created_id)
            if row is not None:
                from models.user import ActivityLog
                ActivityLog.query.filter_by(user_id=created_id).delete(synchronize_session=False)
                db.session.delete(row)
                db.session.commit()

@pytest.fixture
def client(test_app, admin_id):
    http = test_app.test_client()
    with http.session_transaction() as sess:
        sess['_user_id'] = str(admin_id)
        sess['_fresh'] = True
    return http


@pytest.fixture
def tuition(test_app):
    """یک ثبت‌نام آزمونی با یک قسط معوق (کد FINTEST تا با داده واقعی قاتی نشود).

    موجودی صندوق در ابتدا گرفته و در پایان برمی‌گردد؛ ردیف‌های آزمونی کامل پاک
    می‌شوند تا دیتابیس توسعه تمیز بماند.
    """
    from models.course import Field
    tag = datetime.now().strftime('%H%M%S%f')[:8]
    ids = {}
    with test_app.app_context():
        from models.finance import get_or_create_main_cashbox
        box = get_or_create_main_cashbox()
        box_before = (box.id, box.balance or 0) if box else (None, 0)

        field = Field.query.first()
        if field is None:
            field = Field(name=f'رشته آزمونی {tag}', code=f'FINF{tag}')
            db.session.add(field)
            db.session.flush()
            ids['field'] = field.id
        course = Course(title=f'دوره آزمونی {tag}', code=f'FINTEST-{tag}',
                        field_id=field.id, base_fee=10_000_000)
        db.session.add(course)
        student = Student(first_name='آزمون', last_name=f'ابطال{tag}',
                          student_code=f'FINTESTS{tag}', mobile=f'0912{tag[:7]}')
        db.session.add(student)
        db.session.flush()
        registration = Registration(student_id=student.id, course_id=course.id,
                                    total_fee=10_000_000, paid_amount=0,
                                    remaining_amount=10_000_000, status='active',
                                    reg_code=f'REG-FINTEST-{tag}')
        db.session.add(registration)
        db.session.flush()
        installment = Installment(registration_id=registration.id, installment_number=1,
                                  amount=5_000_000, late_fee=200_000,
                                  due_date=date.today() - timedelta(days=9),
                                  paid_amount=0, status='pending')
        db.session.add(installment)
        db.session.flush()
        ids.update({'course': course.id, 'student': student.id,
                    'registration': registration.id, 'installment': installment.id,
                    'box_before': box_before})
        db.session.commit()

    yield ids

    with test_app.app_context():
        payment_ids = [row.id for row in Payment.query.filter(
            (Payment.registration_id == ids['registration'])
            | (Payment.installment_id == ids['installment'])).all()]
        if payment_ids:
            # اول تراکنش‌های صندوق (وابسته)، بعد خود پرداخت‌ها
            CashboxTransaction.query.filter(
                CashboxTransaction.reference_type == 'payment',
                CashboxTransaction.reference_id.in_(payment_ids)
            ).delete(synchronize_session=False)
            Payment.query.filter(Payment.id.in_(payment_ids)).delete(synchronize_session=False)
        Installment.query.filter_by(id=ids['installment']).delete(synchronize_session=False)
        for model, key in ((Registration, 'registration'), (Student, 'student'),
                           (Course, 'course')):
            row = db.session.get(model, ids[key])
            if row is not None:
                db.session.delete(row)
        if 'field' in ids:
            row = db.session.get(Field, ids['field'])
            if row is not None:
                db.session.delete(row)
        box_id, box_balance = ids['box_before']
        if box_id:
            box = db.session.get(Cashbox, box_id)
            if box is not None:
                box.balance = box_balance
        db.session.commit()


def _rows(test_app, ids):
    with test_app.app_context():
        registration = db.session.get(Registration, ids['registration'])
        installment = db.session.get(Installment, ids['installment'])
        payment = Payment.query.filter_by(installment_id=installment.id).order_by(
            Payment.id.desc()).first()
        box = db.session.get(Cashbox, payment.cashbox_id) if payment and payment.cashbox_id else None
        return {
            'reg_paid': registration.paid_amount, 'reg_due': registration.remaining_amount,
            'inst_paid': installment.paid_amount, 'inst_status': installment.status,
            'inst_remaining': installment.remaining,
            'pay_status': payment.status if payment else None,
            'reason': payment.cancel_reason if payment else None,
            'refunded': payment.refunded_amount if payment else None,
            'box': box.balance if box else None,
            'box_id': box.id if box else None,
        }


class TestPaymentFlow:
    def test_add_payment_updates_everything(self, client, test_app, tuition):
        payload = {'student_id': tuition['student'], 'registration_id': tuition['registration'],
                   'installment_id': tuition['installment'], 'amount': '5,200,000',
                   'payment_method': 'cash', 'description': 'پرداخت آزمونی ابطال'}
        response = client.post('/finance/payments/add', data=payload, follow_redirects=False)
        assert response.status_code in (200, 302), response.status_code
        after = _rows(test_app, tuition)
        assert after['pay_status'] == 'confirmed'
        assert after['reg_paid'] == pytest.approx(5_200_000)
        assert after['reg_due'] == pytest.approx(4_800_000)
        # ۵٬۲۰۰٬۰۰۰ = اصل ۵ میلیونی + جریمه ۲۰۰ هزار ⇒ قسط باید تسویه باشد
        assert after['inst_status'] == 'paid'
        assert after['box'] is not None and after['box'] >= 5_200_000
        assert after['box_id'], 'cashbox_id ثبت نشده ⇒ مرجوعی قابل محاسبه نیست'

    def test_cancel_requires_reason(self, client, test_app, tuition):
        client.post('/finance/payments/add', data={
            'student_id': tuition['student'], 'registration_id': tuition['registration'],
            'installment_id': tuition['installment'], 'amount': '5200000',
            'payment_method': 'cash', 'description': 'پرداخت آزمونی ابطال'})
        before = _rows(test_app, tuition)
        response = client.post(f'/finance/payments/{_payment_id(test_app, tuition)}/cancel',
                              data={'reason': ''}, follow_redirects=False)
        assert response.status_code == 302
        after = _rows(test_app, tuition)
        assert after['pay_status'] == before['pay_status'] == 'confirmed', 'ابطال بی‌دلیل نباید بشود'
        assert after['reg_paid'] == before['reg_paid']

    def test_cancel_refunds_and_recomputes_balance(self, client, test_app, tuition):
        client.post('/finance/payments/add', data={
            'student_id': tuition['student'], 'registration_id': tuition['registration'],
            'installment_id': tuition['installment'], 'amount': '5200000',
            'payment_method': 'cash', 'description': 'پرداخت آزمونی ابطال'})
        payment_id = _payment_id(test_app, tuition)
        before = _rows(test_app, tuition)
        assert before['reg_paid'] == pytest.approx(5_200_000)

        response = client.post(f'/finance/payments/{payment_id}/cancel',
                              data={'reason': 'مبلغ اشتباه وارد شد', 'refund': 'on'},
                              follow_redirects=False)
        assert response.status_code == 302
        after = _rows(test_app, tuition)
        assert after['pay_status'] == 'cancelled'
        assert after['reason'] == 'مبلغ اشتباه وارد شد'
        assert after['reg_paid'] == pytest.approx(0)
        assert after['reg_due'] == pytest.approx(10_000_000)
        assert after['inst_status'] == 'pending'
        assert after['inst_paid'] == pytest.approx(0)
        # پول از صندوق هم باید خارج شده باشد (مرجوعی به هنرجو)
        assert after['box'] == pytest.approx(before['box'] - 5_200_000)
        assert after['refunded'] == pytest.approx(5_200_000)

    def test_cancel_without_refund_keeps_cashbox(self, client, test_app, tuition):
        client.post('/finance/payments/add', data={
            'student_id': tuition['student'], 'registration_id': tuition['registration'],
            'installment_id': tuition['installment'], 'amount': '3000000',
            'payment_method': 'cash', 'description': 'پرداخت آزمونی ابطال'})
        payment_id = _payment_id(test_app, tuition)
        before = _rows(test_app, tuition)
        client.post(f'/finance/payments/{payment_id}/cancel',
                    data={'reason': 'پرداخت تکراری بود'}, follow_redirects=False)
        after = _rows(test_app, tuition)
        assert after['pay_status'] == 'cancelled'
        assert after['box'] == pytest.approx(before['box']), 'بدون تیک مرجوعی، صندوق نباید تکان بخورد'
        assert after['refunded'] in (0, None, 0.0)

    def test_restore_reverses_cancel(self, client, test_app, tuition):
        client.post('/finance/payments/add', data={
            'student_id': tuition['student'], 'registration_id': tuition['registration'],
            'installment_id': tuition['installment'], 'amount': '5200000',
            'payment_method': 'cash', 'description': 'پرداخت آزمونی ابطال'})
        payment_id = _payment_id(test_app, tuition)
        before = _rows(test_app, tuition)
        client.post(f'/finance/payments/{payment_id}/cancel',
                    data={'reason': 'اشتباه اپراتور', 'refund': 'on'})
        mid = _rows(test_app, tuition)
        assert mid['pay_status'] == 'cancelled'

        response = client.post(f'/finance/payments/{payment_id}/restore', data={},
                              follow_redirects=False)
        assert response.status_code == 302
        after = _rows(test_app, tuition)
        assert after['pay_status'] == 'confirmed'
        assert after['reason'] is None
        assert after['reg_paid'] == pytest.approx(before['reg_paid'])
        assert after['box'] == pytest.approx(before['box']), 'مرجوعی باید به صندوق برگردد'
        assert after['inst_status'] == 'paid'

    def test_refund_blocked_when_box_is_short(self, client, test_app, tuition):
        client.post('/finance/payments/add', data={
            'student_id': tuition['student'], 'registration_id': tuition['registration'],
            'installment_id': tuition['installment'], 'amount': '5200000',
            'payment_method': 'cash', 'description': 'پرداخت آزمونی ابطال'})
        payment_id = _payment_id(test_app, tuition)
        with test_app.app_context():
            payment = db.session.get(Payment, payment_id)
            box = db.session.get(Cashbox, payment.cashbox_id)
            box.balance = 10_000          # عمداً کمتر از مبلغ مرجوعی
            db.session.commit()

        response = client.post(f'/finance/payments/{payment_id}/cancel',
                              data={'reason': 'صندوق خالی است', 'refund': 'on'},
                              follow_redirects=False)
        assert response.status_code == 302
        after = _rows(test_app, tuition)
        assert after['pay_status'] == 'confirmed', 'با موجودی ناکافی نباید ابطال شود'
        assert after['reg_paid'] == pytest.approx(5_200_000)

    def test_double_cancel_is_rejected(self, client, test_app, tuition):
        client.post('/finance/payments/add', data={
            'student_id': tuition['student'], 'registration_id': tuition['registration'],
            'installment_id': tuition['installment'], 'amount': '1000000',
            'payment_method': 'card', 'description': 'پرداخت آزمونی ابطال'})
        payment_id = _payment_id(test_app, tuition)
        first = client.post(f'/finance/payments/{payment_id}/cancel',
                           data={'reason': 'دلیل اول'})
        second = client.post(f'/finance/payments/{payment_id}/cancel',
                            data={'reason': 'دلیل دوم'})
        assert first.status_code == 302 and second.status_code == 302
        with test_app.app_context():
            payment = db.session.get(Payment, payment_id)
            assert payment.cancel_reason == 'دلیل اول', 'ابطال دوم نباید دلیل اول را بازنویسی کند'
        # ابطال اول مانده را به صفر برگرداند؛ ابطال دوم نباید دوباره کم کند
        # (یعنی paid_amount منفی نشود) و نباید مبلغ صندوق را جابه‌جا کند
        after = _rows(test_app, tuition)
        assert after['reg_paid'] == pytest.approx(0), 'ابطال تکراری مبلغ را دو بار کم کرد'
        assert after['reg_due'] == pytest.approx(10_000_000)
        assert after['inst_paid'] == pytest.approx(0)
        with test_app.app_context():
            payment = db.session.get(Payment, payment_id)
            assert payment.cancelled_at is not None

    def test_card_payment_touches_no_cashbox(self, client, test_app, tuition):
        client.post('/finance/payments/add', data={
            'student_id': tuition['student'], 'registration_id': tuition['registration'],
            'installment_id': tuition['installment'], 'amount': '2000000',
            'payment_method': 'card', 'card_number': '60379911',
            'tracking_number': 'TRX-TEST', 'description': 'پرداخت آزمونی ابطال'})
        payment_id = _payment_id(test_app, tuition)
        before = _rows(test_app, tuition)
        assert before['box'] is None or before['box_id'] is None, \
            'پرداخت کارت نباید به صندوق نقدی بخورد'
        client.post(f'/finance/payments/{payment_id}/cancel', data={'reason': 'کارت ناموفق'})
        after = _rows(test_app, tuition)
        assert after['pay_status'] == 'cancelled'
        assert after['refunded'] in (0, None, 0.0)


def _payment_id(test_app, tuition):
    with test_app.app_context():
        payment = Payment.query.filter_by(installment_id=tuition['installment']).order_by(
            Payment.id.desc()).first()
        assert payment is not None, 'پرداخت آزمونی ثبت نشد'
        return payment.id


class TestInstallmentPaymentRoute:
    """مسیر «پرداخت قسط» در داشبورد اقساط (routes/new_features.py)."""

    def test_late_fee_survives_when_form_omits_it(self, client, test_app, tuition):
        """قبلاً نبودِ فیلد late_fee در فرم، جریمه ثبت‌شده را صفر می‌کرد."""
        response = client.post(f"/finance/installments/{tuition['installment']}/pay",
                              data={'amount': '5200000', 'method': 'cash'},
                              follow_redirects=False)
        assert response.status_code == 302
        after = _rows(test_app, tuition)
        assert after['inst_status'] == 'paid', 'جریمه پاک شد ⇒ مانده و وضعیت قسط غلط شد'
        assert after['reg_paid'] == pytest.approx(5_200_000)
        with test_app.app_context():
            installment = db.session.get(Installment, tuition['installment'])
            assert installment.late_fee == pytest.approx(200_000), 'جریمه قسط پاک شده'
            payment = Payment.query.filter_by(installment_id=installment.id).first()
            assert payment is not None, 'پرداخت قسط به جدول payments وصل نمی‌شود'
            assert payment.cashbox_id is not None, 'صندوق ثبت نشده ⇒ ابطال/مرجوعی ممکن نیست'

    def test_overpayment_is_still_blocked(self, client, test_app, tuition):
        response = client.post(f"/finance/installments/{tuition['installment']}/pay",
                              data={'amount': '9000000', 'method': 'cash'},
                              follow_redirects=False)
        assert response.status_code == 302
        after = _rows(test_app, tuition)
        assert after['inst_status'] == 'pending'
        assert after['reg_paid'] == pytest.approx(0)


class TestDocumentNumbers:
    """رسیدها باید از `document_sequences` شماره بگیرند، نه `last.id+1`."""

    def test_routes_do_not_build_receipts_from_max_id(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        offenders = []
        for rel in ('routes/finance.py', 'routes/new_features.py'):
            with open(os.path.join(root, rel), encoding='utf-8') as handle:
                source = handle.read()
            for line in source.splitlines():
                if 'PAY-' in line and '.id + 1' in line.replace('+1', ' + 1'):
                    offenders.append((rel, line.strip()[:80]))
        assert not offenders, f'شماره‌گذاری مبتنی بر MAX(id) باقی مانده: {offenders}'

    def test_receipt_from_add_payment_is_sequenced(self, client, test_app, tuition):
        client.post('/finance/payments/add', data={
            'student_id': tuition['student'], 'registration_id': tuition['registration'],
            'installment_id': tuition['installment'], 'amount': '500000',
            'payment_method': 'card', 'description': 'پرداخت آزمونی ابطال'})
        with test_app.app_context():
            payment = Payment.query.filter_by(installment_id=tuition['installment']).first()
            assert payment.receipt_no.startswith('PAY-14'), \
                f'شماره رسید از توالی استاندارد نیست: {payment.receipt_no}'


class TestCombinedPayment:
    """پرداخت ترکیبی: ریز سهم‌ها ثبت و فقط سهم نقدی به صندوق می‌خورد."""

    def test_cash_part_reaches_box_only(self, client, test_app, tuition):
        before = _rows(test_app, tuition)
        # قبل از اولین پرداخت، هیچ ردیفی به صندوق وصل نیست ⇒ before['box'] برابر
        # None است؛ پس مبنای مقایسه باید موجودی اولیه‌ای باشد که fixture گرفته.
        box0 = (tuition['box_before'][1] or 0)
        client.post('/finance/payments/add', data={
            'student_id': tuition['student'], 'registration_id': tuition['registration'],
            'installment_id': tuition['installment'], 'amount': '5200000',
            'payment_method': 'combined', 'cash_amount': '1200000',
            'card_amount': '4000000', 'check_amount': '0',
            'description': 'پرداخت آزمونی ابطال'})
        payment_id = _payment_id(test_app, tuition)
        with test_app.app_context():
            payment = db.session.get(Payment, payment_id)
            assert payment.cash_amount == pytest.approx(1_200_000)
            assert payment.card_amount == pytest.approx(4_000_000)
            assert payment.cashbox_id is not None
        after = _rows(test_app, tuition)
        assert after['box'] == pytest.approx(box0 + 1_200_000), \
            'صندوق باید فقط سهم نقدی را بگیرد'
        assert after['reg_paid'] == pytest.approx(5_200_000)
        assert after['inst_status'] == 'paid'

        # ابطال با مرجوعی: فقط ۱/۲ میلیون نقد از صندوق خارج می‌شود
        client.post(f'/finance/payments/{payment_id}/cancel',
                    data={'reason': 'مرجوعی ترکیبی', 'refund': 'on'})
        final = _rows(test_app, tuition)
        assert final['refunded'] == pytest.approx(1_200_000)
        assert final['box'] == pytest.approx(box0), 'صندوق باید به حالت اول برگردد'
        assert final['reg_paid'] == pytest.approx(0)

    def test_parts_must_sum_to_amount(self, client, test_app, tuition):
        client.post('/finance/payments/add', data={
            'student_id': tuition['student'], 'registration_id': tuition['registration'],
            'installment_id': tuition['installment'], 'amount': '5200000',
            'payment_method': 'combined', 'cash_amount': '1000000', 'card_amount': '2000000',
            'description': 'پرداخت آزمونی ابطال'})
        # جمع بخش‌ها ۳ میلیون است نه ۵/۲ ⇒ نباید پرداختی ثبت شود
        with test_app.app_context():
            count = Payment.query.filter_by(installment_id=tuition['installment']).count()
        assert count == 0, 'پرداخت نابالغ ثبت شد'
        assert _rows(test_app, tuition)['reg_paid'] == pytest.approx(0)


class TestPaymentFormWiring:
    """فرم ثبت پرداخت باید به ثبت‌نام/قسط وصل باشد (وگرنه مانده هنرجو کم نمی‌شود)."""

    def test_form_exposes_linkage_and_method_fields(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(root, 'templates', 'finance', 'add_payment.html'),
                  encoding='utf-8') as handle:
            form = handle.read()
        for field in ('name="registration_id"', 'name="installment_id"', 'name="cash_amount"',
                      'name="card_amount"', 'name="check_amount"', 'value="combined"'):
            assert field in form, f'فیلد {field} از فرم حذف شده'
        assert 'input.disabled = !on' in form, \
            'فیلد پنهان بدون disabled ارسال می‌شود و مقدار فیلد هم‌نام را پاک می‌کند'

    def test_route_reads_combined_parts(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(root, 'routes', 'finance.py'), encoding='utf-8') as handle:
            source = handle.read()
        assert 'cash_amount=cash_part' in source and 'abs(parts_total - amount) > 1' in source


class TestJalaliWindows:
    """B7 — پنجره «ماه جاری» باید شمسی باشد."""

    def test_current_period_matches_jalali_calendar(self):
        from utils.jalali import current_jalali_period
        import pytest as _pytest
        assert current_jalali_period(date(2026, 9, 3)) == '1405/06'
        assert current_jalali_period(date(2026, 9, 22)) == '1405/06'
        assert current_jalali_period(date(2026, 9, 23)) == '1405/07', \
            '۱ مهر ۱۴۰۵ = ۲۰۲۶/۰۹/۲۳ ⇒ پنجره باید عوض شود'

    def test_month_bounds_cover_whole_jalali_month(self):
        from utils.jalali import jalali_month_bounds, jalali_period_bounds
        start, end = jalali_period_bounds('1405/06')
        assert (start - date(2026, 8, 23)).days == 0
        assert (end - date(2026, 9, 22)).days == 0
        # اولین روز ماه همیشه داخل پنجره است — همان چیزی که قبلاً خارج بود
        bounds = jalali_month_bounds(date(2026, 9, 3))
        assert bounds[0] <= date(2026, 8, 23) <= bounds[1]

    def test_months_back_labels_are_jalali_and_contiguous(self):
        from utils.jalali import jalali_months_back
        rows = jalali_months_back(12)
        assert len(rows) == 12
        labels = [row[0] for row in rows]
        assert labels == sorted(labels), 'از قدیم به جدید'
        # بدون هم‌پوشانی و بدون روز جاافتاده
        for (_, _, prev_end), (label, start, _end) in zip(rows, rows[1:]):
            assert (start - prev_end).days == 1, f'شکاف/هم‌پوشانی قبل از {label}'

    def test_no_gregorian_month_windows_left_in_routes(self):
        """رجرسون: هر جا «ماه جاری» لازم است باید از ياردهای شمسی استفاده شود."""
        root = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'routes')
        offenders = []
        for name in sorted(os.listdir(root)):
            if not name.endswith('.py'):
                continue
            with open(os.path.join(root, name), encoding='utf-8') as handle:
                source = handle.read()
            for line in source.splitlines():
                if 'replace(day=1)' in line and not line.strip().startswith('#'):
                    offenders.append((name, line.strip()[:70]))
        assert not offenders, f'پنجره میلادی باقی مانده: {offenders}'

    INCOME_RE = re.compile(
        r'درآمد ماه</div>\s*<div class="stat-value"[^>]*>\s*([0-9\u06F0-\u06F9,]+)')

    def _month_income(self, client):
        """عدد کارت «درآمد ماه»؛ رقم‌های فارسی و جداکننده هزارگان نرمال می‌شوند."""
        html = client.get('/finance/dashboard').get_data(as_text=True)
        match = self.INCOME_RE.search(html)
        assert match, 'کارت «درآمد ماه» در داشبورد مالی رندر نشد'
        text = ''.join(
            str(int(ch)) if '\u06F0' <= ch <= '\u06F9' else ch for ch in match.group(1))
        return int(text.replace(',', '').replace('\u066B', '') or 0)

    def test_finance_dashboard_counts_first_day_of_jalali_month(self, client, test_app, tuition):
        """اختلافِ عدد داشبورد، نه مبلغ مطلق — دیتابیس توسعه داده واقعی دارد."""
        from utils.jalali import jalali_month_bounds
        start, _end = jalali_month_bounds()
        before_total = self._month_income(client)
        with test_app.app_context():
            payment = Payment(
                receipt_no='PAY-FINTEST-B1', student_id=tuition['student'],
                registration_id=tuition['registration'], amount=7_000_000,
                payment_method='cash', payment_date=start, status='confirmed',
                description='پرداخت آزمونی اول ماه')
            db.session.add(payment)
            db.session.commit()
            payment_id = payment.id
        try:
            assert self._month_income(client) - before_total == 7_000_000, \
                'پرداخت اول ماه شمسی در داشبورد مالی حساب نمی‌شود'
        finally:
            with test_app.app_context():
                row = db.session.get(Payment, payment_id)
                if row:
                    db.session.delete(row)
                    db.session.commit()


class TestPaymentHelpers:
    def test_cash_portion_of_combined_payment(self):
        from utils.payments import cash_portion

        class _P:
            def __init__(self, method, amount=0, cash_amount=0):
                self.payment_method, self.amount, self.cash_amount = method, amount, cash_amount

        assert cash_portion(_P('cash', 500)) == 500
        assert cash_portion(_P('combined', 900, 300)) == 300
        assert cash_portion(_P('card', 700)) == 0
        assert cash_portion(None) == 0

    def test_receipt_numbers_are_unique_and_prefixed(self, test_app):
        from utils.payments import build_receipt_no
        with test_app.app_context():
            first, second = build_receipt_no(), build_receipt_no()
        assert first != second
        assert first.startswith('PAY-')

    def test_installment_remaining_tolerates_nulls(self, test_app):
        """ستون‌های nullable نباید صفحه اقساط را ۵۰۰ کنند."""
        with test_app.app_context():
            row = Installment(amount=1_000, late_fee=None, paid_amount=None)
            assert row.remaining == 1_000
