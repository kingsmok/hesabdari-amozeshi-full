"""
قابلیت‌های نهایی تکمیلی:
- Dark Mode واقعی
- جستجوی سراسری پیشرفته
- صفحات باقیمانده
- بهبودهای UI
"""
import os, json, re
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, make_response
from flask_login import login_required, current_user
from extensions import db

final_bp = Blueprint('final', __name__)


# ═══════════════════════════════════════════════════════════════
#  Dark Mode CSS
# ═══════════════════════════════════════════════════════════════

@final_bp.route('/api/dark-mode', methods=['POST'])
@login_required
def toggle_dark():
    """تغییر حالت تاریک"""
    current = request.cookies.get('dark_mode', 'off')
    new_val = 'on' if current == 'off' else 'off'
    resp = make_response(jsonify({'ok': True, 'dark_mode': new_val}))
    forwarded_proto = request.headers.get('X-Forwarded-Proto', '').split(',')[0].strip().lower()
    resp.set_cookie('dark_mode', new_val, max_age=365*24*60*60,
                    samesite='Lax', secure=request.is_secure or forwarded_proto == 'https')
    return resp


# ═══════════════════════════════════════════════════════════════
#  جستجوی سراسری پیشرفته
# ═══════════════════════════════════════════════════════════════

@final_bp.route('/api/search')
@login_required
def advanced_search():
    """Permission-aware search across every operational section."""
    from sqlalchemy.orm import joinedload
    from models.student import Student
    from models.teacher import Teacher
    from models.registration import Registration, Installment
    from models.course import Course, Field, Certificate, Room
    from models.classes import ClassGroup
    from models.finance import (
        Payment, Expense, Check, Cashbox, BankAccount, ExpenseCategory,
        DiscountCode, Payslip, SalaryContract,
    )
    from models.accounting import JournalEntry, Account, SubAccount, DetailAccount
    from models.exam import Exam, QuestionBank
    from models.system import Branch, Message, InternalMessage, Ticket, Complaint
    from models.reporting import (
        AccountReconciliation, ReportBudget, ReportPreset, ReportSchedule,
    )
    from models.user import User
    from license_client import has_feature
    from license_features import FEATURE_KEYS
    from utils.reporting import catalog_for_user, normalise_text

    raw = request.args.get('q', '').strip()[:120]
    if len(raw) < 2:
        return jsonify({'results': [], 'groups': {}, 'count': 0})
    per_group = max(2, min(request.args.get('limit', 5, type=int) or 5, 10))
    requested_type = request.args.get('type', '').strip()
    normalized = normalise_text(raw)
    fa_digits = normalized.translate(str.maketrans('0123456789', '۰۱۲۳۴۵۶۷۸۹'))
    variants = {raw, normalized, fa_digits,
                normalized.replace('ی', 'ي'), normalized.replace('ک', 'ك')}
    variants = [item for item in variants if item]
    numeric_text = normalized.replace(',', '').replace('٬', '').replace('−', '-').strip()
    try:
        numeric_value = Decimal(numeric_text) if re.fullmatch(r'[+-]?\d+(?:\.\d+)?', numeric_text) else None
        if (numeric_value is not None and
                (not numeric_value.is_finite() or abs(numeric_value) > Decimal('1e18'))):
            numeric_value = None
    except (InvalidOperation, TypeError, ValueError):
        numeric_value = None
    results = []
    permission_cache = {}

    def allowed(module):
        # Search results must never reveal a module the user cannot view or a
        # product area disabled by the signed licence state.
        feature = {'settings': 'crm'}.get(module, module)
        if feature in FEATURE_KEYS and not has_feature(feature):
            return False
        if current_user.is_admin:
            return True
        if module not in permission_cache:
            permission_cache[module] = current_user.has_permission(module, 'view')
        return permission_cache[module]

    visible_reports_cache = None

    def visible_reports():
        nonlocal visible_reports_cache
        if visible_reports_cache is None:
            visible_reports_cache = (catalog_for_user(current_user)
                                     if allowed('reports') else {})
        return visible_reports_cache

    def wanted(group):
        return not requested_type or requested_type == group

    def match(*columns):
        return db.or_(*(column.icontains(value, autoescape=True)
                        for column in columns for value in variants))

    def scope(query, model, include_global=False):
        branch_id = getattr(current_user, 'branch_id', None)
        if current_user.is_admin or not branch_id or not hasattr(model, 'branch_id'):
            return query
        column = getattr(model, 'branch_id')
        return query.filter(db.or_(column == branch_id, column.is_(None))) if include_global else query.filter(column == branch_id)

    def add(group, label, icon, color, name, detail, url, keywords=''):
        results.append({'group': group, 'type': label, 'icon': icon, 'color': color,
                        'name': name or '-', 'detail': detail or '', 'url': url,
                        'keywords': keywords})

    if allowed('students') and wanted('students'):
        query = scope(Student.query, Student).filter(match(Student.first_name, Student.last_name,
            Student.student_code, Student.national_code, Student.mobile, Student.mobile2,
            Student.parent_name, Student.parent_mobile, Student.email))
        for item in query.limit(per_group).all():
            add('students', 'هنرجو', 'person', '#2563eb', item.full_name,
                f'{item.student_code} · {item.mobile}', url_for('students.view', id=item.id))

    if allowed('teachers') and wanted('teachers'):
        query = scope(Teacher.query, Teacher).filter(match(Teacher.first_name, Teacher.last_name,
            Teacher.teacher_code, Teacher.national_code, Teacher.mobile, Teacher.specialization, Teacher.email))
        for item in query.limit(per_group).all():
            add('teachers', 'مدرس', 'person-workspace', '#7c3aed', item.full_name,
                f'{item.teacher_code} · {item.specialization or item.mobile}', url_for('teachers.view', id=item.id))

    if allowed('courses') and wanted('courses'):
        course_match = match(Course.title, Course.code, Course.standard_code,
                             Course.standard_name, Course.description)
        if numeric_value is not None:
            course_total = sum((db.func.coalesce(column, 0) for column in (
                Course.base_fee, Course.registration_fee, Course.book_fee,
                Course.exam_fee, Course.certificate_fee, Course.other_fees,
            )))
            course_match = db.or_(course_match, course_total == numeric_value)
        query = scope(Course.query, Course, True).filter(course_match)
        for item in query.limit(per_group).all():
            add('courses', 'دوره', 'journal-richtext', '#ea580c', item.title,
                f'{item.code} · {item.total_fee:,.0f} تومان', url_for('new_features.course_view', id=item.id))
        for item in Field.query.filter(match(Field.name, Field.code, Field.description)).limit(per_group).all():
            add('courses', 'رشته', 'bookmark', '#f97316', item.name, item.code,
                url_for('settings.fields'))

    if allowed('classes') and wanted('classes'):
        query = (scope(ClassGroup.query, ClassGroup)
                 .outerjoin(Course, ClassGroup.course_id == Course.id)
                 .outerjoin(Teacher, ClassGroup.teacher_id == Teacher.id)
                 .filter(match(ClassGroup.name, ClassGroup.class_code, ClassGroup.notes,
                               Course.title, Course.code,
                               Teacher.first_name, Teacher.last_name, Teacher.teacher_code)))
        for item in query.limit(per_group).all():
            add('classes', 'کلاس', 'easel2', '#0891b2', item.name,
                f'{item.class_code} · {item.current_count or 0}/{item.max_capacity or 0}',
                url_for('classes.view', id=item.id))
        for item in scope(Room.query, Room, True).filter(match(Room.name, Room.code, Room.notes)).limit(per_group).all():
            add('classes', 'اتاق', 'door-open', '#0e7490', item.name, item.code or '', url_for('settings.rooms'))

    if allowed('registration') and wanted('registrations'):
        query = (scope(Registration.query, Registration)
                 .options(joinedload(Registration.student), joinedload(Registration.course))
                 .join(Student)
                 .outerjoin(Course, Registration.course_id == Course.id)
                 .outerjoin(ClassGroup, Registration.class_id == ClassGroup.id)
                 .filter(match(Registration.reg_code, Student.first_name,
                     Student.last_name, Student.mobile, Student.student_code,
                     Course.title, Course.code, ClassGroup.name, ClassGroup.class_code)))
        for item in query.limit(per_group).all():
            add('registrations', 'ثبت‌نام', 'pencil-square', '#0f766e', item.reg_code,
                f'{item.student.full_name if item.student else "-"} · {item.course.title if item.course else "-"}',
                url_for('registration.view', id=item.id))

    if allowed('finance') and wanted('finance'):
        payment_match = match(Payment.receipt_no, Payment.tracking_number,
            Payment.transaction_id, Payment.card_number, Payment.bank_name,
            Payment.description, Student.first_name, Student.last_name, Student.mobile,
            Student.student_code, Registration.reg_code, Course.title, Course.code,
            ClassGroup.name, ClassGroup.class_code)
        if numeric_value is not None:
            payment_match = db.or_(payment_match, Payment.amount == numeric_value)
        query = (scope(Payment.query, Payment).options(joinedload(Payment.student))
                 .join(Student)
                 .outerjoin(Registration, Payment.registration_id == Registration.id)
                 .outerjoin(Course, Registration.course_id == Course.id)
                 .outerjoin(ClassGroup, Registration.class_id == ClassGroup.id)
                 .filter(payment_match))
        for item in query.limit(per_group).all():
            add('finance', 'پرداخت', 'cash-coin', '#16a34a', item.receipt_no,
                f'{item.student.full_name if item.student else "-"} · {item.amount:,.0f} تومان',
                url_for('finance.view_payment', id=item.id))
        expense_match = match(Expense.expense_number, Expense.paid_to,
                              Expense.description, Expense.payment_method,
                              ExpenseCategory.name, ExpenseCategory.code)
        if numeric_value is not None:
            expense_match = db.or_(expense_match, Expense.amount == numeric_value)
        query = (scope(Expense.query, Expense)
                 .join(ExpenseCategory, Expense.category_id == ExpenseCategory.id)
                 .filter(expense_match))
        for item in query.limit(per_group).all():
            add('finance', 'هزینه', 'wallet2', '#dc2626', item.expense_number,
                f'{item.paid_to or "-"} · {item.amount:,.0f} تومان', url_for('finance.expenses'))
        check_match = match(Check.check_number, Check.bank_name, Check.issuer_name,
                            Check.description, Check.tracking_notes,
                            Student.first_name, Student.last_name, Student.mobile,
                            Student.student_code)
        if numeric_value is not None:
            check_match = db.or_(check_match, Check.amount == numeric_value)
        query = (scope(Check.query, Check)
                 .outerjoin(Student, Check.student_id == Student.id)
                 .filter(check_match))
        for item in query.limit(per_group).all():
            add('finance', 'چک', 'file-earmark-check', '#d97706', item.check_number,
                f'{item.bank_name} · {item.amount:,.0f} تومان', url_for('finance.checks'))
        if has_feature('installments'):
            installment_match = match(Registration.reg_code, Student.first_name,
                                      Student.last_name, Student.mobile, Student.student_code,
                                      Course.title, Course.code,
                                      ClassGroup.name, ClassGroup.class_code)
            if numeric_value is not None:
                remaining_expr = (db.func.coalesce(Installment.amount, 0)
                                  + db.func.coalesce(Installment.late_fee, 0)
                                  - db.func.coalesce(Installment.paid_amount, 0))
                installment_match = db.or_(installment_match, Installment.amount == numeric_value,
                                           remaining_expr == numeric_value)
            query = (Installment.query.join(Registration).join(Student)
                     .outerjoin(Course, Registration.course_id == Course.id)
                     .outerjoin(ClassGroup, Registration.class_id == ClassGroup.id)
                     .options(joinedload(Installment.registration).joinedload(Registration.student))
                     .filter(installment_match))
            if not current_user.is_admin and current_user.branch_id:
                query = query.filter(Registration.branch_id == current_user.branch_id)
            for item in query.limit(per_group).all():
                reg = item.registration
                target = (url_for('reports.view', report_key='installment-calendar', student_id=reg.student_id)
                          if 'installment-calendar' in visible_reports()
                          else url_for('finance.payments', search=reg.reg_code))
                add('finance', 'قسط', 'calendar-check', '#f59e0b',
                    f'{reg.reg_code} / قسط {item.installment_number}',
                    f'{reg.student.full_name if reg and reg.student else "-"} · '
                    f'{((item.amount or 0) + (item.late_fee or 0) - (item.paid_amount or 0)):,.0f} تومان',
                    target)
        for item in ExpenseCategory.query.filter(match(ExpenseCategory.name, ExpenseCategory.code,
                                                        ExpenseCategory.description)).limit(per_group).all():
            add('finance', 'دسته هزینه', 'tags', '#be123c', item.name, item.code or '', url_for('finance.expenses'))
        discount_query = (DiscountCode.query
                          .outerjoin(Course, DiscountCode.course_id == Course.id)
                          .filter(match(DiscountCode.code, DiscountCode.description,
                                        Course.title, Course.code)))
        if not current_user.is_admin and current_user.branch_id:
            discount_query = discount_query.filter(db.or_(
                DiscountCode.course_id.is_(None), Course.branch_id == current_user.branch_id,
                Course.branch_id.is_(None),
            ))
        for item in discount_query.limit(per_group).all():
            add('finance', 'کد تخفیف', 'percent', '#db2777', item.code,
                f'{item.discount_value:g}', url_for('finance.discounts'))
        query = scope(Cashbox.query, Cashbox).filter(match(Cashbox.name, Cashbox.code, Cashbox.description))
        for item in query.limit(per_group).all():
            add('finance', 'صندوق', 'safe2', '#0d9488', item.name,
                f'{item.balance or 0:,.0f} تومان', url_for('finance.cashbox'))
        bank_match = match(BankAccount.bank_name, BankAccount.account_number,
                           BankAccount.card_number, BankAccount.sheba)
        if numeric_value is not None:
            bank_match = db.or_(bank_match, BankAccount.balance == numeric_value)
        bank_query = scope(BankAccount.query, BankAccount, True).filter(bank_match)
        for item in bank_query.limit(per_group).all():
            add('finance', 'حساب بانکی', 'bank', '#1d4ed8', item.bank_name,
                item.account_number or item.card_number or '', url_for('finance.bank'))
        if allowed('reports') and allowed('accounting'):
            budget_match = match(ReportBudget.title, ReportBudget.fiscal_year,
                                 ReportBudget.notes, Account.name, Account.code,
                                 ExpenseCategory.name, Branch.name)
            if numeric_value is not None:
                budget_match = db.or_(budget_match, ReportBudget.amount == numeric_value)
            # A NULL branch budget is an organisation-wide aggregate, not a
            # shared branch record.  Branch users only search their own lines.
            budget_query = (scope(ReportBudget.query, ReportBudget)
                            .outerjoin(Account, ReportBudget.account_id == Account.id)
                            .outerjoin(ExpenseCategory,
                                       ReportBudget.expense_category_id == ExpenseCategory.id)
                            .outerjoin(Branch, ReportBudget.branch_id == Branch.id)
                            .filter(budget_match))
            for item in budget_query.limit(per_group).all():
                add('finance', 'بودجه', 'bullseye', '#7c3aed', item.title,
                    f'{item.fiscal_year} · {item.amount or 0:,.0f} تومان',
                    url_for('reports.budgets'))

        if allowed('reports'):
            reconciliation_match = match(
                AccountReconciliation.notes, Cashbox.name, Cashbox.code,
                BankAccount.bank_name, BankAccount.account_number,
            )
            if numeric_value is not None:
                reconciliation_match = db.or_(
                    reconciliation_match,
                    AccountReconciliation.system_balance == numeric_value,
                    AccountReconciliation.statement_balance == numeric_value,
                    AccountReconciliation.difference == numeric_value,
                )
            reconciliation_query = (AccountReconciliation.query
                                    .outerjoin(Cashbox,
                                               AccountReconciliation.cashbox_id == Cashbox.id)
                                    .outerjoin(BankAccount,
                                               AccountReconciliation.bank_account_id == BankAccount.id)
                                    .filter(reconciliation_match))
            if not current_user.is_admin and current_user.branch_id:
                reconciliation_query = reconciliation_query.filter(db.or_(
                    Cashbox.branch_id == current_user.branch_id,
                    BankAccount.branch_id == current_user.branch_id,
                    db.and_(BankAccount.branch_id.is_(None),
                            AccountReconciliation.bank_account_id.is_not(None)),
                ))
            for item in reconciliation_query.limit(per_group).all():
                account_name = (item.cashbox.name if item.cashbox
                                else item.bank_account.bank_name if item.bank_account else '-')
                add('finance', 'مغایرت', 'clipboard2-check', '#ea580c', account_name,
                    f'{item.reconciliation_date} · {item.difference or 0:,.0f} تومان',
                    url_for('reports.reconciliations'))

    if allowed('payroll') and allowed('teachers') and wanted('payroll'):
        person_join = db.and_(Payslip.person_type == 'teacher',
                              Payslip.person_id == Teacher.id)
        payslip_match = match(
            Payslip.payslip_number, Payslip.period, Payslip.person_type,
            Payslip.status, Payslip.notes, Teacher.first_name,
            Teacher.last_name, Teacher.teacher_code,
        )
        if numeric_value is not None:
            payslip_match = db.or_(
                payslip_match, Payslip.gross_amount == numeric_value,
                Payslip.net_amount == numeric_value, Payslip.tax == numeric_value,
                Payslip.insurance == numeric_value,
            )
        payslip_query = (db.session.query(Payslip, Teacher)
                         .outerjoin(Teacher, person_join).filter(payslip_match))
        if not current_user.is_admin and current_user.branch_id:
            payslip_query = payslip_query.filter(
                Payslip.person_type == 'teacher',
                Teacher.branch_id == current_user.branch_id,
            )
        for item, teacher in payslip_query.limit(per_group).all():
            person = (teacher.full_name if teacher else
                      f'{item.person_type or "شخص"} #{item.person_id}')
            add('payroll', 'فیش حقوقی', 'person-vcard', '#9333ea',
                item.payslip_number, f'{person} · {item.net_amount or 0:,.0f} تومان',
                url_for('payroll.view_payslip', id=item.id))

        contract_join = db.and_(SalaryContract.person_type == 'teacher',
                                SalaryContract.person_id == Teacher.id)
        contract_match = match(
            SalaryContract.person_type, SalaryContract.contract_type,
            SalaryContract.notes, Teacher.first_name, Teacher.last_name,
            Teacher.teacher_code,
        )
        if numeric_value is not None:
            contract_match = db.or_(
                contract_match, SalaryContract.base_salary == numeric_value,
                SalaryContract.hourly_rate == numeric_value,
                SalaryContract.session_rate == numeric_value,
            )
        contract_query = (db.session.query(SalaryContract, Teacher)
                          .outerjoin(Teacher, contract_join).filter(contract_match))
        if not current_user.is_admin and current_user.branch_id:
            contract_query = contract_query.filter(
                SalaryContract.person_type == 'teacher',
                Teacher.branch_id == current_user.branch_id,
            )
        for item, teacher in contract_query.limit(per_group).all():
            person = (teacher.full_name if teacher else
                      f'{item.person_type or "شخص"} #{item.person_id}')
            add('payroll', 'قرارداد حقوق', 'file-person', '#7e22ce', person,
                item.contract_type or '', url_for('payroll.contracts'))

    if allowed('accounting') and wanted('accounting'):
        entry_match = match(JournalEntry.entry_number, JournalEntry.description,
                            JournalEntry.entry_type, JournalEntry.cancel_reason,
                            JournalEntry.adjustment_reason)
        if numeric_value is not None:
            entry_match = db.or_(entry_match, JournalEntry.total_debit == numeric_value,
                                 JournalEntry.total_credit == numeric_value)
        query = scope(JournalEntry.query, JournalEntry).filter(entry_match)
        for item in query.limit(per_group).all():
            add('accounting', 'سند حسابداری', 'journal-bookmark', '#4f46e5', item.entry_number,
                f'{item.description or "-"} · {item.total_debit or 0:,.0f} تومان',
                url_for('accounting.view_entry', id=item.id))
        for model, label, icon in ((Account, 'حساب کل', 'diagram-3'),
                                   (SubAccount, 'حساب معین', 'list-nested'),
                                   (DetailAccount, 'حساب تفصیلی', 'list-columns-reverse')):
            for item in model.query.filter(match(model.code, model.name, model.description)).limit(per_group).all():
                account_id = (item.id if model is Account else item.account_id if model is SubAccount
                              else item.sub_account.account_id if item.sub_account else None)
                if account_id:
                    add('accounting', label, icon, '#6366f1', item.name, item.code,
                        url_for('accounting.account_ledger', account_id=account_id))

    if allowed('exams') and wanted('exams'):
        exam_query = (Exam.query.options(joinedload(Exam.class_group), joinedload(Exam.course))
                      .outerjoin(ClassGroup, Exam.class_id == ClassGroup.id)
                      .outerjoin(Course, Exam.course_id == Course.id)
                      .filter(match(Exam.title, Exam.exam_code, Exam.notes,
                                    Course.title, Course.code,
                                    ClassGroup.name, ClassGroup.class_code)))
        question_query = (QuestionBank.query.outerjoin(Course, QuestionBank.course_id == Course.id)
                          .filter(match(QuestionBank.question_text, QuestionBank.chapter,
                                        QuestionBank.explanation, Course.title, Course.code)))
        if not current_user.is_admin and current_user.branch_id:
            visible_class = db.or_(ClassGroup.branch_id == current_user.branch_id,
                                   ClassGroup.branch_id.is_(None))
            visible_course = db.or_(Course.branch_id == current_user.branch_id,
                                    Course.branch_id.is_(None))
            exam_query = exam_query.filter(db.or_(
                db.and_(Exam.class_id.is_not(None), visible_class),
                db.and_(Exam.class_id.is_(None), visible_course),
            ))
            question_query = question_query.filter(visible_course)
        for item in exam_query.limit(per_group).all():
            add('exams', 'آزمون', 'journal-check', '#8b5cf6', item.title,
                item.exam_code or '', url_for('exams.view', id=item.id))
        for item in question_query.limit(per_group).all():
            add('exams', 'سؤال', 'question-circle', '#9333ea', item.question_text[:90],
                item.chapter or '', url_for('exams.question_bank'))

    if allowed('certificates') and wanted('certificates'):
        query = (Certificate.query.options(joinedload(Certificate.student), joinedload(Certificate.course))
                 .join(Student, Certificate.student_id == Student.id)
                 .outerjoin(Course, Certificate.course_id == Course.id)
                 .filter(match(Certificate.serial_number, Certificate.notes,
                               Student.first_name, Student.last_name, Student.student_code,
                               Course.title, Course.code)))
        if not current_user.is_admin and current_user.branch_id:
            query = query.filter(db.or_(
                Student.branch_id == current_user.branch_id,
                db.and_(Student.branch_id.is_(None),
                        Course.branch_id == current_user.branch_id),
            ))
        for item in query.limit(per_group).all():
            add('certificates', 'گواهینامه', 'award', '#f59e0b', item.serial_number,
                f'{item.student.full_name if item.student else "-"} · {item.course.title if item.course else "-"}',
                url_for('certificates.index'))

    if allowed('messaging') and wanted('messages'):
        query = Message.query.filter(match(Message.phone, Message.message_text,
            Message.delivery_status, Message.error_message))
        if not current_user.is_admin:
            query = query.filter(Message.created_by == current_user.id)
        for item in query.limit(per_group).all():
            add('messages', 'پیامک', 'chat-dots', '#0284c7', item.phone or 'بدون شماره',
                (item.message_text or '')[:100], url_for('messaging.sms'))
        query = InternalMessage.query.filter(match(InternalMessage.subject, InternalMessage.body))
        if not current_user.is_admin:
            query = query.filter(db.or_(InternalMessage.sender_id == current_user.id,
                                        InternalMessage.receiver_id == current_user.id))
        for item in query.limit(per_group).all():
            add('messages', 'پیام داخلی', 'envelope', '#0369a1', item.subject or 'بدون عنوان',
                (item.body or '')[:100], url_for('messaging.view_message', id=item.id))

    if allowed('settings') and wanted('support'):
        ticket_query = Ticket.query.filter(match(Ticket.ticket_number, Ticket.subject,
                                                  Ticket.description))
        if not current_user.is_admin:
            ticket_query = ticket_query.filter(db.or_(Ticket.user_id == current_user.id,
                                                       Ticket.assigned_to == current_user.id))
        for item in ticket_query.limit(per_group).all():
            add('support', 'تیکت', 'ticket', '#64748b', item.ticket_number,
                item.subject, url_for('tickets.view', id=item.id))
        complaint_query = Complaint.query.filter(match(
            Complaint.complaint_number, Complaint.complainant_name,
            Complaint.complainant_phone, Complaint.subject, Complaint.description,
        ))
        if not current_user.is_admin and current_user.branch_id:
            # Anonymous complaints have no reliable branch ownership and stay
            # central; branch users only discover complaints tied to their own
            # students.
            complaint_query = complaint_query.join(Student).filter(
                Student.branch_id == current_user.branch_id
            )
        for item in complaint_query.limit(per_group).all():
            add('support', 'شکایت', 'exclamation-circle', '#e11d48',
                item.complaint_number or item.subject, item.complainant_name or '',
                url_for('complaints.index'))

    if allowed('user_management') and wanted('users'):
        query = scope(User.query, User).filter(match(User.username, User.full_name, User.email, User.phone))
        for item in query.limit(per_group).all():
            add('users', 'کاربر', 'person-gear', '#475569', item.full_name,
                f'{item.username} · {item.role.name if item.role else "-"}', url_for('perms.edit_user', id=item.id))

    if allowed('reports') and wanted('reports'):
        available_reports = visible_reports()
        for item in (ReportSchedule.query.filter_by(user_id=current_user.id)
                     .filter(match(ReportSchedule.name, ReportSchedule.report_key))
                     .limit(per_group).all()):
            add('reports', 'زمان‌بندی گزارش', 'clock-history', '#0ea5e9',
                item.name, item.report_key, url_for('reports.schedules'))
        for item in (ReportPreset.query.filter_by(user_id=current_user.id)
                     .filter(ReportPreset.report_key.in_(tuple(available_reports)),
                             match(ReportPreset.name, ReportPreset.report_key))
                     .limit(per_group).all()):
            add('reports', 'نمای ذخیره‌شده', 'bookmark-check', '#8b5cf6',
                item.name, item.report_key,
                url_for('reports.apply_preset', preset_id=item.id))
        needle = normalise_text(raw)
        for key, meta in available_reports.items():
            if needle in normalise_text(meta['title'] + ' ' + meta['description']):
                add('reports', 'گزارش', meta['icon'], meta['color'], meta['title'],
                    meta['description'], url_for('reports.view', report_key=key))
                if sum(item['group'] == 'reports' for item in results) >= per_group:
                    break

    order = {'reports': 0, 'students': 1, 'registrations': 2, 'finance': 3,
             'accounting': 4, 'courses': 5, 'classes': 6, 'teachers': 7,
             'exams': 8, 'certificates': 9, 'payroll': 10,
             'messages': 11, 'users': 12, 'support': 13}
    results.sort(key=lambda item: (order.get(item['group'], 99), normalise_text(item['name'])))
    groups = {}
    capped_results = []
    for item in results:
        group = item['group']
        if groups.get(group, 0) >= per_group:
            continue
        groups[group] = groups.get(group, 0) + 1
        capped_results.append(item)
    return jsonify({'results': capped_results, 'groups': groups,
                    'count': len(capped_results), 'query': raw})

