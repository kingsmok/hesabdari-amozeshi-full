"""
فهرست بخش‌های قابل قفل‌شدن نرم‌افزار و نگاشت آن‌ها به مسیرهای واقعی برنامه.

این فایل «مرجع ساختاری» است، نه «مرجع دسترسی».
یعنی اینجا فقط می‌گوییم «کدام مسیر متعلق به کدام بخش است»؛
اینکه هر بخش برای مشتریِ در حال اجرا باز است یا بسته، فقط از
`allowed_features` در پاسخ امضاشده‌ی سرور لایسنس خوانده می‌شود
(نگاه کنید به license_client.LicenseState.has_feature).
"""

# ══════════════════════════════════════════════════════════════
#  فهرست بخش‌های این محصول — همان چیزی که موقع فعال‌سازی
#  به سرور اعلام می‌شود تا در پنل مدیریت ظاهر شود.
# ══════════════════════════════════════════════════════════════
AVAILABLE_FEATURES = [
    {'key': 'students', 'label': 'مدیریت هنرجویان',
     'description': 'فهرست، ثبت، ویرایش و پرونده هنرجویان، کارت و QR'},
    {'key': 'teachers', 'label': 'مدیریت مدرسان',
     'description': 'فهرست و پرونده مدرسان، برنامه و رتبه‌بندی'},
    {'key': 'courses', 'label': 'دوره‌ها و رشته‌ها',
     'description': 'تعریف رشته‌ها، دوره‌ها و سرفصل‌ها'},
    {'key': 'classes', 'label': 'کلاس‌ها و جلسات',
     'description': 'ایجاد کلاس، تقویم، جلسات، ادغام و تفکیک کلاس'},
    {'key': 'registration', 'label': 'ثبت‌نام',
     'description': 'ثبت‌نام هنرجو در دوره، ثبت‌نام سریع و انصراف'},
    {'key': 'attendance', 'label': 'حضور و غیاب',
     'description': 'ثبت حضور، گزارش غیبت و دستگاه‌های حضور و غیاب'},
    {'key': 'exams', 'label': 'آزمون‌ها و نمرات',
     'description': 'آزمون، بانک سوالات، ثبت نمره و کارنامه'},
    {'key': 'finance', 'label': 'امور مالی',
     'description': 'پرداخت‌ها، صندوق، بانک، چک، هزینه‌ها و تخفیف‌ها'},
    {'key': 'installments', 'label': 'اقساط',
     'description': 'داشبورد اقساط، پرداخت قسط، جریمه دیرکرد و یادآوری'},
    {'key': 'accounting', 'label': 'حسابداری',
     'description': 'دفتر کل، روزنامه، معین، تراز و سود و زیان'},
    {'key': 'payroll', 'label': 'حقوق و دستمزد',
     'description': 'قرارداد، محاسبه حقوق، فیش حقوقی و هزینه‌های پیشرفته'},
    {'key': 'tax', 'label': 'مالیات',
     'description': 'محاسبه‌گر مالیات، لیست ماهانه و گزارش سالانه'},
    {'key': 'reports', 'label': 'گزارش‌ها',
     'description': 'گزارش‌های هنرجو، مالی، حضور، ثبت‌نام و رتبه‌بندی'},
    {'key': 'analytics', 'label': 'تحلیل هوشمند',
     'description': 'پیش‌بینی ثبت‌نام، ریزش، بدهکاران پرخطر و دستیار هوشمند'},
    {'key': 'messaging', 'label': 'پیام‌رسانی و پیامک',
     'description': 'ارسال پیامک، پیام داخلی، قالب‌ها و یادآورهای خودکار'},
    {'key': 'integrations', 'label': 'اتصالات (تلگرام، بله، پنل پیامک)',
     'description': 'پیکربندی ربات‌ها، وب‌هوک‌ها و پنل پیامکی'},
    {'key': 'bot_panel', 'label': 'پنل ربات',
     'description': 'کاربران ربات، پیام همگانی، کیبوردها و آمار'},
    {'key': 'certificates', 'label': 'گواهینامه‌ها',
     'description': 'صدور، چاپ، استعلام و قالب گواهینامه'},
    {'key': 'crm', 'label': 'باشگاه مشتریان و پشتیبانی',
     'description': 'شکایات، نظرسنجی، تیکت، اهداف، مشتریان سازمانی و نمایندگی'},
    {'key': 'teacher_portal', 'label': 'پرتال مدرس',
     'description': 'پنل اختصاصی مدرس: کلاس‌ها، برنامه، حقوق و ارزیابی'},
    {'key': 'user_management', 'label': 'کاربران و سطوح دسترسی',
     'description': 'تعریف کاربر، نقش، مجوزها و تنظیمات امنیتی'},
    {'key': 'backup', 'label': 'پشتیبان‌گیری و بازیابی',
     'description': 'ساخت، دانلود، بازیابی، رمزگذاری و آزمون فایل پشتیبان'},
    {'key': 'export_data', 'label': 'خروجی اکسل و PDF',
     'description': 'دانلود خروجی CSV/PDF گزارش‌ها و فهرست‌ها'},
    {'key': 'hardware_devices', 'label': 'دستگاه‌های سخت‌افزاری',
     'description': 'دستگاه حضور، بارکدخوان، چاپگر کارت، POS و دوربین'},
    {'key': 'advanced_tools', 'label': 'ابزارهای پیشرفته',
     'description': 'فرم‌ساز، قالب چاپ، پاکسازی و نگهداری پایگاه‌داده'},
]

