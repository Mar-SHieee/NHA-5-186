# scripts/data_audit/

Read-only inspection of the data; nothing here changes a dataset.

| File / folder | What it is |
| --- | --- |
| `acceptance_check.py` | Dataset acceptance audit (schema, empty code, duplicate hashes, language x CWE) -> `dataset_audit.md`. |
| `check_cvefixes_absent_commits.py` | Explains why some CVEfixes commits are missing from function-level data. |
| `explore_bigvul.py` | Exploration report for Big-Vul. |
| `explore_megavul.py` | Exploration report for MegaVul. |
| `explore_cvefixes_cpp.py` | Exploration report for CVEfixes C/C++. |
| `explore_cvefixes_python.py` | Exploration report for CVEfixes Python. |
| `explore_zenodo_python.py` | Exploration report for Zenodo Python. |
| `split_qa.py` | EMPTY placeholder for the split QA tool (task W2-P5-04). |

Parent: [`scripts/`](../README.md)
