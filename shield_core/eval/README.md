# shield_core/eval/

Metrics for results tables (W2-P3-03). Later: ablation and LLM-baseline code.

| File / folder | What it is |
| --- | --- |
| `metrics.py` | `calculate_metrics` and `calculate_confusion_matrix` (weighted totals), plus per-CWE metrics (`per_cwe_metrics`), per language (`per_cwe_metrics_by_language`), a labelled confusion matrix (`cwe_confusion_matrix`) and commits per CWE (`commits_per_cwe`). A row may have several CWEs (multi-label). |

The per-CWE table is built by `scripts/training/per_cwe_table.py`.

Parent: [`shield_core/`](../README.md)
