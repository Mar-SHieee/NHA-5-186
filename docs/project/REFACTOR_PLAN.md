# SHIELD: Folder Refactor Plan (handoff document)

> **Purpose.** Make the repository navigable by someone who never worked on it: every folder has one clear job,
> every file sits in the folder that matches its job, and every folder explains itself in a `README.md`.
> **Paste this file into a new chat** and say "we are at step N of the refactor" to continue.
> **Status: Phases 0-4 DONE in the sandbox copy (verified). Phase 5 (apply to the real repo) is NEXT.**
> Date: 2026-10-26 · Tool: `apply_layout.py` + `layout_docs.py` (re-runnable, idempotent) · Baseline commit: `82a9240`

---

## 0. TL;DR for the next chat

| Question | Answer |
| --- | --- |
| What changed? | 132 files moved (git-detected renames, history kept), 1 deleted, 37 added (folder READMEs, `paths.py`, `__init__.py`, `tests/test_layout.py`), 13 edited. |
| Is behaviour unchanged? | Yes. 598 tests passed / 2 skipped **before** and **after**, ruff and format clean. 3 torch test files cannot run in the sandbox (no torch); a new static test covers their imports. |
| What is left? | Apply it to the real GitHub repo (Phase 5), then update `SHIELD_PLAN.md` (Phase 6). |
| Biggest risk | Teammates' open branches touch the old paths, so a big-bang move creates merge conflicts. See Phase 5. |

---

## 1. The new layout (what a newcomer sees)

```text
SHIELD/
├── README.md · SHIELD_PLAN.md · pyproject.toml · .gitignore ...
├── .github/        CI + PR template
├── docker/joern/   pinned Joern image + smoke test
├── requirements/   pinned GPU torch wheel
│
├── shield_core/    THE LIBRARY (everything importable)
│   ├── interface.py · cli.py · tracking.py · paths.py(new)
│   ├── languages/        registry.py + python/cpp/java .yaml        (was top-level languages/)
│   ├── datasets/
│   │   ├── schema.py · project_names.py
│   │   ├── cvefixes_build/   convert_db + table extraction          (was loose + inside *_loaders/)
│   │   ├── loaders/          one loader per source (5)              (was c_cpp_loaders/ + python_loaders/)
│   │   ├── samples/          20-row samples for spikes
│   │   └── pipeline/         dedupe → project_normalization → merge → splits
│   ├── extraction/       graph_extractor · joern_extractor · cache
│   ├── taint/            joern_queries
│   ├── embeddings/       embedder · node_embeddings                 (was models/embedding/ + extraction/)
│   ├── models/           registry.py + models.yaml
│   ├── fix/templates/    sql · command · path · base · strings · astutil   (was models/fixgen/)
│   ├── verify/           pysource · pattern_checks · evidence
│   └── eval/             metrics.py                                 (was top-level eval/)
├── scripts/        runs, grouped by purpose
│   ├── data_audit/ embeddings/ graphs/(+inspect_export/) spikes/{joern,taint}/ training/ tutorials/(+pyg/)
├── tests/          mirrors shield_core: interface/ languages/ models/ embeddings/ datasets/ extraction/ taint/ fix/ verify/ eval/ fixtures/
└── docs/           by topic: api/ datasets/{audits,exploration,leakage,project_names}/ graphs/ taint/ fixes/ modeling/ project/
```

### Design rules (the "why")

