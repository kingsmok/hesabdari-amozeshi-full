"""مدل‌های انطباق مالیاتی

پوشش‌دهنده:
- تنظیمات سامانه مودیان و ارزش افزوده
- طرف‌حساب‌های مالیاتی (مشتری/تامین‌کننده) با شناسه معتبر
- صورتحساب الکترونیکی و ردیف‌های آن
- لاگ ارسال به سامانه مودیان
- کالا/خدمت با شناسه ۱۳ رقمی و پرچم معافیت
- مالیات تکلیفی (اجاره و حق‌الزحمه ماده ۸۶)
- پله‌های مالیات حقوق
- دارایی ثابت و استهلاک (ماده ۱۴۹)
"""
from datetime import datetime, date

from extensions import db


class TaxSettings(db.Model):
    """تنظیمات مالیاتی و اتصال به سامانه مودیان (یک رکورد)."""
    __tablename__ = 'tax_settings'

    id = db.Column(db.Integer, primary_key=True)

    # ── هویت مودی (فروشنده)
    seller_name = db.Column(db.String(200))
    seller_type = db.Column(db.String(20), default='legal')  # legal | real
    seller_tin = db.Column(db.String(20))          # شناسه ملی / کد ملی فروشنده
    economic_code = db.Column(db.String(20))       # کد اقتصادی
    registration_number = db.Column(db.String(30))  # شماره ثبت
    postal_code = db.Column(db.String(12))
    branch_code = db.Column(db.String(10))
    address = db.Column(db.Text)

    # ── سامانه مودیان
    moadian_enabled = db.Column(db.Boolean, default=False)
    memory_id = db.Column(db.String(6))            # شناسه یکتای حافظه مالیاتی
    client_id = db.Column(db.String(100))          # معمولاً همان شناسه حافظه
    api_base_url = db.Column(db.String(200), default='https://tp.tax.gov.ir/requestsmanager/api/v2')
    private_key_path = db.Column(db.String(300))   # کلید خصوصی امضا (PEM)
    certificate_path = db.Column(db.String(300))   # گواهی امضا (PEM/CER)
    auto_send = db.Column(db.Boolean, default=False)  # ارسال خودکار پس از صدور
    sandbox_mode = db.Column(db.Boolean, default=True)  # حالت آزمایشی: بدون تماس واقعی
    last_serial = db.Column(db.Integer, default=0)    # آخرین سریال داخلی حافظه

    # ── ارزش افزوده
    vat_rate = db.Column(db.Float, default=10.0)      # درصد ارزش افزوده جاری
    education_exempt = db.Column(db.Boolean, default=True)  # معافیت خدمات آموزشی
    default_stuff_id = db.Column(db.String(13))       # شناسه عمومی کالا/خدمت

    # ── مالیات حقوق
    salary_year = db.Column(db.String(10), default='1405')
    salary_monthly_exemption = db.Column(db.Float, default=0)  # سقف معافیت ماهانه
    employer_tax_file_code = db.Column(db.String(30))  # کد کارگاه/پرونده مالیاتی

    # ── مالیات تکلیفی
    rent_withholding_rate = db.Column(db.Float, default=10.0)   # مالیات اجاره
    fee_withholding_rate = db.Column(db.Float, default=10.0)    # حق‌الزحمه ماده ۸۶

    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @staticmethod
    def get():
        """تنظیمات جاری را می‌خواند و در صورت نبود می‌سازد."""
        settings = TaxSettings.query.first()
        if settings is None:
            settings = TaxSettings()
            db.session.add(settings)
            db.session.commit()
        return settings


class TaxParty(db.Model):
    """طرف حساب مالیاتی — مشتری یا تامین‌کننده (برای صورتحساب و ماده ۱۶۹)."""
    __tablename__ = 'tax_parties'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    party_role = db.Column(db.String(20), default='customer')  # customer | supplier | both
    party_type = db.Column(db.String(20), default='real')      # real | legal | foreigner | consumer
    national_id = db.Column(db.String(20), index=True)         # کد ملی / شناسه ملی / کد فراگیر
    economic_code = db.Column(db.String(20))
    registration_number = db.Column(db.String(30))
    postal_code = db.Column(db.String(12))
    phone = db.Column(db.String(20))
    province = db.Column(db.String(50))
    city = db.Column(db.String(50))
    address = db.Column(db.Text)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'))
    is_verified = db.Column(db.Boolean, default=False)   # نتیجه اعتبارسنجی الگوریتمی
    verify_message = db.Column(db.String(200))
    is_active = db.Column(db.Boolean, default=True)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    student = db.relationship('Student', backref='tax_parties')

    @property
    def type_label(self):
        return {
            'real': 'شخص حقیقی',
            'legal': 'شخص حقوقی',
            'foreigner': 'اتباع خارجی',
            'consumer': 'مصرف‌کننده نهایی',
        }.get(self.party_type, self.party_type)


