# scripts/training/

Run `python -m scripts.training.train_v1` after the frozen split parquet files are available.

The trainer creates a window-pooled CodeBERT embedding cache independent of split membership,
then fits class-weighted XGBoost binary and CWE heads. Every run writes models, configuration,
calibration data, and validation/test metrics under `model_artifacts/train_runs/`. Use
`--grid '{"max_depth":[3,5],"learning_rate":[0.03,0.07]}'` to compare a Cartesian parameter grid;
selection is by validation MCC and test metrics remain held out. Add `--publish` to copy the best
validation run to `model_artifacts/v1/` for the model registry.

After the maintainer uploads `model_artifacts/shield-v1.zip` as the `shield-v1.zip` asset on GitHub
Release tag `v1`, teammates can pull the source, install V1, and scan a file:

```powershell
python -m pip install -e ".[ml]"
python -m shield_core.models.install --tag v1
python -m shield_core.cli scan .\path\to\file.py
```

The installer verifies the bundle's SHA-256 manifest before installing `model_artifacts/v1/`.
For a private repository, set `GH_TOKEN` or `GITHUB_TOKEN` with release-read permission.

To reuse existing `.npy` vectors, pass a JSON config that points `embedding_files` at the
train/val/test arrays and `splits_dir` at matching parquet metadata. Metadata must contain
`language`, `label`, and `cwe` in the same row order as each array; precomputed vectors must have
same row count. Set `use_fixed_code_as_negatives` to `false` for these files.

Example:

```powershell
python -m scripts.training.train_v1 --grid '{"max_depth":[3,5],"learning_rate":[0.03,0.07]}' --publish
```
