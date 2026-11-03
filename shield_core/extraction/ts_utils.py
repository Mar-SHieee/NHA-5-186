"""tree-sitter helpers (W2-P5-02): read code into a syntax tree and measure it.

Three jobs, each built on the one before:
  extract_functions   split a source file into its functions
  compute_metrics     measure one function (lines, branches, loops, cyclomatic, nesting)
  build_feature_table measure every row of a dataset (the V2 features)

Everything language-specific comes from the language registry (shield_core/languages/*.yaml):
the grammar module and the node-type names (`ts_nodes`). This file only reads the tree and
counts, so every language produces the same fields and no language name is hardcoded here.
"""

from __future__ import annotations

import importlib
import textwrap
from dataclasses import asdict, dataclass, fields
from functools import lru_cache

import pandas as pd
from tree_sitter import Language, Parser

from shield_core.languages import registry


@lru_cache(maxsize=None)
def _parser_for_module(module_name: str) -> Parser:
    """Build a parser once per grammar module and reuse it."""
    module = importlib.import_module(module_name)
    return Parser(Language(module.language()))


def get_parser(language: str, extension: str | None = None) -> Parser:
    """Return a parser for a registry language ("python", "cpp").

    For C++ the extension matters: ".c" uses the C grammar, anything else the C++ one.
    A disabled or unknown language raises the registry's own error.
    """
    spec = registry.require_enabled(language)
    return _parser_for_module(spec.tree_sitter.module_for(extension))


@dataclass(frozen=True)
class FunctionMetrics:
    """Numbers that describe one function. Fields are added step by step."""

    n_lines: int  # physical lines of code
    n_branches: int  # decision points (if / elif ...)
    n_loops: int  # loops (for / while ...)
    cyclomatic: int  # 1 + branches + loops + extra decision points (and/or, except, case, ?:)
    max_nesting: int  # deepest level of if / loop / try blocks inside each other; 0 = flat code
    has_parse_error: bool  # True when tree-sitter could not read the code cleanly


def _node_types(root) -> list[str]:
    """The type of every node in the tree, e.g. ["module", "function_definition", ...]."""
    types = []
    stack = [root]
    while stack:
        node = stack.pop()
        types.append(node.type)
        stack.extend(node.children)
    return types


def _max_nesting(root, nesting_types: frozenset[str], skip_under: frozenset[str]) -> int:
    """How many nesting blocks are open at the deepest point of the tree (0 if none).

    A nesting node whose direct parent is in `skip_under` adds no level: it continues a chain
    instead of opening a block (the `if` of an `else if`).
    """
    deepest = 0
    stack = [(root, 0)]
    while stack:
        node, depth = stack.pop()
        continues_chain = node.parent is not None and node.parent.type in skip_under
        if node.type in nesting_types and not continues_chain:
            depth += 1
        deepest = max(deepest, depth)
        stack.extend((child, depth) for child in node.children)
    return deepest


def _list_for(spec: registry.LanguageSpec, category: str) -> tuple[str, ...]:
    """A language's list for a `ts_nodes` category. A missing list is an error, not zero."""
    values = spec.ts_nodes.get(category)
    if values is None:
        raise ValueError(f"{spec.name}.yaml has no 'ts_nodes.{category}' list")
    return values


def _types_for(spec: registry.LanguageSpec, category: str) -> frozenset[str]:
    """The node types a language lists for a category, as a set for fast lookup."""
    return frozenset(_list_for(spec, category))


def compute_metrics(code: str, language: str, extension: str | None = None) -> FunctionMetrics:
    """Measure one function given as text."""
    spec = registry.require_enabled(language)
    branch_types = _types_for(spec, "branches")
    loop_types = _types_for(spec, "loops")
    decision_types = _types_for(spec, "decisions")
    nesting_types = _types_for(spec, "nesting")
    skip_nesting_under = _types_for(spec, "skip_nesting_under")

    # A method cut out of a class is indented, and Python rejects that as a syntax error.
    source = textwrap.dedent(code)
    tree = get_parser(language, extension).parse(source.encode("utf-8"))
    types = _node_types(tree.root_node)
    n_branches = sum(1 for t in types if t in branch_types)
    n_loops = sum(1 for t in types if t in loop_types)
    n_decisions = sum(1 for t in types if t in decision_types)
    return FunctionMetrics(
        n_lines=len(code.splitlines()),
        n_branches=n_branches,
        n_loops=n_loops,
        # McCabe: one straight path, plus one for every extra way the code can go.
        cyclomatic=1 + n_branches + n_loops + n_decisions,
        max_nesting=_max_nesting(tree.root_node, nesting_types, skip_nesting_under),
        has_parse_error=tree.root_node.has_error,
    )


