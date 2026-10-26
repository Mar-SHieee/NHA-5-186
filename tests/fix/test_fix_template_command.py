"""CWE-78 template (W2-P4-03, Step 28): shell string in, argument list out."""

import re
import textwrap

import pytest

from shield_core.fix.templates.command import ARG_PATTERN, command_argv
from shield_core.verify.evidence import Checks, Rating, make_report
from shield_core.verify.pattern_checks import argv_list_no_shell
from shield_core.verify.pysource import SourceText

GUARD = (
    'if not re.fullmatch(r"[A-Za-z0-9_.][A-Za-z0-9_.-]*", {name}):\n'
    '    raise ValueError("unsafe command argument")\n'
)


def guard(name: str, indent: str = "    ") -> str:
    return textwrap.indent(GUARD.format(name=name), indent)


def applied(code: str, context: str = "", **kwargs):
    result = command_argv(code, context, **kwargs)
    assert result.applied, result.reason
    assert result.fixed_code is not None
    return result


def refused(code: str, context: str = "", **kwargs) -> str:
    result = command_argv(code, context, **kwargs)
    assert not result.applied and result.fixed_code is None
    return result.reason


# --- the shapes it handles ---------------------------------------------------------------------


def test_os_system_becomes_subprocess_run_with_a_guard():
    code = 'import os\ndef h(host):\n    os.system("ping -c 1 " + host)\n'
    result = applied(code)
    assert result.fixed_code == (
        "import os\ndef h(host):\n"
        + guard("host")
        + '    subprocess.run(["ping", "-c", "1", host], check=True)\n'
    )
    assert result.required_imports == ("import subprocess", "import re")


def test_subprocess_run_with_shell_true_keeps_its_other_keywords():
    code = (
        "import subprocess\n"
        "def h(host):\n"
        '    subprocess.run("ping -c 1 " + host, shell=True, capture_output=True, text=True)\n'
    )
    result = applied(code)
    assert result.fixed_code == (
        "import subprocess\ndef h(host):\n"
        + guard("host")
        + '    subprocess.run(["ping", "-c", "1", host], capture_output=True, text=True)\n'
    )
    assert result.required_imports == ("import re",)  # subprocess is already imported


@pytest.mark.parametrize(
    "expression",
    [
        '"ping -c 1 " + host',
        'f"ping -c 1 {host}"',
        '"ping -c 1 %s" % host',
        '"ping -c 1 {}".format(host)',
    ],
)
def test_all_four_string_forms(expression):
    code = f"import os\ndef h(host):\n    os.system({expression})\n"
    assert '    subprocess.run(["ping", "-c", "1", host], check=True)\n' in applied(code).fixed_code


def test_several_values_and_trailing_literal_words():
    code = 'import os\ndef h(a, b):\n    os.system("cp " + a + " " + b + " -v")\n'
    fixed = applied(code).fixed_code
    assert '    subprocess.run(["cp", a, b, "-v"], check=True)\n' in fixed
    assert guard("a") in fixed and guard("b") in fixed


def test_a_value_that_is_an_expression_is_evaluated_once_into_a_temporary():
    code = 'import os\ndef h(request):\n    os.system("ping " + request.form["host"])\n'
    fixed = applied(code).fixed_code
    assert '    cmd_arg = request.form["host"]\n' in fixed
    assert fixed.count('request.form["host"]') == 1
    assert 'subprocess.run(["ping", cmd_arg], check=True)' in fixed
    assert guard("cmd_arg") in fixed


def test_temporary_name_avoids_collisions():
    code = 'import os\ndef h(request, cmd_arg):\n    os.system("ping " + request.form["h"])\n'
    assert "    cmd_arg_1 = request.form" in applied(code).fixed_code


def test_literal_words_with_quotes_are_split_like_the_shell_would():
    code = "import os\ndef h(h):\n    os.system(\"echo 'two words' \" + h)\n"
    assert '["echo", "two words", h]' in applied(code).fixed_code


def test_no_guard_option_gives_the_list_form_only():
    code = 'import os\ndef h(host):\n    os.system("ping -c 1 " + host)\n'
    result = applied(code, guard=False)
    assert result.fixed_code == (
        'import os\ndef h(host):\n    subprocess.run(["ping", "-c", "1", host], check=True)\n'
    )
    assert result.required_imports == ("import subprocess",)


def test_the_call_may_be_assigned_or_returned():
    code = 'import subprocess\ndef h(h):\n    out = subprocess.run("ls " + h, shell=True).stdout\n'
    fixed = applied(code).fixed_code
    assert '    out = subprocess.run(["ls", h]).stdout\n' in fixed


def test_guard_goes_before_the_with_statement_not_inside_it():
    code = (
        "import subprocess\n"
        "def h(h):\n"
        "    with lock:\n"
        '        subprocess.run("ls " + h, shell=True)\n'
    )
    assert "        if not re.fullmatch" in applied(code).fixed_code


