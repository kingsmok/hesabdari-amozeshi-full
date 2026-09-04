"""
کدینگ حساب‌های پیش‌فرض آموزشگاه
════════════════════════════════════════════════════════════
نصب تازه جدول `accounts` را خالی داشت، در حالی که تراز آزمایشی، سود و زیان و
سند زدن به آن وابسته‌اند؛ کاربر بدون حساب، عملاً هیچ گزارشی نمی‌دید.

این تابع در صورت خالی بودن کدینگ، یک ساختار استاندارد (گروه/کل) می‌سازد.
ایدمپوتنت است: حساب موجود را تغییر نمی‌دهد و فقط کدهای غایب را اضافه می‌کند.
"""
from __future__ import annotations

# (کد گروه, نام گروه, نوع, [(کد حساب, نام حساب, نوع, ماهیت)])
DEFAULT_CHART: list[tuple[str, str, str, list[tuple[str, str, str, str]]]] = [
    ('10', 'دارایی‌ها', 'asset', [
        ('1010', 'صندوق', 'asset', 'debit'),
        ('1020', 'بانک', 'asset', 'debit'),
        ('1030', 'حقوق دریافتنی دانش‌آموزان', 'asset', 'debit'),
        ('1040', 'چک‌های دریافتنی', 'asset', 'debit'),
        ('1050', 'موجودی ابزار و ملزومات', 'asset', 'debit'),
        ('1060', 'پیش‌پرداخت‌ها', 'asset', 'debit'),
    ]),
    ('20', 'بدهی‌ها', 'liability', [
        ('2010', 'حقوق پرداختنی مدرسین و کارکنان', 'liability', 'credit'),
        ('2020', 'چک‌های پرداختنی', 'liability', 'credit'),
        ('2030', 'وام', 'liability', 'credit'),
        ('2040', 'پیش‌دریافت شهریه', 'liability', 'credit'),
        ('2050', 'عقب‌مانده بیمه و مالیات', 'liability', 'credit'),
    ]),
    ('30', 'حقوق صاحبان سهام', 'equity', [
        ('3010', 'سرمایه اولیه', 'equity', 'credit'),
        ('3020', 'اندوخته', 'equity', 'credit'),
        ('3030', 'سود انباشته', 'equity', 'credit'),
    ]),
    ('40', 'درآمدها', 'revenue', [
        ('4010', 'درآمد شهریه', 'revenue', 'credit'),
        ('4020', 'درآمد دوره‌های آزاد', 'revenue', 'credit'),
        ('4030', 'درآمد ثبت‌نام و خدمات جانبی', 'revenue', 'credit'),
        ('4040', 'سایر درآمدها', 'revenue', 'credit'),
    ]),
    ('50', 'هزینه‌ها', 'expense', [
        ('5010', 'حقوق و دستمزد', 'expense', 'debit'),
        ('5020', 'اجاره', 'expense', 'debit'),
        ('5030', 'بیمه و مالیات حقوق', 'expense', 'debit'),
        ('5040', 'ملزومات و چاپ', 'expense', 'debit'),
        ('5050', 'آب، برق، اینترنت و تلفن', 'expense', 'debit'),
        ('5060', 'بازاریابی و تبلیغات', 'expense', 'debit'),
        ('5070', 'استهلاک', 'expense', 'debit'),
        ('5080', 'سایر هزینه‌ها', 'expense', 'debit'),
    ]),
]


def seed_default_chart(commit: bool = True) -> dict:
    """ساخت گروه‌ها و حساب‌های غایب. خروجی: {'groups': n, 'accounts': m}."""
    from extensions import db
    from models.accounting import Account, AccountGroup

    created_groups = created_accounts = 0
    existing_group_codes = {code for (code,) in db.session.query(AccountGroup.code).all()}
    existing_account_codes = {code for (code,) in db.session.query(Account.code).all()}

    for group_code, group_name, group_type, accounts in DEFAULT_CHART:
        group = None
        if group_code not in existing_group_codes:
            group = AccountGroup(code=group_code, name=group_name, account_type=group_type)
            db.session.add(group)
            db.session.flush()
            created_groups += 1
            existing_group_codes.add(group_code)
        if group is None:
            group = AccountGroup.query.filter_by(code=group_code).first()

        for code, name, acc_type, nature in accounts:
            if code in existing_account_codes:
                continue
            db.session.add(Account(code=code, name=name, group_id=group.id,
                                   account_type=acc_type, nature=nature, is_active=True))
            created_accounts += 1
            existing_account_codes.add(code)

    if commit and (created_groups or created_accounts):
        db.session.commit()
    return {'groups': created_groups, 'accounts': created_accounts}


def chart_is_empty() -> bool:
    from extensions import db
    from models.accounting import Account
    return db.session.query(Account.id).first() is None
