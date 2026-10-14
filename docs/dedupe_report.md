# Dedupe report

## Dataset summary

| dataset | original | language-filtered | empty | label conflicts | internal dups | cross dups | final |
| --- | --- | --- | --- | --- | --- | --- | --- |
| megavul | 353,858 | 0 | 0 | 1,215 | 15,747 | 0 | 336,896 |
| bigvul | 217,007 | 0 | 0 | 3,030 | 52,301 | 58,327 | 103,349 |

## Conflicting hash groups

Conflicting hash groups (same code, different binary labels): 1,503

## Pairwise overlaps after internal dedupe, before cross-dataset dedupe

| dataset A | dataset B | shared hashes |
| --- | --- | --- |
| megavul | bigvul | 58,327 |

## Scope and notes

- This report covers MegaVul and Big-Vul only.
- Original input parquet files remain unchanged.
- Cross-dataset duplicates represent shared normalized code hashes between the two datasets.
- Label conflicts must be handled consistently to avoid retaining contradictory binary labels for identical normalized code.