| # | Rule | Reason |
| --- | --- | --- |
| R1 | **One importable root.** `languages/` and `eval/` moved inside `shield_core/`. | The old top-level `languages/` had no `__init__.py` and needed three special entries in `pyproject.toml`. The plan (Section 4.3) already placed them under `shield_core/`. |
| R2 | **Folders are named for the job, not the history.** `fixgen`→`fix/templates`, `c_cpp_loaders`+`python_loaders`→`loaders`, `codebert_embeddings_analysis`→`embeddings`, `joern_spike_audit`→`spikes/joern`, `pyg-gnn`→`tutorials/pyg`. | A hyphenated folder cannot be imported; two loader folders split one concept by language although CVEfixes spans both. |
| R3 | **Datasets folder follows the data chain**: `cvefixes_build/` → `loaders/` → `pipeline/`. | Order of folders = order of commands. |
| R4 | **`scripts/` is grouped by purpose**; 20 loose files became 6 folders. | Newcomers could not tell audits from training from spikes. |
| R5 | **`tests/` mirrors `shield_core/`.** | "Where is the test for X?" has one answer. |
| R6 | **`docs/` is grouped by topic.** 35 flat files became 9 folders. | Generated reports, design notes and CSVs were mixed. |
| R7 | **No `__file__` arithmetic.** New `shield_core/paths.py` owns the repo root and every data/docs folder. | Moving a file silently changed `parents[N]`. This also fixed a latent bug: the Joern spike scripts used `parents[1]` (= `scripts/`, not the repo root). |
| R8 | **Every code folder has a README.md**, enforced by a test. | The user's goal: anyone can open a folder and know what is in it. |
| R9 | **Never name a folder `data/` below the root.** | `.gitignore` has an unanchored `data/` rule that would silently untrack it (this is why `docs/data/` was rejected for `docs/datasets/`). |

---

## 2. Status checklist

### Phase 0: Analysis (DONE)
- [x] Baseline: 598 tests pass, 2 skipped (torch tests excluded); ruff + format clean
- [x] Mapped imports (absolute **and relative**), `__file__`-depth path computations, hard-coded `docs/` and `data/` strings
- [x] **Found a pre-existing bug:** `.gitignore` has an unanchored `sample*/` rule, so `docker/joern/smoke/samples/` (a.c, a.cpp, a.py used by the Joern smoke test) was **never committed**. A fresh clone cannot run the Docker smoke test. The refactor anchors the rule to `/sample*/` and the files become trackable (Phase 5: `git add` them)
- [x] Found traps: unanchored `data/` in `.gitignore`; relative imports in `merge.py`/`splits.py`; wrong `parents[1]` in Joern spike scripts; `train_v1.py` pointing at a manifest path that `splits.py` never writes

### Phase 1: Design (DONE)
- [x] Target tree and rules R1-R9 above
- [x] Old→new map encoded in `apply_layout.py` (`DIR_MAP`, `FILE_MAP`); full table in Appendix A

### Phase 2: Mechanical move (DONE)
- [x] 131 files moved (`git mv`; one duplicate empty `__init__.py` merged); 1 stale empty template deleted (`docs/long_function_strategy.md`)
- [x] 78 files had old paths / module names rewritten automatically (code, docs, YAML, TOML)
- [x] Generated junk removed from the tree (`shield_core.egg-info/`, `scripts/data/`)

### Phase 3: Code fixes the move required (DONE)
- [x] `shield_core/paths.py` created; 13 modules switched from depth-counting to `paths` constants
- [x] `merge.py` / `splits.py`: relative imports replaced by absolute imports
- [x] Generated reports redirected to the new docs folders (`dedupe_report`, `dataset_audit`, manifest, project-name CSVs, explorations, `joern_spike.md`)
- [x] `.gitignore`: `sample*/` → `/sample*/` (otherwise the new `datasets/samples/README.md` and `__init__.py` would be silently ignored, and CI on a fresh clone would fail)
- [x] `train_v1.py`: manifest path corrected; output moved from `artifacts/` to `model_artifacts/train_runs/` (and `.gitignore` extended)
- [x] `pyproject.toml`: package list, package-data (`languages/*.yaml`), ruff `known-first-party`
- [x] Over-long docstring lines reflowed (new paths are longer; ruff E501)

