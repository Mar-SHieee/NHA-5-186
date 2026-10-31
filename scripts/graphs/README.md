# scripts/graphs/

Graph extraction utilities and processed PyG dataset commands.

| File / folder | What it is |
| --- | --- |
| `graphml_to_pyg.py` | Joern GraphML -> PyG `Data` (12 node types one-hot + taint flags; 6 edge types). |
| `build_pyg_dataset.py` | Build versioned split datasets and size reports from cached CodeGraphs. |
| `export_to_fixture.py` | Freeze GraphML exports as deterministic CodeGraph JSON fixtures. |
| `filter_counts.py` | What survives when bookkeeping nodes are dropped. |
| `try_extractor.py` | End-to-end try-out of `CachedGraphExtractor(JoernExtractor)`; two calls prove the cache. |
| `inspect_export/` | Tiny inspectors for a Joern GraphML export. |

Parent: [`scripts/`](../README.md)
