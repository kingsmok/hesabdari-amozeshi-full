"""Unified, permission-aware reporting engine.

Every report shown by the reporting centre is declared in ``REPORT_CATALOG`` and
is produced from the operational database.  The engine deliberately returns a
plain, serialisable structure so the same calculation powers HTML, JSON, CSV,
Excel, PDF, print, snapshots and scheduled delivery.
"""
from __future__ import annotations

import math
import re
import unicodedata
from collections import OrderedDict, defaultdict
from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Iterable, Mapping

from flask import url_for
from sqlalchemy import DateTime as SADateTime
from sqlalchemy.orm import joinedload

from extensions import db
from utils.local_time import local_now, local_today
from utils.jalali import (
    gregorian_to_jalali,
    gregorian_to_jalali_obj,
    jalali_month_name,
    parse_jalali_date,
)


FA_DIGITS = str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789')
STATUS_LABELS = {
    'active': 'فعال', 'inactive': 'غیرفعال', 'graduated': 'فارغ‌التحصیل',
    'withdrawn': 'انصرافی', 'suspended': 'تعلیق', 'transferred': 'منتقل‌شده',
    'completed': 'تکمیل‌شده', 'cancelled': 'لغوشده', 'archived': 'بایگانی',
    'draft': 'پیش‌نویس', 'confirmed': 'تأییدشده', 'approved': 'تصویب‌شده',
    'pending': 'در انتظار', 'partial': 'پرداخت ناقص', 'paid': 'پرداخت‌شده',
    'overdue': 'سررسیدگذشته', 'received': 'دریافتی', 'cashed': 'وصول‌شده',
    'bounced': 'برگشتی', 'spent': 'خرج‌شده', 'issued': 'پرداختی',
    'present': 'حاضر', 'absent': 'غایب', 'late': 'تأخیر', 'leave': 'مرخصی',
    'scheduled': 'زمان‌بندی‌شده', 'in_progress': 'در حال انجام',
    'open': 'باز', 'resolved': 'رفع‌شده', 'reissued': 'صدور مجدد',
    'frozen': 'تعلیق ثبت‌نام',
}
PAYMENT_METHOD_LABELS = {
    'cash': 'نقدی', 'card': 'کارت‌خوان', 'online': 'آنلاین', 'check': 'چک',
    'combined': 'ترکیبی', 'transfer': 'انتقال بانکی', None: 'نامشخص', '': 'نامشخص',
}
REFERRAL_LABELS = {
    'instagram': 'اینستاگرام', 'friend': 'معرفی دوستان', 'website': 'وب‌سایت',
    'phone': 'تماس تلفنی', 'ad': 'تبلیغات', 'other': 'سایر',
    None: 'نامشخص', '': 'نامشخص',
}
ACCOUNT_TYPE_LABELS = {
    'asset': 'دارایی', 'liability': 'بدهی', 'equity': 'حقوق مالکانه',
    'revenue': 'درآمد', 'expense': 'هزینه', None: 'نامشخص', '': 'نامشخص',
}
REPORT_STATUS_VALUES = {
    'journal': ('draft', 'confirmed', 'approved', 'cancelled'),
    'payments': ('confirmed', 'pending', 'cancelled'),
    'expenses': ('confirmed', 'pending', 'cancelled'),
    'reconciliation': ('open', 'resolved'),
    'checks': ('received', 'pending', 'cashed', 'bounced', 'spent', 'cancelled'),
    'payroll': ('draft', 'approved', 'paid'),
    'payroll_tax': ('draft', 'approved', 'paid'),
    'students': ('active', 'graduated', 'withdrawn', 'suspended', 'transferred'),
    'student_lifecycle': ('active', 'graduated', 'withdrawn', 'suspended', 'transferred'),
    'enrollments': ('active', 'completed', 'withdrawn', 'frozen', 'transferred'),
    'class_capacity': ('active', 'completed', 'cancelled'),
    'exams': ('draft', 'scheduled', 'in_progress', 'completed'),
    'certificates': ('active', 'cancelled', 'reissued'),
}
CATEGORY_LABELS = OrderedDict([
    ('executive', 'مدیریتی'),
    ('accounting', 'حسابداری'),
    ('finance', 'دریافت‌ها و عملیات مالی'),
    ('cash_bank', 'صندوق، بانک و مغایرت'),
    ('receivables', 'مطالبات، اقساط و چک'),
    ('profitability', 'هزینه، بودجه و سودآوری'),
    ('education', 'آموزشی'),
    ('performance', 'عملکرد و تحلیل'),
    ('payroll', 'حقوق و دستمزد'),
    ('tax', 'بیمه و مالیات'),
])


def _meta(title: str, description: str, category: str, icon: str, color: str,
          builder: str, *, variant: str | int | None = None,
          permission: str = 'reports', filters: Iterable[str] | None = None,
          date_mode: str = 'range',
          license_features: Iterable[str] | None = None,
          source_permissions: Iterable[str] | None = None) -> dict:
    return {
        'title': title, 'description': description, 'category': category,
        'icon': icon, 'color': color, 'builder': builder, 'variant': variant,
        'permission': permission, 'date_mode': date_mode,
        'license_features': list(license_features or (permission,)),
        # Reports may combine otherwise independent data areas. Listing every
        # source prevents an aggregate route from becoming a permission or
        # licence side channel into a restricted module.
        'source_permissions': list(source_permissions or (
            () if permission == 'reports' else (permission,)
        )),
        'filters': list(filters or ('date', 'branch', 'q')),
    }


# One catalogue is the source of truth for cards, search, permissions and routes.
REPORT_CATALOG: "OrderedDict[str, dict[str, Any]]" = OrderedDict([
    ('executive-dashboard', _meta('داشبورد مدیریتی', 'شاخص‌های کلیدی مالی، آموزشی و هشدارهای روز', 'executive', 'speedometer2', '#2563eb', 'executive', filters=('date', 'branch', 'q'))),
    ('journal', _meta('دفتر روزنامه', 'اسناد حسابداری با گردش بدهکار و بستانکار', 'accounting', 'journal-bookmark', '#4f46e5', 'journal', permission='accounting', filters=('date', 'branch', 'status', 'q', 'fiscal'))),
    ('general-ledger', _meta('دفتر کل', 'گردش و مانده حساب‌های کل با امکان ورود به سند', 'accounting', 'book', '#4338ca', 'ledger', variant='account', permission='accounting', filters=('date', 'branch', 'account', 'q', 'fiscal'))),
    ('subsidiary-ledger', _meta('دفتر معین', 'گردش حساب‌ها در سطح معین', 'accounting', 'bookshelf', '#6366f1', 'ledger', variant='sub', permission='accounting', filters=('date', 'branch', 'account', 'q', 'fiscal'))),
    ('detail-ledger', _meta('دفتر تفصیلی', 'گردش حساب‌ها در سطح تفصیلی', 'accounting', 'list-nested', '#7c3aed', 'ledger', variant='detail', permission='accounting', filters=('date', 'branch', 'account', 'q', 'fiscal'))),
    ('trial-balance-2', _meta('تراز آزمایشی دو ستونی', 'مانده بدهکار و بستانکار حساب‌ها', 'accounting', 'columns-gap', '#0f766e', 'trial_balance', variant=2, permission='accounting', filters=('date', 'branch', 'account', 'q', 'fiscal'))),
    ('trial-balance-4', _meta('تراز آزمایشی چهار ستونی', 'گردش دوره و مانده پایان دوره', 'accounting', 'layout-three-columns', '#0d9488', 'trial_balance', variant=4, permission='accounting', filters=('date', 'branch', 'account', 'q', 'fiscal'))),
    ('trial-balance-6', _meta('تراز آزمایشی شش ستونی', 'اول دوره، گردش دوره و پایان دوره', 'accounting', 'grid-3x2', '#0891b2', 'trial_balance', variant=6, permission='accounting', filters=('date', 'branch', 'account', 'q', 'fiscal'))),
    ('trial-balance-8', _meta('تراز آزمایشی هشت ستونی', 'تراز کامل تجمعی و مانده نهایی', 'accounting', 'grid-3x3-gap', '#0284c7', 'trial_balance', variant=8, permission='accounting', filters=('date', 'branch', 'account', 'q', 'fiscal'))),
    ('balance-sheet', _meta('ترازنامه', 'دارایی‌ها، بدهی‌ها و حقوق مالکانه تا تاریخ گزارش', 'accounting', 'scale', '#0369a1', 'balance_sheet', permission='accounting', filters=('date', 'branch', 'q', 'fiscal'))),
    ('profit-loss', _meta('صورت سود و زیان', 'درآمد، هزینه و سود خالص بر مبنای اسناد قطعی', 'accounting', 'graph-up-arrow', '#059669', 'profit_loss', permission='accounting', filters=('date', 'branch', 'q', 'fiscal'))),
    ('cash-flow', _meta('جریان وجوه نقد', 'ورودی و خروجی نقد به تفکیک ماه شمسی', 'accounting', 'water', '#0ea5e9', 'cash_flow', permission='accounting', filters=('date', 'branch', 'q'))),
    ('equity-changes', _meta('تغییرات حقوق مالکانه', 'گردش حساب‌های حقوق مالکانه', 'accounting', 'pie-chart', '#8b5cf6', 'equity', permission='accounting', filters=('date', 'branch', 'q', 'fiscal'))),
    ('account-turnover', _meta('گردش حساب‌ها', 'جمع بدهکار، بستانکار و مانده هر حساب', 'accounting', 'arrow-left-right', '#64748b', 'ledger', variant='account', permission='accounting', filters=('date', 'branch', 'account', 'q', 'fiscal'))),
    ('opening-closing', _meta('مانده اول و پایان دوره', 'کنترل مانده افتتاحیه، گردش و اختتامیه', 'accounting', 'calendar2-range', '#475569', 'trial_balance', variant=6, permission='accounting', filters=('date', 'branch', 'account', 'q', 'fiscal'))),
    ('unbalanced-entries', _meta('اسناد نامتوازن', 'کنترل اختلاف بدهکار و بستانکار اسناد', 'accounting', 'exclamation-octagon', '#dc2626', 'journal', variant='unbalanced', permission='accounting', filters=('date', 'branch', 'q', 'fiscal'))),
    ('draft-entries', _meta('اسناد در انتظار تأیید', 'پیش‌نویس‌ها و اسناد تأییدنشده', 'accounting', 'hourglass-split', '#d97706', 'journal', variant='draft', permission='accounting', filters=('date', 'branch', 'q', 'fiscal'))),
    ('cancelled-adjusted-entries', _meta('اسناد اصلاحی و ابطالی', 'ردیابی دلیل اصلاح و ابطال اسناد', 'accounting', 'pencil-square', '#be123c', 'journal', variant='changed', permission='accounting', filters=('date', 'branch', 'q', 'fiscal'))),
    ('document-sequence', _meta('کنترل شماره اسناد', 'شناسایی فاصله و شماره‌های غیرعادی اسناد', 'accounting', '123', '#9333ea', 'sequence', permission='accounting', filters=('date', 'branch', 'q', 'fiscal'))),
    ('fiscal-close', _meta('کنترل پایان دوره مالی', 'وضعیت دوره‌ها و کنترل‌های لازم برای بستن سال', 'accounting', 'calendar2-check', '#334155', 'fiscal', permission='accounting', filters=('branch', 'fiscal', 'q'))),
    ('receipts-payments', _meta('دریافت‌ها و پرداخت‌ها', 'فهرست کامل رسیدها و جریان پرداخت شهریه', 'finance', 'receipt', '#16a34a', 'payments', permission='finance', filters=('date', 'branch', 'status', 'course', 'student', 'q'))),
    ('payment-methods', _meta('روش‌های پرداخت', 'سهم نقد، کارت، آنلاین، چک و پرداخت ترکیبی', 'finance', 'credit-card', '#15803d', 'payment_methods', permission='finance', filters=('date', 'branch', 'status', 'q'))),
    ('cancelled-payments', _meta('رسیدهای لغوشده', 'کنترل پرداخت‌های لغوشده و مشکوک', 'finance', 'receipt-cutoff', '#e11d48', 'payments', variant='cancelled', permission='finance', filters=('date', 'branch', 'student', 'q'))),
    ('cashbox-daily', _meta('گردش صندوق', 'ورودی، خروجی و مانده پس از هر تراکنش صندوق', 'cash_bank', 'cash-stack', '#0f766e', 'cashbox_transactions', permission='finance', filters=('date', 'branch', 'q'))),
    ('cashbox-balances', _meta('موجودی صندوق‌ها', 'مانده لحظه‌ای و وضعیت صندوق‌های فعال', 'cash_bank', 'safe2', '#0d9488', 'cashbox_balances', permission='finance', filters=('branch', 'q'))),
    ('cashbox-reconciliation', _meta('مغایرت صندوق', 'مقایسه مانده سیستم و شمارش واقعی صندوق', 'cash_bank', 'clipboard2-check', '#ea580c', 'reconciliation', variant='cashbox', permission='finance', filters=('date', 'branch', 'status', 'q'))),
    ('bank-transactions', _meta('گردش بانک', 'تراکنش‌های واریز، برداشت و انتقال بانکی', 'cash_bank', 'bank', '#0369a1', 'bank_transactions', permission='finance', filters=('date', 'branch', 'q'))),
    ('bank-balances', _meta('مانده حساب‌های بانکی', 'مانده لحظه‌ای حساب‌ها و کارت‌های بانکی', 'cash_bank', 'bank2', '#1d4ed8', 'bank_balances', permission='finance', filters=('branch', 'q'))),
    ('bank-transfers', _meta('انتقال‌های بانکی', 'انتقال وجه بین حساب‌ها و منابع مالی', 'cash_bank', 'arrow-repeat', '#4f46e5', 'bank_transactions', variant='transfer', permission='finance', filters=('date', 'branch', 'q'))),
    ('bank-reconciliation', _meta('مغایرت بانکی', 'تطبیق مانده سیستم با صورت‌حساب بانک', 'cash_bank', 'check2-square', '#f97316', 'reconciliation', variant='bank', permission='finance', filters=('date', 'branch', 'status', 'q'))),
    ('expense-category', _meta('هزینه بر اساس دسته‌بندی', 'تحلیل هزینه‌های قطعی بر مبنای سرفصل', 'profitability', 'tags', '#dc2626', 'expenses', variant='category', permission='finance', filters=('date', 'branch', 'status', 'q'))),
    ('expense-payee', _meta('هزینه بر اساس دریافت‌کننده', 'تحلیل پرداخت‌ها به اشخاص و تأمین‌کنندگان', 'profitability', 'person-down', '#b91c1c', 'expenses', variant='payee', permission='finance', filters=('date', 'branch', 'status', 'q'))),
    ('budget-actual', _meta('بودجه و عملکرد', 'مقایسه بودجه مصوب با درآمد و هزینه واقعی', 'profitability', 'bullseye', '#7c3aed', 'budget', permission='finance', filters=('date', 'branch', 'q'))),
    ('break-even', _meta('نقطه سربه‌سر', 'روند درآمد، هزینه و مازاد یا کسری ماهانه', 'profitability', 'activity', '#0891b2', 'break_even', permission='finance', filters=('date', 'branch', 'q'))),
    ('course-profitability', _meta('سودآوری دوره و کلاس', 'سود تعهدی ثبت‌نام‌های دوره در کنار وصول واقعی بازه و هزینه مستقیم مدرس', 'profitability', 'mortarboard', '#059669', 'course_profitability', permission='finance', filters=('date', 'branch', 'course', 'teacher', 'q'))),
    ('branch-profitability', _meta('سودآوری شعب', 'درآمد، هزینه و سود مستقیم هر شعبه', 'profitability', 'building-check', '#047857', 'branch_profitability', permission='finance', filters=('date', 'branch', 'q'))),
    ('payroll-summary', _meta('خلاصه حقوق و دستمزد', 'فیش‌های حقوقی، ناخالص، کسورات و خالص پرداختی', 'payroll', 'person-vcard', '#9333ea', 'payroll', permission='payroll', filters=('date', 'branch', 'status', 'q'))),
    ('payroll-tax', _meta('مالیات و بیمه حقوق', 'مالیات تکلیفی و بیمه هر فیش به تفکیک شخص و دوره', 'payroll', 'percent', '#c026d3', 'payroll_tax', permission='tax', filters=('date', 'branch', 'status', 'q'))),
    ('tax-control-summary', _meta('خلاصه کنترل مالیاتی', 'گردش درآمد، هزینه و کسورات قانونی برای کنترل اظهارنامه', 'tax', 'clipboard2-pulse', '#be123c', 'tax_summary', permission='tax', filters=('date', 'branch', 'q'))),
    ('statutory-accounts', _meta('گردش حساب‌های مالیات و بیمه', 'مانده و گردش سرفصل‌های مالیات، ارزش افزوده و بیمه', 'tax', 'journal-medical', '#9f1239', 'statutory_accounts', permission='tax', filters=('date', 'branch', 'account', 'q', 'fiscal'))),
    ('checks-all', _meta('گزارش جامع چک‌ها', 'چک‌های دریافتی و پرداختی با وضعیت جاری', 'receivables', 'file-earmark-check', '#2563eb', 'checks', permission='finance', filters=('date', 'branch', 'status', 'student', 'q'))),
    ('checks-received', _meta('چک‌های دریافتی', 'چک‌های دریافتی از هنرجویان و اشخاص', 'receivables', 'box-arrow-in-down', '#16a34a', 'checks', variant='received', permission='finance', filters=('date', 'branch', 'status', 'student', 'q'))),
    ('checks-issued', _meta('چک‌های پرداختی', 'چک‌های صادرشده آموزشگاه', 'receivables', 'box-arrow-up', '#7c3aed', 'checks', variant='issued', permission='finance', filters=('date', 'branch', 'status', 'q'))),
    ('checks-due', _meta('چک‌های نزدیک سررسید', 'چک‌های باز با سررسید ۳۰ روز آینده', 'receivables', 'calendar2-event', '#d97706', 'checks', variant='due', permission='finance', filters=('branch', 'q'))),
    ('checks-bounced', _meta('چک‌های برگشتی', 'چک‌های برگشتی همراه با علت و پیگیری', 'receivables', 'exclamation-diamond', '#dc2626', 'checks', variant='bounced', permission='finance', filters=('date', 'branch', 'student', 'q'))),
    ('receivables-aging', _meta('سنی مطالبات', 'طبقه‌بندی مانده بدهی باز تا تاریخ مبنا در بازه‌های ۳۰، ۶۰ و ۹۰ روزه', 'receivables', 'hourglass-bottom', '#ea580c', 'receivables', variant='aging', permission='finance', filters=('date', 'branch', 'course', 'student', 'q'), date_mode='as_of')),
    ('debtors', _meta('بدهکاران', 'مانده بدهی باز هنرجویان تا تاریخ مبنا، به تفکیک پرونده و ثبت‌نام', 'receivables', 'person-exclamation', '#e11d48', 'receivables', variant='detail', permission='finance', filters=('date', 'branch', 'course', 'student', 'q'), date_mode='as_of')),
    ('installments-overdue', _meta('اقساط عقب‌افتاده', 'مانده اقساط سررسیدگذشته و روزهای تأخیر', 'receivables', 'calendar2-x', '#dc2626', 'installments', variant='overdue', permission='finance', filters=('branch', 'course', 'student', 'q'))),
    ('installments-upcoming', _meta('اقساط نزدیک سررسید', 'اقساط باز با سررسید ۳۰ روز آینده', 'receivables', 'calendar2-week', '#d97706', 'installments', variant='upcoming', permission='finance', filters=('branch', 'course', 'student', 'q'))),
    ('installment-calendar', _meta('تقویم وصول اقساط', 'برنامه وصول و جریان نقدی مورد انتظار', 'receivables', 'calendar3', '#0284c7', 'installments', variant='calendar', permission='finance', filters=('date', 'branch', 'course', 'student', 'q'))),
    ('discounts', _meta('تخفیف‌ها و ابطال‌ها', 'تخفیف اعطایی بر اساس دوره، کاربر و پرونده', 'receivables', 'percent', '#db2777', 'discounts', permission='finance', filters=('date', 'branch', 'course', 'student', 'q'))),
    ('students', _meta('گزارش جامع هنرجویان', 'پرونده، تماس، وضعیت، شعبه و مانده بدهی', 'education', 'people', '#2563eb', 'students', permission='students', filters=('date', 'branch', 'status', 'student', 'q'))),
    ('enrollments', _meta('گزارش ثبت‌نام‌ها', 'ثبت‌نام، شهریه، تخفیف، وصول و مانده', 'education', 'person-plus', '#7c3aed', 'enrollments', permission='registration', filters=('date', 'branch', 'status', 'course', 'class', 'teacher', 'student', 'q'))),
    ('enrollment-trend', _meta('روند ثبت‌نام شمسی', 'ثبت‌نام‌های جدید و وصول واقعی بر مبنای تاریخ هر رویداد به تفکیک ماه شمسی', 'education', 'graph-up', '#8b5cf6', 'enrollment_trend', permission='registration', filters=('date', 'branch', 'course', 'q'))),
    ('class-capacity', _meta('ظرفیت کلاس‌ها', 'ظرفیت پرشده، خالی و درصد اشغال', 'education', 'easel2', '#0891b2', 'class_capacity', permission='classes', filters=('branch', 'status', 'course', 'teacher', 'q'))),
    ('student-lifecycle', _meta('چرخه وضعیت هنرجویان', 'فعال، فارغ‌التحصیل، انصرافی، تعلیق و انتقال', 'education', 'diagram-3', '#64748b', 'student_lifecycle', permission='students', filters=('date', 'branch', 'status', 'q'))),
    ('attendance', _meta('حضور، غیبت و تأخیر', 'عملکرد حضور کلاس و هنرجو با درصد حضور', 'education', 'clipboard-data', '#0d9488', 'attendance', permission='attendance', filters=('date', 'branch', 'course', 'class', 'teacher', 'student', 'q'))),
    ('teacher-performance', _meta('عملکرد مدرسین', 'کلاس، هنرجو، حضور، ارزیابی و درآمد منتسب', 'performance', 'person-workspace', '#059669', 'teacher_performance', permission='teachers', filters=('date', 'branch', 'teacher', 'course', 'q'))),
    ('exam-results', _meta('آزمون و نتایج', 'نمره، قبولی، مردودی و میانگین آزمون‌ها', 'education', 'journal-check', '#4f46e5', 'exams', permission='exams', filters=('date', 'branch', 'course', 'class', 'student', 'status', 'q'))),
    ('certificates', _meta('گواهینامه‌ها', 'مدارک صادرشده، ابطال و صدور مجدد', 'education', 'award', '#d97706', 'certificates', permission='certificates', filters=('date', 'branch', 'course', 'student', 'status', 'q'))),
    ('course-ranking', _meta('رتبه‌بندی دوره‌ها', 'رتبه‌بندی ثبت‌نام، وصول و حاشیه سود تعهدی دوره', 'performance', 'trophy', '#f59e0b', 'course_profitability', permission='reports', filters=('date', 'branch', 'course', 'q'))),
    ('branch-ranking', _meta('رتبه‌بندی شعب', 'مقایسه هنرجو، ثبت‌نام، درآمد و سود شعب', 'performance', 'buildings', '#0ea5e9', 'branch_profitability', permission='reports', filters=('date', 'branch', 'q'))),
    ('referrals', _meta('منابع جذب و تبلیغات', 'تعداد هنرجو و درآمد منتسب به هر منبع معرفی', 'performance', 'megaphone', '#ec4899', 'referrals', permission='reports', filters=('date', 'branch', 'q'))),
    ('retention-churn', _meta('ماندگاری و ریزش', 'نرخ تکمیل، انصراف و پرونده‌های در معرض ریزش', 'performance', 'person-dash', '#f43f5e', 'churn', permission='reports', filters=('date', 'branch', 'course', 'q'))),
])


