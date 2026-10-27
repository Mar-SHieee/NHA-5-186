# shield_core/datasets/loaders/

Each loader reads a raw source, builds `project` with `project_names`, and passes the table through `schema.conform` + `schema.validate`.

| File / folder | What it is |
| --- | --- |
| `megavul_loader.py` | MegaVul JSON (streamed) -> `megavul.parquet`. |
| `bigvul_loader.py` | Big-Vul CSVs (Kaggle) -> `bigvul.parquet`. |
| `cvefixes_cpp_loaders.py` | CVEfixes C/C++ tables -> `cvefixes_cpp.parquet`. |
| `cvefixes_python_loaders.py` | CVEfixes Python tables -> `cvefixes_python.parquet`. |
| `zenodo_python_loader.py` | Zenodo 13870382 `data_Python.csv` -> `zenodo_python.parquet` (positives only). |

- Adding a dataset: see README section 'Add a dataset'. Also add it to `PRIORITY_ORDER` in `pipeline/dedupe.py`.

Parent: [`shield_core/datasets/`](../README.md)