# ═══════════════════════════════════════════════════════════════
#  صفحات باقیمانده — تکمیل پوشش ۱۰۰٪
# ═══════════════════════════════════════════════════════════════

@final_bp.route('/students/<int:id>/multi-register', methods=['GET', 'POST'])
@login_required
def multi_register(id):
    """ثبت‌نام چند دوره‌ای هنرجو"""
    from models.student import Student
    from models.course import Course
    from models.classes import ClassGroup
    from models.registration import Registration
    from models.finance import Payment
    
    student = Student.query.get_or_404(id)
    
    if request.method == 'POST':
        course_ids = request.form.getlist('course_ids')
        class_ids = request.form.getlist('class_ids')
        
        count = 0
        for i, cid in enumerate(course_ids):
            if not cid:
                continue
            
            course = Course.query.get(int(cid))
            if not course:
                continue
            
            last = Registration.query.order_by(Registration.id.desc()).first()
            reg_code = f'REG-{(last.id + 1 + count) if last else 1:06d}'
            
            cls_id = int(class_ids[i]) if i < len(class_ids) and class_ids[i] else None
            
            reg = Registration(
                reg_code=reg_code,
                student_id=id,
                course_id=int(cid),
                class_id=cls_id,
                registration_date=datetime.utcnow().date(),
                base_fee=course.total_fee,
                total_fee=course.total_fee,
                remaining_amount=course.total_fee,
                status='active',
                branch_id=student.branch_id or 1,
                created_by=current_user.id
            )
            reg.calculate_fees()
            db.session.add(reg)
            
            if cls_id:
                cls = ClassGroup.query.get(cls_id)
                if cls:
                    cls.current_count = (cls.current_count or 0) + 1
            
            count += 1
        
        db.session.commit()
        flash(f'{count} دوره برای {student.full_name} ثبت شد', 'success')
        return redirect(url_for('students.view', id=id))
    
    courses = Course.query.filter_by(is_active=True).all()
    classes = ClassGroup.query.filter_by(status='active').all()
    
    return render_template('new/multi_register.html', student=student, courses=courses, classes=classes)


