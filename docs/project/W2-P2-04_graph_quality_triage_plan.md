# W2-P2-04: Joern graph-quality triage (closes condition C3)

STATUS: DONE

> **Single source of truth for this task.** Any chat or person can continue from here.
> Repo path when committed: `docs/project/W2-P2-04_graph_quality_triage_plan.md`.
> Task id in the team plan: **W2-P2-04** (P2 = Eyad, reviewer P1 = Hatem, URGENT, planned 2 h, **Day 2 deadline**).
> Legend: `[ ]` todo · `[~]` in progress · `[x]` done · `[—]` dropped/moved (write why).

---

## 0. RESUME PROTOCOL (read this first if you are a new chat)

1. Read this whole file, then **Section 5 (STATE)**. It says which box was ticked last and what was in progress.
2. Verify reality before trusting the boxes (run from the repo root):
   - `git status` and `git log --oneline -15` (look for commits starting `W2-P2-04:`).
   - `ls scripts/spikes/joern/` (do `triage_core.py` / `triage_joern_spike.py` exist?) and `ls data/interim/joern_triage/`.
   - `ls data/interim/joern_spike_full/ | head` and `ls data/interim/joern_spike_audit.csv` (the spike evidence must exist, see Phase 0).
   - `pytest tests/spikes -q`, `ruff check . && ruff format --check .`, `docker image ls shield-joern`.
3. If the repo contradicts a ticked box, **untick it** and write one line in Section 9 (Handoff log).
4. Continue at the **first unticked box**. Do not redo ticked work.
5. **Working agreement with the user (Eyad):** implement **one step at a time**. At each *REVIEW GATE*: show the diff, explain it
   briefly and precisely, run the tests, and **wait for the user's OK**. Where a step needs the user's machine (Docker, the real
   `data/` folder) say exactly which command to run and what output to paste back. Never invent numbers: every figure in a document
   must come from a file or command output pasted into the chat.
6. After every finished step: tick its box, update Section 5 (STATE), append one line to Section 9.
7. The task is only finished when **Phase 8 is ticked and Phase 9 (professor explanation) has been delivered in the chat.**

---

## 1. What the task is, in one page

**Question to answer:** *Are the Joern graphs good enough to train a GNN on? Per language (Python, C, C++): GO or NO-GO, and why.*

**Where the question comes from.** The Week-1 Joern spike ran Joern on 60 functions (20 Python, 20 C, 20 C++). Every run
"succeeded", yet an audit found that only **47/60** have a non-empty DDG (data-dependence graph) and **30/60** are *flagged for
review* (Python **17/20**, C 8/20, C++ 5/20). The audit report itself says: "Export success is not equivalent to graph usability"
and "GO/NO-GO decisions require agreed acceptance thresholds and representative manual validation." Nobody has yet explained the
flags. The team plan records this as condition **C3** and risk "Python graph quality" (Med likelihood, High impact).

**Why it matters (who waits for this):** P1's W2-P1-02 (batch extraction) waits for the Python go/no-go (Step 11 → Step 12 →
Step 17 of the Week-2 plan). If Python graphs are poor, the plan says: V1 stays the Python primary, `ast` fallback for features
(D4), and the first GNN runs on C/C++ in Week 3.

**What the plan's task text asks for, literally:** inspect the 30 flagged samples and the 13 empty DDGs; sort causes (*expected
for the source, parser gap, UNKNOWN nodes*); choose stub **Rule A or B** for the first build; write an explicit GO/NO-GO per
language into `docs/graphs/joern_spike.md`; P1 gets a yes/no for Python extraction.

**Deliverables (all required):**

| # | Deliverable | Path |
| --- | --- | --- |
| D1 | Pure triage helpers (DOT parsing, flag replication, graph metrics, cause classifier, verdict maths, stub-rule impact) | `scripts/spikes/joern/triage_core.py` |
| D2 | CLI with three subcommands `extract`, `analyze`, `report` | `scripts/spikes/joern/triage_joern_spike.py` |
| D3 | Unit tests, no Docker needed | `tests/spikes/test_triage_core.py`, `tests/spikes/test_triage_cli.py` |
| D4 | Raw triage outputs (git-ignored) | `data/interim/joern_triage/{graph_cache/,triage.csv,summary.json,cards/}` |
| D5 | Hand-made review sheet (committed, so the evidence survives without `data/`) | `docs/graphs/joern_triage_review.csv` |
| D6 | Generated triage report with per-sample table, causes, verdicts, stub-rule evidence | `docs/graphs/joern_triage.md` |
| D7 | Addendum with the explicit GO/NO-GO per language, written **inside protected markers** | `docs/graphs/joern_spike.md` |
| D8 | Decision **D41** (verdicts + stub rule + thresholds) logged in `SHIELD_PLAN.md`; C3 closed | `SHIELD_PLAN.md` |
| D9 | Docs kept in step: root `README.md`, `docs/README.md`, `scripts/spikes/joern/README.md`, `tests/README.md` | Section 8 |
| D10 | Short message to P1 with the yes/no and the stub rule | Phase 4 (preliminary) and Phase 8 (final) |
| D11 | Professor-style explanation of every concept and file, **delivered in the chat** at the very end | Section 10 |

**Out of scope (do NOT do here):** changing `shield_core/extraction/*` (extractor/cache contract), writing the production
batch runner (W2-P1-02), the CPG→PyG converter itself (W2-P2-01; this task only *chooses* the stub rule), training anything,
extracting beyond the 60 spike samples **except** the user-requested C robustness extension in Phase 6.6, Java.
If a finding suggests a library change, **write it as a recommendation in the report**, do not make it.

---

## 2. Facts verified in the repo copy (so nobody re-discovers them)

