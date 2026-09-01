"""
آزمون‌های بررسی سازگاری SQLAlchemy / پایتون ۳.۱۳ و ۳.۱۴.

اجرا:
    pytest tests/test_startup_checks.py -q
"""
import os
import sys
import types

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import startup_checks  # noqa: E402


class TestParseVersion:
    def test_standard(self):
        assert startup_checks.parse_version("2.0.31") == (2, 0, 31)

    def test_prerelease_uses_numeric_prefix(self):
        assert startup_checks.parse_version("2.0.31.post1") == (2, 0, 31)

    def test_empty_and_none(self):
        assert startup_checks.parse_version("") == (0,)
        assert startup_checks.parse_version(None) == (0,)


class TestCompatibility:
    def test_host_python311_accepts_sqlalchemy_20(self):
        """هاست Python 3.11 با SQLAlchemy 2.0.x (حتی قبل از 2.0.31) کار می‌کند."""
        assert startup_checks.sqlalchemy_is_compatible("2.0.23", (3, 11)) is True
        assert startup_checks.sqlalchemy_is_compatible("2.0.16", (3, 11)) is True
        assert startup_checks.sqlalchemy_is_compatible("2.0.52", (3, 11)) is True

    def test_sqlalchemy_14_rejected_everywhere(self):
        assert startup_checks.sqlalchemy_is_compatible("1.4.46", (3, 11)) is False
        assert startup_checks.sqlalchemy_is_compatible("1.4.46", (3, 14)) is False

    def test_old_sqlalchemy_rejected_only_on_313_plus(self):
        assert startup_checks.sqlalchemy_is_compatible("2.0.23", (3, 13)) is False
        assert startup_checks.sqlalchemy_is_compatible("2.0.23", (3, 14)) is False
        assert startup_checks.sqlalchemy_is_compatible("2.0.31", (3, 14)) is True

    def test_fixed_sqlalchemy_is_accepted(self):
        assert startup_checks.sqlalchemy_is_compatible("2.0.31") is True
        assert startup_checks.sqlalchemy_is_compatible("2.0.52") is True

    def test_missing_version_is_rejected(self):
        assert startup_checks.sqlalchemy_is_compatible(None) is False
        assert startup_checks.sqlalchemy_is_compatible("") is False

    def test_min_required_depends_on_python(self):
        assert startup_checks.min_sqlalchemy_required((3, 11)) == (2, 0, 16)
        assert startup_checks.min_sqlalchemy_required((3, 13)) == (2, 0, 31)
        assert startup_checks.min_sqlalchemy_required((3, 14)) == (2, 0, 31)


class TestDiagnose:
    def test_too_old_metadata_does_not_import(self, monkeypatch):
        """نسخه قدیمی باید از فراداده تشخیص داده شود؛ import نباید اجرا شود."""
        monkeypatch.setattr(startup_checks, "installed_sqlalchemy_version", lambda: "1.4.46")

        def boom():
            raise AssertionError("should not import sqlalchemy")

        monkeypatch.setattr(startup_checks, "try_import_sqlalchemy", boom)
        diag = startup_checks.diagnose_sqlalchemy()
        assert diag["ok"] is False
        assert diag["reason"] == "too_old"
        assert diag["version"] == "1.4.46"

    def test_python311_does_not_reject_sqlalchemy_2020(self, monkeypatch):
        """روی هاست 3.11 نسخه 2.0.20 نباید too_old باشد؛ باید import شود."""
        monkeypatch.setattr(startup_checks, "installed_sqlalchemy_version", lambda: "2.0.20")
        monkeypatch.setattr(startup_checks, "try_import_sqlalchemy", lambda: ("2.0.20", None))
        diag = startup_checks.diagnose_sqlalchemy(python_version=(3, 11, 0))
        assert diag["ok"] is True
        assert diag["reason"] == "ok"

    def test_python314_rejects_sqlalchemy_2020_without_import(self, monkeypatch):
        monkeypatch.setattr(startup_checks, "installed_sqlalchemy_version", lambda: "2.0.20")

        def boom():
            raise AssertionError("should not import sqlalchemy")

        monkeypatch.setattr(startup_checks, "try_import_sqlalchemy", boom)
        diag = startup_checks.diagnose_sqlalchemy(python_version=(3, 14, 0))
        assert diag["ok"] is False
        assert diag["reason"] == "too_old"

    def test_typingonly_assertion_is_caught(self, monkeypatch):
        monkeypatch.setattr(startup_checks, "installed_sqlalchemy_version", lambda: "2.0.52")
        err = AssertionError(
            "Class <class 'sqlalchemy.sql.elements.SQLCoreOperations'> "
            "directly inherits TypingOnly but has additional attributes "
            "{'__static_attributes__', '__firstlineno__'}."
        )
        monkeypatch.setattr(startup_checks, "try_import_sqlalchemy", lambda: (None, err))
        diag = startup_checks.diagnose_sqlalchemy()
        assert diag["ok"] is False
        assert diag["reason"] == "typingonly"

    def test_missing_package(self, monkeypatch):
        monkeypatch.setattr(startup_checks, "installed_sqlalchemy_version", lambda: None)
        monkeypatch.setattr(
            startup_checks,
            "try_import_sqlalchemy",
            lambda: (None, ImportError("No module named 'sqlalchemy'")),
        )
        diag = startup_checks.diagnose_sqlalchemy()
        assert diag["ok"] is False
        assert diag["reason"] == "missing"

    def test_compatible_import(self, monkeypatch):
        monkeypatch.setattr(startup_checks, "installed_sqlalchemy_version", lambda: "2.0.52")
        monkeypatch.setattr(startup_checks, "try_import_sqlalchemy", lambda: ("2.0.52", None))
        diag = startup_checks.diagnose_sqlalchemy()
        assert diag["ok"] is True
        assert diag["reason"] == "ok"


