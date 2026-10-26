"""Pattern checks (D35) and the link between shield_core/languages/*.yaml and the code they name."""

import pytest

from shield_core.fix.templates import TEMPLATES, get_template
from shield_core.languages import registry
from shield_core.paths import FIXTURES_DIR
from shield_core.verify.evidence import Rating
from shield_core.verify.pattern_checks import (
    PATTERN_CHECKS,
    argv_list_no_shell,
    execute_literal_sql,
    get_pattern_check,
    resolve_confine_before_open,
)

FIXTURES = FIXTURES_DIR / "taint" / "python"


def fixture(name: str) -> str:
    path = FIXTURES / name
    if not path.exists():
        pytest.skip(f"{path} not found")
    return path.read_text(encoding="utf-8")


# --- registry <-> code -------------------------------------------------------------------------


def test_every_template_and_check_name_in_every_yaml_resolves():
    for spec in registry.all_languages():
        for entry in spec.fix_templates:
            assert entry.template in TEMPLATES, f"{spec.name}: {entry.template}"
            assert entry.pattern_check in PATTERN_CHECKS, f"{spec.name}: {entry.pattern_check}"
            assert get_template(entry.template) is TEMPLATES[entry.template]
            assert get_pattern_check(entry.pattern_check) is PATTERN_CHECKS[entry.pattern_check]


def test_every_rating_in_the_yaml_converts_to_the_evidence_enum():
    for spec in registry.all_languages():
        for entry in spec.fix_templates:
            assert Rating(entry.rating)


def test_ratings_follow_d35():
    python = registry.get("python")
    assert Rating(python.fix_template("CWE-89").rating) is Rating.STRONG
    assert Rating(python.fix_template("CWE-78").rating) is Rating.NONE
    assert Rating(python.fix_template("CWE-22").rating) is Rating.NONE


def test_unknown_names_raise_a_clear_error():
    with pytest.raises(KeyError, match="unknown fix template"):
        get_template("nope")
    with pytest.raises(KeyError, match="unknown pattern check"):
        get_pattern_check("nope")


@pytest.mark.parametrize("name", sorted(TEMPLATES))
def test_every_template_refuses_garbage_without_raising(name):
    for garbage in ("", "def f(:", "\x00", "x = (", "    \n"):
        assert get_template(name)(garbage).applied is False


@pytest.mark.parametrize("check", sorted(PATTERN_CHECKS.values(), key=lambda f: f.__name__))
def test_every_check_is_false_on_garbage(check):
    assert all(check(g) is False for g in ("", "def f(:", "\x00", "x = ("))


# --- execute_literal_sql -----------------------------------------------------------------------


def test_sql_check_on_the_py13_fixture():
    assert execute_literal_sql(fixture("py13_parameterized.py")) is True


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ('c.execute("SELECT 1 WHERE x = ?", (a,))', True),
        ('c.execute("SELECT 1")', True),
        ('c.execute("SELECT 1 WHERE x = " + a)', False),
        ('c.execute(f"SELECT {a}")', False),
        ("c.execute(q, (a,))", False),
        ('c.execute("A" + "B")', False),
        ('c.execute("SELECT 1")\nc.execute("SELECT " + a)', False),
        ("x = 1", False),
    ],
)
def test_sql_check_cases(code, expected):
    assert execute_literal_sql(code) is expected


# --- argv_list_no_shell ------------------------------------------------------------------------


def test_command_check_on_the_py19_fixture():
    assert argv_list_no_shell(fixture("py19_list_argv.py")) is True


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ('subprocess.run(["ping", host])', True),
        ('subprocess.run(["ping", host], check=True, shell=False)', True),
        ('subprocess.run("ping " + host, shell=True)', False),
        ('subprocess.run(["ping", host], shell=True)', False),
        ('subprocess.run("ping")', False),
        ('subprocess.run(("ping", host))', False),
        ('subprocess.run(["a"])\nsubprocess.run("b " + h, shell=True)', False),
        ('subprocess.run(["ping", host])\nos.system("x")', False),
        ('subprocess.run(["ping", host])\nsubprocess.Popen("x", shell=True)', False),
        ('subprocess.run(["ping", host], shell=flag)', False),
        ('os.system("ping " + host)', False),
        ("x = 1", False),
    ],
)
def test_command_check_cases(code, expected):
    assert argv_list_no_shell(code) is expected


# --- resolve_confine_before_open ---------------------------------------------------------------


def test_path_check_on_the_py20_fixture():
    assert resolve_confine_before_open(fixture("py20_resolve_guard.py")) is True


GUARD = (
    "base = Path(B).resolve()\n"
    "t = (base / n).resolve()\n"
    "if not t.is_relative_to(base):\n"
    "    raise ValueError('x')\n"
)


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        (GUARD + "open(t)", True),
        (GUARD.replace("raise ValueError('x')", "return None") + "open(t)", True),
        (GUARD + "with open(t) as f:\n    pass", True),
        ("open(os.path.join(B, n))", False),
        (GUARD.replace("t.is_relative_to(base)", "True") + "open(t)", False),  # no is_relative_to
        (
            GUARD.replace("    raise ValueError('x')\n", "    pass\n") + "open(t)",
            False,
        ),  # no rejection
        ("t = Path(n).resolve()\nopen(t)", False),  # resolve only, no guard
        ("open(t)\n" + GUARD, False),  # guard after the open
        (GUARD, False),  # no open at all
        (
            "if t.is_relative_to(b):\n    open(t)\nelse:\n    raise ValueError()\n",
            False,
        ),  # no resolve
    ],
)
def test_path_check_cases(code, expected):
    assert resolve_confine_before_open(code) is expected
