"""
عملیات مشترک پرداخت و صندوق
════════════════════════════════════════════════════════════════
چرا این فایل هست؟ ثبت/ابطالِ پرداخت در چند مسیر تکرار شده بود
(`routes/finance.py::add_payment`، `routes/new_features.py::pay_installment`،
ثبت پرداخت اولیه در `routes/registration.py`) و هر کدام یک‌سره فرق داشت:

• یکی `PAY-{last.id+1:06d}` می‌ساخت (با دو درخواست هم‌زمان، شماره تکراری و
  IntegrityError)، دیگری از `next_document_number` استفاده می‌کرد؛
• «بخش نقدی» پرداخت ترکیبی (`combined`) هیچ‌وقت به صندوق اضافه نمی‌شد؛
• `cashbox_id` روی پرداخت ثبت نمی‌شد، پس بعداً معلوم نبود پول کدام صندوق رفته
  و ابطال/مرجوعی قابل محاسبه نبود؛
• هیچ مسیری برای ابطال پرداخت وجود نداشت، درحالی‌که مدل `status='cancelled'`،
  `cancelled_by` و `cancelled_at` را داشت ⇒ اصلاح اشتباه = ویرایش دستی دیتابیس.

اینجا همان قواعد، یک‌جا و آزموده‌شده: ثبت‌شده‌ها منبع تاریخ/شماره‌اند و
`apply_payment_to_targets` فقط یک «گام» (delta) اعمال می‌کند — نه بازمحاسبه از
صفر — تا دستی‌کاری‌های مجازِ حسابدار در `paid_amount` پاک نشود.
"""
from __future__ import annotations

from datetime import datetime

from extensions import db
from models.finance import Cashbox, CashboxTransaction, get_or_create_main_cashbox

#: مبلغ‌های کوچک‌تر از این، «صفر» حساب می‌شوند (آشغال float تومانی)
_EPS = 1.0

CASH_METHODS = {'cash'}
COMBINED_METHOD = 'combined'


def cash_portion(payment) -> float:
    """سهم نقدی پرداخت — همان‌قدر که به صندوق وارد/از آن خارج می‌شود.

    پرداخت «نقد» کامل، پرداخت «ترکیبی» فقط به اندازه `cash_amount`.
    """
    if payment is None:
        return 0.0
    if payment.payment_method == COMBINED_METHOD:
        return float(payment.cash_amount or 0)
    if payment.payment_method in CASH_METHODS:
        return float(payment.amount or 0)
    return 0.0


def settle_cashbox(payment, amount, note, user_id=None, direction='in', box=None):
    """یک تراکنش صندوق + تغییر موجودی.

    Returns:
        (ok: bool, message: str) — اگر `ok` False باشد هیچ چیزی تغییر نکرده
        (موجودی صندوق برای مرجوعی کافی نیست؛ همان قاعده فیش حقوقی).
    """
    amount = float(amount or 0)
    if amount <= _EPS:
        return True, ''      # سهم نقدی ندارد ⇒ کاری لازم نیست

    if box is None:
        box = (db.session.get(Cashbox, payment.cashbox_id)
               if payment is not None and payment.cashbox_id else None)
    if box is None:
        box = get_or_create_main_cashbox()
    if box is None:                                                   # pragma: no cover
        return False, 'صندوقی برای ثبت وجود ندارد'

    balance = float(box.balance or 0)
    if direction == 'out':
        if balance + _EPS < amount:
            return False, (f'موجودی «{box.name}» ({balance:,.0f}) برای مرجوعی '
                           f'{amount:,.0f} کافی نیست')
        box.balance = balance - amount
        trans_type = 'out'
    else:
        box.balance = balance + amount
        trans_type = 'in'

    db.session.add(CashboxTransaction(
        cashbox_id=box.id,
        trans_type=trans_type,
        amount=amount,
        description=note,
        reference_type='payment',
        reference_id=payment.id if payment is not None else None,
        balance_after=box.balance,
        created_by=user_id,
        transaction_date=datetime.utcnow(),
    ))
    if payment is not None and payment.cashbox_id is None and direction == 'in':
        # ثبت می‌کنیم پول کدام صندوق رفته تا ابطال/مرجوعی بعداً قابل محاسبه باشد
        payment.cashbox_id = box.id
    return True, ''


def apply_payment_to_targets(payment, sign=1, date_hint=None):
    """اعمال یک پرداخت روی ثبت‌نام و قسط (با گام، نه بازمحاسبه از صفر).

    `sign=+1` برای ثبت/بازگردانی، `sign=-1` برای ابطال.
    وضعیت قسط از روی `Installment.remaining` (شامل `late_fee`) تعیین می‌شود،
    پس «پرداخت ناقص» و «جریمه دیرکرد» هم درست لحاظ می‌شوند.
    """
    registration = payment.registration
    if registration is None and payment.installment_id and payment.installment:
        registration = payment.installment.registration

    amount = float(payment.amount or 0)
    if registration is not None and amount:
        registration.paid_amount = max(0.0, float(registration.paid_amount or 0) + sign * amount)
        total_fee = float(registration.total_fee or 0)
        registration.remaining_amount = max(0.0, total_fee - registration.paid_amount)

    installment = payment.installment
    if installment is not None and amount:
        installment.paid_amount = max(0.0, float(installment.paid_amount or 0) + sign * amount)
        if float(installment.remaining or 0) <= _EPS:
            installment.status = 'paid'
            if sign > 0:
                installment.paid_date = date_hint or installment.paid_date or datetime.utcnow().date()
        else:
            installment.status = 'partial' if installment.paid_amount > _EPS else 'pending'
            if sign < 0:
                installment.paid_date = None
    return registration


def build_receipt_no():
    """شماره رسید یکتا (`PAY-1405-00042`)؛ جای `PAY-{last.id+1}` (ریسک تصادم)."""
    from utils.document_numbers import next_document_number
    return next_document_number('payment')
