"""
گارد اتمیکِ تغییر وضعیت رکوردهای مالی
════════════════════════════════════════════════════════════════
مسیرهای «پرداخت/ابطال» قبل از این دو مرحله‌ای بودند:
    1) خواندن رکورد و بررسی status (مثلاً approved)
    2) تغییر status و commit

با دو کلیکِ پیاپی (یا دو درخواست هم‌زمان)، هر دو درخواست وضعیتِ «مجاز» را
می‌دیدند و دو بار پرداخت/مرجوعی انجام می‌شد — در حسابداری یعنی اختلاس/خطای
مالی جدی. این ماژول با یک `UPDATE ... WHERE status = old` اتمیک (CAS) فقط
به اولین درخواست اجازه می‌دهد؛ بقیه `rowcount = 0` می‌گیرند و رد می‌شوند.
"""
from __future__ import annotations

from flask import flash
from sqlalchemy import update

from extensions import db


def atomic_transition(model, record_id: int, from_statuses, to_status: str,
                      values: dict | None = None) -> bool | None:
    """تغییر وضعیت با مقایسه‌ی اتمیک.

    Returns:
        True  → تغییر انجام شد (رکورد جاری session با مقدار جدید همگام است)
        False → رکورد وجود دارد ولی وضعیتش با from_statuses نمی‌خواند
                (درخواست هم‌زمان/تکراری بوده؛ هیچ تغییری اعمال نشده)
        None  → رکورد پیدا نشد
    """
    if isinstance(from_statuses, str):
        from_statuses = (from_statuses,)
    values = dict(values or {})
    values['status'] = to_status

    result = db.session.execute(
        update(model)
        .where(model.id == record_id,
               model.status.in_(from_statuses))
        .values(**values)
    )
    if result.rowcount == 0:
        db.session.rollback()      # تراکنشِ بلااستفاده را بسته نگه نمی‌داریم
        row = db.session.get(model, record_id)
        return False if row is not None else None

    # رکوردِ در حال استفاده (برای اعمال بقیهٔ تغییرات مثل صندوق) را همگام می‌کنیم
    record = db.session.get(model, record_id)
    for key, value in values.items():
        if record is not None:
            setattr(record, key, value)
    return True


def flash_transition_result(result, messages: dict) -> bool:
    """پیام مناسب برای نتیجه‌ی atomic_transition؛ True یعنی باید ادامه دهیم."""
    if result is True:
        return True
    if result is False:
        flash(messages.get('conflict',
                           'این عملیات هم‌زمان توسط درخواست دیگری انجام شده و '
                           'برای جلوگیری از خطا در حسابداری رد شد.'), 'warning')
    else:
        flash(messages.get('missing', 'رکورد موردنظر یافت نشد.'), 'danger')
    return False
