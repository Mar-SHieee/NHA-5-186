"""CWE-22 fix template (plan section 4.3): resolve the final path and keep it inside the base.

    open(os.path.join(BASE, name))
    -->
    base = Path(BASE).resolve()
    target = (base / name).resolve()
    if not target.is_relative_to(base):
        raise ValueError("path escapes base directory")
    open(target)

Applies to `open(os.path.join(<base>, <var>))`, inline or through one plain assignment
(`p = os.path.join(...)`; then the assignment itself is replaced and `open(p)` stays). Refuses when
there is no base directory (no two-argument `os.path.join`). `Path("/srv") / "/etc/passwd"` is
`/etc/passwd`, so an absolute input is rejected by the guard too.

D35: re-detection still reports a flow for this fixed shape (py20), so the verdict comes from the
pattern check `resolve_confine_before_open`, not from re-detection.
"""

from __future__ import annotations

import ast

from shield_core.fix.templates.astutil import (
    enclosing_statement,
    fresh_name,
    has_from_import,
    rebound_names,
    single_assignment,
    used_names,
)
from shield_core.fix.templates.base import TemplateResult, finalize, refuse
from shield_core.verify.pysource import Edit, SourceText, dotted_name, parent_map

IMPORT_LINE = "from pathlib import Path"


def _is_join(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and dotted_name(node.func) == "os.path.join"
        and len(node.args) == 2
        and not node.keywords
        and not any(isinstance(a, ast.Starred) for a in node.args)
    )


def path_confine(code: str, context: str = "") -> TemplateResult:
    src = SourceText.parse(code)
    if src is None:
        return refuse("the code does not parse")
    tree = src.tree

    candidates = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "open"
        ):
            if node.args:
                first = node.args[0]
                if not (isinstance(first, ast.Constant) and isinstance(first.value, str)):
                    candidates.append(node)
    if not candidates:
        return refuse("no open() call with a built path was found")
    if len(candidates) > 1:
        return refuse("more than one open() call with a built path; fixing none")
    call = candidates[0]
    arg = call.args[0]

    assignment: ast.Assign | None = None
    if _is_join(arg):
        join = arg
    elif isinstance(arg, ast.Name):
        definition, why = single_assignment(src, arg.id, call)
        if definition is None:
            return refuse(f"no base directory could be found: {why}")
        if not _is_join(definition.statement.value):
            return refuse(f"'{arg.id}' is not built with a two-argument os.path.join(base, name)")
        assignment, join = definition.statement, definition.statement.value
    else:
        return refuse("the path is not built with os.path.join(base, name): there is no base")
    base_expr, name_expr = join.args  # type: ignore[attr-defined]

    clash = rebound_names(tree, {"Path"})
    if clash:
        return refuse("the function rebinds Path, shadowing the new import")

    used = used_names(tree)
    base_name = fresh_name("base", used)
    base_text, name_text = src.text(base_expr), src.text(name_expr)

    edits: list[Edit] = []
    if assignment is not None:
        # replace the assignment by the guard; the variable keeps its name and now holds the
        # resolved path, so open(p) and every later use stay as they are
        variable = assignment.targets[0].id  # type: ignore[attr-defined]
        if src.before_on_line(assignment).strip():
            return refuse("the assignment shares its line with other code")
        rest = src.after_on_line(assignment).strip()
        if rest and not rest.startswith("#"):
            return refuse("the assignment shares its line with other code")
        indent = src.before_on_line(assignment)
        lines = _guard_lines(base_name, variable, base_text, name_text, indent)
        edits.append((*src.span(assignment), (src.newline + indent).join(lines)))
    else:
        statement, why = enclosing_statement(call, parent_map(tree))
        if statement is None:
            return refuse(why)
        indent = src.before_on_line(statement)
        if indent.strip():
            return refuse("the statement shares its line with other code")
        target = fresh_name("target", used)
        lines = _guard_lines(base_name, target, base_text, name_text, indent)
        block = "".join(f"{indent}{line}{src.newline}" for line in lines)
        start = src.line_start(statement)
        edits.append((start, start, block))
        edits.append((*src.span(arg), target))

    fixed = src.apply(edits)
    imports = () if has_from_import(code + "\n" + context, "pathlib", "Path") else (IMPORT_LINE,)
    return finalize(fixed, "confined the path to its base directory with resolve()", imports)


def _guard_lines(base: str, target: str, base_text: str, name_text: str, indent: str) -> list[str]:
    unit = "\t" if "\t" in indent else "    "
    return [
        f"{base} = Path({base_text}).resolve()",
        f"{target} = ({base} / {name_text}).resolve()",
        f"if not {target}.is_relative_to({base}):",
        f'{unit}raise ValueError("path escapes base directory")',
    ]
