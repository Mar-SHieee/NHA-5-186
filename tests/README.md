# `tests/`

The test tree mirrors the source tree: for `shield_core/<area>/`, look in `tests/<area>/`.

| Folder | Coverage |
| --- | --- |
| `interface/` | Interface contract, CLI JSON output, and result shape. |
| `languages/` | Language registry and configuration. |
| `models/` | Model registry/fallback, V1 result mapping, and installer checksum/path validation. |
| `embeddings/` | CodeBERT and long-function windowing. |
| `datasets/` | Schema, loaders, dedupe, normalization, and group-safe splits. |
| `extraction/` | Graph cache, plus the tree-sitter helpers: function extraction, code metrics, and the V2 feature table. |
| `taint/`, `fix/`, `verify/`, `eval/` | Taint queries, fixes, verification, and metrics. |
| `fixtures/` | Shared Joern and taint examples. |
| `graph_dataset/` | Torch-free filter golden counts and optional PyG tensor/builder tests. |
| `spikes/` | Joern graph-quality triage, extraction benchmarking, fidelity checks, and spike analysis. |

Run all tests with `pytest`, or one area with `pytest tests/models`.
