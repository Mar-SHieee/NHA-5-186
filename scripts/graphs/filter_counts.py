# What survives if we drop the bookkeeping?
import collections
import sys

import networkx as nx

KEEP_NODES = {
    "METHOD", "METHOD_PARAMETER_IN", "METHOD_RETURN", "BLOCK", "CALL",
    "IDENTIFIER", "LITERAL", "LOCAL", "FIELD_IDENTIFIER", "RETURN",
    "METHOD_REF", "CONTROL_STRUCTURE",
}  # fmt: skip
KEEP_EDGES = {"AST", "CFG", "REACHING_DEF", "CALL", "ARGUMENT", "CDG"}

g = nx.read_graphml(sys.argv[1])


def vtype(n):
    return g.nodes[n].get("labelV")


# operator stubs (<operator>.addition etc.) and the parts hanging off them
stubs = {
    n
    for n in g.nodes
    if vtype(n) == "METHOD" and str(g.nodes[n].get("NAME", "")).startswith("<operator>")
}
stub_parts = {b for a, b, d in g.edges(data=True) if a in stubs and d.get("labelE") == "AST"}
drop = stubs | stub_parts

kept = {n for n in g.nodes if vtype(n) in KEEP_NODES and n not in drop}
kept_edges = [
    d.get("labelE")
    for a, b, d in g.edges(data=True)
    if d.get("labelE") in KEEP_EDGES and a in kept and b in kept
]

print("nodes:", g.number_of_nodes(), "->", len(kept))
print("edges:", g.number_of_edges(), "->", len(kept_edges))
print("kept node types:", dict(collections.Counter(vtype(n) for n in kept)))
print("kept edge types:", dict(collections.Counter(kept_edges)))
