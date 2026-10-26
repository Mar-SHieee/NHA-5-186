import torch

torch.manual_seed(0)

# Graph A: the 4-node graph from Lesson 2
x_a = torch.tensor(
    [[1, 0, 0, 0], [0, 0, 0, 1], [0, 0, 1, 0], [0, 0, 0, 1]],
    dtype=torch.float,
)
ei_a = torch.tensor([[0, 1, 1], [1, 2, 3]])


def layer(x, edge_index, w):
    # Lesson 2's rule: own vector + sum of incoming vectors
    agg = torch.zeros_like(x)
    agg.index_add_(0, edge_index[1], x[edge_index[0]])
    # Lesson 3's idea: a weight matrix, then ReLU (negatives become 0)
    return torch.relu((x + agg) @ w)


# Weights: random for now. Training (Lesson 3) would adjust them.
w1 = torch.randn(4, 8)  # layer 1: 4 features -> 8
w2 = torch.randn(8, 8)  # layer 2: 8 -> 8
w_out = torch.randn(8, 2)  # final: 8 -> 2 class scores

h1 = layer(x_a, ei_a, w1)
h2 = layer(h1, ei_a, w2)
print("node vectors after 2 layers:", tuple(h2.shape))  # (4, 8)

graph_vec = h2.max(dim=0).values  # pooling: average over the nodes
print("pooled graph vector:", tuple(graph_vec.shape))  # (8,)

scores = graph_vec @ w_out
print("class scores:", scores)  # 2 numbers

# --- Two graphs at once (this is what PyG's batching does) ---
x_b = torch.tensor([[1, 0, 0, 0], [0, 0, 0, 1], [0, 0, 1, 0]], dtype=torch.float)
ei_b = torch.tensor([[0, 1], [1, 2]])

x_all = torch.cat([x_a, x_b])  # 7 nodes total
ei_all = torch.cat([ei_a, ei_b + 4], dim=1)  # graph B's indices shifted by 4
batch = torch.tensor([0, 0, 0, 0, 1, 1, 1])  # which graph each node is in

h = layer(layer(x_all, ei_all, w1), ei_all, w2)
pooled = torch.stack([h[batch == i].mean(dim=0) for i in range(2)])
print("pooled, one row per graph:", tuple(pooled.shape))  # (2, 8)
print("scores, one row per graph:", tuple((pooled @ w_out).shape))  # (2, 2)
