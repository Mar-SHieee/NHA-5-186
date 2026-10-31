# `shield_core/graph_dataset/`

This package converts cached Joern `CodeGraph` objects into a stable, versioned PyTorch Geometric
dataset. It reads graphs and split manifests; it never runs Joern or trains a model.

| File | Purpose |
| --- | --- |
| `schema.py` | Frozen node/edge identifiers, converter config and `node_text_hash` helper. |
| `filtering.py` | Torch-free node/edge filtering, cap decisions and graph-quality diagnostics. |
| `to_pyg.py` | Convert one filtered graph to PyG tensors and provenance fields. |
| `builder.py` | Read split Parquet rows, look up cached graphs, write split data and reports. |
| `dataset.py` | Load an already-built split as `ShieldGraphDataset`. |
| `stats.py` | Size percentiles, candidate cap balance and Markdown report rendering. |

Importing this package does not import torch. PyG is an optional runtime dependency for tensor and
dataset operations. `torch.save` files should only be loaded from a trusted local build.

Parent: [`shield_core/`](../README.md) · Schema: [`docs/graphs/graph_schema.md`](../../docs/graphs/graph_schema.md)
