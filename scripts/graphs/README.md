# scripts/graphs/

Prototype graph tooling. `graphml_to_pyg.py` is meant to move into `shield_core/` (task W2-P2-01).

| File / folder | What it is |
| --- | --- |
| `graphml_to_pyg.py` | Joern GraphML -> PyG `Data` (12 node types one-hot + taint flags; 6 edge types). |
| `filter_counts.py` | What survives when bookkeeping nodes are dropped. |
| `try_extractor.py` | End-to-end try-out of `CachedGraphExtractor(JoernExtractor)`; two calls prove the cache. |
| `inspect_export/` | Tiny inspectors for a Joern GraphML export. |

Parent: [`scripts/`](../README.md)