FEATURE_KEYS = frozenset(item['key'] for item in AVAILABLE_FEATURES)

FEATURE_LABELS = {item['key']: item['label'] for item in AVAILABLE_FEATURES}


# ══════════════════════════════════════════════════════════════
#  مسیرهایی که بدون لایسنس هم باید کار کنند
#  (صفحه فعال‌سازی خودش با پیشوند license. شناسایی می‌شود)
# ══════════════════════════════════════════════════════════════
LICENSE_EXEMPT_ENDPOINTS = frozenset({
    'static',
    'favicon',
    'auth.login',
    'auth.logout',
})

LICENSE_BLUEPRINT_PREFIX = 'license.'


# ══════════════════════════════════════════════════════════════
#  مسیرهایی که لایسنس معتبر می‌خواهند ولی به هیچ بخشی قفل نمی‌شوند
#  (داشبورد، تنظیمات پایه، سلامت سیستم، تنظیمات ظاهری کاربر)
# ══════════════════════════════════════════════════════════════
UNLOCKED_ENDPOINTS = frozenset({
    'dashboard.index',
    # ویزارد نصب و پیکربندی دیتابیس
    'setup.wizard',
    'setup.database_settings',
    'setup.test_db',
    # اطلاعات شبکه و سلامت
    'network.network_info',
    'network.api_network',
    'features.system_health',
    'features.security_log',
    'features.global_search',
    'features.help_center',
    'features.suggestions',
    'features.license_management',
    'features.toggle_dark_mode',
    'features2.network_status',
    'features2.test_connection',
    'features2.check_update',
    'features2.support_center',
    # ترجیحات ظاهری و میان‌بُرها
    'features2.change_language',
    'features2.change_theme',
    'features2.keyboard_shortcuts',
    'features2.view_favorites',
    'features2.toggle_favorite',
    'features2.customize_dashboard',
    'final.toggle_dark',
    'final.advanced_search',
    'final.advanced_health',
    # تنظیمات پایه آموزشگاه
    'settings.index',
    'settings.general',
    'settings.branches',
    'settings.add_branch',
    'settings.logs',
    'settings_panel.control_panel',
    'settings_panel.general_config',
    'settings_panel.diagnostics',
    'settings_panel.repair_diagnostics',
    'settings_panel.api_status',
})


# ══════════════════════════════════════════════════════════════
#  نگاشت پیش‌فرض بلوپرینت → بخش
#  (بلوپرینت‌هایی که کاملاً متعلق به یک بخش هستند)
# ══════════════════════════════════════════════════════════════
BLUEPRINT_FEATURES = {
    'students': 'students',
    'teachers': 'teachers',
    'classes': 'classes',
    'registration': 'registration',
    'attendance': 'attendance',
    'exams': 'exams',
    'finance': 'finance',
    'accounting': 'accounting',
    'payroll': 'payroll',
    'tax': 'tax',
    'reports': 'reports',
    'messaging': 'messaging',
    'certificates': 'certificates',
    'analytics': 'analytics',
    'bot_panel': 'bot_panel',
    'teacher_portal': 'teacher_portal',
    'perms': 'user_management',
    'complaints': 'crm',
    'surveys': 'crm',
    'tickets': 'crm',
    'goals': 'crm',
}


