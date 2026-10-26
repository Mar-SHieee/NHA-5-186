# tests/

The test tree **mirrors the source tree**: to test `shield_core/<x>/`, look in `tests/<x>/`.

| Folder | Tests code in | Files |
| --- | --- | --- |
| `interface/` | `shield_core/interface.py`, `cli.py` | `test_interface.py`, `test_contract.py`, `test_cli.py` |
| `languages/` | `shield_core/languages/` | `test_registry.py` (includes "no language literals outside the registry") |
| `models/` | `shield_core/models/` | `test_model_registry.py` |
| `embeddings/` | `shield_core/embeddings/`, `scripts/embeddings/` | `test_embedder.py`, `test_node_embeddings.py`, `test_long_embedding.py` (need torch) |
| `datasets/` | `shield_core/datasets/` | schema, loaders (5), `test_dedupe_overlap.py`, `test_project_normalizer.py`, `test_splits.py` |
| `extraction/` | `shield_core/extraction/` | `test_graph_cache.py` |
| `taint/` | `shield_core/taint/`, `scripts/spikes/taint/` | `test_taint_queries.py` |
| `fix/` | `shield_core/fix/templates/` | `test_fix_template_sql.py`, `_command.py`, `_path.py` |
| `verify/` | `shield_core/verify/` | `test_pattern_checks.py`, `test_evidence.py` |
| `eval/` | `shield_core/eval/` | `test_metrics.py` |
| *(root)* | cross-cutting | `test_layout.py` (folder layout + import + README path guard), `test_tracking.py`, `test_smoke.py` |
| `fixtures/` | shared test inputs | `joern/` (Python + C++ files to study Joern output), `taint/{python,c}/` (taint fixtures, each with an `EXPECT:` line) |

```bash
pytest                      # everything
pytest tests/datasets       # one area
```

Paths to docs or fixtures in tests come from `shield_core.paths`, never from `__file__` arithmetic.
