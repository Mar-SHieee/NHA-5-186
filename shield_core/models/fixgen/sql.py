"""CWE-89 fix template (plan section 4.1): constant SQL with placeholders, values as parameters.

    q = "SELECT * FROM u WHERE id = " + uid          cursor.execute("SELECT * FROM u WHERE id = %s",
    cursor.execute(q)                         ->                    (uid,))

Applies to exactly one `<obj>.execute(arg)` whose SQL is built by `+`, an f-string, `%` or
`.format()`, inline or in a variable assigned once. Everything else is a refusal with a reason.
"""

from __future__ import annotations

import ast
import re

from shield_core.models.fixgen.astutil import (
    single_assignment,
    top_level_modules,
)
from shield_core.models.fixgen.base import TemplateResult, finalize, refuse
from shield_core.models.fixgen.strings import Piece, decompose, py_literal, value_text
from shield_core.verify.pysource import Edit, SourceText

# Placeholder style by DB-API driver (survey 4.1). Keys are lowercase top-level module names.
_STYLES = {"sqlite3": "?", "psycopg2": "%s", "pymysql": "%s", "mysqldb": "%s"}
# Drivers and ORMs that are visible in imports but not handled in v1: seeing one means refusal.
_UNSUPPORTED = frozenset(
    {
        "sqlalchemy",
        "psycopg",
        "asyncpg",
        "aiosqlite",
        "aiomysql",
        "mysql",
        "pymssql",
        "pyodbc",
        "oracledb",
        "cx_oracle",
        "peewee",
    }
)
# A value may only follow a comparison operator, optionally inside quotes: `= 'x'`, `>= 5`.
_VALUE_POSITION = re.compile(r"(?:<>|!=|<=|>=|=|<|>)\s*(['\"]?)\Z")
_AFTER_VALUE = re.compile(r"[\s),;]")


def _detect_style(text: str) -> tuple[str | None, str]:
    modules = top_level_modules(text)
    drivers = (modules & _STYLES.keys()) | (modules & _UNSUPPORTED)
    if not drivers:
        return None, "cannot tell the database driver (no known driver import is visible)"
    if len(drivers) > 1:
        return None, f"several database drivers are imported ({', '.join(sorted(drivers))})"
    (driver,) = drivers
    if driver not in _STYLES:
        return None, f"the database driver {driver!r} is not supported yet"
    return _STYLES[driver], ""


def _candidates(tree: ast.AST) -> list[ast.Call]:
    """`.execute(x)` calls whose first argument is not a plain string literal."""
    found = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "execute"
            and node.args
        ):
            first = node.args[0]
            if not (isinstance(first, ast.Constant) and isinstance(first.value, str)):
                found.append(node)
    return found


def _build(pieces: list[Piece], style: str) -> tuple[str, list[Piece]] | str:
    """The new SQL text and the values in order, or a refusal reason."""
    sql: list[str] = []  # output text (with escaping)
    pre = ""  # raw text so far, placeholders included, used to judge each value position
    values: list[Piece] = []
    closing_quote = ""
    after_value = False
    for piece in pieces:
        if piece.text is not None:
            text = piece.text
            if closing_quote:
                if not text.startswith(closing_quote):
                    return "a quote around a value is not closed right after it"
                text, closing_quote = text[1:], ""
            if after_value and text and not _AFTER_VALUE.match(text):
                return "a value is glued to the text after it (part of a larger word)"
            after_value = False
            pre += text
            sql.append(text.replace("%", "%%") if style == "%s" else text)
            continue
        match = _VALUE_POSITION.search(pre)
        if match is None:
            return (
                "a value is not directly after a comparison operator "
                "(identifier, ORDER BY, IN (...), LIKE or LIMIT position)"
            )
        head = pre[: match.start(1)]
        if head.count("'") % 2 or head.count('"') % 2:
            return "a value sits inside a quoted SQL string"
        if match.group(1):  # drop the opening quote: a placeholder is never quoted
            closing_quote = match.group(1)
            pre = pre[:-1]
            sql[-1] = sql[-1][:-1]
        pre += style
        sql.append(style)
        values.append(piece)
        after_value = True
    if closing_quote:
        return "a quote around a value is not closed"
    if not values:
        return "nothing to parameterize: no interpolated value"
    return "".join(sql), values


def sql_parameterize(code: str, context: str = "") -> TemplateResult:
    src = SourceText.parse(code)
    if src is None:
        return refuse("the code does not parse")
    style, why = _detect_style(code + "\n" + context)
    if style is None:
        return refuse(why)

    candidates = _candidates(src.tree)
    if not candidates:
        return refuse("no execute() call with a built query was found")
    if len(candidates) > 1:
        return refuse("more than one execute() call with a built query; fixing none")
    call = candidates[0]
    if len(call.args) != 1 or call.keywords:
        return refuse("execute() already has parameters or keyword arguments")
    arg = call.args[0]
    if isinstance(arg, ast.Starred):
        return refuse("execute() gets a starred argument")

    edits: list[Edit] = []
    expression: ast.expr = arg
    between: list[ast.stmt] = []
    if isinstance(arg, ast.Name):
        definition, why = single_assignment(src, arg.id, call)
        if definition is None:
            return refuse(why)
        loads = sum(
            1
            for n in ast.walk(src.tree)
            if isinstance(n, ast.Name) and n.id == arg.id and isinstance(n.ctx, ast.Load)
        )
        if loads != 1:
            return refuse(f"'{arg.id}' is used more than once, so its assignment cannot be removed")
        statement = definition.statement
        if src.before_on_line(statement).strip():
            return refuse("the assignment shares its line with other code")
        rest = src.after_on_line(statement).strip()
        if rest and not rest.startswith("#"):
            return refuse("the assignment shares its line with other code")
        expression, between = statement.value, definition.between
        # delete the whole assignment (with its trailing comment and line break)
        end = src.span(statement)[1] + len(src.after_on_line(statement))
        for line_break in ("\r\n", "\n", "\r"):
            if src.code.startswith(line_break, end):
                end += len(line_break)
                break
        edits.append((src.line_start(statement), end, ""))

    pieces, why = decompose(expression)
    if pieces is None:
        return refuse(why)
    built = _build(pieces, style)
    if isinstance(built, str):
        return refuse(built)
    sql_text, values = built

    if between:
        loaded = {
            n.id
            for p in values
            for n in ast.walk(p.value)
            if isinstance(n, ast.Name)  # type: ignore[arg-type]
        }
        stored = {
            n.id
            for stmt in between
            for n in ast.walk(stmt)
            if isinstance(n, ast.Name) and isinstance(n.ctx, (ast.Store, ast.Del))
        }
        if loaded & stored:
            return refuse(
                "a value is reassigned between the query assignment and execute(): "
                + ", ".join(sorted(loaded & stored))
            )

    literal = py_literal(sql_text)
    if literal is None:
        return refuse("the new SQL text cannot be written as a safe string literal")
    texts = [value_text(src, v) for v in values]
    params = f"({texts[0]},)" if len(texts) == 1 else "(" + ", ".join(texts) + ")"
    edits.append((*src.span(arg), f"{literal}, {params}"))

    fixed = src.apply(edits)
    return finalize(
        fixed,
        f"parameterized the query: {len(values)} value(s) moved out of the SQL text "
        f"(placeholder {style})",
    )
