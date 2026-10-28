# scripts/training/

Run `python -m scripts.training.train_v1` after the frozen split parquet files are available.

The trainer creates a window-pooled CodeBERT embedding cache independent of split membership,
then fits class-weighted XGBoost binary and hierarchical CWE heads. The CWE hierarchy predicts
an internal family first, then a specific CWE within that family; rare leaves are grouped as
`Other`, while predictions exposed by the API remain real CWE IDs or `null`. The family map is
maintained in `cwe_family_map.json`. Its `language` setting may be a single registry language or
`all` to include Python and C/C++ rows together. Every run writes models, configuration,
calibration data, and validation/test metrics under `model_artifacts/train_runs/`. Use
`--grid '{"max_depth":[3,5],"learning_rate":[0.03,0.07]}'` to compare a Cartesian parameter grid;
selection is by mean per-language precision/recall balance. By default, each language's threshold
maximizes the smaller of validation precision and recall; ties favor higher F1, then closer
precision and recall. Set `binary_target_recall` when you want a specific recall target instead.
Test metrics remain held out. Add `--publish` to copy the best
validation run to `model_artifacts/v1/` for the model registry.

After the maintainer uploads `model_artifacts/shield-v1.zip` as the `shield-v1.zip` asset on GitHub
Release tag `v1`, teammates can pull the source, install V1, and scan a file:

```powershell
python -m pip install -e ".[ml]"
python -m shield_core.models.install --tag v1
python -m shield_core.cli scan .\path\to\file.py
```

The trainer's `--publish` option copies the selected run to `model_artifacts/v1/` and creates
`model_artifacts/shield-v1.zip` with a SHA-256 manifest. The installer verifies that manifest
before installing `model_artifacts/v1/`.
For a private repository, set `GH_TOKEN` or `GITHUB_TOKEN` with release-read permission.

To reuse existing `.npy` vectors, pass a JSON config that points `embedding_files` at the
train/val/test arrays and `splits_dir` at matching parquet metadata. Metadata must contain
`language`, `label`, and `cwe` in the same row order as each array; precomputed vectors must have
same row count. Set `use_fixed_code_as_negatives` to `false` for these files. The supplied
all-language configuration at `model_artifacts/train_runs/all_languages_config.json` is a local
workspace file and is ignored by Git; update its absolute paths for another machine.

Example:

```powershell
python -m scripts.training.train_v1 --config .\model_artifacts\train_runs\all_languages_config.json --grid '{"max_depth":[3,5],"learning_rate":[0.03,0.07]}' --publish
```

In PowerShell, use the checked-in grid file to avoid quoting differences:

```powershell
python -m scripts.training.train_v1 --config .\model_artifacts\train_runs\all_languages_config.json --grid-file .\scripts\training\v1_grid.json --publish
```

The current trial grid uses the best observed setting: 1,400 trees, depth 5, and learning rate 0.05.
The local all-language config uses 100-round early stopping and selects per-language thresholds by
the smaller of validation precision and recall. The `precision_recall_balance` metric records this
smaller value in run summaries; test precision and recall show how the balance generalizes.

This fits on the complete train embedding array, uses validation rows for model selection and
calibration, and reserves test rows for final reporting. It does not refit on validation or test.

To evaluate the broad family classifier for an already trained V1 without retraining, run:

```powershell
python -m scripts.training.evaluate_v1_families --run-dir .\model_artifacts\v1
```

The evaluator uses only labeled vulnerable rows in the held-out test split and reports family
accuracy, macro-F1, per-family precision/recall/F1, a confusion matrix, and per-language metrics.
