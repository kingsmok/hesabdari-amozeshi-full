"""
آزمون‌های نصب‌کننده‌ی هوشمند وابستگی‌ها (tools/install_deps.py).

ریشه‌ی این فایل یک خطای واقعی نصب است:

    × Building wheel for greenlet (pyproject.toml) did not run successfully.
    ERROR: Failed building wheel for greenlet
    error: failed-wheel-build-for-install

اجرا:
    pytest tests/test_install_deps.py -q
"""
import os
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(REPO_ROOT, "tools")
for path in (REPO_ROOT, TOOLS):
    if path not in sys.path:
        sys.path.insert(0, path)

import install_deps  # noqa: E402


REAL_PIP_ERROR = """
error: subprocess-exited-with-error

× Building wheel for greenlet (pyproject.toml) did not run successfully.
│ exit code: 1
╰─> No available output.

note: This error originates from a subprocess, and is likely not a problem with pip.
ERROR: Failed building wheel for greenlet
error: failed-wheel-build-for-install

× Failed to build installable wheels for some pyproject.toml based projects
╰─> greenlet
"""


class TestGreenletFailureDetection:
    def test_detects_the_reported_error(self):
        assert install_deps.is_greenlet_failure(REAL_PIP_ERROR) is True

    def test_detects_missing_wheel_variant(self):
        text = "ERROR: Could not find a version that satisfies the requirement greenlet"
        assert install_deps.is_greenlet_failure(text) is True

    def test_ignores_other_build_failures(self):
        assert install_deps.is_greenlet_failure(
            "ERROR: Failed building wheel for cryptography") is False

    def test_ignores_success_output(self):
        assert install_deps.is_greenlet_failure(
            "Successfully installed greenlet-3.5.5") is False

    def test_empty_output(self):
        assert install_deps.is_greenlet_failure("") is False
        assert install_deps.is_greenlet_failure(None) is False


class TestPipCheckParsing:
    def test_extracts_missing_names(self):
        out = (
            "flask 3.1.3 requires werkzeug>=3.1, which is not installed.\n"
            "flask-migrate 4.0.5 requires alembic>=1.9.0, which is not installed.\n"
        )
        assert install_deps.parse_missing_dependencies(out) == ["alembic", "werkzeug"]

    def test_greenlet_is_never_installed_in_fallback(self):
        """قلب راه‌حل: در حالت fallback نباید دوباره سراغ greenlet برویم."""
        out = "sqlalchemy 2.0.52 requires greenlet, which is not installed."
        assert install_deps.parse_missing_dependencies(out) == []

    def test_names_are_normalized_and_unique(self):
        out = (
            "a 1.0 requires Flask_SQLAlchemy, which is not installed.\n"
            "b 1.0 requires flask-sqlalchemy, which is not installed.\n"
        )
        assert install_deps.parse_missing_dependencies(out) == ["flask-sqlalchemy"]

    def test_clean_environment(self):
        assert install_deps.parse_missing_dependencies("No broken requirements found.") == []
        assert install_deps.parse_missing_dependencies("") == []

    def test_version_conflicts_are_not_treated_as_missing(self):
        out = "flask 3.1.3 has requirement werkzeug>=3.1, but you have werkzeug 2.0.0."
        assert install_deps.parse_missing_dependencies(out) == []


class TestCommandBuilding:
    def test_pip_cmd_uses_current_interpreter(self):
        cmd = install_deps.pip_cmd("install", "x")
        assert cmd[:3] == [sys.executable, "-m", "pip"]

    def test_greenlet_wheel_command_never_compiles(self, monkeypatch):
        seen = {}

        def fake_run(cmd, dry_run=False, echo=True):
            seen["cmd"] = cmd
            return 0, ""

        monkeypatch.setattr(install_deps, "run", fake_run)
        ok, _ = install_deps.install_greenlet_wheel()
        assert ok is True
        assert "--only-binary=:all:" in seen["cmd"], "باید ساخت از سورس ممنوع باشد"
        assert seen["cmd"][-1] == "greenlet"

    def test_requirements_install_prefers_wheels(self, monkeypatch):
        seen = {}
        monkeypatch.setattr(
            install_deps, "run",
            lambda cmd, dry_run=False, echo=True: (seen.setdefault("cmd", cmd), (0, ""))[1])
        install_deps.install_requirements("requirements.txt")
        assert "--prefer-binary" in seen["cmd"]

    def test_fallback_installs_everything_without_deps(self, monkeypatch):
        calls = []

        def fake_run(cmd, dry_run=False, echo=True):
            calls.append(cmd)
            if "check" in cmd:
                return 0, "No broken requirements found."
            return 0, ""

        monkeypatch.setattr(install_deps, "run", fake_run)
        ok, _ = install_deps.install_without_greenlet("requirements.txt")
        assert ok is True
        assert "--no-deps" in calls[0]

    def test_fallback_loops_until_dependencies_resolved(self, monkeypatch):
        """pip check → نصب گم‌شده‌ها → دوباره pip check تا پاک شدن."""
        outputs = iter([
            "app 1.0 requires jinja2, which is not installed.\n"
            "sqlalchemy 2.0.52 requires greenlet, which is not installed.",
            "jinja2 3.1 requires markupsafe, which is not installed.",
            "sqlalchemy 2.0.52 requires greenlet, which is not installed.",
        ])
        installed = []

        def fake_run(cmd, dry_run=False, echo=True):
            if cmd[-1] == "check":
                return 0, next(outputs, "")
            if "install" in cmd:
                installed.append([c for c in cmd[4:] if not c.startswith("-")])
            return 0, ""

        monkeypatch.setattr(install_deps, "run", fake_run)
        ok, _ = install_deps.install_without_greenlet("requirements.txt")
        assert ok is True
        flat = [pkg for group in installed for pkg in group]
        assert "jinja2" in flat and "markupsafe" in flat
        assert "greenlet" not in flat, "greenlet نباید در حالت fallback نصب شود"


