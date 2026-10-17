"""CWE-89 template (W2-P4-03, Step 24): small vulnerable snippets in, fixed snippets out."""

import sqlite3
import textwrap

import pytest

from shield_core.models.fixgen.sql import sql_parameterize
from shield_core.verify.evidence import Checks, Rating, make_report
from shield_core.verify.pattern_checks import execute_literal_sql
from shield_core.verify.pysource import SourceText

PG = "import psycopg2\n"
LITE = "import sqlite3\n"


def fix(code: str, context: str = ""):
    return sql_parameterize(code, context)


def applied(code: str, context: str = "") -> str:
    result = fix(code, context)
    assert result.applied, result.reason
    assert result.fixed_code is not None
    return result.fixed_code


def refused(code: str, context: str = "") -> str:
    result = fix(code, context)
    assert not result.applied and result.fixed_code is None
    assert result.reason
    return result.reason


# --- the four expression forms, inline and through a variable ---------------------------------

EXPRESSIONS = {
    "plus": '"SELECT * FROM u WHERE id = " + uid',
    "fstring": 'f"SELECT * FROM u WHERE id = {uid}"',
    "percent": '"SELECT * FROM u WHERE id = %s" % uid',
    "percent_tuple": '"SELECT * FROM u WHERE id = %s" % (uid,)',
    "format": '"SELECT * FROM u WHERE id = {}".format(uid)',
    "format_indexed": '"SELECT * FROM u WHERE id = {0}".format(uid)',
}


@pytest.mark.parametrize("form", EXPRESSIONS)
def test_inline_form(form):
    code = f"{PG}def h(cursor, uid):\n    cursor.execute({EXPRESSIONS[form]})\n"
    assert applied(code) == (
        f'{PG}def h(cursor, uid):\n    cursor.execute("SELECT * FROM u WHERE id = %s", (uid,))\n'
    )


@pytest.mark.parametrize("form", EXPRESSIONS)
def test_variable_form_removes_the_assignment(form):
    code = (
        f"{PG}def h(cursor, uid):\n"
        f"    query = {EXPRESSIONS[form]}\n"
        f"    cursor.execute(query)\n"
        f"    return cursor.fetchall()\n"
    )
    assert applied(code) == (
        f"{PG}def h(cursor, uid):\n"
        f'    cursor.execute("SELECT * FROM u WHERE id = %s", (uid,))\n'
        f"    return cursor.fetchall()\n"
    )


def test_the_survey_example():
    code = textwrap.dedent(
        """\
        import psycopg2
        def f(request, cursor):
            user_id = request.args["id"]
            query = "SELECT * FROM users WHERE id = " + user_id
            cursor.execute(query)
        """
    )
    assert applied(code) == textwrap.dedent(
        """\
        import psycopg2
        def f(request, cursor):
            user_id = request.args["id"]
            cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
        """
    )


def test_several_values_keep_their_order():
    code = LITE + 'def h(c, a, b):\n    c.execute("SELECT 1 WHERE x = " + a + " AND y < " + b)\n'
    assert 'c.execute("SELECT 1 WHERE x = ? AND y < ?", (a, b))' in applied(code)


def test_values_may_be_expressions():
    code = LITE + 'def h(c, request):\n    c.execute("SELECT 1 WHERE x = " + request.args["id"])\n'
    assert 'c.execute("SELECT 1 WHERE x = ?", (request.args["id"],))' in applied(code)


@pytest.mark.parametrize("op", ["=", "<", ">", "<=", ">=", "!=", "<>"])
def test_every_comparison_operator_is_a_value_position(op):
    code = LITE + f'def h(c, a):\n    c.execute("SELECT 1 WHERE x {op} " + a)\n'
    assert f'"SELECT 1 WHERE x {op} ?"' in applied(code)


# --- quotes: a placeholder is never quoted -----------------------------------------------------


QUOTED = {
    "single": 'c.execute("SELECT 1 WHERE n = \'" + name + "\'")',
    "double": "c.execute('SELECT 1 WHERE n = \"' + name + '\"')",
}


