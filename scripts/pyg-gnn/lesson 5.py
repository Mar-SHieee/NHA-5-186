import torch
import torch.nn.functional as F
from torch.nn import Linear
from torch_geometric.data import Data
from torch_geometric.loader import DataLoader
from torch_geometric.nn import GCNConv, global_mean_pool

torch.manual_seed(0)

# Graph A: safe (input -> sanitize -> build query -> run)
a = Data(
    x=torch.tensor(
        [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 0, 1], [0, 0, 1, 0]],
        dtype=torch.float,
    ),
    edge_index=torch.tensor([[0, 1, 2], [1, 2, 3]]),
    y=torch.tensor([0]),
)

# Graph B: vulnerable (input -> build query -> run)
b = Data(
    x=torch.tensor([[1, 0, 0, 0], [0, 0, 0, 1], [0, 0, 1, 0]], dtype=torch.float),
    edge_index=torch.tensor([[0, 1], [1, 2]]),
    y=torch.tensor([1]),
)

loader = DataLoader([a, b], batch_size=2)
batch = next(iter(loader))
print(batch)  # one big graph with 7 nodes
print(batch.batch)  # tensor([0, 0, 0, 0, 1, 1, 1])


class Net(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.conv1 = GCNConv(4, 8)  # like w1: 4 -> 8
        self.conv2 = GCNConv(8, 8)  # like w2: 8 -> 8
        self.lin = Linear(8, 2)  # like w_out: 8 -> 2

    def forward(self, x, edge_index, batch):
        x = self.conv1(x, edge_index).relu()
        x = self.conv2(x, edge_index).relu()
        x = global_mean_pool(x, batch)
        return self.lin(x)


model = Net()
out = model(batch.x, batch.edge_index, batch.batch)
print("scores, one row per graph:", tuple(out.shape))  # (2, 2)

# Lesson 3's training loop, with Adam in place of "w -= lr * w.grad"
optimizer = torch.optim.Adam(model.parameters(), lr=0.01)
for step in range(100):
    optimizer.zero_grad()
    out = model(batch.x, batch.edge_index, batch.batch)
    loss = F.cross_entropy(out, batch.y)
    loss.backward()
    optimizer.step()
    if step % 20 == 0:
        print(f"step {step:3d} | loss {loss.item():.4f}")

print("predictions:", out.argmax(dim=1).tolist(), "| truth:", batch.y.tolist())
