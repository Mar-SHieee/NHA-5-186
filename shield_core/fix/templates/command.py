"""CWE-78 fix template (plan section 4.2): no shell, command and arguments as a list.

    os.system("ping -c 1 " + host)
    -->
    if not re.fullmatch(r"[A-Za-z0-9_.][A-Za-z0-9_.-]*", host):
        raise ValueError("unsafe command argument")
    subprocess.run(["ping", "-c", "1", host], check=True)

Applies to `os.system(<string>)` and `subprocess.run(<string>, shell=True)` where the string is a
literal command plus variables, each variable a whole shell word. Refuses shell features, values
that are part of a word or a quoted expression, and a command name that comes from input.

The validation guard (decision O5) rejects a value that could be read as an option (it cannot start
with `-`). It CHANGES BEHAVIOUR for values with other characters (spaces, `/`, ...): the pattern is
a placeholder to tighten per command (docs/fixes/fix_templates_python.md). `guard=False` gives
list form
only.

D35: re-detection still reports a flow for this fixed shape (py19), so the verdict comes from the
pattern check `argv_list_no_shell`, not from re-detection.
"""

from __future__ import annotations

import ast
import json
import re
import shlex

from shield_core.fix.templates.astutil import (
    enclosing_statement,
    fresh_name,
    has_import,
    rebound_names,
    used_names,
)
from shield_core.fix.templates.base import TemplateResult, finalize, refuse
from shield_core.fix.templates.strings import decompose, value_text
from shield_core.verify.pysource import Edit, SourceText, dotted_name, parent_map

ARG_PATTERN = r"[A-Za-z0-9_.][A-Za-z0-9_.-]*"

# Keyword arguments of subprocess.run the rewrite understands and keeps unchanged.
_KEPT_KEYWORDS = frozenset(
    {
        "check",
        "capture_output",
        "text",
        "timeout",
        "cwd",
        "stdin",
        "stdout",
        "stderr",
        "input",
        "env",
        "encoding",
        "errors",
        "universal_newlines",
    }
)
# Anything the shell would interpret: pipes, redirects, globs, substitution, comments, escapes,
# and the cmd.exe characters (% ^), because os.system uses cmd.exe on Windows.
_SHELL_FEATURE = re.compile(r"[|&;<>()$`*?\[\]{}~#!\\\n\r%^]")
_ENV_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")


def _is_candidate(call: ast.Call) -> bool:
    name = dotted_name(call.func)
    if name == "os.system":
        return True
    return name == "subprocess.run" and any(k.arg == "shell" for k in call.keywords)


def command_argv(code: str, context: str = "", *, guard: bool = True) -> TemplateResult:
    src = SourceText.parse(code)
    if src is None:
        return refuse("the code does not parse")
    tree = src.tree
    candidates = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and _is_candidate(n)]
    if not candidates:
        return refuse("no os.system() or subprocess.run(..., shell=...) call was found")
    if len(candidates) > 1:
        return refuse("more than one shell command call; fixing none")
    call = candidates[0]
    is_system = dotted_name(call.func) == "os.system"

    kept: list[str] = []
    if is_system:
        if len(call.args) != 1 or call.keywords or isinstance(call.args[0], ast.Starred):
            return refuse("os.system() is not called with a single plain argument")
    else:
        if len(call.args) != 1 or isinstance(call.args[0], ast.Starred):
            return refuse("subprocess.run() does not get exactly one positional argument")
        for keyword in call.keywords:
            if keyword.arg == "shell":
                if not (isinstance(keyword.value, ast.Constant) and keyword.value.value is True):
                    return refuse("shell= is not the literal True")
            elif keyword.arg in _KEPT_KEYWORDS:
                kept.append(src.text(keyword))
            else:
                return refuse(f"subprocess.run() keyword {keyword.arg or '**'!r} is not understood")

    parents = parent_map(tree)
    statement, why = enclosing_statement(call, parents)
    if statement is None:
        return refuse(why)
    if is_system and not (isinstance(statement, ast.Expr) and statement.value is call):
        return refuse("the result of os.system() is used, subprocess.run() returns another type")
    indent = src.before_on_line(statement)
    if guard and indent.strip():
        return refuse("the statement shares its line with other code")

    pieces, why = decompose(call.args[0])
    if pieces is None:
        return refuse(f"the command is not built inside the call: {why}")
    if not any(p.value is not None for p in pieces):
        return refuse("the command has no variable part")

    items: list[str] = []  # source text of each argv element
    origin: list[str] = []  # "literal" or "value", parallel to items
    values: list[ast.expr] = []
    for position, piece in enumerate(pieces):
        if piece.text is not None:
            text = piece.text
            if _SHELL_FEATURE.search(text):
                return refuse("the command uses shell features (pipe, redirect, glob, $, ...)")
            if position > 0 and text and not text[0].isspace():
                return refuse("a value is part of a larger word")
            try:
                words = shlex.split(text)
            except ValueError:
                return refuse("a quote in the command is not closed inside the literal text")
            items.extend(json.dumps(w, ensure_ascii=False) for w in words)
            origin.extend("literal" for _ in words)
        else:
            assert piece.value is not None
            if position == 0:
                return refuse("the command name comes from input")
            before = pieces[position - 1].text
            if before is None:
                return refuse("two values are joined without a space")
            if not before or not before[-1].isspace():
                return refuse("a value is part of a larger word or a quoted expression")
            values.append(piece.value)
            items.append(value_text(src, piece))
            origin.append("value")
    if not origin or origin[0] != "literal":
        return refuse("the command name comes from input")
    if _ENV_ASSIGNMENT.match(shlex.split(pieces[0].text or "")[0]):
        return refuse("the command starts with an environment variable assignment")

    needed = {"subprocess"} | ({"re"} if guard else set())
    clash = rebound_names(tree, needed)
    if clash:
        return refuse(f"the function rebinds {', '.join(sorted(clash))}, shadowing the new import")

    edits: list[Edit] = []
    checked: set[str] = set()  # names the guard validates
    if guard:
        preface: list[str] = []
        used = used_names(tree)
        value_index = 0
        for index, kind in enumerate(origin):
            if kind != "value":
                continue
            node = values[value_index]
            value_index += 1
            if isinstance(node, ast.Name):
                name = node.id
            else:
                name = fresh_name("cmd_arg", used)
                preface.append(f"{name} = {items[index]}")
                items[index] = name
            if name not in checked:
                checked.add(name)
                preface.append(f'if not re.fullmatch(r"{ARG_PATTERN}", {name}):')
                unit = "\t" if "\t" in indent else "    "
                preface.append(f'{unit}raise ValueError("unsafe command argument")')
        newline = src.newline
        block = "".join(f"{indent}{line}{newline}" for line in preface)
        start = src.line_start(statement)
        edits.append((start, start, block))

    argv = "[" + ", ".join(items) + "]"
    if is_system:
        replacement = f"subprocess.run({argv}, check=True)"
    else:
        replacement = f"{src.text(call.func)}({', '.join([argv, *kept])})"
    edits.append((*src.span(call), replacement))

    fixed = src.apply(edits)
    visible = code + "\n" + context
    imports = tuple(
        f"import {m}" for m in ("subprocess", "re") if m in needed and not has_import(visible, m)
    )
    summary = "ran the command as an argument list without a shell"
    if guard:
        summary += f"; added a validation guard on {len(checked)} value(s)"
    return finalize(fixed, summary, imports)
