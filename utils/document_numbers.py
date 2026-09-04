"""
شماره‌گذار مطمئن اسناد
════════════════════════════════════════════════════════════

باگ زمینه‌ای: در ۱۶ نقطه از برنامه شماره سند با `f'PRE-{last.id + 1:06d}'` ساخته می‌شد.
این الگو با (الف) دو کاربر همزمان، (ب) حذف فیزیکی آخرین رکورد، (ج) Restore از بکاپ قدیمی
شماره تکراری می‌سازد و چون ستون unique است، صفحه ۵۰۰ می‌شود.

اینجا شماره از یک شمارنده پایدار (`DocumentSequence`) گرفته می‌شود و در صورت تعارض
چند بار retry می‌شود. اگر هنوز جدول شمارنده در دیتابیس ساخته نشده باشد (نصب قدیمی که
migrate نشده) به‌امن‌ترین حالت قبلی برمی‌گردد: بیشترین شماره عددی موجود + یک.
"""
from __future__ import annotations

import re

from sqlalchemy.exc import IntegrityError, OperationalError, ProgrammingError

from extensions import db
from utils.jalali import current_jalali_year

#: پیشوند نمایشی هر نوع سند
PREFIXES = {
    'payslip': 'PS',
    'complaint': 'CMP',
    'ticket': 'TKT',
    'exam': 'EXM',
    'course': 'CRS',
    'class_split': 'SPL',
    'expense': 'EXP',
    'payment': 'PAY',
    'voucher': 'SND',
    'student': 'ST',
    'teacher': 'TEC',   # با داده موجود (`TEC-1405-001`) هم‌قالب بماند
    'class': 'CLS',
    'registration': 'REG',
    'installment': 'INS',
    'check': 'CHK',
    'advance': 'ADV',
    'contract': 'CTR',
}

_TRAILING_DIGITS = re.compile(r'(\d+)\s*$')


def _highest_existing_number(kind: str) -> int:
    """بیشترین شماره عددیِ موجود برای همان نوع سند (برای هم‌گام‌سازی اولیه شمارنده)."""
    pair = _LEGACY_SOURCES.get(kind)
    if not pair:
        return 0
    model, column = pair
    highest = 0
    try:
        for (value,) in db.session.query(column).all():
            match = _TRAILING_DIGITS.search(str(value or ''))
            if match:
                highest = max(highest, int(match.group(1)))
    except Exception:
        return 0
    return highest


def next_sequence_number(kind: str, *, with_year: bool = True) -> int:
    """فقط «عدد بعدی» از شمارنده پایدار.

    برای قالب‌های سفارشی که پیشوندشان ثابت نیست — مثل کلاس که
    `PR-1405-03` (دو حرف اول کد دوره) می‌شود — تا آن‌ها هم number را از
    `MAX(id)+1` نگیرند.
    """
    key_year = current_jalali_year() if with_year else '-'

    if _sequence_table_ready():
        from models.system import DocumentSequence
        for _attempt in range(6):
            seq = DocumentSequence.query.filter_by(kind=kind, year=key_year).first()
            if seq is None:
                seq = DocumentSequence(kind=kind, year=key_year,
                                       next_no=_highest_existing_number(kind) + 1)
                db.session.add(seq)
                try:
                    db.session.flush()
                except IntegrityError:
                    db.session.rollback()
                    continue
            number = seq.next_no
            seq.next_no = number + 1
            try:
                db.session.flush()
            except (IntegrityError, OperationalError, ProgrammingError):
                db.session.rollback()
                continue
            return number

    # مسیر جایگزین (بدون جدول شمارنده)
    return _highest_existing_number(kind) + 1


def next_document_number(kind: str, *, with_year: bool = True, width: int = 5) -> str:
    """شماره بعدی سند؛ قالب `PS-1405-00042` یا (بدون سال) `PS-00042`."""
    prefix = PREFIXES.get(kind, kind.upper())
    year = current_jalali_year() if with_year else None
    number = next_sequence_number(kind, with_year=with_year)
    return _format(prefix, year, number, width)


_TABLE_READY_CACHE: dict[str, bool] = {}


def _sequence_table_ready() -> bool:
    """جدول شمارنده موجود است؟ (یک‌بار بررسی و کش می‌شود.)"""
    try:
        bind = db.session.get_bind()
        if bind is None:
            return False
        key = str(bind.url.database)
        cached = _TABLE_READY_CACHE.get(key)
        if cached is not None:
            return cached
        from sqlalchemy import inspect as sqlalchemy_inspect
        ready = bool(sqlalchemy_inspect(bind).has_table('document_sequences'))
        _TABLE_READY_CACHE[key] = ready
        return ready
    except Exception:
        return False


def _format(prefix: str, year, number: int, width: int) -> str:
    parts = [prefix]
    if year:
        parts.append(str(year))
    parts.append(f'{int(number):0{width}d}')
    return '-'.join(parts)


def _legacy_sources():
    """map kind → (model, column). import تنبل تا چرخه import ایجاد نشود."""
    from models.finance import Payslip, Expense, Payment
    from models.accounting import JournalEntry
    from models.student import Student
    from models.teacher import Teacher
    from models.classes import ClassGroup
    from models.registration import Registration
    from models.course import Course
    from models.exam import Exam
    from models.system import Complaint, Ticket
    return {
        'payslip': (Payslip, Payslip.payslip_number),
        'expense': (Expense, Expense.expense_number),
        'payment': (Payment, Payment.receipt_no),
        'voucher': (JournalEntry, JournalEntry.entry_number),
        'student': (Student, Student.student_code),
        'teacher': (Teacher, Teacher.teacher_code),
        'class': (ClassGroup, ClassGroup.class_code),
        'registration': (Registration, Registration.reg_code),
        'exam': (Exam, Exam.exam_code),
        'course': (Course, Course.code),
        'complaint': (Complaint, Complaint.complaint_number),
        'ticket': (Ticket, Ticket.ticket_number),
        'class_split': (ClassGroup, ClassGroup.class_code),
    }


class _LazySources(dict):
    def __init__(self, loader):
        super().__init__()
        self._loader = loader
        self._loaded = False

    def _ensure(self):
        if not self._loaded:
            self.update(self._loader())
            self._loaded = True

    def get(self, key, default=None):
        self._ensure()
        return super().get(key, default)


_LEGACY_SOURCES = _LazySources(_legacy_sources)
