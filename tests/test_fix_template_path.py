"""CWE-22 template (W2-P4-03, Step 28): open(os.path.join(base, name)) confined to its base."""

import os
import textwrap
from pathlib import Path

import pytest

from shield_core.models.fixgen.path import path_confine
from shield_core.verify.evidence import Checks, Rating, make_report
from shield_core.verify.pattern_checks import resolve_confine_before_open
from shield_core.verify.pysource import SourceText

FIXTURES = Path(__file__).parent / "fixtures" / "taint" / "python"

INLINE = (
    "import os\n"
    "def read(name):\n"
    "    with open(os.path.join(UPLOAD_DIR, name)) as f:\n"
    "        return f.read()\n"
)


def applied(code: str, context: str = ""):
    result = path_confine(code, context)
    assert result.applied, result.reason
    assert result.fixed_code is not None
    return result


def refused(code: str, context: str = "") -> str:
    result = path_confine(code, context)
    assert not result.applied and result.fixed_code is None
    return result.reason


# --- the shapes it handles ---------------------------------------------------------------------


def test_inline_form_inserts_the_guard_and_opens_the_resolved_path():
    result = applied(INLINE)
    assert result.fixed_code == (
        "import os\n"
        "def read(name):\n"
        "    base = Path(UPLOAD_DIR).resolve()\n"
        "    target = (base / name).resolve()\n"
        "    if not target.is_relative_to(base):\n"
        '        raise ValueError("path escapes base directory")\n'
        "    with open(target) as f:\n"
        "        return f.read()\n"
    )
    assert result.required_imports == ("from pathlib import Path",)


def test_the_survey_example():
    code = textwrap.dedent(
        """\
        import os
        def f(request):
            name = request.args["file"]
            with open(os.path.join(UPLOAD_DIR, name)) as f:
                data = f.read()
        """
    )
    assert "    target = (base / name).resolve()\n" in applied(code).fixed_code


def test_variable_form_replaces_the_assignment_and_keeps_later_uses():
    code = (
        "import os\n"
        "def read(name):\n"
        "    p = os.path.join(BASE, name)\n"
        "    log(p)\n"
        '    return open(p, "rb").read()\n'
    )
    assert applied(code).fixed_code == (
        "import os\n"
        "def read(name):\n"
        "    base = Path(BASE).resolve()\n"
        "    p = (base / name).resolve()\n"
        "    if not p.is_relative_to(base):\n"
        '        raise ValueError("path escapes base directory")\n'
        "    log(p)\n"
        '    return open(p, "rb").read()\n'
    )


def test_open_with_a_chained_call_is_handled():
    code = "import os\ndef read(n):\n    return open(os.path.join(BASE, n)).read()\n"
    fixed = applied(code).fixed_code
    assert "    return open(target).read()\n" in fixed


def test_the_name_may_be_an_expression_evaluated_once():
    code = (
        "import os\n"
        "def read(request):\n"
        '    return open(os.path.join(BASE, request.args["f"])).read()\n'
    )
    fixed = applied(code).fixed_code
    assert fixed.count('request.args["f"]') == 1
    assert '    target = (base / request.args["f"]).resolve()\n' in fixed


def test_other_open_arguments_are_kept():
    code = (
        "import os\n"
        "def w(n):\n"
        '    with open(os.path.join(BASE, n), "w", encoding="utf-8") as f:\n'
        '        f.write("x")\n'
    )
    assert '    with open(target, "w", encoding="utf-8") as f:\n' in applied(code).fixed_code


def test_names_that_already_occur_are_replaced_by_unused_ones():
    code = (
        "import os\n"
        "def read(name):\n"
        "    base = 1\n"
        "    target = 2\n"
        "    return open(os.path.join(BASE, name)).read()\n"
    )
    fixed = applied(code).fixed_code
    assert "    base_1 = Path(BASE).resolve()\n" in fixed
    assert "    target_1 = (base_1 / name).resolve()\n" in fixed
    assert "open(target_1)" in fixed and "    base = 1\n    target = 2\n" in fixed


def test_import_is_not_required_when_path_is_already_imported():
    assert applied(INLINE, context="from pathlib import Path\n").required_imports == ()
    assert applied("from pathlib import Path\n" + INLINE).required_imports == ()
    assert applied(INLINE, context="from pathlib import (\n    Path,\n)\n").required_imports == ()
    wrong = applied(INLINE, context="import pathlib\n")  # `Path` is not bound by that
    assert wrong.required_imports == ("from pathlib import Path",)