class TaxServiceItem(db.Model):
    """کالا/خدمت قابل درج در صورتحساب با شناسه ۱۳ رقمی سازمان."""
    __tablename__ = 'tax_service_items'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    stuff_id = db.Column(db.String(13))            # شناسه کالا/خدمت (stuffid.tax.gov.ir)
    unit = db.Column(db.String(30), default='عدد')
    unit_price = db.Column(db.Float, default=0)
    is_service = db.Column(db.Boolean, default=True)
    vat_exempt = db.Column(db.Boolean, default=False)   # معاف از ارزش افزوده
    vat_rate = db.Column(db.Float)                      # نرخ اختصاصی؛ خالی = نرخ عمومی
    exempt_reason = db.Column(db.String(200))
    course_id = db.Column(db.Integer, db.ForeignKey('courses.id'))
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    course = db.relationship('Course', backref='tax_items')

    def effective_vat_rate(self, default_rate: float) -> float:
        if self.vat_exempt:
            return 0.0
        if self.vat_rate is not None:
            return float(self.vat_rate)
        return float(default_rate or 0)


class TaxInvoice(db.Model):
    """صورتحساب الکترونیکی (فروش یا خرید)."""
    __tablename__ = 'tax_invoices'

    id = db.Column(db.Integer, primary_key=True)
    invoice_number = db.Column(db.String(30), unique=True, nullable=False, index=True)
    direction = db.Column(db.String(10), default='sale')   # sale | purchase
    invoice_date = db.Column(db.Date, default=date.today, index=True)

    # الگو و نوع طبق دستورالعمل سامانه مودیان
    pattern = db.Column(db.String(2), default='1')   # ins: 1 فروش ... 7 صادرات
    invoice_type = db.Column(db.String(2), default='1')   # inty: 1/2/3
    subject = db.Column(db.String(2), default='1')        # inp: اصلی/اصلاحی/ابطالی/برگشتی

    # شماره منحصر به فرد مالیاتی
    tax_number = db.Column(db.String(22), unique=True, index=True)
    internal_serial = db.Column(db.Integer)
    memory_id = db.Column(db.String(6))

    party_id = db.Column(db.Integer, db.ForeignKey('tax_parties.id'))
    party_name_snapshot = db.Column(db.String(200))

    # مبالغ
    total_before_discount = db.Column(db.Float, default=0)
    total_discount = db.Column(db.Float, default=0)
    total_taxable = db.Column(db.Float, default=0)
    total_exempt = db.Column(db.Float, default=0)
    total_vat = db.Column(db.Float, default=0)
    other_taxes = db.Column(db.Float, default=0)
    total_amount = db.Column(db.Float, default=0)

    currency = db.Column(db.String(10), default='IRR')
    exchange_rate = db.Column(db.Float, default=1)

    # وضعیت ارسال
    status = db.Column(db.String(20), default='draft')
    # draft | issued | sending | sent | confirmed | rejected | cancelled
    moadian_uid = db.Column(db.String(100))
    moadian_reference = db.Column(db.String(100))
    moadian_status = db.Column(db.String(50))
    moadian_message = db.Column(db.Text)
    sent_at = db.Column(db.DateTime)
    confirmed_at = db.Column(db.DateTime)

    # ارجاعات داخلی
    payment_id = db.Column(db.Integer, db.ForeignKey('payments.id'))
    registration_id = db.Column(db.Integer, db.ForeignKey('registrations.id'))
    expense_id = db.Column(db.Integer, db.ForeignKey('expenses.id'))
    journal_entry_id = db.Column(db.Integer, db.ForeignKey('journal_entries.id'))

    correction_of_id = db.Column(db.Integer, db.ForeignKey('tax_invoices.id'))
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))

    party = db.relationship('TaxParty', backref='invoices')
    items = db.relationship('TaxInvoiceItem', backref='invoice',
                            lazy='dynamic', cascade='all, delete-orphan')
    logs = db.relationship('MoadianLog', backref='invoice',
                           lazy='dynamic', cascade='all, delete-orphan')
    correction_of = db.relationship('TaxInvoice', remote_side=[id])

    STATUS_LABELS = {
        'draft': 'پیش‌نویس',
        'issued': 'صادر شده',
        'sending': 'در حال ارسال',
        'sent': 'ارسال شده',
        'confirmed': 'تایید سامانه',
        'rejected': 'رد شده',
        'cancelled': 'ابطال شده',
    }

    @property
    def status_label(self):
        return self.STATUS_LABELS.get(self.status, self.status)

    def recalculate(self, default_vat_rate: float = 0.0):
        """جمع‌های صورتحساب را از روی ردیف‌ها بازمحاسبه می‌کند."""
        before = discount = taxable = exempt = vat = other = 0.0
        for item in self.items.all():
            item.recalculate(default_vat_rate)
            before += item.gross_amount
            discount += item.discount or 0
            if item.vat_exempt:
                exempt += item.net_amount
            else:
                taxable += item.net_amount
            vat += item.vat_amount or 0
            other += item.other_tax or 0
        self.total_before_discount = round(before, 2)
        self.total_discount = round(discount, 2)
        self.total_taxable = round(taxable, 2)
        self.total_exempt = round(exempt, 2)
        self.total_vat = round(vat, 2)
        self.other_taxes = round(other, 2)
        self.total_amount = round(taxable + exempt + vat + other, 2)
        return self.total_amount


