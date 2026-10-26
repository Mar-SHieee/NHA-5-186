# Dedupe report

| dataset | original | language-filtered | empty | label conflicts | internal dups | cross dups | final |
| --- | --- | --- | --- | --- | --- | --- | --- |
| megavul | 353,858 | 0 | 0 | 1,693 | 15,726 | 0 | 336,439 |
| bigvul | 188,636 | 0 | 0 | 3,370 | 1,845 | 65,511 | 117,910 |
| cvefixes_cpp | 15,222 | 0 | 0 | 1,677 | 219 | 4,533 | 8,793 |
| cvefixes_python | 4,943 | 0 | 0 | 355 | 49 | 10 | 4,529 |
| zenodo_python | 2,316 | 0 | 0 | 117 | 364 | 1,191 | 644 |

Conflicting code-hash groups (0 vs 1): 2,580 (across datasets: 1,707, inside one dataset: 873)
Code-hash groups with multiple CWE labels: 43,353
Code-hash groups with multiple CVE ids: 32,520

Layout-insensitive Python matching (sources without line breaks, e.g. Zenodo): 1,287 key merges, 1,473 rows linked to another copy.

Same code recorded under different languages (loader mislabel): 10 key merges, 13 rows linked to another copy.

## Languages excluded by registry


## Pairwise overlaps after internal dedupe, before cross-dataset dedupe

| dataset A | dataset B | shared hashes |
| --- | --- | --- |
| megavul | bigvul | 65,511 |
| megavul | cvefixes_cpp | 3,156 |
| megavul | cvefixes_python | 0 |
| megavul | zenodo_python | 0 |
| bigvul | cvefixes_cpp | 2,609 |
| bigvul | cvefixes_python | 0 |
| bigvul | zenodo_python | 0 |
| cvefixes_cpp | cvefixes_python | 10 |
| cvefixes_cpp | zenodo_python | 5 |
| cvefixes_python | zenodo_python | 1,191 |

## Policy

- Language names and enabled status come from the language registry YAML files.
- One retained row per normalized code hash across datasets; source priority determines owner.
- Same-code CWE and CVE labels are unioned into the retained row (multi-label); provenance of other rows is not retained.
- Conflicting binary labels (0/1) for the same hash are excluded from every dataset.
- Normalization is token-based for Python and C-family languages, conservative for unknown languages.
- Python code without line breaks is matched to its laid-out copy by layout-insensitive keys; two laid-out versions are never merged this way.
- No CVE/commit/project grouping or semantic clone detection is performed; use group-aware splitting later.
- All original input parquet files remain unchanged.
- project/commit/date metadata come from the selected representative row;
  deduplication does not preserve every provenance relation.
- Keep the *_commit_cve_mapping.parquet files (CVEfixes, Big-Vul, MegaVul, Zenodo) separately for splitting.
