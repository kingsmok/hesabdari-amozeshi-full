"""
آزمون‌های سلامت APIی Qt در app_desktop.py.

چرا این فایل وجود دارد؟
    خطاهایی از این دست هیچ‌وقت هنگام import یا بسته‌بندی دیده نمی‌شوند و فقط وقتی
    کاربر دکمه‌ای را می‌زند بیرون می‌زنند:

        AttributeError: type object 'ShortcutContext' has no attribute
                        'WindowWithChildrenContext'          ← هنگام ساخت پنجره
        AttributeError: 'QWebEngineDownloadRequest' object has no attribute
                        'setPath' / 'finished' / 'interrupted'  ← هنگام دانلود
        TypeError: int() argument must be ... not 'DialogCode'    ← هنگام چاپ

    بخش اول این آزمون‌ها بدون نیاز به نصب PyQt6 اجرا می‌شود (بررسی الگوهای ممنوع)،
    بخش دوم در صورت نصب بودن PyQt6، تمام ارجاع‌ها را با stubهای رسمی تطبیق می‌دهد.

اجرا:
    pytest tests/test_desktop_qt_api.py -q
"""
import ast
import os
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

DESKTOP = os.path.join(ROOT, 'app_desktop.py')
SOURCE = open(DESKTOP, encoding='utf-8').read()


def _has_pyqt6() -> bool:
    try:                                   # فقط برای بخش دوم لازم است
        import PyQt6  # noqa: F401
        return True
    except Exception:
        return False


class TestNoRemovedQt5Api:
    """متدها و enumهایی که در Qt6 حذف شده‌اند و باعث AttributeError می‌شوند."""

    def test_download_uses_qt6_api(self):
        """setPath / finished / interrupted مال Qt5 (QWebEngineDownloadItem) هستند."""
        for banned in ('download.setPath', 'download.finished', 'download.interrupted'):
            assert banned not in SOURCE, (
                f"«{banned}» متعلق به Qt5 است؛ در Qt6 از setDownloadDirectory/"
                "setDownloadFileName و stateChanged استفاده کن")

    def test_download_sets_directory_and_filename(self):
        assert 'setDownloadDirectory(' in SOURCE
        assert 'setDownloadFileName(' in SOURCE

    def test_download_state_is_compared_to_enum(self):
        """مقایسه با عدد ۰ یعنی DownloadRequested (شروع)، نه پایان دانلود."""
        assert 'DownloadCompleted' in SOURCE
        assert not re.search(r"int\(getattr\(state", SOURCE)

    def test_no_int_on_qt_enums(self):
        """`int(QDialog.DialogCode.Accepted)` روی enumهای PyQt6 خطا می‌دهد."""
        offenders = re.findall(r"(?<![\w.])int\(\s*(Q[A-Za-z0-9]+\.[A-Za-z0-9]+\.[A-Za-z0-9]+)",
                               SOURCE)
        assert not offenders, f"int() روی enum Qt ممنوع است: {offenders}"

    def test_shortcut_context_is_a_real_pyqt6_value(self):
        valid = {'WidgetShortcut', 'WindowShortcut', 'ApplicationShortcut',
                 'WidgetWithChildrenShortcut'}
        used = re.findall(r"setContext\(\s*Qt\.ShortcutContext\.(\w+)", SOURCE)
        assert used, "هیچ shortcut contextای پیدا نشد"
        assert set(used) <= valid, f"context نامعتبر: {set(used) - valid}"

    def test_no_retry_role(self):
        """`QMessageBox.ButtonRole.RetryRole` وجود ندارد (تا ApplyRole می‌رود)."""
        assert 'ButtonRole.RetryRole' not in SOURCE

    def test_dialog_result_compared_as_enum(self):
        assert re.search(r"QDialog\.DialogCode\(dialog\.exec\(\)\)", SOURCE)


class TestSourceStillImportsCleanly:
    def test_module_parses(self):
        tree = ast.parse(SOURCE)
        assert any(isinstance(n, ast.ClassDef) and n.name == 'MainWindow' for n in tree.body)


@pytest.mark.skipif(not _has_pyqt6(), reason='PyQt6 نصب نیست؛ بررسی stubها رد می‌شود')
class TestAgainstOfficialStubs:
    """تطبیق تمام ارجاع‌های Qt با فایل‌های .pyi نصب‌شده (همان کاری که ابزار انجام می‌دهد)."""

    def test_every_qt_reference_exists(self):
        sys.path.insert(0, os.path.join(ROOT, 'tools'))
        import check_qt_api

        index, bases = check_qt_api.build_index(check_qt_api.collect_stub_dirs([]))
        problems = check_qt_api.check_file(__import__('pathlib').Path(DESKTOP), index, bases)
        assert not problems, "ارجاع نامعتبر Qt:\n" + "\n".join(
            f"  سطر {lineno}: {dotted} — {message}" for lineno, dotted, message in problems)
