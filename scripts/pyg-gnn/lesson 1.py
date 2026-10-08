"""
nodes=[
    "user  = input()",
    "query = "SELECT * FROM t WHERE x=" + user",
    "run(query)"
]
"""

import torch
from torch_geometric.data import Data

edges = [(0, 1), (1, 2)]

features = [[1, 0, 0, 0], [0, 0, 0, 1], [0, 0, 1, 0]]

x = torch.tensor(features, dtype=torch.float)
sources = [a for a, b in edges]
targets = [b for a, b in edges]
edge_index = torch.tensor([sources, targets])
graph = Data(x=x, edge_index=edge_index, y=torch.tensor([1]))
print(x)
print(x.shape)
print(edge_index)
print(edge_index.shape)
print(graph)
print(graph.x)
print(graph.edge_index)