def test_indentation_style_and_line_endings_are_kept():
    code = 'import os\ndef h(host):\n\tos.system("ping " + host)\n'.replace("\n", "\r\n")
    fixed = applied(code).fixed_code
    assert "\n" not in fixed.replace("\r\n", "")
    assert '\tif not re.fullmatch(r"' in fixed and "\t\traise ValueError(" in fixed


def test_everything_outside_the_call_is_byte_identical():
    code = (
        "import os\n"
        "# keep\n"
        "def h(request):  # keep too\n"
        '    host = request.form["host"]   # odd   spacing\n'
        '    os.system("ping -c 1 " + host)\n'
        "    return 1   # tail\n"
    )
    fixed = applied(code).fixed_code
    for line in (code.splitlines()[i] for i in (0, 1, 2, 3, 5)):
        assert line in fixed.splitlines()


def test_unicode_before_the_call_does_not_shift_the_edit():
    code = 'import os\ndef h(h):\n    x = "é"; os.system("ls " + h)\n'
    assert refused(code) == "the statement shares its line with other code"
    code = 'import os\ndef h(h):\n    x = "é"\n    os.system("ls " + h)\n'
    assert '    subprocess.run(["ls", h], check=True)\n' in applied(code).fixed_code


def test_an_indented_method_is_handled():
    code = '    def run(self, host):\n        os.system("ping " + host)\n'
    result = applied(code)
    assert result.fixed_code.startswith("    def run(self, host):\n        if not re.fullmatch(")
    assert SourceText.parse(result.fixed_code) is not None


def test_output_parses_and_the_pattern_check_flips():
    for expression in ('"ping -c 1 " + host', 'f"ping -c 1 {host}"'):
        code = f"import os\ndef h(host):\n    os.system({expression})\n"
        fixed = applied(code).fixed_code
        assert SourceText.parse(fixed) is not None
        assert argv_list_no_shell(code) is False
        assert argv_list_no_shell(fixed) is True


# --- refusals (survey 4.2 and the plan) --------------------------------------------------------

REFUSALS = [
    ("pipe", 'os.system("ping " + h + " | grep ms")', "shell features"),
    ("redirect", 'os.system("ping " + h + " > out.txt")', "shell features"),
    ("glob", 'os.system("ls " + h + " *.txt")', "shell features"),
    ("semicolon", 'os.system("ping " + h + "; id")', "shell features"),
    ("and", 'os.system("a && b " + h)', "shell features"),
    ("backtick", 'os.system("echo `id` " + h)', "shell features"),
    ("dollar", 'os.system("echo $HOME " + h)', "shell features"),
    ("tilde", 'os.system("ls ~/x " + h)', "shell features"),
    ("part of a word", 'os.system("ping " + h + ".com")', "larger word"),
    ("prefix of a word", 'os.system("ping -c" + h)', "larger word"),
    ("single quoted", 'os.system("ping \'" + h + "\'")', "not closed|larger word"),
    ("double quoted", "os.system('ping \"' + h + '\"')", "not closed|larger word"),
    ("quote spans the value", 'os.system("echo \'a " + h + " b\'")', "not closed"),
    ("command from input", 'os.system(h + " -v")', "command name"),
    ("command from input in fstring", 'os.system(f"{h} -v")', "command name"),
    ("blank then value", 'os.system(" " + h)', "command name"),
    ("env assignment", 'os.system("PATH=/x ls " + h)', "environment variable"),
    ("two values glued", 'os.system("ping " + h + h)', "without a space"),
    ("no variable part", 'os.system("ping " + "localhost")', "no variable part"),
    ("constant string", 'os.system("ping -c 1 localhost")', "not built inside the call"),
    ("variable command", "os.system(cmd)", "not built inside the call"),
    ("fstring conversion", 'os.system(f"ping {h!r}")', "conversion"),
    ("two arguments", "os.system(a, b)", "single plain argument"),
    ("result used", 'rc = os.system("ping " + h)', "result of os.system"),
    ("in a condition", 'ok = h and os.system("ping " + h)', "conditionally"),
    ("in a comprehension", '[os.system("ping " + x) for x in h]', "conditionally"),
    ("in a while test", 'while os.system("ping " + h):\n        pass', "WhileStatement|While"),
    ("same line", 'x = 1; os.system("ping " + h)', "shares its line"),
]


@pytest.mark.parametrize(("label", "statement", "expected"), REFUSALS, ids=[r[0] for r in REFUSALS])
def test_refuses(label, statement, expected):
    code = f"import os\nimport subprocess\ndef h(a, b, h, cmd):\n    {statement}\n"
    assert re.search(expected, refused(code)), refused(code)