class TaxInvoiceItem(db.Model):
    """ردیف صورتحساب الکترونیکی."""
    __tablename__ = 'tax_invoice_items'

    id = db.Column(db.Integer, primary_key=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey('tax_invoices.id'), nullable=False)
    service_item_id = db.Column(db.Integer, db.ForeignKey('tax_service_items.id'))

    row_number = db.Column(db.Integer, default=1)
    title = db.Column(db.String(200), nullable=False)
    stuff_id = db.Column(db.String(13))
    unit = db.Column(db.String(30), default='عدد')
    quantity = db.Column(db.Float, default=1)
    unit_price = db.Column(db.Float, default=0)
    discount = db.Column(db.Float, default=0)

    vat_exempt = db.Column(db.Boolean, default=False)
    vat_rate = db.Column(db.Float, default=0)
    vat_amount = db.Column(db.Float, default=0)
    other_tax = db.Column(db.Float, default=0)

    gross_amount = db.Column(db.Float, default=0)   # مبلغ قبل از تخفیف
    net_amount = db.Column(db.Float, default=0)     # پس از تخفیف، بدون ارزش افزوده
    total_amount = db.Column(db.Float, default=0)   # با ارزش افزوده

    service_item = db.relationship('TaxServiceItem', backref='invoice_items')

    def recalculate(self, default_vat_rate: float = 0.0):
        quantity = float(self.quantity or 0)
        price = float(self.unit_price or 0)
        self.gross_amount = round(quantity * price, 2)
        self.net_amount = round(max(self.gross_amount - float(self.discount or 0), 0), 2)
        if self.vat_exempt:
            self.vat_rate = 0
            self.vat_amount = 0
        else:
            rate = self.vat_rate if self.vat_rate not in (None, 0) else default_vat_rate
            self.vat_rate = float(rate or 0)
            self.vat_amount = round(self.net_amount * self.vat_rate / 100.0, 2)
        self.total_amount = round(self.net_amount + (self.vat_amount or 0) + (self.other_tax or 0), 2)
        return self.total_amount


class MoadianLog(db.Model):
    """لاگ تعامل با سامانه مودیان — برای رهگیری و رفع خطا."""
    __tablename__ = 'moadian_logs'

    id = db.Column(db.Integer, primary_key=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey('tax_invoices.id'))
    action = db.Column(db.String(40))   # send | inquiry | token | server-info
    success = db.Column(db.Boolean, default=False)
    http_status = db.Column(db.Integer)
    request_trace_id = db.Column(db.String(60))
    message = db.Column(db.Text)
    payload_preview = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))


