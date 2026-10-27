# Joern extraction report

<!-- P1 sections may be added below. -->

<!-- BENCHMARK:BEGIN -->
## 1. Extraction benchmark (W2-P2-05)

### 1.1 Environment

- **timestamp_utc:** 2026-10-26T23:56:33Z
- **os:** Windows-11-10.0.26200-SP0
- **python:** 3.12.0
- **cpu_count:** 24
- **ram_bytes:** 16907100160
- **docker_cpus:** 24
- **docker_mem_bytes:** 8188325888
- **image:** shield-joern
- **image_id:** sha256:51394b312f9ae88868f5058a3e1f90ae630bb3c6521a750d85f2552992282fba
- **joern_version:** 4.0.647
- **repo_inside_onedrive:** True
- **notes:** Legion Performance Mode confirmed; plugged-in and background-app status not independently verified; E2_QUIET is retained from pre-performance calibration, while current E2/E3/E4 runs use Performance Mode
- **scenario_counts:** parquet counts; S2 uses D31 in-scope CWEs

### 1.2 Method

A uses `JoernExtractor`; B runs samples sequentially in one container; C parses a batch. Wall time uses `perf_counter`; warm-ups (`rep=0`) are excluded; memory uses the recorded container peak method.

### 1.3 Spike vs production path

E1 is represented by the E3 production-path A runs. The historical spike baseline was 5.85 s/sample; it used three Joern exports per sample, so this is not a like-for-like comparison.

| Group | Production A median (s/sample) |
| --- | --- |
| c | 4.847 |
| cpp | 5.049 |
| python | 5.451 |

### 1.4 Where the time goes

| Variant | Group | Wall (s) | Parse (s) | Export (s) | XML (s) | Peak MiB |
| --- | --- | --- | --- | --- | --- | --- |
| B | c | 4.844 | 2.732 | 1.123 | 0.001 | 265.7 |
| B | cpp | 5.134 | 3.018 | 1.446 | 0.005 | 267.7 |
| B | python | 5.489 | 2.853 | 1.773 | 0.014 | 248.6 |
| floor | floor | 0.785 | 0.000 | 0.000 | 0.000 | N/A |

### 1.5 Variants at one worker

| Variant | Group | Workers | Batch | Wall (s) | Samples/s | Speed-up | Efficiency | Success | Failures | Peak MiB |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A | c | 1 | 1 | 96.931 | 0.206 | 1.00x | N/A | 100.0% | 0 | N/A |
| A | cpp | 1 | 1 | 100.990 | 0.198 | 1.00x | N/A | 100.0% | 0 | N/A |
| A | python | 1 | 1 | 109.022 | 0.183 | 1.00x | N/A | 100.0% | 0 | N/A |
| B | c | 1 | 1 | 89.083 | 0.225 | 1.09x | N/A | 100.0% | 0 | 294.7 |
| B | cpp | 1 | 1 | 89.441 | 0.224 | 1.13x | N/A | 100.0% | 0 | 276.8 |
| B | python | 1 | 1 | 98.027 | 0.204 | 1.11x | N/A | 100.0% | 0 | 345.7 |
| C | c | 1 | 10 | 15.752 | 1.270 | 6.15x | N/A | 100.0% | 0 | 289.5 |
| C | c | 1 | 20 | 9.726 | 2.056 | 9.97x | N/A | 100.0% | 0 | 380.6 |
| C | c | 1 | 50 | 8.829 | 2.265 | 10.98x | N/A | 66.7% | 20 | 328.4 |
| C | cpp | 1 | 10 | 12.753 | 1.568 | 7.92x | N/A | 100.0% | 0 | 298.1 |
| C | cpp | 1 | 20 | 8.529 | 2.345 | 11.84x | N/A | 100.0% | 0 | 337.0 |
| C | cpp | 1 | 50 | 8.927 | 2.240 | 11.31x | N/A | 100.0% | 0 | 392.8 |
| C | python | 1 | 10 | 18.095 | 1.105 | 6.02x | N/A | 100.0% | 0 | 398.7 |
| C | python | 1 | 20 | 13.500 | 1.482 | 8.08x | N/A | 100.0% | 0 | 834.0 |
| C | python | 1 | 50 | 12.901 | 1.550 | 8.45x | N/A | 100.0% | 0 | 768.3 |

### 1.6 Workers

