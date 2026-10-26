# shield_core/datasets/

Five sources are turned into one unified table (schema 1.2) and then into train/val/test/holdout files. Work flows through the sub-folders in this order: `cvefixes_build/` -> `loaders/` -> `pipeline/` (dedupe -> merge -> splits).

| File / folder | What it is |
| --- | --- |
| `schema.py` | The unified 10-column schema: `conform`, `validate`, parquet I/O. |
| `project_names.py` | One naming convention (`owner/repo`) from repository URLs; used by every loader. |
| `cvefixes_build/` | Build CVEfixes.db and cut it into per-language CSV tables (step 1-2 of the data chain). |
| `loaders/` | One loader per source dataset -> `data/interim/<source>.parquet` in the unified schema. |
| `pipeline/` | The processing chain: dedupe -> project normalization -> merge -> leakage-safe splits. |
| `samples/` | Small seeded random samples (20 rows) used by the Joern spikes. |

Parent: [`shield_core/`](../README.md)
