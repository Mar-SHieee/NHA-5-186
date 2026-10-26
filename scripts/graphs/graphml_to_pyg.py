"""Convert a Joern GraphML export into a PyG Data object (schema 0.1-draft)."""

import sys

import networkx as nx
import torch
from torch_geometric.data import Data

# The order of this list defines the one-hot positions. Changing it means a new schema_version.
NODE_TYPES = [
    "METHOD", "METHOD_PARAMETER_IN", "METHOD_RETURN", "BLOCK", "CALL", "IDENTIFIER",
    "LITERAL", "LOCAL", "FIELD_IDENTIFIER", "RETURN", "METHOD_REF", "CONTROL_STRUCTURE",
]  # fmt: skip
EDGE_TYPES = {"AST": 0, "CFG": 1, "REACHING_DEF": 2, "CALL": 3, "ARGUMENT": 4, "CDG": 5}
NUM_FLAGS = 3  # is_source, is_sink, is_sanitizer (all 0 until the taint spike fills them)


def kept_nodes(g):
    """Return the ids of the nodes we keep (same rules as filter_counts.py)."""

    def vtype(n):
        return g.nodes[n].get("labelV")

    # Joern adds hollow METHOD nodes named <operator>.addition, <operator>.assignment, ...
    stubs = {
        n
        for n in g.nodes
        if vtype(n) == "METHOD" and str(g.nodes[n].get("NAME", "")).startswith("<operator>")
    }
    # their parameters and return nodes hang off them through AST edges
    stub_parts = {b for a, b, d in g.edges(data=True) if a in stubs and d.get("labelE") == "AST"}
    drop = stubs | stub_parts
    return {n for n in g.nodes if vtype(n) in NODE_TYPES and n not in drop}


def build(g):
    kept = kept_nodes(g)

    # 1. Row numbers. Joern ids are huge numbers, but x needs rows 0..N-1.
    #    Sorting makes the row order identical on every run (needed for the cache).
    order = sorted(kept)
    index = {node_id: row for row, node_id in enumerate(order)}

    # 2. x: one row per node = one-hot node type, then the flag columns (zeros for now).
    x = torch.zeros(len(order), len(NODE_TYPES) + NUM_FLAGS)
    for row, node_id in enumerate(order):
        x[row, NODE_TYPES.index(g.nodes[node_id]["labelV"])] = 1.0

    # 3. Edges: keep an edge only if its type is wanted and BOTH ends are kept nodes.
    srcs, dsts, types = [], [], []
    for a, b, d in g.edges(data=True):
        label = d.get("labelE")
        if label in EDGE_TYPES and a in index and b in index:
            srcs.append(index[a])
            dsts.append(index[b])
            types.append(EDGE_TYPES[label])

    edge_index = torch.tensor([srcs, dsts], dtype=torch.long)
    edge_type = torch.tensor(types, dtype=torch.long)
    return Data(x=x, edge_index=edge_index, edge_type=edge_type)


if __name__ == "__main__":
    graph = build(nx.read_graphml(sys.argv[1]))
    print(graph)
    counts = torch.bincount(graph.edge_type, minlength=len(EDGE_TYPES)).tolist()
    print("edges per type:", dict(zip(EDGE_TYPES, counts, strict=True)))