| Variant | Group | Workers | Batch | Wall (s) | Samples/s | Speed-up | Efficiency | Success | Failures | Peak MiB |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A | c | 1 | 1 | 102.197 | 0.197 | 1.00x | 100.0% | 100.0% | 0 | N/A |
| A | c | 2 | 1 | 56.597 | 0.353 | 1.81x | 90.3% | 100.0% | 0 | N/A |
| A | c | 4 | 1 | 40.904 | 0.490 | 2.50x | 62.5% | 100.0% | 0 | N/A |
| A | cpp | 1 | 1 | 98.668 | 0.203 | 1.00x | 100.0% | 100.0% | 0 | N/A |
| A | cpp | 2 | 1 | 56.945 | 0.351 | 1.73x | 86.6% | 100.0% | 0 | N/A |
| A | cpp | 4 | 1 | 39.433 | 0.508 | 2.50x | 62.6% | 100.0% | 0 | N/A |
| A | python | 1 | 1 | 104.315 | 0.192 | 1.00x | 100.0% | 100.0% | 0 | N/A |
| A | python | 2 | 1 | 57.448 | 0.348 | 1.82x | 90.8% | 100.0% | 0 | N/A |
| A | python | 4 | 1 | 39.928 | 0.501 | 2.61x | 65.3% | 100.0% | 0 | N/A |
| C | c | 1 | 20 | 8.947 | 2.235 | 1.00x | 100.0% | 100.0% | 0 | 389.2 |
| C | c | 2 | 20 | 8.273 | 2.420 | 1.08x | 54.1% | 100.0% | 0 | 290.7 |
| C | c | 4 | 20 | 9.635 | 2.076 | 0.93x | 23.2% | 100.0% | 0 | 278.8 |
| C | cpp | 1 | 20 | 8.527 | 2.347 | 1.00x | 100.0% | 100.0% | 0 | 339.2 |
| C | cpp | 2 | 20 | 7.893 | 2.534 | 1.08x | 54.0% | 100.0% | 0 | 295.4 |
| C | cpp | 4 | 20 | 11.550 | 1.734 | 0.74x | 18.5% | 100.0% | 0 | 290.4 |
| C | python | 1 | 20 | 12.964 | 1.543 | 1.00x | 100.0% | 100.0% | 0 | 778.6 |
| C | python | 2 | 20 | 10.055 | 1.992 | 1.29x | 64.5% | 100.0% | 0 | 504.5 |
| C | python | 4 | 20 | 12.229 | 1.636 | 1.06x | 26.5% | 100.0% | 0 | 367.1 |

### 1.7 Scale set and long tail

**Per-sample tail statistics (E5; successful latencies, failures shown separately):**

| Variant | Group | Workers | Batch | Samples | p50 (s) | p95 (s) | Max (s) | Timeouts | Timed-out IDs | Other failures | Other IDs | Slowest 5% time share | Corr(lines,time) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A | c | 4 | 1 | 200 | 6.328 | 7.943 | 14.398 | 0 | none | 0 | none | 7.1% | 0.741 |
| A | cpp | 4 | 1 | 200 | 7.060 | 8.196 | 10.688 | 0 | none | 0 | none | 6.1% | 0.650 |
| A | python | 4 | 1 | 200 | 7.002 | 8.648 | 54.067 | 0 | none | 0 | none | 11.0% | 0.834 |
| C | c | 4 | 20 | 200 | 0.585 | 0.841 | 0.841 | 0 | none | 0 | none | 7.0% | 0.128 |
| C | cpp | 4 | 20 | 200 | 0.651 | 0.923 | 0.946 | 0 | none | 0 | none | 7.1% | 0.054 |
| C | python | 4 | 20 | 200 | 0.690 | 1.221 | 6.457 | 0 | none | 0 | none | 31.4% | 0.312 |

**Scale versus spike throughput (matched configurations):**

| Variant | Group | Workers | Batch | Spike samples/s | Scale samples/s | Change | >25%? |
| --- | --- | --- | --- | --- | --- | --- | --- |
| A | c | 4 | 1 | 0.490 | 0.606 | +23.6% | no |
| A | cpp | 4 | 1 | 0.508 | 0.558 | +10.0% | no |
| A | python | 4 | 1 | 0.501 | 0.503 | +0.3% | no |
| C | c | 4 | 20 | 2.076 | 5.838 | +181.2% | yes |
| C | cpp | 4 | 20 | 1.734 | 5.374 | +210.0% | yes |
| C | python | 4 | 20 | 1.636 | 2.105 | +28.6% | yes |

