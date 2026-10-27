# SHIELD Dataset Acceptance Audit

Generated (UTC): 2026-10-20T23:05:08.942233+00:00

Scope: every `*_deduped.parquet` file discovered in the configured directory.
This is a read-only, preliminary automated audit, not final ML acceptance.

## Dataset summary

| Dataset | Rows | Columns | Unique hashes | Duplicate-hash rows | Empty code | Multi-CWE rows | Missing commits | Verdict |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| bigvul | 117,910 | 10 | 117,910 | 0 | 0 | 779 | 0 | PRELIMINARY PASS |
| cvefixes_cpp | 8,793 | 10 | 8,793 | 0 | 0 | 338 | 0 | PRELIMINARY PASS |
| cvefixes_python | 4,539 | 10 | 4,539 | 0 | 0 | 176 | 0 | PRELIMINARY PASS |
| megavul | 336,439 | 10 | 336,439 | 0 | 0 | 41,995 | 0 | PRELIMINARY PASS |
| zenodo_python | 644 | 10 | 644 | 0 | 0 | 65 | 25 | PRELIMINARY PASS |

## Schema, nulls, labels and languages

### bigvul

- Schema errors: `[]`
- Missing values: `{"code": 0, "language": 0, "label": 0, "cwe": 0, "project": 0, "commit": 0, "date": 12574, "cve": 0, "fixed_code": 111145, "source": 0}`
- Empty lists (cwe / cve): `{"cwe": 27737, "cve": 12009}`
- Empty strings (non-CWE columns): `{"code": 0, "language": 0, "project": 0, "commit": 0, "date": 0, "cve": 0, "fixed_code": 0, "source": 0}`
- Label distribution: `{"0": 111145, "1": 6765}`
- Language distribution: `{"cpp": 117910}`

### cvefixes_cpp

- Schema errors: `[]`
- Missing values: `{"code": 0, "language": 0, "label": 0, "cwe": 0, "project": 0, "commit": 0, "date": 0, "cve": 0, "fixed_code": 6446, "source": 0}`
- Empty lists (cwe / cve): `{"cwe": 6228, "cve": 5773}`
- Empty strings (non-CWE columns): `{"code": 0, "language": 0, "project": 0, "commit": 0, "date": 0, "cve": 0, "fixed_code": 0, "source": 0}`
- Label distribution: `{"0": 5773, "1": 3020}`
- Language distribution: `{"cpp": 8793}`

### cvefixes_python

- Schema errors: `[]`
- Missing values: `{"code": 0, "language": 0, "label": 0, "cwe": 0, "project": 0, "commit": 0, "date": 0, "cve": 0, "fixed_code": 2576, "source": 0}`
- Empty lists (cwe / cve): `{"cwe": 2469, "cve": 1982}`
- Empty strings (non-CWE columns): `{"code": 0, "language": 0, "project": 0, "commit": 0, "date": 0, "cve": 0, "fixed_code": 0, "source": 0}`
- Label distribution: `{"1": 2557, "0": 1982}`
- Language distribution: `{"python": 4539}`

### megavul

- Schema errors: `[]`
- Missing values: `{"code": 0, "language": 0, "label": 0, "cwe": 0, "project": 0, "commit": 0, "date": 0, "cve": 0, "fixed_code": 320143, "source": 0}`
- Empty lists (cwe / cve): `{"cwe": 27852, "cve": 0}`
- Empty strings (non-CWE columns): `{"code": 0, "language": 0, "project": 0, "commit": 0, "date": 0, "cve": 0, "fixed_code": 0, "source": 0}`
- Label distribution: `{"0": 320143, "1": 16296}`
- Language distribution: `{"cpp": 336439}`

### zenodo_python

- Schema errors: `[]`
- Missing values: `{"code": 0, "language": 0, "label": 0, "cwe": 0, "project": 0, "commit": 25, "date": 0, "cve": 0, "fixed_code": 0, "source": 0}`
- Empty lists (cwe / cve): `{"cwe": 47, "cve": 0}`
- Empty strings (non-CWE columns): `{"code": 0, "language": 0, "project": 0, "commit": 0, "date": 0, "cve": 0, "fixed_code": 0, "source": 0}`
- Label distribution: `{"1": 644}`
- Language distribution: `{"python": 644}`