class TestRequirementsPin:
    """requirements.txt باید greenlet را برای پایتون ۳.۱۳+ کف‌بندی کند تا pip
    سراغ نسخه‌های بدون wheel نرود."""

    def _requirements(self):
        with open(os.path.join(REPO_ROOT, "requirements.txt"), encoding="utf-8") as fh:
            return fh.read()

    def test_greenlet_floor_present(self):
        lines = [ln.strip() for ln in self._requirements().splitlines()
                 if ln.strip().lower().startswith("greenlet")]
        assert lines, "کف نسخه greenlet در requirements.txt نیست"
        assert "3.2.4" in lines[0]
        assert "python_version" in lines[0], "باید فقط برای پایتون جدید اعمال شود"


class TestMainFlow:
    def test_greenlet_failure_triggers_recovery(self, monkeypatch, tmp_path):
        """سناریوی کاربر: نصب اول با خطای greenlet می‌شکند → باید خودکار جبران شود."""
        req = tmp_path / "requirements.txt"
        req.write_text("Flask==3.1.3\n", encoding="utf-8")
        steps = []

        monkeypatch.setattr(install_deps, "upgrade_pip", lambda dry_run=False: steps.append("pip"))
        monkeypatch.setattr(install_deps, "verify_imports", lambda dry_run=False: True)

        def fake_requirements(path, dry_run=False, extra=()):
            steps.append("install")
            # بار اول شکست greenlet، بار دوم موفق
            return (1, REAL_PIP_ERROR) if steps.count("install") == 1 else (0, "")

        monkeypatch.setattr(install_deps, "install_requirements", fake_requirements)
        monkeypatch.setattr(
            install_deps, "install_greenlet_wheel",
            lambda dry_run=False: (steps.append("greenlet-wheel"), (True, ""))[1])

        assert install_deps.main(["-r", str(req)]) == 0
        assert steps == ["pip", "install", "greenlet-wheel", "install"]

    def test_falls_back_to_no_greenlet_install(self, monkeypatch, tmp_path):
        req = tmp_path / "requirements.txt"
        req.write_text("Flask==3.1.3\n", encoding="utf-8")
        steps = []

        monkeypatch.setattr(install_deps, "upgrade_pip", lambda dry_run=False: True)
        monkeypatch.setattr(install_deps, "verify_imports", lambda dry_run=False: True)
        monkeypatch.setattr(
            install_deps, "install_requirements",
            lambda path, dry_run=False, extra=(): (1, REAL_PIP_ERROR))
        monkeypatch.setattr(
            install_deps, "install_greenlet_wheel",
            lambda dry_run=False: (False, "no wheel"))
        monkeypatch.setattr(
            install_deps, "install_without_greenlet",
            lambda path, dry_run=False, extra=(), max_rounds=6: (steps.append("no-greenlet"), (True, ""))[1])

        assert install_deps.main(["-r", str(req)]) == 0
        assert steps == ["no-greenlet"]

    def test_unrelated_failure_is_not_masked(self, monkeypatch, tmp_path):
        req = tmp_path / "requirements.txt"
        req.write_text("Flask==3.1.3\n", encoding="utf-8")
        monkeypatch.setattr(install_deps, "upgrade_pip", lambda dry_run=False: True)
        monkeypatch.setattr(
            install_deps, "install_requirements",
            lambda path, dry_run=False, extra=(): (1, "ERROR: Failed building wheel for cryptography"))

        def boom(*a, **k):  # نباید صدا زده شود
            raise AssertionError("برای خطای غیر greenlet نباید fallback اجرا شود")

        monkeypatch.setattr(install_deps, "install_greenlet_wheel", boom)
        monkeypatch.setattr(install_deps, "install_without_greenlet", boom)
        assert install_deps.main(["-r", str(req)]) == 1

    def test_missing_requirements_file(self, tmp_path):
        assert install_deps.main(["-r", str(tmp_path / "nope.txt")]) == 2


class TestInstallBatWiring:
    """install.bat باید همین مسیر امن را صدا بزند، نه pip خام را."""

    def test_install_bat_uses_helper(self):
        path = os.path.join(REPO_ROOT, "install.bat")
        if not os.path.isfile(path):
            pytest.skip("install.bat در این نصب نیست")
        with open(path, encoding="utf-8") as fh:
            content = fh.read()
        assert "tools\\install_deps.py" in content
        assert "--skip-greenlet" in content, "راهنمای fallback باید در پیام خطا باشد"
