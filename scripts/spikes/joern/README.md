# scripts/spikes/joern/

Result: GO for Python, C and C++ (decision D27). Report: `docs/graphs/joern_spike.md`.

| File / folder | What it is |
| --- | --- |
| `run_joern_spike.py` | Runs Joern on 20 samples each of Python, C, C++. |
| `audit_joern_spike.py` | Checks CFG/DDG/call edges of those runs -> `docs/graphs/joern_spike.md`. |
| `analyze_joern_performance.py` | Seconds-per-sample summary. |

Parent: [`scripts/spikes/`](../README.md)
