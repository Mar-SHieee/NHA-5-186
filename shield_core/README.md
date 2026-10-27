# `shield_core/`

`shield_core` is SHIELD's Python library and CLI. The frozen public API is in `interface.py`.

| File / folder | What it does |
| --- | --- |
| `interface.py` | Public `predict`, `scan_repo`, and `suggest_fix` calls plus their result dataclasses. |
| `cli.py` | `shield scan <file>`; returns the frozen `Result` as JSON. |
| `tracking.py` | Seeds, dataset hashes, and MLflow/W&B/console run logging. |
| `paths.py` | Central paths for repo, data, docs, and generated artifacts. |
| `datasets/` | Dataset schema, loaders, deduplication, merge, and group-safe splits. |
| `embeddings/` | CodeBERT function and graph-node embeddings. V1 uses sliding windows and mean pooling. |
| `eval/` | Evaluation metrics. |
| `extraction/` | Joern code-property-graph extraction and disk cache. |
| `fix/`, `verify/` | Template fixes and verification checks. |
| `languages/` | Language configuration and registry. |
| `models/` | Model registry, CodeBERT + XGBoost V1 loader, and GitHub Release installer. |
| `taint/` | Taint-analysis query generation and result parsing. |

## Use the trained Python V1

After the maintainer publishes `shield-v1.zip` on GitHub Release tag `v1`, install the project,
fetch the bundle, and scan a file:

```powershell
python -m pip install -e ".[ml]"
python -m shield_core.models.install --tag v1
python -m shield_core.cli scan .\path\to\file.py
```

The installer verifies SHA-256 checksums before installing the model to `model_artifacts/v1/`.
For a private repository, set `GH_TOKEN` or `GITHUB_TOKEN` with release-read access. You can also
call `shield_core.interface.predict(code, "python")` after installing V1. CodeBERT's pretrained
weights must be cached or downloadable on first inference. C/C++ currently use the registry stub.