| Fact | Where | Why it matters |
| --- | --- | --- |
| The spike ran **one `docker run` per sample** with `joern-parse /workspace/sample<ext> --output cpg.bin` (**no `--language` flag**), then `joern-export --repr cfg --format dot` and `joern-export --repr ddg --format dot`. | `scripts/spikes/joern/run_joern_spike.py` | The spike let Joern guess the frontend from the extension. **Production passes `--language pythonsrc / newc`.** The two paths may build different graphs. Hypothesis H2. |
| The production extractor exports **`--repr all --format graphml`** and parses it into a `CodeGraph` (nodes with `type/code/name/line`, edges with `type`). The GNN will consume **this** graph, including `REACHING_DEF` edges. | `shield_core/extraction/joern_extractor.py`, `graph_extractor.py`, `docs/graphs/graph_schema.md` | The audit looked at `--repr ddg` **DOT files**, a different *view* than what the model will see. "Empty DDG DOT" is not automatically "no data flow in the training graph". Hypothesis H1. |
| The audit counts `UNKNOWN` as a **substring** of the whole DOT label, case-insensitive (`"UNKNOWN" in label.upper()`). A label contains the node's code text, so a Python variable called `unknown_x`, a string literal, or Joern's `<unknownFullName>` placeholder would be counted as an UNKNOWN **node**. | `audit_joern_spike.py`, `inspect_dot_file` | Possible false positives in the 17 Python flags. Hypothesis H3. **Verify, do not assume.** |
| The audit sums DOT counts **per file**; `joern-export` writes one DOT file **per method**. A file with only a METHOD and METHOD_RETURN node is "non-empty" but carries no flow. | `inspect_graph_directory` | "DDG has nodes" is a weak test; edges of type REACHING_DEF are the real signal. |
| Review flags that exist: `MISSING_SOURCE, MISSING_OR_EMPTY_CPG, NO_CFG_DOT_FILES, CFG_HAS_NO_NODES, CFG_HAS_NO_EDGES, CFG_NO_METHOD_NODE, CFG_UNKNOWN_NODES, NO_DDG_DOT_FILES, DDG_HAS_NO_NODES, DDG_HAS_NO_EDGES`. A sample is "flagged" if the string is non-empty. | `audit_joern_spike.py` | The triage must reproduce 30 flagged / 13 empty-DDG from these rules before explaining them. |
| Spike artifacts live in **git-ignored** `data/interim/`: `joern_spike_full/<language>_<NN>/{sample.<ext>, cpg.bin, cfg_export/, ddg_export/, joern.log}`, `joern_spike_results.csv`, `joern_spike_audit.csv`, and the three `*_samples_20.parquet` files. **They were NOT in the uploaded repo zip**, so nothing below was checked against real graphs. | `run_joern_spike.py`, `.gitignore` | Every statement about causes is a *hypothesis* until Phase 3/6 prove it on the user's machine. |
| `benchmark_samples.load_spike_samples()` rebuilds the same 60 rows (ids `python_spike_001`, `c_spike_001`, `cpp_spike_001`, same order as the parquet files). Spike dir `c_07` ↔ sample `c_spike_007`. `BENCH_GROUPS` maps group → (registry language, extension): `python→(python,.py)`, `c→(cpp,.c)`, `cpp→(cpp,.cpp)`. | `benchmark_samples.py`, `benchmark_core.py` | Reuse them; do not re-read parquet by hand. Check the sha256 of each `sample.<ext>` against `Sample.sha256` to prove the rows match. |
| Phase 6 source audit found the spike/scale `c` source mapping is not actually C: `bigvul_deduped.parquet` and its 20-row spike file have `language=cpp` for every row. The C-labelled spike's `c_001` source is C++ member syntax. `cvefixes_cpp.parquet` contains 11,405 rows labeled `c` and 3,817 labeled `cpp`; its deduped output contains only `cpp`. | Local Parquet metadata inspected in Phase 6.6 | Do not call BigVul-derived scale rows a C sample or combine them with the 20 C-labelled spike rows for a C verdict. The user-requested true-C robustness set is drawn from `cvefixes_cpp.parquet` with `language == "c"`, deduplicated by normalized code hash and excluding the original spike hashes. |
| `GraphCache(root)` / `CachedGraphExtractor(JoernExtractor(docker_image="shield-joern"), cache)` already store `CodeGraph` as gzip JSON, keyed by code sha + language + extension + versions; failures raise `ExtractionError` and are never cached. | `shield_core/extraction/cache.py` | `extract` subcommand uses this; no new storage format. |
| `scripts/graphs/try_extractor.py` already prints UNKNOWN nodes' `(code, line)`. | file | Shows UNKNOWN is a real node **type** (`n.type == "UNKNOWN"`) in the GraphML path. |
| Stub rules, from `graph_schema.md` §8: **Rule A** (current) keeps wrapper methods (`<module>`, `<global>`) and external-function stubs (`strcpy`); **Rule B** drops every METHOD without a line number. "Decide with a training comparison." | `graph_schema.md` | Training comparison is Week 3. This task picks the **provisional default for the first build** from structural evidence (Phase 6.5). |
| Python flow: `tmpN` temporaries and `<metaClassAdapter>` are lowering artifacts; Python calls to undefined functions produce **no** CALL edge; C calls to external functions produce a CALL edge to a stub METHOD. | `graph_schema.md` §3, §5 | Explains why Rule A and B differ for C but not for Python. |
| Rule: `joern-export` refuses to write into an existing folder. | `graph_schema.md` §10 | Delete or use a fresh `--out` dir when re-exporting by hand. |
| **`audit_joern_spike.py` overwrites `docs/graphs/joern_spike.md` completely** every time it runs. | `main()` | Anything hand-written there is destroyed on the next audit run. Phase 7.2 protects the addendum with markers. **Do not run the audit script between Phase 7.1 and 7.2.** |
| CI: `ruff check`, `ruff format --check`, `pytest` on Python 3.12, **no Docker, no GPU**. Line length 100. Rules E, F, I, B. `tests/test_layout.py`: every code folder has `__init__.py` + `README.md`; every backticked path in the root `README.md` starting `docs/`, `scripts/`, `shield_core/`, `tests/`, `docker/` must exist; first-party imports must resolve. | `pyproject.toml`, `tests/test_layout.py` | Tests must not need Docker; README may only name files that exist. |
| `tree-sitter` is installed **only inside the Docker image**, not in `pyproject.toml`. | `docker/joern/requirements-docker.txt` | Python source analysis uses stdlib `ast`; C/C++ uses a documented regex heuristic, and the **manual review is the authority** for C/C++. |
| Paths come from `shield_core/paths.py`; add constants there, never `parents[N]`. Next free decision id is **D41** (D40 = folder refactor). `SHIELD_PLAN.md` mixes long lines; edit with exact-match replacements, do not reformat the file. | `paths.py`, `SHIELD_PLAN.md` | Follow the existing conventions. |

---

## 3. Method

### 3.1 Vocabulary (the minimum you need before touching data)

- **CPG (code property graph):** one graph per function holding several "layers" at once. Nodes = code elements (METHOD, CALL, IDENTIFIER, LITERAL, ...). Edges of many types.
- **AST** edge = syntax tree (parent → child). **CFG** edge = possible execution order. **REACHING_DEF** edge = "the value defined here may reach that use" (data flow; this is what the plan calls DFG). **DDG** (data-dependence graph) = Joern's *view* built from REACHING_DEF for export. **CALL** edge = call site → callee. **CDG** = control dependence.
- **Frontend** = the Joern parser for a language (`pythonsrc`, `newc`). **UNKNOWN node** = Joern's placeholder for a syntax construct the frontend does not understand. It is a node **type**, not just text.
- **DOT** = a text graph format; `--repr cfg|ddg --format dot` writes one file per method. **GraphML** = XML, `--repr all` writes the whole CPG in one file. The first is for looking at; the second is what production parses.
- **Triage** = sort items by cause and urgency instead of fixing blindly.

### 3.2 Hypotheses to test (written BEFORE looking at data; keep them even if wrong)

| # | Hypothesis | How it is tested | If true, consequence | Phase 3 observation |
| --- | --- | --- | --- | --- |
| H1 | Many "empty DDG" samples are a **view problem**: the `--repr ddg` DOT is empty but the GraphML has REACHING_DEF edges. | Compare per sample: DDG DOT edges vs REACHING_DEF count in the production graph. | Empty DDG is not evidence against GO. | **Contradicted:** all 13 empty-DDG samples also have zero production `REACHING_DEF`; this is not only a DOT-view problem. |
| H2 | The spike (no `--language`) and production (`--language`) frontends give **different graphs** for the same code. | Re-extract the 60 with production, compare node/edge counts per sample with the spike's. | The spike numbers do not describe the production graphs; only the production numbers count. | **Partly tested; full counts remain open:** DDG/`REACHING_DEF` presence matches sample-for-sample, but full node/edge counts were not compared. |
| H3 | Python's 17 flags come mostly from the **audit heuristic** (`UNKNOWN` substring matching code text or `<unknownFullName>`), not from real UNKNOWN nodes. | Count `type == "UNKNOWN"` nodes vs substring matches. | Most Python flags are `AUDIT_ARTIFACT`; Python is probably GO. | **Contradicted:** every audit `CFG_UNKNOWN_NODES` sample has production `UNKNOWN` nodes (Python 17/17, C 8/8, C++ 5/5). Python has 53 such nodes across 17 samples. |
| H4 | Some functions simply have **no data flow** (e.g. `return 1`, no parameters, no locals), so an empty DDG is correct. | Static estimate of expected flow from the source (`ast` for Python). Manual check. | Cause `EXPECTED_NO_FLOW`; counts as usable. | **Partly supported:** one reviewed case was expected no-flow, but many empty-DDG cases are source/context fragments. C/C++ estimates remain approximate. |
| H5 | C/C++ dataset rows are **fragments** (missing includes, macros, templates, partial bodies), so Joern misses constructs. | Look at flagged C/C++ sources and UNKNOWN nodes' code. | Cause `INPUT_FRAGMENT`; documents a limit of the data, not of Joern. | **Supported in reviewed samples:** fragments/context gaps were confirmed, including five non-usable verified-C samples. The legacy `.c` rows are metadata `cpp`. |
| H6 | Rule A vs B only matters for C/C++ (external stubs); Python has none. | Count line-less METHODs per language and the edges they carry. | Choose by Section 6.4 criteria. | **Contradicted:** Python has 217 line-less METHODs; dropping them loses 225 `REACHING_DEF` and 116 CFG edges and increases components in 13/20 samples. C++ also has line-less operator METHODs. |