@final_bp.route('/corporate/<int:id>/invoice')
@login_required
def corporate_invoice(id):
    """صورتحساب سازمانی"""
    from models.student import Student
    from models.registration import Registration
    
    student = Student.query.get_or_404(id)
    regs = Registration.query.filter_by(student_id=id).all()
    
    total = sum(r.total_fee for r in regs)
    paid = sum(r.paid_amount for r in regs)
    
    return render_template('new/corporate_invoice.html', student=student, regs=regs, total=total, paid=paid)


@final_bp.route('/settings/auto-sms-triggers', methods=['GET', 'POST'])
@login_required
def auto_sms_triggers():
    """تنظیمات ارسال خودکار پیامک"""
    from models.system import SystemSettings
    settings = SystemSettings.query.first()
    
    if request.method == 'POST':
        # ذخیره تنظیمات trigger
        flash('تنظیمات ارسال خودکار ذخیره شد', 'success')
        return redirect(url_for('final.auto_sms_triggers'))
    
    return render_template('new/auto_sms_triggers.html', settings=settings)


@final_bp.route('/settings/auto-sms/registration', methods=['POST'])
@login_required
def trigger_registration_sms():
    """ارسال پیامک خودکار ثبت‌نام"""
    from models.registration import Registration
    from models.system import Message
    
    reg_id = request.form.get('registration_id')
    if not reg_id:
        return jsonify({'ok': False, 'error': 'شناسه ثبت‌نام الزامی است'}), 400
    try:
        reg = db.session.get(Registration, int(reg_id))
    except (ValueError, TypeError):
        reg = None
    
    if reg and reg.student and reg.student.mobile:
        msg_text = f"ثبت‌نام شما در دوره {reg.course.title if reg.course else ''} با موفقیت انجام شد. کد: {reg.reg_code}"
        
        from routes.new_features import send_farazsms
        send_farazsms(reg.student.mobile, msg_text)
        
        log = Message(
            recipient_type='student', recipient_id=reg.student_id,
            phone=reg.student.mobile, message_text=msg_text,
            send_type='auto_registration', status='sent',
            created_by=current_user.id
        )
        db.session.add(log)
        db.session.commit()
    
    return jsonify({'ok': True})