# ══════════════════════════════════════════════════════════════
#  نگاشت دقیق endpoint → بخش
#  برای بلوپرینت‌های چندمنظوره (features, features2, final,
#  new_features, settings, settings_panel) و استثناهای بلوپرینت‌ها.
# ══════════════════════════════════════════════════════════════
ENDPOINT_FEATURES = {
    # ── features_bp ─────────────────────────────────────────
    'features.create_backup': 'backup',
    'features.list_backups': 'backup',
    'features.restore_backup': 'backup',
    'features.download_backup': 'backup',
    'features.delete_backup': 'backup',
    'features.merge_class': 'classes',
    'features.split_class': 'classes',
    'features.print_class_list': 'classes',
    'features.student_qr': 'students',
    'features.student_card': 'students',
    'features.auto_generate_exam': 'exams',
    'features.report_card': 'exams',
    'features.bulk_report_card': 'exams',
    'features.check_alerts': 'finance',
    'features.teacher_ranking': 'teachers',
    'features.course_ranking': 'reports',
    'features.branch_ranking': 'reports',
    'features.staff_ranking': 'reports',
    'features.export_students_csv': 'export_data',
    'features.export_payments_csv': 'export_data',
    'features.usage_analytics': 'analytics',
    'features.birthday_check': 'messaging',
    'features.bulk_certificates': 'certificates',
    'features.workflows': 'advanced_tools',

    # ── features2_bp ────────────────────────────────────────
    'features2.attendance_device': 'hardware_devices',
    'features2.sync_attendance': 'hardware_devices',
    'features2.barcode_scanner': 'hardware_devices',
    'features2.barcode_lookup': 'hardware_devices',
    'features2.card_printer': 'hardware_devices',
    'features2.pos_terminal': 'hardware_devices',
    'features2.security_cameras': 'hardware_devices',
    'features2.authorized_devices': 'user_management',
    'features2.two_factor': 'user_management',
    'features2.optimize_database': 'advanced_tools',
    'features2.repair_database': 'advanced_tools',
    'features2.database_stats': 'advanced_tools',
    'features2.database_log': 'advanced_tools',
    'features2.data_cleanup': 'advanced_tools',
    'features2.document_versions': 'advanced_tools',
    'features2.form_builder': 'advanced_tools',
    'features2.print_templates': 'advanced_tools',
    'features2.demo_mode': 'advanced_tools',
    'features2.encrypt_backup': 'backup',
    'features2.test_backup': 'backup',
    'features2.suggested_courses': 'students',
    'features2.enrollment_forecast': 'analytics',
    'features2.churn_analysis': 'analytics',
    'features2.high_risk_debtors': 'analytics',
    'features2.customer_behavior': 'analytics',
    'features2.marketing_suggestions': 'analytics',
    'features2.smart_assistant': 'analytics',
    'features2.staff_rewards': 'reports',
    'features2.custom_report': 'reports',
    'features2.crisis_alert': 'messaging',
    'features2.corporate_clients': 'crm',
    'features2.add_corporate': 'crm',
    'features2.franchise': 'crm',
    'features2.polls': 'crm',

    # ── final_bp ────────────────────────────────────────────
    'final.multi_register': 'registration',
    'final.corporate_invoice': 'crm',
    'final.auto_sms_triggers': 'messaging',
    'final.trigger_registration_sms': 'messaging',
    'final.trigger_absence_sms': 'messaging',
    'final.trigger_birthday_sms': 'messaging',
    'final.trigger_payment_sms': 'messaging',

    # ── new_features_bp ─────────────────────────────────────
    'new_features.course_list': 'courses',
    'new_features.course_add': 'courses',
    'new_features.course_view': 'courses',
    'new_features.course_edit': 'courses',
    'new_features.class_pdf': 'classes',
    'new_features.attendance_sheet': 'classes',
    'new_features.telegram_settings': 'integrations',
    'new_features.set_telegram_webhook': 'integrations',
    'new_features.telegram_webhook': 'integrations',
    'new_features.bale_settings': 'integrations',
    'new_features.bale_webhook': 'integrations',
    'new_features.farazsms_settings': 'integrations',
    'new_features.farazsms_send': 'messaging',
    'new_features.send_installment_reminders': 'messaging',
    'new_features.installment_dashboard': 'installments',
    'new_features.pay_installment': 'installments',
    'new_features.batch_reminders': 'installments',
    'new_features.installment_report': 'installments',
    'new_features.auto_late_fee': 'installments',

    # ── settings_bp ─────────────────────────────────────────
    'settings.users': 'user_management',
    'settings.add_user': 'user_management',
    'settings.edit_user': 'user_management',
    'settings.roles': 'user_management',
    'settings.add_role': 'user_management',
    'settings.fields': 'courses',
    'settings.add_field': 'courses',
    'settings.courses': 'courses',
    'settings.add_course': 'courses',
    'settings.rooms': 'classes',
    'settings.add_room': 'classes',
    'settings.academic_year': 'classes',
    'settings.add_academic_year': 'classes',
    'settings.expense_categories': 'finance',
    'settings.add_expense_category': 'finance',
    'settings.edit_expense_category': 'finance',
    'settings.delete_expense_category': 'finance',
    'settings.expense_categories_pdf': 'export_data',
    'settings.sms': 'messaging',
    'settings.message_templates': 'messaging',
    'settings.add_message_template': 'messaging',
    'settings.backup': 'backup',
    'settings.cert_templates': 'certificates',

    # ── settings_panel_bp ───────────────────────────────────
    'settings_panel.backup_config': 'backup',
    'settings_panel.create_backup': 'backup',
    'settings_panel.telegram_config': 'integrations',
    'settings_panel.set_telegram_webhook': 'integrations',
    'settings_panel.test_telegram_message': 'integrations',
    'settings_panel.bale_config': 'integrations',
    'settings_panel.set_bale_webhook': 'integrations',
    'settings_panel.start_bale_polling': 'integrations',
    'settings_panel.stop_bale_polling': 'integrations',
    'settings_panel.test_bale_message': 'integrations',
    'settings_panel.farazsms_config': 'integrations',
    'settings_panel.check_farazsms': 'integrations',
    'settings_panel.test_farazsms': 'integrations',
    'settings_panel.farazsms_bulk': 'messaging',
    'settings_panel.farazsms_installment_reminders': 'messaging',

    # ── استثناهای بلوپرینت‌های تک‌بخشی ──────────────────────
    'finance.expenses_pdf': 'export_data',
    'demo.create_demo': 'advanced_tools',
}