### 3.3 Cause taxonomy (one primary cause per flagged sample; add a secondary in the notes if needed)

| Code | Meaning | Counts as usable? |
| --- | --- | --- |
| `AUDIT_ARTIFACT` | Flagged only by the audit's heuristics; the production graph passes all checks (e.g. "UNKNOWN" came from identifier text). | yes |
| `DOT_VIEW_ONLY` | DDG DOT is empty/edgeless but the production graph has REACHING_DEF edges (H1). | yes |
| `EXPECTED_NO_FLOW` | The function really has no data flow to show (static estimate E = 0 and a human confirmed). | yes |
| `INPUT_FRAGMENT` | The input is not a parseable whole (missing braces/includes/macros/templates); Joern output is partial because of the data. | no (but not Joern's fault; record the share) |
| `PARSER_GAP` | The source *has* data flow (E > 0) but the production graph has no REACHING_DEF, **or** UNKNOWN nodes exceed the limit. The frontend failed. | no |
| `EXTRACTION_FAILURE` | Joern/export produced nothing usable (no METHOD for the target function, no CFG edges, `ExtractionError`). | no |
| `OTHER` | Needs a sentence of explanation in the review sheet. | decide per case |

### 3.4 Pre-registered acceptance criteria (Phase 1 freezes these; changing them after seeing results must be written down with the reason)

A sample's production graph is **usable** if ALL hold:

1. **U1 method:** it contains a METHOD node that has a line number (the real function, not only wrappers or stubs).
2. **U2 control flow:** at least 1 CFG edge.
3. **U3 flow:** if the source's expected-flow estimate `E > 0` then at least 1 `REACHING_DEF` edge exists; if `E == 0` this check is skipped.
4. **U4 unknowns:** nodes of type `UNKNOWN` are at most **5 %** of all nodes.

Language verdict from `k` usable samples out of `n = 20` (always print the 95 % Wilson interval next to it, because `n = 20` is small):

| Usable | Verdict | Meaning for P1 |
| --- | --- | --- |
| `k/n ≥ 85 %` (17 of 20 or more) | **GO** | Python/C/C++ extraction proceeds as planned |
| `70 % ≤ k/n < 85 %` (14 to 16) | **GO-WITH-LIMITS** | Extraction proceeds; the report names the failure causes; the model must tolerate missing flow; fallbacks stay on |
| `k/n < 70 %` (13 or less) | **NO-GO** | Extraction for that language is postponed; V1 stays primary; `ast` fallback (D4) |

"Python extraction proceeds" = verdict GO or GO-WITH-LIMITS. The user accepted these thresholds unchanged on 2026-10-28 at 04:38 Africa/Cairo; log them as part of D41 and tell P1.

### 3.5 Stub-rule criteria (pre-registered; evaluated on all 60 production graphs)

Choose **Rule B** (drop every METHOD without a line number) if ALL of:
- (a) no `REACHING_DEF` or `CFG` edge between two *kept* nodes is removed by Rule B (count = 0);
- (b) the number of weakly connected components of the kept graph under B is ≤ under A for every sample;
- (c) the dropped METHODs carry no source text of their own (their `code` is empty/`<empty>`);
- (d) Rule B makes the languages consistent (it removes C's external stubs, matching Python, which never had them).

Otherwise choose **Rule A**. Either way it is a **provisional default for the first build**, recorded as D41, to be revisited by the Week-3 ablation. Also record what happens to wrapper methods (`<module>`, `<global>`): do they have a line number in the real data? (This decides whether B drops them.)

The user accepted these stub-rule criteria unchanged on 2026-10-28 at 04:38 Africa/Cairo.

### 3.6 Statistics note (explain this in Phase 9)

With only 20 samples per language, "17/20 usable" could be 70 %–94 % in reality. The Wilson interval makes that visible. The user requested and completed a 100-row Python scale re-check in Phase 6.7.

---

## 4. Phases and checklists

Each phase ends with a **REVIEW GATE**: show what changed, run the tests, wait for the user's OK.

### Phase 0: Orient, branch, evidence present (≈ 0.3 h)

- [x] 0.1 Read Section 2 of this file. The three sample parquet inputs exist locally; the spike outputs do not.
- [x] 0.2 Confirmed current branch is `W2-P2-04`; kept the existing task branch rather than switching branches or pulling.
- [x] 0.3 Checked evidence: 60 sample directories; audit/results CSVs and all three source parquet files exist; Docker ran the spike successfully.
- [x] 0.4 Spike regenerated from the existing 20-row Python, C, and C++ parquet files; the audit reproduces 47/60 with DDG nodes and 30/60 flagged.
- [x] 0.5 Baseline checks pass before implementation: pytest with a workspace-local basetemp (831 passed, 3 skipped), `ruff check .`, and `ruff format --check .`. The default OS temp path had sandbox rename errors.
- [x] 0.6 Added this plan to `docs/project/W2-P2-04_graph_quality_triage_plan.md`; included in commit `b4699ac W2-P2-04: complete graph-quality triage`.

**REVIEW GATE 0:** user confirms the evidence folder exists (or has been regenerated).

### Phase 1: Freeze the criteria (≈ 0.3 h)

- [x] 1.1 User accepted the thresholds and stub-rule criteria unchanged on 2026-10-28 at 04:38 Africa/Cairo.
- [x] 1.2 Recorded the accepted criteria as final in Sections 3.4/3.5.

**REVIEW GATE 1:** criteria frozen. Anything changed later goes in Section 9 with the reason.

### Phase 2: Reproduce the 60 / 47 / 30 numbers from the existing audit CSV (≈ 0.2 h)

Do **not** run `audit_joern_spike.py` (it overwrites `docs/graphs/joern_spike.md`). Read the CSV instead.

- [x] 2.1 Read and summarized the audit CSV directly (did not rerun the audit script).
  ```
  python - <<'EOF'
  import pandas as pd
  a = pd.read_csv("data/interim/joern_spike_audit.csv").fillna({"review_flags": ""})
  print(len(a), a.groupby("language").size().to_dict())
  print("ddg_has_edges:", int(a.ddg_has_edges.sum()), "flagged:", int(a.review_flags.ne("").sum()))
  print(a.groupby("language").review_flags.apply(lambda s: int(s.ne("").sum())))
  print(a.review_flags.str.split(";").explode().value_counts())
  EOF
  ```
- [x] 2.2 Reproduced 60 samples, 47 with DDG nodes, 30 flagged (Python 17, C 8, C++ 5), and 13 without DDG nodes; recorded flag frequencies in Section 5.
- [x] 2.3 Recorded the empty-DDG and flagged sample lists separately in Section 5.

**REVIEW GATE 2:** numbers reproduced, flag table in STATE.

### Phase 3: Look at the raw material by hand BEFORE writing code (≈ 0.5 h)

Purpose: learn the real DOT/GraphML format so the code is written for facts, not guesses.

- [x] 3.1 Inspected flagged Python `python_01`, `python_03`, `python_10`; flagged C `c_01`, `c_13`; flagged C++ `cpp_03`, `cpp_05`; unflagged controls `python_02`, `cpp_01`.
- [x] 3.2 Read each selected source, first 20 lines of one CFG and DDG DOT file per sample, and all case-insensitive `unknown` matches in those DOT folders.
- [x] 3.3 Recorded the DOT label, empty-DDG shape, UNKNOWN examples, and per-method file naming in Section 5.
- [x] 3.4 Updated H1–H6 with evidence-based Phase 3 observations; production-graph hypotheses remain open until extraction.

**REVIEW GATE 3:** the format notes exist; the label-type rule for `label_type()` is decided from real files.

### Phase 4: Production-path re-extraction of the 60 samples (≈ 0.3 h of work, ≈ 6 min of waiting) and the early message to P1

Needs Docker. Uses the existing extractor and cache; **no change to `shield_core/extraction`**.

- [x] 4.1 Added `JOERN_TRIAGE_DIR = INTERIM_DIR / "joern_triage"` to `shield_core/paths.py`; layout tests pass (63 passed).
- [x] 4.2 Ran the one-off production extraction for all 60 samples (the CLI will be implemented in Phase 5); 60 succeeded, 0 failed, and the cache was filled with 60 misses.
  ```
  python - <<'EOF'
  from pathlib import Path
  from scripts.spikes.joern.benchmark_samples import load_spike_samples
  from scripts.spikes.joern.benchmark_core import BENCH_GROUPS
  from shield_core.extraction.cache import GraphCache, CachedGraphExtractor
  from shield_core.extraction.joern_extractor import JoernExtractor
  from shield_core.paths import JOERN_TRIAGE_DIR
  cache = GraphCache(JOERN_TRIAGE_DIR / "graph_cache")
  ex = CachedGraphExtractor(JoernExtractor(docker_image="shield-joern"), cache)
  for s in load_spike_samples():
      lang, ext = BENCH_GROUPS[s.group]
      try:
          g = ex.extract(s.code, lang, ext)
          kinds = {}
          for e in g.edges: kinds[e.type] = kinds.get(e.type, 0) + 1
          print(s.sample_id, len(g.nodes), kinds.get("REACHING_DEF", 0), sum(n.type == "UNKNOWN" for n in g.nodes))
      except Exception as exc:
          print(s.sample_id, "FAILED", type(exc).__name__, str(exc)[:80])
  EOF
  ```
  Columns printed: id, nodes, REACHING_DEF edges, UNKNOWN nodes.
- [x] 4.3 Verified every spike `sample.<ext>` against its `Sample.sha256` after newline normalization: 60/60 match.
- [ ] 4.4 **Early answer to P1 (clearly labelled PRELIMINARY).** Review the draft and send it after approval. Python is 7/20 (NO-GO); C++ is 17/20 (GO). The legacy C-labelled 13/20 result is not a valid C verdict: the spike source is BigVul, whose rows are all metadata-labeled `cpp`. A verified-C scale check is required because C is needed for interprocedural tainting; final report and manual review follow.
- [x] 4.5 `JOERN_TRIAGE_DIR` path change committed in `b4699ac W2-P2-04: complete graph-quality triage`.

**REVIEW GATE 4:** user sees the table, agrees what the preliminary message to P1 says, sends it.

### Phase 5: Build the tooling, test-first (≈ 2.5 h)

All logic that decides anything lives in **`triage_core.py` as pure functions** (no Docker, no file system except where stated) so CI can test it. The CLI only glues.

#### 5.1 `scripts/spikes/joern/triage_core.py`: functions to write (names fixed so another chat can continue)

| Function | Input → output | Rule |
| --- | --- | --- |
| `parse_dot(text)` | DOT text → `DotStats(nodes: dict[id,label], edges: set[(src,dst)])` | Same regexes as `audit_joern_spike.inspect_dot_file` (so counts match), plus `html.unescape` on labels. |
| `label_type(label)` | DOT label → first token (node type or name) | Rule fixed in Phase 3.3 from real files. |
| `audit_flags(cfg_stats, ddg_stats, *, cpg_ok, source_ok)` | → list of the **same flag names** as the audit | Reproduces `review_flags` exactly. A test compares it with a fixture row of `joern_spike_audit.csv`. |
| `real_unknown_count(labels)` vs `substring_unknown_count(labels)` | labels → ints | Splits "type UNKNOWN" from "text contains unknown" (tests H3). |
| `graph_metrics(graph: CodeGraph)` | → `GraphMetrics` (dataclass): `n_nodes, n_edges, edge_counts{type:int}, n_unknown_nodes, unknown_share, methods:[(name,line)], n_real_methods, n_lineless_methods, has_reaching_def` | From the production graph. |
| `flow_expectation(language, code)` | → `(E:int, method:str)` | Python: stdlib `ast`; E = number of uses of a parameter or of a name assigned earlier in the same function (cheap, deterministic). C/C++: regex heuristic (count of assignments `=` not `==`, plus parameters used); `method="regex"` and flagged approximate. **Manual review is the authority.** |
| `classify(row)` | one sample's metrics + flags → `(cause_code, reason_text)` | Precedence: `EXTRACTION_FAILURE` → `INPUT_FRAGMENT` (no real METHOD or tree-sitter/regex says unbalanced braces) → `PARSER_GAP` (E>0 and no REACHING_DEF, or unknown_share > 5 %) → `DOT_VIEW_ONLY` (DDG DOT edgeless but REACHING_DEF present) → `EXPECTED_NO_FLOW` (E==0) → `AUDIT_ARTIFACT` (flagged but all U1–U4 pass) → `OTHER`. |
| `is_usable(row)` | → bool | U1–U4 from Section 3.4. |
| `wilson_interval(k, n, z=1.96)` | → `(low, high)` | centre = (p + z²/2n)/(1 + z²/n); half = z·sqrt(p(1−p)/n + z²/4n²)/(1 + z²/n). |
| `language_verdict(k, n)` | → `"GO" \| "GO-WITH-LIMITS" \| "NO-GO"` | Thresholds from 3.4. |
| `stub_rule_impact(graph)` | → `StubImpact(dropped_nodes, dropped_edges_by_type, kept_edge_loss, components_a, components_b, dropped_have_text)` | Union-find over kept nodes for A (all kept node types per `graph_schema.md`) and for B (A minus line-less METHOD nodes). |
| `preserve_block(old_text, new_text, begin, end)` | → text | Keeps the `<!-- TRIAGE:BEGIN -->…<!-- TRIAGE:END -->` block of `old_text` when the audit script regenerates the report (Phase 7.2). |

- [x] 5.1.a Wrote tests for the core helpers first, observed the initial collection/failure states, then implemented and fixed the helpers.
- [x] 5.1.b `ruff check .` and `ruff format --check .` pass after the core and CLI implementation.

#### 5.2 Code style rules (match the repo)

Type hints; short docstrings stating the *why*; no globals except constants; constants for thresholds at the top (`USABLE_UNKNOWN_SHARE = 0.05`, `GO_THRESHOLD = 0.85`, `LIMITS_THRESHOLD = 0.70`); no `parents[N]`; no Docker in `triage_core.py`; every public function covered by a test.

#### 5.3 `scripts/spikes/joern/triage_joern_spike.py` (CLI; subcommands)

| Subcommand | What it does | Needs Docker |
| --- | --- | --- |
| `extract` | Loads the 60 spike samples, runs them through `CachedGraphExtractor(JoernExtractor)` into `data/interim/joern_triage/graph_cache/`, prints progress and failures. Idempotent (cache hits on re-run). | yes |
| `analyze` | For each of the 60: reads the spike DOT folders (flags, DDG/CFG stats), loads the production graph, computes `graph_metrics`, `flow_expectation`, `classify`, `is_usable`, `stub_rule_impact`; writes `triage.csv`, `summary.json` (per-language usable counts, Wilson intervals, verdicts, stub-rule evidence) and one **review card** per flagged/empty-DDG sample in `cards/<id>.md`. | no |
| `report` | Reads `triage.csv`, `summary.json` and `docs/graphs/joern_triage_review.csv`; writes `docs/graphs/joern_triage.md` and prints the addendum text for `joern_spike.md`. | no |

`triage.csv` columns (fixed): `sample_id, language, spike_dir, flagged, review_flags, ddg_dot_edges, cfg_dot_edges, n_nodes, n_edges, reaching_def, cfg_edges, call_edges, n_unknown_nodes, unknown_share, substring_unknown, real_methods, lineless_methods, expected_flow, flow_method, auto_cause, auto_reason, usable`.

A **review card** contains: the numbered source, the flag list, the metrics, the METHOD list `(name, line)`, the first 15 `REACHING_DEF` edges as `src code → dst code`, the first 10 UNKNOWN nodes `(code, line)`, and the auto cause with its reason. It is what the human reads in Phase 6.

- [x] 5.3.a Implemented and tested `analyze`, `report`, and the thin `extract` wrapper; scale C selection is supported without overwriting spike results.
- [x] 5.3.b `python -m scripts.spikes.joern.triage_joern_spike --help` works and lists all three subcommands.

#### 5.4 Tests (`tests/spikes/test_triage_core.py`, `tests/spikes/test_triage_cli.py`)

Write at least these cases (synthetic strings and tiny `CodeGraph` objects; no Docker):

- `parse_dot`: counts nodes/edges on a 3-node DOT; ignores non-node lines; unescapes `&lt;`.
- `label_type`: operator call label, METHOD label, UNKNOWN label, label with commas in code.
- `audit_flags`: each of the 10 flag names fires exactly when its rule says; a clean sample gives `[]`.
- `real_unknown_count` vs `substring_unknown_count`: a node of type UNKNOWN counts in both; a variable named `unknown_x` counts only in the substring version.
- `graph_metrics`: edge counts per type, unknown share, line-less METHOD counting.
- `flow_expectation`: `def f(): return 1` → 0; `def f(x): y = x; return y` → ≥ 2; syntax error → falls back with a note, no exception.
- `classify`: one test per cause code, plus precedence (a sample with both UNKNOWN share > 5 % and E > 0 without REACHING_DEF is `PARSER_GAP`).
- `is_usable`: boundary at 5.0 % and 5.1 % unknown share; E==0 skips U3.
- `wilson_interval`: known values (e.g. 17/20 → about 0.64–0.95; compare with a hand calculation); `k=0` and `k=n` do not crash.
- `language_verdict`: 17 → GO, 16 → GO-WITH-LIMITS, 14 → GO-WITH-LIMITS, 13 → NO-GO (n=20).
- `stub_rule_impact`: a graph with a `strcpy` stub and a CALL edge into it: B drops 1 node and the CALL edge, components unchanged; a graph where the stub bridges two components: components_b > components_a is reported.
- `preserve_block`: block kept when new text has none; block replaced only if the new text carries its own; text without markers unchanged.
- CLI: `analyze` on a fake spike directory writes the columns in the fixed order and one card per flagged sample.

- [x] 5.4 Added core and CLI tests for the listed behavior, including scale selection and absence of spike DOT flags for scale rows.

**REVIEW GATE 5 (after each of 5.1, 5.3, 5.4):** `pytest tests/spikes -q` → 166 passed, 2 skipped; `pytest tests/test_layout.py -q` → 63 passed; `ruff check .` and `ruff format --check .` pass. Diff is ready for user review; wait for the OK before Phase 6.

- [x] 5.5 Committed per logical unit: `30942a0 W2-P2-04: triage_core helpers + tests`; `df09c03 W2-P2-04: triage CLI + tests`.

### Phase 6: Run the triage and judge by hand (≈ 1.5 h)

- [x] 6.1 Re-ran `extract --sample-set spike`; 60 samples, 0 failures, 60 cache hits, 0 misses.
- [x] 6.2 Ran `analyze --sample-set spike`; reproduced 30 flagged and 13 empty DDG (Python 17/3, C 8/7, C++ 5/3). Preliminary usable counts remain Python 7/20, C 13/20, C++ 17/20.
- [x] 6.3 **Manual review.** [joern_triage_review.csv](../graphs/joern_triage_review.csv) has 41 evidence rows: all 30 original flagged samples, the available original controls (Python 4, legacy C 2, C++ 2), all 5 verified-C non-usable cards, and 5 verified-C usable controls chosen with `random.Random(42)`. Evidence is ≤ 200 chars and cites source lines or node text.
- [x] 6.4 Classifier agreement is 36/36 (100%) on rows with an assigned cause; the five scale-C clean controls have blank causes and are excluded from this rate. No classifier tuning was needed.
- [x] 6.5 **Stub rule: Rule A (provisional).** Verified C: 2,215 line-less METHODs; Rule B drops 4,426 REACHING_DEF and 2,215 CFG edges; components worsen in 0/100; dropped METHODs have no text; `<global>` wrappers have line 1 (200 occurrences). Python: 217 line-less METHODs; B drops 225 REACHING_DEF/116 CFG edges and worsens components in 13/20; no dropped text; `<module>` wrappers have line 1 (20). C++: 144 line-less METHODs; B drops 264 REACHING_DEF/144 CFG edges; 0/20 component regressions; no dropped text; `<global>` wrappers have line 1 (40). Rule B fails (a) and (b), so Rule A is selected; Python's line-less methods include operators such as `<operator>.assignment` and `<operator>.fieldAccess`, so the effect is not limited to C/C++ external stubs. The legacy C-labelled/BigVul figures are excluded from the C comparison because those rows are metadata `cpp`.
- [x] 6.6 **User-requested C robustness check:** the first 100-row `scale --group c` run completed (100/100) but is invalid for a C verdict: BigVul labels every row `cpp`. Exclude it from C evidence. The corrected seeded sampler selected 100 unique rows labeled `c` from `cvefixes_cpp.parquet` (`language == "c"`, seed 43), excluding all original spike hashes. Extraction: 100 samples, 0 failures, 0 cache hits, 100 misses. Analysis: 95/100 usable, Wilson 0.8882–0.9785, **GO**; 5 `INPUT_FRAGMENT` cases. The legacy C-labelled 20 are shown separately with a provenance warning; do not calculate a combined C 120 verdict. All five non-usable cards and five seeded usable controls were manually reviewed. Thresholds remain unchanged.
- [x] 6.7 **User-requested Python robustness check:** 100 unique rows from `cvefixes_python_deduped.parquet`, seed 43, excluding spike hashes; extraction 0 failures. Analysis: 38/100 usable, Wilson 0.2910–0.4779, **NO-GO**. All 62 non-usable rows lack a line-numbered real METHOD (U1); 61/62 have expected flow > 0. Combined with the disjoint original 20, Python is 45/120 usable, Wilson 0.2935–0.4642, still **NO-GO**. This check is outside the original 60.
- [x] 6.8 Final raw-path table: Python original 7/20 (0.1812–0.5671), scale 38/100 (0.2910–0.4779), combined 45/120 (0.2935–0.4642), **NO-GO**; verified C 95/100 (0.8882–0.9785), **GO**; C++ 17/20 (0.6396–0.9476), **GO**. The legacy C-labelled 13/20 is invalid C evidence (BigVul metadata is `cpp`); no mixed 120-row C estimate is reported.
- [x] 6.9 **Python context recovery experiment:** wrapped original spike extraction: 20 samples, 0 failures, 20 baseline hits, 13 wrapper misses; analysis 20/20 usable, 13 wrapped. Wrapped scale: 100/100 usable, 62 wrapped. The disjoint combined set is 120/120 usable (95% Wilson 0.9690–1.0000). This is triage-only transformed evidence; the synthetic class adds a line, so production adoption and a GO verdict remain blocked on correct source-line mapping validation.

**REVIEW GATE 6:** user reviews the review sheet, the verdicts and the stub decision. Final yes/no for Python agreed.

### Phase 7: Write it down (≈ 1.5 h)

- [x] 7.1 Generated `docs/graphs/joern_triage.md` with frozen thresholds, raw per-language results (true-C extension shown separately), cause counts, original per-sample table, H1–H6 outcomes, Rule A evidence, limitations, and reproduction commands. The transformed Python wrapper result is clearly labeled triage-only.
- [x] 7.2 Added `preserve_block` to `audit_joern_spike.py`; added a test and verified by regenerating `joern_spike.md` that exactly one protected triage block survives. Added explicit language verdicts, Python wrapper caveat, main causes, Rule A, and report links.
- [x] 7.3 Updated `SHIELD_PLAN.md`: closed C3, added D41, checked W2-P2-04, updated Python graph-quality risk and changelog. G2 remains unchecked because C1, C2 and C4 remain open.
- [x] 7.4 Updated root README, `docs/README.md`, the Joern spike README, `tests/README.md`, and `graph_schema.md`; layout tests pass (64).
- [x] 7.5 Prepared the final P1 message in Appendix C. It has not been sent; external messaging requires the user's direct authorization.

**REVIEW GATE 7:** user reads the diff of every document change.

### Phase 8: Final checks and close (≈ 0.5 h)

- [x] 8.1 `ruff check .`, `ruff format --check .`, `pytest -q`: all green; 885 passed, 3 skipped.
- [x] 8.2 `git status` is clean; generated data and pytest basetemp files are not tracked.
- [x] 8.3 PR [#53](https://github.com/nhahub/NHA-5-186/pull/53) targets `main` from `origin/w2-p2-04-graph-triage`. The user created the PR; its approved summary, verification, and limitations are in the description. The P1 message remains drafted in Appendix C and unsent.
- [x] 8.4 GitHub Actions passed on PR #53's final head after the plan closeout commit (1/1 check; verified 2026-10-28).
- [x] 8.5 Phase 8 final checks, PR, and CI are complete. The overall task is complete after Phase 9, as required by Section 0.

### Phase 9: Professor-style explanation (≈ the user's reading time)

- [x] 9.1 Delivered in the chat after Phase 8: concepts, file/function walkthrough, examples, ten self-check questions, and a coding exercise following Section 10.

---

## 5. STATE (update after every step)

- Last ticked box: *9.1*
- In progress: *None. PR #53 is open from `w2-p2-04-graph-triage` to `main`; its approved description is published, and GitHub Actions passed on the final PR head. The P1 message is drafted but unsent.*
- Criteria frozen on: *2026-10-28 04:38 Africa/Cairo (thresholds accepted unchanged)*
- Flag frequency table (Phase 2):
  | Flag | Python | C | C++ | Total |
  | --- | ---: | ---: | ---: | ---: |
  | `CFG_UNKNOWN_NODES` | 17 | 8 | 5 | 30 |
  | `DDG_HAS_NO_NODES` | 3 | 7 | 3 | 13 |
- The only observed flags are `CFG_UNKNOWN_NODES` and `DDG_HAS_NO_NODES`; UNKNOWN flags dominate, especially in Python. This prioritizes H3, but does not establish whether those are real UNKNOWN nodes.
- Production extraction (user-run one-off; 2026-10-28): 60/60 graphs extracted, 0 failures, 60 cache misses. Per language: all 20 have CFG edges; 17 Python, 13 C, and 17 C++ have `REACHING_DEF`; all 13 with no `REACHING_DEF` are the same 13 with empty spike DDGs. Every production sample flagged by spike `CFG_UNKNOWN_NODES` has at least one real production UNKNOWN node (Python 17/17, C 8/8, C++ 5/5).
- Preliminary structural screen (a line-numbered named METHOD excluding `<module>`/`<global>` wrappers; UNKNOWN over-limit samples overlap only with U1 failures):
  | Language | U1 real METHOD | U2 CFG | U3 has `REACHING_DEF` among U1 passes | U4 samples over 5% UNKNOWN | U1–U4 usable |
  | --- | ---: | ---: | ---: | ---: | ---: |
  | Python | 7/20 | 20/20 | 7/7 | 4/20 | 7/20 |
  | C | 13/20 | 20/20 | 13/13 | 7/20 | 13/20 |
  | C++ | 17/20 | 20/20 | 17/17 | 3/20 | 17/20 |
- Raw-path results after U1–U4: Python 7/20, scale 38/100, combined 45/120, **NO-GO** (Wilson 0.2935–0.4642); verified C 95/100, **GO** (0.8882–0.9785); C++ 17/20, **GO** (0.6396–0.9476). The triage-only synthetic-class experiment gives Python 120/120 usable (Wilson 0.9690–1.0000), pending production source-line mapping validation. The legacy C-labelled spike is 13/20 (0.43–0.82), but is **not a valid C verdict** because every row is metadata-labeled `cpp`; the first BigVul scale-C run is invalid for the same reason.
- Lists: empty-DDG samples = *python_01, python_10, python_16, c_01, c_02, c_03, c_04, c_13, c_16, c_18, cpp_05, cpp_09, cpp_11*; flagged samples = *python_01, python_03, python_04, python_05, python_06, python_07, python_09, python_10, python_11, python_12, python_13, python_14, python_15, python_16, python_17, python_19, python_20, c_01, c_02, c_03, c_04, c_13, c_15, c_16, c_18, cpp_03, cpp_05, cpp_06, cpp_09, cpp_11*
- Format notes (Phase 3):
  - DOT files contain physical line breaks (the earlier terminal output rendered them as `\\n`). Node records use `"id" [label = <TYPE, line<BR/>code> ]`; `TYPE` may be a Joern node type (`METHOD`, `UNKNOWN`), operator name (`&lt;operator&gt;.assignment`), or call name (`assertEqual`). Parsing can use physical lines; label text must be HTML-unescaped before classifying types.
  - Empty DDG example: `digraph "&lt;module&gt;" { node [shape="rect"]; \n\n}` with no node or edge records. This is an actually empty view in the sampled file, not merely a METHOD-only graph.
  - Flagged Python CFG matches for `python_01`/`python_03`/`python_10` are `UNKNOWN` node labels containing `ErrorStatement(io.joern.pythonparser.ParseException...)`; these are node types, not just source text. C/C++ examples also show UNKNOWN node labels. In control `cpp_01`, lowercase `&lt;unknown&gt;` appears in DDG edge labels (`ITC_AT_END`), not node labels.
  - CFG and DDG exports are split per method and numbered (`0-cfg.dot`, `1-cfg.dot`, etc.; corresponding `*-ddg.dot`). The first file can be the `<module>`/`<global>` wrapper. In the inspected spike DOT, wrapper METHOD labels have line 1; production GraphML still needs checking.
- Preliminary message to P1 sent: *no*
- Per-language result after manual review and user-requested Python scale: Python *7/20 original; 38/100 scale; 45/120 combined, 0.2935–0.4642, NO-GO* · verified C *95/100, 0.8882–0.9785, GO* · C++ *17/20, 0.6396–0.9476, GO*. The legacy C-labelled 20 (13/20) are all metadata `cpp` and are not combined with verified C.
- Stub rule chosen: *Rule A (provisional). Rule B loses REACHING_DEF/CFG edges for verified C (4,426/2,215), Python (225/116), and C++ (264/144); Python components worsen in 13/20 samples. No dropped METHODs have text. Wrappers have line 1, so B retains them. Python also has line-less operator METHODs, contradicting H6.*
- Test count before / after: *831 passed, 3 skipped (workspace-local basetemp; default OS temp path caused 6 sandbox rename errors)* / *current: 885 passed, 3 skipped; `tests/spikes` 171 passed, 2 skipped; layout 64 passed; Ruff check and format pass*
- PR: *not created; GitHub connector permission error (403). Pushed branch and PR creation link: `https://github.com/nhahub/NHA-5-186/pull/new/w2-p2-04-graph-triage`*
- Open questions for the user: *Authorize PR creation in GitHub's signed-in browser if you want me to complete it. Direct authorization is also needed to send the prepared message to P1. The wrapper experiment changes parser line positions and is not a production fix until offset mapping is verified.*

---

## 6. Things that can go wrong (and what to do)

| Risk | Sign | Action |
| --- | --- | --- |
| Spike folder not on the machine | `ls` in Phase 0.3 shows fewer than 60 dirs | Regenerate (0.4) and say numbers may differ |
| Audit script overwrites the addendum | `joern_spike.md` loses the block | Never run the audit between 7.1 and 7.2; 7.2 makes it safe; recover from git |
| Production graphs differ from spike graphs (H2) | node counts differ per sample | Production wins; report both |
| Docker memory | extraction killed | one sample at a time (default); raise Docker Desktop memory |
| Joern timeout/crash on a sample | `ExtractionError` | classify as `EXTRACTION_FAILURE`; do not retry more than once |
| Regex flow estimate wrong for C/C++ | manual review disagrees | manual review decides; say so in the report |
| Hand-edited generated doc | `joern_triage.md` differs from `report` output | edit the CSV/code and regenerate |
| `SHIELD_PLAN.md` reformatted by an editor | diff touches many lines | undo; use exact-match replacement |
| Numbers in docs not from outputs | a figure has no source | delete it; paste the real value |

---

## 7. Cause → action quick reference (what the verdict means downstream)

| Finding | Downstream effect |
| --- | --- |
| Python GO / GO-WITH-LIMITS | W2-P1-02 extracts Python first; W2-P2-01 builds the PyG dataset on it |
| Python NO-GO | V1 stays primary for Python; `ast`/tree-sitter features (D4); first GNN on C/C++ in Week 3 |
| Many `INPUT_FRAGMENT` in C/C++ | add a "parseable whole" filter before extraction (recommendation to P1) |
| Many `PARSER_GAP` for one construct | open an issue naming the construct; consider that construct in feature fallbacks |
| Rule B chosen | W2-P2-01 converter drops line-less METHODs; converter version bumped when it lands (graph cache stays valid) |
| Rule A chosen | converter keeps wrappers and stubs; revisit after the ablation |

---

## 8. Documentation updates (do them in the same PR; `README.md` §18 is the rule book)

**Root `README.md`**

| Section | Edit |
| --- | --- |
| §2 Component maturity (Graphs rows) | add a row: `Graph-quality triage (scripts/spikes/joern/triage_joern_spike.py)` ✅ with a note "verdicts per language in docs/graphs/joern_triage.md"; mention the verdicts in the existing "Batch extraction" note |
| §5 Folder structure schema | add `triage_core.py`, `triage_joern_spike.py` under `scripts/spikes/joern/` and the new test files under `tests/spikes/` |
| §7 Functionality → folder table | add "Judge graph quality" → `scripts/spikes/joern/` |
| §8.9 scripts table | add rows for the two scripts (purpose / input / output as in Section 5.3); update the `audit_joern_spike.py` row (it now preserves the triage block) |
| §8.10 tests | update the test count and add the new test files |
| §9 sequence flow | add a **Story G: graph-quality triage** sequence diagram (participants: `triage_joern_spike.py extract/analyze/report`, `JoernExtractor`, Docker `shield-joern`, `triage_core.py`, human reviewer, `joern_triage.md`, `joern_spike.md`); insert it after 9.6, renumber the dependency map to 9.8 and fix the Table of Contents anchor; add the new imports to the dependency map |
| §10.4 artifact registry | add rows: triage graphs/csv/cards (`data/interim/joern_triage/…`), review sheet, `docs/graphs/joern_triage.md` |
| §11 activity diagrams | add a short activity diagram "Lifecycle of a triage run" (green = real) or extend 11.5 with the quality-check branch |
| §17 Known gaps | update gap #6 (graph quality now measured; verdicts); add new gaps found (e.g. "C/C++ rows are fragments", "Rule A/B provisional, ablation in Week 3") |
| "What comes next" (end of §17) | tick "Joern graph-quality triage recorded" |
| §19 Documentation index | add `docs/graphs/joern_triage.md`, `joern_triage_review.csv` |

Keep the colour convention (green working · yellow partial/stub · grey dashed planned · red error). Only name paths that exist (`tests/test_layout.py` fails otherwise).

**Other files:** `docs/README.md` (add the two files and the plan file to the `graphs/` and `project/` rows); `scripts/spikes/joern/README.md` (add the two scripts); `tests/README.md` (spikes row if absent); `docs/graphs/graph_schema.md` §8 (one line: stub rule decision pointer to D41, no schema version change); `SHIELD_PLAN.md` as in 7.3.

---

## 9. Handoff log (append one line per step: date · who · what · result)

- 2026-10-28 · Codex · Phase 0 · Confirmed branch `W2-P2-04`; regenerated missing spike outputs; audit confirms 60 rows, 47 DDG-node samples, 30 flagged (Python 17, C 8, C++ 5); baseline passes with workspace-local pytest temp files (831 passed, 3 skipped); Ruff checks pass.
- 2026-10-28 · Codex · Phases 1–2 · User accepted the proposed thresholds unchanged; audit CSV reproduced the 60/47/30 counts; recorded both flags and their per-language frequencies and lists of empty-DDG and flagged samples.
- 2026-10-28 · Codex · Phase 3 · Inspected nine selected raw samples; confirmed physical DOT line breaks (the terminal had rendered them as `\\n`), real UNKNOWN node labels on inspected Python flags, empty DDG views, per-method numbered exports, and fragment/context indicators; updated H1–H6 status.
- 2026-10-28 · Codex · Phase 4 · Added the triage path constant; 63 layout tests pass; all 60 spike hashes match; user-run production extraction succeeded 60/60 with 0 failures and 60 cache misses. Preliminary U1–U4 counts: Python 7/20, legacy C-labelled rows 13/20, C++ 17/20. Later metadata validation showed the legacy C-labelled source is all `cpp`, so it is not used as a C verdict. Production UNKNOWN-node presence matches every audit UNKNOWN flag. P1 message awaits user review/send.
- 2026-10-28 · User · Scope update · Requested an additional C sample check because C is needed for interprocedural tainting; added a seeded 100-row C extension for Phase 6, keeping original and expanded results separate and thresholds unchanged.
- 2026-10-28 · Codex · Phase 5 · Added pure triage helpers, scale-aware analyze/report/extract CLI, and core/CLI tests; 166 spike tests pass (2 skipped), 63 layout tests pass, Ruff check/format pass. At review gate; Phase 6 awaits user OK.
- 2026-10-28 · User · Phase 5 review · Approved proceeding with Phase 5 before the C sample extension.
- 2026-10-28 · Codex · Phase 5.5 · Committed core + tests as `30942a0` and CLI + tests as `df09c03`; pre-commit hooks pass. Phase 5 complete; ready for Phase 6.
- 2026-10-28 · Codex · Phase 6.1–6.2 · Re-extracted all 60 original rows from cache (60 hits, 0 failures) and analyzed them; audit counts reproduce 30 flagged / 13 empty DDG. Original structural screen unchanged.
- 2026-10-28 · Codex · Phase 6.6 source validation · The first user-run 100-row C-group extract succeeded technically, but metadata audit showed BigVul is 100% `cpp`; excluded it from C findings. Added a language-filtered sampler from the raw CVEFixes C/C++ file, confirmed 100 unique C-labeled candidates with no original-spike hash overlap, and added CLI set `c-scale`. Verified-C extraction is pending a user Docker run.
- 2026-10-28 · Codex · Phase 6 implementation fix · Added tests-first C-language sampler/CLI routing and corrected scale analysis to leave clean usable rows unclassified and clear stale generated review cards; `tests/spikes` 168 passed, 2 skipped; Ruff clean.
- 2026-10-28 · Codex · Phase 6.3/6.5 preliminary · Manually reviewed the 30 original flagged/empty-DDG samples plus all eight available auto-cause control candidates; wrote 31 evidence rows. Rule B would remove 341 REACHING_DEF/CFG edges in Python and worsen components in 13/20 samples; Rule A is the provisional choice. The legacy C-labelled values are not a true-C verdict.
- 2026-10-28 · User · Phase 6.6 · Ran corrected `c-scale` extraction: 100 true-C-labeled samples, 0 failures, 0 cache hits, 100 misses.
- 2026-10-28 · Codex · Phase 6 complete · Corrected C analysis: 95/100 usable, 95% Wilson 0.8882–0.9785, GO. Reviewed all five failures and five seeded usable controls; review sheet has 41 rows and 36/36 cause-coded agreement. Rule A selected provisionally from per-language Rule B edge-loss and component evidence. Waiting at Review Gate 6.
- 2026-10-28 · User/Codex · Phase 6.7 · User ran the 100-row Python scale extract (0 failures, 100 misses). Analysis is 38/100 usable, Wilson 0.2910–0.4779, NO-GO; combined with the disjoint spike 20, Python is 45/120, Wilson 0.2935–0.4642, NO-GO. All 62 scale non-usable rows fail U1.
- 2026-10-28 · User/Codex · Python context recovery · Wrapped original spike extraction: 20/20, 0 failures, 20 baseline hits, 13 wrapped misses; analysis 20/20 usable. Wrapped scale: 100/100 usable, 62 wrapped. The disjoint 120-row transformed set is 120/120 usable (Wilson 0.9690–1.0000). Raw Python remains NO-GO until production source-line mapping is validated. Generated the report and protected addendum; added D41 and refreshed documentation.
- 2026-10-28 · Codex · Phase 8 · Final checks: 885 passed, 3 skipped; Ruff and formatting passed. Commit `b4699ac` pushed to `origin/w2-p2-04-graph-triage`. GitHub PR creation returned 403 (`Resource not accessible by integration`); waiting for user direction on the signed-in browser path. CI has not run because no PR exists.
- 2026-10-28 · User/Codex · Phase 8 close · User created PR [#53](https://github.com/nhahub/NHA-5-186/pull/53) from `w2-p2-04-graph-triage` to `main`; verified head `be1c0af` and GitHub Actions CI run `40634429687` conclusion `success`. PR description is still the placeholder template. P1 message remains unsent. Phase 9 explanation is the final task step.
- 2026-10-28 · Codex · Phase 9 · Delivered the professor-style explanation, ten self-check questions, and a coding exercise in chat. PR #53 description update was rejected by automatic review pending specific approval; PR itself and its green CI are unchanged.
- 2026-10-28 · Codex · PR description · After the user approved the exact replacement text, updated and verified PR #53's description through the signed-in GitHub browser; connector write returned 403. PR head and CI are unchanged.
- 2026-10-28 · Codex · Final plan closeout · Recorded completion of Phases 8–9 in the plan, then pushed the documentation-only closeout to PR #53; CI passed on the resulting head.

---

## 10. Plan for the final professor explanation (Phase 9)

Order of teaching (each item: the idea in plain words → a tiny example → where it appears in the code):

1. What a code property graph is; AST vs CFG vs data flow (REACHING_DEF/DDG); why a GNN wants these edges.
2. Joern frontends and why `--language` matters; DOT view vs GraphML; what an UNKNOWN node is.
3. Why "export succeeded" is not "graph is good": the audit's heuristics, one by one, and what each can get wrong.
4. Triage as a method: hypotheses written first, causes taxonomy, pre-registered criteria, why we freeze thresholds before looking.
5. Sampling and uncertainty: why 17/20 is not 85 % for sure; the Wilson interval derived step by step.
6. Static estimate of data flow with Python's `ast` (walk the tree, parameters, assignments) and why the C/C++ regex is only a hint.
7. Stub methods and Rule A/B; union-find / connected components; why dropping a node can disconnect a graph.
8. File by file: `triage_core.py` (every function, with an input/output example), `triage_joern_spike.py` (subcommands, why `extract` is last and thin), the tests (what each one protects), the marker-protected addendum and `preserve_block`.
9. How to run everything from a clean clone; how to read `joern_triage.md`.
10. Self-check questions (10) and one "write it yourself" exercise (e.g. re-implement `wilson_interval` and `language_verdict` from the description).

---

## Appendix A: command cheat sheet

```
git switch -c w2-p2-04-graph-triage
python -m scripts.spikes.joern.triage_joern_spike extract
python -m scripts.spikes.joern.triage_joern_spike analyze
python -m scripts.spikes.joern.triage_joern_spike report
pytest tests/spikes -q
pytest tests/test_layout.py -q
ruff check . && ruff format --check .
```

## Appendix B: addendum template for `docs/graphs/joern_spike.md` (fill every `<…>` from `summary.json`; delete nothing else)

```
<!-- TRIAGE:BEGIN -->
## Graph-quality triage (W2-P2-04, closes C3)

Criteria (frozen <date>): a graph is usable if it has a real METHOD node, at least one CFG edge, at least one
REACHING_DEF edge whenever the source has data flow, and at most 5 % UNKNOWN nodes. Verdict: GO at ≥ 85 % usable,
GO-WITH-LIMITS at 70–84 %, NO-GO below 70 % (n = 20 per language, so intervals are wide).

| Language | Usable | 95 % interval | Verdict |
| --- | --- | --- | --- |
| Python | <k>/20 | <lo>–<hi> | <verdict> |
| C | <k>/20 | <lo>–<hi> | <verdict> |
| C++ | <k>/20 | <lo>–<hi> | <verdict> |

Verdict sentence: Joern graph extraction is <GO / GO-WITH-LIMITS / NO-GO> for Python, <…> for C and <…> for C++.
Main causes: <cause counts per language>. First-build stub rule: <A or B> (decision D41, provisional until the Week-3 ablation).
Full evidence: `docs/graphs/joern_triage.md`, `docs/graphs/joern_triage_review.csv`.
<!-- TRIAGE:END -->
```

## Appendix C: message to P1 (Hatem), final version

> Draft — not sent. W2-P2-04 graph-quality triage complete. Current raw-path verdicts: Python **NO-GO** (45/120 usable, 95% Wilson 0.2935–0.4642); verified C **GO** (95/100, 0.8882–0.9785); C++ **GO** (17/20, 0.6396–0.9476). Rule A is the provisional first-build stub policy; revisit in the Week-3 ablation. The triage-only Python synthetic-class context experiment reached 120/120 usable, but adds a parser line and needs source-line mapping validation before production adoption.
> Main causes: missing class context in indented Python method excerpts; input fragments in verified C; input fragments and expected no-flow cases in C++. Details: `docs/graphs/joern_triage.md` and `docs/graphs/joern_triage_review.csv`. C/C++ expected-flow estimates are approximate; the spike and scale sets do not establish representativeness of the full datasets.
> Recommendation for W2-P1-02: consistently wrap every indented Python method excerpt with its class context before production extraction, correct the added source-line offset, and verify the production mapping before changing Python from NO-GO.
