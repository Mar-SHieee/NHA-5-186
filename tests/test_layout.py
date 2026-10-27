"""Guards the folder layout: imports resolve, packages are complete, README paths are real.

Runs without torch, so it also covers modules whose own tests need a GPU stack.
"""

import ast
import re
import shutil
import subprocess

import pytest

from shield_core import paths

CODE_ROOTS = ("shield_core", "scripts", "tests")
TRACKED_TOP = (
    "shield_core/",
    "scripts/",
    "docs/",
    "tests/",
    "docker/",
    "requirements/",
    ".github/",
)


def py_files():
    for top in CODE_ROOTS:
        for p in (paths.REPO_ROOT / top).rglob("*.py"):
            rel = p.relative_to(paths.REPO_ROOT).as_posix()
            if not rel.startswith("tests/fixtures/"):
                yield p


def module_exists(dotted: str) -> bool:
    base = paths.REPO_ROOT.joinpath(*dotted.split("."))
    return base.with_suffix(".py").is_file() or (base / "__init__.py").is_file()


def test_every_first_party_import_resolves():
    bad = []
    for p in py_files():
        rel = p.relative_to(paths.REPO_ROOT)
        for node in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module]
            elif isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            else:
                continue
            for name in names:
                if name.split(".")[0] in ("shield_core", "scripts") and not module_exists(name):
                    bad.append(f"{rel}: {name}")
    assert not bad, "unresolved imports:\n" + "\n".join(bad)


def test_imported_submodules_exist():
    """`from shield_core.datasets import splits` must find splits.py (or an attribute)."""
    bad = []
    for p in py_files():
        for node in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
            if not (isinstance(node, ast.ImportFrom) and node.level == 0 and node.module):
                continue
            if node.module.split(".")[0] not in ("shield_core", "scripts"):
                continue
            pkg_dir = paths.REPO_ROOT.joinpath(*node.module.split("."))
            if not pkg_dir.is_dir():
                continue  # a module file: names are attributes
            init = (pkg_dir / "__init__.py").read_text(encoding="utf-8")
            for alias in node.names:
                is_module = module_exists(f"{node.module}.{alias.name}")
                if not is_module and alias.name not in init:
                    bad.append(f"{p.relative_to(paths.REPO_ROOT)}: {node.module}.{alias.name}")
    assert not bad, "names that are neither submodules nor defined in __init__:\n" + "\n".join(bad)


def test_every_code_folder_is_a_package():
    missing = []
    for top in ("shield_core", "scripts"):
        for d in (paths.REPO_ROOT / top).rglob("*"):
            if d.is_dir() and d.name != "__pycache__" and any(d.glob("*.py")):
                if not (d / "__init__.py").exists():
                    missing.append(d.relative_to(paths.REPO_ROOT).as_posix())
    assert not missing, f"folders with .py files but no __init__.py: {missing}"


def test_tracked_path_constants_exist():
    tracked = [
        paths.DOCS_API_DIR,
        paths.DOCS_AUDITS_DIR,
        paths.DOCS_EXPLORATION_DIR,
        paths.DOCS_LEAKAGE_DIR,
        paths.DOCS_PROJECT_NAMES_DIR,
        paths.DOCS_GRAPHS_DIR,
        paths.DOCS_TAINT_DIR,
        paths.DOCS_FIXES_DIR,
        paths.DOCS_MODELING_DIR,
        paths.FIXTURES_DIR,
    ]
    assert [p for p in tracked if not p.is_dir()] == []


def test_every_code_folder_has_a_readme():
    missing = []
    for top in ("shield_core", "scripts"):
        for d in (paths.REPO_ROOT / top).rglob("*"):
            if d.is_dir() and d.name != "__pycache__" and any(d.glob("*.py")):
                if not (d / "README.md").exists():
                    missing.append(d.relative_to(paths.REPO_ROOT).as_posix())
    assert not missing, f"folders without a README.md: {missing}"


def readme_path_tokens():
    text = (paths.REPO_ROOT / "README.md").read_text(encoding="utf-8")
    for tok in re.findall(r"`([^`\s]+)`", text):
        tok = tok.rstrip("/.,:;")
        if tok.startswith(TRACKED_TOP) and not re.search(r"[*<>{}…]|\.\.\.", tok):
            yield tok.split("::")[0]


@pytest.mark.parametrize("token", sorted(set(readme_path_tokens())))
def test_readme_paths_exist(token):
    assert (paths.REPO_ROOT / token).exists(), (
        f"README mentions a path that does not exist: {token}"
    )


@pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
def test_no_source_file_is_silently_git_ignored():
    """A source/doc file matched by .gitignore is never committed, so CI would not see it."""
    r = subprocess.run(
        ["git", "ls-files", "--others", "--ignored", "--exclude-standard"],
        cwd=paths.REPO_ROOT,
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        pytest.skip("not a git checkout")
    suffixes = (".py", ".md", ".yaml", ".yml", ".toml", ".sh", ".c", ".cpp", ".txt")
    hidden = [
        f
        for f in r.stdout.splitlines()
        if f.endswith(suffixes)
        and f.split("/")[0] in ("shield_core", "scripts", "tests", "docs", "docker")
        and "__pycache__" not in f
        and not f.startswith(("tests/fixtures/", "scripts/data/"))
    ]
    assert not hidden, f"ignored by .gitignore, so never committed: {hidden}"