E5 differs from E4 by more than 25% for C/c/w4, C/cpp/w4, C/python/w4. E5 scale throughput is used for projections.

| Variant | Group | Workers | Batch | Wall (s) | Samples/s | Speed-up | Efficiency | Success | Failures | Peak MiB |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A | c | 4 | 1 | 330.099 | 0.606 | N/A | N/A | 100.0% | 0 | N/A |
| A | cpp | 4 | 1 | 358.318 | 0.558 | N/A | N/A | 100.0% | 0 | N/A |
| A | python | 4 | 1 | 397.816 | 0.503 | N/A | N/A | 100.0% | 0 | N/A |
| C | c | 4 | 20 | 34.261 | 5.838 | N/A | N/A | 100.0% | 0 | 851.3 |
| C | cpp | 4 | 20 | 37.217 | 5.374 | N/A | N/A | 100.0% | 0 | 824.5 |
| C | python | 4 | 20 | 95.021 | 2.105 | N/A | N/A | 100.0% | 0 | 1871.1 |

### 1.8 Is batching safe?

Match rule: exact per-file node-type and edge-type histograms; omit unattributable nodes and their incident edges, plus METHOD_PARAMETER_IN/OUT. Ignored node types observed: BINDING, BLOCK, CLOSURE_BINDING, FILE, META_DATA, METHOD, METHOD_PARAMETER_IN, METHOD_PARAMETER_OUT, METHOD_RETURN, NAMESPACE, NAMESPACE_BLOCK, TYPE, TYPE_DECL.

| Group | Batching | Unattributable METHODS | Cross-file CALL edges | Mismatch rate by file | Caveats | Candidate signals |
| --- | --- | --- | --- | --- | --- | --- |
| c | not usable | 1 | 0 | c_spike_001.c: 56.7%, c_spike_002.c: 56.7% | 1 METHOD nodes lack unique file attribution; per-file type histograms differ for c_spike_001.c, c_spike_002.c | METHOD.FILENAME: separates (2 files, c_spike_001.c=1, c_spike_002.c=1); NAMESPACE_BLOCK.FILENAME: separates (2 files, c_spike_001.c=1, c_spike_002.c=1); TYPE_DECL.FILENAME: separates (2 files, c_spike_001.c=1, c_spike_002.c=1); FILE.NAME: separates (2 files, c_spike_001.c=1, c_spike_002.c=1); SOURCE_FILE edges: separates (2 files); AST/CONTAINS reachability from file nodes: separates (methods 2/3) |
| cpp | not usable | 10 | 0 | cpp_spike_001.cpp: 45.6%, cpp_spike_002.cpp: 30.9% | 10 METHOD nodes lack unique file attribution; per-file type histograms differ for cpp_spike_001.cpp, cpp_spike_002.cpp | METHOD.FILENAME: separates (2 files, cpp_spike_001.cpp=2, cpp_spike_002.cpp=2); NAMESPACE_BLOCK.FILENAME: separates (2 files, cpp_spike_001.cpp=1, cpp_spike_002.cpp=1); TYPE_DECL.FILENAME: separates (2 files, cpp_spike_001.cpp=2, cpp_spike_002.cpp=2); FILE.NAME: separates (2 files, cpp_spike_001.cpp=1, cpp_spike_002.cpp=1); SOURCE_FILE edges: separates (2 files); AST/CONTAINS reachability from file nodes: separates (methods 4/14) |
| python | not usable | 4 | 0 | python_fidelity_calls.py: 32.1%, python_fidelity_get_user.py: 33.2% | 4 METHOD nodes lack unique file attribution; per-file type histograms differ for python_fidelity_calls.py, python_fidelity_get_user.py | METHOD.FILENAME: separates (2 files, python_fidelity_calls.py=3, python_fidelity_get_user.py=2); NAMESPACE_BLOCK.FILENAME: separates (2 files, python_fidelity_calls.py=1, python_fidelity_get_user.py=1); TYPE_DECL.FILENAME: separates (2 files, python_fidelity_calls.py=3, python_fidelity_get_user.py=2); FILE.NAME: separates (2 files, python_fidelity_calls.py=1, python_fidelity_get_user.py=1); SOURCE_FILE edges: separates (2 files); AST/CONTAINS reachability from file nodes: separates (methods 5/9) |

