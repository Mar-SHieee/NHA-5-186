# shield_core/

`shield_core` is the product's engine: a Python library plus a CLI. The FastAPI backend, Angular app and VS Code extension (Weeks 5-6) will only ever call `shield_core/interface.py`.

| File / folder | What it is |
| --- | --- |
| `interface.py` | FROZEN public contract: `predict`, `scan_repo`, `suggest_fix` + data classes (v1.0). |
| `cli.py` | `shield scan <file>` command-line front end. |
| `tracking.py` | Run logging (MLflow / W&B / console), seeds, dataset hashes. |
| `paths.py` | Where everything lives on disk (repo root, data/, docs/ folders). Import paths from here. |
| `datasets/` | Raw datasets -> one schema -> deduped -> merged -> leakage-safe splits. |
| `embeddings/` | CodeBERT vectors: for whole functions and for graph nodes. |
| `eval/` | Evaluation metrics. |
| `extraction/` | Source code -> code property graph (Joern behind an interface) + a disk cache. |
| `fix/` | Fix generation (template-based today; CodeT5 later). |
| `languages/` | Language plug-ins: one YAML per language + the registry that validates them. |
| `models/` | Which model answers a scan: the model registry and its config. |
| `taint/` | Taint-analysis queries generated from the language YAMLs. |
| `verify/` | 'Is this fix sane?': syntax, pattern checks, evidence line, PASS/FAIL verdict. |

- Rule: `scripts/` may import `shield_core`; `shield_core` never imports `scripts/`.
- Rule: no language name is hard-coded here; languages are plug-ins in `languages/`.
