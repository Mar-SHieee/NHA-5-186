# shield_core/datasets/cvefixes_build/

One-time preparation of the 12.7 GB CVEfixes release. Output feeds `loaders/`.

| File / folder | What it is |
| --- | --- |
| `cvefixes_convert_db.py` | Downloads the CVEfixes zip, extracts the dump, builds `data/raw/CVEfixes.db`. |
| `cvefixes_cpp_tables_extraction.py` | C/C++ tables -> `data/raw/cvefixes_cpp/*.csv`. |
| `cvefixes_python_tables_extraction.py` | Python tables -> `data/raw/cvefixes_python/*.csv`. |

Parent: [`shield_core/datasets/`](../README.md)
