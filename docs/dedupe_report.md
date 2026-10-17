# Dedupe report

| dataset | original | language-filtered | empty | label conflicts | internal dups | cross dups | final |
| --- | --- | --- | --- | --- | --- | --- | --- |
| megavul | 353,858 | 0 | 0 | 1,353 | 15,731 | 0 | 336,774 |
| bigvul | 188,636 | 0 | 0 | 3,125 | 1,845 | 65,648 | 118,018 |

Conflicting code-hash groups (0 vs 1): 1,811
Code-hash groups with multiple CWE labels: 42,558

## Languages excluded by registry


## Pairwise overlaps after internal dedupe, before cross-dataset dedupe

| dataset A | dataset B | shared hashes |
| --- | --- | --- |
| megavul | bigvul | 65,648 |

## Policy

- Language names and enabled status come from the language registry YAML files.
- One retained row per normalized code hash across datasets; source priority determines owner.
- Same-code CWE labels are unioned into the retained row (multi-label); provenance of other rows is not retained.
- Conflicting binary labels (0/1) for the same hash are excluded from every dataset.
- Normalization is token-based for Python and C-family languages, conservative for unknown languages.
- No CVE/commit/project grouping or semantic clone detection is performed; use group-aware splitting later.
- All original input parquet files remain unchanged.