# Every cross-module report has one explicit source contract.  Both catalogue
# visibility and scheduled execution use these permissions, while licence
# checks use the corresponding feature list.  Keeping this mapping next to the
# catalogue avoids aggregate reports becoming a side channel into another
# module (for example, accounting cash flow into operational finance data).
COMPOSITE_REPORT_SOURCES: dict[str, tuple[str, ...]] = {
    'cash-flow': ('accounting', 'finance'),
    'receipts-payments': ('finance', 'students', 'registration', 'courses'),
    'payment-methods': ('finance', 'students', 'registration', 'courses'),
    'cancelled-payments': ('finance', 'students', 'registration', 'courses'),
    'budget-actual': ('finance', 'accounting'),
    'course-profitability': ('finance', 'registration', 'courses', 'teachers'),
    'branch-profitability': ('finance', 'registration', 'students'),
    'payroll-summary': ('payroll', 'teachers'),
    'payroll-tax': ('tax', 'payroll', 'teachers'),
    'tax-control-summary': ('tax', 'finance', 'payroll', 'teachers'),
    'statutory-accounts': ('tax', 'accounting'),
    'checks-all': ('finance', 'students'),
    'checks-received': ('finance', 'students'),
    'checks-issued': ('finance', 'students'),
    'checks-due': ('finance', 'students'),
    'checks-bounced': ('finance', 'students'),
    'receivables-aging': ('finance', 'registration', 'students', 'courses'),
    'debtors': ('finance', 'registration', 'students', 'courses'),
    'installments-overdue': ('finance', 'registration', 'students', 'courses'),
    'installments-upcoming': ('finance', 'registration', 'students', 'courses'),
    'installment-calendar': ('finance', 'registration', 'students', 'courses'),
    'discounts': ('finance', 'registration', 'students', 'courses'),
    'students': ('students', 'registration'),
    'enrollments': ('registration', 'students', 'courses', 'classes', 'teachers'),
    'enrollment-trend': (
        'registration', 'students', 'courses', 'classes', 'teachers', 'finance',
    ),
    'class-capacity': ('classes', 'registration', 'courses', 'teachers'),
    'student-lifecycle': ('students', 'registration'),
    'attendance': ('attendance', 'classes', 'courses', 'teachers', 'students'),
    'teacher-performance': (
        'teachers', 'classes', 'courses', 'registration', 'finance', 'attendance',
    ),
    'exam-results': ('exams', 'courses', 'classes', 'students'),
    'certificates': ('certificates', 'students', 'courses'),
    'course-ranking': ('finance', 'registration', 'courses'),
    'branch-ranking': ('finance', 'registration', 'students'),
    'referrals': ('students', 'finance'),
    'retention-churn': ('registration', 'courses'),
}
_REPORT_LICENSE_FEATURE_EXTRAS: dict[str, tuple[str, ...]] = {
    'receivables-aging': ('installments',),
    'debtors': ('installments',),
    'installments-overdue': ('installments',),
    'installments-upcoming': ('installments',),
    'installment-calendar': ('installments',),
}
for _report_key, _source_modules in COMPOSITE_REPORT_SOURCES.items():
    REPORT_CATALOG[_report_key]['source_permissions'] = list(_source_modules)
    REPORT_CATALOG[_report_key]['license_features'] = list(dict.fromkeys(
        _source_modules + _REPORT_LICENSE_FEATURE_EXTRAS.get(_report_key, ())
    ))


@dataclass
class ReportFilters:
    date_from: date | None = None
    date_to: date | None = None
    branch_id: int | None = None
    course_id: int | None = None
    class_id: int | None = None
    teacher_id: int | None = None
    student_id: int | None = None
    account_id: int | None = None
    fiscal_id: int | None = None
    status: str = ''
    q: str = ''
    sort: str = ''
    direction: str = 'desc'
    page: int = 1
    per_page: int = 25
    compare: str = ''
    forced_branch_id: int | None = None
    # None means an internal/admin calculation; a concrete set is attached to
    # non-admin HTTP/scheduled users and controls optional cross-module links.
    visible_modules: frozenset[str] | None = None

    @classmethod
    def from_mapping(cls, values: Mapping[str, Any], user=None) -> 'ReportFilters':
        def integer(name: str, default=None):
            raw = values.get(name, default)
            try:
                return int(raw) if raw not in (None, '') else default
            except (TypeError, ValueError):
                return default

        start = parse_jalali_date(values.get('date_from')) if values.get('date_from') else None
        end = parse_jalali_date(values.get('date_to')) if values.get('date_to') else None
        if start and end and start > end:
            start, end = end, start
        forced_branch = None
        visible_modules = None
        if user is not None and not getattr(user, 'is_admin', False):
            forced_branch = getattr(user, 'branch_id', None)
            checker = getattr(user, 'has_permission', None)
            modules = (
                'accounting', 'finance', 'students', 'registration', 'courses',
                'classes', 'teachers', 'exams', 'certificates',
            )
            visible_modules = frozenset(
                module for module in modules
                if callable(checker) and checker(module, 'view')
            )
        branch = forced_branch or integer('branch_id')
        return cls(
            date_from=start,
            date_to=end,
            branch_id=branch,
            course_id=integer('course_id'),
            class_id=integer('class_id'),
            teacher_id=integer('teacher_id'),
            student_id=integer('student_id'),
            account_id=integer('account_id'),
            fiscal_id=integer('fiscal_id'),
            status=str(values.get('status') or '').strip()[:30],
            q=str(values.get('q') or '').strip()[:200],
            sort=str(values.get('sort') or '').strip()[:80],
            direction='asc' if values.get('direction') == 'asc' else 'desc',
            page=max(1, integer('page', 1) or 1),
            per_page=max(10, min(integer('per_page', 25) or 25, 200)),
            compare=(str(values.get('compare') or '').strip()
                     if str(values.get('compare') or '').strip() in ('previous', 'year') else ''),
            forced_branch_id=forced_branch,
            visible_modules=visible_modules,
        )

    def as_query_dict(self, include_paging: bool = True) -> dict[str, str]:
        data: dict[str, Any] = {
            'date_from': gregorian_to_jalali(self.date_from) if self.date_from else '',
            'date_to': gregorian_to_jalali(self.date_to) if self.date_to else '',
            'branch_id': self.branch_id or '', 'course_id': self.course_id or '',
            'class_id': self.class_id or '', 'teacher_id': self.teacher_id or '',
            'student_id': self.student_id or '', 'account_id': self.account_id or '',
            'fiscal_id': self.fiscal_id or '', 'status': self.status, 'q': self.q,
            'sort': self.sort, 'direction': self.direction, 'compare': self.compare,
            'per_page': self.per_page,
        }
        if include_paging:
            data['page'] = self.page
        # Empty date bounds are meaningful: they represent an explicitly
        # open-ended report.  Keeping them in pagination/export/preset URLs
        # prevents a later request from silently restoring the default year.
        return {
            key: str(value) for key, value in data.items()
            if key in ('date_from', 'date_to') or value not in ('', None)
        }

    def serialisable(self) -> dict[str, Any]:
        data = self.as_query_dict(include_paging=False)
        # Pin automation/presets to the non-admin user's authorised branch.
        if self.forced_branch_id:
            data['branch_id'] = str(self.forced_branch_id)
        return data


def normalise_text(value: Any) -> str:
    text = unicodedata.normalize('NFKC', str(value or '')).translate(FA_DIGITS).strip().lower()
    text = (text.replace('ي', 'ی').replace('ى', 'ی').replace('ك', 'ک')
            .replace('\u200c', ' ').replace('ۀ', 'ه').replace('ة', 'ه')
            .replace(',', '').replace('٬', '').replace('٫', '.'))
    return re.sub(r'\s+', ' ', text)


def money(value: Any) -> Decimal:
    try:
        number = Decimal(str(value or 0))
        return number.quantize(Decimal('0.01')) if number.is_finite() else Decimal('0.00')
    except (InvalidOperation, ValueError, TypeError):
        return Decimal('0.00')


def _registration_paid_as_of(registrations: Iterable[Any], as_of: date) -> dict[int, Decimal]:
    """Reconstruct collections per registration at a historical cut-off.

    ``Registration.paid_amount`` is a denormalised current value.  Confirmed
    payment rows provide dates; any legacy amount not represented by those rows
    is retained as an opening collection so old installations remain balanced.
    """
    from models.finance import Payment

    registrations = list(registrations)
    registration_ids = [item.id for item in registrations]
    tracked_total = defaultdict(Decimal)
    paid_to_date = defaultdict(Decimal)
    for offset in range(0, len(registration_ids), 900):
        payments = Payment.query.filter(
            Payment.registration_id.in_(registration_ids[offset:offset + 900]),
            Payment.status == 'confirmed',
        ).all()
        for payment in payments:
            amount = money(payment.amount)
            tracked_total[payment.registration_id] += amount
            if payment.payment_date is None or payment.payment_date <= as_of:
                paid_to_date[payment.registration_id] += amount

    result = {}
    for registration in registrations:
        legacy_opening = max(
            money(registration.paid_amount) - tracked_total[registration.id],
            Decimal(0),
        )
        result[registration.id] = legacy_opening + paid_to_date[registration.id]
    return result


def _col(key: str, label: str, kind: str = 'text', *, link: bool = False) -> dict:
    return {'key': key, 'label': label, 'type': kind, 'link': link}


def _kpi(label: str, value: Any, kind: str = 'number', color: str = 'primary',
         icon: str = 'bar-chart') -> dict:
    return {'label': label, 'value': value, 'type': kind, 'color': color, 'icon': icon}


def _result(columns: list[dict], rows: list[dict], *, kpis: list[dict] | None = None,
            chart: dict | None = None, warnings: list[str] | None = None,
            footers: Mapping[str, Any] | None = None) -> dict:
    return {
        'columns': columns, 'rows': rows, 'kpis': kpis or [], 'chart': chart,
        'warnings': warnings or [], 'footers': dict(footers or {}),
    }


def _date_ok(value: date | datetime | None, filters: ReportFilters) -> bool:
    if value is None:
        return not (filters.date_from or filters.date_to)
    current = value.date() if isinstance(value, datetime) else value
    return ((not filters.date_from or current >= filters.date_from) and
            (not filters.date_to or current <= filters.date_to))


def _branch_ok(value: int | None, filters: ReportFilters) -> bool:
    return not filters.branch_id or value == filters.branch_id


def _can_drill_down(filters: ReportFilters, module: str) -> bool:
    """Return whether a row may link into another operational module."""
    return filters.visible_modules is None or module in filters.visible_modules


def _query_range(query, column, filters: ReportFilters):
    """Push an inclusive day range into SQL for both Date and DateTime columns."""
    is_datetime = isinstance(getattr(column, 'type', None), SADateTime)
    if filters.date_from:
        lower = (datetime.combine(filters.date_from, time.min)
                 if is_datetime else filters.date_from)
        query = query.filter(column >= lower)
    if filters.date_to:
        if is_datetime:
            # A strict next-midnight bound includes every timestamp on date_to,
            # including values with microseconds.
            upper = datetime.combine(filters.date_to + timedelta(days=1), time.min)
            query = query.filter(column < upper)
        else:
            query = query.filter(column <= filters.date_to)
    return query


def _query_branch(query, column, filters: ReportFilters):
    return query.filter(column == filters.branch_id) if filters.branch_id else query


def _status_label(value: Any) -> str:
    return STATUS_LABELS.get(value, str(value or 'نامشخص'))


def _jalali_month(value: date | datetime | None) -> tuple[str, str]:
    if not value:
        return ('نامشخص', 'نامشخص')
    obj = gregorian_to_jalali_obj(value)
    if not obj:
        return ('نامشخص', 'نامشخص')
    key = f'{obj.year}/{obj.month:02d}'
    return key, f'{jalali_month_name(obj.month)} {obj.year}'


def _previous_jalali_year(value: date) -> date:
    """Return the matching day last Jalali year, clamped at Esfand's end."""
    import jdatetime
    current = jdatetime.date.fromgregorian(date=value)
    day = current.day
    while day:
        try:
            return jdatetime.date(current.year - 1, current.month, day).togregorian()
        except ValueError:
            day -= 1
    return value - timedelta(days=365)


def _previous_jalali_month(value: date) -> date:
    """Return the matching day in the prior Jalali month, clamped at month end."""
    import jdatetime
    current = jdatetime.date.fromgregorian(date=value)
    year, month = current.year, current.month - 1
    if month == 0:
        year, month = year - 1, 12
    day = current.day
    while day:
        try:
            return jdatetime.date(year, month, day).togregorian()
        except ValueError:
            day -= 1
    return value - timedelta(days=30)


def _chart(labels: list, datasets: list[dict], chart_type: str = 'bar') -> dict:
    return {'type': chart_type, 'labels': labels, 'datasets': datasets}


def _valid_entries(filters: ReportFilters, *, include_before_start: bool = False):
    from models.accounting import JournalEntry

    query = JournalEntry.query.filter(JournalEntry.status.in_(['confirmed', 'approved']))
    if filters.date_to:
        query = query.filter(JournalEntry.entry_date <= filters.date_to)
    if filters.date_from and not include_before_start:
        query = query.filter(JournalEntry.entry_date >= filters.date_from)
    if filters.branch_id:
        query = query.filter(JournalEntry.branch_id == filters.branch_id)
    if filters.fiscal_id:
        query = query.filter(JournalEntry.fiscal_period_id == filters.fiscal_id)
    return query


def _entry_items(filters: ReportFilters, *, cumulative: bool = False):
    from models.accounting import JournalEntry, JournalItem

    query = (JournalItem.query.join(JournalEntry)
             .options(joinedload(JournalItem.account),
                      joinedload(JournalItem.sub_account),
                      joinedload(JournalItem.detail_account),
                      joinedload(JournalItem.entry))
             .filter(JournalEntry.status.in_(['confirmed', 'approved'])))
    if filters.date_to:
        query = query.filter(JournalEntry.entry_date <= filters.date_to)
    if filters.date_from and not cumulative:
        query = query.filter(JournalEntry.entry_date >= filters.date_from)
    if filters.branch_id:
        query = query.filter(JournalEntry.branch_id == filters.branch_id)
    if filters.fiscal_id:
        query = query.filter(JournalEntry.fiscal_period_id == filters.fiscal_id)
    if filters.account_id:
        query = query.filter(JournalItem.account_id == filters.account_id)
    return query.all()


def _journal(filters: ReportFilters, variant=None) -> dict:
    from models.accounting import JournalEntry

    query = JournalEntry.query.options(joinedload(JournalEntry.branch), joinedload(JournalEntry.fiscal_period))
    if filters.date_from:
        query = query.filter(JournalEntry.entry_date >= filters.date_from)
    if filters.date_to:
        query = query.filter(JournalEntry.entry_date <= filters.date_to)
    if filters.branch_id:
        query = query.filter(JournalEntry.branch_id == filters.branch_id)
    if filters.fiscal_id:
        query = query.filter(JournalEntry.fiscal_period_id == filters.fiscal_id)
    if variant == 'draft':
        query = query.filter(JournalEntry.status.in_(['draft', 'confirmed']))
    elif variant == 'changed':
        query = query.filter(db.or_(JournalEntry.status == 'cancelled', JournalEntry.is_adjusted.is_(True)))
    elif filters.status:
        query = query.filter(JournalEntry.status == filters.status)
    entries = query.order_by(JournalEntry.entry_date.desc(), JournalEntry.entry_number.desc()).all()
    rows = []
    for entry in entries:
        debit = money(entry.total_debit)
        credit = money(entry.total_credit)
        difference = debit - credit
        if variant == 'unbalanced' and abs(difference) < Decimal('0.01'):
            continue
        rows.append({
            'number': entry.entry_number,
            'date': entry.entry_date,
            'type': entry.entry_type or '-',
            'description': entry.description or '-',
            'branch': entry.branch.name if entry.branch else '-',
            'fiscal': entry.fiscal_period.name if entry.fiscal_period else '-',
            'debit': debit, 'credit': credit, 'difference': difference,
            'status': _status_label(entry.status),
            'change_reason': entry.cancel_reason or entry.adjustment_reason or '-',
            'number_url': (url_for('accounting.view_entry', id=entry.id)
                           if _can_drill_down(filters, 'accounting') else None),
        })
    columns = [
        _col('number', 'شماره سند', link=True), _col('date', 'تاریخ', 'date'),
        _col('description', 'شرح'), _col('type', 'نوع'), _col('branch', 'شعبه'),
        _col('debit', 'بدهکار', 'money'), _col('credit', 'بستانکار', 'money'),
        _col('difference', 'اختلاف', 'money'), _col('status', 'وضعیت', 'status'),
    ]
    if variant == 'changed':
        columns.append(_col('change_reason', 'دلیل اصلاح/ابطال'))
    total_debit = sum((r['debit'] for r in rows), Decimal(0))
    total_credit = sum((r['credit'] for r in rows), Decimal(0))
    return _result(columns, rows, kpis=[
        _kpi('تعداد اسناد', len(rows), icon='journal-text'),
        _kpi('جمع بدهکار', total_debit, 'money', 'info', 'arrow-down-circle'),
        _kpi('جمع بستانکار', total_credit, 'money', 'success', 'arrow-up-circle'),
        _kpi('اختلاف', total_debit - total_credit, 'money', 'danger', 'exclamation-triangle'),
    ], footers={'debit': total_debit, 'credit': total_credit, 'difference': total_debit - total_credit})


