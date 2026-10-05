import random
import time

import numpy as np
import torch
import torch.nn.functional as F
from torch.nn import Linear
from torch_geometric.datasets import TUDataset
from torch_geometric.loader import DataLoader
from torch_geometric.nn import GCNConv, global_mean_pool

# ---------- 1. Reproducibility ----------
SEED = 0
random.seed(SEED)
np.random.seed(SEED)
torch.manual_seed(SEED)
dev = "cuda" if torch.cuda.is_available() else "cpu"
print("device:", dev)

# ---------- 2. Data ----------
dataset = TUDataset(root="data/TUDataset", name="MUTAG")
print("graphs:", len(dataset))
print("node features:", dataset.num_node_features)
print("classes:", dataset.num_classes)
print("first graph:", dataset[0])

dataset = dataset.shuffle()
train_set, test_set = dataset[:150], dataset[150:]
train_loader = DataLoader(train_set, batch_size=32, shuffle=True)
test_loader = DataLoader(test_set, batch_size=64)

batch = next(iter(train_loader))
print("one batch:", batch)
print("batch vector:", batch.batch[:20], "...")
print("graphs in batch:", batch.num_graphs)


# ---------- 3. Model ----------
class Net(torch.nn.Module):
    def __init__(self, in_dim, hidden, num_classes):
        super().__init__()
        self.conv1 = GCNConv(in_dim, hidden)
        self.conv2 = GCNConv(hidden, hidden)
        self.lin = Linear(hidden, num_classes)

    def forward(self, x, edge_index, batch):
        x = self.conv1(x, edge_index).relu()
        x = self.conv2(x, edge_index).relu()
        x = global_mean_pool(x, batch)  # [num_nodes, hidden] -> [num_graphs, hidden]
        return self.lin(x)  # [num_graphs, num_classes]


# ---------- 4. Train / evaluate ----------
model = Net(dataset.num_node_features, 32, dataset.num_classes).to(dev)
optimizer = torch.optim.Adam(model.parameters(), lr=0.01)


def train():
    model.train()
    for data in train_loader:
        data = data.to(dev)
        optimizer.zero_grad()
        logits = model(data.x, data.edge_index, data.batch)
        loss = F.cross_entropy(logits, data.y)
        loss.backward()
        optimizer.step()


@torch.no_grad()
def test(loader):
    model.eval()
    correct = 0
    for data in loader:
        data = data.to(dev)
        logits = model(data.x, data.edge_index, data.batch)
        pred = logits.argmax(dim=1)
        correct += (pred == data.y).sum().item()
    return correct / len(loader.dataset)


start = time.time()
for epoch in range(1, 101):
    train()
    if epoch % 10 == 0:
        print(f"epoch {epoch:3d} | train {test(train_loader):.3f} | test {test(test_loader):.3f}")
print(f"training time: {time.time() - start:.1f} s")

# ---------- 5. Resource log ----------
if dev == "cuda":
    print("peak VRAM (MB):", round(torch.cuda.max_memory_allocated() / 1024**2, 1))
