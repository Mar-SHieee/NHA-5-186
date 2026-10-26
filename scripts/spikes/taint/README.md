# scripts/spikes/taint/

Compares results with each fixture's `EXPECT:` line. Evidence: `docs/taint/taint_spike.md`.

| File / folder | What it is |
| --- | --- |
| `run_taint_spike.py` | Verdicts `OK / KNOWN-MISS / KNOWN-FP / NOW-OK / UNEXPECTED`; exit 1 on `UNEXPECTED`. |

Parent: [`scripts/spikes/`](../README.md)
