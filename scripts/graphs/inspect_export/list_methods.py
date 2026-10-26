# Why 6 METHOD nodes for one function?
import sys

import networkx as nx

g = nx.read_graphml(sys.argv[1])
for n, d in g.nodes(data=True):
    if d.get("labelV") == "METHOD":
        print(n, d.get("NAME"), "|", d.get("FULL_NAME"), "| line", d.get("LINE_NUMBER"))
