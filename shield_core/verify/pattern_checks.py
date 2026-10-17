"""Syntactic checks per fix class (D35, plan W2-P4-03).

Each check takes the PATCHED code and returns True when the cheap structural property that the
class's verdict depends on holds. They never run code and never raise: code that does not parse
is simply False. The names are the `pattern_check` values in languages/<language>.yaml.

    execute_literal_sql          CWE-89  every execute() call has a string literal as its SQL
    argv_list_no_shell           CWE-78  subprocess.run gets a list literal, no shell anywhere
    resolve_confine_before_open  CWE-22  resolve(), is_relative_to() and a rejection precede open()

For the strong class (CWE-89) the result is recorded in the notes and is not a gate (D35); for
the weak/none classes it IS the gate, together with syntax and tests (evidence.decide_verdict).
"""

from __future__ import annotations

import ast
from collections.abc import Callable

from shield_core.verify.pysource import SourceText, dotted_name


def _calls(tree: ast.AST) -> list[ast.Call]:
    return [n for n in ast.walk(tree) if isinstance(n, ast.Call)]


def execute_literal_sql(code: str) -> bool:
    src = SourceText.parse(code)
    if src is None:
        return False
    executes = [
        c
        for c in _calls(src.tree)
        if isinstance(c.func, ast.Attribute) and c.func.attr == "execute" and c.args
    ]
    return bool(executes) and all(
        isinstance(c.args[0], ast.Constant) and isinstance(c.args[0].value, str) for c in executes
    )


def argv_list_no_shell(code: str) -> bool:
    src = SourceText.parse(code)
    if src is None:
        return False
    calls = _calls(src.tree)
    runs = [c for c in calls if dotted_name(c.func) == "subprocess.run"]
    if not runs:
        return False
    if any(dotted_name(c.func) == "os.system" for c in calls):
        return False  # a shell is still in use
    for call in calls:
        for keyword in call.keywords:
            if keyword.arg == "shell" and not (
                isinstance(keyword.value, ast.Constant) and keyword.value.value is False
            ):
                return False
    return all(c.args and isinstance(c.args[0], ast.List) for c in runs)


def _is_rejection(statements: list[ast.stmt]) -> bool:
    return any(isinstance(n, (ast.Raise, ast.Return)) for s in statements for n in ast.walk(s))


def resolve_confine_before_open(code: str) -> bool:
    src = SourceText.parse(code)
    if src is None:
        return False
    opens = [c for c in _calls(src.tree) if isinstance(c.func, ast.Name) and c.func.id == "open"]
    if not opens:
        return False
    first_open = min(src.span(c)[0] for c in opens)

    def before_open(node: ast.AST) -> bool:
        return src.span(node)[1] <= first_open

    resolves = [
        c
        for c in _calls(src.tree)
        if isinstance(c.func, ast.Attribute) and c.func.attr == "resolve" and before_open(c)
    ]
    guards = []
    for node in ast.walk(src.tree):
        if isinstance(node, ast.If) and before_open(node):
            tests = [
                c
                for c in _calls(node.test)
                if isinstance(c.func, ast.Attribute) and c.func.attr == "is_relative_to"
            ]
            if tests and _is_rejection(node.body + node.orelse):
                guards.append(node)
    return bool(resolves) and bool(guards)


PATTERN_CHECKS: dict[str, Callable[[str], bool]] = {
    "execute_literal_sql": execute_literal_sql,
    "argv_list_no_shell": argv_list_no_shell,
    "resolve_confine_before_open": resolve_confine_before_open,
}


def get_pattern_check(name: str) -> Callable[[str], bool]:
    try:
        return PATTERN_CHECKS[name]
    except KeyError:
        raise KeyError(
            f"unknown pattern check {name!r}; known: {', '.join(PATTERN_CHECKS)}"
        ) from None