class TestEnsureCompatible:
    def test_incompatible_does_not_sys_exit_when_disabled(self, monkeypatch, capsys):
        monkeypatch.setattr(
            startup_checks,
            "diagnose_sqlalchemy",
            lambda: {"ok": False, "version": "2.0.20", "reason": "too_old", "error": None},
        )
        assert startup_checks.ensure_compatible(exit_on_error=False, auto_fix=False) is False
        out = capsys.readouterr().out
        assert "TypingOnly" in out or "۲.۰.۳۱" in out or "2.0.31" in out
        assert "pip install" in out

    def test_compatible_returns_true(self, monkeypatch):
        monkeypatch.setattr(
            startup_checks,
            "diagnose_sqlalchemy",
            lambda: {"ok": True, "version": "2.0.52", "reason": "ok", "error": None},
        )
        assert startup_checks.ensure_compatible(exit_on_error=False, auto_fix=False) is True

    def test_auto_fix_reexecs_after_upgrade(self, monkeypatch):
        monkeypatch.setattr(
            startup_checks,
            "diagnose_sqlalchemy",
            lambda: {"ok": False, "version": "1.4.46", "reason": "too_old", "error": None},
        )
        monkeypatch.setattr(startup_checks, "upgrade_sqlalchemy", lambda: True)
        called = {}

        def fake_reexec(extra_env=None):
            called["env"] = extra_env
            raise SystemExit(0)

        monkeypatch.setattr(startup_checks, "reexec_current_process", fake_reexec)
        with pytest.raises(SystemExit):
            startup_checks.ensure_compatible(exit_on_error=True, auto_fix=True)
        assert called.get("env", {}).get(startup_checks.REEXEC_GUARD_ENV) == "1"

    def test_already_new_version_does_not_reexec(self, monkeypatch):
        """اگر نسخه از قبل کافی باشد، pip+reexec حلقه بی‌نهایت می‌سازد."""
        monkeypatch.setattr(
            startup_checks,
            "diagnose_sqlalchemy",
            lambda: {
                "ok": False,
                "version": "2.0.52",
                "reason": "typingonly",
                "error": AssertionError("TypingOnly"),
            },
        )
        monkeypatch.setattr(
            startup_checks,
            "upgrade_sqlalchemy",
            lambda: (_ for _ in ()).throw(AssertionError("must not upgrade")),
        )
        monkeypatch.setattr(
            startup_checks,
            "reexec_current_process",
            lambda extra_env=None: (_ for _ in ()).throw(AssertionError("must not reexec")),
        )
        assert startup_checks.ensure_compatible(exit_on_error=False, auto_fix=True) is False

    def test_pytest_disables_auto_fix(self):
        assert startup_checks.should_auto_fix() is False

    def test_passenger_host_disables_auto_fix(self, monkeypatch):
        monkeypatch.setattr(startup_checks, "_in_tests", lambda: False)
        monkeypatch.setattr(startup_checks, "_is_interactive", lambda: True)
        monkeypatch.setenv("PASSENGER_APP_ENV", "production")
        assert startup_checks.running_on_host() is True
        assert startup_checks.should_auto_fix() is False

    def test_wsgi_module_counts_as_host(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "passenger_wsgi", types.ModuleType("passenger_wsgi"))
        assert startup_checks.running_on_host() is True


class TestTryImport:
    def test_assertion_error_is_returned_not_raised(self, monkeypatch):
        fake_sa = types.ModuleType("sqlalchemy")

        def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "sqlalchemy" or (name.startswith("sqlalchemy")):
                raise AssertionError(
                    "Class SQLCoreOperations directly inherits TypingOnly "
                    "but has additional attributes {'__firstlineno__'}."
                )
            return orig(name, globals, locals, fromlist, level)

        orig = __import__
        monkeypatch.setattr("builtins.__import__", fake_import)
        # اگر ماژول از قبل در sys.modules باشد import دیگر اجرا نمی‌شود
        monkeypatch.delitem(sys.modules, "sqlalchemy", raising=False)
        version, err = startup_checks.try_import_sqlalchemy()
        assert version is None
        assert isinstance(err, AssertionError)
        assert "TypingOnly" in str(err)
        # اطمینان از این‌که ماژول جعلی نشت نکرده
        assert fake_sa is not None
