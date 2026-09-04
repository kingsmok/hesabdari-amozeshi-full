"""منطق گزارش‌ساز سفارشی (`/reports/custom-builder`)

چرا این فایل جدا است: مسیر گزارش‌سار ابتدا با `login_required` خالی باز بود و
هیچ ستونی را فیلتر نمی‌کرد. چون فرم **انتخاب ستون نداشت**، شرط
«ستون‌های مجاز همان جدول» عملاً یعنی *همهٔ ستون‌ها* ⇒ هر کاربر واردشده
می‌توانست با `table=users` هشِ رمز همهٔ حساب‌ها را در قالب یک جدول ببیند.

سه کنترل:
۱) فقط مدیر کل (ساختنِ query دلخواه روی هر جدولی، ابزار کار پرسنل نیست؛
   گزارش‌های آماده برای نقش‌ها در همین بخش وجود دارد)؛
۲) جدول‌های اعتبارنامه/نشست هرگز قابل انتخاب نیستند (`DENIED_TABLES`)؛
۳) ستون‌های حساس (هش، توکن، salt، سشن…) در فهرست ستون‌ها و در خروجی حذف
   می‌شوند — حتی برای مدیر کل، چون این صفحه یک *گزارش* است نه عیب‌یابی.

ساخت query با SQLAlchemy Core و از روی شیء `Table` انجام می‌شود؛ نام جدول یا
ستون هرگز به‌صورت رشته داخل SQL نمی‌رود، پس تزریق ممکن نیست.
"""
import re

from extensions import db

# جداولی که در گزارش‌ساز قابل انتخاب نیستند (دسترسی‌شان از مسیرهای مخصوص خودش
# و با تأیید مجدد انجام می‌شود، نه از یک گرید عمومی)
DENIED_TABLES = frozenset({
    'users', 'user_sessions', 'roles', 'permissions', 'role_permissions',
    'bot_tokens', 'bot_users', 'remember_me_tokens',
})

#: نام‌های دقیقِ شناخته‌شده (هیچ ستون کاری‌ای این نام‌ها را ندارد)
SENSITIVE_EXACT = frozenset({
    'password', 'password_hash', 'passwd', 'pwd', 'salt', 'secret', 'secret_key',
    'api_key', 'apikey', 'access_key', 'private_key', 'token', 'auth_token',
    'access_token', 'refresh_token', 'remember_token', 'session_token', 'csrf_token',
    'otp', 'otp_code', 'reset_token', 'activation_code', 'api_secret',
})

#: پسوند/پیشوندِ امنیتی؛ *لنگر* دارد تا `total_sessions` یا `session_rate`
#: (که ستون‌های کاری‌اند) فیلتر نشوند — تجربهٔ این مخزن نشان داد فیلتر
#: شلِ «هرچی session توش هست» ابزار گزارش‌گیری را فلج می‌کند.
SENSITIVE_SUFFIX = re.compile(r'(^|_)(token|api_?key|apikey|secret|password|passwd|private_?key)$',
                              re.IGNORECASE)

DEFAULT_LIMIT = 50
MAX_LIMIT = 500


def is_sensitive_column(name: str) -> bool:
    lowered = (name or '').lower()
    return lowered in SENSITIVE_EXACT or bool(SENSITIVE_SUFFIX.search(lowered))


def table_names():
    """فهرست جدول‌های قابل نمایش در گزارش‌ساز."""
    return sorted(name for name in db.metadata.tables if name not in DENIED_TABLES)


def resolve_table(name: str):
    """شیء `Table` یا None (جدول ناموجود یا ممنوع)."""
    if not name or name in DENIED_TABLES:
        return None
    return db.metadata.tables.get(name)


def visible_columns(table) -> list:
    return [column.name for column in table.columns if not is_sensitive_column(column.name)]


def clamp_limit(raw) -> int:
    try:
        limit = int(raw)
    except (TypeError, ValueError):
        limit = DEFAULT_LIMIT
    return max(1, min(limit, MAX_LIMIT))


def build_query(table_name: str, requested_columns=None, raw_limit=None):
    """خروجی: (columns, statement) — یا (None، پیام خطا) در ورودی نامعتبر.

    نام‌های درخواستی که در جدول نیستند یا حساس‌اند نادیده گرفته می‌شوند؛ اگر
    *همه* مردود بودند خطای خوانا برمی‌گردد (نه fallback به «همهٔ ستون‌ها»).
    """
    table = resolve_table(table_name)
    if table is None:
        return None, 'جدول انتخاب‌شده معتبر نیست یا در گزارش‌ساز مجاز نیست.'

    allowed = {column.name for column in table.columns}
    requested = [name for name in (requested_columns or []) if name in allowed]
    blocked = [name for name in (requested_columns or []) if name not in allowed]
    if not requested:
        return None, ('دست‌کم یک ستون غیرحساس انتخاب کنید.' if requested_columns or blocked
                      else 'حداقل یک ستون انتخاب کنید.')
    sensitive = [name for name in requested if is_sensitive_column(name)]
    safe = [name for name in requested if not is_sensitive_column(name)]
    if not safe:
        return None, 'ستون‌های انتخابی حساس هستند و قابل نمایش نیستند.'

    columns = [table.columns[name] for name in safe]
    statement = db.select(*columns).limit(clamp_limit(raw_limit))
    note = None
    if sensitive:
        note = f'ستون‌های حساس حذف شدند: {", ".join(sensitive)}'
    return (safe, statement), note