RUN_REFUSALS = [
    ("shell is a variable", 'subprocess.run("ls " + h, shell=flag)', "literal True"),
    (
        "unknown keyword",
        'subprocess.run("ls " + h, shell=True, executable="/bin/zsh")',
        "executable",
    ),
    ("kwargs", 'subprocess.run("ls " + h, shell=True, **opts)', "keyword"),
    ("second positional", 'subprocess.run("ls " + h, 10, shell=True)', "exactly one positional"),
    ("already a list", 'subprocess.run(["ls", h], shell=True)', "not built inside the call"),
]


@pytest.mark.parametrize(
    ("label", "statement", "expected"), RUN_REFUSALS, ids=[r[0] for r in RUN_REFUSALS]
)
def test_refuses_subprocess_run_shapes(label, statement, expected):
    code = f"import subprocess\ndef h(h, flag, opts):\n    {statement}\n"
    assert expected in refused(code)


def test_refuses_two_shell_calls():
    code = 'import os\ndef h(a, b):\n    os.system("ls " + a)\n    os.system("ls " + b)\n'
    assert "more than one" in refused(code)


def test_refuses_when_there_is_no_shell_call():
    assert "no os.system()" in refused(
        "import subprocess\ndef h(h):\n    subprocess.run(['ls', h])\n"
    )


def test_refuses_code_that_does_not_parse():
    assert refused("def h(:\n") == "the code does not parse"


def test_refuses_when_the_function_shadows_a_new_import():
    code = 'import os\ndef h(host, re):\n    os.system("ping " + host)\n'
    assert "shadowing" in refused(code)
    assert "shadowing" in refused(
        'import os\ndef h(host):\n    subprocess = 1\n    os.system("ping " + host)\n'
    )


# --- behaviour against a stub: the three survey inputs -----------------------------------------


class _Recorder:
    def __init__(self):
        self.calls = []

    def run(self, argv, **kwargs):
        self.calls.append((argv, kwargs))


def _execute(code: str, host: str):
    recorder = _Recorder()
    namespace = {"subprocess": recorder, "re": re}
    exec(compile(code, "<snippet>", "exec"), namespace)  # noqa: S102 - test snippet
    namespace["ping"](host)
    return recorder.calls


SNIPPET = 'import os\ndef ping(host):\n    os.system("ping -c 1 " + host)\n'


def test_behaviour_a_normal_host_is_one_argument():
    assert _execute(applied(SNIPPET).fixed_code, "example.com") == [
        (["ping", "-c", "1", "example.com"], {"check": True})
    ]


def test_behaviour_a_semicolon_value_never_reaches_the_command():
    with pytest.raises(ValueError, match="unsafe command argument"):
        _execute(applied(SNIPPET).fixed_code, "a; id")


def test_behaviour_an_option_value_is_rejected_by_the_guard():
    with pytest.raises(ValueError, match="unsafe command argument"):
        _execute(applied(SNIPPET).fixed_code, "--version")


def test_behaviour_without_the_guard_a_semicolon_is_a_single_harmless_argument():
    calls = _execute(applied(SNIPPET, guard=False).fixed_code, "a; id")
    assert calls == [(["ping", "-c", "1", "a; id"], {"check": True})]  # no shell: one argument


def test_without_the_guard_an_option_value_is_NOT_stopped():
    # documents the limit that the guard exists for (argument injection)
    calls = _execute(applied(SNIPPET, guard=False).fixed_code, "--version")
    assert calls[0][0][-1] == "--version"


def test_the_guard_pattern_rejects_what_it_should():
    pattern = re.compile(ARG_PATTERN)
    for good in ("example.com", "host_1", "a-b.c", ".hidden"):
        assert pattern.fullmatch(good)
    for bad in ("-v", "--version", "a b", "a;b", "", "a/b", "a\nb", "$(id)"):
        assert not pattern.fullmatch(bad)


# --- verdict (D35): CWE-78 is weak/none, the pattern check decides, re-detection does not ------


def test_verdict_passes_on_the_pattern_check_although_redetection_still_flows():
    fixed = applied(SNIPPET).fixed_code
    checks = Checks(
        syntax_ok=SourceText.parse(fixed) is not None,
        redetect_ok=False,  # py19: a correct fix still flows; passed by hand in W2
        tests_ok=None,
        pattern_ok=argv_list_no_shell(fixed),
    )
    report = make_report(Rating.NONE, checks)
    assert report.verdict == "PASS"
    assert report.redetect_ok is False
    assert report.notes.startswith(
        "[evidence] syntax=ok; redetect=false(not decisive); pattern_check=ok; tests=not_run."
    )
    assert "Not verified by re-detection." in report.notes


def test_verdict_fails_if_the_pattern_check_fails_even_when_the_detector_is_quiet():
    vulnerable = SNIPPET
    checks = Checks(
        syntax_ok=True,
        redetect_ok=True,
        tests_ok=None,
        pattern_ok=argv_list_no_shell(vulnerable),
    )
    assert make_report(Rating.NONE, checks).verdict == "FAIL"