def _ledger(filters: ReportFilters, level='account') -> dict:
    items = _entry_items(filters, cumulative=True)
    grouped: dict[Any, dict] = {}
    for item in items:
        entry_date = item.entry.entry_date
        is_opening = bool(filters.date_from and entry_date < filters.date_from)
        if level == 'sub':
            obj = item.sub_account
            key = ('sub', item.sub_account_id or 0, item.account_id)
            code = obj.code if obj else 'بدون معین'
            name = obj.name if obj else f'بدون معین - {item.account.name}'
        elif level == 'detail':
            obj = item.detail_account
            key = ('detail', item.detail_account_id or 0, item.sub_account_id or 0, item.account_id)
            code = obj.code if obj else 'بدون تفصیلی'
            name = obj.name if obj else f'بدون تفصیلی - {item.account.name}'
        else:
            obj = item.account
            key = ('account', item.account_id)
            code = obj.code
            name = obj.name
        account_type = (item.account.account_type or
                        (item.account.group.account_type if item.account.group else ''))
        row = grouped.setdefault(key, {
            'code': code, 'name': name, 'account': item.account.name,
            'account_id': item.account_id,
            'type': ACCOUNT_TYPE_LABELS.get(account_type, account_type or '-'),
            'opening_debit': Decimal(0), 'opening_credit': Decimal(0),
            'period_debit': Decimal(0), 'period_credit': Decimal(0),
        })
        debit, credit = money(item.debit), money(item.credit)
        if is_opening:
            row['opening_debit'] += debit
            row['opening_credit'] += credit
        elif _date_ok(entry_date, filters):
            row['period_debit'] += debit
            row['period_credit'] += credit
    rows = []
    for row in grouped.values():
        opening_net = row['opening_debit'] - row['opening_credit']
        period_net = row['period_debit'] - row['period_credit']
        ending_net = opening_net + period_net
        row.update({
            'opening': opening_net,
            'code_url': (url_for('accounting.account_ledger', account_id=row['account_id'])
                         if _can_drill_down(filters, 'accounting') else None),
            # Opening columns show the net brought-forward balance, not all
            # historical turnover before the selected period.
            'opening_debit': max(opening_net, Decimal(0)),
            'opening_credit': max(-opening_net, Decimal(0)),
            'debit': row['period_debit'], 'credit': row['period_credit'],
            'balance': ending_net,
            'balance_debit': max(ending_net, Decimal(0)),
            'balance_credit': max(-ending_net, Decimal(0)),
        })
        rows.append(row)
    rows.sort(key=lambda row: normalise_text(row['code']))
    total_debit = sum((r['debit'] for r in rows), Decimal(0))
    total_credit = sum((r['credit'] for r in rows), Decimal(0))
    return _result([
        _col('code', 'کد حساب', link=True), _col('name', 'عنوان حساب'), _col('account', 'حساب کل'),
        _col('type', 'ماهیت گروه'), _col('opening', 'مانده اول دوره', 'money'),
        _col('debit', 'گردش بدهکار', 'money'), _col('credit', 'گردش بستانکار', 'money'),
        _col('balance_debit', 'مانده بدهکار', 'money'), _col('balance_credit', 'مانده بستانکار', 'money'),
    ], rows, kpis=[
        _kpi('تعداد حساب', len(rows), icon='diagram-3'),
        _kpi('گردش بدهکار', total_debit, 'money', 'info', 'arrow-down'),
        _kpi('گردش بستانکار', total_credit, 'money', 'success', 'arrow-up'),
        _kpi('اختلاف گردش', total_debit-total_credit, 'money', 'danger', 'exclamation-circle'),
    ], footers={'debit': total_debit, 'credit': total_credit,
                'balance_debit': sum((r['balance_debit'] for r in rows), Decimal(0)),
                'balance_credit': sum((r['balance_credit'] for r in rows), Decimal(0))})


def _trial_balance(filters: ReportFilters, variant=4) -> dict:
    base = _ledger(filters, 'account')
    available = {col['key']: col for col in base['columns']}
    if variant == 2:
        keys = ['code', 'name', 'balance_debit', 'balance_credit']
    elif variant == 4:
        keys = ['code', 'name', 'debit', 'credit', 'balance_debit', 'balance_credit']
    elif variant == 6:
        keys = ['code', 'name', 'opening_debit', 'opening_credit', 'debit', 'credit', 'balance_debit', 'balance_credit']
        available['opening_debit'] = _col('opening_debit', 'اول دوره بدهکار', 'money')
        available['opening_credit'] = _col('opening_credit', 'اول دوره بستانکار', 'money')
    else:
        keys = ['code', 'name', 'opening_debit', 'opening_credit', 'debit', 'credit', 'cumulative_debit', 'cumulative_credit', 'balance_debit', 'balance_credit']
        available['opening_debit'] = _col('opening_debit', 'اول دوره بدهکار', 'money')
        available['opening_credit'] = _col('opening_credit', 'اول دوره بستانکار', 'money')
        available['cumulative_debit'] = _col('cumulative_debit', 'تجمعی بدهکار', 'money')
        available['cumulative_credit'] = _col('cumulative_credit', 'تجمعی بستانکار', 'money')
        for row in base['rows']:
            row['cumulative_debit'] = row['opening_debit'] + row['debit']
            row['cumulative_credit'] = row['opening_credit'] + row['credit']
    base['columns'] = [available[k] for k in keys]
    base['footers'] = {k: sum((money(row.get(k)) for row in base['rows']), Decimal(0))
                       for k in keys if k not in ('code', 'name')}
    return base


def _balance_sheet(filters: ReportFilters) -> dict:
    items = _entry_items(filters, cumulative=True)
    grouped = defaultdict(lambda: {'debit': Decimal(0), 'credit': Decimal(0), 'account': None})
    # A balance sheet is cumulative; date_from is intentionally ignored by
    # _entry_items while date_to remains the as-of date.
    for item in items:
        data = grouped[item.account_id]
        data['account'] = item.account
        data['debit'] += money(item.debit)
        data['credit'] += money(item.credit)
    rows = []
    category_totals = defaultdict(Decimal)
    current_result = Decimal(0)
    for data in grouped.values():
        account = data['account']
        kind = account.account_type or (account.group.account_type if account.group else '')
        raw = data['debit'] - data['credit']
        if kind == 'revenue':
            current_result += -raw
            continue
        if kind == 'expense':
            current_result -= raw
            continue
        if kind not in ('asset', 'liability', 'equity'):
            continue
        amount = raw if kind == 'asset' else -raw
        category_totals[kind] += amount
        rows.append({'section': ACCOUNT_TYPE_LABELS.get(kind, kind), 'code': account.code,
                     'name': account.name, 'amount': amount,
                     'code_url': (url_for('accounting.account_ledger', account_id=account.id)
                                  if _can_drill_down(filters, 'accounting') else None)})
    if current_result:
        category_totals['equity'] += current_result
        rows.append({'section': ACCOUNT_TYPE_LABELS['equity'], 'code': '—',
                     'name': 'سود (زیان) جاری تا تاریخ گزارش', 'amount': current_result})
    rows.sort(key=lambda r: (r['section'], normalise_text(r['code'])))
    assets = category_totals['asset']
    claims = category_totals['liability'] + category_totals['equity']
    return _result([
        _col('section', 'گروه'), _col('code', 'کد', link=True), _col('name', 'عنوان حساب'),
        _col('amount', 'مانده', 'money')
    ], rows, kpis=[
        _kpi('جمع دارایی', assets, 'money', 'primary', 'wallet2'),
        _kpi('جمع بدهی', category_totals['liability'], 'money', 'danger', 'credit-card'),
        _kpi('حقوق مالکانه', category_totals['equity'], 'money', 'info', 'pie-chart'),
        _kpi('اختلاف ترازنامه', assets-claims, 'money', 'warning', 'scale'),
    ], footers={'amount': sum((r['amount'] for r in rows), Decimal(0))},
       warnings=[] if abs(assets-claims) < Decimal('0.01') else ['ترازنامه متوازن نیست؛ اسناد افتتاحیه یا کدینگ حساب‌ها را بررسی کنید.'])


def _profit_loss(filters: ReportFilters) -> dict:
    items = _entry_items(filters, cumulative=False)
    grouped = defaultdict(lambda: {'debit': Decimal(0), 'credit': Decimal(0), 'account': None})
    for item in items:
        data = grouped[item.account_id]
        data['account'] = item.account
        data['debit'] += money(item.debit)
        data['credit'] += money(item.credit)
    rows, income, expense = [], Decimal(0), Decimal(0)
    for data in grouped.values():
        account = data['account']
        kind = account.account_type or (account.group.account_type if account.group else '')
        if kind == 'revenue':
            amount = data['credit'] - data['debit']; income += amount
        elif kind == 'expense':
            amount = data['debit'] - data['credit']; expense += amount
        else:
            continue
        rows.append({'section': ACCOUNT_TYPE_LABELS[kind], 'code': account.code,
                     'name': account.name, 'amount': amount,
                     'code_url': (url_for('accounting.account_ledger', account_id=account.id)
                                  if _can_drill_down(filters, 'accounting') else None)})
    rows.sort(key=lambda r: (r['section'], normalise_text(r['code'])))
    profit = income - expense
    chart = _chart(['درآمد', 'هزینه', 'سود خالص'], [{
        'label': 'مبلغ', 'data': [float(income), float(expense), float(profit)],
        'backgroundColor': ['#16a34a', '#dc2626', '#2563eb' if profit >= 0 else '#f97316']
    }])
    return _result([_col('section', 'بخش'), _col('code', 'کد', link=True), _col('name', 'سرفصل'), _col('amount', 'مبلغ', 'money')], rows,
        kpis=[_kpi('درآمد عملیاتی', income, 'money', 'success', 'graph-up-arrow'),
              _kpi('هزینه عملیاتی', expense, 'money', 'danger', 'graph-down-arrow'),
              _kpi('سود/زیان خالص', profit, 'money', 'primary' if profit >= 0 else 'warning', 'cash-coin'),
              _kpi('حاشیه سود', (profit / income * 100) if income else 0, 'percent', 'info', 'percent')],
        chart=chart, footers={'amount': income + expense})


def _cash_flow(filters: ReportFilters) -> dict:
    from models.finance import Expense, Payment

    incoming = defaultdict(Decimal); outgoing = defaultdict(Decimal)
    payment_query = _query_branch(_query_range(
        Payment.query.filter_by(status='confirmed'), Payment.payment_date, filters
    ), Payment.branch_id, filters)
    for obj in payment_query.all():
        incoming[_jalali_month(obj.payment_date)] += money(obj.amount)
    expense_query = _query_branch(_query_range(
        Expense.query.filter_by(status='confirmed'), Expense.expense_date, filters
    ), Expense.branch_id, filters)
    for obj in expense_query.all():
        outgoing[_jalali_month(obj.expense_date)] += money(obj.amount)
    keys = sorted(set(incoming) | set(outgoing), key=lambda x: x[0])
    rows = [{'month': label, 'income': incoming[key], 'expense': outgoing[key],
             'net': incoming[key]-outgoing[key]} for key, label in keys]
    total_in = sum(incoming.values(), Decimal(0)); total_out = sum(outgoing.values(), Decimal(0))
    return _result([_col('month', 'ماه شمسی'), _col('income', 'ورودی', 'money'),
                    _col('expense', 'خروجی', 'money'), _col('net', 'جریان خالص', 'money')], rows,
        kpis=[_kpi('کل ورودی نقد', total_in, 'money', 'success', 'arrow-down-left-circle'),
              _kpi('کل خروجی نقد', total_out, 'money', 'danger', 'arrow-up-right-circle'),
              _kpi('جریان نقد خالص', total_in-total_out, 'money', 'primary', 'water'),
              _kpi('ماه‌های گزارش', len(rows), icon='calendar3')],
        chart=_chart([r['month'] for r in rows], [
            {'label': 'ورودی', 'data': [float(r['income']) for r in rows], 'borderColor': '#16a34a', 'backgroundColor': 'rgba(22,163,74,.12)'},
            {'label': 'خروجی', 'data': [float(r['expense']) for r in rows], 'borderColor': '#dc2626', 'backgroundColor': 'rgba(220,38,38,.10)'},
            {'label': 'خالص', 'data': [float(r['net']) for r in rows], 'borderColor': '#2563eb', 'backgroundColor': 'rgba(37,99,235,.10)'}
        ], 'line'), footers={'income': total_in, 'expense': total_out, 'net': total_in-total_out})


def _equity(filters: ReportFilters) -> dict:
    base = _ledger(filters, 'account')
    rows = [row for row in base['rows'] if row.get('type') == ACCOUNT_TYPE_LABELS['equity']]
    base['rows'] = rows
    base['kpis'] = [_kpi('حساب‌های حقوق مالکانه', len(rows), icon='pie-chart'),
                    _kpi('مانده خالص', sum((money(r['balance']) for r in rows), Decimal(0)), 'money', 'primary', 'cash-stack')]
    base['footers'] = {
        key: sum((money(row.get(key)) for row in rows), Decimal(0))
        for key in ('debit', 'credit', 'balance_debit', 'balance_credit')
    }
    return base


def _sequence(filters: ReportFilters) -> dict:
    from models.accounting import JournalEntry

    query = _query_branch(_query_range(JournalEntry.query, JournalEntry.entry_date, filters),
                          JournalEntry.branch_id, filters)
    if filters.fiscal_id:
        query = query.filter(JournalEntry.fiscal_period_id == filters.fiscal_id)
    entries = query.order_by(JournalEntry.id).all()
    series = defaultdict(list)
    for entry in entries:
        match = re.search(r'^(.*?)(\d+)$', entry.entry_number or '')
        if match:
            prefix = match.group(1).strip('-_/ ') or 'بدون پیشوند'
            series[prefix].append((int(match.group(2)), entry))

    rows=[]; truncated=False; numbered=0
    for prefix, parsed in sorted(series.items(), key=lambda item: normalise_text(item[0])):
        parsed.sort(key=lambda item: (item[0], item[1].id)); previous=None
        numbered += len(parsed)
        for number, entry in parsed:
            if previous is not None and number > previous + 1:
                gap_end=min(number, previous+101)
                for missing in range(previous+1,gap_end):
                    rows.append({'series':prefix,'number':missing,'issue':'شماره مفقود','date':None,
                                 'document':'-','status':'نیازمند بررسی'})
                if number-previous>101: truncated=True
            duplicate = previous == number
            rows.append({'series':prefix,'number':number,
                         'issue':'شماره تکراری' if duplicate else 'ثبت‌شده',
                         'date':entry.entry_date,'document':entry.entry_number,
                         'status':'نیازمند بررسی' if duplicate else _status_label(entry.status),
                         'document_url':(url_for('accounting.view_entry',id=entry.id)
                                         if _can_drill_down(filters, 'accounting') else None)})
            previous=number
    missing_count=sum(row['issue']=='شماره مفقود' for row in rows)
    duplicate_count=sum(row['issue']=='شماره تکراری' for row in rows)
    warnings=[]
    if truncated: warnings.append('برای جلوگیری از خروجی بسیار بزرگ، هر فاصله حداکثر تا ۱۰۰ شماره نمایش داده شده است.')
    return _result([_col('series','سری سند'),_col('number','شماره ترتیبی'),_col('issue','کنترل'),
                    _col('document','شماره سند',link=True),_col('date','تاریخ','date'),
                    _col('status','وضعیت','status')],rows,
        kpis=[_kpi('اسناد شماره‌دار',numbered,icon='journal'),
              _kpi('شماره مفقود',missing_count,color='danger',icon='exclamation-triangle'),
              _kpi('شماره تکراری',duplicate_count,color='warning',icon='files'),
              _kpi('سری شماره‌گذاری',len(series),icon='sort-numeric-down')],warnings=warnings)


def _fiscal(filters: ReportFilters) -> dict:
    from models.accounting import FiscalPeriod, JournalEntry

    rows = []
    period_query = FiscalPeriod.query
    if filters.fiscal_id:
        period_query = period_query.filter(FiscalPeriod.id == filters.fiscal_id)
    for period in period_query.order_by(FiscalPeriod.start_date.desc()).all():
        entries = JournalEntry.query.filter_by(fiscal_period_id=period.id)
        if filters.branch_id:
            entries = entries.filter(JournalEntry.branch_id == filters.branch_id)
        draft = entries.filter(JournalEntry.status.in_(['draft', 'confirmed'])).count()
        unbalanced = entries.filter(db.func.abs(
            db.func.coalesce(JournalEntry.total_debit, 0) -
            db.func.coalesce(JournalEntry.total_credit, 0)
        ) > .009).count()
        rows.append({'name': period.name, 'start': period.start_date, 'end': period.end_date,
                     'documents': entries.count(), 'pending': draft, 'unbalanced': unbalanced,
                     'closed': 'بسته' if period.is_closed else 'باز', 'closed_at': period.closed_at})
    return _result([_col('name', 'دوره مالی'), _col('start', 'شروع', 'date'), _col('end', 'پایان', 'date'),
                    _col('documents', 'تعداد سند', 'number'), _col('pending', 'تأییدنشده', 'number'),
                    _col('unbalanced', 'نامتوازن', 'number'), _col('closed', 'وضعیت', 'status'),
                    _col('closed_at', 'زمان بستن', 'datetime')], rows,
        kpis=[_kpi('دوره‌ها', len(rows), icon='calendar-range'),
              _kpi('دوره باز', sum(r['closed']=='باز' for r in rows), color='warning', icon='unlock'),
              _kpi('اسناد تأییدنشده', sum(r['pending'] for r in rows), color='danger', icon='hourglass'),
              _kpi('اسناد نامتوازن', sum(r['unbalanced'] for r in rows), color='danger', icon='exclamation-octagon')])


def _payments(filters: ReportFilters, variant=None) -> dict:
    from models.finance import Payment
    from models.registration import Registration

    query = Payment.query.options(
        joinedload(Payment.student),
        joinedload(Payment.registration).joinedload(Registration.course),
        joinedload(Payment.branch),
    )
    query = _query_branch(_query_range(query, Payment.payment_date, filters), Payment.branch_id, filters)
    if variant == 'cancelled': query = query.filter(Payment.status == 'cancelled')
    if filters.status: query = query.filter(Payment.status == filters.status)
    if filters.student_id: query = query.filter(Payment.student_id == filters.student_id)
    if filters.course_id:
        query = query.filter(Payment.registration.has(
            Registration.course_id == filters.course_id))
    payments = query.order_by(Payment.payment_date.desc(), Payment.id.desc()).all()
    rows = []
    for p in payments:
        rows.append({'receipt': p.receipt_no, 'date': p.payment_date,
                     'student': p.student.full_name if p.student else '-',
                     'student_code': p.student.student_code if p.student else '-',
                     'course': p.registration.course.title if p.registration and p.registration.course else '-',
                     'amount': money(p.amount),
                     'method': PAYMENT_METHOD_LABELS.get(p.payment_method, p.payment_method or '-'),
                     'tracking': p.tracking_number or p.transaction_id or '-',
                     'branch': p.branch.name if p.branch else '-', 'status': _status_label(p.status),
                     'receipt_url': (url_for('finance.view_payment', id=p.id)
                                     if _can_drill_down(filters, 'finance') else None),
                     'student_url': (url_for('students.view', id=p.student_id)
                                     if p.student_id and _can_drill_down(filters, 'students') else None)})
    total = sum((r['amount'] for r in rows), Decimal(0))
    confirmed = sum((r['amount'] for r in rows if r['status']==_status_label('confirmed')), Decimal(0))
    return _result([_col('receipt', 'شماره رسید', link=True), _col('date', 'تاریخ', 'date'),
                    _col('student', 'هنرجو', link=True), _col('student_code', 'کد هنرجو'),
                    _col('course', 'دوره'), _col('amount', 'مبلغ', 'money'),
                    _col('method', 'روش'), _col('tracking', 'شماره پیگیری'),
                    _col('branch', 'شعبه'), _col('status', 'وضعیت', 'status')], rows,
        kpis=[_kpi('تعداد رسید', len(rows), icon='receipt'), _kpi('جمع رسیدها', total, 'money', 'success', 'cash'),
              _kpi('وصول قطعی', confirmed, 'money', 'primary', 'check2-circle'),
              _kpi('میانگین پرداخت', total/len(rows) if rows else 0, 'money', 'info', 'calculator')],
        footers={'amount': total})


def _payment_methods(filters: ReportFilters) -> dict:
    # By default, payment-method shares represent realised receipts; users can
    # still explicitly select another status from the report filter.
    base = _payments(filters if filters.status else replace(filters, status='confirmed'))
    grouped = defaultdict(lambda: {'count': 0, 'amount': Decimal(0)})
    for row in base['rows']:
        grouped[row['method']]['count'] += 1; grouped[row['method']]['amount'] += row['amount']
    total = sum((v['amount'] for v in grouped.values()), Decimal(0))
    rows = [{'method': key, 'count': value['count'], 'amount': value['amount'],
             'share': (value['amount']/total*100) if total else 0}
            for key, value in grouped.items()]
    rows.sort(key=lambda r: r['amount'], reverse=True)
    return _result([_col('method', 'روش پرداخت'), _col('count', 'تعداد', 'number'),
                    _col('amount', 'مبلغ', 'money'), _col('share', 'سهم', 'percent')], rows,
        kpis=base['kpis'], chart=_chart([r['method'] for r in rows], [{
            'label': 'مبلغ', 'data': [float(r['amount']) for r in rows],
            'backgroundColor': ['#16a34a','#2563eb','#f59e0b','#8b5cf6','#06b6d4','#64748b'][:len(rows)]
        }], 'doughnut'), footers={'count': sum(r['count'] for r in rows), 'amount': total, 'share': 100 if total else 0})


