#!/usr/bin/env python3
"""بررسی استاتیک ارجاع‌های Qt در app_desktop.py بر اساس stubهای رسمی PyQt6.

چرا؟ PyInstaller/pip هیچ خطای import-time برای enumها و متدهای غلط نمی‌دهند؛
این خطاها فقط وقتی کاربر دکمه را می‌زند بیرون می‌زنند (مثل
`Qt.ShortcutContext.WindowWithChildrenContext` که اصلاً وجود ندارد).

این اسکریپت نام کلاس‌های Qt را از فایل‌های `.pyi` نصب‌شده (یا یک پوشه stub مثل
`--stubs /tmp/pyi`) می‌خواند و هر ارجاع `ClassName.member` / `ClassName.Enum.Member`
را در فایل‌های هدف چک می‌کند.

اجرا:
    python tools/check_qt_api.py app_desktop.py
    python tools/check_qt_api.py --stubs /tmp/pyi app_desktop.py
"""
from __future__ import annotations

import argparse
import ast
import os
import sys
from pathlib import Path

# کلاس‌هایی که از QtWebEngine می‌آیند و ممکن است نصب نباشند
SIP_STUB_GLOB = "*.pyi"


def collect_stub_dirs(extra: list[str] | None) -> list[Path]:
    dirs: list[Path] = []
    try:                                    # پوشه stub داخل بسته نصب‌شده
        import PyQt6  # noqa: F401
        dirs.append(Path(PyQt6.__file__).parent)
    except Exception:
        pass
    for item in extra or []:
        p = Path(item)
        if p.is_dir():
            # هم خود پوشه و هم حالت استخراج‌شدهٔ wheel ( .../PyQt6/*.pyi )
            dirs.append(p)
            nested = p / "PyQt6"
            if nested.is_dir():
                dirs.append(nested)
    return dirs


def build_index(dirs: list[Path]) -> tuple[dict[str, set[str]], dict[str, list[str]]]:
    """نگاشت نام کلاس/ماژول -> مجموعه اعضا (متدها، enumها، سیگنال‌ها) + والدها."""
    index: dict[str, set[str]] = {}
    bases: dict[str, list[str]] = {}
    for directory in dirs:
        for stub in sorted(directory.glob(SIP_STUB_GLOB)):
            module = stub.stem
            try:
                tree = ast.parse(stub.read_text(encoding="utf-8"))
            except Exception:
                continue
            index.setdefault(module, set())

            def walk(node, prefix=""):
                """کلاس‌های تو در تو را با نام نقطه‌دار ثبت کن (Qt.ShortcutContext)."""
                for child in ast.iter_child_nodes(node):
                    if isinstance(child, ast.ClassDef):
                        name = prefix + child.name
                        members = index.setdefault(name, set())
                        bases[name] = [ast.unparse(b) for b in child.bases]
                        for body in child.body:
                            if isinstance(body, (ast.FunctionDef, ast.AsyncFunctionDef)):
                                members.add(body.name)
                            elif isinstance(body, ast.AnnAssign) and isinstance(body.target, ast.Name):
                                members.add(body.target.id)
                            elif isinstance(body, ast.Assign) and len(body.targets) == 1 \
                                    and isinstance(body.targets[0], ast.Name):
                                # اعضای enum: `WidgetShortcut = ... # type: Qt.ShortcutContext`
                                members.add(body.targets[0].id)
                            elif isinstance(body, ast.ClassDef):
                                # enum تو در تو: QMessageBox.Icon / Qt.ShortcutContext
                                members.add(body.name)
                        walk(child, prefix=name + ".")
                    elif isinstance(child, (ast.If, ast.Try)):
                        walk(child, prefix)

            walk(tree)
    return index, bases


def dotted_name(node) -> str | None:
    """`Qt.ShortcutContext.WindowWithChildrenContext` -> رشته نقطه‌دار."""
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return None


def members_of(owner: str, index: dict[str, set[str]], bases: dict[str, list[str]], depth: int = 0) -> set[str]:
    """اعضای یک کلاس با احتساب ارث‌بری (مثل QApplication -> QGuiApplication)."""
    found = set(index.get(owner, ()))
    if depth > 6:
        return found
    for base in bases.get(owner, ()):
        found |= members_of(_resolve(base, index), index, bases, depth + 1)
    return found


def _resolve(name: str, index: dict[str, set[str]]) -> str:
    for candidate in (name, name.split(".")[-1]):
        if candidate in index:
            return candidate
    return name


def check_file(path: Path, index: dict[str, set[str]], bases: dict[str, list[str]]) -> list[tuple[int, str, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    problems: list[tuple[int, str, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Attribute):
            continue
        dotted = dotted_name(node)
        if not dotted or dotted.count(".") < 1:
            continue
        head, _, _rest = dotted.partition(".")
        if head not in index:          # فقط نام‌های شناخته‌شده Qt را چک کن
            continue
        # طولانی‌ترین پیشوند موجود را پیدا کن
        parts = dotted.split(".")
        for cut in range(len(parts) - 1, 0, -1):
            owner = ".".join(parts[:cut])
            member = parts[cut]
            if owner in index:
                known = members_of(owner, index, bases)
                if member not in known:
                    problems.append((node.lineno, f"{owner}.{member}",
                                     f"عضو «{member}» در {owner} نیست" + hint(owner, member, index, bases)))
                break
    return problems


def hint(owner: str, member: str, index: dict[str, set[str]], bases: dict[str, list[str]]) -> str:
    import difflib
    close = difflib.get_close_matches(member, sorted(members_of(owner, index, bases)), n=3, cutoff=0.5)
    return f"  (نزدیک: {', '.join(close)})" if close else ""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("files", nargs="+")
    parser.add_argument("--stubs", action="append", default=[])
    args = parser.parse_args()

    dirs = collect_stub_dirs(args.stubs)
    if not dirs:
        print("PyQt6 نصب نیست و پوشه‌ای هم داده نشد؛ --stubs بدهید.", file=sys.stderr)
        return 2
    index, bases = build_index(dirs)
    print(f"stubها: {', '.join(str(d) for d in dirs)}")
    print(f"{len(index)} کلاس/ماژول ایندکس شد\n")

    total = 0
    for file in args.files:
        problems = check_file(Path(file), index, bases)
        for lineno, dotted, message in problems:
            print(f"✗ {file}:{lineno}  {dotted}  ← {message}")
        if problems:
            total += len(problems)
        else:
            print(f"✓ {file}: ارجاع Qt سالم است")
    return 1 if total else 0


if __name__ == "__main__":
    raise SystemExit(main())