python: Test distinct Joern wrappers per file or variant D: one JVM with one importCode per file.
Variant D feasibility: not evaluated in this phase.

### 1.9 How long for N rows

| Scenario | Language | Rows | Config | Samples/s | Hours | Hours (p95) | Rows / 10 h | Note |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| S1 | c | 105973 | A-b1-w4 (best non-batched (fidelity fallback); scale) | 0.606 | 48.58 | 233.82 | 21812 | E5 scale-set A baseline; batching not usable per Phase 7 fidelity probe |
| S2 | c | 3613 | A-b1-w4 (best non-batched (fidelity fallback); scale) | 0.606 | 1.66 | 7.97 | 21812 | E5 scale-set A baseline; batching not usable per Phase 7 fidelity probe |
| S3 | c | 7226 | A-b1-w4 (best non-batched (fidelity fallback); scale) | 0.606 | 3.31 | 15.94 | 21812 | E5 scale-set A baseline; batching not usable per Phase 7 fidelity probe |
| S4 | c | 14452 | A-b1-w4 (best non-batched (fidelity fallback); scale) | 0.606 | 6.63 | 31.89 | 21812 | E5 scale-set A baseline; batching not usable per Phase 7 fidelity probe |
| S1 | python | 4486 | A-b1-w4 (best non-batched (fidelity fallback); scale) | 0.503 | 2.48 | 10.78 | 18097 | E5 scale-set A baseline; batching not usable per Phase 7 fidelity probe |
| S2 | python | 1206 | A-b1-w4 (best non-batched (fidelity fallback); scale) | 0.503 | 0.67 | 2.90 | 18097 | E5 scale-set A baseline; batching not usable per Phase 7 fidelity probe |
| S3 | python | 2412 | A-b1-w4 (best non-batched (fidelity fallback); scale) | 0.503 | 1.33 | 5.79 | 18097 | E5 scale-set A baseline; batching not usable per Phase 7 fidelity probe |
| S4 | python | 4824 | A-b1-w4 (best non-batched (fidelity fallback); scale) | 0.503 | 2.67 | 11.59 | 18097 | E5 scale-set A baseline; batching not usable per Phase 7 fidelity probe |
| S5 | python | 4486 | A-b1-w4 (best non-batched (fidelity fallback); scale) | 0.503 | 2.48 | 10.78 | 18097 | E5 scale-set A baseline; batching not usable per Phase 7 fidelity probe |
| S1 | cpp | 336803 | A-b1-w4 (best non-batched (fidelity fallback); scale) | 0.558 | 167.60 | 766.79 | 20095 | E5 scale-set A baseline; batching not usable per Phase 7 fidelity probe |
| S2 | cpp | 10626 | A-b1-w4 (best non-batched (fidelity fallback); scale) | 0.558 | 5.29 | 24.19 | 20095 | E5 scale-set A baseline; batching not usable per Phase 7 fidelity probe |
| S3 | cpp | 21252 | A-b1-w4 (best non-batched (fidelity fallback); scale) | 0.558 | 10.58 | 48.38 | 20095 | E5 scale-set A baseline; batching not usable per Phase 7 fidelity probe |
| S4 | cpp | 42504 | A-b1-w4 (best non-batched (fidelity fallback); scale) | 0.558 | 21.15 | 96.77 | 20095 | E5 scale-set A baseline; batching not usable per Phase 7 fidelity probe |

### 1.10 Recommendation

Fastest successful configs (non-batched E3 fallback where fidelity failed): c: B (non-batched, batch 1, 1 workers, 0.225 samples/s); cpp: B (non-batched, batch 1, 1 workers, 0.224 samples/s); python: B (non-batched, batch 1, 1 workers, 0.204 samples/s). Fastest tested production-path worker count: c: 4; cpp: 4; python: 4. Batching is speed-only for groups that failed the Phase 7 fidelity check. The recommendation falls back to the fastest successful non-batched E3 variant; the scale projections use E5 A measurements where batching was not usable.

### 1.11 Hypotheses and limitations

H1 fixed costs dominate: confirmed by A/B versus C batch speed differences; H2 batches of 20-50 are faster: confirmed for successful runs; batching was not usable in the Phase 7 fidelity probe; H3 worker scaling is sub-linear: confirmed (A four-worker speed-up is below 4x); H4 Python attribution is a problem: confirmed by the Phase 7 probe.
<!-- BENCHMARK:END -->
