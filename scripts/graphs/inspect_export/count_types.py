# Which node and edge types exist, and how many?

import collections
import sys

import networkx as nx

g = nx.read_graphml(sys.argv[1])
print("nodes:", g.number_of_nodes(), "| edges:", g.number_of_edges())

node_types = collections.Counter(
    d.get("labelV", d.get("label", "?")) for _, d in g.nodes(data=True)
)
edge_types = collections.Counter(
    d.get("labelE", d.get("label", "?")) for _, _, d in g.edges(data=True)
)
print("node types:", dict(node_types))
print("edge types:", dict(edge_types))