@pytest.mark.parametrize("statement", QUOTED.values(), ids=QUOTED.keys())
def test_quotes_around_a_value_are_removed(statement):
    code = f"{LITE}def h(c, name):\n    {statement}\n"
    assert 'c.execute("SELECT 1 WHERE n = ?", (name,))' in applied(code)


def test_quotes_removed_in_an_fstring_with_more_text_after():
    code = LITE + "def h(c, n):\n    c.execute(f\"SELECT 1 WHERE n = '{n}' ORDER BY id\")\n"
    assert 'c.execute("SELECT 1 WHERE n = ? ORDER BY id", (n,))' in applied(code)


def test_a_quote_that_is_not_closed_is_refused():
    code = LITE + 'def h(c, n):\n    c.execute("SELECT 1 WHERE n = \'" + n)\n'
    assert "not closed" in refused(code)


def test_mismatched_closing_quote_is_refused():
    code = LITE + "def h(c, n):\n    c.execute(\"SELECT 1 WHERE n = '\" + n + '\"')\n"
    assert "not closed" in refused(code)


# --- driver detection --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("imports", "placeholder"),
    [
        ("import sqlite3", "?"),
        ("import psycopg2", "%s"),
        ("import pymysql", "%s"),
        ("import PyMySQL", "%s"),
        ("import MySQLdb", "%s"),
        ("from sqlite3 import connect", "?"),
        ("import psycopg2.extras", "%s"),
        ("import sqlite3 as db", "?"),
    ],
)
def test_driver_decides_the_placeholder(imports, placeholder):
    code = f'{imports}\ndef h(c, a):\n    c.execute("SELECT 1 WHERE x = " + a)\n'
    assert f'"SELECT 1 WHERE x = {placeholder}"' in applied(code)


def test_driver_can_come_from_the_context_only():
    code = 'def h(c, a):\n    c.execute("SELECT 1 WHERE x = " + a)\n'
    assert refused(code).startswith("cannot tell the database driver")
    assert '"SELECT 1 WHERE x = ?"' in applied(code, context="import sqlite3\nimport os\n")


@pytest.mark.parametrize(
    ("imports", "expected"),
    [
        ("import os", "cannot tell the database driver"),
        ("import sqlite3\nimport psycopg2", "several database drivers"),
        ("import sqlalchemy", "not supported yet"),
        ("import psycopg2\nimport sqlalchemy", "several database drivers"),
        ("import psycopg", "not supported yet"),
    ],
)
def test_driver_that_cannot_be_told_is_refused(imports, expected):
    code = f'{imports}\ndef h(c, a):\n    c.execute("SELECT 1 WHERE x = " + a)\n'
    assert expected in refused(code)


def test_percent_in_the_sql_text_is_doubled_for_percent_drivers_only():
    body = 'def h(c, a):\n    c.execute("SELECT 1 WHERE n = " + a + " AND t LIKE \'x%\'")\n'
    assert "LIKE 'x%%'" in applied(PG + body)
    assert "LIKE 'x%'" in applied(LITE + body)


def test_a_double_percent_in_the_original_format_string_stays_one_percent_for_sqlite():
    code = LITE + "def h(c, a):\n    c.execute(\"SELECT 1 WHERE n = '%s' AND t LIKE 'x%%'\" % a)\n"
    assert "LIKE 'x%'" in applied(code)


# --- every refusal from the survey and the plan ------------------------------------------------

