# HIGH RISK — Python CWE Dataset Concentration & Evaluation Leakage

**Status:** OPEN — requires remediation before final ML evaluation
**Scope:** SHIELD Python vulnerable samples, after code deduplication
**Evidence:** `docs/python_cwe_commit_audit.csv` (generated from `cvefixes_python_deduped.parquet` and `zenodo_python_deduped.parquet`)
**Risk owner:** Dataset preparation / ML evaluation team

> [!CAUTION]
> **Do not perform random row-level train/validation/test splitting on these datasets.** Multiple distinct code samples originate from the same repository and commit. Row-level deduplication does **not** establish independence of security vulnerabilities. A random split can leak related examples across partitions and inflate reported model performance.

## 1. Confirmed findings

The audit counts vulnerable (`label=1`) Python samples, expands multi-CWE labels, and counts unique `(project, commit)` groups per CWE. It reports:

| Dataset | Vulnerable samples | Unique `(project, commit)` groups | Missing project/commit in audited rows |
|---|---:|---:|---:|
| CVEfixes Python | 2,581 | 648 | 0 |
| Zenodo Python | 1,906 | 436 | 0 |

**Do not interpret 648 + 436 as a verified global unique-commit count:** the same `(project, commit)` could occur in both datasets. Also, this is an audit of vulnerable rows, not all dataset rows.

### High-concentration examples

| CWE | Vulnerable sample occurrences | Unique `(project, commit)` groups | Largest single group | Share of CWE samples |
|---|---:|---:|---:|---:|
| CWE-352 | 193 | 25 | 108 | **56.0%** |
| CWE-444 | 215 | 9 | 99 | **46.0%** |
| CWE-613 | 198 | 11 | 86 | **43.4%** |
| CWE-918 | 319 | 36 | 114 | **35.7%** |
| CWE-400 | 156 | 16 | 53 | **34.0%** |
| CWE-601 | 249 | 37 | 48 | **19.3%** |
| CWE-79 | 283 | 118 | 26 | 9.2% |
| CWE-20 | 150 | 57 | 11 | 7.3% |

These are **observed concentration statistics**, not measured leakage rates or proof that the labels are wrong. CWE sample counts are *occurrences*: a multi-CWE row can contribute to multiple CWE totals.

### Investigated commit example

For `janeczku/calibre-web`, commit `4545f4a20d9ff90b99bbd4e3e34b6de4441d6367`, tagged CWE-918:

| Measure | Before deduplication | After deduplication |
|---|---:|---:|
| Rows | 228 | 114 |
| Unique vulnerable code (literal) | 115 | 114 |
| Duplicate vulnerable code (literal) | 113 | 0 |
| Unique fixed code | 178 | 98 |

**Interpretation:** code deduplication removed repeated samples, but 114 distinct vulnerable-code rows still share a single commit. They must not be split across training and evaluation. The source commit's security-fix identity and sample-to-patch correspondence have **not yet been independently verified**.

## 2. Why this matters

- **Leakage risk:** different functions or code fragments from one patch may share implementation details, vulnerable patterns, and context; random splitting can put closely related examples in train and test.
- **Effective sample size:** hundreds of function-level rows do not imply hundreds of independent vulnerability events.
- **CWE imbalance/concentration:** a model may overfit a few repositories, commits, or vulnerability families, especially for CWE-444, CWE-613, and CWE-352.
- **Optimistic evaluation:** high random-split metrics would not establish generalization to unseen projects or vulnerability events.

The current **14 Python CWEs are a provisional scope selection**, not evidence that all 14 classes have adequate independent support. Retain them in the language registry for now; decide training eligibility only after the checks below.

## 3. Required actions before training/evaluation sign-off

1. **Implement group-aware partitioning:** at minimum, keep each `(project, commit)` group entirely within one of train/validation/test. Never use missing commits as one shared global group; handle missing identifiers with explicit fallback and report them.
2. **Audit CVE-level independence:** where CVE IDs can be recovered, prevent the same CVE from crossing partitions, including when it spans multiple commits. Consider connected-component grouping when CVE and commit relationships overlap.
3. **Run a project-disjoint evaluation:** test on projects absent from training to measure cross-project generalization. Document the trade-off in per-CWE test coverage.
4. **Recalculate class support per split:** report rows, unique projects, unique `(project, commit)` groups, and CVEs (where known), for each CWE and partition. Flag classes without adequate independent validation/test groups; do not fabricate a minimum threshold without an agreed evaluation policy.
5. **Inspect top-contributing commits:** verify repository/SHA existence, whether the commit is actually a security fix, whether the recorded CWE is supported, and whether vulnerable/fixed code pairs match the real patch. Prioritize the highest-concentration groups.
6. **Check residual near-duplicates across splits:** exact normalized-hash deduplication does not eliminate semantic clones or related code across different commits/projects.
7. **Document provenance and limitations:** distinguish raw row counts from independent vulnerability events; record commit-resolution heuristics, missing CVE metadata, multi-CWE counting, and known uncertain labels.

## 4. Acceptance gate — BLOCK FINAL METRICS until complete

- [ ] Partitioning enforces no `(project, commit)` overlap across train/validation/test.
- [ ] CVE overlap is checked where CVE metadata exists; unresolved cases are documented.
- [ ] Project-disjoint evaluation is produced or an explicit limitation is recorded.
- [ ] Per-CWE group counts and concentration are reported **for every split**.
- [ ] High-concentration commits and vulnerable/fixed pairs are manually spot-checked.
- [ ] Exact and near-duplicate cross-split risks are assessed.
- [ ] Final metrics identify the split methodology and are not presented as independent-vulnerability performance without evidence.

**Current disposition:** **Dataset deduplication passed its narrow duplicate-removal objective; independent-event validation and leakage-safe evaluation remain OPEN.** Do not delete entire commits or remove CWE classes solely because of concentration; preserve evidence and make a documented split/training decision.

## 5. Reproduction / handoff

- Audit output: `docs/python_cwe_commit_audit.csv`.
- Input datasets: `data/interim/cvefixes_python_deduped.parquet`, `data/interim/zenodo_python_deduped.parquet`.
- Audit definition: vulnerable Python rows only (`label == 1`), CWE values exploded into individual labels, `(project, commit)` used as the grouping key, largest-group percentage = largest group rows / all rows for that CWE.
- **Caveat:** the audit's CWE-level deduplication key includes `dataset` and `code`; it is not a substitute for cross-dataset CVE identity resolution or independent-vulnerability counting.

**Next owner:** ML dataset splitting / evaluation engineer. **Next deliverable:** reproducible leakage-safe split manifest and per-split independence report.
