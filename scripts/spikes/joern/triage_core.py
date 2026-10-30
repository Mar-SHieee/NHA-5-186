"""Pure helpers for Joern graph-quality triage.

These functions keep graph decisions independently testable from Docker, the cache, and files.
"""

from __future__ import annotations

import ast
import html
import math
import re
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from shield_core.extraction.graph_extractor import CodeGraph, GraphEdge

USABLE_UNKNOWN_SHARE = 0.05
GO_THRESHOLD = 0.85
LIMITS_THRESHOLD = 0.70
_WRAPPER_METHODS = {"<module>", "<global>"}
_ASSIGNMENT_RE = re.compile(r"(?<![<>=!])=(?!=)")
_NODE_RE = re.compile(r'^\s*"([^"]+)"\s*\[label\s*=\s*<(.+)>')
_EDGE_RE = re.compile(r'^\s*"([^"]+)"\s*->\s*"([^"]+)"')


@dataclass(frozen=True)
class DotStats:
    """Counts and labels from one DOT view or a directory aggregate."""

    nodes: dict[str, str] = field(default_factory=dict)
    edges: set[tuple[str, str]] = field(default_factory=set)
    dot_files: int = 0


@dataclass(frozen=True)
class GraphMetrics:
    """Small structural summary of the production graph for one sample."""

    n_nodes: int
    n_edges: int
    edge_counts: dict[str, int]
    n_unknown_nodes: int
    unknown_share: float
    methods: list[tuple[str, int | None]]
    n_real_methods: int
    n_lineless_methods: int
    has_reaching_def: bool


@dataclass(frozen=True)
class StubImpact:
    """Structural cost of dropping line-less METHOD nodes under Rule B."""

    dropped_nodes: int
    dropped_edges_by_type: dict[str, int]
    kept_edge_loss: int
    components_a: int
    components_b: int
    dropped_have_text: bool


def parse_dot(text: str) -> DotStats:
    """Parse node labels and edges with the same line rules used by the spike audit."""
    nodes: dict[str, str] = {}
    edges: set[tuple[str, str]] = set()
    for line in text.splitlines():
        edge_match = _EDGE_RE.match(line)
        if edge_match:
            edges.add((edge_match.group(1), edge_match.group(2)))
            continue
        node_match = _NODE_RE.match(line)
        if node_match:
            node_id, label = node_match.groups()
            nodes[node_id] = html.unescape(label)
    return DotStats(nodes=nodes, edges=edges, dot_files=1)


def label_type(label: str) -> str:
    """Return the node/operator/call token before the DOT label's first comma."""
    decoded = html.unescape(label).strip()
    return decoded.split(",", maxsplit=1)[0].strip()


def audit_flags(
    cfg_stats: DotStats,
    ddg_stats: DotStats,
    *,
    cpg_ok: bool,
    source_ok: bool,
) -> list[str]:
    """Replicate the original audit flags so the triage starts from the same evidence."""
    flags: list[str] = []
    cfg_nodes = cfg_stats.nodes
    cfg_edges = cfg_stats.edges
    ddg_nodes = ddg_stats.nodes
    ddg_edges = ddg_stats.edges

    if not source_ok:
        flags.append("MISSING_SOURCE")
    if not cpg_ok:
        flags.append("MISSING_OR_EMPTY_CPG")
    if cfg_stats.dot_files == 0:
        flags.append("NO_CFG_DOT_FILES")
    elif not cfg_nodes:
        flags.append("CFG_HAS_NO_NODES")
    if cfg_nodes and not cfg_edges:
        flags.append("CFG_HAS_NO_EDGES")
    if cfg_nodes and not any(re.search(r"\bMETHOD\b", label) for label in cfg_nodes.values()):
        flags.append("CFG_NO_METHOD_NODE")
    if any("UNKNOWN" in label.upper() for label in cfg_nodes.values()):
        flags.append("CFG_UNKNOWN_NODES")
    if ddg_stats.dot_files == 0:
        flags.append("NO_DDG_DOT_FILES")
    elif not ddg_nodes:
        flags.append("DDG_HAS_NO_NODES")
    if ddg_nodes and not ddg_edges:
        flags.append("DDG_HAS_NO_EDGES")
    return flags


def real_unknown_count(labels: Iterable[str]) -> int:
    """Count labels whose node type is UNKNOWN, excluding source text mentions."""
    return sum(label_type(label).upper() == "UNKNOWN" for label in labels)


def substring_unknown_count(labels: Iterable[str]) -> int:
    """Replicate the audit's broader substring search for comparison with node types."""
    return sum("UNKNOWN" in html.unescape(label).upper() for label in labels)


