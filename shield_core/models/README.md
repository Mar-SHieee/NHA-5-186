# `shield_core/models/`

The model registry selects Python V1 from `models.yaml`. The model weights are distributed as a
GitHub Release asset because the files exceed the repository's added-file size limit. The installer
fetches and verifies the asset into `model_artifacts/v1/`.

| File / folder | What it does |
| --- | --- |
| `registry.py` | Validates the model catalog, lazily loads model kinds, and applies default/fallback selection. `SHIELD_MODELS_DIR` changes the artifact root. |
| `models.yaml` | Sets `v1` as the Python default and `stub-v0` as the fallback. |
| `v1/__init__.py` | Loads the binary and CWE XGBoost models, calibrator, threshold, and CodeBERT inference settings. |
| `install.py` | Downloads `shield-v1.zip` from GitHub Releases, verifies checksums, and installs the V1 files. |

## Install V1 after pulling the repo

A maintainer publishes `model_artifacts/shield-v1.zip` as `shield-v1.zip` on GitHub Release tag
`v1`. Teammates then run:

```powershell
python -m pip install -e ".[ml]"
python -m shield_core.models.install --tag v1
python -m shield_core.cli scan .\path\to\file.py
```

For private repositories, set `GH_TOKEN` or `GITHUB_TOKEN` with release-read access. The installer
refuses to overwrite an existing V1 folder. It downloads `microsoft/codebert-base` weights on first
inference when they are not already cached.

Parent: [`shield_core/`](../README.md)
