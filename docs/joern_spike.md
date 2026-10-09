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

## Performance Evaluation

### Overall Results

| Metric | Result |
|---|---:|
| Samples processed | 60 |
| Sum of per-sample processing times | 350.90 seconds |
| Average processing time per sample | 5.85 seconds |
| Median processing time per sample | 5.95 seconds |
| Fastest sample | 4.23 seconds |
| Slowest sample | 6.06 seconds |
| Average per-sample peak container memory | 214.51 MiB |
| Maximum per-sample peak container memory | 243.50 MiB |

### Results by Language

| Language | Samples | Total Processing Time | Average Time per Sample | Average Peak Memory |
|---|---:|---:|---:|---:|
| C | 20 | 117.05 s | 5.85 s | 207.98 MiB |
| C++ | 20 | 119.04 s | 5.95 s | 216.76 MiB |
| Python | 20 | 114.81 s | 5.74 s | 218.78 MiB |

### Interpretation

- Per-sample processing times were similar across the three languages.
- The average recorded processing time was approximately 5.85 seconds per sample.
- The sum of per-sample processing times is not necessarily the wall-clock duration of the entire experiment.
- Memory figures represent recorded per-sample peak container memory, not total system memory consumption.
- These measurements apply to the tested 60-sample set and should not be treated as a guaranteed performance estimate for larger datasets.

### Export Success vs. Graph Content

The original results CSV records successful parsing, CFG export, DDG export, and pipeline execution for all 60 samples. However, the separate artifact audit found non-empty DDG graphs in only 47 samples.

This distinction indicates that a successful export operation does not necessarily guarantee a non-empty graph. The empty DDG outputs and UNKNOWN CFG nodes require further investigation before graph extraction can be considered fully validated.