def graph_metrics(graph: CodeGraph) -> GraphMetrics:
    """Summarize graph structure used by the frozen acceptance criteria."""
    edge_counts = dict(Counter(edge.type for edge in graph.edges))
    methods = [(node.name, node.line) for node in graph.nodes if node.type == "METHOD"]
    method_nodes = [node for node in graph.nodes if node.type == "METHOD"]
    real_methods = [
        node for node in method_nodes if node.line is not None and node.name not in _WRAPPER_METHODS
    ]
    unknowns = sum(node.type == "UNKNOWN" for node in graph.nodes)
    return GraphMetrics(
        n_nodes=len(graph.nodes),
        n_edges=len(graph.edges),
        edge_counts=edge_counts,
        n_unknown_nodes=unknowns,
        unknown_share=unknowns / len(graph.nodes) if graph.nodes else 0.0,
        methods=methods,
        n_real_methods=len(real_methods),
        n_lineless_methods=sum(node.line is None for node in method_nodes),
        has_reaching_def=edge_counts.get("REACHING_DEF", 0) > 0,
    )


def _walk_without_nested_scope(node: ast.AST) -> Iterable[ast.AST]:
    """Walk one statement without counting a nested function's local reads/writes."""
    stack = [node]
    while stack:
        current = stack.pop()
        yield current
        for child in reversed(list(ast.iter_child_nodes(current))):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
                continue
            stack.append(child)


def _python_function_flow(function: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    args = function.args
    parameters = [*args.posonlyargs, *args.args, *args.kwonlyargs]
    if args.vararg:
        parameters.append(args.vararg)
    if args.kwarg:
        parameters.append(args.kwarg)
    tracked = {arg.arg for arg in parameters}
    uses = 0
    for statement in function.body:
        walked = list(_walk_without_nested_scope(statement))
        uses += sum(
            isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load) and node.id in tracked
            for node in walked
        )
        tracked.update(
            node.id
            for node in walked
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store)
        )
    return uses


def _regex_flow_expectation(code: str) -> int:
    """Approximate C/C++ flow using assignments and references to function parameters."""
    count = len(_ASSIGNMENT_RE.findall(code))
    signature = re.search(r"\b[A-Za-z_]\w*\s*\(([^()]*)\)", code, flags=re.DOTALL)
    if signature is None:
        return count
    body = code[signature.end() :]
    for chunk in signature.group(1).split(","):
        names = re.findall(r"[A-Za-z_]\w*", chunk)
        if names and names[-1] not in {"void", "const", "volatile"}:
            count += len(re.findall(rf"\b{re.escape(names[-1])}\b", body))
    return count


