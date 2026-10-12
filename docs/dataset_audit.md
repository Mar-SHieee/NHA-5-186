# SHIELD Dataset Acceptance Audit

Generated (UTC): 2026-10-12T18:47:45.447228+00:00

Scope: every `*_deduped.parquet` file discovered in the configured directory.
This is a read-only, preliminary automated audit, not final ML acceptance.

## Dataset summary

| Dataset | Rows | Columns | Unique hashes | Duplicate-hash rows | Empty code | Multi-CWE rows | Missing commits | Verdict |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| bigvul | 103,234 | 8 | 103,234 | 0 | 0 | 623 | 0 | PRELIMINARY PASS |
| cvefixes_cpp | 8,985 | 8 | 8,985 | 0 | 0 | 349 | 0 | PRELIMINARY PASS |
| cvefixes_python | 4,563 | 8 | 4,563 | 0 | 0 | 171 | 0 | PRELIMINARY PASS |
| megavul | 336,548 | 8 | 336,548 | 0 | 0 | 40,436 | 0 | PRELIMINARY PASS |
| zenodo_python | 1,906 | 8 | 1,906 | 0 | 0 | 151 | 55 | PRELIMINARY PASS |

## Schema, nulls, labels and languages

### bigvul

- Schema errors: `[]`
- Missing values: `{"code": 0, "language": 0, "label": 0, "cwe": 0, "project": 0, "commit": 0, "fixed_code": 97431, "source": 0}`
- Empty strings (non-CWE columns): `{"code": 0, "language": 0, "project": 0, "commit": 0, "fixed_code": 0, "source": 0}`
- Label distribution: `{"0": 97431, "1": 5803}`
- Language distribution: `{"cpp": 103234}`

### cvefixes_cpp

- Schema errors: `[]`
- Missing values: `{"code": 0, "language": 0, "label": 0, "cwe": 0, "project": 0, "commit": 0, "fixed_code": 6523, "source": 0}`
- Empty strings (non-CWE columns): `{"code": 0, "language": 0, "project": 0, "commit": 0, "fixed_code": 0, "source": 0}`
- Label distribution: `{"0": 5814, "1": 3171}`
- Language distribution: `{"cpp": 8985}`

### cvefixes_python

- Schema errors: `[]`
- Missing values: `{"code": 0, "language": 0, "label": 0, "cwe": 0, "project": 0, "commit": 0, "fixed_code": 2577, "source": 0}`
- Empty strings (non-CWE columns): `{"code": 0, "language": 0, "project": 0, "commit": 0, "fixed_code": 0, "source": 0}`
- Label distribution: `{"1": 2581, "0": 1982}`
- Language distribution: `{"python": 4563}`

### megavul

- Schema errors: `[]`
- Missing values: `{"code": 0, "language": 0, "label": 0, "cwe": 0, "project": 0, "commit": 0, "fixed_code": 320154, "source": 0}`
- Empty strings (non-CWE columns): `{"code": 0, "language": 0, "project": 0, "commit": 0, "fixed_code": 0, "source": 0}`
- Label distribution: `{"0": 320154, "1": 16394}`
- Language distribution: `{"cpp": 336548}`

### zenodo_python

- Schema errors: `[]`
- Missing values: `{"code": 0, "language": 0, "label": 0, "cwe": 0, "project": 2, "commit": 55, "fixed_code": 0, "source": 0}`
- Empty strings (non-CWE columns): `{"code": 0, "language": 0, "project": 0, "commit": 0, "fixed_code": 0, "source": 0}`
- Label distribution: `{"1": 1906}`
- Language distribution: `{"python": 1906}`

## Language × CWE matrix

Multi-CWE rows count once in each CWE category. `<MISSING>` denotes empty CWE lists.

