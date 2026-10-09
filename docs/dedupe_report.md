# Dedupe v0 report

| dataset | original | language-filtered | empty | label conflicts | internal dups | cross dups | final |
| --- | --- | --- | --- | --- | --- | --- | --- |
| megavul | 353,858 | 0 | 0 | 1,577 | 15,739 | 0 | 336,542 |
| bigvul | 217,007 | 0 | 0 | 3,318 | 52,252 | 58,206 | 103,231 |
| cvefixes_cpp | 15,222 | 0 | 0 | 1,632 | 219 | 4,386 | 8,985 |
| cvefixes_python | 4,943 | 0 | 0 | 412 | 34 | 11 | 4,486 |

Conflicting hash groups (same code, different label): 2,351

## Overlap between datasets (shared normalized hashes)

| dataset A | dataset B | shared |
| --- | --- | --- |
| megavul | bigvul | 58,206 |
| megavul | cvefixes_cpp | 3,191 |
| megavul | cvefixes_python | 1 |
| bigvul | cvefixes_cpp | 2,248 |
| bigvul | cvefixes_python | 0 |
| cvefixes_cpp | cvefixes_python | 10 |