### Phase 4: Self-documentation and guards (DONE)
- [x] 28 folder `README.md` files + `docs/README.md` + `tests/README.md`
- [x] `tests/test_layout.py`: no source file is silently git-ignored, every first-party import resolves (no torch needed), submodule imports exist, every code folder has `__init__.py` and `README.md`, tracked path constants exist, every README path exists. Mutation-tested (a deliberately broken import fails it)
- [x] Root `README.md` updated: §5 tree + "where does my file go?", §6, §8 catalog rows, §8.10, §19, §17 gap #4, auto-rewritten commands (`python -m shield_core.datasets.pipeline.dedupe` etc.)

**Verification results (sandbox):** ruff clean · format clean · `pytest` 598 passed + layout guards, 658 collected (3 files need torch) · git sees 132 renames.

### Phase 5: Apply to the real repo (NEXT, your action)
- [ ] **Freeze:** announce a 1-hour window; ask everyone to merge or rebase open PRs first (open branches touching moved files will conflict)
- [ ] `git checkout main && git pull && git checkout -b refactor/folder-layout`
- [ ] Copy `apply_layout.py` and `layout_docs.py` to a folder **outside** the repo (or at least do not commit them)
- [ ] From the repo root: `python /path/to/apply_layout.py --dry-run`, read the output, then run without `--dry-run`
- [ ] `ruff check --fix . && ruff format .`
- [ ] Replace `README.md` with the updated one; add `docs/project/REFACTOR_PLAN.md` (this file)
- [ ] `pytest` (on a machine **with torch**, so the 3 embedding test files run too) and `pre-commit run --all-files`
- [ ] `git status` should now show `docker/joern/smoke/samples/` as new files: `git add` them (they were never committed before)
- [ ] Push, open PR titled `REFACTOR: folder layout (no behaviour change)`, wait for CI green, merge
- [ ] Teammates: `git fetch && git rebase origin/main`; any conflict on a moved file = take your edit and re-apply it at the new path (`git log --follow` shows history)
- [ ] Re-install once: `pip install -e ".[dev]"` (package list changed)
- [ ] Also run the pipeline commands once on a real checkout; the sandbox had no datasets, so `python -m shield_core.datasets.pipeline.dedupe` / `.merge` / `.splits` were verified by tests and static analysis, **not by a real data run**

### Phase 6: Plan and docs follow-up (AFTER merge)
- [ ] `SHIELD_PLAN.md`: replace Section 4.3 layout and the "Layout as built" note; add a Decisions Log row **D40** (layout refactor, R1-R9) and a Changelog line; update path mentions in Week 2 tasks (e.g. `scripts/split_qa.py` → `scripts/data_audit/split_qa.py`, `shield_core/eval/` instead of top-level `eval/`, `docs/datasets/data_sources.md` for W2-P1-04)
- [ ] Commit `SHIELD_PLAN.md` to the repo root (already owed as W2-P5-05)
- [ ] Tell other chats: "folders were reorganized; see `docs/project/REFACTOR_PLAN.md` Appendix A for old→new paths"

### Phase 7: Optional follow-ups (NOT done; deliberately out of scope for a no-behaviour-change PR)
- [ ] Convert the remaining depth-based roots (loaders use `parents[3]`, which still works because their depth did not change) to `shield_core.paths`; `models/registry.py` `DEFAULT_ARTIFACT_DIR` too
- [ ] Promote library logic out of `scripts/`: `graphs/graphml_to_pyg.py` (task W2-P2-01), `embeddings/long_embedding.py` + `long_function_analysis.py` (imported by `train_v1.py` and tests)
- [ ] Untangle `fix/templates` → `verify/pysource.py` (shared editing helper lives in `verify/`)
- [ ] `.gitignore`: anchor `data/` as `/data/`; remove the stray line `test`
- [ ] README numbers that are stale for reasons unrelated to the refactor (dataset counts in §14, "Week 2 in progress" status) are unchanged: review them at the Gate G2 update

---

## 3. How to re-run or adapt the refactor

```bash
cd <repo root>
python /path/to/apply_layout.py --dry-run     # list moves + rewrites, change nothing
python /path/to/apply_layout.py               # apply (git mv when inside a git repo)
ruff check --fix . && ruff format .           # re-sort rewritten imports
pytest
```

