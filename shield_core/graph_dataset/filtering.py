"""Torch-free deterministic filtering so graph selection can run in lightweight CI."""

from __future__ import annotations

from dataclasses import dataclass

from shield_core.extraction.graph_extractor import CodeGraph, GraphNode
from shield_core.graph_dataset.schema import (
    EDGE_TYPES,
    NODE_TYPES,
    WRAPPER_METHODS,
    ConverterConfig,
)


@dataclass(frozen=True)
class GraphDiagnostics:
    n_nodes_raw: int
    n_edges_raw: int
    n_nodes: int
    n_edges: int
    edge_counts: dict[str, int]
    has_real_method: bool
    n_unknown: int
    unknown_share: float
    n_cfg: int
    n_reaching_def: int
    n_meta_class_adapter: int
    usable: bool


@dataclass(frozen=True)
class FilteredGraph:
    nodes: list[GraphNode]
    edges: list[tuple[int, int, int]]
    diagnostics: GraphDiagnostics


@dataclass(frozen=True)
class FilterResult:
    graph: FilteredGraph | None
    reason: str
    diagnostics: GraphDiagnostics


def filter_graph(graph: CodeGraph, config: ConverterConfig) -> FilterResult:
    """Apply schema rules and report raw quality even when the graph is skipped."""
    raw_nodes = graph.nodes
    raw_edges = graph.edges
    n_unknown = sum(node.type == "UNKNOWN" for node in raw_nodes)
    unknown_share = n_unknown / len(raw_nodes) if raw_nodes else 0.0
    real_method = any(
        n.type == "METHOD" and n.line is not None and n.name not in WRAPPER_METHODS
        for n in raw_nodes
    )
    n_cfg = sum(edge.type == "CFG" for edge in raw_edges)
    n_rd = sum(edge.type == "REACHING_DEF" for edge in raw_edges)
    n_adapter = sum("<metaClassAdapter>" in n.name for n in raw_nodes)
    usable = real_method and n_cfg > 0 and unknown_share <= 0.05
    stubs = {
        n.id
        for n in raw_nodes
        if n.type == "METHOD"
        and (n.name.startswith("<operator>") or (config.stub_rule == "B" and n.line is None))
    }
    parts = {e.dst for e in raw_edges if e.type == "AST" and e.src in stubs}
    kept = sorted(
        (n for n in raw_nodes if n.type in NODE_TYPES and n.id not in stubs | parts),
        key=lambda n: n.id,
    )
    by_id = {n.id: i for i, n in enumerate(kept)}
    edges = sorted(
        (by_id[e.src], by_id[e.dst], EDGE_TYPES[e.type])
        for e in raw_edges
        if e.type in config.edge_types and e.src in by_id and e.dst in by_id
    )
    counts = {name: sum(edge[2] == idx for edge in edges) for name, idx in EDGE_TYPES.items()}
    diag = GraphDiagnostics(
        len(raw_nodes),
        len(raw_edges),
        len(kept),
        len(edges),
        counts,
        real_method,
        n_unknown,
        unknown_share,
        n_cfg,
        n_rd,
        n_adapter,
        usable,
    )
    reason = "ok"
    if not kept:
        reason = "empty_after_filter"
    elif config.max_nodes is not None and len(kept) > config.max_nodes:
        reason = "over_node_cap"
    elif config.drop_unusable and not usable:
        reason = "unusable"
    if reason != "ok":
        return FilterResult(None, reason, diag)
    return FilterResult(FilteredGraph(kept, edges, diag), reason, diag)