@dataclass(frozen=True)
class FunctionInfo:
    """One function found inside a source file."""

    name: str | None  # None when the grammar gives no name (an anonymous function)
    start_line: int  # first line of the function, counting from 1
    end_line: int  # last line of the function
    source: str  # the text of the function, exactly as written in the file
    language: str  # registry language name, e.g. "python"
    has_parse_error: bool  # True when tree-sitter could not read this function cleanly


def _first_child_by_fields(node, fields: tuple[str, ...]):
    for field in fields:
        child = node.child_by_field_name(field)
        if child is not None:
            return child
    return None


def _function_name(node, name_fields: tuple[str, ...]) -> str | None:
    """Follow the language's name fields from a function node down to its name.

    Python: function_definition -> name.  C/C++: function_definition -> declarator ->
    declarator ... -> identifier (a pointer or a qualified name adds a step or two).
    """
    current = node
    while (child := _first_child_by_fields(current, name_fields)) is not None:
        current = child
    if current is node:
        return None
    return current.text.decode("utf-8", errors="replace")


def extract_functions(
    source: str, language: str, extension: str | None = None
) -> list[FunctionInfo]:
    """Split a whole source file into its functions, in the order they appear.

    Methods inside a class (or a namespace) are found too. A function defined inside another
    function stays part of the outer one and is not listed separately.
    """
    spec = registry.require_enabled(language)
    function_types = _types_for(spec, "functions")
    name_fields = _list_for(spec, "name_fields")

    data = source.encode("utf-8")
    tree = get_parser(language, extension).parse(data)
    found = []
    stack = [tree.root_node]
    while stack:
        node = stack.pop()
        if node.type in function_types:
            found.append(
                FunctionInfo(
                    name=_function_name(node, name_fields),
                    start_line=node.start_point.row + 1,
                    end_line=node.end_point.row + 1,
                    source=data[node.start_byte : node.end_byte].decode("utf-8"),
                    language=spec.name,
                    has_parse_error=node.has_error,
                )
            )
            continue  # do not look inside: a nested function belongs to this one
        stack.extend(reversed(node.children))  # reversed, so the first child is visited first
    return found


# Column names of the feature table. Taken from FunctionMetrics so the two cannot drift apart.
FEATURE_NAMES: tuple[str, ...] = tuple(f.name for f in fields(FunctionMetrics))
_FEATURE_DTYPES = {name: "int32" for name in FEATURE_NAMES}
_FEATURE_DTYPES["has_parse_error"] = "bool"


def build_feature_table(
    df: pd.DataFrame, code_col: str = "code", language_col: str = "language"
) -> pd.DataFrame:
    """Measure every row of a dataset: one row of metrics per input row (the V2 features).

    The result has the same index as `df`, so `df.join(table)` lines the rows up, and the
    columns are FEATURE_NAMES. A row whose code is not text or whose language is missing is an
    error that names the row, and so is a language the registry does not enable: a silent zero
    would look like a real measurement.
    """
    rows = []
    for label, code, language in zip(df.index, df[code_col], df[language_col], strict=True):
        if not isinstance(code, str):
            raise ValueError(f"row {label!r}: '{code_col}' is not text ({code!r})")
        if not isinstance(language, str):
            raise ValueError(f"row {label!r}: '{language_col}' is not text ({language!r})")
        rows.append(asdict(compute_metrics(code, language)))
    table = pd.DataFrame(rows, index=df.index, columns=list(FEATURE_NAMES))
    return table.astype(_FEATURE_DTYPES)
