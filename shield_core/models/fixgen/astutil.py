"""Small AST and import helpers used by more than one template."""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass

from shield_core.verify.pysource import SourceText, parent_map, statement_lists

# ------------------------------------------------------------------------------------ names


def used_names(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.arg):
            names.add(node.arg)
    return names


def fresh_name(preferred: str, used: set[str]) -> str:
    """`preferred`, or `preferred_1`, `preferred_2`, ... when it already occurs; marks it used."""
    name, n = preferred, 0
    while name in used:
        n += 1
        name = f"{preferred}_{n}"
    used.add(name)
    return name


def rebound_names(tree: ast.AST, names: set[str]) -> set[str]:
    """Which of `names` the function assigns or takes as a parameter (so a new import of the
    same name would be shadowed)."""
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            found.add(node.id)
        elif isinstance(node, ast.arg):
            found.add(node.arg)
    return found & names


# --------------------------------------------------------------------------------- imports

_IMPORT_RE = re.compile(r"^[ \t]*import[ \t]+([^#\n]+)", re.MULTILINE)
_FROM_RE = re.compile(r"^[ \t]*from[ \t]+([\w.]+)[ \t]+import[ \t]+([^(#\n][^#\n]*)", re.MULTILINE)
_FROM_PAREN_RE = re.compile(r"^[ \t]*from[ \t]+([\w.]+)[ \t]+import[ \t]*\(([^)]*)\)", re.MULTILINE)


def _alias_bound(entry: str, dotted: bool) -> str:
    """The name an import entry binds: `a.b` -> a, `a.b as c` -> c, `x as y` -> y."""
    parts = entry.split()
    if len(parts) == 3 and parts[1] == "as":
        return parts[2]
    return parts[0].split(".")[0] if dotted else parts[0]


def plain_imports(text: str) -> set[str]:
    """Names bound by `import x` statements anywhere in the text."""
    bound: set[str] = set()
    for match in _IMPORT_RE.finditer(text):
        for entry in match.group(1).split(","):
            if entry.split():
                bound.add(_alias_bound(entry, dotted=True))
    return bound


def from_imports(text: str) -> dict[str, set[str]]:
    """{module: names bound} for `from module import names` statements."""
    result: dict[str, set[str]] = {}
    for regex in (_FROM_RE, _FROM_PAREN_RE):
        for match in regex.finditer(text):
            body = re.sub(r"#[^\n]*", "", match.group(2))
            for entry in body.replace("\n", ",").split(","):
                if entry.split():
                    result.setdefault(match.group(1), set()).add(_alias_bound(entry, dotted=False))
    return result


def top_level_modules(text: str) -> set[str]:
    """Lowercase top-level names of every imported module (both import forms)."""
    modules: set[str] = set()
    for match in _IMPORT_RE.finditer(text):
        for entry in match.group(1).split(","):
            if entry.split():
                modules.add(entry.split()[0].split(".")[0].lower())
    for module in from_imports(text):
        modules.add(module.split(".")[0].lower())
    return modules


def has_import(text: str, module: str) -> bool:
    return module in plain_imports(text)


def has_from_import(text: str, module: str, name: str) -> bool:
    return name in from_imports(text).get(module, set())


# -------------------------------------------------------------------------------- statements

_SIMPLE_STATEMENTS = (ast.Expr, ast.Assign, ast.AnnAssign, ast.AugAssign, ast.Return)
_CONDITIONAL = (
    ast.Lambda,
    ast.IfExp,
    ast.BoolOp,
    ast.ListComp,
    ast.SetComp,
    ast.DictComp,
    ast.GeneratorExp,
)


def enclosing_statement(
    call: ast.Call, parents: dict[ast.AST, ast.AST]
) -> tuple[ast.stmt | None, str]:
    """The statement a block of new lines can be put in front of without changing when `call`
    runs. Refuses when the call is evaluated conditionally, repeatedly, or later."""
    node: ast.AST = call
    while True:
        parent = parents.get(node)
        if parent is None:
            return None, "the call is not inside a statement"
        if isinstance(parent, ast.stmt):
            break
        if isinstance(parent, _CONDITIONAL):
            return None, "the call is evaluated conditionally or later (lambda, comprehension, ...)"
        node = parent
    if isinstance(parent, _SIMPLE_STATEMENTS):
        return parent, ""
    if isinstance(parent, ast.With) and parent.items[0] is node:
        return parent, ""
    if isinstance(parent, ast.For) and parent.iter is node:
        return parent, ""
    return None, f"the call is in a {type(parent).__name__} statement the template does not handle"


@dataclass(frozen=True)
class Definition:
    statement: ast.Assign
    between: list[ast.stmt]  # statements strictly between the assignment and the use


def single_assignment(src: SourceText, name: str, use: ast.AST) -> tuple[Definition | None, str]:
    """The one plain `name = <expr>` that defines `name` before `use`, in the same block.

    Refuses when `name` is a parameter, is assigned more than once, is changed by `+=`, a loop,
    `with`, `except`, `global` ..., or is defined in another block (branch, loop, try).
    """
    tree = src.tree
    for node in ast.walk(tree):
        if isinstance(node, ast.arg) and node.arg == name:
            return None, f"'{name}' is a parameter, its value is built elsewhere"
        if isinstance(node, (ast.Global, ast.Nonlocal)) and name in node.names:
            return None, f"'{name}' is declared global or nonlocal"
        if isinstance(node, (ast.ExceptHandler, ast.MatchAs, ast.MatchStar)) and node.name == name:
            return None, f"'{name}' is also bound by except or match"
    stores = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Name) and n.id == name and isinstance(n.ctx, (ast.Store, ast.Del))
    ]
    if not stores:
        return None, f"'{name}' is not assigned in this function"
    if len(stores) > 1:
        return None, f"'{name}' is assigned more than once (conditional or piecewise building)"
    parent = parent_map(tree).get(stores[0])
    plain = isinstance(parent, ast.Assign) and parent.targets == [stores[0]]
    if not plain:
        return None, f"'{name}' is not defined by a plain assignment"
    use_start, use_end = src.span(use)
    assert isinstance(parent, ast.Assign)
    if src.span(parent)[1] > use_start:
        return None, f"'{name}' is assigned after it is used"
    for block in statement_lists(tree):
        if not any(stmt is parent for stmt in block):
            continue
        index = next(i for i, stmt in enumerate(block) if stmt is parent)
        for position in range(index + 1, len(block)):
            start, end = src.span(block[position])
            if start <= use_start and use_end <= end:
                return Definition(parent, block[index + 1 : position]), ""
        return None, f"the use of '{name}' is not in the same block as its assignment"
    return None, f"cannot locate the assignment of '{name}'"