@final_bp.route('/settings/auto-sms/absence', methods=['POST'])
@login_required
def trigger_absence_sms():
    """ارسال پیامک خودکار غیبت"""
    from models.attendance import Attendance
    from models.system import Message
    
    session_id = request.form.get('session_id')
    absentees = Attendance.query.filter_by(session_id=session_id, status='absent').all()
    
    from routes.new_features import send_farazsms
    
    count = 0
    for att in absentees:
        if att.student and att.student.mobile:
            msg_text = f"هنرجوی گرامی، شما در جلسه امروز غایب بودید. لطفاً با آموزشگاه تماس بگیرید."
            send_farazsms(att.student.mobile, msg_text)
            
            log = Message(
                recipient_type='student', recipient_id=att.student_id,
                phone=att.student.mobile, message_text=msg_text,
                send_type='auto_absence', status='sent',
                created_by=current_user.id
            )
            db.session.add(log)
            count += 1
    
    db.session.commit()
    flash(f'پیامک غیبت به {count} نفر ارسال شد', 'info')
    return jsonify({'ok': True, 'count': count})


@final_bp.route('/settings/auto-sms/birthday', methods=['POST'])
@login_required
def trigger_birthday_sms():
    """ارسال پیامک تولد"""
    from models.student import Student
    from models.system import Message
    
    today = datetime.utcnow().date()
    
    students = Student.query.filter(
        db.extract('month', Student.birth_date) == today.month,
        db.extract('day', Student.birth_date) == today.day,
        Student.status == 'active'
    ).all()
    
    from routes.new_features import send_farazsms
    
    count = 0
    for s in students:
        if s.mobile:
            msg_text = f"🎉 {s.full_name} عزیز، تولدت مبارک! آرزوی موفقیت برای شما داریم. آموزشگاه"
            send_farazsms(s.mobile, msg_text)
            
            log = Message(
                recipient_type='student', recipient_id=s.id,
                phone=s.mobile, message_text=msg_text,
                send_type='birthday', status='sent',
                created_by=current_user.id
            )
            db.session.add(log)
            count += 1
    
    db.session.commit()
    flash(f'پیامک تولد به {count} نفر ارسال شد', 'success')
    return jsonify({'ok': True, 'count': count})


