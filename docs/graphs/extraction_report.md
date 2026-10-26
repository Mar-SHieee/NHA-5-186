# Joern extraction report

<!-- P1 sections may be added below. -->

<!-- BENCHMARK:BEGIN -->
## 1. Extraction benchmark (W2-P2-05)

### 1.1 Environment

- **timestamp_utc:** 2026-10-26T10:38:16Z
- **os:** Windows-11-10.0.26200-SP0
- **python:** 3.12.0
- **cpu_count:** 24
- **ram_bytes:** 16907100160
- **docker_cpus:** 24
- **docker_mem_bytes:** 8188317696
- **image:** shield-joern
- **image_id:** sha256:51394b312f9ae88868f5058a3e1f90ae630bb3c6521a750d85f2552992282fba
- **joern_version:** 4.0.647
- **repo_inside_onedrive:** True
- **notes:** plugged in, high performance, apps closed

### 1.2 Method

A uses `JoernExtractor`; B runs samples sequentially in one container; C parses a batch. Wall time uses `perf_counter`; warm-ups (`rep=0`) are excluded; memory uses the recorded container peak method.

### 1.3 Spike vs production path

not run

### 1.4 Where the time goes

not run

### 1.5 Variants at one worker

not run

### 1.6 Workers

not run

### 1.7 Scale set and long tail

not run

### 1.8 Is batching safe?

not run

### 1.9 How long for N rows

not run

### 1.10 Recommendation

not run: no decision-grade measurements are present yet.

### 1.11 Hypotheses and limitations

H1–H4 verdicts are not run until the corresponding experiments are recorded.
<!-- BENCHMARK:END -->
