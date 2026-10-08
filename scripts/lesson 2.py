import torch

x = torch.tensor(
    [
        [1, 0, 0, 0],
        [0, 0, 0, 1],
        [0, 0, 1, 0],
        [0, 0, 0, 1],
    ],
    dtype=torch.float,
)
edge_index = torch.tensor([[0, 1, 1], [1, 2, 3]])


def one_round(x, edge_index):
    new_x = x.clone()  # start from each node's own vector
    num_edges = edge_index.shape[1]
    for e in range(num_edges):
        src = edge_index[0, e]  # where the edge starts
        dst = edge_index[1, e]  # where it ends
        new_x[dst] += x[src]  # the target adds the source's OLD vector
    return new_x


h1 = one_round(x, edge_index)
print("after round 1:\n", h1)
h2 = one_round(h1, edge_index)
print("after round 2:\n", h2)
h3 = one_round(h2, edge_index)
print("after round 3:\n", h3)

undirected_edge_index = torch.tensor([[0, 1, 1, 1, 2, 3], [1, 2, 3, 0, 1, 1]])

h1 = one_round(x, undirected_edge_index)
print("after round 1:\n", h1)