def _cashbox_transactions(filters: ReportFilters) -> dict:
    from models.finance import Cashbox, CashboxTransaction

    query = (CashboxTransaction.query.join(Cashbox)
             .options(joinedload(CashboxTransaction.cashbox)))
    query = _query_range(query, CashboxTransaction.transaction_date, filters)
    if filters.branch_id:
        query = query.filter(Cashbox.branch_id == filters.branch_id)
    transactions = query.order_by(CashboxTransaction.transaction_date.desc()).all()
    rows = []
    for tx in transactions:
        rows.append({'date': tx.transaction_date, 'cashbox': tx.cashbox.name if tx.cashbox else '-',
                     'type': {'in':'دریافت','out':'پرداخت'}.get(tx.trans_type,tx.trans_type or '-'),
                     'description': tx.description or '-', 'reference': tx.reference_type or '-',
                     'in': money(tx.amount) if tx.trans_type == 'in' else Decimal(0),
                     'out': money(tx.amount) if tx.trans_type == 'out' else Decimal(0),
                     'balance': money(tx.balance_after)})
    incoming = sum((r['in'] for r in rows), Decimal(0)); outgoing = sum((r['out'] for r in rows), Decimal(0))
    return _result([_col('date', 'تاریخ', 'datetime'), _col('cashbox', 'صندوق'), _col('type', 'نوع'),
                    _col('description', 'شرح'), _col('reference', 'منبع'), _col('in', 'ورودی', 'money'),
                    _col('out', 'خروجی', 'money'), _col('balance', 'مانده', 'money')], rows,
        kpis=[_kpi('تراکنش‌ها', len(rows), icon='arrow-left-right'), _kpi('ورودی', incoming, 'money', 'success', 'arrow-down'),
              _kpi('خروجی', outgoing, 'money', 'danger', 'arrow-up'), _kpi('خالص گردش', incoming-outgoing, 'money', 'primary', 'cash-stack')],
        footers={'in': incoming, 'out': outgoing})


def _cashbox_balances(filters: ReportFilters) -> dict:
    from models.finance import Cashbox, CashboxTransaction

    query = Cashbox.query.options(joinedload(Cashbox.branch))
    if filters.branch_id:
        query = query.filter(Cashbox.branch_id == filters.branch_id)
    boxes = query.order_by(Cashbox.name).all()
    box_ids = [box.id for box in boxes]
    counts = {}
    for offset in range(0, len(box_ids), 900):
        counts.update(dict(db.session.query(
            CashboxTransaction.cashbox_id, db.func.count(CashboxTransaction.id)
        ).filter(CashboxTransaction.cashbox_id.in_(box_ids[offset:offset + 900]))
          .group_by(CashboxTransaction.cashbox_id).all()))
    rows = []
    for box in boxes:
        rows.append({'code': box.code or '-', 'name': box.name,
                     'branch': box.branch.name if box.branch else '-',
                     'balance': money(box.balance), 'status': 'فعال' if box.is_active else 'غیرفعال',
                     'transactions': counts.get(box.id, 0)})
    total = sum((r['balance'] for r in rows), Decimal(0))
    return _result([_col('code','کد'), _col('name','صندوق'), _col('branch','شعبه'),
                    _col('transactions','تعداد تراکنش','number'), _col('balance','موجودی','money'),
                    _col('status','وضعیت','status')], rows,
        kpis=[_kpi('تعداد صندوق', len(rows), icon='safe2'), _kpi('صندوق فعال', sum(r['status']=='فعال' for r in rows), color='success', icon='check-circle'),
              _kpi('موجودی کل', total, 'money', 'primary', 'cash-stack'), _kpi('تعداد گردش', sum(r['transactions'] for r in rows), icon='arrow-repeat')], footers={'transactions': sum(r['transactions'] for r in rows), 'balance': total})


def _bank_transactions(filters: ReportFilters, variant=None) -> dict:
    from models.finance import BankAccount, BankTransaction

    query=(BankTransaction.query.join(BankAccount)
           .options(joinedload(BankTransaction.bank_account)))
    query=_query_range(query,BankTransaction.transaction_date,filters)
    if filters.branch_id:
        query=query.filter(db.or_(BankAccount.branch_id==filters.branch_id,BankAccount.branch_id.is_(None)))
    if variant=='transfer': query=query.filter(BankTransaction.trans_type=='transfer')
    rows = []
    for tx in query.order_by(BankTransaction.transaction_date.desc()).all():
        rows.append({'date': tx.transaction_date,
                     'bank': tx.bank_account.bank_name if tx.bank_account else '-',
                     'account': tx.bank_account.account_number if tx.bank_account else '-',
                     'branch': tx.bank_account.branch.name if tx.bank_account and tx.bank_account.branch else 'مشترک',
                     'type': {'deposit':'واریز','withdrawal':'برداشت','transfer':'انتقال'}.get(tx.trans_type, tx.trans_type),
                     'description': tx.description or '-', 'reference': tx.reference_type or '-',
                     'in': money(tx.amount) if tx.trans_type == 'deposit' else Decimal(0),
                     'out': money(tx.amount) if tx.trans_type in ('withdrawal','transfer') else Decimal(0),
                     'balance': money(tx.balance_after)})
    incoming=sum((r['in'] for r in rows),Decimal(0)); outgoing=sum((r['out'] for r in rows),Decimal(0))
    return _result([_col('date','تاریخ','datetime'),_col('bank','بانک'),_col('account','شماره حساب'),
                    _col('branch','شعبه سازمانی'),_col('type','نوع'),_col('description','شرح'),_col('reference','مرجع'),
                    _col('in','واریز','money'),_col('out','برداشت','money'),_col('balance','مانده','money')], rows,
        kpis=[_kpi('تراکنش‌ها',len(rows),icon='bank'),_kpi('واریز',incoming,'money','success','arrow-down'),
              _kpi('برداشت',outgoing,'money','danger','arrow-up'),_kpi('خالص',incoming-outgoing,'money','primary','arrow-left-right')],
        footers={'in':incoming,'out':outgoing})


def _bank_balances(filters: ReportFilters) -> dict:
    from models.finance import BankAccount, BankTransaction

    query=BankAccount.query.options(joinedload(BankAccount.branch))
    if filters.branch_id:
        query=query.filter(db.or_(BankAccount.branch_id==filters.branch_id,BankAccount.branch_id.is_(None)))
    accounts=query.order_by(BankAccount.bank_name).all(); ids=[item.id for item in accounts]; counts={}
    for offset in range(0,len(ids),900):
        counts.update(dict(db.session.query(BankTransaction.bank_account_id,db.func.count(BankTransaction.id))
                           .filter(BankTransaction.bank_account_id.in_(ids[offset:offset+900]))
                           .group_by(BankTransaction.bank_account_id).all()))
    rows=[{'bank':b.bank_name,'account':b.account_number or '-','card':b.card_number or '-',
           'sheba':b.sheba or '-','bank_branch':b.branch_name or '-',
           'branch':b.branch.name if b.branch else 'مشترک','balance':money(b.balance),
           'transactions':counts.get(b.id,0),'status':'فعال' if b.is_active else 'غیرفعال'}
          for b in accounts]
    total=sum((r['balance'] for r in rows),Decimal(0))
    return _result([_col('bank','بانک'),_col('account','شماره حساب'),_col('card','کارت'),_col('sheba','شبا'),
                    _col('bank_branch','شعبه بانک'),_col('branch','شعبه سازمانی'),_col('transactions','گردش','number'),_col('balance','مانده','money'),_col('status','وضعیت','status')],rows,
        kpis=[_kpi('حساب‌ها',len(rows),icon='bank2'),_kpi('حساب فعال',sum(r['status']=='فعال' for r in rows),color='success',icon='check-circle'),
              _kpi('مانده کل بانک',total,'money','primary','cash-stack'),_kpi('تعداد گردش',sum(r['transactions'] for r in rows),icon='arrow-repeat')],
        footers={'transactions':sum(r['transactions'] for r in rows),'balance':total})


def _reconciliation(filters: ReportFilters, variant='cashbox') -> dict:
    from models.reporting import AccountReconciliation

    query=AccountReconciliation.query.filter_by(account_kind=variant)
    query=_query_range(query,AccountReconciliation.reconciliation_date,filters)
    if filters.status: query=query.filter(AccountReconciliation.status==filters.status)
    records=query.order_by(AccountReconciliation.reconciliation_date.desc()).all()
    rows=[]
    for r in records:
        account = r.cashbox if variant == 'cashbox' else r.bank_account
        if filters.branch_id:
            allowed_branches = ((filters.branch_id,) if variant == 'cashbox'
                                else (None, filters.branch_id))
            if account is None or account.branch_id not in allowed_branches:
                continue
        name=(r.cashbox.name if variant=='cashbox' and r.cashbox else
              r.bank_account.bank_name if r.bank_account else '-')
        rows.append({'date':r.reconciliation_date,'account':name,'system':money(r.system_balance),
                     'statement':money(r.statement_balance),'difference':money(r.difference),
                     'status':_status_label(r.status),'notes':r.notes or '-'})
    difference=sum((r['difference'] for r in rows),Decimal(0))
    return _result([_col('date','تاریخ تطبیق','date'),_col('account','حساب'),_col('system','مانده سیستم','money'),
                    _col('statement','مانده واقعی/صورت‌حساب','money'),_col('difference','مغایرت','money'),
                    _col('status','وضعیت','status'),_col('notes','توضیحات')],rows,
        kpis=[_kpi('تطبیق‌ها',len(rows),icon='clipboard-check'),_kpi('باز',sum(r['status']==_status_label('open') for r in rows),color='warning',icon='unlock'),
              _kpi('رفع‌شده',sum(r['status']==_status_label('resolved') for r in rows),color='success',icon='check2-circle'),
              _kpi('خالص مغایرت',difference,'money','danger','exclamation-triangle')],footers={'difference':difference})


def _checks(filters: ReportFilters, variant=None) -> dict:
    from models.finance import Check

    today=local_today(); due_limit=today+timedelta(days=30)
    query=_query_branch(Check.query.options(joinedload(Check.student),joinedload(Check.branch)),Check.branch_id,filters)
    if variant in ('received','issued'): query=query.filter(Check.check_type==variant)
    if variant=='bounced': query=query.filter(Check.status=='bounced')
    if variant=='due':
        query=query.filter(Check.due_date.between(today,due_limit),
                           Check.status.in_(['received','pending']))
    elif variant=='bounced':
        # The meaningful activity date for a returned cheque is its bounce
        # date; legacy records without one fall back to their due date.
        query=_query_range(query,db.func.coalesce(Check.bounced_date,Check.due_date),filters)
    else:
        query=_query_range(query,Check.due_date,filters)
    if filters.status: query=query.filter(Check.status==filters.status)
    if filters.student_id: query=query.filter(Check.student_id==filters.student_id)
    rows=[]
    for ch in query.order_by(Check.due_date).all():
        rows.append({'number':ch.check_number,'type':{'received':'دریافتی','issued':'پرداختی'}.get(ch.check_type,ch.check_type or '-'),
                     'bank':ch.bank_name,'issuer':ch.issuer_name or '-',
                     'student':ch.student.full_name if ch.student else '-', 'amount':money(ch.amount),
                     'issue':ch.issue_date,'due':ch.due_date,'bounced':ch.bounced_date,
                     'days':(ch.due_date-today).days,'status':_status_label(ch.status),
                     'branch':ch.branch.name if ch.branch else '-',
                     'reason':ch.bounced_reason or ch.tracking_notes or '-'})
    total=sum((r['amount'] for r in rows),Decimal(0))
    return _result([_col('number','شماره چک'),_col('type','نوع'),_col('bank','بانک'),_col('issuer','صادرکننده'),
                    _col('student','هنرجو'),_col('amount','مبلغ','money'),_col('issue','تاریخ صدور','date'),
                    _col('due','سررسید','date'),_col('bounced','تاریخ برگشت','date'),
                    _col('days','روز تا سررسید','number'),_col('status','وضعیت','status'),
                    _col('branch','شعبه'),_col('reason','پیگیری/علت')],rows,
        kpis=[_kpi('تعداد چک',len(rows),icon='file-earmark-check'),_kpi('جمع مبلغ',total,'money','primary','cash-stack'),
              _kpi('برگشتی',sum(r['status']==_status_label('bounced') for r in rows),color='danger',icon='exclamation-diamond'),
              _kpi('نزدیک سررسید',sum(0<=r['days']<=30 and r['status'] in
                                      (_status_label('received'), _status_label('pending'))
                                      for r in rows),color='warning',icon='calendar-event')],
        footers={'amount':total})


def _receivables(filters: ReportFilters, variant='detail') -> dict:
    from models.registration import Installment, Registration

    query = Registration.query.options(
        joinedload(Registration.student), joinedload(Registration.course),
        joinedload(Registration.branch),
    ).filter(db.or_(Registration.total_fee > 0, Registration.remaining_amount > 0))
    # Receivables are a balance at one cut-off date.  Fully paid registrations
    # must remain candidates because they may still have been open historically.
    query = _query_branch(query, Registration.branch_id, filters)
    as_of = filters.date_to or local_today()
    query = query.filter(db.or_(
        Registration.registration_date <= as_of,
        Registration.registration_date.is_(None),
    ))
    if filters.course_id:
        query = query.filter(Registration.course_id == filters.course_id)
    if filters.student_id:
        query = query.filter(Registration.student_id == filters.student_id)
    registrations = query.all()
    paid_as_of = _registration_paid_as_of(registrations, as_of)

    grouped_installments = defaultdict(list)
    registration_ids = [registration.id for registration in registrations]
    for offset in range(0, len(registration_ids), 900):
        items = Installment.query.filter(
            Installment.registration_id.in_(registration_ids[offset:offset + 900])
        ).all()
        for item in items:
            paid_before_cutoff = (
                item.status == 'paid' and
                (item.paid_date is None or item.paid_date <= as_of)
            )
            if not paid_before_cutoff:
                grouped_installments[item.registration_id].append(item)

    rows = []
    buckets = defaultdict(Decimal)
    for registration in registrations:
        fee = money(registration.total_fee)
        paid = paid_as_of[registration.id]
        remaining = (max(fee - paid, Decimal(0)) if fee > 0 else
                     max(money(registration.remaining_amount), Decimal(0)))
        if remaining <= 0:
            continue
        unpaid = grouped_installments[registration.id]
        base_date = min(
            (item.due_date for item in unpaid),
            default=registration.registration_date or as_of,
        )
        age = max(0, (as_of - base_date).days)
        bucket = ('سررسیدنشده' if base_date > as_of else
                  'تا ۳۰ روز' if age <= 30 else
                  '۳۱ تا ۶۰ روز' if age <= 60 else
                  '۶۱ تا ۹۰ روز' if age <= 90 else 'بیش از ۹۰ روز')
        buckets[bucket] += remaining
        rows.append({
            'code': registration.reg_code,
            'student': registration.student.full_name if registration.student else '-',
            'mobile': registration.student.mobile if registration.student else '-',
            'course': registration.course.title if registration.course else '-',
            'date': registration.registration_date, 'fee': fee, 'paid': paid,
            'remaining': remaining, 'age': age, 'bucket': bucket,
            'branch': registration.branch.name if registration.branch else '-',
            'code_url': (url_for('registration.view', id=registration.id)
                         if _can_drill_down(filters, 'registration') else None),
            'student_url': (url_for('students.view', id=registration.student_id)
                            if _can_drill_down(filters, 'students') else None),
        })
    total = sum((row['remaining'] for row in rows), Decimal(0))
    rows.sort(key=lambda row: row['remaining'], reverse=True)
    warning = ('مانده در تاریخ مبنا از پرداخت‌های قطعی تاریخ‌دار بازسازی شده است؛ '
               'پرداخت‌های قدیمی فاقد ریزتاریخ به‌عنوان مانده افتتاحیه منظور می‌شوند.')
    if variant == 'aging':
        order = ['سررسیدنشده', 'تا ۳۰ روز', '۳۱ تا ۶۰ روز',
                 '۶۱ تا ۹۰ روز', 'بیش از ۹۰ روز']
        aging_rows = [{
            'bucket': key,
            'accounts': sum(1 for row in rows if row['bucket'] == key),
            'amount': buckets[key],
            'share': buckets[key] / total * 100 if total else 0,
        } for key in order]
        return _result([
            _col('bucket', 'سن مطالبه'), _col('accounts', 'تعداد پرونده', 'number'),
            _col('amount', 'مانده', 'money'), _col('share', 'سهم', 'percent'),
        ], aging_rows, kpis=[
            _kpi('پرونده بدهکار', len(rows), icon='person-exclamation'),
            _kpi('کل مطالبات', total, 'money', 'danger', 'cash-stack'),
            _kpi('بیش از ۹۰ روز', buckets['بیش از ۹۰ روز'],
                 'money', 'warning', 'hourglass-bottom'),
            _kpi('میانگین بدهی', total / len(rows) if rows else 0,
                 'money', 'info', 'calculator'),
        ], chart=_chart(order, [{
            'label': 'مطالبات', 'data': [float(buckets[key]) for key in order],
            'backgroundColor': ['#3b82f6', '#22c55e', '#f59e0b', '#f97316', '#dc2626'],
        }]), footers={
            'accounts': len(rows), 'amount': total, 'share': 100 if total else 0,
        }, warnings=[warning])
    return _result([
        _col('code', 'ثبت‌نام', link=True), _col('student', 'هنرجو', link=True),
        _col('mobile', 'موبایل'), _col('course', 'دوره'),
        _col('date', 'تاریخ ثبت‌نام', 'date'), _col('fee', 'شهریه', 'money'),
        _col('paid', 'پرداختی تا مبنا', 'money'),
        _col('remaining', 'مانده در مبنا', 'money'),
        _col('age', 'سن بدهی', 'number'), _col('bucket', 'طبقه'),
        _col('branch', 'شعبه'),
    ], rows, kpis=[
        _kpi('پرونده بدهکار', len(rows), icon='person-exclamation'),
        _kpi('کل مطالبات', total, 'money', 'danger', 'cash-stack'),
        _kpi('مطالبات پرریسک', buckets['بیش از ۹۰ روز'],
             'money', 'warning', 'exclamation-triangle'),
        _kpi('میانگین بدهی', total / len(rows) if rows else 0,
             'money', 'info', 'calculator'),
    ], footers={
        'fee': sum((row['fee'] for row in rows), Decimal(0)),
        'paid': sum((row['paid'] for row in rows), Decimal(0)),
        'remaining': total,
    }, warnings=[warning])