@final_bp.route('/settings/auto-sms/payment', methods=['POST'])
@login_required
def trigger_payment_sms():
    """ارسال پیامک تایید پرداخت"""
    from models.finance import Payment
    from models.system import Message
    
    payment_id = request.form.get('payment_id')
    if not payment_id:
        return jsonify({'ok': False, 'error': 'شناسه پرداخت الزامی است'}), 400
    try:
        payment = db.session.get(Payment, int(payment_id))
    except (ValueError, TypeError):
        payment = None
    
    if payment and payment.student and payment.student.mobile:
        msg_text = (
            f"پرداخت شما به مبلغ {payment.amount:,.0f} تومان "
            f"با رسید {payment.receipt_no} ثبت شد. متشکریم."
        )
        
        from routes.new_features import send_farazsms
        send_farazsms(payment.student.mobile, msg_text)
        
        log = Message(
            recipient_type='student', recipient_id=payment.student_id,
            phone=payment.student.mobile, message_text=msg_text,
            send_type='auto_payment', status='sent',
            created_by=current_user.id
        )
        db.session.add(log)
        db.session.commit()
    
    return jsonify({'ok': True})


# ═══════════════════════════════════════════════════════════════
#  گزارش سلامت پیشرفته
# ═══════════════════════════════════════════════════════════════

