# What are these mystery nodes (738, 744, ...)?
import sys

import networkx as nx

g = nx.read_graphml(sys.argv[1])
for n in sys.argv[2:]:
    d = g.nodes[n]
    print(
        n, d.get("labelV"), "|", d.get("NAME"), "|", d.get("CODE"), "| line", d.get("LINE_NUMBER")
    )