def _installments(filters: ReportFilters, variant='calendar') -> dict:
    from models.registration import Installment, Registration

    today=local_today(); limit=today+timedelta(days=30); rows=[]
    query=(Installment.query.join(Registration).options(
           joinedload(Installment.registration).joinedload(Registration.student),
           joinedload(Installment.registration).joinedload(Registration.course),
           joinedload(Installment.registration).joinedload(Registration.branch)))
    if filters.branch_id: query=query.filter(Registration.branch_id==filters.branch_id)
    if filters.course_id: query=query.filter(Registration.course_id==filters.course_id)
    if filters.student_id: query=query.filter(Registration.student_id==filters.student_id)
    open_statuses=['pending','partial','overdue']
    open_labels={_status_label(value) for value in open_statuses}
    if variant=='overdue': query=query.filter(Installment.due_date<today,Installment.status.in_(open_statuses))
    elif variant=='upcoming': query=query.filter(Installment.due_date.between(today,limit),Installment.status.in_(open_statuses))
    elif variant=='calendar': query=_query_range(query,Installment.due_date,filters)
    installments=query.order_by(Installment.due_date).all()
    for inst in installments:
        reg=inst.registration
        delay_until = inst.paid_date if inst.status == 'paid' and inst.paid_date else today
        days=(delay_until-inst.due_date).days
        rows.append({'registration':reg.reg_code,'student':reg.student.full_name if reg.student else '-',
                     'mobile':reg.student.mobile if reg.student else '-', 'course':reg.course.title if reg.course else '-',
                     'number':inst.installment_number,'due':inst.due_date,'amount':money(inst.amount),
                     'paid':money(inst.paid_amount),'late_fee':money(inst.late_fee),
                     'remaining':max(money(inst.remaining),Decimal(0)),
                     'delay':max(0,days),'status':_status_label(inst.status),
                     'reminder':'ارسال شده' if inst.reminder_sent else 'ارسال نشده',
                     'registration_url':(url_for('registration.view',id=reg.id)
                                         if _can_drill_down(filters, 'registration') else None)})
    total=sum((r['remaining'] for r in rows),Decimal(0))
    return _result([_col('registration','ثبت‌نام',link=True),_col('student','هنرجو'),_col('mobile','موبایل'),
                    _col('course','دوره'),_col('number','قسط','number'),_col('due','سررسید','date'),
                    _col('amount','مبلغ','money'),_col('paid','پرداختی','money'),_col('late_fee','دیرکرد','money'),
                    _col('remaining','مانده','money'),_col('delay','روز تأخیر','number'),_col('status','وضعیت','status'),
                    _col('reminder','یادآوری','status')],rows,
        kpis=[_kpi('تعداد اقساط',len(rows),icon='calendar-check'),_kpi('مانده قابل وصول',total,'money','danger','cash-stack'),
              _kpi('جریمه دیرکرد',sum((r['late_fee'] for r in rows),Decimal(0)),'money','warning','clock-history'),
              _kpi('یادآوری‌نشده',sum(
                  r['reminder']=='ارسال نشده' and r['status'] in open_labels
                  for r in rows
              ),color='info',icon='bell')],
        footers={'amount':sum((r['amount'] for r in rows),Decimal(0)),'paid':sum((r['paid'] for r in rows),Decimal(0)),
                 'late_fee':sum((r['late_fee'] for r in rows),Decimal(0)),'remaining':total})


def _discounts(filters: ReportFilters) -> dict:
    from models.registration import Registration

    query=(Registration.query.options(joinedload(Registration.student),joinedload(Registration.course),joinedload(Registration.branch))
           .filter(db.or_(Registration.discount_amount>0,
                          Registration.status=='withdrawn',
                          Registration.cancellation_reason.isnot(None),
                          Registration.cancelled_at.isnot(None))))
    query=_query_branch(_query_range(query,Registration.registration_date,filters),Registration.branch_id,filters)
    if filters.course_id: query=query.filter(Registration.course_id==filters.course_id)
    if filters.student_id: query=query.filter(Registration.student_id==filters.student_id)
    rows=[]
    for reg in query.all():
        rows.append({'code':reg.reg_code,'date':reg.registration_date,'student':reg.student.full_name if reg.student else '-',
                     'course':reg.course.title if reg.course else '-','base':money(reg.base_fee),'type':reg.discount_type or '-',
                     'value':reg.discount_value or 0,'discount':money(reg.discount_amount),'final':money(reg.total_fee),
                     'coupon':reg.discount_code or '-','branch':reg.branch.name if reg.branch else '-',
                     'status':_status_label(reg.status),
                     'cancellation':reg.cancellation_reason or '-',
                     'code_url':(url_for('registration.view',id=reg.id)
                                 if _can_drill_down(filters, 'registration') else None)})
    total=sum((r['discount'] for r in rows),Decimal(0)); base=sum((r['base'] for r in rows),Decimal(0))
    return _result([_col('code','ثبت‌نام',link=True),_col('date','تاریخ','date'),_col('student','هنرجو'),_col('course','دوره'),
                    _col('base','مبلغ پایه','money'),_col('type','نوع تخفیف'),_col('value','مقدار','number'),
                    _col('discount','تخفیف','money'),_col('final','نهایی','money'),_col('coupon','کد تخفیف'),
                    _col('branch','شعبه'),_col('status','وضعیت','status'),_col('cancellation','علت ابطال/انصراف')],rows,
        kpis=[_kpi('پرونده تخفیف‌دار',sum(r['discount']>0 for r in rows),icon='percent'),
              _kpi('ابطال/انصراف',sum(r['cancellation']!='-' or r['status']==_status_label('withdrawn') for r in rows),color='danger',icon='x-octagon'),
              _kpi('جمع تخفیف',total,'money','danger','tags'),
              _kpi('نرخ تخفیف',total/base*100 if base else 0,'percent','warning','pie-chart')],
        footers={'base':base,'discount':total,'final':sum((r['final'] for r in rows),Decimal(0))})


def _expenses(filters: ReportFilters, variant='category') -> dict:
    from models.finance import Expense

    query=Expense.query.options(joinedload(Expense.category),joinedload(Expense.branch))
    query=_query_branch(_query_range(query,Expense.expense_date,filters),Expense.branch_id,filters)
    if filters.status: query=query.filter(Expense.status==filters.status)
    else: query=query.filter(Expense.status=='confirmed')
    expenses=query.all()
    grouped=defaultdict(lambda:{'count':0,'amount':Decimal(0)})
    for exp in expenses:
        key=(exp.category.name if exp.category else 'بدون دسته‌بندی') if variant=='category' else (exp.paid_to or 'نامشخص')
        grouped[key]['count']+=1; grouped[key]['amount']+=money(exp.amount)
    total=sum((v['amount'] for v in grouped.values()),Decimal(0))
    rows=[{'group':k,'count':v['count'],'amount':v['amount'],'share':v['amount']/total*100 if total else 0}
          for k,v in grouped.items()]
    rows.sort(key=lambda r:r['amount'],reverse=True)
    return _result([_col('group','دسته‌بندی' if variant=='category' else 'دریافت‌کننده'),_col('count','تعداد','number'),
                    _col('amount','مبلغ','money'),_col('share','سهم','percent')],rows,
        kpis=[_kpi('تعداد هزینه',sum(r['count'] for r in rows),icon='wallet2'),_kpi('جمع هزینه',total,'money','danger','graph-down-arrow'),
              _kpi('بیشترین سرفصل',rows[0]['group'] if rows else '-',color='warning',icon='bar-chart'),
              _kpi('میانگین هزینه',total/sum(r['count'] for r in rows) if rows else 0,'money','info','calculator')],
        chart=_chart([r['group'] for r in rows[:10]],[{'label':'هزینه','data':[float(r['amount']) for r in rows[:10]],'backgroundColor':'#ef4444'}]),
        footers={'count':sum(r['count'] for r in rows),'amount':total,'share':100 if total else 0})


def _budget_period_bounds(item) -> tuple[date | None, date | None]:
    """Convert one Jalali budget period to an inclusive Gregorian range."""
    try:
        import jdatetime
        year = int(item.fiscal_year)
        if item.period == 'month' and item.period_no:
            first_month, next_month = int(item.period_no), int(item.period_no) + 1
        elif item.period == 'quarter' and item.period_no:
            first_month = (int(item.period_no) - 1) * 3 + 1
            next_month = first_month + 3
        else:
            first_month, next_month = 1, 13
        start = jdatetime.date(year, first_month, 1).togregorian()
        if next_month == 13:
            next_start = jdatetime.date(year + 1, 1, 1).togregorian()
        else:
            next_start = jdatetime.date(year, next_month, 1).togregorian()
        return start, next_start - timedelta(days=1)
    except (ImportError, TypeError, ValueError, OverflowError):
        return None, None


def _budget(filters: ReportFilters) -> dict:
    from models.accounting import JournalEntry, JournalItem
    from models.finance import Expense, Payment
    from models.reporting import ReportBudget

    records=(ReportBudget.query.options(joinedload(ReportBudget.branch),joinedload(ReportBudget.account),joinedload(ReportBudget.expense_category)).all())
    expense_query=_query_branch(Expense.query.filter_by(status='confirmed'),Expense.branch_id,filters)
    payment_query=_query_branch(Payment.query.filter_by(status='confirmed'),Payment.branch_id,filters)
    expenses=expense_query.all(); payments=payment_query.all()
    rows=[]; legacy_periods=False
    for item in records:
        if filters.branch_id and item.branch_id!=filters.branch_id: continue
        period_start,period_end=_budget_period_bounds(item)
        if not period_start or not period_end: continue
        if filters.date_from and period_end<filters.date_from: continue
        if filters.date_to and period_start>filters.date_to: continue
        if item.period in ('month','quarter') and not item.period_no: legacy_periods=True
        actual=Decimal(0)
        if item.account_id:
            # Account-linked budgets use posted journal turnover, preserving the
            # accounting source of truth rather than approximating from cash.
            account_query = (db.session.query(
                    db.func.sum(JournalItem.debit), db.func.sum(JournalItem.credit))
                .join(JournalEntry, JournalItem.entry_id == JournalEntry.id)
                .filter(JournalItem.account_id == item.account_id,
                        JournalEntry.status.in_(['confirmed', 'approved']),
                        JournalEntry.entry_date.between(period_start, period_end)))
            if item.branch_id:
                account_query = account_query.filter(JournalEntry.branch_id == item.branch_id)
            debit, credit = account_query.one()
            actual = (money(debit) - money(credit) if item.budget_type == 'expense'
                      else money(credit) - money(debit))
        elif item.budget_type=='expense':
            for exp in expenses:
                if not (period_start<=exp.expense_date<=period_end): continue
                if item.expense_category_id and exp.category_id!=item.expense_category_id: continue
                if not item.branch_id or exp.branch_id==item.branch_id: actual+=money(exp.amount)
        else:
            for p in payments:
                if not (period_start<=p.payment_date<=period_end): continue
                if not item.branch_id or p.branch_id==item.branch_id: actual+=money(p.amount)
        planned=money(item.amount); variance=(planned-actual if item.budget_type=='expense' else actual-planned)
        period_label=('سالانه' if item.period=='year' else
                      f'فصل {item.period_no or "؟"}' if item.period=='quarter' else
                      f'ماه {item.period_no or "؟"}')
        rows.append({'year':item.fiscal_year,'period':period_label,'title':item.title,
                     'type':'هزینه' if item.budget_type=='expense' else 'درآمد',
                     'branch':item.branch.name if item.branch else 'کل سازمان (تجمیعی)','budget':planned,'actual':actual,
                     'variance':variance,'progress':actual/planned*100 if planned else 0})
    total_budget=sum((r['budget'] for r in rows),Decimal(0)); total_actual=sum((r['actual'] for r in rows),Decimal(0))
    income_rows=[r for r in rows if r['type']=='درآمد']; expense_rows=[r for r in rows if r['type']=='هزینه']
    income_budget=sum((r['budget'] for r in income_rows),Decimal(0)); income_actual=sum((r['actual'] for r in income_rows),Decimal(0))
    expense_budget=sum((r['budget'] for r in expense_rows),Decimal(0)); expense_actual=sum((r['actual'] for r in expense_rows),Decimal(0))
    warnings=[]
    if not rows: warnings.append('هنوز بودجه‌ای ثبت نشده است؛ از دکمه «ثبت بودجه» در مرکز گزارش‌ها استفاده کنید.')
    if legacy_periods: warnings.append('برای برخی بودجه‌های قدیمی شماره ماه یا فصل ثبت نشده و عملکرد کل سال استفاده شده است.')
    return _result([_col('year','سال'),_col('period','دوره'),_col('title','عنوان بودجه'),_col('type','نوع'),_col('branch','شعبه'),
                    _col('budget','بودجه','money'),_col('actual','عملکرد','money'),_col('variance','انحراف مطلوب','money'),_col('progress','تحقق','percent')],rows,
        kpis=[_kpi('هدف درآمد',income_budget,'money','primary','bullseye'),_kpi('درآمد محقق',income_actual,'money','success','graph-up-arrow'),
              _kpi('سقف هزینه',expense_budget,'money','warning','clipboard-data'),_kpi('هزینه واقعی',expense_actual,'money','danger','graph-down-arrow')],
        chart=_chart([r['title'] for r in rows[:12]],[
            {'label':'بودجه','data':[float(r['budget']) for r in rows[:12]],'backgroundColor':'#8b5cf6'},
            {'label':'عملکرد','data':[float(r['actual']) for r in rows[:12]],'backgroundColor':'#0ea5e9'}]),
        footers={'budget':total_budget,'actual':total_actual,'variance':sum((r['variance'] for r in rows),Decimal(0))},warnings=warnings)


def _break_even(filters: ReportFilters) -> dict:
    base=_cash_flow(filters); rows=[]; cumulative=Decimal(0); break_month='-'
    for source in base['rows']:
        cumulative+=source['net']
        row=dict(source); row['cumulative']=cumulative; row['state']='مازاد' if source['net']>=0 else 'کسری'
        if break_month=='-' and cumulative>=0 and source['income']>0: break_month=source['month']
        rows.append(row)
    base['columns']=[_col('month','ماه شمسی'),_col('income','درآمد','money'),_col('expense','هزینه','money'),
                     _col('net','مازاد/کسری','money'),_col('cumulative','تجمعی','money'),_col('state','وضعیت','status')]
    base['rows']=rows; base['kpis'].append(_kpi('اولین نقطه سربه‌سر',break_month,color='warning',icon='bullseye'))
    base['footers']['cumulative']=cumulative
    return base


def _course_profitability(filters: ReportFilters) -> dict:
    from models.course import Course
    from models.finance import Payment
    from models.registration import Registration

    course_query=Course.query.options(joinedload(Course.field),joinedload(Course.branch))
    if filters.course_id: course_query=course_query.filter(Course.id==filters.course_id)
    if filters.branch_id: course_query=course_query.filter(db.or_(Course.branch_id==filters.branch_id,Course.branch_id.is_(None)))
    courses=course_query.all()

    reg_query=_query_branch(_query_range(Registration.query,Registration.registration_date,filters),Registration.branch_id,filters)
    if filters.course_id: reg_query=reg_query.filter(Registration.course_id==filters.course_id)
    if filters.teacher_id: reg_query=reg_query.filter(Registration.teacher_id==filters.teacher_id)
    registrations=reg_query.all(); grouped_regs=defaultdict(list)
    for reg in registrations:
        grouped_regs[reg.course_id].append(reg)

    # Collections are activity in the selected payment period, even when the
    # underlying registration originated earlier.  Joining Registration keeps
    # course, teacher and branch attribution exact.
    payment_query = (db.session.query(Registration.course_id, db.func.sum(Payment.amount))
                     .join(Payment, Payment.registration_id == Registration.id)
                     .filter(Payment.status == 'confirmed'))
    if filters.date_from:
        payment_query = payment_query.filter(Payment.payment_date >= filters.date_from)
    if filters.date_to:
        payment_query = payment_query.filter(Payment.payment_date <= filters.date_to)
    if filters.branch_id:
        payment_query = payment_query.filter(Registration.branch_id == filters.branch_id)
    if filters.course_id:
        payment_query = payment_query.filter(Registration.course_id == filters.course_id)
    if filters.teacher_id:
        payment_query = payment_query.filter(Registration.teacher_id == filters.teacher_id)
    revenue_by_course = defaultdict(Decimal)
    for course_id, amount in payment_query.group_by(Registration.course_id).all():
        if course_id:
            revenue_by_course[course_id] = money(amount)

    rows=[]
    for course in courses:
        regs=grouped_regs[course.id]; revenue=revenue_by_course[course.id]
        if not regs and not revenue:
            continue
        fees=sum((money(r.total_fee) for r in regs),Decimal(0))
        teacher_cost=sum((money(r.teacher_payment_amount) for r in regs),Decimal(0))
        receivable=sum((max(money(r.remaining_amount), Decimal(0)) for r in regs), Decimal(0))
        # Contract value and its direct teaching obligation share the same
        # registration cohort.  Collections remain a separate cash KPI, so a
        # payment for an older enrolment cannot create a fictitious 100% profit.
        profit=fees-teacher_cost; margin=profit/fees*100 if fees else 0
        rows.append({'code':course.code,'course':course.title,'field':course.field.name if course.field else '-',
                     'branch':course.branch.name if course.branch else 'مشترک', 'registrations':len(regs),
                     'contract_value':fees,'revenue':revenue,'receivable':receivable,
                     'direct_cost':teacher_cost,'profit':profit,'margin':margin,
                     'code_url':(url_for('new_features.course_view',id=course.id)
                                 if _can_drill_down(filters, 'courses') else None)})
    rows.sort(key=lambda r:(r['profit'],r['revenue']),reverse=True)
    contract_value=sum((r['contract_value'] for r in rows),Decimal(0))
    revenue=sum((r['revenue'] for r in rows),Decimal(0)); profit=sum((r['profit'] for r in rows),Decimal(0))
    return _result([_col('code','کد',link=True),_col('course','دوره'),_col('field','رشته'),_col('branch','شعبه'),
                    _col('registrations','ثبت‌نام جدید','number'),_col('contract_value','ارزش قرارداد جدید','money'),
                    _col('revenue','وصولی طی بازه','money'),_col('receivable','مانده فعلی گروه','money'),_col('direct_cost','هزینه مستقیم گروه','money'),
                    _col('profit','سود تعهدی گروه','money'),_col('margin','حاشیه تعهدی','percent')],rows,
        kpis=[_kpi('ارزش قرارداد جدید',contract_value,'money','primary','file-earmark-text'),
              _kpi('وصولی طی بازه',revenue,'money','success','cash-stack'),
              _kpi('سود تعهدی ثبت‌نام جدید',profit,'money','primary','graph-up-arrow'),
              _kpi('حاشیه تعهدی',profit/contract_value*100 if contract_value else 0,'percent','info','percent')],
        chart=_chart([r['course'] for r in rows[:10]],[{'label':'ارزش قرارداد جدید','data':[float(r['contract_value']) for r in rows[:10]],'backgroundColor':'#8b5cf6'},
                                                               {'label':'وصولی طی بازه','data':[float(r['revenue']) for r in rows[:10]],'backgroundColor':'#22c55e'},
                                                               {'label':'سود تعهدی گروه','data':[float(r['profit']) for r in rows[:10]],'backgroundColor':'#2563eb'}]),
        footers={k:sum((money(r[k]) for r in rows),Decimal(0)) for k in ('contract_value','revenue','receivable','direct_cost','profit')}|{'registrations':sum(r['registrations'] for r in rows)},
        warnings=['سود و هزینه مستقیم بر مبنای ثبت‌نام‌های ایجادشده در بازه است؛ وصولی صرفاً بر اساس تاریخ واقعی پرداخت همان بازه نمایش داده می‌شود.'])


def _branch_profitability(filters: ReportFilters) -> dict:
    from models.finance import Expense, Payment
    from models.registration import Registration
    from models.student import Student
    from models.system import Branch

    # Keep inactive branches in historical profitability; hiding a closed
    # branch would also hide its accounting activity from prior periods.
    branch_query=Branch.query
    if filters.branch_id: branch_query=branch_query.filter(Branch.id==filters.branch_id)
    branches=branch_query.all(); branch_ids={item.id for item in branches}
    grouped=defaultdict(lambda:{'income':Decimal(0),'expense':Decimal(0),'registrations':0,'students':0})
    for payment in _query_range(Payment.query.filter(Payment.status=='confirmed',Payment.branch_id.in_(branch_ids)),Payment.payment_date,filters).all():
        grouped[payment.branch_id]['income']+=money(payment.amount)
    for expense in _query_range(Expense.query.filter(Expense.status=='confirmed',Expense.branch_id.in_(branch_ids)),Expense.expense_date,filters).all():
        grouped[expense.branch_id]['expense']+=money(expense.amount)
    for reg in _query_range(Registration.query.filter(Registration.branch_id.in_(branch_ids)),Registration.registration_date,filters).all():
        grouped[reg.branch_id]['registrations']+=1
    for student in Student.query.filter(Student.branch_id.in_(branch_ids),Student.status=='active').all():
        grouped[student.branch_id]['students']+=1
    rows=[]
    for branch in branches:
        data=grouped[branch.id]; income=data['income']; cost=data['expense']; profit=income-cost
        rows.append({'code':branch.code or '-','branch':branch.name,
                     'status':'فعال' if branch.is_active else 'غیرفعال',
                     'students':data['students'],
                     'registrations':data['registrations'],'income':income,'expense':cost,
                     'profit':profit,'margin':profit/income*100 if income else 0})
    rows.sort(key=lambda r:r['profit'],reverse=True); income=sum((r['income'] for r in rows),Decimal(0)); expense=sum((r['expense'] for r in rows),Decimal(0))
    return _result([_col('code','کد'),_col('branch','شعبه'),_col('status','وضعیت','status'),
                    _col('students','هنرجوی فعال','number'),_col('registrations','ثبت‌نام','number'),
                    _col('income','درآمد','money'),_col('expense','هزینه','money'),
                    _col('profit','سود مستقیم','money'),_col('margin','حاشیه سود','percent')],rows,
        kpis=[_kpi('شعب گزارش',len(rows),icon='buildings'),_kpi('درآمد',income,'money','success','graph-up'),
              _kpi('هزینه',expense,'money','danger','graph-down'),_kpi('سود مستقیم',income-expense,'money','primary','cash-coin')],
        chart=_chart([r['branch'] for r in rows],[{'label':'درآمد','data':[float(r['income']) for r in rows],'backgroundColor':'#22c55e'},
                                                   {'label':'هزینه','data':[float(r['expense']) for r in rows],'backgroundColor':'#ef4444'}]),
        footers={'students':sum(r['students'] for r in rows),'registrations':sum(r['registrations'] for r in rows),
                 'income':income,'expense':expense,'profit':income-expense})