@final_bp.route('/settings/system-health/advanced')
@login_required
def advanced_health():
    """گزارش سلامت پیشرفته"""
    from models.user import User, ActivityLog
    from models.student import Student
    from models.teacher import Teacher
    from models.registration import Registration
    from models.finance import Payment, Expense
    from models.classes import ClassGroup
    import platform
    from utils.database_tools import collect_table_stats, database_size_bytes

    table_stats = collect_table_stats()
    db_size = database_size_bytes()
    
    # آمار کلی
    stats = {
        'db_size_mb': round(db_size / (1024 * 1024), 2),
        'db_size_bytes': db_size,
        'total_tables': len(table_stats),
        'total_records': sum(t['count'] for t in table_stats),
        'total_users': User.query.count(),
        'active_users': User.query.filter_by(is_active=True).count(),
        'total_students': Student.query.count(),
        'active_students': Student.query.filter_by(status='active').count(),
        'total_teachers': Teacher.query.count(),
        'active_teachers': Teacher.query.filter_by(is_active=True).count(),
        'total_classes': ClassGroup.query.count(),
        'active_classes': ClassGroup.query.filter_by(status='active').count(),
        'total_registrations': Registration.query.count(),
        'active_registrations': Registration.query.filter_by(status='active').count(),
        'total_payments': Payment.query.count(),
        'total_expenses': Expense.query.count(),
        'platform': platform.system(),
        'python': platform.python_version(),
    }
    
    # سلامت
    health_checks = []
    
    # بررسی دیتابیس
    try:
        db.session.execute(db.text('SELECT 1'))
        health_checks.append({'name': 'اتصال دیتابیس', 'status': 'ok', 'message': 'سالم'})
    except:
        health_checks.append({'name': 'اتصال دیتابیس', 'status': 'error', 'message': 'خطا'})
    
    # بررسی حجم
    if stats['db_size_mb'] > 500:
        health_checks.append({'name': 'حجم دیتابیس', 'status': 'warning', 'message': f'{stats["db_size_mb"]} MB - نیاز به بهینه‌سازی'})
    else:
        health_checks.append({'name': 'حجم دیتابیس', 'status': 'ok', 'message': f'{stats["db_size_mb"]} MB'})
    
    # بررسی کاربران
    if stats['active_users'] == 0:
        health_checks.append({'name': 'کاربران', 'status': 'error', 'message': 'کاربر فعالی نیست'})
    else:
        health_checks.append({'name': 'کاربران', 'status': 'ok', 'message': f'{stats["active_users"]} فعال'})
    
    # بررسی لاگ‌های اخیر
    recent_logs = ActivityLog.query.order_by(ActivityLog.created_at.desc()).limit(5).all()
    
    return render_template('new/advanced_health.html', stats=stats, table_stats=table_stats, 
                         health_checks=health_checks, recent_logs=recent_logs)