REFUSALS = [
    ("table name from input", 'c.execute("SELECT * FROM " + t + " WHERE id = 1")', "comparison"),
    ("column name from input", 'c.execute("SELECT " + col + " FROM u")', "comparison"),
    ("order by", 'c.execute("SELECT * FROM u ORDER BY id " + direction)', "comparison"),
    ("order by column", 'c.execute("SELECT * FROM u ORDER BY " + col)', "comparison"),
    ("IN list", 'c.execute("SELECT * FROM u WHERE id IN (" + ids + ")")', "comparison"),
    (
        "LIKE with percent",
        'c.execute("SELECT * FROM u WHERE n LIKE \'%" + n + "%\'")',
        "comparison",
    ),
    ("LIKE plain", 'c.execute("SELECT * FROM u WHERE n LIKE " + n)', "comparison"),
    ("LIMIT", 'c.execute("SELECT * FROM u LIMIT " + n)', "comparison"),
    ("value inside a string", 'c.execute("SELECT \'a = " + n + "\'")', "quoted SQL string"),
    ("glued to a word", 'c.execute("SELECT * FROM u WHERE id = " + n + "abc")', "larger word"),
    ("adjacent values", 'c.execute("SELECT * FROM u WHERE id = " + a + b)', "comparison"),
    ("starts with a value", 'c.execute(a + " WHERE id = 1")', "comparison"),
    ("no interpolation", 'c.execute("SELECT 1" + "")', "nothing to parameterize"),
    ("percent d", 'c.execute("SELECT * FROM u WHERE id = %d" % n)', "not supported"),
    ("percent mapping", 'c.execute("SELECT * FROM u WHERE id = %(id)s" % {"id": n})', "mapping"),
    ("fstring conversion", 'c.execute(f"SELECT * FROM u WHERE id = {n!r}")', "conversion"),
    ("fstring format spec", 'c.execute(f"SELECT * FROM u WHERE id = {n:>5}")', "format spec"),
    ("format name", 'c.execute("SELECT * FROM u WHERE id = {n}".format(n=n))', "keyword"),
    ("format reuse", 'c.execute("SELECT * FROM u WHERE a = {0} AND b = {0}".format(n))', "twice"),
    ("not a string form", "c.execute(build_query(n))", "not built with"),
    ("non string constant", 'c.execute("SELECT * FROM u WHERE id = " + 5)', "non-string"),
    ("second positional argument", 'c.execute("SELECT * FROM u WHERE id = " + n, (1,))', "already"),
    ("keyword argument", 'c.execute("SELECT * FROM u WHERE id = " + n, params=(1,))', "already"),
    ("starred", "c.execute(*parts)", "starred"),
]


@pytest.mark.parametrize(("label", "statement", "expected"), REFUSALS, ids=[r[0] for r in REFUSALS])
def test_refuses(label, statement, expected):
    code = f"{LITE}def h(c, a, b, n, t, col, ids, direction, parts):\n    {statement}\n"
    assert expected in refused(code)


def test_refuses_two_candidate_calls():
    code = (
        f"{LITE}def h(c, a, b):\n"
        '    c.execute("SELECT 1 WHERE x = " + a)\n'
        '    c.execute("SELECT 2 WHERE y = " + b)\n'
    )
    assert "more than one" in refused(code)


def test_a_constant_second_execute_is_not_a_candidate():
    code = (
        f"{LITE}def h(c, a):\n"
        '    c.execute("SELECT 1 WHERE x = " + a)\n'
        '    c.execute("DELETE FROM log")\n'
    )
    assert 'c.execute("DELETE FROM log")' in applied(code)


def test_refuses_when_there_is_no_candidate():
    assert "no execute() call" in refused(f'{LITE}def h(c):\n    c.execute("SELECT 1")\n')
    assert "no execute() call" in refused(f"{LITE}def h(c):\n    return 1\n")


def test_refuses_code_that_does_not_parse():
    assert refused("def h(:\n") == "the code does not parse"


def test_refuses_python_2_style_code():
    assert refused('import sqlite3\nprint "x"\n') == "the code does not parse"


# --- conditional, piecewise or cross-function assembly -----------------------------------------


def test_refuses_conditional_assembly():
    code = (
        f"{LITE}def h(c, a, admin):\n"
        '    q = "SELECT * FROM u WHERE x = " + a\n'
        "    if admin:\n"
        '        q = q + " AND y = 1"\n'
        "    c.execute(q)\n"
    )
    assert "more than once" in refused(code)


def test_refuses_augmented_assignment():
    code = (
        f"{LITE}def h(c, a):\n"
        '    q = "SELECT * FROM u WHERE x = " + a\n'
        '    q += " AND y = 1"\n'
        "    c.execute(q)\n"
    )
    assert "more than once" in refused(code)


def test_refuses_building_in_a_loop():
    code = (
        f"{LITE}def h(c, items):\n"
        '    q = "SELECT * FROM u WHERE 1 = 1"\n'
        "    for i in items:\n"
        '        q = q + " OR x = " + i\n'
        "    c.execute(q)\n"
    )
    assert "more than once" in refused(code)


