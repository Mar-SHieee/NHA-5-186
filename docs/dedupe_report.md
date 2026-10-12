# Dedupe report

| dataset | original | language-filtered | empty | label conflicts | internal dups | cross dups | final |
| --- | --- | --- | --- | --- | --- | --- | --- |
| megavul | 353,858 | 0 | 0 | 1,577 | 15,733 | 0 | 336,548 |
| bigvul | 217,007 | 0 | 0 | 3,318 | 52,249 | 58,206 | 103,234 |
| cvefixes_cpp | 15,222 | 0 | 0 | 1,632 | 219 | 4,386 | 8,985 |
| cvefixes_python | 4,943 | 0 | 0 | 346 | 34 | 0 | 4,563 |
| zenodo_python | 2,316 | 0 | 0 | 0 | 403 | 7 | 1,906 |

Conflicting code-hash groups (0 vs 1): 2,318
Code-hash groups with multiple CWE labels: 41,730

## Languages excluded by registry


## Pairwise overlaps after internal dedupe, before cross-dataset dedupe

| dataset A | dataset B | shared hashes |
| --- | --- | --- |
| megavul | bigvul | 58,206 |
| megavul | cvefixes_cpp | 3,191 |
| megavul | cvefixes_python | 0 |
| megavul | zenodo_python | 0 |
| bigvul | cvefixes_cpp | 2,248 |
| bigvul | cvefixes_python | 0 |
| bigvul | zenodo_python | 0 |
| cvefixes_cpp | cvefixes_python | 0 |
| cvefixes_cpp | zenodo_python | 0 |
| cvefixes_python | zenodo_python | 7 |

## Policy

- Language names and enabled status come from the language registry YAML files.
- One retained row per normalized code hash across datasets; source priority determines owner.
- Same-code CWE labels are unioned into the retained row (multi-label); provenance of other rows is not retained.
- Conflicting binary labels (0/1) for the same hash are excluded from every dataset.
- Normalization is token-based for Python and C-family languages, conservative for unknown languages.
- No CVE/commit/project grouping or semantic clone detection is performed; use group-aware splitting later.
- All original input parquet files remain unchanged.