def test_for_loop_iterable_and_return_are_allowed_places():
    code = (
        "import os\n"
        "def lines(n):\n"
        "    for line in open(os.path.join(BASE, n)):\n"
        "        yield line\n"
    )
    assert "    for line in open(target):\n" in applied(code).fixed_code


def test_everything_outside_the_sink_is_byte_identical():
    code = (
        "import os\n"
        "# keep\n"
        "def read(name):  # keep too\n"
        "    x = 1   # odd   spacing\n"
        "    with open(os.path.join(BASE, name)) as f:\n"
        "        return f.read()   # tail\n"
    )
    fixed = applied(code).fixed_code
    for index in (0, 1, 2, 3, 5):
        assert code.splitlines()[index] in fixed.splitlines()


def test_unicode_and_crlf_are_handled():
    code = INLINE.replace("def read(name):\n", 'def read(name):\n    note = "é"\n').replace(
        "\n", "\r\n"
    )
    fixed = applied(code).fixed_code
    assert "\n" not in fixed.replace("\r\n", "")
    assert "    target = (base / name).resolve()\r\n" in fixed


def test_an_indented_method_is_handled():
    code = (
        "    def read(self, name):\n"
        "        with open(os.path.join(self.root, name)) as f:\n"
        "            return f.read()\n"
    )
    result = applied(code)
    assert "        base = Path(self.root).resolve()\n" in result.fixed_code
    assert SourceText.parse(result.fixed_code) is not None


def test_output_parses_and_the_pattern_check_flips():
    fixed = applied(INLINE).fixed_code
    assert SourceText.parse(fixed) is not None
    assert resolve_confine_before_open(INLINE) is False
    assert resolve_confine_before_open(fixed) is True


# --- refusals (survey 4.3 and the plan) --------------------------------------------------------

REFUSALS = [
    ("no base: plain parameter", "return open(name).read()", "no base directory"),
    ("no base: concatenation", 'return open(BASE + "/" + name).read()', "no base"),
    ("no base: one-argument join", "return open(os.path.join(name)).read()", "no base"),
    ("several directories", "return open(os.path.join(A, B, name)).read()", "no base"),
    ("keyword in join", "return open(os.path.join(BASE, name, sep='/')).read()", "no base"),
    ("starred join", "return open(os.path.join(*parts)).read()", "no base"),
    ("path built elsewhere", "return open(make_path(name)).read()", "no base"),
    ("conditional open", "return name and open(os.path.join(BASE, name)).read()", "conditionally"),
    ("open in a lambda", "return (lambda: open(os.path.join(BASE, name)))()", "conditionally"),
    ("open in a while test", "while open(os.path.join(BASE, name)):\n        pass", "While"),
    ("same line", "x = 1; y = open(os.path.join(BASE, name))", "shares its line"),
]


@pytest.mark.parametrize(("label", "statement", "expected"), REFUSALS, ids=[r[0] for r in REFUSALS])
def test_refuses(label, statement, expected):
    code = f"import os\ndef read(name, parts):\n    {statement}\n"
    assert expected in refused(code)


def test_refuses_a_variable_that_is_not_a_join():
    code = "import os\ndef read(n):\n    p = BASE + n\n    return open(p).read()\n"
    assert "not built with a two-argument os.path.join" in refused(code)


def test_refuses_a_variable_assigned_twice():
    code = (
        "import os\ndef read(n, admin):\n"
        "    p = os.path.join(BASE, n)\n"
        "    if admin:\n"
        "        p = os.path.join(ADMIN, n)\n"
        "    return open(p).read()\n"
    )
    assert "more than once" in refused(code)


def test_refuses_an_assignment_in_another_block():
    code = (
        "import os\ndef read(n, flag):\n"
        "    if flag:\n"
        "        p = os.path.join(BASE, n)\n"
        "    return open(p).read()\n"
    )
    assert "same block" in refused(code)


def test_refuses_two_candidate_opens():
    code = (
        "import os\ndef read(a, b):\n"
        "    x = open(os.path.join(BASE, a)).read()\n"
        "    y = open(os.path.join(BASE, b)).read()\n"
        "    return x + y\n"
    )
    assert "more than one" in refused(code)


def test_a_constant_open_is_not_a_candidate():
    code = (
        "import os\ndef read(n):\n"
        '    cfg = open("config.json").read()\n'
        "    return open(os.path.join(BASE, n)).read()\n"
    )
    assert 'open("config.json")' in applied(code).fixed_code