def is_exempt_endpoint(endpoint):
    """آیا این مسیر بدون لایسنس هم باید کار کند؟"""
    if not endpoint:
        return True
    return endpoint in LICENSE_EXEMPT_ENDPOINTS or endpoint.startswith(LICENSE_BLUEPRINT_PREFIX)


def feature_for_endpoint(endpoint):
    """
    بخشِ مربوط به یک endpoint را برمی‌گرداند.
    None یعنی «لایسنس لازم است ولی این مسیر به بخشی قفل نمی‌شود».
    """
    if not endpoint or endpoint in UNLOCKED_ENDPOINTS:
        return None
    feature = ENDPOINT_FEATURES.get(endpoint)
    if feature:
        return feature
    blueprint = endpoint.rsplit('.', 1)[0] if '.' in endpoint else ''
    return BLUEPRINT_FEATURES.get(blueprint)


def audit_endpoint_coverage(url_map):
    """
    گزارش پوشش نگاشت: هر endpointی که نه معاف است، نه بدون قفل و
    نه به بخشی نگاشت شده، اینجا فهرست می‌شود.
    خروجی برای لاگ راه‌اندازی و آزمون‌های داخلی استفاده می‌شود.
    """
    unmapped = []
    per_feature = {key: [] for key in FEATURE_KEYS}
    unknown_keys = set()

    for rule in url_map.iter_rules():
        endpoint = rule.endpoint
        if is_exempt_endpoint(endpoint) or endpoint in UNLOCKED_ENDPOINTS:
            continue
        feature = feature_for_endpoint(endpoint)
        if feature is None:
            unmapped.append(endpoint)
        elif feature in per_feature:
            per_feature[feature].append(rule.rule)
        else:
            unknown_keys.add(feature)

    return {
        'unmapped': sorted(set(unmapped)),
        'unknown_keys': sorted(unknown_keys),
        'unused_features': sorted(key for key, rules in per_feature.items() if not rules),
        'per_feature': {key: sorted(set(rules)) for key, rules in per_feature.items()},
    }
