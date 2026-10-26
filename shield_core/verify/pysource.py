"""Python source helpers shared by the fix templates and the pattern checks (W2-P4-03).

The templates understand code with the stdlib `ast` module but edit it as text: they replace
exact source ranges, so comments, formatting and every untouched line stay byte-identical.
`ast.unparse` is never used on a whole function for that reason.

Two traps handled here (docs/fixes/fix_templates_python.md, plan finding F3):
  * `col_offset` counts UTF-8 BYTES, not characters, so offsets are converted per line.
  * `suggest_fix` gets the text of one function, which is often indented (a method). Such text
    does not parse on its own, so it is parsed again inside an `if True:` wrapper.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Iterator

# ast counts a line break as \n, \r\n or \r (not \x0b, \x0c, \u2028 ...), unlike str.splitlines.
_LINE_RE = re.compile(r"[^\r\n]*(?:\r\n|\r|\n)|[^\r\n]+")
_NEWLINE_RE = re.compile(r"\r\n|\r|\n")

Edit = tuple[int, int, str]  # (start, end, replacement) in character offsets of the source


def dotted_name(node: ast.AST) -> str | None:
    """`os.path.join` for a chain of attributes ending in a name, else None."""
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return None


def parent_map(tree: ast.AST) -> dict[ast.AST, ast.AST]:
    return {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}


def statement_lists(tree: ast.AST) -> Iterator[list[ast.stmt]]:
    """Every list of statements in the tree (bodies, else branches, finally blocks)."""
    for node in ast.walk(tree):
        for field in ("body", "orelse", "finalbody"):
            value = getattr(node, field, None)
            if isinstance(value, list) and value and isinstance(value[0], ast.stmt):
                yield value


class SourceText:
    """A parsed function plus the means to turn AST positions into text offsets."""

    def __init__(self, code: str, tree: ast.Module, shift: int) -> None:
        self.code = code
        self.tree = tree
        self._shift = shift  # lines added by the wrapper (0 or 1)
        self._lines = _LINE_RE.findall(code)
        self._starts: list[int] = []
        position = 0
        for line in self._lines:
            self._starts.append(position)
            position += len(line)

    @classmethod
    def parse(cls, code: str) -> SourceText | None:
        """Parse `code`; None when it is not valid Python (a refusal, not an error)."""
        try:
            return cls(code, ast.parse(code), 0)
        except (SyntaxError, ValueError, RecursionError):
            pass
        try:
            wrapped = ast.parse("if True:\n" + code)
        except (SyntaxError, ValueError, RecursionError):
            return None
        return cls(code, ast.Module(body=wrapped.body[0].body, type_ignores=[]), 1)

    # -- positions ---------------------------------------------------------------------------

    def _index(self, lineno: int) -> int:
        return lineno - self._shift - 1

    def offset(self, lineno: int, col: int) -> int:
        i = self._index(lineno)
        line = self._lines[i]
        return self._starts[i] + len(line.encode("utf-8")[:col].decode("utf-8", errors="replace"))

    def span(self, node: ast.AST) -> tuple[int, int]:
        return (
            self.offset(node.lineno, node.col_offset),  # type: ignore[attr-defined]
            self.offset(node.end_lineno, node.end_col_offset),  # type: ignore[attr-defined]
        )

    def text(self, node: ast.AST) -> str:
        start, end = self.span(node)
        return self.code[start:end]

    def line_start(self, node: ast.AST) -> int:
        """Offset of the start of the line the node begins on."""
        return self._starts[self._index(node.lineno)]  # type: ignore[attr-defined]

    def before_on_line(self, node: ast.AST) -> str:
        """Text between the start of the node's first line and the node."""
        return self.code[self.line_start(node) : self.span(node)[0]]

    def after_on_line(self, node: ast.AST) -> str:
        """Text between the end of the node and the end of its last line (no line break)."""
        j = self._index(node.end_lineno)  # type: ignore[attr-defined]
        line_end = self._starts[j] + len(self._lines[j].rstrip("\r\n"))
        return self.code[self.span(node)[1] : line_end]

    @property
    def newline(self) -> str:
        match = _NEWLINE_RE.search(self.code)
        return match.group(0) if match else "\n"

    # -- editing -----------------------------------------------------------------------------

    def apply(self, edits: list[Edit]) -> str:
        """Apply non-overlapping edits. Insertions at the same offset as a replacement go first."""
        ordered = sorted(edits, key=lambda e: (e[0], e[1]))
        for (_, previous_end, _), (start, _, _) in zip(ordered, ordered[1:], strict=False):
            if start < previous_end:
                raise ValueError("overlapping edits")
        text = self.code
        for start, end, replacement in reversed(ordered):
            text = text[:start] + replacement + text[end:]
        return text
