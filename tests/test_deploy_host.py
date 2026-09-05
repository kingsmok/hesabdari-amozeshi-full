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

    def test_bootstrap_package_is_packed(self):
        """پکیج bootstrap (جداسازی مسئولیت‌های create_app) باید روی هاست برود."""
        assert "bootstrap" in deploy_host.DIRS
        assert os.path.isdir(os.path.join(ROOT, "bootstrap"))
        assert os.path.isfile(os.path.join(ROOT, "bootstrap", "blueprints.py"))
        assert os.path.isfile(os.path.join(ROOT, "bootstrap", "schema.py"))

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

    def test_vps_files_are_packed(self):
        """مسیر VPS (Gunicorn) هم باید از همان بسته قابل اجرا باشد."""
        packed = set(deploy_host.REQUIRED_FILES)
        assert "requirements-prod.txt" in packed
        assert "gunicorn.conf.py" in packed

    def test_logs_dir_is_a_runtime_dir(self):
        """لاگ چرخشی در logs/ نوشته می‌شود؛ باید از قبل ساخته و writable باشد."""
        assert "logs" in deploy_host.RUNTIME_DIRS

    def test_tmp_dir_exists_for_passenger_restart(self):
        """قرارداد ری‌استارت Passenger (touch tmp/restart.txt) به پوشه tmp نیاز دارد."""
        assert "tmp" in deploy_host.RUNTIME_DIRS

    def test_local_settings_are_never_copied(self):
        """settings.json محلی (راز/مسیر مطلق) نباید به هاست برود؛ نسخه‌ی تمیز
        درجای آن ساخته می‌شود."""
        assert "settings.json" not in deploy_host.REQUIRED_FILES
        assert "settings.json" not in deploy_host.OPTIONAL_FILES
        assert deploy_host.HOST_SETTINGS["database"]["type"] == "sqlite"
        assert "secret_key" not in deploy_host.HOST_SETTINGS.get("app", {})

    def test_htaccess_does_not_break_passenger(self):
        """ریدایرکت قدیمی به wsgi.py روی Passenger حلقه/404 می‌ساخت."""
        htaccess = open(os.path.join(ROOT, ".htaccess"), encoding="utf-8").read()
        assert "wsgi.py/$1" not in htaccess
        assert "wsgi.py/" not in htaccess
        # ولی سد امنیتی باید بماند
        assert "settings\\.json" in htaccess or "settings.json" in htaccess

    def test_passenger_entry_is_host_safe(self):
        """entry point باید application را صادر و تردهای پس‌زمینه را خاموش کند."""
        src = open(os.path.join(ROOT, "passenger_wsgi.py"), encoding="utf-8").read()
        assert "application" in src
        assert "ACADEMY_DISABLE_SCHEDULER" in src
        assert "ACADEMY_DISABLE_BALE" in src

    def test_mysql_driver_is_in_requirements(self):
        """انتخاب MySQL در ویزارد بدون PyMySQL روی هاست خطا می‌داد."""
        requirements = open(os.path.join(ROOT, "requirements.txt"),
                            encoding="utf-8").read()
        assert "PyMySQL" in requirements

    def test_all_local_imports_are_available_on_host(self):
        """همه‌ی importهای محلیِ همه‌ی فایل‌ها (نه فقط app.py) باید در بسته باشند."""
        problems = deploy_host._verify_staged_imports(ROOT)
        # روی خود ریپو همیشه باید سالم باشد (بسته زیرمجموعه‌ی ریپوست)
        assert problems == [], f"importهای گمشده: {problems[:5]}"

    def test_packaging_list_covers_codebase_imports(self):
        """هر ماژول ریشه‌ای که کدی در routes/models/utils/bootstrap به آن نیاز
        دارد باید در REQUIRED_FILES باشد (وگرنه هاست 500 می‌دهد)."""
        repo_modules = deploy_host._repo_root_modules()
        packed = {
            os.path.splitext(f)[0] for f in deploy_host.REQUIRED_FILES if f.endswith(".py")
        } | set(deploy_host.DIRS)
        needed = set()
        for package in ("routes", "models", "utils", "bootstrap"):
            folder = os.path.join(ROOT, package)
            for dirpath, _dirs, files in os.walk(folder):
                for name in files:
                    if not name.endswith(".py"):
                        continue
                    with open(os.path.join(dirpath, name), encoding="utf-8") as handle:
                        try:
                            tree = ast.parse(handle.read())
                        except SyntaxError:
                            continue
                    for node in ast.walk(tree):
                        if isinstance(node, ast.ImportFrom) and node.module \
                                and node.level == 0:
                            needed.add(node.module.split(".")[0])
                        elif isinstance(node, ast.Import):
                            for alias in node.names:
                                needed.add(alias.name.split(".")[0])
        missing = sorted(mod for mod in needed
                         if mod in repo_modules and mod not in packed)
        assert missing == [], f"ماژول‌هایی که بسته‌بندی نشده‌اند: {missing}"

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
            "threading", "apscheduler", "jdatetime", "time", "weakref",
        }
        missing = []
        for name in local:
            if name in third_party:
                continue
            if name in packed_modules or name in packed_packages:
                continue
            missing.append(name)
        assert missing == [], f"ماژول‌های app.py که به هاست نمی‌روند: {missing}"
