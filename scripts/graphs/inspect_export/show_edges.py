# What do CDG, CFG, REACHING_DEF edges connect?
import sys

import networkx as nx

g = nx.read_graphml(sys.argv[1])
wanted = set(sys.argv[2:])


def label(n):
    d = g.nodes[n]
    return f"{d.get('labelV')} line {d.get('LINE_NUMBER')} [{d.get('CODE')}]"


for a, b, d in g.edges(data=True):
    if d.get("labelE") in wanted:
        print(d.get("labelE"), ":", label(a), "->", label(b))
