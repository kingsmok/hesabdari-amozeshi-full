"""
آزمون بسته‌ی آپلود هاست (Python 3.11 / Passenger).

اجرا:
    pytest tests/test_deploy_host.py -q
"""
import ast
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import deploy_host  # noqa: E402


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestRequiredHostFiles:
    def test_every_required_file_exists_in_repo(self):
        missing = [
            f for f in deploy_host.REQUIRED_FILES
            if not os.path.isfile(os.path.join(ROOT, f))
        ]
        assert missing == [], f"فایل‌های لازم هاست در ریپو نیستند: {missing}"

    def test_every_required_dir_exists(self):
        missing = [
            d for d in deploy_host.DIRS
            if not os.path.isdir(os.path.join(ROOT, d))
        ]
        assert missing == [], f"پوشه‌های لازم هاست نیستند: {missing}"

    def test_startup_checks_is_packed(self):
        """app.py این ماژول را در سطح بالا import می‌کند؛ بدون آن هاست ۵۰۰ می‌دهد."""
        assert "startup_checks.py" in deploy_host.REQUIRED_FILES

    def test_desktop_only_files_are_not_packed(self):
        packed = set(deploy_host.REQUIRED_FILES)
        for name in ("app_desktop.py", "start_desktop.bat", "run.bat"):
            assert name not in packed

    def test_wsgi_entry_points_are_packed(self):
        packed = set(deploy_host.REQUIRED_FILES)
        assert "passenger_wsgi.py" in packed
        assert "wsgi.py" in packed
        assert ".htaccess" in packed
        assert "requirements.txt" in packed

    def test_layout_includes_responsive_stylesheet(self):
        layout = open(os.path.join(ROOT, "templates", "base", "layout.html"), encoding="utf-8").read()
        assert "css/responsive.css" in layout
        assert os.path.isfile(os.path.join(ROOT, "static", "css", "responsive.css"))

    def test_app_py_local_imports_are_available_on_host(self):
        """importهای سطح بالای app.py که مال خود پروژه‌اند باید در بسته هاست باشند."""
        src = open(os.path.join(ROOT, "app.py"), encoding="utf-8").read()
        tree = ast.parse(src)
        packed_modules = {
            os.path.splitext(f)[0] for f in deploy_host.REQUIRED_FILES if f.endswith(".py")
        }
        packed_packages = set(deploy_host.DIRS)
        local = []
        for node in tree.body:
            if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                root_mod = node.module.split(".")[0]
                local.append(root_mod)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    local.append(alias.name.split(".")[0])
        third_party = {
            "os", "sys", "flask", "json", "secrets", "datetime",
            "threading", "apscheduler", "jdatetime", "time",
        }
        missing = []
        for name in local:
            if name in third_party:
                continue
            if name in packed_modules or name in packed_packages:
                continue
            missing.append(name)
        assert missing == [], f"ماژول‌های app.py که به هاست نمی‌روند: {missing}"
