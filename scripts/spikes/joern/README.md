# scripts/spikes/joern/

Result: GO for Python, C and C++ (decision D27). Report: `docs/graphs/joern_spike.md`.

| File / folder | What it is |
| --- | --- |
| `run_joern_spike.py` | Runs Joern on 20 samples each of Python, C, C++. |
| `audit_joern_spike.py` | Checks CFG/DDG/call edges of those runs -> `docs/graphs/joern_spike.md`. |
| `analyze_joern_performance.py` | Seconds-per-sample summary. |
| `benchmark_core.py` | Pure batching, marker parsing, failure classification, statistics, projections and CSV helpers. |
| `benchmark_samples.py` | Builds seeded spike-60 and scale-600 sample sets. |
| `benchmark_extraction.py` | Measures per-sample, single-container and batched Joern extraction across worker configurations. |
| `benchmark_fidelity.py` | Checks filename attribution and per-file graph fidelity for two-file batches. |
| `benchmark_report.py` | Generates benchmark results, fidelity findings and full-scale projections. |

Parent: [`scripts/spikes/`](../README.md)
