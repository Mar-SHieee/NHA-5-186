import sys

import networkx as nx

g = nx.read_graphml(sys.argv[1])
line = sys.argv[2]
ids = set()
for n, d in g.nodes(data=True):
    if str(d.get("LINE_NUMBER", "")) == line:
        ids.add(n)
        print(n, d.get("labelV"), "|", d.get("NAME"), "|", d.get("CODE"))
print()
keep = {"AST", "ARGUMENT", "REACHING_DEF", "CFG"}
for a, b, d in g.edges(data=True):
    if (a in ids or b in ids) and d.get("labelE") in keep:
        print(a, "->", b, d.get("labelE"))