def test_refuses_a_query_that_is_a_parameter():
    code = f"{LITE}def h(c, query):\n    c.execute(query)\n"
    assert "parameter" in refused(code)


def test_refuses_a_query_built_in_another_function():
    code = f"{LITE}def h(c, a):\n    c.execute(make_query(a))\n"
    assert "not built with" in refused(code)


def test_refuses_an_assignment_in_another_block():
    code = (
        f"{LITE}def h(c, a, flag):\n"
        "    if flag:\n"
        '        q = "SELECT * FROM u WHERE x = " + a\n'
        "    c.execute(q)\n"
    )
    assert "same block" in refused(code)


def test_refuses_a_query_variable_used_twice():
    code = (
        f"{LITE}def h(c, a):\n"
        '    q = "SELECT * FROM u WHERE x = " + a\n'
        "    log(q)\n"
        "    c.execute(q)\n"
    )
    assert "used more than once" in refused(code)


def test_refuses_when_a_value_changes_between_assignment_and_execute():
    code = (
        f"{LITE}def h(c, a):\n"
        '    q = "SELECT * FROM u WHERE x = " + a\n'
        "    a = clean(a)\n"
        "    c.execute(q)\n"
    )
    assert "reassigned between" in refused(code)


def test_unrelated_statements_between_are_fine():
    code = (
        f"{LITE}def h(c, a):\n"
        '    q = "SELECT * FROM u WHERE x = " + a\n'
        "    cur = c.cursor()\n"
        "    cur.execute(q)\n"
    )
    assert applied(code).endswith(
        '    cur = c.cursor()\n    cur.execute("SELECT * FROM u WHERE x = ?", (a,))\n'
    )


def test_a_trailing_comment_on_the_removed_assignment_goes_with_it():
    code = LITE + 'def h(c, a):\n    q = "SELECT 1 WHERE x = " + a  # build\n    c.execute(q)\n'
    assert applied(code) == LITE + 'def h(c, a):\n    c.execute("SELECT 1 WHERE x = ?", (a,))\n'


def test_refuses_an_assignment_sharing_its_line():
    code = LITE + 'def h(c, a):\n    z = 1; q = "SELECT 1 WHERE x = " + a\n    c.execute(q)\n'
    assert "shares its line" in refused(code)


# --- the rest of the function is untouched -----------------------------------------------------


def test_everything_outside_the_sink_is_byte_identical():
    code = (
        "import psycopg2\n"
        "\n"
        "# keep this comment\n"
        "def h(request, cur):  # and this one\n"
        '    uid = request.args["id"]   # odd   spacing\n'
        '    cur.execute("SELECT * FROM u WHERE id = " + uid)\n'
        "    rows = cur.fetchall()\n"
        "    return [r for r in rows]   # tail\n"
    )
    fixed = applied(code)
    old_lines, new_lines = code.splitlines(), fixed.splitlines()
    assert len(old_lines) == len(new_lines)
    changed = [i for i, (a, b) in enumerate(zip(old_lines, new_lines, strict=True)) if a != b]
    assert changed == [5]


def test_unicode_before_the_call_does_not_shift_the_edit():
    code = LITE + 'def h(c, a):\n    note = "é"; c.execute("SELECT 1 WHERE x = " + a)\n'
    assert applied(code).endswith('note = "é"; c.execute("SELECT 1 WHERE x = ?", (a,))\n')


def test_crlf_line_endings_are_kept():
    code = (LITE + 'def h(c, a):\n    q = "SELECT 1 WHERE x = " + a\n    c.execute(q)\n').replace(
        "\n", "\r\n"
    )
    fixed = applied(code)
    assert "\n" not in fixed.replace("\r\n", "")
    assert fixed.endswith('    c.execute("SELECT 1 WHERE x = ?", (a,))\r\n')


def test_an_indented_method_is_handled():
    code = textwrap.indent(
        "def get(self, uid):\n"
        '    q = "SELECT * FROM u WHERE id = " + uid\n'
        "    self.cur.execute(q)\n",
        "    ",
    )
    result = sql_parameterize(code, LITE)  # the driver import comes from the context
    assert result.applied, result.reason
    assert result.fixed_code == textwrap.indent(
        'def get(self, uid):\n    self.cur.execute("SELECT * FROM u WHERE id = ?", (uid,))\n',
        "    ",
    )


