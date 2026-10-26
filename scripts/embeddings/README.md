# scripts/embeddings/

Implements the long-function policy (docs/modeling/long_function_policy.md).

| File / folder | What it is |
| --- | --- |
| `token_length_stats.py` | How many functions exceed 512 tokens, per dataset. |
| `long_function_analysis.py` | `apply_truncation_policy`: sliding windows (510 tokens, overlap, optional cap). |
| `long_embedding.py` | Embeds every function in a parquet, mean-pooling windows -> `.npy` + processed parquet. |
| `coverage_check.py` | Checks embeddings cover the rows. |
| `sanity_check.py` | Sanity checks on embeddings. |

Parent: [`scripts/`](../README.md)
