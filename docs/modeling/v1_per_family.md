# V1 per-family results (test split)

Run: `xgboost_codebert_v1_20261029_124819`. Only rows with label = 1 are scored.
Not final: split QA is not green yet (see `docs/datasets/audits/split_qa.md`, D33).
`reliable = no` means fewer than 3 commits for that CWE, so do not quote its numbers.
A CWE is listed if it is the true CWE of a test row, or if the model predicted it.
`support = 0` means the model predicted that CWE, but no test row has it.

## cpp

| family | support | commits | reliable | precision | recall | f1 |
| --- | --- | --- | --- | --- | --- | --- |
| memory_safety | 1074 | 621 | yes | 0.746 | 0.425 | 0.541 |
| resource_availability | 183 | 98 | yes | 0.105 | 0.120 | 0.112 |
| input_injection | 170 | 71 | yes | 0.119 | 0.094 | 0.105 |
| access_control | 105 | 45 | yes | 0.143 | 0.133 | 0.138 |
| data_crypto | 93 | 40 | yes | 0.100 | 0.118 | 0.108 |
| error_configuration | 61 | 33 | yes | 0.025 | 0.016 | 0.020 |
| path_network | 40 | 27 | yes | 0.070 | 0.475 | 0.123 |
| concurrency_state | 27 | 10 | yes | 0.080 | 0.407 | 0.133 |
| other | 6 | 2 | no | 0.014 | 0.333 | 0.026 |

## python

| family | support | commits | reliable | precision | recall | f1 |
| --- | --- | --- | --- | --- | --- | --- |
| input_injection | 145 | 32 | yes | 0.528 | 0.386 | 0.446 |
| path_network | 84 | 20 | yes | 0.410 | 0.571 | 0.478 |
| access_control | 74 | 17 | yes | 0.390 | 0.216 | 0.278 |
| data_crypto | 54 | 11 | yes | 0.175 | 0.185 | 0.180 |
| concurrency_state | 11 | 2 | no | 0.000 | 0.000 | 0.000 |
| error_configuration | 8 | 7 | yes | 0.000 | 0.000 | 0.000 |
| resource_availability | 1 | 1 | no | 0.000 | 0.000 | 0.000 |
| memory_safety | 0 | 0 | no | 0.000 | 0.000 | 0.000 |
| other | 0 | 0 | no | 0.000 | 0.000 | 0.000 |
