# scripts/

Scripts are *runs*, the library is `shield_core/`. A script may import `shield_core`; `shield_core` never imports a script. Run scripts from the repo root, e.g. `python scripts/data_audit/acceptance_check.py` or `python -m scripts.embeddings.long_embedding`.

| File / folder | What it is |
| --- | --- |
| `data_audit/` | Dataset audits and exploration reports (write into `docs/datasets/`). |
| `embeddings/` | Token-length analysis and bulk CodeBERT embedding jobs. |
| `graphs/` | Joern graph tooling: GraphML -> PyG, extractor try-out, export inspectors. |
| `spikes/` | Time-boxed experiments that produced go/no-go evidence. |
| `training/` | Model training entry points. |
| `tutorials/` | Learning material and demos (not part of the product). |