## Language × CWE matrix

Multi-CWE rows count once in each CWE category. `<MISSING>` denotes empty CWE lists.

| Dataset | Language | CWE | Samples | Vulnerable samples |
| --- | --- | --- | ---: | ---: |
| bigvul | cpp | <MISSING> | 27,737 | 1,710 |
| bigvul | cpp | CWE-119 | 15,544 | 1,225 |
| bigvul | cpp | CWE-20 | 14,475 | 789 |
| bigvul | cpp | CWE-399 | 9,852 | 561 |
| bigvul | cpp | CWE-125 | 3,694 | 308 |
| bigvul | cpp | CWE-200 | 4,417 | 269 |
| bigvul | cpp | CWE-264 | 6,282 | 259 |
| bigvul | cpp | CWE-416 | 6,620 | 211 |
| bigvul | cpp | CWE-189 | 3,557 | 204 |
| bigvul | cpp | CWE-362 | 2,981 | 170 |
| bigvul | cpp | CWE-787 | 1,924 | 158 |
| bigvul | cpp | CWE-190 | 2,183 | 139 |
| bigvul | cpp | CWE-284 | 1,544 | 118 |
| bigvul | cpp | CWE-254 | 2,416 | 94 |
| bigvul | cpp | CWE-400 | 447 | 84 |
| bigvul | cpp | CWE-476 | 2,157 | 73 |
| bigvul | cpp | CWE-732 | 1,349 | 50 |
| bigvul | cpp | CWE-310 | 712 | 49 |
| bigvul | cpp | CWE-772 | 225 | 48 |
| bigvul | cpp | CWE-404 | 793 | 43 |
| bigvul | cpp | CWE-19 | 417 | 41 |
| bigvul | cpp | CWE-415 | 369 | 40 |
| bigvul | cpp | CWE-79 | 649 | 38 |
| bigvul | cpp | CWE-22 | 543 | 26 |
| bigvul | cpp | CWE-269 | 314 | 25 |
| bigvul | cpp | CWE-285 | 430 | 24 |
| bigvul | cpp | CWE-59 | 594 | 24 |
| bigvul | cpp | CWE-17 | 313 | 21 |
| bigvul | cpp | CWE-835 | 537 | 20 |
| bigvul | cpp | CWE-134 | 613 | 19 |
| bigvul | cpp | CWE-311 | 200 | 19 |
| bigvul | cpp | CWE-358 | 61 | 18 |
| bigvul | cpp | CWE-287 | 374 | 16 |
| bigvul | cpp | CWE-704 | 558 | 16 |
| bigvul | cpp | CWE-369 | 316 | 13 |
| bigvul | cpp | CWE-94 | 176 | 11 |
| bigvul | cpp | CWE-617 | 802 | 9 |
| bigvul | cpp | CWE-78 | 219 | 8 |
| bigvul | cpp | CWE-120 | 51 | 7 |
| bigvul | cpp | CWE-18 | 22 | 7 |
| bigvul | cpp | CWE-255 | 70 | 7 |
| bigvul | cpp | CWE-281 | 50 | 7 |
| bigvul | cpp | CWE-320 | 117 | 7 |
| bigvul | cpp | CWE-354 | 23 | 7 |
| bigvul | cpp | CWE-191 | 15 | 6 |
| bigvul | cpp | CWE-611 | 319 | 6 |
| bigvul | cpp | CWE-674 | 35 | 6 |
| bigvul | cpp | CWE-754 | 263 | 6 |
| bigvul | cpp | CWE-770 | 46 | 6 |
| bigvul | cpp | CWE-295 | 66 | 4 |
| bigvul | cpp | CWE-346 | 69 | 4 |
| bigvul | cpp | CWE-436 | 80 | 4 |
| bigvul | cpp | CWE-668 | 29 | 4 |
| bigvul | cpp | CWE-129 | 7 | 3 |
| bigvul | cpp | CWE-347 | 24 | 3 |
| bigvul | cpp | CWE-388 | 100 | 3 |
| bigvul | cpp | CWE-426 | 28 | 3 |
| bigvul | cpp | CWE-763 | 3 | 3 |
| bigvul | cpp | CWE-77 | 114 | 3 |
| bigvul | cpp | CWE-834 | 40 | 3 |
| bigvul | cpp | CWE-908 | 3 | 3 |
| bigvul | cpp | CWE-252 | 2 | 2 |
| bigvul | cpp | CWE-319 | 2 | 2 |
| bigvul | cpp | CWE-327 | 3 | 2 |
| bigvul | cpp | CWE-345 | 2 | 2 |
| bigvul | cpp | CWE-502 | 23 | 2 |
| bigvul | cpp | CWE-522 | 7 | 2 |
| bigvul | cpp | CWE-601 | 46 | 2 |
| bigvul | cpp | CWE-682 | 3 | 2 |
| bigvul | cpp | CWE-776 | 2 | 2 |
| bigvul | cpp | CWE-862 | 46 | 2 |
| bigvul | cpp | CWE-1021 | 63 | 1 |
| bigvul | cpp | CWE-122 | 1 | 1 |
| bigvul | cpp | CWE-209 | 1 | 1 |
| bigvul | cpp | CWE-290 | 64 | 1 |
| bigvul | cpp | CWE-326 | 1 | 1 |
| bigvul | cpp | CWE-330 | 55 | 1 |
| bigvul | cpp | CWE-331 | 1 | 1 |
| bigvul | cpp | CWE-352 | 36 | 1 |
| bigvul | cpp | CWE-401 | 1 | 1 |
| bigvul | cpp | CWE-532 | 79 | 1 |
| bigvul | cpp | CWE-664 | 17 | 1 |
| bigvul | cpp | CWE-665 | 5 | 1 |
| bigvul | cpp | CWE-74 | 9 | 1 |
| bigvul | cpp | CWE-755 | 16 | 1 |
| bigvul | cpp | CWE-824 | 6 | 1 |
| bigvul | cpp | CWE-90 | 18 | 1 |
| bigvul | cpp | CWE-16 | 33 | 0 |
| bigvul | cpp | CWE-172 | 3 | 0 |
| bigvul | cpp | CWE-361 | 2 | 0 |
| bigvul | cpp | CWE-494 | 2 | 0 |
| bigvul | cpp | CWE-693 | 12 | 0 |
| bigvul | cpp | CWE-706 | 14 | 0 |
| bigvul | cpp | CWE-769 | 3 | 0 |
| bigvul | cpp | CWE-89 | 49 | 0 |
| bigvul | cpp | CWE-909 | 3 | 0 |
| bigvul | cpp | CWE-918 | 16 | 0 |
| bigvul | cpp | CWE-93 | 99 | 0 |
| cvefixes_cpp | cpp | CWE-125 | 583 | 583 |
| cvefixes_cpp | cpp | CWE-787 | 562 | 562 |
| cvefixes_cpp | cpp | <MISSING> | 6,228 | 455 |
| cvefixes_cpp | cpp | CWE-190 | 315 | 315 |
| cvefixes_cpp | cpp | CWE-120 | 127 | 127 |
| cvefixes_cpp | cpp | CWE-416 | 127 | 127 |
| cvefixes_cpp | cpp | CWE-476 | 127 | 127 |
| cvefixes_cpp | cpp | CWE-20 | 125 | 125 |
| cvefixes_cpp | cpp | CWE-415 | 62 | 62 |
| cvefixes_cpp | cpp | CWE-617 | 60 | 60 |
| cvefixes_cpp | cpp | CWE-119 | 53 | 53 |
| cvefixes_cpp | cpp | CWE-284 | 52 | 52 |
| cvefixes_cpp | cpp | CWE-122 | 50 | 50 |
| cvefixes_cpp | cpp | CWE-295 | 47 | 47 |
| cvefixes_cpp | cpp | CWE-22 | 41 | 41 |
| cvefixes_cpp | cpp | CWE-843 | 40 | 40 |
| cvefixes_cpp | cpp | CWE-78 | 36 | 36 |
| cvefixes_cpp | cpp | CWE-200 | 35 | 35 |
| cvefixes_cpp | cpp | CWE-835 | 29 | 29 |
| cvefixes_cpp | cpp | CWE-59 | 27 | 27 |
| cvefixes_cpp | cpp | CWE-362 | 23 | 23 |
| cvefixes_cpp | cpp | CWE-400 | 23 | 23 |
| cvefixes_cpp | cpp | CWE-401 | 19 | 19 |
| cvefixes_cpp | cpp | CWE-276 | 18 | 18 |
| cvefixes_cpp | cpp | CWE-674 | 16 | 16 |
| cvefixes_cpp | cpp | CWE-330 | 15 | 15 |
| cvefixes_cpp | cpp | CWE-776 | 15 | 15 |
| cvefixes_cpp | cpp | CWE-116 | 14 | 14 |
| cvefixes_cpp | cpp | CWE-369 | 12 | 12 |
| cvefixes_cpp | cpp | CWE-287 | 11 | 11 |
| cvefixes_cpp | cpp | CWE-252 | 10 | 10 |
| cvefixes_cpp | cpp | CWE-399 | 10 | 10 |
| cvefixes_cpp | cpp | CWE-203 | 9 | 9 |
| cvefixes_cpp | cpp | CWE-352 | 9 | 9 |
| cvefixes_cpp | cpp | CWE-763 | 8 | 8 |
| cvefixes_cpp | cpp | CWE-863 | 8 | 8 |
| cvefixes_cpp | cpp | CWE-134 | 7 | 7 |
| cvefixes_cpp | cpp | CWE-323 | 7 | 7 |
| cvefixes_cpp | cpp | CWE-444 | 7 | 7 |
| cvefixes_cpp | cpp | CWE-754 | 7 | 7 |
| cvefixes_cpp | cpp | CWE-755 | 7 | 7 |
| cvefixes_cpp | cpp | CWE-908 | 7 | 7 |
| cvefixes_cpp | cpp | CWE-1284 | 6 | 6 |
| cvefixes_cpp | cpp | CWE-189 | 6 | 6 |
| cvefixes_cpp | cpp | CWE-347 | 6 | 6 |
| cvefixes_cpp | cpp | CWE-601 | 6 | 6 |
| cvefixes_cpp | cpp | CWE-681 | 6 | 6 |
| cvefixes_cpp | cpp | CWE-770 | 6 | 6 |
| cvefixes_cpp | cpp | CWE-121 | 5 | 5 |
| cvefixes_cpp | cpp | CWE-269 | 5 | 5 |
| cvefixes_cpp | cpp | CWE-310 | 5 | 5 |
| cvefixes_cpp | cpp | CWE-74 | 5 | 5 |
| cvefixes_cpp | cpp | CWE-79 | 5 | 5 |
| cvefixes_cpp | cpp | CWE-823 | 5 | 5 |
| cvefixes_cpp | cpp | CWE-407 | 4 | 4 |
| cvefixes_cpp | cpp | CWE-824 | 4 | 4 |
| cvefixes_cpp | cpp | CWE-1333 | 3 | 3 |
| cvefixes_cpp | cpp | CWE-17 | 3 | 3 |
| cvefixes_cpp | cpp | CWE-19 | 3 | 3 |
| cvefixes_cpp | cpp | CWE-273 | 3 | 3 |
| cvefixes_cpp | cpp | CWE-290 | 3 | 3 |
| cvefixes_cpp | cpp | CWE-327 | 3 | 3 |
| cvefixes_cpp | cpp | CWE-354 | 3 | 3 |
| cvefixes_cpp | cpp | CWE-428 | 3 | 3 |
| cvefixes_cpp | cpp | CWE-459 | 3 | 3 |
| cvefixes_cpp | cpp | CWE-552 | 3 | 3 |
| cvefixes_cpp | cpp | CWE-668 | 3 | 3 |
| cvefixes_cpp | cpp | CWE-670 | 3 | 3 |
| cvefixes_cpp | cpp | CWE-772 | 3 | 3 |
| cvefixes_cpp | cpp | CWE-862 | 3 | 3 |
| cvefixes_cpp | cpp | CWE-90 | 3 | 3 |
| cvefixes_cpp | cpp | CWE-909 | 3 | 3 |
| cvefixes_cpp | cpp | CWE-913 | 3 | 3 |
| cvefixes_cpp | cpp | CWE-129 | 2 | 2 |
| cvefixes_cpp | cpp | CWE-131 | 2 | 2 |
| cvefixes_cpp | cpp | CWE-191 | 2 | 2 |
| cvefixes_cpp | cpp | CWE-193 | 2 | 2 |
| cvefixes_cpp | cpp | CWE-241 | 2 | 2 |
| cvefixes_cpp | cpp | CWE-345 | 2 | 2 |
| cvefixes_cpp | cpp | CWE-384 | 2 | 2 |
| cvefixes_cpp | cpp | CWE-404 | 2 | 2 |
| cvefixes_cpp | cpp | CWE-502 | 2 | 2 |
| cvefixes_cpp | cpp | CWE-667 | 2 | 2 |
| cvefixes_cpp | cpp | CWE-77 | 2 | 2 |
| cvefixes_cpp | cpp | CWE-126 | 1 | 1 |
| cvefixes_cpp | cpp | CWE-457 | 1 | 1 |
| cvefixes_cpp | cpp | CWE-613 | 1 | 1 |
| cvefixes_cpp | cpp | CWE-665 | 1 | 1 |
| cvefixes_cpp | cpp | CWE-672 | 1 | 1 |
| cvefixes_cpp | cpp | CWE-697 | 1 | 1 |
| cvefixes_cpp | cpp | CWE-704 | 1 | 1 |
| cvefixes_cpp | cpp | CWE-706 | 1 | 1 |
| cvefixes_cpp | cpp | CWE-918 | 1 | 1 |
| cvefixes_python | python | <MISSING> | 2,469 | 487 |
| cvefixes_python | python | CWE-79 | 165 | 165 |
| cvefixes_python | python | CWE-918 | 161 | 161 |
| cvefixes_python | python | CWE-22 | 157 | 157 |
| cvefixes_python | python | CWE-601 | 130 | 130 |
| cvefixes_python | python | CWE-444 | 118 | 118 |
| cvefixes_python | python | CWE-94 | 100 | 100 |
| cvefixes_python | python | CWE-613 | 90 | 90 |
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
| cvefixes_python | python | CWE-359 | 31 | 31 |
| cvefixes_python | python | CWE-59 | 31 | 31 |
| cvefixes_python | python | CWE-74 | 31 | 31 |
| cvefixes_python | python | CWE-269 | 30 | 30 |
| cvefixes_python | python | CWE-29 | 27 | 27 |
| cvefixes_python | python | CWE-209 | 25 | 25 |
| cvefixes_python | python | CWE-521 | 25 | 25 |
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
| cvefixes_python | python | CWE-522 | 2 | 2 |
| cvefixes_python | python | CWE-640 | 2 | 2 |
| cvefixes_python | python | CWE-88 | 2 | 2 |
| cvefixes_python | python | CWE-1336 | 1 | 1 |
| cvefixes_python | python | CWE-134 | 1 | 1 |
| cvefixes_python | python | CWE-377 | 1 | 1 |
| cvefixes_python | python | CWE-415 | 1 | 1 |
| cvefixes_python | python | CWE-440 | 1 | 1 |
| cvefixes_python | python | CWE-475 | 1 | 1 |
| cvefixes_python | python | CWE-534 | 1 | 1 |
| cvefixes_python | python | CWE-620 | 1 | 1 |
| cvefixes_python | python | CWE-707 | 1 | 1 |
| cvefixes_python | python | CWE-754 | 1 | 1 |
| cvefixes_python | python | CWE-80 | 1 | 1 |
| cvefixes_python | python | CWE-824 | 1 | 1 |
| cvefixes_python | python | CWE-98 | 1 | 1 |
| megavul | cpp | CWE-119 | 29,514 | 1,605 |
| megavul | cpp | CWE-787 | 29,116 | 1,482 |
| megavul | cpp | CWE-125 | 25,482 | 1,398 |
| megavul | cpp | <MISSING> | 27,852 | 1,346 |
| megavul | cpp | CWE-476 | 28,625 | 1,282 |
| megavul | cpp | CWE-20 | 21,640 | 1,094 |
| megavul | cpp | CWE-416 | 26,779 | 994 |
| megavul | cpp | CWE-190 | 12,467 | 652 |
| megavul | cpp | CWE-200 | 13,370 | 574 |
| megavul | cpp | CWE-362 | 11,838 | 504 |
| megavul | cpp | CWE-264 | 12,576 | 468 |
| megavul | cpp | CWE-399 | 12,269 | 449 |
| megavul | cpp | CWE-120 | 7,264 | 418 |
| megavul | cpp | CWE-400 | 6,920 | 311 |
| megavul | cpp | CWE-189 | 7,038 | 310 |
| megavul | cpp | CWE-401 | 11,884 | 278 |
| megavul | cpp | CWE-617 | 4,113 | 258 |
| megavul | cpp | CWE-835 | 5,296 | 250 |
| megavul | cpp | CWE-772 | 3,653 | 183 |
| megavul | cpp | CWE-415 | 6,331 | 177 |
| megavul | cpp | CWE-369 | 2,891 | 169 |
| megavul | cpp | CWE-22 | 3,782 | 155 |
| megavul | cpp | CWE-254 | 3,193 | 129 |
| megavul | cpp | CWE-674 | 2,036 | 120 |
| megavul | cpp | CWE-122 | 2,123 | 107 |
| megavul | cpp | CWE-908 | 1,830 | 101 |
| megavul | cpp | CWE-284 | 1,780 | 94 |
| megavul | cpp | CWE-287 | 1,639 | 93 |
| megavul | cpp | CWE-59 | 1,841 | 93 |
| megavul | cpp | CWE-770 | 2,046 | 90 |
| megavul | cpp | CWE-834 | 4,293 | 87 |
| megavul | cpp | CWE-310 | 1,389 | 82 |
| megavul | cpp | CWE-269 | 1,575 | 79 |
| megavul | cpp | CWE-909 | 1,331 | 78 |
| megavul | cpp | CWE-74 | 2,411 | 73 |
| megavul | cpp | CWE-295 | 1,947 | 69 |
| megavul | cpp | CWE-667 | 1,502 | 69 |
| megavul | cpp | CWE-17 | 1,098 | 65 |
| megavul | cpp | CWE-193 | 905 | 65 |
| megavul | cpp | CWE-459 | 670 | 60 |
| megavul | cpp | CWE-78 | 1,364 | 60 |
| megavul | cpp | CWE-404 | 1,947 | 59 |
| megavul | cpp | CWE-843 | 1,109 | 58 |
| megavul | cpp | CWE-754 | 1,048 | 57 |
| megavul | cpp | CWE-79 | 967 | 57 |
| megavul | cpp | CWE-19 | 1,308 | 54 |
| megavul | cpp | CWE-732 | 825 | 52 |
| megavul | cpp | CWE-681 | 706 | 51 |
| megavul | cpp | CWE-863 | 1,277 | 46 |
| megavul | cpp | CWE-665 | 1,276 | 43 |
| megavul | cpp | CWE-252 | 527 | 42 |
| megavul | cpp | CWE-755 | 1,051 | 42 |
| megavul | cpp | CWE-89 | 1,745 | 37 |
| megavul | cpp | CWE-129 | 782 | 36 |
| megavul | cpp | CWE-668 | 854 | 35 |
| megavul | cpp | CWE-1284 | 369 | 32 |
| megavul | cpp | CWE-131 | 544 | 32 |
| megavul | cpp | CWE-203 | 735 | 32 |
| megavul | cpp | CWE-682 | 732 | 32 |
| megavul | cpp | CWE-704 | 875 | 32 |
| megavul | cpp | CWE-330 | 511 | 31 |
| megavul | cpp | CWE-367 | 1,263 | 31 |
| megavul | cpp | CWE-354 | 445 | 30 |
| megavul | cpp | CWE-862 | 475 | 29 |
| megavul | cpp | CWE-134 | 1,056 | 28 |
| megavul | cpp | CWE-763 | 445 | 28 |
| megavul | cpp | CWE-191 | 965 | 27 |
| megavul | cpp | CWE-276 | 674 | 24 |
| megavul | cpp | CWE-327 | 333 | 24 |
| megavul | cpp | CWE-824 | 514 | 24 |
| megavul | cpp | CWE-121 | 233 | 23 |
| megavul | cpp | CWE-502 | 113 | 22 |
| megavul | cpp | CWE-77 | 491 | 22 |
| megavul | cpp | CWE-212 | 290 | 20 |
| megavul | cpp | CWE-345 | 197 | 20 |
| megavul | cpp | CWE-697 | 239 | 20 |
| megavul | cpp | CWE-436 | 286 | 19 |
| megavul | cpp | CWE-444 | 186 | 18 |
| megavul | cpp | CWE-611 | 339 | 18 |
| megavul | cpp | CWE-662 | 111 | 18 |
| megavul | cpp | CWE-776 | 92 | 18 |
| megavul | cpp | CWE-94 | 411 | 18 |
| megavul | cpp | CWE-326 | 156 | 17 |
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
| megavul | cpp | CWE-670 | 172 | 8 |
| megavul | cpp | CWE-913 | 46 | 8 |
| megavul | cpp | CWE-388 | 275 | 7 |
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
| megavul | cpp | CWE-285 | 204 | 4 |
| megavul | cpp | CWE-338 | 21 | 4 |
| megavul | cpp | CWE-427 | 360 | 4 |
| megavul | cpp | CWE-522 | 67 | 4 |
| megavul | cpp | CWE-626 | 55 | 4 |
| megavul | cpp | CWE-88 | 28 | 4 |
| megavul | cpp | CWE-118 | 32 | 3 |
| megavul | cpp | CWE-1188 | 260 | 3 |
| megavul | cpp | CWE-172 | 24 | 3 |
| megavul | cpp | CWE-184 | 3 | 3 |
| megavul | cpp | CWE-229 | 113 | 3 |
| megavul | cpp | CWE-320 | 31 | 3 |
| megavul | cpp | CWE-325 | 38 | 3 |
| megavul | cpp | CWE-494 | 48 | 3 |
| megavul | cpp | CWE-706 | 146 | 3 |
| megavul | cpp | CWE-707 | 16 | 3 |
| megavul | cpp | CWE-113 | 17 | 2 |
| megavul | cpp | CWE-1333 | 3 | 2 |
| megavul | cpp | CWE-255 | 9 | 2 |
| megavul | cpp | CWE-307 | 138 | 2 |
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
| megavul | cpp | CWE-311 | 74 | 0 |
| megavul | cpp | CWE-358 | 65 | 0 |
| megavul | cpp | CWE-788 | 22 | 0 |
| zenodo_python | python | CWE-352 | 116 | 116 |
| zenodo_python | python | CWE-94 | 54 | 54 |
| zenodo_python | python | <MISSING> | 47 | 47 |
| zenodo_python | python | CWE-79 | 47 | 47 |
| zenodo_python | python | CWE-20 | 31 | 31 |
| zenodo_python | python | CWE-400 | 30 | 30 |
| zenodo_python | python | CWE-693 | 28 | 28 |
| zenodo_python | python | CWE-22 | 26 | 26 |
| zenodo_python | python | CWE-918 | 26 | 26 |
| zenodo_python | python | CWE-601 | 21 | 21 |
| zenodo_python | python | CWE-613 | 21 | 21 |
| zenodo_python | python | CWE-444 | 18 | 18 |
| zenodo_python | python | CWE-200 | 16 | 16 |
| zenodo_python | python | CWE-269 | 16 | 16 |
| zenodo_python | python | CWE-209 | 15 | 15 |
| zenodo_python | python | CWE-502 | 13 | 13 |
| zenodo_python | python | CWE-74 | 12 | 12 |
| zenodo_python | python | CWE-770 | 12 | 12 |
| zenodo_python | python | CWE-264 | 11 | 11 |
| zenodo_python | python | CWE-287 | 11 | 11 |
| zenodo_python | python | CWE-59 | 10 | 10 |
| zenodo_python | python | CWE-203 | 8 | 8 |
| zenodo_python | python | CWE-532 | 8 | 8 |
| zenodo_python | python | CWE-78 | 7 | 7 |
| zenodo_python | python | CWE-89 | 7 | 7 |
| zenodo_python | python | CWE-611 | 6 | 6 |
| zenodo_python | python | CWE-1333 | 5 | 5 |
| zenodo_python | python | CWE-295 | 5 | 5 |
| zenodo_python | python | CWE-331 | 5 | 5 |
| zenodo_python | python | CWE-359 | 5 | 5 |
| zenodo_python | python | CWE-436 | 5 | 5 |
| zenodo_python | python | CWE-21 | 4 | 4 |
| zenodo_python | python | CWE-521 | 4 | 4 |
| zenodo_python | python | CWE-755 | 4 | 4 |
| zenodo_python | python | CWE-863 | 4 | 4 |
| zenodo_python | python | CWE-125 | 3 | 3 |
| zenodo_python | python | CWE-306 | 3 | 3 |
| zenodo_python | python | CWE-326 | 3 | 3 |
| zenodo_python | python | CWE-113 | 2 | 2 |
| zenodo_python | python | CWE-19 | 2 | 2 |
| zenodo_python | python | CWE-212 | 2 | 2 |
| zenodo_python | python | CWE-29 | 2 | 2 |
| zenodo_python | python | CWE-330 | 2 | 2 |
| zenodo_python | python | CWE-347 | 2 | 2 |
| zenodo_python | python | CWE-367 | 2 | 2 |
| zenodo_python | python | CWE-617 | 2 | 2 |
| zenodo_python | python | CWE-668 | 2 | 2 |
| zenodo_python | python | CWE-674 | 2 | 2 |
| zenodo_python | python | CWE-77 | 2 | 2 |
| zenodo_python | python | CWE-1021 | 1 | 1 |
| zenodo_python | python | CWE-116 | 1 | 1 |
| zenodo_python | python | CWE-119 | 1 | 1 |
| zenodo_python | python | CWE-190 | 1 | 1 |
| zenodo_python | python | CWE-23 | 1 | 1 |
| zenodo_python | python | CWE-255 | 1 | 1 |
| zenodo_python | python | CWE-284 | 1 | 1 |
| zenodo_python | python | CWE-290 | 1 | 1 |
| zenodo_python | python | CWE-310 | 1 | 1 |
| zenodo_python | python | CWE-311 | 1 | 1 |
| zenodo_python | python | CWE-36 | 1 | 1 |
| zenodo_python | python | CWE-362 | 1 | 1 |
| zenodo_python | python | CWE-377 | 1 | 1 |
| zenodo_python | python | CWE-662 | 1 | 1 |
| zenodo_python | python | CWE-670 | 1 | 1 |
| zenodo_python | python | CWE-684 | 1 | 1 |
| zenodo_python | python | CWE-697 | 1 | 1 |
| zenodo_python | python | CWE-75 | 1 | 1 |
| zenodo_python | python | CWE-789 | 1 | 1 |
| zenodo_python | python | CWE-80 | 1 | 1 |
| zenodo_python | python | CWE-824 | 1 | 1 |

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

## Expected datasets and layout-insensitive matches

- Datasets expected by `dedupe.PRIORITY_ORDER` with no `*_deduped.parquet`: **none**.
- Python code without line breaks that still matches exactly one laid-out copy: **0** (expected 0; anything else means dedupe missed a duplicate).
- Python code without line breaks that matches several different laid-out versions (left alone on purpose): 1.

## Label conflicts and limitations

- Remaining cross-dataset normalized-hash label-conflict groups: **0**.
- Hashes use the same language-prefix, normalizers and SHA-256 implementation as `dedupe.py`.
- CWE and CVE arrays decoded from Parquet are converted to Python lists only for `schema.validate()`.
- No CVE/commit/project group-aware splitting or semantic-clone detection is performed.
- A PRELIMINARY PASS only covers schema, empty-code and duplicate-hash checks.
- This audit does not validate that commit SHAs correspond to security fixes or that CWE labels are correct.
- No dataset files are modified.