| Dataset | Language | CWE | Samples | Vulnerable samples |
| --- | --- | --- | ---: | ---: |
| bigvul | cpp | <MISSING> | 24,291 | 1,468 |
| bigvul | cpp | CWE-119 | 13,617 | 1,083 |
| bigvul | cpp | CWE-20 | 12,712 | 663 |
| bigvul | cpp | CWE-399 | 8,643 | 478 |
| bigvul | cpp | CWE-125 | 3,265 | 266 |
| bigvul | cpp | CWE-200 | 3,865 | 234 |
| bigvul | cpp | CWE-264 | 5,514 | 222 |
| bigvul | cpp | CWE-416 | 5,731 | 179 |
| bigvul | cpp | CWE-189 | 3,140 | 169 |
| bigvul | cpp | CWE-362 | 2,605 | 147 |
| bigvul | cpp | CWE-787 | 1,620 | 126 |
| bigvul | cpp | CWE-190 | 1,921 | 117 |
| bigvul | cpp | CWE-284 | 1,280 | 95 |
| bigvul | cpp | CWE-254 | 2,099 | 78 |
| bigvul | cpp | CWE-400 | 387 | 68 |
| bigvul | cpp | CWE-476 | 1,900 | 63 |
| bigvul | cpp | CWE-772 | 199 | 41 |
| bigvul | cpp | CWE-310 | 617 | 40 |
| bigvul | cpp | CWE-415 | 318 | 39 |
| bigvul | cpp | CWE-19 | 364 | 38 |
| bigvul | cpp | CWE-732 | 1,124 | 38 |
| bigvul | cpp | CWE-404 | 700 | 34 |
| bigvul | cpp | CWE-79 | 546 | 32 |
| bigvul | cpp | CWE-22 | 479 | 25 |
| bigvul | cpp | CWE-285 | 369 | 22 |
| bigvul | cpp | CWE-59 | 547 | 22 |
| bigvul | cpp | CWE-17 | 281 | 19 |
| bigvul | cpp | CWE-269 | 279 | 19 |
| bigvul | cpp | CWE-835 | 482 | 19 |
| bigvul | cpp | CWE-134 | 547 | 16 |
| bigvul | cpp | CWE-311 | 165 | 16 |
| bigvul | cpp | CWE-358 | 48 | 14 |
| bigvul | cpp | CWE-704 | 475 | 13 |
| bigvul | cpp | CWE-287 | 328 | 12 |
| bigvul | cpp | CWE-369 | 277 | 11 |
| bigvul | cpp | CWE-94 | 152 | 9 |
| bigvul | cpp | CWE-78 | 199 | 8 |
| bigvul | cpp | CWE-120 | 47 | 7 |
| bigvul | cpp | CWE-18 | 22 | 7 |
| bigvul | cpp | CWE-354 | 21 | 7 |
| bigvul | cpp | CWE-611 | 288 | 7 |
| bigvul | cpp | CWE-617 | 723 | 7 |
| bigvul | cpp | CWE-255 | 62 | 6 |
| bigvul | cpp | CWE-281 | 39 | 6 |
| bigvul | cpp | CWE-320 | 110 | 6 |
| bigvul | cpp | CWE-754 | 245 | 6 |
| bigvul | cpp | CWE-674 | 31 | 5 |
| bigvul | cpp | CWE-770 | 37 | 5 |
| bigvul | cpp | CWE-191 | 12 | 4 |
| bigvul | cpp | CWE-436 | 72 | 4 |
| bigvul | cpp | CWE-763 | 4 | 4 |
| bigvul | cpp | CWE-346 | 59 | 3 |
| bigvul | cpp | CWE-347 | 22 | 3 |
| bigvul | cpp | CWE-388 | 92 | 3 |
| bigvul | cpp | CWE-668 | 23 | 3 |
| bigvul | cpp | CWE-776 | 3 | 3 |
| bigvul | cpp | CWE-908 | 3 | 3 |
| bigvul | cpp | CWE-129 | 4 | 2 |
| bigvul | cpp | CWE-252 | 2 | 2 |
| bigvul | cpp | CWE-295 | 56 | 2 |
| bigvul | cpp | CWE-327 | 3 | 2 |
| bigvul | cpp | CWE-345 | 2 | 2 |
| bigvul | cpp | CWE-426 | 22 | 2 |
| bigvul | cpp | CWE-522 | 6 | 2 |
| bigvul | cpp | CWE-601 | 37 | 2 |
| bigvul | cpp | CWE-682 | 3 | 2 |
| bigvul | cpp | CWE-77 | 100 | 2 |
| bigvul | cpp | CWE-834 | 34 | 2 |
| bigvul | cpp | CWE-862 | 41 | 2 |
| bigvul | cpp | CWE-1021 | 56 | 1 |
| bigvul | cpp | CWE-122 | 1 | 1 |
| bigvul | cpp | CWE-209 | 1 | 1 |
| bigvul | cpp | CWE-319 | 1 | 1 |
| bigvul | cpp | CWE-326 | 1 | 1 |
| bigvul | cpp | CWE-330 | 50 | 1 |
| bigvul | cpp | CWE-352 | 29 | 1 |
| bigvul | cpp | CWE-401 | 1 | 1 |
| bigvul | cpp | CWE-502 | 21 | 1 |
| bigvul | cpp | CWE-532 | 67 | 1 |
| bigvul | cpp | CWE-664 | 13 | 1 |
| bigvul | cpp | CWE-74 | 9 | 1 |
| bigvul | cpp | CWE-755 | 14 | 1 |
| bigvul | cpp | CWE-824 | 6 | 1 |
| bigvul | cpp | CWE-90 | 17 | 1 |
| bigvul | cpp | CWE-16 | 29 | 0 |
| bigvul | cpp | CWE-172 | 2 | 0 |
| bigvul | cpp | CWE-290 | 58 | 0 |
| bigvul | cpp | CWE-361 | 2 | 0 |
| bigvul | cpp | CWE-494 | 2 | 0 |
| bigvul | cpp | CWE-665 | 3 | 0 |
| bigvul | cpp | CWE-693 | 12 | 0 |
| bigvul | cpp | CWE-706 | 12 | 0 |
| bigvul | cpp | CWE-769 | 3 | 0 |
| bigvul | cpp | CWE-89 | 47 | 0 |
| bigvul | cpp | CWE-909 | 2 | 0 |
| bigvul | cpp | CWE-918 | 15 | 0 |
| bigvul | cpp | CWE-93 | 91 | 0 |
| cvefixes_cpp | cpp | CWE-125 | 599 | 599 |
| cvefixes_cpp | cpp | CWE-787 | 573 | 573 |
| cvefixes_cpp | cpp | <MISSING> | 6,281 | 467 |
| cvefixes_cpp | cpp | CWE-190 | 325 | 325 |
| cvefixes_cpp | cpp | CWE-20 | 138 | 138 |
| cvefixes_cpp | cpp | CWE-416 | 135 | 135 |
| cvefixes_cpp | cpp | CWE-476 | 133 | 133 |
| cvefixes_cpp | cpp | CWE-120 | 127 | 127 |
| cvefixes_cpp | cpp | CWE-119 | 70 | 70 |
| cvefixes_cpp | cpp | CWE-415 | 63 | 63 |
| cvefixes_cpp | cpp | CWE-617 | 61 | 61 |
| cvefixes_cpp | cpp | CWE-284 | 53 | 53 |
| cvefixes_cpp | cpp | CWE-122 | 50 | 50 |
| cvefixes_cpp | cpp | CWE-295 | 49 | 49 |
| cvefixes_cpp | cpp | CWE-22 | 41 | 41 |
| cvefixes_cpp | cpp | CWE-843 | 40 | 40 |
| cvefixes_cpp | cpp | CWE-200 | 36 | 36 |
| cvefixes_cpp | cpp | CWE-400 | 36 | 36 |
| cvefixes_cpp | cpp | CWE-78 | 36 | 36 |
| cvefixes_cpp | cpp | CWE-362 | 31 | 31 |
| cvefixes_cpp | cpp | CWE-835 | 29 | 29 |
| cvefixes_cpp | cpp | CWE-59 | 28 | 28 |
| cvefixes_cpp | cpp | CWE-401 | 19 | 19 |
| cvefixes_cpp | cpp | CWE-276 | 18 | 18 |
| cvefixes_cpp | cpp | CWE-399 | 17 | 17 |
| cvefixes_cpp | cpp | CWE-674 | 17 | 17 |
| cvefixes_cpp | cpp | CWE-189 | 15 | 15 |
| cvefixes_cpp | cpp | CWE-330 | 15 | 15 |
| cvefixes_cpp | cpp | CWE-776 | 15 | 15 |
| cvefixes_cpp | cpp | CWE-116 | 14 | 14 |
| cvefixes_cpp | cpp | CWE-369 | 12 | 12 |
| cvefixes_cpp | cpp | CWE-287 | 11 | 11 |
| cvefixes_cpp | cpp | CWE-252 | 10 | 10 |
| cvefixes_cpp | cpp | CWE-203 | 9 | 9 |
| cvefixes_cpp | cpp | CWE-352 | 9 | 9 |
| cvefixes_cpp | cpp | CWE-310 | 8 | 8 |
| cvefixes_cpp | cpp | CWE-763 | 8 | 8 |
| cvefixes_cpp | cpp | CWE-863 | 8 | 8 |
| cvefixes_cpp | cpp | CWE-134 | 7 | 7 |
| cvefixes_cpp | cpp | CWE-323 | 7 | 7 |
| cvefixes_cpp | cpp | CWE-444 | 7 | 7 |
| cvefixes_cpp | cpp | CWE-754 | 7 | 7 |
| cvefixes_cpp | cpp | CWE-755 | 7 | 7 |
| cvefixes_cpp | cpp | CWE-772 | 7 | 7 |
| cvefixes_cpp | cpp | CWE-908 | 7 | 7 |
| cvefixes_cpp | cpp | CWE-1284 | 6 | 6 |
| cvefixes_cpp | cpp | CWE-269 | 6 | 6 |
| cvefixes_cpp | cpp | CWE-347 | 6 | 6 |
| cvefixes_cpp | cpp | CWE-601 | 6 | 6 |
| cvefixes_cpp | cpp | CWE-681 | 6 | 6 |
| cvefixes_cpp | cpp | CWE-770 | 6 | 6 |
| cvefixes_cpp | cpp | CWE-121 | 5 | 5 |
| cvefixes_cpp | cpp | CWE-264 | 5 | 5 |
| cvefixes_cpp | cpp | CWE-74 | 5 | 5 |
| cvefixes_cpp | cpp | CWE-79 | 5 | 5 |
| cvefixes_cpp | cpp | CWE-823 | 5 | 5 |
| cvefixes_cpp | cpp | CWE-17 | 4 | 4 |
| cvefixes_cpp | cpp | CWE-19 | 4 | 4 |
| cvefixes_cpp | cpp | CWE-191 | 4 | 4 |
| cvefixes_cpp | cpp | CWE-290 | 4 | 4 |
| cvefixes_cpp | cpp | CWE-358 | 4 | 4 |
| cvefixes_cpp | cpp | CWE-407 | 4 | 4 |
| cvefixes_cpp | cpp | CWE-668 | 4 | 4 |
| cvefixes_cpp | cpp | CWE-824 | 4 | 4 |
| cvefixes_cpp | cpp | CWE-129 | 3 | 3 |
| cvefixes_cpp | cpp | CWE-1333 | 3 | 3 |
| cvefixes_cpp | cpp | CWE-273 | 3 | 3 |
| cvefixes_cpp | cpp | CWE-327 | 3 | 3 |
| cvefixes_cpp | cpp | CWE-354 | 3 | 3 |
| cvefixes_cpp | cpp | CWE-428 | 3 | 3 |
| cvefixes_cpp | cpp | CWE-459 | 3 | 3 |
| cvefixes_cpp | cpp | CWE-552 | 3 | 3 |
| cvefixes_cpp | cpp | CWE-667 | 3 | 3 |
| cvefixes_cpp | cpp | CWE-670 | 3 | 3 |
| cvefixes_cpp | cpp | CWE-77 | 3 | 3 |
| cvefixes_cpp | cpp | CWE-862 | 3 | 3 |
| cvefixes_cpp | cpp | CWE-90 | 3 | 3 |
| cvefixes_cpp | cpp | CWE-909 | 3 | 3 |
| cvefixes_cpp | cpp | CWE-913 | 3 | 3 |
| cvefixes_cpp | cpp | CWE-131 | 2 | 2 |
| cvefixes_cpp | cpp | CWE-193 | 2 | 2 |
| cvefixes_cpp | cpp | CWE-241 | 2 | 2 |
| cvefixes_cpp | cpp | CWE-345 | 2 | 2 |
| cvefixes_cpp | cpp | CWE-384 | 2 | 2 |
| cvefixes_cpp | cpp | CWE-404 | 2 | 2 |
| cvefixes_cpp | cpp | CWE-502 | 2 | 2 |
| cvefixes_cpp | cpp | CWE-126 | 1 | 1 |
| cvefixes_cpp | cpp | CWE-18 | 1 | 1 |
| cvefixes_cpp | cpp | CWE-285 | 1 | 1 |
| cvefixes_cpp | cpp | CWE-319 | 1 | 1 |
| cvefixes_cpp | cpp | CWE-426 | 1 | 1 |
| cvefixes_cpp | cpp | CWE-457 | 1 | 1 |
| cvefixes_cpp | cpp | CWE-613 | 1 | 1 |
| cvefixes_cpp | cpp | CWE-665 | 1 | 1 |
| cvefixes_cpp | cpp | CWE-672 | 1 | 1 |
| cvefixes_cpp | cpp | CWE-697 | 1 | 1 |
| cvefixes_cpp | cpp | CWE-704 | 1 | 1 |
| cvefixes_cpp | cpp | CWE-706 | 1 | 1 |
| cvefixes_cpp | cpp | CWE-918 | 1 | 1 |
| cvefixes_python | python | <MISSING> | 2,471 | 489 |
| cvefixes_python | python | CWE-79 | 165 | 165 |
| cvefixes_python | python | CWE-918 | 162 | 162 |
| cvefixes_python | python | CWE-22 | 158 | 158 |
| cvefixes_python | python | CWE-601 | 130 | 130 |
| cvefixes_python | python | CWE-444 | 118 | 118 |
| cvefixes_python | python | CWE-613 | 104 | 104 |
| cvefixes_python | python | CWE-94 | 98 | 98 |
| cvefixes_python | python | CWE-20 | 87 | 87 |
| cvefixes_python | python | CWE-400 | 69 | 69 |
| cvefixes_python | python | CWE-200 | 68 | 68 |
| cvefixes_python | python | CWE-502 | 60 | 60 |
| cvefixes_python | python | CWE-352 | 50 | 50 |
| cvefixes_python | python | CWE-89 | 49 | 49 |
| cvefixes_python | python | CWE-287 | 45 | 45 |
| cvefixes_python | python | CWE-863 | 41 | 41 |
| cvefixes_python | python | CWE-78 | 39 | 39 |
| cvefixes_python | python | CWE-264 | 36 | 36 |
| cvefixes_python | python | CWE-770 | 35 | 35 |
| cvefixes_python | python | CWE-693 | 34 | 34 |
| cvefixes_python | python | CWE-59 | 32 | 32 |
| cvefixes_python | python | CWE-359 | 31 | 31 |
| cvefixes_python | python | CWE-269 | 30 | 30 |
| cvefixes_python | python | CWE-74 | 30 | 30 |
| cvefixes_python | python | CWE-29 | 27 | 27 |
| cvefixes_python | python | CWE-521 | 27 | 27 |
| cvefixes_python | python | CWE-209 | 25 | 25 |
| cvefixes_python | python | CWE-203 | 24 | 24 |
| cvefixes_python | python | CWE-125 | 23 | 23 |
| cvefixes_python | python | CWE-312 | 23 | 23 |
| cvefixes_python | python | CWE-436 | 20 | 20 |
| cvefixes_python | python | CWE-21 | 19 | 19 |
| cvefixes_python | python | CWE-532 | 18 | 18 |
| cvefixes_python | python | CWE-611 | 16 | 16 |
| cvefixes_python | python | CWE-295 | 14 | 14 |
| cvefixes_python | python | CWE-755 | 14 | 14 |
| cvefixes_python | python | CWE-434 | 13 | 13 |
| cvefixes_python | python | CWE-77 | 13 | 13 |
| cvefixes_python | python | CWE-843 | 13 | 13 |
| cvefixes_python | python | CWE-362 | 12 | 12 |
| cvefixes_python | python | CWE-835 | 12 | 12 |
| cvefixes_python | python | CWE-119 | 11 | 11 |
| cvefixes_python | python | CWE-190 | 11 | 11 |
| cvefixes_python | python | CWE-116 | 10 | 10 |
| cvefixes_python | python | CWE-1333 | 10 | 10 |
| cvefixes_python | python | CWE-326 | 10 | 10 |
| cvefixes_python | python | CWE-367 | 10 | 10 |
| cvefixes_python | python | CWE-346 | 9 | 9 |
| cvefixes_python | python | CWE-617 | 9 | 9 |
| cvefixes_python | python | CWE-668 | 9 | 9 |
| cvefixes_python | python | CWE-311 | 8 | 8 |
| cvefixes_python | python | CWE-697 | 8 | 8 |
| cvefixes_python | python | CWE-862 | 8 | 8 |
| cvefixes_python | python | CWE-93 | 8 | 8 |
| cvefixes_python | python | CWE-290 | 7 | 7 |
| cvefixes_python | python | CWE-787 | 7 | 7 |
| cvefixes_python | python | CWE-366 | 6 | 6 |
| cvefixes_python | python | CWE-670 | 6 | 6 |
| cvefixes_python | python | CWE-73 | 6 | 6 |
| cvefixes_python | python | CWE-921 | 6 | 6 |
| cvefixes_python | python | CWE-330 | 5 | 5 |
| cvefixes_python | python | CWE-331 | 5 | 5 |
| cvefixes_python | python | CWE-674 | 5 | 5 |
| cvefixes_python | python | CWE-684 | 5 | 5 |
| cvefixes_python | python | CWE-1188 | 4 | 4 |
| cvefixes_python | python | CWE-23 | 4 | 4 |
| cvefixes_python | python | CWE-254 | 4 | 4 |
| cvefixes_python | python | CWE-284 | 4 | 4 |
| cvefixes_python | python | CWE-347 | 4 | 4 |
| cvefixes_python | python | CWE-36 | 4 | 4 |
| cvefixes_python | python | CWE-667 | 4 | 4 |
| cvefixes_python | python | CWE-75 | 4 | 4 |
| cvefixes_python | python | CWE-776 | 4 | 4 |
| cvefixes_python | python | CWE-1021 | 3 | 3 |
| cvefixes_python | python | CWE-120 | 3 | 3 |
| cvefixes_python | python | CWE-193 | 3 | 3 |
| cvefixes_python | python | CWE-252 | 3 | 3 |
| cvefixes_python | python | CWE-285 | 3 | 3 |
| cvefixes_python | python | CWE-306 | 3 | 3 |
| cvefixes_python | python | CWE-310 | 3 | 3 |
| cvefixes_python | python | CWE-354 | 3 | 3 |
| cvefixes_python | python | CWE-416 | 3 | 3 |
| cvefixes_python | python | CWE-427 | 3 | 3 |
| cvefixes_python | python | CWE-476 | 3 | 3 |
| cvefixes_python | python | CWE-662 | 3 | 3 |
| cvefixes_python | python | CWE-682 | 3 | 3 |
| cvefixes_python | python | CWE-732 | 3 | 3 |
| cvefixes_python | python | CWE-789 | 3 | 3 |
| cvefixes_python | python | CWE-1236 | 2 | 2 |
| cvefixes_python | python | CWE-172 | 2 | 2 |
| cvefixes_python | python | CWE-19 | 2 | 2 |
| cvefixes_python | python | CWE-212 | 2 | 2 |
| cvefixes_python | python | CWE-255 | 2 | 2 |
| cvefixes_python | python | CWE-327 | 2 | 2 |
| cvefixes_python | python | CWE-369 | 2 | 2 |
| cvefixes_python | python | CWE-404 | 2 | 2 |
| cvefixes_python | python | CWE-415 | 2 | 2 |
| cvefixes_python | python | CWE-522 | 2 | 2 |
| cvefixes_python | python | CWE-640 | 2 | 2 |
| cvefixes_python | python | CWE-88 | 2 | 2 |
| cvefixes_python | python | CWE-1336 | 1 | 1 |
| cvefixes_python | python | CWE-134 | 1 | 1 |
| cvefixes_python | python | CWE-377 | 1 | 1 |
| cvefixes_python | python | CWE-440 | 1 | 1 |
| cvefixes_python | python | CWE-475 | 1 | 1 |
| cvefixes_python | python | CWE-534 | 1 | 1 |
| cvefixes_python | python | CWE-620 | 1 | 1 |
| cvefixes_python | python | CWE-707 | 1 | 1 |
| cvefixes_python | python | CWE-754 | 1 | 1 |
| cvefixes_python | python | CWE-80 | 1 | 1 |
| cvefixes_python | python | CWE-824 | 1 | 1 |
| cvefixes_python | python | CWE-98 | 1 | 1 |
| megavul | cpp | CWE-119 | 29,272 | 1,626 |
| megavul | cpp | CWE-787 | 29,111 | 1,490 |
| megavul | cpp | CWE-125 | 25,385 | 1,406 |
| megavul | cpp | <MISSING> | 28,153 | 1,362 |
| megavul | cpp | CWE-476 | 28,597 | 1,289 |
| megavul | cpp | CWE-20 | 21,439 | 1,098 |
| megavul | cpp | CWE-416 | 26,710 | 998 |
| megavul | cpp | CWE-190 | 12,443 | 658 |
| megavul | cpp | CWE-200 | 13,250 | 574 |
| megavul | cpp | CWE-362 | 11,731 | 507 |
| megavul | cpp | CWE-264 | 12,253 | 463 |
| megavul | cpp | CWE-399 | 12,049 | 449 |
| megavul | cpp | CWE-120 | 7,264 | 419 |
| megavul | cpp | CWE-400 | 6,860 | 311 |
| megavul | cpp | CWE-189 | 6,941 | 309 |
| megavul | cpp | CWE-401 | 11,887 | 278 |
| megavul | cpp | CWE-617 | 4,110 | 259 |
| megavul | cpp | CWE-835 | 5,293 | 252 |
| megavul | cpp | CWE-772 | 3,592 | 180 |
| megavul | cpp | CWE-415 | 6,309 | 178 |
| megavul | cpp | CWE-369 | 2,870 | 170 |
| megavul | cpp | CWE-22 | 3,781 | 155 |
| megavul | cpp | CWE-254 | 3,158 | 129 |
| megavul | cpp | CWE-674 | 2,035 | 120 |
| megavul | cpp | CWE-122 | 2,123 | 107 |
| megavul | cpp | CWE-908 | 1,831 | 102 |
| megavul | cpp | CWE-284 | 1,756 | 94 |
| megavul | cpp | CWE-287 | 1,639 | 93 |
| megavul | cpp | CWE-59 | 1,833 | 93 |
| megavul | cpp | CWE-770 | 2,048 | 92 |
| megavul | cpp | CWE-834 | 4,286 | 88 |
| megavul | cpp | CWE-310 | 1,376 | 82 |
| megavul | cpp | CWE-909 | 1,331 | 78 |
| megavul | cpp | CWE-269 | 1,526 | 76 |
| megavul | cpp | CWE-74 | 2,411 | 73 |
| megavul | cpp | CWE-295 | 1,947 | 69 |
| megavul | cpp | CWE-667 | 1,502 | 69 |
| megavul | cpp | CWE-17 | 1,093 | 65 |
| megavul | cpp | CWE-193 | 905 | 65 |
| megavul | cpp | CWE-404 | 1,934 | 60 |
| megavul | cpp | CWE-459 | 670 | 60 |
| megavul | cpp | CWE-78 | 1,359 | 60 |
| megavul | cpp | CWE-754 | 1,034 | 58 |
| megavul | cpp | CWE-843 | 1,109 | 58 |
| megavul | cpp | CWE-79 | 961 | 57 |
| megavul | cpp | CWE-19 | 1,305 | 54 |
| megavul | cpp | CWE-732 | 825 | 52 |
| megavul | cpp | CWE-681 | 706 | 51 |
| megavul | cpp | CWE-863 | 1,277 | 46 |
| megavul | cpp | CWE-665 | 1,275 | 43 |
| megavul | cpp | CWE-252 | 527 | 42 |
| megavul | cpp | CWE-755 | 1,051 | 42 |
| megavul | cpp | CWE-89 | 1,745 | 37 |
| megavul | cpp | CWE-129 | 777 | 36 |
| megavul | cpp | CWE-668 | 854 | 35 |
| megavul | cpp | CWE-203 | 736 | 33 |
| megavul | cpp | CWE-1284 | 369 | 32 |
| megavul | cpp | CWE-131 | 544 | 32 |
| megavul | cpp | CWE-367 | 1,264 | 32 |
| megavul | cpp | CWE-682 | 732 | 32 |
| megavul | cpp | CWE-704 | 863 | 32 |
| megavul | cpp | CWE-330 | 511 | 31 |
| megavul | cpp | CWE-354 | 445 | 30 |
| megavul | cpp | CWE-862 | 476 | 30 |
| megavul | cpp | CWE-134 | 1,056 | 28 |
| megavul | cpp | CWE-763 | 445 | 28 |
| megavul | cpp | CWE-191 | 965 | 27 |
| megavul | cpp | CWE-327 | 334 | 25 |
| megavul | cpp | CWE-276 | 674 | 24 |
| megavul | cpp | CWE-824 | 514 | 24 |
| megavul | cpp | CWE-121 | 233 | 23 |
| megavul | cpp | CWE-502 | 113 | 22 |
| megavul | cpp | CWE-77 | 477 | 22 |
| megavul | cpp | CWE-212 | 290 | 20 |
| megavul | cpp | CWE-345 | 197 | 20 |
| megavul | cpp | CWE-697 | 239 | 20 |
| megavul | cpp | CWE-436 | 286 | 19 |
| megavul | cpp | CWE-326 | 157 | 18 |
| megavul | cpp | CWE-444 | 186 | 18 |
| megavul | cpp | CWE-611 | 339 | 18 |
| megavul | cpp | CWE-662 | 111 | 18 |
| megavul | cpp | CWE-776 | 92 | 18 |
| megavul | cpp | CWE-94 | 411 | 18 |
| megavul | cpp | CWE-434 | 577 | 16 |
| megavul | cpp | CWE-116 | 456 | 15 |
| megavul | cpp | CWE-601 | 223 | 15 |
| megavul | cpp | CWE-672 | 89 | 13 |
| megavul | cpp | CWE-347 | 100 | 12 |
| megavul | cpp | CWE-440 | 635 | 11 |
| megavul | cpp | CWE-197 | 35 | 10 |
| megavul | cpp | CWE-426 | 249 | 10 |
| megavul | cpp | CWE-613 | 44 | 10 |
| megavul | cpp | CWE-306 | 113 | 9 |
| megavul | cpp | CWE-319 | 219 | 9 |
| megavul | cpp | CWE-384 | 217 | 9 |
| megavul | cpp | CWE-552 | 338 | 9 |
| megavul | cpp | CWE-1021 | 503 | 8 |
| megavul | cpp | CWE-290 | 80 | 8 |
| megavul | cpp | CWE-346 | 232 | 8 |
| megavul | cpp | CWE-388 | 256 | 8 |
| megavul | cpp | CWE-670 | 172 | 8 |
| megavul | cpp | CWE-913 | 46 | 8 |
| megavul | cpp | CWE-428 | 106 | 7 |
| megavul | cpp | CWE-911 | 168 | 7 |
| megavul | cpp | CWE-918 | 105 | 7 |
| megavul | cpp | CWE-18 | 36 | 6 |
| megavul | cpp | CWE-331 | 38 | 6 |
| megavul | cpp | CWE-385 | 64 | 6 |
| megavul | cpp | CWE-407 | 59 | 6 |
| megavul | cpp | CWE-532 | 127 | 6 |
| megavul | cpp | CWE-90 | 92 | 6 |
| megavul | cpp | CWE-1187 | 78 | 5 |
| megavul | cpp | CWE-126 | 26 | 5 |
| megavul | cpp | CWE-337 | 21 | 5 |
| megavul | cpp | CWE-409 | 17 | 5 |
| megavul | cpp | CWE-680 | 143 | 5 |
| megavul | cpp | CWE-693 | 329 | 5 |
| megavul | cpp | CWE-823 | 115 | 5 |
| megavul | cpp | CWE-1077 | 100 | 4 |
| megavul | cpp | CWE-16 | 310 | 4 |
| megavul | cpp | CWE-241 | 21 | 4 |
| megavul | cpp | CWE-273 | 161 | 4 |
| megavul | cpp | CWE-285 | 203 | 4 |
| megavul | cpp | CWE-338 | 21 | 4 |
| megavul | cpp | CWE-427 | 360 | 4 |
| megavul | cpp | CWE-522 | 67 | 4 |
| megavul | cpp | CWE-626 | 55 | 4 |
| megavul | cpp | CWE-88 | 28 | 4 |
| megavul | cpp | CWE-118 | 32 | 3 |
| megavul | cpp | CWE-1188 | 260 | 3 |
| megavul | cpp | CWE-172 | 23 | 3 |
| megavul | cpp | CWE-184 | 3 | 3 |
| megavul | cpp | CWE-229 | 113 | 3 |
| megavul | cpp | CWE-325 | 38 | 3 |
| megavul | cpp | CWE-494 | 48 | 3 |
| megavul | cpp | CWE-706 | 146 | 3 |
| megavul | cpp | CWE-707 | 16 | 3 |
| megavul | cpp | CWE-113 | 17 | 2 |
| megavul | cpp | CWE-1333 | 3 | 2 |
| megavul | cpp | CWE-255 | 9 | 2 |
| megavul | cpp | CWE-307 | 138 | 2 |
| megavul | cpp | CWE-320 | 29 | 2 |
| megavul | cpp | CWE-639 | 116 | 2 |
| megavul | cpp | CWE-762 | 7 | 2 |
| megavul | cpp | CWE-838 | 34 | 2 |
| megavul | cpp | CWE-924 | 12 | 2 |
| megavul | cpp | CWE-1049 | 7 | 1 |
| megavul | cpp | CWE-1050 | 75 | 1 |
| megavul | cpp | CWE-117 | 9 | 1 |
| megavul | cpp | CWE-185 | 8 | 1 |
| megavul | cpp | CWE-202 | 3 | 1 |
| megavul | cpp | CWE-208 | 48 | 1 |
| megavul | cpp | CWE-209 | 1 | 1 |
| megavul | cpp | CWE-23 | 27 | 1 |
| megavul | cpp | CWE-248 | 60 | 1 |
| megavul | cpp | CWE-250 | 587 | 1 |
| megavul | cpp | CWE-26 | 27 | 1 |
| megavul | cpp | CWE-282 | 31 | 1 |
| megavul | cpp | CWE-300 | 56 | 1 |
| megavul | cpp | CWE-312 | 187 | 1 |
| megavul | cpp | CWE-323 | 12 | 1 |
| megavul | cpp | CWE-324 | 2 | 1 |
| megavul | cpp | CWE-335 | 22 | 1 |
| megavul | cpp | CWE-349 | 62 | 1 |
| megavul | cpp | CWE-352 | 18 | 1 |
| megavul | cpp | CWE-361 | 27 | 1 |
| megavul | cpp | CWE-460 | 92 | 1 |
| megavul | cpp | CWE-475 | 21 | 1 |
| megavul | cpp | CWE-590 | 22 | 1 |
| megavul | cpp | CWE-610 | 80 | 1 |
| megavul | cpp | CWE-628 | 15 | 1 |
| megavul | cpp | CWE-73 | 11 | 1 |
| megavul | cpp | CWE-93 | 47 | 1 |
| megavul | cpp | CWE-943 | 56 | 1 |
| megavul | cpp | CWE-311 | 68 | 0 |
| megavul | cpp | CWE-358 | 65 | 0 |
| megavul | cpp | CWE-788 | 22 | 0 |
| zenodo_python | python | CWE-918 | 157 | 157 |
| zenodo_python | python | CWE-352 | 143 | 143 |
| zenodo_python | python | CWE-601 | 119 | 119 |
| zenodo_python | python | CWE-79 | 118 | 118 |
| zenodo_python | python | <MISSING> | 115 | 115 |
| zenodo_python | python | CWE-444 | 97 | 97 |
| zenodo_python | python | CWE-613 | 94 | 94 |
| zenodo_python | python | CWE-400 | 87 | 87 |
| zenodo_python | python | CWE-94 | 87 | 87 |
| zenodo_python | python | CWE-22 | 84 | 84 |
| zenodo_python | python | CWE-20 | 63 | 63 |
| zenodo_python | python | CWE-200 | 58 | 58 |
| zenodo_python | python | CWE-89 | 51 | 51 |
| zenodo_python | python | CWE-287 | 39 | 39 |
| zenodo_python | python | CWE-863 | 38 | 38 |
| zenodo_python | python | CWE-264 | 37 | 37 |
| zenodo_python | python | CWE-359 | 33 | 33 |
| zenodo_python | python | CWE-59 | 31 | 31 |
| zenodo_python | python | CWE-693 | 31 | 31 |
| zenodo_python | python | CWE-269 | 30 | 30 |
| zenodo_python | python | CWE-770 | 29 | 29 |
| zenodo_python | python | CWE-521 | 27 | 27 |
| zenodo_python | python | CWE-74 | 27 | 27 |
| zenodo_python | python | CWE-502 | 26 | 26 |
| zenodo_python | python | CWE-78 | 25 | 25 |
| zenodo_python | python | CWE-203 | 22 | 22 |
| zenodo_python | python | CWE-125 | 21 | 21 |
| zenodo_python | python | CWE-209 | 21 | 21 |
| zenodo_python | python | CWE-312 | 21 | 21 |
| zenodo_python | python | CWE-21 | 19 | 19 |
| zenodo_python | python | CWE-532 | 15 | 15 |
| zenodo_python | python | CWE-611 | 15 | 15 |
| zenodo_python | python | CWE-436 | 14 | 14 |
| zenodo_python | python | CWE-755 | 14 | 14 |
| zenodo_python | python | CWE-295 | 13 | 13 |
| zenodo_python | python | CWE-843 | 13 | 13 |
| zenodo_python | python | CWE-190 | 11 | 11 |
| zenodo_python | python | CWE-119 | 10 | 10 |
| zenodo_python | python | CWE-326 | 10 | 10 |
| zenodo_python | python | CWE-362 | 10 | 10 |
| zenodo_python | python | CWE-668 | 10 | 10 |
| zenodo_python | python | CWE-116 | 8 | 8 |
| zenodo_python | python | CWE-1333 | 8 | 8 |
| zenodo_python | python | CWE-311 | 8 | 8 |
| zenodo_python | python | CWE-367 | 7 | 7 |
| zenodo_python | python | CWE-697 | 7 | 7 |
| zenodo_python | python | CWE-75 | 7 | 7 |
| zenodo_python | python | CWE-284 | 6 | 6 |
| zenodo_python | python | CWE-331 | 6 | 6 |
| zenodo_python | python | CWE-670 | 6 | 6 |
| zenodo_python | python | CWE-93 | 6 | 6 |
| zenodo_python | python | CWE-290 | 5 | 5 |
| zenodo_python | python | CWE-787 | 5 | 5 |
| zenodo_python | python | CWE-254 | 4 | 4 |
| zenodo_python | python | CWE-29 | 4 | 4 |
| zenodo_python | python | CWE-306 | 4 | 4 |
| zenodo_python | python | CWE-330 | 4 | 4 |
| zenodo_python | python | CWE-347 | 4 | 4 |
| zenodo_python | python | CWE-77 | 4 | 4 |
| zenodo_python | python | CWE-1021 | 3 | 3 |
| zenodo_python | python | CWE-19 | 3 | 3 |
| zenodo_python | python | CWE-23 | 3 | 3 |
| zenodo_python | python | CWE-252 | 3 | 3 |
| zenodo_python | python | CWE-310 | 3 | 3 |
| zenodo_python | python | CWE-427 | 3 | 3 |
| zenodo_python | python | CWE-617 | 3 | 3 |
| zenodo_python | python | CWE-684 | 3 | 3 |
| zenodo_python | python | CWE-732 | 3 | 3 |
| zenodo_python | python | CWE-113 | 2 | 2 |
| zenodo_python | python | CWE-1236 | 2 | 2 |
| zenodo_python | python | CWE-172 | 2 | 2 |
| zenodo_python | python | CWE-212 | 2 | 2 |
| zenodo_python | python | CWE-255 | 2 | 2 |
| zenodo_python | python | CWE-285 | 2 | 2 |
| zenodo_python | python | CWE-327 | 2 | 2 |
| zenodo_python | python | CWE-346 | 2 | 2 |
| zenodo_python | python | CWE-36 | 2 | 2 |
| zenodo_python | python | CWE-369 | 2 | 2 |
| zenodo_python | python | CWE-404 | 2 | 2 |
| zenodo_python | python | CWE-476 | 2 | 2 |
| zenodo_python | python | CWE-522 | 2 | 2 |
| zenodo_python | python | CWE-674 | 2 | 2 |
| zenodo_python | python | CWE-789 | 2 | 2 |
| zenodo_python | python | CWE-835 | 2 | 2 |
| zenodo_python | python | CWE-862 | 2 | 2 |
| zenodo_python | python | CWE-134 | 1 | 1 |
| zenodo_python | python | CWE-377 | 1 | 1 |
| zenodo_python | python | CWE-415 | 1 | 1 |
| zenodo_python | python | CWE-475 | 1 | 1 |
| zenodo_python | python | CWE-620 | 1 | 1 |
| zenodo_python | python | CWE-662 | 1 | 1 |
| zenodo_python | python | CWE-707 | 1 | 1 |
| zenodo_python | python | CWE-754 | 1 | 1 |
| zenodo_python | python | CWE-80 | 1 | 1 |
| zenodo_python | python | CWE-824 | 1 | 1 |
| zenodo_python | python | CWE-88 | 1 | 1 |

## Cross-dataset code overlap

| Dataset A | Dataset B | Shared normalized hashes |
| --- | --- | ---: |
| bigvul | cvefixes_cpp | 0 |
| bigvul | cvefixes_python | 0 |
| bigvul | megavul | 0 |
| bigvul | zenodo_python | 0 |
| cvefixes_cpp | cvefixes_python | 0 |
| cvefixes_cpp | megavul | 0 |
| cvefixes_cpp | zenodo_python | 0 |
| cvefixes_python | megavul | 0 |
| cvefixes_python | zenodo_python | 0 |
| megavul | zenodo_python | 0 |

## Label conflicts and limitations

- Remaining cross-dataset normalized-hash label-conflict groups: **0**.
- Hashes use the same language-prefix, normalizers and SHA-256 implementation as `dedupe.py`.
- CWE arrays decoded from Parquet are converted to Python lists only for `schema.validate()`.
- No CVE/commit/project group-aware splitting or semantic-clone detection is performed.
- A PRELIMINARY PASS only covers schema, empty-code and duplicate-hash checks.
- This audit does not validate that commit SHAs correspond to security fixes or that CWE labels are correct.
- No dataset files are modified.
