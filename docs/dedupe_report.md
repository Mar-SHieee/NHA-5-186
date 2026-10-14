# Dedupe v0 report

| dataset | original | language-filtered | empty | label conflicts | internal dups | cross dups | final |
| --- | --- | --- | --- | --- | --- | --- | --- |
| megavul | 353,858 | 0 | 0 | 1,215 | 15,747 | 0 | 336,896 |
| bigvul | 217,007 | 0 | 0 | 3,030 | 52,301 | 58,327 | 103,349 |

## Language values removed by the language filter


Conflicting hash groups (same code, different label): 1,503

## Overlap between datasets (shared normalized hashes)

| dataset A | dataset B | shared |
| --- | --- | --- |
| megavul | bigvul | 58,327 |