def _payroll(filters: ReportFilters, *, finalized_only: bool = False) -> dict:
    from models.finance import Payslip
    from models.teacher import Teacher

    teacher_query = Teacher.query
    if filters.branch_id:
        teacher_query = teacher_query.filter(Teacher.branch_id == filters.branch_id)
    teachers = {item.id: item for item in teacher_query.all()}
    payslip_query = Payslip.query
    if filters.branch_id:
        payslip_query = payslip_query.filter(
            Payslip.person_type == 'teacher',
            Payslip.person_id.in_(
                db.session.query(Teacher.id).filter(
                    Teacher.branch_id == filters.branch_id
                )
            ),
        )
    rows = []
    for p in payslip_query.order_by(Payslip.created_at.desc()).all():
        pay_date=p.paid_date or (p.created_at.date() if p.created_at else None)
        if not _date_ok(pay_date,filters): continue
        if filters.status and p.status!=filters.status: continue
        if finalized_only and not filters.status and p.status not in ('approved','paid'): continue
        teacher = teachers.get(p.person_id) if p.person_type == 'teacher' else None
        # Employee/manager records have no branch field in the current schema;
        # hide them from branch-restricted users rather than leaking global data.
        if filters.branch_id and (teacher is None or teacher.branch_id != filters.branch_id): continue
        person_name = teacher.full_name if teacher else f'{p.person_type} #{p.person_id}'
        row={'number':p.payslip_number,'period':p.period or '-','person':person_name,
             'gross':money(p.gross_amount),'insurance':money(p.insurance),'tax':money(p.tax),
             'deductions':money(p.total_deductions),'net':money(p.net_amount),'paid':p.paid_date,'status':_status_label(p.status)}
        if teacher and _can_drill_down(filters, 'teachers'):
            row['person_url'] = url_for('teachers.view', id=teacher.id)
        rows.append(row)
    gross=sum((r['gross'] for r in rows),Decimal(0)); net=sum((r['net'] for r in rows),Decimal(0))
    return _result([_col('number','فیش'),_col('period','دوره'),_col('person','شخص',link=True),_col('gross','ناخالص','money'),
                    _col('insurance','بیمه','money'),_col('tax','مالیات','money'),_col('deductions','کسورات','money'),
                    _col('net','خالص','money'),_col('paid','تاریخ پرداخت','date'),_col('status','وضعیت','status')],rows,
        kpis=[_kpi('تعداد فیش',len(rows),icon='person-vcard'),_kpi('حقوق ناخالص',gross,'money','primary','cash-stack'),
              _kpi('حقوق خالص',net,'money','success','wallet2'),_kpi('مالیات و بیمه',sum((r['insurance']+r['tax'] for r in rows),Decimal(0)),'money','warning','percent')],
        footers={key:sum((r[key] for r in rows),Decimal(0)) for key in ('gross','insurance','tax','deductions','net')})


def _payroll_tax(filters: ReportFilters) -> dict:
    base = _payroll(filters, finalized_only=True)
    rows=[]
    periods=defaultdict(lambda:{'tax':Decimal(0),'insurance':Decimal(0)})
    for source in base['rows']:
        row={key:value for key,value in source.items() if key in {
            'number','period','person','person_url','gross','tax','insurance','paid','status'
        }}
        row['legal_total']=row['tax']+row['insurance']
        rows.append(row)
        periods[row['period']]['tax'] += row['tax']
        periods[row['period']]['insurance'] += row['insurance']
    total_tax=sum((r['tax'] for r in rows),Decimal(0)); total_insurance=sum((r['insurance'] for r in rows),Decimal(0))
    labels=sorted(periods)
    return _result([
        _col('number','فیش'),_col('period','دوره'),_col('person','شخص',link=True),
        _col('gross','حقوق ناخالص','money'),_col('tax','مالیات تکلیفی','money'),
        _col('insurance','بیمه','money'),_col('legal_total','جمع کسورات قانونی','money'),
        _col('paid','تاریخ پرداخت','date'),_col('status','وضعیت','status')
    ],rows,
        kpis=[_kpi('تعداد فیش',len(rows),icon='person-vcard'),
              _kpi('مالیات حقوق',total_tax,'money','danger','percent'),
              _kpi('بیمه',total_insurance,'money','warning','shield-check'),
              _kpi('جمع تعهد قانونی',total_tax+total_insurance,'money','primary','bank')],
        chart=_chart(labels,[
            {'label':'مالیات','data':[float(periods[p]['tax']) for p in labels],'backgroundColor':'#be123c'},
            {'label':'بیمه','data':[float(periods[p]['insurance']) for p in labels],'backgroundColor':'#f59e0b'}]),
        footers={'gross':sum((r['gross'] for r in rows),Decimal(0)),'tax':total_tax,
                 'insurance':total_insurance,'legal_total':total_tax+total_insurance},
        warnings=['مبالغ بر پایه فیش‌های ثبت‌شده‌اند؛ وضعیت ارسال و پرداخت به سازمان‌های قانونی باید با اسناد رسمی تطبیق داده شود.'])


def _tax_summary(filters: ReportFilters) -> dict:
    from models.finance import Expense, Payment
    payment_query=_query_branch(_query_range(Payment.query.filter_by(status='confirmed'),Payment.payment_date,filters),Payment.branch_id,filters)
    expense_query=_query_branch(_query_range(Expense.query.filter_by(status='confirmed'),Expense.expense_date,filters),Expense.branch_id,filters)
    payments=payment_query.all(); expenses=expense_query.all()
    payroll=_payroll(filters, finalized_only=True)
    income=sum((money(p.amount) for p in payments),Decimal(0))
    cost=sum((money(e.amount) for e in expenses),Decimal(0))
    gross=sum((money(r['gross']) for r in payroll['rows']),Decimal(0))
    payroll_tax=sum((money(r['tax']) for r in payroll['rows']),Decimal(0))
    insurance=sum((money(r['insurance']) for r in payroll['rows']),Decimal(0))
    rows=[
        {'section':'درآمد وصول‌شده','records':len(payments),'base':income,'obligation':Decimal(0),'note':'مبنای کنترل فروش/درآمد'},
        {'section':'هزینه‌های قطعی','records':len(expenses),'base':cost,'obligation':Decimal(0),'note':'مبنای کنترل خرید و هزینه'},
        {'section':'حقوق ناخالص','records':len(payroll['rows']),'base':gross,'obligation':Decimal(0),'note':'جمع فیش‌های حقوقی'},
        {'section':'مالیات تکلیفی حقوق','records':len(payroll['rows']),'base':gross,'obligation':payroll_tax,'note':'بر اساس فیش حقوقی'},
        {'section':'بیمه حقوق','records':len(payroll['rows']),'base':gross,'obligation':insurance,'note':'بر اساس فیش حقوقی'},
    ]
    return _result([
        _col('section','حوزه کنترل'),_col('records','تعداد رکورد','number'),
        _col('base','مبلغ مبنا','money'),_col('obligation','تعهد ثبت‌شده','money'),_col('note','توضیح')
    ],rows,
        kpis=[_kpi('گردش درآمد',income,'money','success','graph-up-arrow'),
              _kpi('گردش هزینه',cost,'money','danger','graph-down-arrow'),
              _kpi('مالیات حقوق',payroll_tax,'money','warning','percent'),
              _kpi('بیمه حقوق',insurance,'money','primary','shield-check')],
        chart=_chart(['درآمد','هزینه','مالیات حقوق','بیمه'],[
            {'label':'مبلغ','data':[float(income),float(cost),float(payroll_tax),float(insurance)],
             'backgroundColor':['#16a34a','#dc2626','#be123c','#f59e0b']}],chart_type='bar'),
        warnings=['این گزارش ابزار کنترل داخلی است و جایگزین اظهارنامه، دفاتر قانونی یا محاسبه مشاور مالیاتی نیست. نرخ مالیات بر ارزش افزوده به‌دلیل نبود فیلد مالیات در اسناد عملیاتی، به‌صورت خودکار برآورد نمی‌شود.'])


def _statutory_accounts(filters: ReportFilters) -> dict:
    ledger=_ledger(filters,'account')
    keywords=('مالیات','ارزش افزوده','بیمه','تامین اجتماعی','تأمین اجتماعی')
    rows=[row for row in ledger['rows'] if any(normalise_text(word) in normalise_text(
        f"{row.get('code','')} {row.get('name','')}") for word in keywords)]
    debit=sum((money(r['debit']) for r in rows),Decimal(0)); credit=sum((money(r['credit']) for r in rows),Decimal(0))
    balance=sum((money(r['balance']) for r in rows),Decimal(0))
    warnings=[] if rows else ['سرفصلی با عنوان مالیات، ارزش افزوده، بیمه یا تأمین اجتماعی در کدینگ حساب‌ها پیدا نشد.']
    return _result([
        _col('code','کد حساب',link=True),_col('name','عنوان حساب'),_col('type','ماهیت'),
        _col('opening','مانده اول دوره','money'),_col('debit','گردش بدهکار','money'),
        _col('credit','گردش بستانکار','money'),_col('balance','مانده پایان دوره','money')
    ],rows,
        kpis=[_kpi('سرفصل قانونی',len(rows),icon='journal-medical'),
              _kpi('گردش بدهکار',debit,'money','success','arrow-down-left'),
              _kpi('گردش بستانکار',credit,'money','danger','arrow-up-right'),
              _kpi('خالص مانده',balance,'money','primary','scale')],
        footers={'debit':debit,'credit':credit,'balance':balance},warnings=warnings)


def _students(filters: ReportFilters) -> dict:
    from models.registration import Registration
    from models.student import Student

    query=Student.query.options(joinedload(Student.branch))
    query=_query_branch(_query_range(query,Student.created_at,filters),Student.branch_id,filters)
    if filters.status: query=query.filter(Student.status==filters.status)
    if filters.student_id: query=query.filter(Student.id==filters.student_id)
    students=query.order_by(Student.created_at.desc()).all()
    grouped_regs=defaultdict(list)
    student_ids=[s.id for s in students]
    for offset in range(0,len(student_ids),900):
        registration_query = Registration.query.filter(
            Registration.student_id.in_(student_ids[offset:offset+900])
        )
        if filters.branch_id:
            registration_query = registration_query.filter(Registration.branch_id == filters.branch_id)
        for reg in registration_query.all():
            grouped_regs[reg.student_id].append(reg)
    rows=[]
    for s in students:
        regs=grouped_regs[s.id]; debt=sum((money(r.remaining_amount) for r in regs if money(r.remaining_amount)>0),Decimal(0))
        rows.append({'code':s.student_code,'name':s.full_name,'national':s.national_code or '-',
                     'mobile':s.mobile,'category':s.category or '-','referral':s.referral_source or '-',
                     'branch':s.branch.name if s.branch else '-','registrations':len(regs),'debt':debt,
                     'status':_status_label(s.status),'created':s.created_at,
                     'code_url':(url_for('students.view',id=s.id)
                                 if _can_drill_down(filters, 'students') else None),
                     'name_url':(url_for('students.view',id=s.id)
                                 if _can_drill_down(filters, 'students') else None)})
    debt=sum((r['debt'] for r in rows),Decimal(0))
    return _result([_col('code','کد',link=True),_col('name','نام هنرجو',link=True),_col('national','کد ملی'),_col('mobile','موبایل'),
                    _col('category','دسته'),_col('referral','معرف'),_col('branch','شعبه'),_col('registrations','ثبت‌نام','number'),
                    _col('debt','بدهی','money'),_col('status','وضعیت','status'),_col('created','تاریخ ایجاد','datetime')],rows,
        kpis=[_kpi('هنرجویان',len(rows),icon='people'),_kpi('فعال',sum(r['status']==_status_label('active') for r in rows),color='success',icon='person-check'),
              _kpi('دارای بدهی',sum(r['debt']>0 for r in rows),color='danger',icon='person-exclamation'),_kpi('جمع بدهی',debt,'money','warning','cash-stack')],
        footers={'registrations':sum(r['registrations'] for r in rows),'debt':debt})


def _enrollments(filters: ReportFilters) -> dict:
    from models.registration import Registration

    rows=[]
    query=Registration.query.options(joinedload(Registration.student),joinedload(Registration.course),joinedload(Registration.class_group),
                                     joinedload(Registration.teacher),joinedload(Registration.branch))
    query=_query_branch(_query_range(query,Registration.registration_date,filters),Registration.branch_id,filters)
    if filters.status: query=query.filter(Registration.status==filters.status)
    if filters.course_id: query=query.filter(Registration.course_id==filters.course_id)
    if filters.class_id: query=query.filter(Registration.class_id==filters.class_id)
    if filters.teacher_id: query=query.filter(Registration.teacher_id==filters.teacher_id)
    if filters.student_id: query=query.filter(Registration.student_id==filters.student_id)
    regs=query.order_by(Registration.registration_date.desc()).all()
    for r in regs:
        rows.append({'code':r.reg_code,'date':r.registration_date,'student':r.student.full_name if r.student else '-',
                     'course':r.course.title if r.course else '-','class':r.class_group.name if r.class_group else '-',
                     'teacher':r.teacher.full_name if r.teacher else '-', 'base':money(r.base_fee),'discount':money(r.discount_amount),
                     'fee':money(r.total_fee),'paid':money(r.paid_amount),
                     'remaining':max(money(r.remaining_amount),Decimal(0)),
                     'branch':r.branch.name if r.branch else '-','status':_status_label(r.status),
                     'code_url':(url_for('registration.view',id=r.id)
                                 if _can_drill_down(filters, 'registration') else None),
                     'student_url':(url_for('students.view',id=r.student_id)
                                    if _can_drill_down(filters, 'students') else None)})
    fee=sum((r['fee'] for r in rows),Decimal(0)); paid=sum((r['paid'] for r in rows),Decimal(0))
    remaining=sum((max(r['remaining'],Decimal(0)) for r in rows),Decimal(0))
    return _result([_col('code','کد ثبت‌نام',link=True),_col('date','تاریخ','date'),_col('student','هنرجو',link=True),
                    _col('course','دوره'),_col('class','کلاس'),_col('teacher','مدرس'),_col('base','پایه','money'),
                    _col('discount','تخفیف','money'),_col('fee','نهایی','money'),_col('paid','پرداختی','money'),
                    _col('remaining','مانده','money'),_col('branch','شعبه'),_col('status','وضعیت','status')],rows,
        kpis=[_kpi('ثبت‌نام',len(rows),icon='person-plus'),_kpi('ارزش قرارداد',fee,'money','primary','file-earmark-text'),
              _kpi('وصول ثبت‌شده',paid,'money','success','cash'),_kpi('مانده',remaining,'money','danger','hourglass')],
        footers={key:sum((r[key] for r in rows),Decimal(0)) for key in ('base','discount','fee','paid','remaining')})


def _enrollment_trend(filters: ReportFilters) -> dict:
    """Show enrolment cohorts and actual collections on their own event dates."""
    from models.finance import Payment
    from models.registration import Registration

    cohort = _enrollments(filters)
    grouped = defaultdict(lambda: {
        'label': '', 'count': 0, 'fee': Decimal(0),
        'paid': Decimal(0), 'remaining': Decimal(0),
    })
    for row in cohort['rows']:
        key, label = _jalali_month(row['date'])
        values = grouped[key]
        values['label'] = label
        values['count'] += 1
        values['fee'] += money(row['fee'])
        # This is the current open balance of registrations created that month;
        # it is deliberately not fee minus unrelated same-month collections.
        values['remaining'] += max(money(row['remaining']), Decimal(0))

    payment_query = (Payment.query.join(
        Registration, Payment.registration_id == Registration.id
    ).filter(Payment.status == 'confirmed'))
    payment_query = _query_range(payment_query, Payment.payment_date, filters)
    if filters.branch_id:
        payment_query = payment_query.filter(Registration.branch_id == filters.branch_id)
    if filters.course_id:
        payment_query = payment_query.filter(Registration.course_id == filters.course_id)
    for payment in payment_query.all():
        key, label = _jalali_month(payment.payment_date)
        grouped[key]['label'] = label
        grouped[key]['paid'] += money(payment.amount)

    rows = [{
        'month': values['label'], 'count': values['count'],
        'fee': values['fee'], 'paid': values['paid'],
        'remaining': values['remaining'],
    } for _key, values in sorted(grouped.items())]
    registration_count = sum(row['count'] for row in rows)
    contract_value = sum((row['fee'] for row in rows), Decimal(0))
    collected = sum((row['paid'] for row in rows), Decimal(0))
    current_remaining = sum((row['remaining'] for row in rows), Decimal(0))
    return _result([
        _col('month', 'ماه شمسی'), _col('count', 'ثبت‌نام جدید', 'number'),
        _col('fee', 'ارزش قرارداد جدید', 'money'),
        _col('paid', 'وصول واقعی ماه', 'money'),
        _col('remaining', 'مانده فعلی گروه ثبت‌نام', 'money'),
    ], rows, kpis=[
        _kpi('ثبت‌نام جدید', registration_count, icon='person-plus'),
        _kpi('ارزش قرارداد جدید', contract_value, 'money', 'primary', 'file-earmark-text'),
        _kpi('وصول طی بازه', collected, 'money', 'success', 'cash'),
        _kpi('مانده فعلی ثبت‌نام‌های بازه', current_remaining,
             'money', 'danger', 'hourglass'),
    ], chart=_chart([row['month'] for row in rows], [
        {'label': 'تعداد ثبت‌نام', 'data': [row['count'] for row in rows],
         'borderColor': '#7c3aed', 'backgroundColor': 'rgba(124,58,237,.12)',
         'yAxisID': 'y'},
        {'label': 'وصول واقعی', 'data': [float(row['paid']) for row in rows],
         'borderColor': '#16a34a', 'backgroundColor': 'rgba(22,163,74,.1)',
         'yAxisID': 'y1'},
    ], 'line'), footers={
        'count': registration_count, 'fee': contract_value,
        'paid': collected, 'remaining': current_remaining,
    }, warnings=[
        'ثبت‌نام‌ها بر اساس تاریخ ثبت و وصولی‌ها بر اساس تاریخ واقعی پرداخت در ماه مربوط نمایش داده می‌شوند.'
    ])


def _class_capacity(filters: ReportFilters) -> dict:
    from models.classes import ClassGroup, ClassSession
    from models.registration import Registration

    query=_query_branch(ClassGroup.query.options(joinedload(ClassGroup.course),joinedload(ClassGroup.teacher),joinedload(ClassGroup.branch)),ClassGroup.branch_id,filters)
    if filters.status: query=query.filter(ClassGroup.status==filters.status)
    if filters.course_id: query=query.filter(ClassGroup.course_id==filters.course_id)
    if filters.teacher_id: query=query.filter(ClassGroup.teacher_id==filters.teacher_id)
    classes=query.all(); counts=defaultdict(int); ids=[c.id for c in classes]
    for offset in range(0,len(ids),900):
        values=(db.session.query(Registration.class_id,db.func.count(Registration.id))
                .filter(Registration.class_id.in_(ids[offset:offset+900]),Registration.status=='active')
                .group_by(Registration.class_id).all())
        counts.update(dict(values))
    session_counts=defaultdict(int)
    for offset in range(0,len(ids),900):
        values=(db.session.query(ClassSession.class_id,db.func.count(ClassSession.id))
                .filter(ClassSession.class_id.in_(ids[offset:offset+900]))
                .group_by(ClassSession.class_id).all())
        session_counts.update(dict(values))
    rows=[]
    for c in classes:
        current=counts[c.id]; maximum=c.max_capacity or 0
        rows.append({'code':c.class_code,'class':c.name,'course':c.course.title if c.course else '-',
                     'teacher':c.teacher.full_name if c.teacher else '-','capacity':maximum,'current':current,
                     'available':max(0,maximum-current),'occupancy':current/maximum*100 if maximum else 0,
                     'sessions':session_counts[c.id],'branch':c.branch.name if c.branch else '-',
                     'status':_status_label(c.status),
                     'code_url':(url_for('classes.view',id=c.id)
                                 if _can_drill_down(filters, 'classes') else None)})
    capacity=sum(r['capacity'] for r in rows); current=sum(r['current'] for r in rows)
    return _result([_col('code','کد کلاس',link=True),_col('class','کلاس'),_col('course','دوره'),_col('teacher','مدرس'),
                    _col('capacity','ظرفیت','number'),_col('current','ثبت‌نام فعال','number'),_col('available','خالی','number'),
                    _col('occupancy','اشغال','percent'),_col('sessions','جلسه','number'),_col('branch','شعبه'),_col('status','وضعیت','status')],rows,
        kpis=[_kpi('کلاس‌ها',len(rows),icon='easel2'),_kpi('ظرفیت کل',capacity,icon='people'),_kpi('ثبت‌نام فعال',current,color='success',icon='person-check'),
              _kpi('نرخ اشغال',current/capacity*100 if capacity else 0,'percent','info','pie-chart')],
        footers={'capacity':capacity,'current':current,
                 'available':sum(r['available'] for r in rows),
                 'sessions':sum(r['sessions'] for r in rows)})


