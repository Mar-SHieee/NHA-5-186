# `scripts/`

Scripts run experiments, data preparation, and tooling. The library lives in `shield_core/`; script
modules can import the library, while the library contains the inference helpers used by V1.
Run commands from the repository root.

| Folder | What it contains |
| --- | --- |
| `data_audit/` | Dataset audits, split reports, and exploration. |
| `embeddings/` | Token-length analysis and CodeBERT bulk embedding jobs. |
| `graphs/` | Joern graph tools and GraphML-to-PyG utilities. |
| `spikes/` | Time-boxed experiments and their evidence. |
| `training/` | V1 XGBoost/CodeBERT training, parameter-grid comparison, saved metrics and artifacts. |
| `tutorials/` | Learning examples and demos. |

Train from splits and existing CodeBERT cache with `python -m scripts.training.train_v1`. To use
precomputed vectors, pass a config with aligned `.npy` files and metadata parquet paths. The script
selects parameter sets by validation MCC and saves test metrics separately. See
[`training/README.md`](training/README.md).