class SalaryTaxBracket(db.Model):
    """پله‌های مالیات حقوق سالانه (قابل تعریف برای هر سال)."""
    __tablename__ = 'salary_tax_brackets'

    id = db.Column(db.Integer, primary_key=True)
    year = db.Column(db.String(10), nullable=False, index=True)
    title = db.Column(db.String(50))
    from_amount = db.Column(db.Float, default=0)     # ماهانه
    to_amount = db.Column(db.Float)                  # خالی = بی‌نهایت
    rate = db.Column(db.Float, default=0)            # درصد
    order_index = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class WithholdingTax(db.Model):
    """مالیات تکلیفی — اجاره و حق‌الزحمه (ماده ۸۶)."""
    __tablename__ = 'withholding_taxes'

    id = db.Column(db.Integer, primary_key=True)
    doc_number = db.Column(db.String(30), unique=True)
    tax_type = db.Column(db.String(20), default='rent')  # rent | fee_86 | contract | other
    period = db.Column(db.String(10))                    # 1405/01
    payee_name = db.Column(db.String(200), nullable=False)
    payee_national_id = db.Column(db.String(20))
    payee_type = db.Column(db.String(20), default='real')
    gross_amount = db.Column(db.Float, default=0)
    rate = db.Column(db.Float, default=10)
    tax_amount = db.Column(db.Float, default=0)
    net_amount = db.Column(db.Float, default=0)
    doc_date = db.Column(db.Date, default=date.today)
    is_paid = db.Column(db.Boolean, default=False)       # واریز به حساب سازمان
    paid_date = db.Column(db.Date)
    payment_reference = db.Column(db.String(60))
    teacher_id = db.Column(db.Integer, db.ForeignKey('teachers.id'))
    expense_id = db.Column(db.Integer, db.ForeignKey('expenses.id'))
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))

    teacher = db.relationship('Teacher', backref='withholding_taxes')

    TYPE_LABELS = {
        'rent': 'مالیات اجاره',
        'fee_86': 'حق‌الزحمه (ماده ۸۶)',
        'contract': 'قرارداد پیمانکاری',
        'other': 'سایر',
    }

    @property
    def type_label(self):
        return self.TYPE_LABELS.get(self.tax_type, self.tax_type)

    def recalculate(self):
        self.tax_amount = round(float(self.gross_amount or 0) * float(self.rate or 0) / 100.0)
        self.net_amount = round(float(self.gross_amount or 0) - self.tax_amount)
        return self.tax_amount


class FixedAsset(db.Model):
    """دارایی ثابت و استهلاک بر اساس جدول ماده ۱۴۹."""
    __tablename__ = 'fixed_assets'

    id = db.Column(db.Integer, primary_key=True)
    asset_code = db.Column(db.String(30), unique=True)
    name = db.Column(db.String(200), nullable=False)
    category = db.Column(db.String(100))          # گروه دارایی (ماده ۱۴۹)
    acquisition_date = db.Column(db.Date, default=date.today)
    cost = db.Column(db.Float, default=0)         # بهای تمام شده
    salvage_value = db.Column(db.Float, default=0)  # ارزش اسقاط
    method = db.Column(db.String(20), default='straight')  # straight | declining
    useful_life_years = db.Column(db.Float, default=5)     # برای خط مستقیم
    declining_rate = db.Column(db.Float, default=25)       # درصد نزولی
    accumulated_depreciation = db.Column(db.Float, default=0)
    is_disposed = db.Column(db.Boolean, default=False)
    disposal_date = db.Column(db.Date)
    location = db.Column(db.String(150))
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    depreciations = db.relationship('DepreciationRecord', backref='asset',
                                    lazy='dynamic', cascade='all, delete-orphan')

    @property
    def method_label(self):
        return 'خط مستقیم' if self.method == 'straight' else 'نزولی'

    @property
    def book_value(self):
        return round(float(self.cost or 0) - float(self.accumulated_depreciation or 0), 2)


class DepreciationRecord(db.Model):
    """رکورد استهلاک سالانه یک دارایی."""
    __tablename__ = 'depreciation_records'

    id = db.Column(db.Integer, primary_key=True)
    asset_id = db.Column(db.Integer, db.ForeignKey('fixed_assets.id'), nullable=False)
    year = db.Column(db.String(10), nullable=False)
    period_index = db.Column(db.Integer, default=1)
    opening_value = db.Column(db.Float, default=0)
    depreciation = db.Column(db.Float, default=0)
    accumulated = db.Column(db.Float, default=0)
    closing_value = db.Column(db.Float, default=0)
    journal_entry_id = db.Column(db.Integer, db.ForeignKey('journal_entries.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