* **Idempotent:** a second run finds nothing to move. Edits assert their target text and stop loudly if the file drifted.
* **To change a destination:** edit `DIR_MAP` / `FILE_MAP` at the top of `apply_layout.py`; text references follow automatically.
* **To add a folder README:** add an entry to `FOLDERS` in `layout_docs.py` (the parent's table updates itself).
* **If a teammate added a new file in an old folder** before you run it: it moves with its folder (`DIR_MAP`); a new *loose* file in `scripts/` or `docs/` stays where it is: add it to `FILE_MAP`.

## 4. Lessons recorded (so they are not rediscovered)

1. A grep for `from x import` misses **relative imports**; the test run caught two broken ones. Always run the suite, not just grep.
2. `__file__`-relative roots are the main hidden coupling when moving files. Prefer destinations at the same depth, and otherwise use `paths.py`.
3. Multi-line text replacements must tolerate CRLF (many files here are CRLF); the script reads/writes with `newline=""`.
4. A rewriter must never touch a document whose job is to record the *old* paths (this plan's Appendix A is excluded for that reason).
5. `.gitignore` rules without a leading `/` match at any depth. Before naming a folder, check `git check-ignore -v <path>`; `tests/test_layout.py` now fails if a source file is ignored.
6. Text that appears in several tables (a row like `| \`tracking.py\` |`) must be replaced inside one section, never globally.

---

## Appendix A: old path → new path (132 renames, generated from git)

| Old | New |
| --- | --- |
| `docs/api_contract.md` | `docs/api/api_contract.md` |
| `docs/bigvul_exploration.md` | `docs/datasets/exploration/bigvul_exploration.md` |
| `docs/c_cpp_cwe_data_leakage_high_risk.md` | `docs/datasets/leakage/c_cpp_cwe_data_leakage_high_risk.md` |
| `docs/cpp_cwe_commit_audit.csv` | `docs/datasets/audits/cpp_cwe_commit_audit.csv` |
| `docs/cvefixes_cpp_absent_commits.md` | `docs/datasets/exploration/cvefixes_cpp_absent_commits.md` |
| `docs/cvefixes_cpp_exploration.md` | `docs/datasets/exploration/cvefixes_cpp_exploration.md` |
| `docs/cvefixes_python_absent_commits.md` | `docs/datasets/exploration/cvefixes_python_absent_commits.md` |
| `docs/cvefixes_python_exploration.md` | `docs/datasets/exploration/cvefixes_python_exploration.md` |
| `docs/cwe_lists_python_cpp.md` | `docs/datasets/audits/cwe_lists_python_cpp.md` |
| `docs/dataset_audit.md` | `docs/datasets/audits/dataset_audit.md` |
| `docs/dataset_manifest_v0.json` | `docs/datasets/audits/dataset_manifest_v0.json` |
| `docs/dedupe_report.md` | `docs/datasets/audits/dedupe_report.md` |
| `docs/fix_template_survey.md` | `docs/fixes/fix_template_survey.md` |
| `docs/fix_templates_architecture.md` | `docs/fixes/fix_templates_architecture.md` |
| `docs/fix_templates_python.md` | `docs/fixes/fix_templates_python.md` |
| `docs/graph_extractor.md` | `docs/graphs/graph_extractor.md` |
| `docs/graph_schema.md` | `docs/graphs/graph_schema.md` |
| `docs/joern_spike.md` | `docs/graphs/joern_spike.md` |
| `docs/long_function_policy.md` | `docs/modeling/long_function_policy.md` |
| `docs/megavul_exploration.md` | `docs/datasets/exploration/megavul_exploration.md` |
| `docs/normalized_name_groups.csv` | `docs/datasets/project_names/normalized_name_groups.csv` |
| `docs/project_alias_ambiguous.csv` | `docs/datasets/project_names/project_alias_ambiguous.csv` |
| `docs/project_alias_candidates.csv` | `docs/datasets/project_names/project_alias_candidates.csv` |
| `docs/project_alias_evidence.csv` | `docs/datasets/project_names/project_alias_evidence.csv` |
| `docs/project_alias_review.csv` | `docs/datasets/project_names/project_alias_review.csv` |
| `docs/project_aliases.json` | `docs/datasets/project_names/project_aliases.json` |
| `docs/project_name_mapping.csv` | `docs/datasets/project_names/project_name_mapping.csv` |
| `docs/project_same_repo_other_owner.csv` | `docs/datasets/project_names/project_same_repo_other_owner.csv` |
| `docs/pyg_setup.md` | `docs/graphs/pyg_setup.md` |
| `docs/python_cwe_commit_audit.csv` | `docs/datasets/audits/python_cwe_commit_audit.csv` |
| `docs/python_cwe_data_leakage_high_risk.md` | `docs/datasets/leakage/python_cwe_data_leakage_high_risk.md` |
| `docs/shared_commit_projects.csv` | `docs/datasets/project_names/shared_commit_projects.csv` |
| `docs/taint_spike.md` | `docs/taint/taint_spike.md` |
| `docs/zenodo_python_exploration.md` | `docs/datasets/exploration/zenodo_python_exploration.md` |
| `eval/__init__.py` | `scripts/data_audit/__init__.py` |
| `eval/metrics.py` | `shield_core/eval/metrics.py` |
| `languages/cpp.yaml` | `shield_core/languages/cpp.yaml` |
| `languages/java.yaml` | `shield_core/languages/java.yaml` |
| `languages/python.yaml` | `shield_core/languages/python.yaml` |
| `languages/registry.py` | `shield_core/languages/registry.py` |
| `scripts/acceptance_check.py` | `scripts/data_audit/acceptance_check.py` |
| `scripts/check_cvefixes_absent_commits.py` | `scripts/data_audit/check_cvefixes_absent_commits.py` |
| `scripts/codebert_embeddings_analysis/__init__.py` | `scripts/embeddings/__init__.py` |
| `scripts/codebert_embeddings_analysis/coverage_check.py` | `scripts/embeddings/coverage_check.py` |
| `scripts/codebert_embeddings_analysis/long_embedding.py` | `scripts/embeddings/long_embedding.py` |
| `scripts/codebert_embeddings_analysis/long_function_analysis.py` | `scripts/embeddings/long_function_analysis.py` |
| `scripts/codebert_embeddings_analysis/sanity_check.py` | `scripts/embeddings/sanity_check.py` |
| `scripts/codebert_embeddings_analysis/token_length_stats.py` | `scripts/embeddings/token_length_stats.py` |
| `scripts/demo_tracking.py` | `scripts/tutorials/demo_tracking.py` |
| `scripts/explore/__init__.py` | `scripts/graphs/__init__.py` |
| `scripts/explore/count_types.py` | `scripts/graphs/inspect_export/count_types.py` |
| `scripts/explore/dump_line.py` | `scripts/graphs/inspect_export/dump_line.py` |
| `scripts/explore/list_methods.py` | `scripts/graphs/inspect_export/list_methods.py` |
| `scripts/explore/show_edges.py` | `scripts/graphs/inspect_export/show_edges.py` |
| `scripts/explore/show_nodes.py` | `scripts/graphs/inspect_export/show_nodes.py` |
| `scripts/explore_bigvul.py` | `scripts/data_audit/explore_bigvul.py` |
| `scripts/explore_cvefixes_cpp.py` | `scripts/data_audit/explore_cvefixes_cpp.py` |
| `scripts/explore_cvefixes_python.py` | `scripts/data_audit/explore_cvefixes_python.py` |
| `scripts/explore_megavul.py` | `scripts/data_audit/explore_megavul.py` |
| `scripts/explore_zenodo_python.py` | `scripts/data_audit/explore_zenodo_python.py` |
| `scripts/filter_counts.py` | `scripts/graphs/filter_counts.py` |
| `scripts/graphml_to_pyg.py` | `scripts/graphs/graphml_to_pyg.py` |
| `scripts/joern_spike_audit/__init__.py` | `scripts/graphs/inspect_export/__init__.py` |
| `scripts/joern_spike_audit/analyze_joern_performance.py` | `scripts/spikes/joern/analyze_joern_performance.py` |
| `scripts/joern_spike_audit/audit_joern_spike.py` | `scripts/spikes/joern/audit_joern_spike.py` |
| `scripts/joern_spike_audit/run_joern_spike.py` | `scripts/spikes/joern/run_joern_spike.py` |
| `scripts/pyg-gnn/__init__.py` | `scripts/spikes/__init__.py` |
| `scripts/pyg-gnn/check_env.py` | `scripts/tutorials/pyg/check_env.py` |
| `scripts/pyg-gnn/lesson 1.py` | `scripts/tutorials/pyg/lesson1.py` |
| `scripts/pyg-gnn/lesson 2.py` | `scripts/tutorials/pyg/lesson2.py` |
| `scripts/pyg-gnn/lesson 4.py` | `scripts/tutorials/pyg/lesson4.py` |
| `scripts/pyg-gnn/lesson 5.py` | `scripts/tutorials/pyg/lesson5.py` |
| `scripts/pyg-gnn/lesson 6.py` | `scripts/tutorials/pyg/lesson6.py` |
| `scripts/pyg-gnn/lesson3.py` | `scripts/tutorials/pyg/lesson3.py` |
| `scripts/pyg-gnn/toy_gnn.py` | `scripts/tutorials/pyg/toy_gnn.py` |
| `scripts/split_qa.py` | `scripts/data_audit/split_qa.py` |
| `scripts/taint/__init__.py` | `scripts/spikes/joern/__init__.py` |
| `scripts/taint/run_taint_spike.py` | `scripts/spikes/taint/run_taint_spike.py` |
| `scripts/train_v1.py` | `scripts/training/train_v1.py` |
| `scripts/try_extractor.py` | `scripts/graphs/try_extractor.py` |
| `shield_core/datasets/c_cpp_loaders/Random_samples_20.py` | `shield_core/datasets/samples/megavul_bigvul_samples.py` |
| `shield_core/datasets/c_cpp_loaders/__init__.py` | `scripts/spikes/taint/__init__.py` |
| `shield_core/datasets/c_cpp_loaders/bigvul_loader.py` | `shield_core/datasets/loaders/bigvul_loader.py` |
| `shield_core/datasets/c_cpp_loaders/cvefixes_cpp_loaders.py` | `shield_core/datasets/loaders/cvefixes_cpp_loaders.py` |
| `shield_core/datasets/c_cpp_loaders/cvefixes_cpp_sample.py` | `shield_core/datasets/samples/cvefixes_cpp_sample.py` |
| `shield_core/datasets/c_cpp_loaders/cvefixes_cpp_tables_extraction.py` | `shield_core/datasets/cvefixes_build/cvefixes_cpp_tables_extraction.py` |
| `shield_core/datasets/c_cpp_loaders/megavul_loader.py` | `shield_core/datasets/loaders/megavul_loader.py` |
| `shield_core/datasets/cvefixes_convert_db.py` | `shield_core/datasets/cvefixes_build/cvefixes_convert_db.py` |
| `shield_core/datasets/dedupe.py` | `shield_core/datasets/pipeline/dedupe.py` |
| `shield_core/datasets/merge.py` | `shield_core/datasets/pipeline/merge.py` |
| `shield_core/datasets/project_normalization.py` | `shield_core/datasets/pipeline/project_normalization.py` |
| `shield_core/datasets/python_loaders/__init__.py` | `scripts/training/__init__.py` |
| `shield_core/datasets/python_loaders/cvefixes_python_loaders.py` | `shield_core/datasets/loaders/cvefixes_python_loaders.py` |
| `shield_core/datasets/python_loaders/cvefixes_python_sample.py` | `shield_core/datasets/samples/cvefixes_python_sample.py` |
| `shield_core/datasets/python_loaders/cvefixes_python_tables_extraction.py` | `shield_core/datasets/cvefixes_build/cvefixes_python_tables_extraction.py` |
| `shield_core/datasets/python_loaders/zenodo_python_loader.py` | `shield_core/datasets/loaders/zenodo_python_loader.py` |
| `shield_core/datasets/splits.py` | `shield_core/datasets/pipeline/splits.py` |
| `shield_core/extraction/node_embeddings.py` | `shield_core/embeddings/node_embeddings.py` |
| `shield_core/models/embedding/__init__.py` | `scripts/tutorials/__init__.py` |
| `shield_core/models/embedding/embedder.py` | `shield_core/embeddings/embedder.py` |
| `shield_core/models/fixgen/__init__.py` | `shield_core/fix/templates/__init__.py` |
| `shield_core/models/fixgen/astutil.py` | `shield_core/fix/templates/astutil.py` |
| `shield_core/models/fixgen/base.py` | `shield_core/fix/templates/base.py` |
| `shield_core/models/fixgen/command.py` | `shield_core/fix/templates/command.py` |
| `shield_core/models/fixgen/path.py` | `shield_core/fix/templates/path.py` |
| `shield_core/models/fixgen/sql.py` | `shield_core/fix/templates/sql.py` |
| `shield_core/models/fixgen/strings.py` | `shield_core/fix/templates/strings.py` |
| `tests/test_bigvul_loader.py` | `tests/datasets/test_bigvul_loader.py` |
| `tests/test_cli.py` | `tests/interface/test_cli.py` |
| `tests/test_contract.py` | `tests/interface/test_contract.py` |
| `tests/test_cvefixes_cpp_loaders.py` | `tests/datasets/test_cvefixes_cpp_loaders.py` |
| `tests/test_cvefixes_python_loader.py` | `tests/datasets/test_cvefixes_python_loader.py` |
| `tests/test_dedupe_overlap.py` | `tests/datasets/test_dedupe_overlap.py` |
| `tests/test_embedder.py` | `tests/embeddings/test_embedder.py` |
| `tests/test_evidence.py` | `tests/verify/test_evidence.py` |
| `tests/test_fix_template_command.py` | `tests/fix/test_fix_template_command.py` |
| `tests/test_fix_template_path.py` | `tests/fix/test_fix_template_path.py` |
| `tests/test_fix_template_sql.py` | `tests/fix/test_fix_template_sql.py` |
| `tests/test_graph_cache.py` | `tests/extraction/test_graph_cache.py` |
| `tests/test_interface.py` | `tests/interface/test_interface.py` |
| `tests/test_loaders.py` | `tests/datasets/test_loaders.py` |
| `tests/test_long_embedding.py` | `tests/embeddings/test_long_embedding.py` |
| `tests/test_megavul.py` | `tests/datasets/test_megavul.py` |
| `tests/test_metrics.py` | `tests/eval/test_metrics.py` |
| `tests/test_model_registry.py` | `tests/models/test_model_registry.py` |
| `tests/test_n_embedder.py` | `tests/embeddings/test_node_embeddings.py` |
| `tests/test_pattern_checks.py` | `tests/verify/test_pattern_checks.py` |
| `tests/test_project_normalizer.py` | `tests/datasets/test_project_normalizer.py` |
| `tests/test_registry.py` | `tests/languages/test_registry.py` |
| `tests/test_schema.py` | `tests/datasets/test_schema.py` |
| `tests/test_splits.py` | `tests/datasets/test_splits.py` |
| `tests/test_taint_queries.py` | `tests/taint/test_taint_queries.py` |

Also deleted: `docs/long_function_strategy.md` (empty template). Also created: `shield_core/paths.py`, `tests/test_layout.py`, `docs/README.md`, `tests/README.md`, 28 folder `README.md` files, new `__init__.py` files.