def test_refuses_when_there_is_no_open():
    assert "no open()" in refused("import os\ndef read(n):\n    return n\n")
    assert "no open()" in refused('def read():\n    return open("a.txt").read()\n')


def test_refuses_code_that_does_not_parse():
    assert refused("def read(:\n") == "the code does not parse"


def test_refuses_when_the_function_shadows_path():
    code = "import os\ndef read(name, Path):\n    return open(os.path.join(BASE, name)).read()\n"
    assert "shadowing" in refused(code)


# --- behaviour: ../../etc/passwd, an absolute path, a symlink, a normal name -------------------


def _reader(code: str, base: Path):
    namespace = {"UPLOAD_DIR": str(base), "os": os, "Path": Path}
    exec(compile(code, "<snippet>", "exec"), namespace)  # noqa: S102 - test snippet
    return namespace["read"]


@pytest.fixture
def uploads(tmp_path):
    base = tmp_path / "uploads"
    base.mkdir()
    (base / "ok.txt").write_text("fine", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("secret", encoding="utf-8")
    return base


def test_behaviour_a_normal_name_reads_the_file(uploads):
    read = _reader(applied(INLINE).fixed_code, uploads)
    assert read("ok.txt") == "fine"
    assert _reader(INLINE, uploads)("ok.txt") == "fine"  # same as before the fix


def test_behaviour_dot_dot_traversal_is_rejected(uploads):
    assert _reader(INLINE, uploads)("../secret.txt") == "secret"  # the bug
    with pytest.raises(ValueError, match="path escapes base directory"):
        _reader(applied(INLINE).fixed_code, uploads)("../secret.txt")


def test_behaviour_an_absolute_path_is_rejected(uploads, tmp_path):
    absolute = str(tmp_path / "secret.txt")
    assert _reader(INLINE, uploads)(absolute) == "secret"  # join drops the base: the bug
    with pytest.raises(ValueError, match="path escapes base directory"):
        _reader(applied(INLINE).fixed_code, uploads)(absolute)


def test_behaviour_a_symlink_that_points_outside_is_rejected(uploads, tmp_path):
    link = uploads / "link.txt"
    try:
        link.symlink_to(tmp_path / "secret.txt")
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are not available here (Windows without privileges)")
    assert _reader(INLINE, uploads)("link.txt") == "secret"  # the bug
    with pytest.raises(ValueError, match="path escapes base directory"):
        _reader(applied(INLINE).fixed_code, uploads)("link.txt")


def test_behaviour_a_sibling_directory_with_the_same_prefix_is_rejected(uploads, tmp_path):
    (tmp_path / "uploads2").mkdir()
    (tmp_path / "uploads2" / "x.txt").write_text("x", encoding="utf-8")
    with pytest.raises(ValueError, match="path escapes base directory"):
        _reader(applied(INLINE).fixed_code, uploads)("../uploads2/x.txt")


def test_behaviour_variable_form_rejects_traversal_too(uploads):
    code = (
        "import os\n"
        "def read(name):\n"
        "    p = os.path.join(UPLOAD_DIR, name)\n"
        "    with open(p) as f:\n"
        "        return f.read()\n"
    )
    read = _reader(applied(code).fixed_code, uploads)
    assert read("ok.txt") == "fine"
    with pytest.raises(ValueError, match="path escapes base directory"):
        read("../secret.txt")


# --- verdict (D35): CWE-22 is weak/none, the pattern check decides -----------------------------


def test_verdict_passes_on_the_pattern_check_although_redetection_still_flows():
    fixed = applied(INLINE).fixed_code
    checks = Checks(
        syntax_ok=SourceText.parse(fixed) is not None,
        redetect_ok=False,  # py20: a correct fix still flows; passed by hand in W2
        tests_ok=None,
        pattern_ok=resolve_confine_before_open(fixed),
    )
    report = make_report(Rating.NONE, checks)
    assert report.verdict == "PASS" and report.redetect_ok is False
    assert "pattern_check=ok" in report.notes and "redetect=false(not decisive)" in report.notes


def test_verdict_fails_for_the_unfixed_code_even_when_the_detector_is_quiet():
    checks = Checks(True, True, None, pattern_ok=resolve_confine_before_open(INLINE))
    assert make_report(Rating.NONE, checks).verdict == "FAIL"


def test_the_hand_written_py20_fixture_is_a_positive_case():
    code = (FIXTURES / "py20_resolve_guard.py").read_text(encoding="utf-8")
    assert resolve_confine_before_open(code) is True
