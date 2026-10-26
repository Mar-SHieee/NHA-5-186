# HIGH RISK — C/C++ CWE commit concentration and evaluation leakage

**Status:** OPEN — evaluation safeguard required before ML sign-off
**Scope:** SHIELD C/C++ vulnerable samples (`label=1`) **after deduplication and preliminary acceptance checks**
**Primary evidence:** `docs/datasets/audits/cpp_cwe_commit_audit.csv`
**Input datasets:** `megavul_deduped.parquet`, `bigvul_deduped.parquet`, `cvefixes_cpp_deduped.parquet`
**Owner:** Dataset preparation and ML evaluation teams

> [!CAUTION]
> **Do not use random row-level train/validation/test splitting.** Deduplication removes repeated code according to the implemented normalization/hash policy; it does not guarantee that examples derived from the same security fix, repository, or CVE are independent. A random split can put related samples in both training and evaluation.

## 1. What the audit actually measures

The audit reads **deduplicated Parquet files**, selects C/C++ vulnerable rows, expands multi-CWE annotations, and reports each CWE's sample occurrences, unique `(project, commit)` keys, unique projects, and the contribution of its largest single `(project, commit)` group.

- **Samples:** vulnerable row occurrences for a CWE, not independent CVEs or independent vulnerabilities. A multi-CWE row can appear in more than one CWE count.
- **Unique commits:** distinct `(project, commit)` keys, not merely distinct SHA strings.
- **Largest group share:** the percentage of the CWE's sample occurrences belonging to its most represented `(project, commit)` group. **This is not a measured leakage percentage.**
- **Missing metadata:** the provided CSV reports zero missing project/commit keys in its CWE rows. This does not independently validate the authenticity or correctness of the commit metadata.
- **Acceptance status:** the earlier acceptance result was *PRELIMINARY PASS* for schema/duplicate-related checks; it did **not** certify leakage-safe partitions.

The audit CSV contains **178 CWE categories**, whereas the language registry currently scopes **15 C/C++ CWEs** for the main project. The table below covers those 15 selected categories.

## 2. Results for the 15 selected C/C++ CWEs

| CWE | Vulnerable samples | Unique project-commit groups | Unique projects | Largest group | Largest group share |
|---|---:|---:|---:|---:|---:|
| CWE-119 | 2,779 | 1,189 | 275 | 108 | 3.9% |
| CWE-125 | 2,271 | 1,050 | 263 | 204 | 9.0% |
| CWE-787 | 2,189 | 952 | 314 | 204 | 9.3% |
| CWE-20 | 1,899 | 763 | 164 | 87 | 4.6% |
| CWE-476 | 1,485 | 802 | 203 | 26 | 1.8% |
| CWE-416 | 1,312 | 629 | 135 | 24 | 1.8% |
| CWE-190 | 1,100 | 417 | 179 | 219 | 19.9% |
| CWE-200 | 844 | 381 | 91 | 32 | 3.8% |
| CWE-362 | 685 | 260 | 51 | 35 | 5.1% |
| CWE-120 | 553 | 240 | 127 | 48 | 8.7% |
| CWE-400 | 415 | 130 | 52 | 74 | 17.8% |
| CWE-835 | 300 | 174 | 61 | 13 | 4.3% |
| CWE-401 | 298 | 207 | 67 | 10 | 3.4% |
| CWE-415 | 280 | 129 | 73 | 34 | 12.1% |
| CWE-22 | 221 | 97 | 74 | 24 | 10.9% |

### Main observations

**Broadly distributed categories.** CWE-119 has 2,779 sample occurrences across 1,189 project-commit groups and 275 projects; its largest group contributes 3.9%. CWE-476 and CWE-416 each have a largest-group share of just 1.8%. These are comparatively encouraging distribution indicators, **not proof of leakage-free evaluation**.

**Groups that deserve closer review.**

- **CWE-190:** 1,100 samples across 417 groups, but **219 samples (19.9%)** originate from one group.
- **CWE-400:** 415 samples across 130 groups; the largest group contributes **74 (17.8%)**.
- **CWE-415:** 280 samples across 129 groups; the largest group contributes **34 (12.1%)**.
- **CWE-22:** 221 samples across 97 groups; the largest group contributes **24 (10.9%)**.
- **CWE-787 / CWE-125:** their largest groups each contribute **204 samples**, or 9.3% / 9.0% respectively. Those figures alone do not establish that they refer to the same commit.

**Interpretation:** C/C++ generally shows much broader commit and project coverage than the previously audited concentrated Python categories. Nevertheless, a high number of commits does not exclude near-duplicate code, multi-commit CVEs, project-specific shortcuts, or leakage caused by the split design.

## 3. Why this matters for SHIELD

A single security-fix commit may yield many function-level examples. Those examples can share code context, project conventions, and vulnerability-specific patterns. If related examples land in both training and test partitions, model performance may reflect recognition of a previously encountered fix or project rather than generalization to unseen vulnerabilities.

**Important distinction:** concentration is a **risk indicator**, not evidence that leakage has already occurred. Actual leakage must be assessed against the partitions used for training and evaluation.

## 4. Required actions before ML evaluation sign-off

1. **Group-aware splitting:** keep every known `(project, commit)` group wholly inside one partition. Do not treat all missing commit values as a single global group.
2. **CVE-aware protection:** recover CVE identifiers where feasible. Where one CVE spans several commits, ensure all connected samples remain in the same partition; use connected-component grouping if CVE/commit relationships overlap.
3. **Project-disjoint holdout:** include a separate evaluation on unseen projects, and report any reduction in CWE coverage.
4. **Inspect high-concentration commits:** prioritize CWE-190, CWE-400, CWE-415, and CWE-22. Check repository/SHA validity, security-fix provenance, CWE annotation, and code-to-patch correspondence.
5. **Recompute support after splitting:** for every selected CWE and partition, report row count, unique project-commit groups, unique projects, and unique CVEs where available.
6. **Cross-partition contamination audit:** check normalized code hashes, near-duplicates, shared commit/CVE/project groups, and vulnerable/fixed counterpart relationships across partitions.
7. **Publish evaluation protocol:** document the grouping keys, fallback for missing metadata, split seed, exclusion rules, per-class support, and any remaining limitations.

## 5. Acceptance checklist

- [ ] Commit/CVE relationships audited and grouping strategy approved
- [ ] Train/validation/test partitions created with group-aware logic
- [ ] No known `(project, commit)` or CVE group crosses partitions
- [ ] Project-disjoint evaluation completed or limitation explicitly documented
- [ ] Top-contributing commit groups manually reviewed
- [ ] Per-CWE independent support and contamination checks published
- [ ] Final metrics reported only with the validated evaluation protocol

## 6. Decision and handoff

**Decision:** keep the 15 selected C/C++ CWEs provisionally. **Do not delete valid samples merely because they share a commit.** Preserve their group metadata, implement leakage-aware evaluation, and reassess per-class eligibility using independent group coverage and label quality—not raw sample counts alone.

**Next owner:** the data splitting / ML training engineer. Read this document and `docs/datasets/audits/cpp_cwe_commit_audit.csv` **before** producing train/validation/test files.

**Source of figures:** the supplied `cpp_cwe_commit_audit.csv`. This document describes the audit results and the resulting evaluation risk; it does not claim that actual train/test leakage has already been observed.
