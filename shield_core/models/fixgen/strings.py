"""Take a string-building expression apart: literal text pieces and interpolated values.

Handles the four forms the survey lists: `+`, f-strings, `%` formatting and `.format()`.
Anything else (or any format option that changes the text: `!r`, `:>5`, `%d`, `{name}`) is
reported as a reason to refuse, never guessed.
"""

from __future__ import annotations

import ast
import json
import re
import string
import sys
from dataclasses import dataclass

from shield_core.verify.pysource import SourceText

# %[(key)][flags][width][.precision][length]type
_PERCENT_RE = re.compile(r"%(?:\([^)]*\))?[#0\- +]*(?:\d+|\*)?(?:\.(?:\d+|\*))?[hlL]?[a-zA-Z%]")


@dataclass(frozen=True)
class Piece:
    """Either literal `text`, or an interpolated `value` expression (exactly one is set)."""

    text: str | None = None
    value: ast.expr | None = None
    in_fstring: bool = False


Decomposed = tuple[list[Piece] | None, str]


def _merge(pieces: list[Piece]) -> list[Piece]:
    merged: list[Piece] = []
    for piece in pieces:
        if piece.text is not None and merged and merged[-1].text is not None:
            merged[-1] = Piece(text=merged[-1].text + piece.text)
        elif piece.text != "":
            merged.append(piece)
    return merged


def _is_str(node: ast.AST) -> bool:
    return isinstance(node, ast.Constant) and isinstance(node.value, str)


def decompose(node: ast.expr) -> Decomposed:
    """(pieces, "") for a recognised form, else (None, reason)."""
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return _concat(node)
    if isinstance(node, ast.JoinedStr):
        return _fstring(node)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod):
        return _percent(node)
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "format"
        and _is_str(node.func.value)
    ):
        return _format(node)
    return None, "the string is not built with +, an f-string, % or .format()"


def _flatten_add(node: ast.expr, out: list[ast.expr]) -> None:
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        _flatten_add(node.left, out)
        _flatten_add(node.right, out)
    else:
        out.append(node)


def _concat(node: ast.BinOp) -> Decomposed:
    items: list[ast.expr] = []
    _flatten_add(node, items)
    pieces: list[Piece] = []
    for item in items:
        if _is_str(item):
            pieces.append(Piece(text=item.value))  # type: ignore[attr-defined]
        elif isinstance(item, ast.Constant):
            return None, "a non-string constant is concatenated"
        elif isinstance(item, ast.JoinedStr):
            inner, why = _fstring(item)
            if inner is None:
                return None, why
            pieces.extend(inner)
        else:
            pieces.append(Piece(value=item))
    return _merge(pieces), ""


def _fstring(node: ast.JoinedStr) -> Decomposed:
    pieces: list[Piece] = []
    for part in node.values:
        if isinstance(part, ast.Constant):
            pieces.append(Piece(text=str(part.value)))
        elif isinstance(part, ast.FormattedValue):
            if part.conversion != -1 or part.format_spec is not None:
                return None, "an f-string field has a conversion or format spec (!r, :>5, ...)"
            pieces.append(Piece(value=part.value, in_fstring=True))
        else:  # pragma: no cover - the grammar has no other member
            return None, "unexpected f-string content"
    return _merge(pieces), ""


def _percent(node: ast.BinOp) -> Decomposed:
    if not _is_str(node.left):
        return None, "the left side of % is not a string literal"
    fmt: str = node.left.value  # type: ignore[attr-defined]
    right = node.right
    if isinstance(right, ast.Dict):
        return None, "% formatting with a mapping"
    if isinstance(right, ast.Tuple):
        if any(isinstance(e, ast.Starred) for e in right.elts):
            return None, "a starred value in % formatting"
        values = list(right.elts)
    else:
        values = [right]
    pieces: list[Piece] = []
    position, used = 0, 0
    for match in _PERCENT_RE.finditer(fmt):
        literal = fmt[position : match.start()]
        if "%" in literal:
            return None, "the % format string is malformed"
        pieces.append(Piece(text=literal))
        token = match.group(0)
        if token == "%%":
            pieces.append(Piece(text="%"))
        elif token == "%s":
            if used >= len(values):
                return None, "more %s fields than values"
            pieces.append(Piece(value=values[used]))
            used += 1
        else:
            return None, f"the % directive {token!r} is not supported (only %s and %%)"
        position = match.end()
    tail = fmt[position:]
    if "%" in tail:
        return None, "the % format string is malformed"
    pieces.append(Piece(text=tail))
    if used != len(values):
        return None, "the number of values does not match the number of %s fields"
    return _merge(pieces), ""


def _format(node: ast.Call) -> Decomposed:
    if node.keywords or any(isinstance(a, ast.Starred) for a in node.args):
        return None, ".format() with keyword or starred arguments"
    fmt: str = node.func.value.value  # type: ignore[attr-defined]
    try:
        fields = list(string.Formatter().parse(fmt))
    except ValueError:
        return None, "the .format() string is malformed"
    pieces: list[Piece] = []
    next_auto, used, mode = 0, set(), None
    for literal, name, spec, conversion in fields:
        pieces.append(Piece(text=literal))
        if name is None:
            continue
        if spec or conversion:
            return None, "a .format() field has a conversion or format spec"
        if name == "":
            kind, index = "auto", next_auto
            next_auto += 1
        elif name.isdigit():
            kind, index = "explicit", int(name)
        else:
            return None, f"the .format() field {name!r} is not a plain position"
        if mode not in (None, kind):
            return None, "automatic and numbered .format() fields are mixed"
        mode = kind
        if index >= len(node.args):
            return None, "more .format() fields than arguments"
        if index in used:
            return None, "a .format() argument is used twice"
        used.add(index)
        pieces.append(Piece(value=node.args[index]))
    if used != set(range(len(node.args))):
        return None, "a .format() argument is not used"
    return _merge(pieces), ""


# ---------------------------------------------------------------------------- output text


def value_text(src: SourceText, piece: Piece) -> str:
    """Source text of an interpolated value.

    Before Python 3.12 the positions of nodes inside an f-string are unreliable, so those are
    rendered with `ast.unparse` (only the value expression, never the surrounding code).
    """
    assert piece.value is not None
    if piece.in_fstring and sys.version_info < (3, 12):
        return ast.unparse(piece.value)
    return src.text(piece.value)


def py_literal(text: str) -> str | None:
    """A Python string literal that evaluates to `text`; None if it cannot be proven to."""
    plain = all(c in "\n\t" or (c >= " " and c != "\x7f") for c in text)
    if "\n" in text and plain:
        body = text.replace("\\", "\\\\").replace('"', '\\"')
        literal = '"""' + body + '"""'
    else:
        literal = json.dumps(text, ensure_ascii=False)
    try:
        return literal if ast.literal_eval(literal) == text else None
    except (SyntaxError, ValueError):
        return None