def _student_lifecycle(filters: ReportFilters) -> dict:
    from models.registration import Registration
    from models.student import Student

    query=_query_branch(_query_range(Student.query,Student.created_at,filters),Student.branch_id,filters)
    if filters.status: query=query.filter(Student.status==filters.status)
    students=query.all(); debts=defaultdict(Decimal); ids=[s.id for s in students]
    for offset in range(0,len(ids),900):
        registration_query = Registration.query.filter(
            Registration.student_id.in_(ids[offset:offset+900])
        )
        if filters.branch_id:
            registration_query = registration_query.filter(Registration.branch_id == filters.branch_id)
        for reg in registration_query.all():
            debts[reg.student_id]+=max(money(reg.remaining_amount),Decimal(0))
    grouped=defaultdict(lambda:{'count':0,'debt':Decimal(0)})
    for s in students:
        grouped[_status_label(s.status)]['count']+=1
        grouped[_status_label(s.status)]['debt']+=debts[s.id]
    total=sum(v['count'] for v in grouped.values())
    rows=[{'status':k,'count':v['count'],'share':v['count']/total*100 if total else 0,'debt':v['debt']} for k,v in grouped.items()]
    rows.sort(key=lambda r:r['count'],reverse=True)
    return _result([_col('status','وضعیت','status'),_col('count','تعداد','number'),_col('share','سهم','percent'),_col('debt','مانده بدهی','money')],rows,
        kpis=[_kpi('کل هنرجویان',total,icon='people'),_kpi('فعال',next((r['count'] for r in rows if r['status']==_status_label('active')),0),color='success',icon='person-check'),
              _kpi('انصرافی',next((r['count'] for r in rows if r['status']==_status_label('withdrawn')),0),color='danger',icon='person-x'),
              _kpi('نرخ ماندگاری',next((r['count'] for r in rows if r['status']==_status_label('active')),0)/total*100 if total else 0,'percent','info','graph-up')],
        chart=_chart([r['status'] for r in rows],[{'label':'هنرجو','data':[r['count'] for r in rows],
                                                       'backgroundColor':['#22c55e','#3b82f6','#ef4444','#f59e0b','#8b5cf6'][:len(rows)]}],'doughnut'),
        footers={'count':total,'share':100 if total else 0,'debt':sum((r['debt'] for r in rows),Decimal(0))})


def _attendance(filters: ReportFilters) -> dict:
    from models.attendance import Attendance
    from models.classes import ClassGroup, ClassSession

    grouped=defaultdict(lambda:{'class':None,'total':0,'present':0,'absent':0,'late':0,'leave':0,'late_minutes':0})
    query=(Attendance.query.join(ClassSession,Attendance.session_id==ClassSession.id)
           .join(ClassGroup,ClassSession.class_id==ClassGroup.id)
           .options(joinedload(Attendance.session).joinedload(ClassSession.class_group)))
    query=_query_branch(_query_range(query,ClassSession.session_date,filters),ClassGroup.branch_id,filters)
    if filters.class_id: query=query.filter(ClassGroup.id==filters.class_id)
    if filters.course_id: query=query.filter(ClassGroup.course_id==filters.course_id)
    if filters.teacher_id: query=query.filter(ClassGroup.teacher_id==filters.teacher_id)
    if filters.student_id: query=query.filter(Attendance.student_id==filters.student_id)
    records=query.all()
    for a in records:
        session=a.session; cls=session.class_group if session else None
        if not session or not cls: continue
        data=grouped[cls.id]; data['class']=cls; data['total']+=1
        if a.status in data: data[a.status]+=1
        data['late_minutes']+=a.late_minutes or 0
    rows=[]
    for data in grouped.values():
        cls=data.pop('class'); total=data['total']; present=data['present']+data['late']
        rows.append({'code':cls.class_code,'class':cls.name,'course':cls.course.title if cls.course else '-',
                     'teacher':cls.teacher.full_name if cls.teacher else '-',**data,
                     'rate':present/total*100 if total else 0,
                     'code_url':(url_for('classes.view',id=cls.id)
                                 if _can_drill_down(filters, 'classes') else None)})
    total=sum(r['total'] for r in rows); present=sum(r['present']+r['late'] for r in rows)
    return _result([_col('code','کد کلاس',link=True),_col('class','کلاس'),_col('course','دوره'),_col('teacher','مدرس'),
                    _col('total','ثبت حضور','number'),_col('present','حاضر','number'),_col('absent','غایب','number'),
                    _col('late','تأخیر','number'),_col('leave','مرخصی','number'),_col('late_minutes','دقایق تأخیر','number'),_col('rate','درصد حضور','percent')],rows,
        kpis=[_kpi('ثبت حضور',total,icon='clipboard-check'),_kpi('حاضر',present,color='success',icon='person-check'),
              _kpi('غایب',sum(r['absent'] for r in rows),color='danger',icon='person-x'),_kpi('نرخ حضور',present/total*100 if total else 0,'percent','info','pie-chart')],
        footers={key:sum(r[key] for r in rows) for key in ('total','present','absent','late','leave','late_minutes')})


def _teacher_performance(filters: ReportFilters) -> dict:
    from models.attendance import TeacherAttendance
    from models.classes import ClassGroup, ClassSession
    from models.finance import Payment
    from models.registration import Registration
    from models.teacher import Teacher, TeacherEvaluation

    teacher_query = Teacher.query.options(joinedload(Teacher.branch))
    if filters.teacher_id:
        teacher_query = teacher_query.filter(Teacher.id == filters.teacher_id)
    teacher_query = _query_branch(teacher_query, Teacher.branch_id, filters)
    teachers = teacher_query.all()
    teacher_ids = [item.id for item in teachers]

    stats = defaultdict(lambda: {
        'classes': 0, 'students': 0, 'hours': 0.0, 'late': 0,
        'evaluation_total': 0.0, 'evaluations': 0, 'income': Decimal(0),
    })
    # Chunk the IN lists to remain compatible with SQLite's parameter limit.
    for offset in range(0, len(teacher_ids), 900):
        ids = teacher_ids[offset:offset + 900]
        class_scope = [ClassGroup.teacher_id.in_(ids)]
        if filters.course_id:
            class_scope.append(ClassGroup.course_id == filters.course_id)
        if filters.branch_id:
            class_scope.append(ClassGroup.branch_id == filters.branch_id)
        if filters.date_from:
            class_scope.append(db.or_(ClassGroup.end_date.is_(None),
                                      ClassGroup.end_date >= filters.date_from))
        if filters.date_to:
            class_scope.append(db.or_(ClassGroup.start_date.is_(None),
                                      ClassGroup.start_date <= filters.date_to))

        for teacher_id, count in (db.session.query(ClassGroup.teacher_id, db.func.count(ClassGroup.id))
                                  .filter(*class_scope).group_by(ClassGroup.teacher_id).all()):
            stats[teacher_id]['classes'] = count
        student_query = (db.session.query(
                ClassGroup.teacher_id, db.func.count(db.distinct(Registration.student_id)))
                .join(Registration, Registration.class_id == ClassGroup.id)
                .filter(
                    *class_scope,
                    Registration.status.in_(['active', 'completed', 'transferred']),
                    Registration.is_reserved.is_not(True),
                ))
        # Count actual participating enrolments that intersect the report
        # period, rather than everyone ever attached to a matching class.
        if filters.date_from:
            student_query = student_query.filter(db.or_(
                Registration.end_date.is_(None),
                Registration.end_date >= filters.date_from,
            ))
        if filters.date_to:
            student_query = student_query.filter(db.or_(
                Registration.registration_date.is_(None),
                Registration.registration_date <= filters.date_to,
            ))
        if filters.branch_id:
            student_query = student_query.filter(Registration.branch_id == filters.branch_id)
        for teacher_id, count in student_query.group_by(ClassGroup.teacher_id).all():
            stats[teacher_id]['students'] = count

        payment_query = (db.session.query(ClassGroup.teacher_id, db.func.sum(Payment.amount))
                         .join(Registration, Registration.class_id == ClassGroup.id)
                         .join(Payment, Payment.registration_id == Registration.id)
                         .filter(*class_scope, Payment.status == 'confirmed'))
        if filters.date_from:
            payment_query = payment_query.filter(Payment.payment_date >= filters.date_from)
        if filters.date_to:
            payment_query = payment_query.filter(Payment.payment_date <= filters.date_to)
        if filters.branch_id:
            payment_query = payment_query.filter(
                Registration.branch_id == filters.branch_id
            )
        for teacher_id, amount in payment_query.group_by(ClassGroup.teacher_id).all():
            stats[teacher_id]['income'] = money(amount)

        attendance_query = (db.session.query(
                TeacherAttendance.teacher_id,
                db.func.sum(TeacherAttendance.teaching_hours),
                db.func.sum(TeacherAttendance.late_minutes))
                .join(ClassSession, TeacherAttendance.session_id == ClassSession.id)
                .join(ClassGroup, ClassSession.class_id == ClassGroup.id)
                .filter(TeacherAttendance.teacher_id.in_(ids)))
        if filters.date_from:
            attendance_query = attendance_query.filter(ClassSession.session_date >= filters.date_from)
        if filters.date_to:
            attendance_query = attendance_query.filter(ClassSession.session_date <= filters.date_to)
        if filters.course_id:
            attendance_query = attendance_query.filter(
                ClassGroup.course_id == filters.course_id)
        if filters.branch_id:
            attendance_query = attendance_query.filter(
                ClassGroup.branch_id == filters.branch_id)
        for teacher_id, hours, late in attendance_query.group_by(TeacherAttendance.teacher_id).all():
            stats[teacher_id]['hours'] = hours or 0
            stats[teacher_id]['late'] = late or 0

        evaluation_query = db.session.query(
            TeacherEvaluation.teacher_id,
            db.func.sum(TeacherEvaluation.overall_satisfaction),
            db.func.count(TeacherEvaluation.id),
        ).filter(TeacherEvaluation.teacher_id.in_(ids))
        if filters.course_id or filters.branch_id:
            evaluation_query = evaluation_query.join(
                ClassGroup, TeacherEvaluation.class_id == ClassGroup.id)
        if filters.course_id:
            evaluation_query = evaluation_query.filter(
                ClassGroup.course_id == filters.course_id)
        if filters.branch_id:
            evaluation_query = evaluation_query.filter(
                ClassGroup.branch_id == filters.branch_id)
        if filters.date_from:
            evaluation_query = evaluation_query.filter(TeacherEvaluation.created_at >= filters.date_from)
        if filters.date_to:
            evaluation_query = evaluation_query.filter(
                TeacherEvaluation.created_at < datetime.combine(filters.date_to + timedelta(days=1), time.min)
            )
        for teacher_id, total, count in evaluation_query.group_by(TeacherEvaluation.teacher_id).all():
            stats[teacher_id]['evaluation_total'] = total or 0
            stats[teacher_id]['evaluations'] = count or 0

    rows = []
    for teacher in teachers:
        item = stats[teacher.id]
        average = item['evaluation_total'] / item['evaluations'] if item['evaluations'] else 0
        rows.append({
            'code': teacher.teacher_code, 'teacher': teacher.full_name,
            'specialization': teacher.specialization or '-',
            'branch': teacher.branch.name if teacher.branch else '-',
            'classes': item['classes'], 'students': item['students'],
            'hours': item['hours'], 'late': item['late'],
            'evaluation': average, 'evaluations': item['evaluations'],
            'income': item['income'], 'status': 'فعال' if teacher.is_active else 'غیرفعال',
            'code_url': (url_for('teachers.view', id=teacher.id)
                         if _can_drill_down(filters, 'teachers') else None),
        })
    rows.sort(key=lambda row: (row['evaluation'], row['income']), reverse=True)
    evaluation_count = sum(row['evaluations'] for row in rows)
    evaluation_average = (sum(row['evaluation'] * row['evaluations'] for row in rows) /
                          evaluation_count if evaluation_count else 0)
    return _result([
        _col('code', 'کد', link=True), _col('teacher', 'مدرس'), _col('specialization', 'تخصص'),
        _col('branch', 'شعبه'), _col('classes', 'کلاس', 'number'),
        _col('students', 'هنرجو', 'number'), _col('hours', 'ساعت تدریس', 'number'),
        _col('late', 'دقیقه تأخیر', 'number'), _col('evaluation', 'ارزیابی از ۵', 'number'),
        _col('evaluations', 'نظرسنجی', 'number'), _col('income', 'درآمد منتسب', 'money'),
        _col('status', 'وضعیت', 'status'),
    ], rows, kpis=[
        _kpi('مدرسین', len(rows), icon='person-workspace'),
        _kpi('کلاس‌ها', sum(row['classes'] for row in rows), icon='easel2'),
        _kpi('ساعت تدریس', sum(row['hours'] for row in rows), color='info', icon='clock'),
        _kpi('میانگین ارزیابی', evaluation_average,
             'number', 'warning', 'star'),
    ], footers={
        'classes': sum(row['classes'] for row in rows),
        'students': sum(row['students'] for row in rows),
        'hours': sum(row['hours'] for row in rows),
        'late': sum(row['late'] for row in rows),
        'evaluations': sum(row['evaluations'] for row in rows),
        'income': sum((row['income'] for row in rows), Decimal(0)),
    })


def _exams(filters: ReportFilters) -> dict:
    from models.exam import Exam, ExamResult
    from models.student import Student

    query=_query_range(Exam.query.options(joinedload(Exam.course),joinedload(Exam.class_group)),Exam.exam_date,filters)
    if filters.course_id: query=query.filter(Exam.course_id==filters.course_id)
    if filters.class_id: query=query.filter(Exam.class_id==filters.class_id)
    if filters.status: query=query.filter(Exam.status==filters.status)
    exams=[]
    for exam in query.all():
        exam_branch=exam.class_group.branch_id if exam.class_group else (exam.course.branch_id if exam.course else None)
        if not filters.branch_id or exam_branch in (None,filters.branch_id): exams.append(exam)
    grouped_results=defaultdict(list); exam_ids=[item.id for item in exams]
    for offset in range(0,len(exam_ids),900):
        result_query=ExamResult.query.filter(ExamResult.exam_id.in_(exam_ids[offset:offset+900]))
        if filters.student_id: result_query=result_query.filter(ExamResult.student_id==filters.student_id)
        if filters.branch_id:
            result_query = result_query.join(Student).filter(
                Student.branch_id == filters.branch_id
            )
        for result in result_query.all(): grouped_results[result.exam_id].append(result)
    rows=[]
    for exam in exams:
        results=grouped_results[exam.id]
        if filters.student_id and not results:
            continue
        graded=[r for r in results if r.is_passed is not None]
        scored=[r.total_score or 0 for r in graded]
        passed=sum(r.is_passed is True for r in graded)
        failed=sum(r.is_passed is False for r in graded)
        rows.append({'code':exam.exam_code or '-','exam':exam.title,'date':exam.exam_date,
                     'course':exam.course.title if exam.course else '-','class':exam.class_group.name if exam.class_group else '-',
                     'type':exam.exam_type or '-','participants':len(results),'average':sum(scored)/len(scored) if scored else 0,
                     'passed':passed,'failed':failed,'ungraded':len(results)-len(graded),
                     'pass_rate':passed/len(graded)*100 if graded else 0,
                     'status':_status_label(exam.status),
                     'code_url':(url_for('exams.view',id=exam.id)
                                 if _can_drill_down(filters, 'exams') else None)})
    participants=sum(r['participants'] for r in rows); passed=sum(r['passed'] for r in rows)
    failed=sum(r['failed'] for r in rows); ungraded=sum(r['ungraded'] for r in rows)
    return _result([_col('code','کد',link=True),_col('exam','آزمون'),_col('date','تاریخ','date'),_col('course','دوره'),_col('class','کلاس'),
                    _col('type','نوع'),_col('participants','شرکت‌کننده','number'),_col('average','میانگین','number'),
                    _col('passed','قبول','number'),_col('failed','مردود','number'),
                    _col('ungraded','تصحیح‌نشده','number'),_col('pass_rate','نرخ قبولی','percent'),
                    _col('status','وضعیت','status')],rows,
        kpis=[_kpi('آزمون‌ها',len(rows),icon='journal-check'),_kpi('شرکت‌کنندگان',participants,icon='people'),
              _kpi('قبول‌شده',passed,color='success',icon='check-circle'),
              _kpi('نرخ قبولی',passed/(passed+failed)*100
                   if passed+failed else 0,'percent','info','award')],
        footers={'participants':participants,'passed':passed,
                 'failed':failed,'ungraded':ungraded})


def _certificates(filters: ReportFilters) -> dict:
    from models.course import Certificate

    query=_query_range(Certificate.query.options(joinedload(Certificate.student),joinedload(Certificate.course),joinedload(Certificate.template)),Certificate.issue_date,filters)
    if filters.course_id: query=query.filter(Certificate.course_id==filters.course_id)
    if filters.student_id: query=query.filter(Certificate.student_id==filters.student_id)
    if filters.status: query=query.filter(Certificate.status==filters.status)
    rows=[]
    for c in query.all():
        certificate_branch=(
            c.student.branch_id if c.student and c.student.branch_id is not None
            else (c.course.branch_id if c.course else None)
        )
        if filters.branch_id and certificate_branch!=filters.branch_id: continue
        rows.append({'serial':c.serial_number,'date':c.issue_date,'student':c.student.full_name if c.student else '-',
                     'student_code':c.student.student_code if c.student else '-','course':c.course.title if c.course else '-',
                     'template':c.template.name if c.template else '-','qr':'دارد' if c.qr_code else 'ندارد','status':_status_label(c.status),
                     'student_url':(url_for('students.view',id=c.student_id)
                                    if c.student and _can_drill_down(filters, 'students') else None)})
    return _result([_col('serial','سریال'),_col('date','تاریخ صدور','date'),_col('student','هنرجو',link=True),_col('student_code','کد'),
                    _col('course','دوره'),_col('template','قالب'),_col('qr','QR','status'),_col('status','وضعیت','status')],rows,
        kpis=[_kpi('کل مدارک',len(rows),icon='award'),_kpi('فعال',sum(r['status']==_status_label('active') for r in rows),color='success',icon='patch-check'),
              _kpi('ابطال',sum(r['status']==_status_label('cancelled') for r in rows),color='danger',icon='x-octagon'),
              _kpi('دارای QR',sum(r['qr']=='دارد' for r in rows),color='info',icon='qr-code')])


def _referrals(filters: ReportFilters) -> dict:
    from models.finance import Payment
    from models.student import Student

    student_query = _query_branch(_query_range(Student.query, Student.created_at, filters),
                                  Student.branch_id, filters)
    students = student_query.all()
    income_by_student = defaultdict(Decimal)
    student_ids = [item.id for item in students]
    for offset in range(0, len(student_ids), 900):
        query = (db.session.query(Payment.student_id, db.func.sum(Payment.amount))
                 .filter(Payment.student_id.in_(student_ids[offset:offset + 900]),
                         Payment.status == 'confirmed'))
        if filters.date_from:
            query = query.filter(Payment.payment_date >= filters.date_from)
        if filters.date_to:
            query = query.filter(Payment.payment_date <= filters.date_to)
        if filters.branch_id:
            query = query.filter(Payment.branch_id == filters.branch_id)
        for student_id, amount in query.group_by(Payment.student_id).all():
            income_by_student[student_id] += money(amount)

    grouped = defaultdict(lambda: {'students': 0, 'active': 0, 'income': Decimal(0)})
    for student in students:
        key = REFERRAL_LABELS.get(student.referral_source,
                                  student.referral_source or 'نامشخص')
        grouped[key]['students'] += 1
        grouped[key]['active'] += int(student.status == 'active')
        grouped[key]['income'] += income_by_student[student.id]
    total = sum(value['students'] for value in grouped.values())
    income = sum((value['income'] for value in grouped.values()), Decimal(0))
    rows = [{
        'source': key, 'students': value['students'], 'active': value['active'],
        'income': value['income'], 'share': value['students'] / total * 100 if total else 0,
        'value': value['income'] / value['students'] if value['students'] else 0,
    } for key, value in grouped.items()]
    rows.sort(key=lambda row: (row['students'], row['income']), reverse=True)
    return _result([
        _col('source', 'منبع جذب'), _col('students', 'هنرجو', 'number'),
        _col('active', 'فعال', 'number'), _col('share', 'سهم جذب', 'percent'),
        _col('income', 'درآمد منتسب', 'money'), _col('value', 'ارزش هر هنرجو', 'money'),
    ], rows, kpis=[
        _kpi('منابع جذب', len(rows), icon='megaphone'),
        _kpi('هنرجوی جذب‌شده', total, icon='person-plus'),
        _kpi('درآمد منتسب', income, 'money', 'success', 'cash-stack'),
        _kpi('بهترین منبع', rows[0]['source'] if rows else '-', color='warning', icon='trophy'),
    ], chart=_chart([row['source'] for row in rows], [{
        'label': 'هنرجو', 'data': [row['students'] for row in rows],
        'backgroundColor': '#ec4899',
    }]), footers={
        'students': total, 'active': sum(row['active'] for row in rows),
        'share': 100 if total else 0, 'income': income,
    })


