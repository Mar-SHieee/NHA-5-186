"""Turn filtered CodeGraph rows into tensors consumed by PyG."""

from __future__ import annotations

import torch
from torch_geometric.data import Data

from shield_core.graph_dataset.filtering import FilteredGraph
from shield_core.graph_dataset.schema import NODE_TYPES, NUM_NODE_FEATURES, text_hash64


def to_data(
    graph: FilteredGraph,
    *,
    y: int | None = None,
    cwe_multihot=None,
    code_sha: str | None = None,
    row: int | None = None,
) -> Data:
    """Create stable node/edge tensors and provenance fields for one function."""
    node_type = torch.tensor([NODE_TYPES.index(n.type) for n in graph.nodes], dtype=torch.long)
    x = torch.zeros((len(graph.nodes), NUM_NODE_FEATURES), dtype=torch.float)
    if graph.nodes:
        x[torch.arange(len(graph.nodes)), node_type] = 1.0
    edge_index = torch.tensor(
        [
            [e[0] for e in graph.edges],
            [e[1] for e in graph.edges],
        ],
        dtype=torch.long,
    ).reshape(2, -1)
    edge_type = torch.tensor([e[2] for e in graph.edges], dtype=torch.long)
    values = dict(
        x=x,
        edge_index=edge_index,
        edge_type=edge_type,
        node_type=node_type,
        node_text_hash=torch.tensor([text_hash64(n.code) for n in graph.nodes], dtype=torch.long),
        line=torch.tensor(
            [n.line if n.line is not None else -1 for n in graph.nodes], dtype=torch.long
        ),
        joern_id=torch.tensor([n.id for n in graph.nodes], dtype=torch.long),
    )
    if y is not None:
        values["y"] = torch.tensor([y], dtype=torch.long)
    if cwe_multihot is not None:
        values["cwe_multihot"] = torch.as_tensor(cwe_multihot, dtype=torch.float).reshape(1, -1)
    if code_sha is not None:
        values["code_sha"] = code_sha
    if row is not None:
        values["row"] = row
    return Data(**values)
