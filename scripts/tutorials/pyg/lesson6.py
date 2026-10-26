import torch
from torch_geometric.data import Data

CFG, DFG = 0, 1  # edge type ids

# features: [is_method, is_assign, is_call, is_return, is_source, is_sink,is_sanitizer]
x = torch.tensor(
    [
        [1, 0, 0, 0, 0, 0, 0],  # 0 def get_user
        [0, 1, 0, 0, 1, 0, 0],  # 1 name = request.args[...]   (source)
        [0, 1, 0, 0, 0, 0, 1],  # 2 name = escape(name)
        [0, 1, 0, 0, 0, 0, 0],  # 3 q = "..." + name
        [0, 1, 0, 0, 0, 0, 0],  # 4 cur = db.cursor()
        [0, 0, 1, 0, 0, 1, 0],  # 5 cur.execute(q)            (sink)
        [0, 0, 0, 1, 0, 0, 0],  # 6 return cur.fetchall()
    ],
    dtype=torch.float,
)

# (from, to, type)
edges = [
    (0, 1, CFG), (1, 2, CFG), (2, 3, CFG), (3, 4, CFG), (4, 5, CFG),(5, 6, CFG),
    (1, 2, DFG),(2,3,DFG), (3, 5, DFG), (4, 5, DFG), (5, 6, DFG),
]  # fmt: skip

edge_index = torch.tensor([[a for a, b, t in edges], [b for a, b, t in edges]])
edge_type = torch.tensor([t for a, b, t in edges])

graph = Data(x=x, edge_index=edge_index, edge_type=edge_type, y=torch.tensor([1]))
print(graph)
print(graph.edge_index)
print(graph.edge_type)
