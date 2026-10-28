# Joern Spike Audit Report

## Scope

Audit of the existing Joern spike artifacts for up to 60 samples.
This script does not rerun Joern or modify the original results.

DOT node and edge counts are summed per file. Node IDs may repeat
between files, so these totals are not guaranteed to be globally unique.
A METHOD node alone does not prove that a useful method-level graph exists.
DDG node/edge presence does not prove semantic data-dependence correctness.
CALL resolution and source-to-graph semantic correctness were not verified.

## Results by language

### c

- Samples audited: 20
- Nonempty CPGs: 20
- Samples with CFG nodes: 20
- Samples with CFG edges: 20
- Samples with a METHOD node: 20
- Samples with DDG nodes: 13
- Samples with DDG edges: 13
- Samples flagged for review: 8

### cpp

- Samples audited: 20
- Nonempty CPGs: 20
- Samples with CFG nodes: 20
- Samples with CFG edges: 20
- Samples with a METHOD node: 20
- Samples with DDG nodes: 17
- Samples with DDG edges: 17
- Samples flagged for review: 5

### python

- Samples audited: 20
- Nonempty CPGs: 20
- Samples with CFG nodes: 20
- Samples with CFG edges: 20
- Samples with a METHOD node: 20
- Samples with DDG nodes: 17
- Samples with DDG edges: 17
- Samples flagged for review: 17

## Interpretation and limitations

- Export success is not equivalent to graph usability.
- Empty DDGs are flagged for review; whether this is expected depends on the source.
- UNKNOWN nodes and missing method nodes are diagnostic indicators, not automatic proof of failure.
- Condition-node counts are simple label-based indicators, not semantic validation.
- CALL resolution was not measured.
- GO/NO-GO decisions require agreed acceptance thresholds and representative manual validation.

## Artifacts

- Audit CSV: `data/interim/joern_spike_audit.csv`
- Original results CSV: `data/interim/joern_spike_results.csv`

<!-- TRIAGE:BEGIN -->
## Graph-quality triage (W2-P2-04)

Raw-path verdicts under frozen U1–U4 thresholds:

- **Python: NO-GO** — 45/120 usable (95% Wilson 0.2935–0.4642).
- **C: GO** — 95/100 verified C samples usable (95% Wilson 0.8882–0.9785). The legacy BigVul C-labelled samples were metadata `cpp` and are excluded.
- **C++: GO** — 17/20 usable (95% Wilson 0.6396–0.9476).

Python is **NO-GO on the current raw production path**. The triage-only synthetic-class context experiment made 120/120 Python samples usable. Recommendation: apply the wrapper consistently to every indented Python method excerpt in production, with source-line offset correction. The experiment adds a parser line and does not change the raw-path verdict until that production path is implemented and verified. Main causes were missing input context in Python excerpts, input fragments among verified C samples, and input fragments or expected no-flow cases in C++.

First-build stub rule: **Rule A (provisional)**; revisit in the Week-3 ablation (decision D41). Full evidence: [joern_triage.md](joern_triage.md), with the reviewed evidence in [joern_triage_review.csv](joern_triage_review.csv).
<!-- TRIAGE:END -->