def _churn(filters: ReportFilters) -> dict:
    from models.course import Course
    from models.registration import Registration

    course_query = Course.query
    if filters.course_id:
        course_query = course_query.filter(Course.id == filters.course_id)
    if filters.branch_id:
        course_query = course_query.filter(db.or_(Course.branch_id == filters.branch_id,
                                                  Course.branch_id.is_(None)))
    courses = course_query.all()
    counts = defaultdict(lambda: defaultdict(int))
    course_ids = [item.id for item in courses]
    for offset in range(0, len(course_ids), 900):
        query = (_query_branch(_query_range(
                    Registration.query, Registration.registration_date, filters),
                    Registration.branch_id, filters)
                 .filter(Registration.course_id.in_(course_ids[offset:offset + 900])))
        for course_id, status, count in (query.with_entities(
                Registration.course_id, Registration.status, db.func.count(Registration.id))
                .group_by(Registration.course_id, Registration.status).all()):
            counts[course_id][status or 'unknown'] += count

    rows = []
    for course in courses:
        states = counts[course.id]
        total = sum(states.values())
        if not total:
            continue
        active = states['active']; completed = states['completed']
        transferred = states['transferred']; withdrawn = states['withdrawn']
        frozen = states['frozen']
        other = max(0, total-active-completed-transferred-withdrawn-frozen)
        lost = withdrawn + other
        retained = active + completed + transferred
        rows.append({
            'course': course.title, 'total': total, 'active': active,
            'completed': completed, 'transferred': transferred,
            'withdrawn': withdrawn, 'frozen': frozen, 'other': other,
            'churn': lost / total * 100,
            'retention': retained / total * 100,
        })
    rows.sort(key=lambda row: row['churn'], reverse=True)
    total = sum(row['total'] for row in rows)
    retained = sum(row['active'] + row['completed'] + row['transferred'] for row in rows)
    lost = sum(row['withdrawn'] + row['other'] for row in rows)
    return _result([
        _col('course', 'دوره'), _col('total', 'کل', 'number'),
        _col('active', 'فعال', 'number'), _col('completed', 'تکمیل', 'number'),
        _col('transferred', 'منتقل‌شده', 'number'),
        _col('withdrawn', 'انصراف', 'number'), _col('frozen', 'در معرض ریزش', 'number'),
        _col('other', 'سایر وضعیت‌های ریزش', 'number'),
        _col('churn', 'نرخ ریزش', 'percent'), _col('retention', 'ماندگاری', 'percent'),
    ], rows, kpis=[
        _kpi('ثبت‌نام بررسی‌شده', total, icon='people'),
        _kpi('ریزش', lost, color='danger', icon='person-dash'),
        _kpi('نرخ ریزش', lost / total * 100 if total else 0,
             'percent', 'danger', 'graph-down-arrow'),
        _kpi('نرخ ماندگاری', retained / total * 100 if total else 0,
             'percent', 'success', 'graph-up-arrow'),
    ], footers={key: sum(row[key] for row in rows)
                for key in ('total', 'active', 'completed', 'transferred',
                            'withdrawn', 'frozen', 'other')})


def _executive(filters: ReportFilters) -> dict:
    from models.classes import ClassGroup
    from models.registration import Installment, Registration
    from models.student import Student

    def source_available(module: str, *features: str) -> bool:
        if not _can_drill_down(filters, module):
            return False
        try:
            from license_client import has_feature
            return all(has_feature(feature) for feature in (features or (module,)))
        except (ImportError, RuntimeError):
            # Internal calculations outside a Flask application still honour
            # permission scope, while HTTP/scheduled runs always have licence state.
            return True

    finance_visible = source_available('finance')
    registration_visible = source_available('registration')
    students_visible = source_available('students')
    classes_visible = source_available('classes')
    installments_visible = finance_visible and registration_visible and source_available(
        'finance', 'finance', 'installments'
    )

    rows = []
    kpis = []
    chart = None
    debt_as_of = filters.date_to or local_today()

    if finance_visible:
        cash_flow = _cash_flow(filters)
        income = sum((money(row['income']) for row in cash_flow['rows']), Decimal(0))
        cost = sum((money(row['expense']) for row in cash_flow['rows']), Decimal(0))
        profit = income - cost
        chart = cash_flow['chart']
        rows.extend([
            {'area': 'مالی', 'indicator': 'درآمد قطعی', 'value': income,
             'unit': 'تومان', 'status': 'مطلوب' if income >= cost else 'نیازمند توجه'},
            {'area': 'مالی', 'indicator': 'هزینه قطعی', 'value': cost,
             'unit': 'تومان', 'status': 'کنترل شود' if cost > income else 'مطلوب'},
            {'area': 'مالی', 'indicator': 'سود مستقیم', 'value': profit,
             'unit': 'تومان', 'status': 'مطلوب' if profit >= 0 else 'هشدار'},
        ])
        kpis.extend([
            _kpi('درآمد', income, 'money', 'success', 'graph-up-arrow'),
            _kpi('هزینه', cost, 'money', 'danger', 'graph-down-arrow'),
            _kpi('سود مستقیم', profit, 'money', 'primary', 'cash-coin'),
            _kpi('حاشیه سود', profit / income * 100 if income else 0,
                 'percent', 'primary', 'percent'),
        ])

    if finance_visible and registration_visible:
        # Outstanding debt is a point-in-time control and must not disappear
        # merely because the enrolment originated before the activity period.
        # It combines finance and registration data, so both areas must be
        # visible before the aggregate itself is exposed.
        debt_query = _query_branch(Registration.query, Registration.branch_id, filters)
        debt_query = debt_query.filter(db.or_(
            Registration.registration_date <= debt_as_of,
            Registration.registration_date.is_(None),
        ), db.or_(Registration.total_fee > 0, Registration.remaining_amount > 0))
        debt_registrations = debt_query.all()
        debt_paid = _registration_paid_as_of(debt_registrations, debt_as_of)
        debt = sum((
            max(money(registration.total_fee) - debt_paid[registration.id], Decimal(0))
            if money(registration.total_fee) > 0
            else max(money(registration.remaining_amount), Decimal(0))
            for registration in debt_registrations
        ), Decimal(0))
        rows.append({
            'area': 'مطالبات', 'indicator': 'مانده ثبت‌نام‌ها', 'value': debt,
            'unit': 'تومان', 'status': 'نیازمند پیگیری' if debt else 'مطلوب',
        })
        kpis.append(_kpi(
            'مطالبات', debt, 'money', 'warning', 'person-exclamation',
        ))

    if installments_visible:
        overdue_query = Installment.query.join(Registration).filter(
            Installment.due_date < debt_as_of,
            db.or_(
                Installment.status.in_(['pending', 'partial', 'overdue']),
                db.and_(Installment.paid_date.is_not(None),
                        Installment.paid_date > debt_as_of),
            ),
        )
        if filters.branch_id:
            overdue_query = overdue_query.filter(Registration.branch_id == filters.branch_id)
        overdue = overdue_query.count()
        rows.append({
            'area': 'مطالبات', 'indicator': 'اقساط معوق', 'value': overdue,
            'unit': 'قسط', 'status': 'نیازمند پیگیری' if overdue else 'مطلوب',
        })
        kpis.append(_kpi('اقساط معوق', overdue, color='danger', icon='calendar-x'))

    if registration_visible:
        registration_query = _query_branch(_query_range(
            Registration.query, Registration.registration_date, filters),
            Registration.branch_id, filters,
        )
        registrations = registration_query.count()
        rows.append({'area': 'آموزش', 'indicator': 'ثبت‌نام دوره',
                     'value': registrations, 'unit': 'مورد', 'status': 'اطلاعات'})
        kpis.append(_kpi('ثبت‌نام', registrations, icon='person-plus'))

    if students_visible:
        active_students = (_query_branch(Student.query, Student.branch_id, filters)
                           .filter(Student.status == 'active').count())
        rows.append({'area': 'آموزش', 'indicator': 'هنرجوی فعال',
                     'value': active_students, 'unit': 'نفر', 'status': 'اطلاعات'})
        kpis.append(_kpi('هنرجوی فعال', active_students, color='info', icon='people'))

    if classes_visible:
        active_classes = _query_branch(
            ClassGroup.query.filter_by(status='active'), ClassGroup.branch_id, filters,
        ).count()
        rows.append({'area': 'آموزش', 'indicator': 'کلاس فعال',
                     'value': active_classes, 'unit': 'کلاس', 'status': 'اطلاعات'})
        kpis.append(_kpi('کلاس فعال', active_classes, color='info', icon='easel2'))

    warnings = [
        'شاخص‌های جریان بر مبنای بازه انتخابی‌اند؛ مطالبات و اقساط معوق در تاریخ پایان بازه و شاخص‌های فعال بر مبنای وضعیت فعلی نمایش داده می‌شوند.'
    ]
    if not rows:
        warnings.append('برای نمایش شاخص‌های مدیریتی، دسترسی مشاهده یکی از حوزه‌های مالی، ثبت‌نام، هنرجویان یا کلاس‌ها لازم است.')
    elif not all((finance_visible, registration_visible, students_visible, classes_visible)):
        warnings.append('این داشبورد فقط شاخص‌های حوزه‌های مجاز و فعال در لایسنس را نمایش می‌دهد.')

    return _result([
        _col('area', 'حوزه'), _col('indicator', 'شاخص'),
        _col('value', 'مقدار', 'smart'), _col('unit', 'واحد'),
        _col('status', 'وضعیت', 'status'),
    ], rows, kpis=kpis, chart=chart, warnings=warnings)


BUILDERS: dict[str, Callable[..., dict]] = {
    'journal': _journal, 'ledger': _ledger, 'trial_balance': _trial_balance,
    'balance_sheet': _balance_sheet, 'profit_loss': _profit_loss,
    'cash_flow': _cash_flow, 'equity': _equity, 'sequence': _sequence,
    'fiscal': _fiscal, 'payments': _payments, 'payment_methods': _payment_methods,
    'cashbox_transactions': _cashbox_transactions, 'cashbox_balances': _cashbox_balances,
    'bank_transactions': _bank_transactions, 'bank_balances': _bank_balances,
    'reconciliation': _reconciliation, 'checks': _checks, 'receivables': _receivables,
    'installments': _installments, 'discounts': _discounts, 'expenses': _expenses,
    'budget': _budget, 'break_even': _break_even,
    'course_profitability': _course_profitability, 'branch_profitability': _branch_profitability,
    'payroll': _payroll, 'payroll_tax': _payroll_tax, 'tax_summary': _tax_summary,
    'statutory_accounts': _statutory_accounts,
    'students': _students, 'enrollments': _enrollments,
    'enrollment_trend': _enrollment_trend, 'class_capacity': _class_capacity,
    'student_lifecycle': _student_lifecycle, 'attendance': _attendance,
    'teacher_performance': _teacher_performance, 'exams': _exams,
    'certificates': _certificates, 'referrals': _referrals, 'churn': _churn,
    'executive': _executive,
}


def _report_feature_enabled(meta: Mapping[str, Any]) -> bool:
    """Require the signed-licence feature of both reports and its source area."""
    from license_client import has_feature
    from license_features import FEATURE_KEYS

    if not has_feature('reports'):
        return False
    source_features = meta.get('license_features') or (meta.get('permission', 'reports'),)
    return all(feature not in FEATURE_KEYS or has_feature(feature)
               for feature in source_features)


def can_view_report(user, meta: Mapping[str, Any], *, check_license: bool = True,
                    _permission_checker=None) -> bool:
    if check_license and not _report_feature_enabled(meta):
        return False
    if getattr(user, 'is_admin', False):
        return True
    checker = _permission_checker or (
        getattr(user, 'has_permission', None) if user is not None else None
    )
    if not callable(checker) or not checker('reports', 'view'):
        return False
    # Source-module view permission is required as well. This is intentionally
    # checked here (not only in the HTTP decorator), because scheduled reports
    # execute outside the report route. Cross-module reports list every source
    # in ``source_permissions``; aggregate dashboard rows are instead suppressed
    # dynamically by the builder when their individual source is unavailable.
    required = meta.get('source_permissions')
    if required is None:  # Compatibility with catalogue extensions using the old contract.
        module = meta.get('permission', 'reports')
        required = () if module == 'reports' else (module,)
    return all(checker(module, 'view') for module in required)


def catalog_for_user(user, *, check_license: bool = True) -> OrderedDict[str, dict]:
    if not user:
        return OrderedDict()
    permission_method = getattr(user, 'has_permission', None)
    if not getattr(user, 'is_admin', False) and not callable(permission_method):
        return OrderedDict()
    permission_cache: dict[tuple[str, str], bool] = {}

    def cached_permission(module: str, action: str) -> bool:
        key = (module, action)
        if key not in permission_cache:
            permission_cache[key] = bool(permission_method(module, action))
        return permission_cache[key]

    if (not getattr(user, 'is_admin', False)
            and not cached_permission('reports', 'view')):
        return OrderedDict()

    return OrderedDict(
        (key, dict(meta, key=key)) for key, meta in REPORT_CATALOG.items()
        if can_view_report(
            user, meta, check_license=check_license,
            _permission_checker=cached_permission,
        )
    )


def _matches_query(row: Mapping[str, Any], query: str) -> bool:
    needle = normalise_text(query)
    if not needle:
        return True
    searchable = []
    for key, value in row.items():
        if key.endswith('_url'):
            continue
        searchable.append(normalise_text(value))
        if isinstance(value, (date, datetime)):
            searchable.append(normalise_text(gregorian_to_jalali(value)))
    return needle in ' '.join(searchable)


def _sort_value(value: Any):
    if value is None: return (1, '')
    if isinstance(value, (Decimal, int, float)): return (0, float(value))
    if isinstance(value, (date, datetime)): return (0, value.isoformat())
    return (0, normalise_text(value))


def run_report(report_key: str, filters: ReportFilters, *, paginate: bool = True) -> dict:
    meta = REPORT_CATALOG.get(report_key)
    if not meta:
        raise KeyError(report_key)
    builder = BUILDERS[meta['builder']]
    if meta.get('variant') is not None:
        result = builder(filters, meta['variant'])
    else:
        result = builder(filters)

    # Period comparison is calculated by the very same builder, preventing the
    # dashboard and exported figures from drifting apart. Point-in-time reports
    # compare against the matching date one Jalali month/year earlier.
    comparison_filters = None
    if filters.compare and filters.date_to:
        if meta.get('date_mode') == 'as_of':
            try:
                previous_to = (_previous_jalali_year(filters.date_to)
                               if filters.compare == 'year'
                               else _previous_jalali_month(filters.date_to))
            except (ImportError, TypeError, ValueError, OverflowError):
                previous_to = filters.date_to - timedelta(
                    days=365 if filters.compare == 'year' else 30)
            comparison_filters = replace(
                filters, date_from=None, date_to=previous_to,
                compare='', page=1, q='', sort=''
            )
        elif filters.date_from:
            duration = filters.date_to - filters.date_from
            if filters.compare == 'year':
                try:
                    previous_from = _previous_jalali_year(filters.date_from)
                    previous_to = _previous_jalali_year(filters.date_to)
                except (ImportError, TypeError, ValueError, OverflowError):
                    previous_from = filters.date_from - timedelta(days=365)
                    previous_to = filters.date_to - timedelta(days=365)
            else:
                previous_to = filters.date_from - timedelta(days=1)
                previous_from = previous_to - duration
            comparison_filters = replace(
                filters, date_from=previous_from, date_to=previous_to,
                compare='', page=1, q='', sort=''
            )
    if comparison_filters:
        if meta.get('variant') is not None:
            previous = builder(comparison_filters, meta['variant'])
        else:
            previous = builder(comparison_filters)
        previous_metrics = {item['label']: item.get('value') for item in previous.get('kpis', [])}
        for item in result.get('kpis', []):
            current_value = item.get('value')
            previous_value = previous_metrics.get(item['label'])
            if isinstance(current_value, (Decimal, int, float)) and isinstance(previous_value, (Decimal, int, float)):
                current_number, previous_number = float(current_value), float(previous_value)
                if previous_number:
                    item['comparison'] = (current_number - previous_number) / abs(previous_number) * 100
                elif current_number:
                    item['comparison'] = 100.0
        if meta.get('date_mode') == 'as_of':
            comparison_caption = f'تاریخ مبنای {gregorian_to_jalali(previous_to)}'
        else:
            comparison_caption = (f'بازه {gregorian_to_jalali(previous_from)} تا '
                                  f'{gregorian_to_jalali(previous_to)}')
        result.setdefault('warnings', []).append(
            f'مقایسه با {comparison_caption} انجام شده است.'
        )

    rows = [row for row in result['rows'] if _matches_query(row, filters.q)]
    if filters.q:
        result.setdefault('warnings', []).append(
            'جستجوی متنی فقط ردیف‌های جدول را محدود می‌کند؛ KPIها و جمع‌های مدیریتی بر پایه سایر فیلترهای گزارش هستند.'
        )
    column_keys = {column['key'] for column in result['columns']}
    sort_key = filters.sort if filters.sort in column_keys else ''
    if sort_key:
        populated = [row for row in rows if row.get(sort_key) not in (None, '')]
        missing = [row for row in rows if row.get(sort_key) in (None, '')]
        populated.sort(key=lambda row: _sort_value(row.get(sort_key)),
                       reverse=filters.direction == 'desc')
        rows = populated + missing
    result['total_rows'] = len(rows)
    result['per_page'] = filters.per_page
    result['pages'] = max(1, math.ceil(len(rows) / filters.per_page))
    result['page'] = min(filters.page, result['pages'])
    if len(rows) > 50000:
        # Announce the ceiling on the HTML/API result as well as the exported
        # payload, so users know before downloading a deliberately partial file.
        result.setdefault('warnings', []).append(
            'خروجی به ۵۰٬۰۰۰ ردیف محدود می‌شود؛ بازه گزارش را کوچک‌تر کنید.'
        )
    if paginate:
        start = (result['page'] - 1) * filters.per_page
        result['rows'] = rows[start:start + filters.per_page]
    else:
        # A hard ceiling protects desktop installations from accidental memory
        # exhaustion while still allowing substantial accounting exports.
        result['rows'] = rows[:50000]
    result['meta'] = dict(meta, key=report_key)
    result['generated_at'] = local_now()
    result['filters'] = filters
    return result


def serialise_value(value: Any) -> Any:
    if isinstance(value, Decimal): return float(value) if value.is_finite() else None
    if isinstance(value, float): return value if math.isfinite(value) else None
    if isinstance(value, datetime): return value.isoformat(timespec='seconds')
    if isinstance(value, date): return value.isoformat()
    if isinstance(value, Mapping):
        return {key: serialise_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [serialise_value(item) for item in value]
    return value


def serialise_result(result: Mapping[str, Any]) -> dict:
    return {
        'meta': result['meta'], 'columns': result['columns'],
        'rows': [{k: serialise_value(v) for k, v in row.items() if not k.endswith('_url')}
                 for row in result['rows']],
        'kpis': [{**item, 'value': serialise_value(item['value'])} for item in result['kpis']],
        'chart': serialise_value(result.get('chart')), 'warnings': result.get('warnings', []),
        'footers': {key: serialise_value(value)
                    for key, value in result.get('footers', {}).items()},
        'filters': serialise_value(result['filters'].serialisable()),
        'total_rows': result['total_rows'], 'page': result['page'],
        'pages': result['pages'], 'per_page': result['per_page'],
        'generated_at': result['generated_at'].isoformat(timespec='seconds'),
    }


def default_date_range() -> tuple[str, str]:
    """Current Jalali year-to-date range used by report defaults."""
    try:
        import jdatetime
        today = jdatetime.date.fromgregorian(date=local_today())
        return f'{today.year}/01/01', today.strftime('%Y/%m/%d')
    except Exception:
        return '', ''