def test_multiline_triple_quoted_sql_keeps_its_layout():
    code = LITE + (
        "def h(c, uid):\n"
        '    c.execute(f"""\n'
        "        SELECT *\n"
        "        FROM u\n"
        "        WHERE id = {uid}\n"
        '    """)\n'
    )
    fixed = applied(code)
    assert (
        'c.execute("""\n        SELECT *\n        FROM u\n        WHERE id = ?\n    """, (uid,))'
        in fixed
    )


def test_the_output_always_parses_and_the_pattern_check_flips():
    for expression in EXPRESSIONS.values():
        code = f"{PG}def h(cursor, uid):\n    cursor.execute({expression})\n"
        fixed = applied(code)
        assert SourceText.parse(fixed) is not None
        assert execute_literal_sql(code) is False
        assert execute_literal_sql(fixed) is True


def test_no_required_imports():
    assert (
        fix(f"{PG}def h(c, a):\n    c.execute('SELECT 1 WHERE x = ' + a)\n").required_imports == ()
    )


# --- behaviour on a real database: a normal id and a quote character (survey 4.1) --------------


def _database():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE u (id INTEGER, name TEXT)")
    conn.executemany("INSERT INTO u VALUES (?, ?)", [(1, "ann"), (2, "bob"), (3, "o'brien")])
    return conn


def _run(code: str, value) -> list:
    namespace: dict = {}
    exec(compile(code, "<snippet>", "exec"), namespace)  # noqa: S102 - test snippet
    return namespace["lookup"](_database(), value)


VULNERABLE = """\
import sqlite3


def lookup(conn, name):
    cursor = conn.cursor()
    query = "SELECT id FROM u WHERE name = '" + name + "'"
    cursor.execute(query)
    return cursor.fetchall()
"""


def test_behaviour_normal_value_gives_the_same_rows():
    fixed = applied(VULNERABLE)
    assert _run(VULNERABLE, "bob") == _run(fixed, "bob") == [(2,)]


def test_behaviour_a_quote_character_now_works():
    fixed = applied(VULNERABLE)
    assert _run(fixed, "o'brien") == [(3,)]
    with pytest.raises(sqlite3.OperationalError):  # the vulnerable query breaks on the quote
        _run(VULNERABLE, "o'brien")


def test_behaviour_an_injection_payload_is_just_a_value():
    fixed = applied(VULNERABLE)
    payload = "x' OR '1'='1"
    assert len(_run(VULNERABLE, payload)) == 3  # the bug: every row comes back
    assert _run(fixed, payload) == []  # fixed: no user has that name


def test_behaviour_numeric_id_in_the_fixed_query():
    code = VULNERABLE.replace('name = \'" + name + "\'"', 'id = " + str(name)')
    fixed = applied(code)
    assert _run(fixed, 2) == [(2,)]


# --- verdict (D35): CWE-89 is a strong class, so re-detection gates PASS -----------------------


def test_strong_class_verdict_follows_redetection():
    fixed = applied(VULNERABLE)
    assert SourceText.parse(fixed) is not None
    checks = Checks(
        syntax_ok=True,
        redetect_ok=True,  # in W2 passed by hand: the Joern hook is W3-P4-01
        tests_ok=None,
        pattern_ok=execute_literal_sql(fixed),
    )
    report = make_report(Rating.STRONG, checks)
    assert report.verdict == "PASS"
    assert "pattern_check=ok" in report.notes
    assert make_report(Rating.STRONG, Checks(True, False, None, True)).verdict == "FAIL"


def test_fstring_values_work_on_python_before_3_12(monkeypatch):
    # Before 3.12 the positions inside an f-string are unreliable, so the value is unparsed.
    import types

    from shield_core.models.fixgen import strings

    monkeypatch.setattr(strings, "sys", types.SimpleNamespace(version_info=(3, 11, 0)))
    code = (
        LITE + "def h(c, request):\n    c.execute(f\"SELECT 1 WHERE x = {request.args['id']}\")\n"
    )
    assert "(request.args['id'],)" in applied(code)
