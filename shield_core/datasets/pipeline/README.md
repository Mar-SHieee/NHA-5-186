# shield_core/datasets/pipeline/

Run in this order (each reads the previous step's output). Commands are in the root README, section 'Rebuild the dataset'.

| File / folder | What it is |
| --- | --- |
| `dedupe.py` | Token-normalized code hash; one row per hash across datasets; label conflicts dropped. Writes `*_deduped.parquet` + `dedupe_report.md`. |
| `project_normalization.py` | Canonical project names with learned + manual aliases; writes `docs/datasets/project_names/`. |
| `merge.py` | Merges every `*_deduped.parquet` into `merged_datasets.parquet`. |
| `splits.py` | Group-safe train/val/test/holdout (no project/commit crosses a split) + manifest JSON. |

Parent: [`shield_core/datasets/`](../README.md)
