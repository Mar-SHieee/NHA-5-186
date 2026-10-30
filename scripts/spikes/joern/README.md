# scripts/spikes/joern/

Initial export decision D27 was GO for all three languages. The later W2-P2-04 graph-quality triage refines that result: raw Python NO-GO, verified C GO, and C++ GO. See `docs/graphs/joern_triage.md`; the Python synthetic-class recovery remains an experiment pending source-line mapping validation.

| File / folder | What it is |
| --- | --- |
| `run_joern_spike.py` | Runs Joern on 20 samples each of Python, C, C++. |
| `audit_joern_spike.py` | Checks CFG/DDG/call edges of those runs -> `docs/graphs/joern_spike.md`. |
| `triage_core.py` | Pure graph-quality metrics, flags, causes, verdicts, stub-rule comparison, and marker-block preservation. |
| `triage_joern_spike.py` | Extracts cached graphs, analyzes the original and scale samples, and generates the W2-P2-04 report. |
| `analyze_joern_performance.py` | Seconds-per-sample summary. |
| `benchmark_core.py` | Pure batching, marker parsing, failure classification, statistics, projections and CSV helpers. |
| `benchmark_samples.py` | Builds seeded spike-60 and scale-600 sample sets. |
| `benchmark_extraction.py` | Measures per-sample, single-container and batched Joern extraction across worker configurations. |
| `benchmark_fidelity.py` | Checks filename attribution and per-file graph fidelity for two-file batches. |
| `benchmark_report.py` | Generates benchmark results, fidelity findings and full-scale projections. |

Parent: [`scripts/spikes/`](../README.md)
