import platform
import sys

import torch

print("python      :", sys.version.split()[0], "|", platform.platform())
print("torch       :", torch.__version__)
print("cuda (wheel):", torch.version.cuda)
print("cuda avail  :", torch.cuda.is_available())
if torch.cuda.is_available():
    p = torch.cuda.get_device_properties(0)
    print("gpu         :", p.name, f"{p.total_memory / 1024**3:.1f} GB")

try:
    import torch_geometric

    print("pyg         :", torch_geometric.__version__)
except ImportError:
    print("pyg         : NOT INSTALLED")
