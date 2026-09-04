"""نگهبان‌های مخزن: چه فایل‌هایی نباید هرگز commit شوند.

ریشه این آزمون، نشتی واقعی این مخزن است: `instance/academy.db` (دیتابیس کامل با
هشِ رمزها و دادهٔ هنرجویان) و `cookies.txt` یک‌بار track شدند و تا ابد در
تاریخچه یک مخزن **عمومی** ماندند — `git rm --cached` فقط آینده را نجات می‌دهد.
پس علاوه بر `.gitignore`، خودِ فهرست فایل‌های track شده هم بررسی می‌شود.

روی نصب‌های بسته‌بندی‌شده (PyInstaller) که `.git` ندارند، آزمون skip می‌شود.
"""
import os
import re
import subprocess
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

# هرچه داده کاربر، نشست، یا کلید است
FORBIDDEN = re.compile(
    r'('
    r'\.db$|\.db-wal$|\.db-shm$|\.db-journal$'   # دیتابیس و فایل‌های کمکی SQLite
    r'|\.sqlite3?$'
    r'|cookies\.txt$'                            # کوکی نشستِ ذخیره‌شده با curl
    r'|\.pyc$|__pycache__/'                      # بایت‌کد (مسیر مطلق لو می‌دهد)
    r'|(^|/)\.env(\.|$)'                         # متغیرهای محیطی
    r'|\.pem$|credentials|secret_key\.py'
    r')'
)


def _tracked_files():
    try:
        out = subprocess.run(
            ['git', '-C', REPO_ROOT, 'ls-files', '-z'],
            capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        pytest.skip('git در این محیط در دسترس نیست')
    if out.returncode != 0:
        pytest.skip('این مسیر یک مخزن git نیست (نصب بسته‌بندی‌شده؟)')
    return [name for name in out.stdout.split('\0') if name]


class TestTrackedFiles:
    def test_no_database_or_credential_files_are_tracked(self):
        offenders = sorted(name for name in _tracked_files() if FORBIDDEN.search(name))
        assert not offenders, (
            'این فایل‌ها داده/راز دارند و نباید در تاریخچه مخزن عمومی بمانند: '
            + ', '.join(offenders[:10]))

    def test_instance_directory_only_holds_placeholders(self):
        tracked = _tracked_files()
        inside = [name for name in tracked if name.startswith('instance/')]
        stray = [name for name in inside if not name.endswith(('.gitkeep', '.gitignore',
                                                               'README.md'))]
        assert not stray, f'فایل‌های زیر داخل instance/ نباید track شوند: {stray}'


class TestGitignoreGuards:
    """`.gitignore` باید کنار فایل‌های WAL را هم بپوشاند، وگرنه یک `git add -A`
    می‌تواند `academy.db-wal` را با دادهٔ تازه به مخزن عمومی برگرداند."""

    def _gitignore(self):
        path = os.path.join(REPO_ROOT, '.gitignore')
        if not os.path.isfile(path):
            pytest.skip('فایل .gitignore در این نصب وجود ندارد')
        with open(path, encoding='utf-8') as handle:
            return handle.read()

    @pytest.mark.parametrize('entry', ['instance/*.db', 'instance/*.db-wal',
                                      'instance/*.db-shm', 'instance/*.db-journal'])
    def test_sqlite_artifacts_ignored(self, entry):
        lines = [line.strip() for line in self._gitignore().splitlines()]
        assert entry in lines, f'`{entry}` به .gitignore اضافه شود'

    def test_database_backup_does_not_copy_raw_file(self):
        """با حالت WAL، کپی فایلِ خام می‌تواند دیتابیس نیمه‌کاره بدهد؛
        پشتیبان‌گیری باید از Backup API استفاده کند (همین حالا همین‌طور است)."""
        import inspect
        from utils.database_tools import sqlite_backup
        body = inspect.getsource(sqlite_backup)
        assert '.backup(' in body, 'sqlite_backup باید از Connection.backup استفاده کند'
        assert 'shutil.copy' not in body, 'کپی خام فایل دیتابیس برای پشتیبان مجاز نیست'


class TestHistoryOfThisBranch:
    """تاریخچه همین برنچ هم باید پاک باشد.

    `git rm --cached` فایل را از این پس حذف می‌کند ولی بلاب‌های گذشته دست‌نخورده
    می‌مانند — در مخزن عمومی، همان بلاب قابل دانلود است. پس معیارِ «پاک بودن»،
    فهرست فایل‌های تمام کامیت‌های `HEAD` است (نه فقط index).
    """

    def test_no_sensitive_blobs_in_committed_history(self):
        try:
            out = subprocess.run(
                ['git', '-C', REPO_ROOT, 'log', 'HEAD', '--pretty=format:', '--name-only', '-z'],
                capture_output=True, text=True, timeout=60)
        except (OSError, subprocess.SubprocessError):
            pytest.skip('git در این محیط در دسترس نیست')
        if out.returncode != 0:
            pytest.skip('تاریخچه git در این نصب در دسترس نیست')
        names = {item for item in out.stdout.split('\0') if item}
        offenders = sorted(name for name in names if FORBIDDEN.search(name))
        assert not offenders, (
            f'{len(offenders)} فایل حساس در تاریخچه این برنچ هست؛ بازنویسی تاریخچه '
            '(git filter-repo) لازم است. نمونه: ' + ', '.join(offenders[:6]))
