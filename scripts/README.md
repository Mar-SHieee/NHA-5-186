# `scripts/`

Scripts run experiments, data preparation, and tooling. The library lives in `shield_core/`; script
modules can import the library, while the library contains the inference helpers used by V1.
Run commands from the repository root.

| Folder        | What it contains                                                                                                                           |
| ------------- | ------------------------------------------------------------------------------------------------------------------------------------------ |
| `data_audit/` | Dataset audits, split reports, and exploration. `split_qa.py` (leakage checks, W2-P5-04), `acceptance_check.py`, exploration notebooks.    |
| `embeddings/` | Token-length analysis and CodeBERT bulk embedding jobs.                                                                                    |
| `graphs/`     | Joern graph tools and GraphML-to-PyG utilities.                                                                                            |
| `spikes/`     | Time-boxed experiments and their evidence.                                                                                                 |
| `training/`   | V1 XGBoost/CodeBERT training, V2 code-metrics (`build_code_metrics.py`, W2-P5-02), parameter-grid comparison, saved metrics and artifacts. |
| `tutorials/`  | Learning examples and demos.                                                                                                               |

Train from splits and existing CodeBERT cache with `python -m scripts.training.train_v1`. To use
precomputed vectors, pass a config with aligned `.npy` files and metadata parquet paths. The script
selects parameter sets by validation MCC and saves test metrics separately. See
[`training/README.md`](training/README.md).

Build V2 code metrics with `python scripts/training/build_code_metrics.py` (or `--limit 2000` for trial).
Output: `data/interim/code_metrics/code_metrics.parquet` + `code_metrics.meta.json` + `docs/modeling/code_metrics_report.md`.

Run split QA with `python scripts/data_audit/split_qa.py` (reads `docs/datasets/audits/dataset_manifest_v0.json`, writes `split_qa.md`).