def flow_expectation(language: str, code: str) -> tuple[int, str]:
    """Estimate whether a source has flow to check; C/C++ use a marked regex fallback."""
    if language.lower() in {"python", "py"}:
        try:
            tree = ast.parse(code)
        except (SyntaxError, ValueError, TypeError):
            return _regex_flow_expectation(code), "regex_fallback"
        functions = [
            node
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        return sum(_python_function_flow(function) for function in functions), "ast"
    return _regex_flow_expectation(code), "regex"


def _count(row: Mapping[str, object], *keys: str, default: int = 0) -> int:
    for key in keys:
        if key in row and row[key] is not None:
            value = row[key]
            if isinstance(value, (list, tuple, set, dict)):
                return len(value)
            return int(value)
    return default


def is_usable(row: Mapping[str, object]) -> bool:
    """Apply U1–U4; expected-flow zero skips only the U3 reaching-def check."""
    methods = _count(row, "real_methods", "n_real_methods")
    cfg_edges = _count(row, "cfg_edges")
    expected = _count(row, "expected_flow")
    reaching_def = _count(row, "reaching_def")
    unknown_share = float(row.get("unknown_share", 0.0) or 0.0)
    return (
        methods > 0
        and cfg_edges > 0
        and (expected == 0 or reaching_def > 0)
        and unknown_share <= USABLE_UNKNOWN_SHARE
    )


def _flagged(row: Mapping[str, object]) -> bool:
    return bool(row.get("flagged")) or bool(str(row.get("review_flags", "")).strip())


def classify(row: Mapping[str, object]) -> tuple[str, str]:
    """Choose the first explainable cause, with parse failures ahead of quality symptoms."""
    if row.get("extraction_failed") or row.get("extraction_error"):
        return "EXTRACTION_FAILURE", "Production extraction failed for this sample."

    methods = _count(row, "real_methods", "n_real_methods", default=1)
    if row.get("input_fragment") or row.get("unbalanced_braces") or methods == 0:
        return "INPUT_FRAGMENT", "No line-numbered real METHOD was recovered from the input."

    expected = _count(row, "expected_flow")
    reaching_def = _count(row, "reaching_def")
    unknown_share = float(row.get("unknown_share", 0.0) or 0.0)
    if expected > 0 and reaching_def == 0:
        return (
            "PARSER_GAP",
            "The source appears to have flow, but the graph has no REACHING_DEF edge.",
        )
    if unknown_share > USABLE_UNKNOWN_SHARE:
        return "PARSER_GAP", "UNKNOWN nodes exceed the frozen 5% graph-share limit."

    if (
        row.get("spike_view_available", True)
        and _count(row, "ddg_dot_edges") == 0
        and reaching_def > 0
    ):
        return (
            "DOT_VIEW_ONLY",
            "The spike DDG view is edgeless, but the production graph has flow edges.",
        )
    if expected == 0:
        return "EXPECTED_NO_FLOW", "The static flow estimate found no tracked value use."
    if _flagged(row) and is_usable(row):
        return (
            "AUDIT_ARTIFACT",
            "The audit flagged this sample, but its production graph passes U1–U4.",
        )
    return "OTHER", "No automatic cause matched; human review is required."


def wilson_interval(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Return a Wilson score interval, which is more useful than a normal interval at small n."""
    if n <= 0 or k < 0 or k > n or z <= 0:
        raise ValueError("require n > 0, 0 <= k <= n, and z > 0")
    p = k / n
    denominator = 1 + z**2 / n
    centre = (p + z**2 / (2 * n)) / denominator
    half = z * math.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / denominator
    return max(0.0, centre - half), min(1.0, centre + half)


def language_verdict(k: int, n: int) -> str:
    """Apply the frozen GO, GO-WITH-LIMITS, and NO-GO usable-rate thresholds."""
    if n <= 0 or k < 0 or k > n:
        raise ValueError("require n > 0 and 0 <= k <= n")
    rate = k / n
    if rate >= GO_THRESHOLD:
        return "GO"
    if rate >= LIMITS_THRESHOLD:
        return "GO-WITH-LIMITS"
    return "NO-GO"


def _component_count(node_ids: set[int], edges: Iterable[GraphEdge]) -> int:
    parents = {node_id: node_id for node_id in node_ids}

    def find(node_id: int) -> int:
        while parents[node_id] != node_id:
            parents[node_id] = parents[parents[node_id]]
            node_id = parents[node_id]
        return node_id

    for edge in edges:
        if edge.src in parents and edge.dst in parents:
            left, right = find(edge.src), find(edge.dst)
            if left != right:
                parents[right] = left
    return len({find(node_id) for node_id in node_ids})


def stub_rule_impact(graph: CodeGraph) -> StubImpact:
    """Compare Rule A (keep all nodes) with Rule B (drop line-less METHOD nodes)."""
    node_ids_a = {node.id for node in graph.nodes}
    dropped = {node.id for node in graph.nodes if node.type == "METHOD" and node.line is None}
    node_ids_b = node_ids_a - dropped
    dropped_edges = [
        edge for edge in graph.edges if edge.src not in node_ids_b or edge.dst not in node_ids_b
    ]
    dropped_counts = dict(Counter(edge.type for edge in dropped_edges))
    kept_edge_loss = sum(edge.type in {"REACHING_DEF", "CFG"} for edge in dropped_edges)
    dropped_methods = [node for node in graph.nodes if node.id in dropped]
    return StubImpact(
        dropped_nodes=len(dropped),
        dropped_edges_by_type=dropped_counts,
        kept_edge_loss=kept_edge_loss,
        components_a=_component_count(node_ids_a, graph.edges),
        components_b=_component_count(node_ids_b, graph.edges),
        dropped_have_text=any(
            node.code.strip().lower() not in {"", "<empty>"} for node in dropped_methods
        ),
    )


def _extract_block(text: str, begin: str, end: str) -> str | None:
    start = text.find(begin)
    finish = text.find(end, start + len(begin)) if start >= 0 else -1
    if start < 0 or finish < 0:
        return None
    return text[start : finish + len(end)]


def preserve_block(old_text: str, new_text: str, begin: str, end: str) -> str:
    """Carry a user-maintained marker block forward when the audit regenerates its report."""
    if _extract_block(new_text, begin, end) is not None:
        return new_text
    old_block = _extract_block(old_text, begin, end)
    if old_block is None:
        return new_text
    separator = "" if not new_text or new_text.endswith("\n") else "\n"
    return f"{new_text}{separator}\n{old_block}\n"
