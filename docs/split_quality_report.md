# SHIELD Dataset Split Quality Audit

## 1. Dataset integrity
- Merged dataset rows: **461,261**
- Total rows across split files: **461,261**
- Row-count difference: **0**
- Row-count check: **PASS**

## 2. Split sizes and label distribution

| Split | Rows | Actual % | Target % | Deviation (pp) | Label 0 | Label 1 |
|---|---:|---:|---:|---:|---:|---:|
| train | 341,640 | 74.07% | 70% | +4.07 | 321,134 | 20,506 |
| val | 39,808 | 8.63% | 10% | -1.37 | 37,300 | 2,508 |
| test | 39,928 | 8.66% | 10% | -1.34 | 37,478 | 2,450 |
| holdout | 39,885 | 8.65% | 10% | -1.35 | 37,425 | 2,460 |

- Ratio check (maximum deviation of 2 percentage points): **REVIEW**

## 3. Label and dataset composition

### Distribution by `language`

| language   |   train |   val |   test |   holdout |
|:-----------|--------:|------:|-------:|----------:|
| cpp        |  337684 | 39033 |  39070 |     39005 |
| python     |    3956 |   775 |    858 |       880 |

### Distribution by `source`

| source                 |   train |   val |   test |   holdout |
|:-----------------------|--------:|------:|-------:|----------:|
| megavul                |  236123 | 32894 |  34670 |     33087 |
| bigvul                 |  101561 |  6139 |   4400 |      5918 |
| cvefixes_python        |    2759 |   600 |    680 |       524 |
| zenodo_13870382_python |    1197 |   175 |    178 |       356 |

## 4. Assignment integrity

- Duplicate row assignments: **0**
- Missing row IDs: **0**
- Unexpected row IDs: **0**

### Group, project, and commit leakage

- `group_key` values appearing in multiple splits: **0**
- `project_key` values appearing in multiple splits: **0**
- `commit_key` values appearing in multiple splits: **0**
- Holdout rows with unknown project: **0**

## 5. CVE leakage

- Distinct CVEs found: **10,062**
- CVEs appearing in multiple splits: **269**
- Example CVEs: `['CVE-2008-1897', 'CVE-2011-3211', 'CVE-2011-4104', 'CVE-2011-4312', 'CVE-2011-4596', 'CVE-2012-2101', 'CVE-2012-2144', 'CVE-2012-2417', 'CVE-2012-2654', 'CVE-2012-3360']`
- Note: CVE overlap is a diagnostic finding, not automatically a project/commit leakage failure.

## 6. CWE distribution

- Distinct CWE IDs: **196**

### CWEs with the largest split-share deviations

| CWE | Total | Train % | Val % | Test % | Holdout % |
|---|---:|---:|---:|---:|---:|
| CWE-98 | 1 | 100.0% | 0.0% | 0.0% | 0.0% |
| CWE-943 | 1 | 100.0% | 0.0% | 0.0% | 0.0% |
| CWE-924 | 2 | 100.0% | 0.0% | 0.0% | 0.0% |
| CWE-921 | 6 | 100.0% | 0.0% | 0.0% | 0.0% |
| CWE-913 | 8 | 100.0% | 0.0% | 0.0% | 0.0% |
| CWE-911 | 7 | 100.0% | 0.0% | 0.0% | 0.0% |
| CWE-90 | 7 | 100.0% | 0.0% | 0.0% | 0.0% |
| CWE-838 | 2 | 100.0% | 0.0% | 0.0% | 0.0% |
| CWE-823 | 5 | 100.0% | 0.0% | 0.0% | 0.0% |
| CWE-80 | 2 | 100.0% | 0.0% | 0.0% | 0.0% |
| CWE-789 | 5 | 100.0% | 0.0% | 0.0% | 0.0% |
| CWE-788 | 1 | 100.0% | 0.0% | 0.0% | 0.0% |
| CWE-762 | 2 | 100.0% | 0.0% | 0.0% | 0.0% |
| CWE-75 | 11 | 100.0% | 0.0% | 0.0% | 0.0% |
| CWE-706 | 3 | 100.0% | 0.0% | 0.0% | 0.0% |
| CWE-680 | 5 | 100.0% | 0.0% | 0.0% | 0.0% |
| CWE-664 | 1 | 100.0% | 0.0% | 0.0% | 0.0% |
| CWE-640 | 2 | 100.0% | 0.0% | 0.0% | 0.0% |
| CWE-639 | 2 | 100.0% | 0.0% | 0.0% | 0.0% |
| CWE-628 | 1 | 100.0% | 0.0% | 0.0% | 0.0% |

CWE distributions are multilabel: a row may contribute to multiple CWE categories. Rare CWEs may not be present in every split because projects and commits must remain grouped.

## 7. Exact code overlap across splits

- Unique normalized code strings shared by train and val: **58**
- Unique normalized code strings shared by train and test: **25**
- Unique normalized code strings shared by train and holdout: **124**
- Unique normalized code strings shared by val and test: **82**
- Unique normalized code strings shared by val and holdout: **59**
- Unique normalized code strings shared by test and holdout: **58**

Note: exact code overlap is an additional diagnostic. It does not by itself establish leakage because identical code can occur with different project, commit, or vulnerability metadata.

## 8. Manifest summary

- Manifest version: **v0.2**
- Task: **W2-P1-01**
- Recorded rows: **461261**
- Recorded split method: **project-disjoint connected components, greedy + local search (multilabel CWE balance)**
- Recorded validation passed: **True**
- Recorded CWE balance: `{'cwes': 197, 'balanced': 61, 'unavoidable': 135, 'residual': 1}`
