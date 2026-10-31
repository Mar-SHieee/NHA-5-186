# SHIELD — Master Execution Plan (6 Weeks, Core-First, Language-Pluggable)

> **SHIELD** = Semantic and Hierarchical Inference for Exploits and Logic Detection
Team of 5 · Target: V4 architecture (CodeBERT + GNN fusion + fix loop) + repo-level aggregation + interprocedural taint + VS Code extension + full web app (Angular + FastAPI).
**Languages:** Python and C/C++ are committed. **Java was deferred at Gate G1 (D36)** and the system is built so that **adding Java, or any language, is configuration + data work, not core code changes** (Section 4.2).
**Phasing:** CORE first (Weeks 1–4), PRODUCT last (Weeks 5–6).
**This file is the single source of truth.** Edit it in place. Tick boxes as work completes. Log changes in Section 15.
Plan version: **v1.2 (folder layout refactor, 2026-10-26; status and task data unchanged since v1.1, 2026-10-12)**
>

---

## 0. HOW A NEW CHAT / TEAMMATE SHOULD READ THIS FILE

1. Read **Section 1 (Status Dashboard)** to see where we are right now.
2. Read **Section 2 (Decisions Log)** so you do not re-debate settled choices.
3. Find the current week in **Section 9**; the unchecked `[ ]` items are the work to do.
4. Never change a decision silently: add a row to Section 2 and a line to Section 15.
5. Task IDs look like `W2-P3-04` = Week 2, Person 3, task 4. Use them in commits/PRs.
6. When starting a new chat, paste this file and say “we are in Week N”.
7. Companion files: `SHIELD_Week1_Wrapup.md` (closed, evidence and outcomes) and `SHIELD_Week2_Wrapup.md` (current week, step sequence and dependencies). Folder moves: `docs/project/REFACTOR_PLAN.md` (Appendix A maps every old path to its new one).

---

## 1. STATUS DASHBOARD (update every Monday and Friday)

| Field | Value |
| --- | --- |
| Current week | **Week 2** (Week 1 closed; details in `SHIELD_Week1_Wrapup.md`) |
| Current phase | Core (W1–W4) → Product (W5–W6) |
| Start date (Day 1) | ≈ 2026-10-04 (first commit in the repo). Confirm and record the exact date |
| Final deadline | **TBD** (Q1). When set, add 6 weeks to Day 1 and record it here |
| Enabled languages | **Python, C/C++** (Java deferred, D36; `java.yaml` stays disabled) |
| Last gate passed | **G1, passed with conditions (2026-10-12)** |
| Overall health | **Amber.** G2 is reachable if the leakage-safe split manifest exists by Day 2 of Week 2 and the extraction subset is agreed on Monday (D38). Live risks: Python data independence, graph-extraction cost, Python graph quality |
| Active blockers | none hard. Four G1 conditions are carried into Week 2 (table below) |
| Last updated | 2026-10-12 |

### Gate tracker (a gate is a go/no-go checkpoint; see Section 10)

| Gate | When | Criterion | Status |
| --- | --- | --- | --- |
| G1 | End W1 | Joern spike done per language; dataset acceptance audit done; Java in/out decided (D24 → D36); core interface + API contract frozen as documents | **[x] PASSED WITH CONDITIONS (2026-10-12)** |
| G2 | End W2 | **V1/V2 safety net works on Python via library + CLI**, with per-CWE metrics recorded on the frozen **leakage-safe** split (split QA green); graph cache built for the training subset (D38) of Python and C/C++, failures logged; D35, D38 and D39 decided; G1 conditions C1–C4 closed | [ ] |
| G3 | End W3 | V3 GNN trained on both enabled languages (Python, C/C++); D20 checkpoint resolved; fix templates + verification module working | [ ] |
| G4 | End W4 | **CORE FREEZE**: V4 + interprocedural (Python and C, D28) + repo aggregation + verification loop work end-to-end via CLI. No new model work after this | [ ] |
| G5 | Mid W6 | **PRODUCT FREEZE**: no new product features after this | [ ] |
| G6 | End W6 | Release: final eval, docs, report, demo | [ ] |

### G1 conditions carried into Week 2

| # | Condition | Why it is open | Closed by | Due |
| --- | --- | --- | --- | --- |
| C1 | Per-dataset source/version/license note | D22 requires a stated license and source. Sources are in the loaders, licenses are written nowhere | W2-P1-04 | Day 2 |
| C2 | Leakage-safe splits before any metric | Both leakage docs are OPEN and block final metrics; schema has no date or CVE id (D26, D33) | W2-P1-01 (manifest), W2-P5-04 (QA) | v0 Day 2, frozen Day 4 |
| C3 | Joern graph-quality triage | Closed by D41: raw Python 45/120 NO-GO; verified C 95/100 GO; C++ 17/20 GO. Triaged Python synthetic-class context reached 120/120 but remains a transformation experiment pending source-line mapping validation. Rule A provisional | W2-P2-04 | Day 2 |
| C4 | Per-CWE and per-language metrics | `shield_core/eval/metrics.py` only gives weighted aggregates; the plan forbids a single aggregate number | W2-P3-03 | Day 3 |

Also confirm on GitHub (not visible in the repo copy): CI green on `main`, branch protection, and that a deliberately failing PR is blocked.

---

## 2. DECISIONS LOG (settled unless a row says otherwise)

| # | Decision | Choice | Reason |
| --- | --- | --- | --- |
| D1 | Graph extraction | **Joern** (CPG: AST+CFG+DFG+call graph) | One schema across languages; built-in interprocedural dataflow; MegaVul ships Joern graphs |
| D2 | Extractor abstraction | `GraphExtractor` interface in front of Joern | ML code never depends on Joern directly; swappable |
| D3 | Complementary parsing | **tree-sitter** for function-boundary extraction and fast syntax checks | Joern is too heavy for per-keystroke work |
| D4 | Python fallback | Python `ast` module if Joern’s Python frontend is too weak (decided at G1). **Not triggered: Joern Python 20/20 (D27)** | Joern’s Python support is its least mature |
| D5 | Joern runtime | Graph cache keyed by `sha256(file)+joern_version+schema_version`; server mode added in product phase | Repo-scale speed, reproducibility |
| D6 | Backend | **FastAPI**, built in Week 5 | Async, OpenAPI, in proposal |
| D7 | Frontend | **Angular**, built in Weeks 5–6 | Requested |
| D8 | Deployment | `docker-compose` local (api, redis, postgres, joern, web), assembled in Week 5 | Enough for demo |
| D9 | Job queue | Redis + Celery for repo scans (fallback: in-process asyncio queue), Week 5 | Per proposal |
| D10 | Database | PostgreSQL (SQLite for dev), Week 5 | Scan history |
| D11 | Auth | API key. GitHub OAuth is Stretch | Minimal |
| D12 | Fix generation | Template-based fixes first; **CodeT5-small + LoRA** as upgrade | Verifiable; 8 GB limit |
| D13 | Interprocedural taint | **Hybrid**: call graph merged into CPG; Joern taint queries give taint-path features + verification signal; evaluated on a curated set. **Scope narrowed by D28: cross-function claims for Python and C only.** | Function-level datasets lack interprocedural labels |
| D14 | Plan format | Single file `SHIELD_PLAN.md` in repo root | Simplicity |
| D15 | Evaluation | Per-CWE, per-language P/R/F1; single- vs multi-step breakdown; LLM baseline | Proposal Section 10 |
| D16 | Splits | Split **by project/commit group, never randomly**; chronological where dates exist; dedupe across datasets first; augmented copies stay in their source’s group. **Amended by D26/D33: schema 1.0 has no `date`, so splits are by `(project, commit)` group plus a project-disjoint holdout; chronological only where dates are recovered.** | Prevents leakage, the most common ML4Code flaw |
| D17 | Experiment tracking | MLflow (local) or W&B; every run logs config, seed, dataset hash | Reproducibility across machines |
| D18 | **Core-first phasing** | Core exposes ONLY a Python library (`shield_core.interface`) and a CLI. Backend, web app, VS Code extension are thin wrappers built in W5–W6 | Focus on core; API contract written early as a document |
| D19 | Core interface | `predict(code, language) -> Result`, `scan_repo(path) -> RepoResult`, `suggest_fix(finding) -> FixResult`; dataclasses defined in W1 and versioned | Stable seam between core and product |
| D20 | **V3 node initialization** | Gated GNN / GAT (PyG) on Joern CPGs with **frozen CodeBERT embeddings of each node’s code text as initial node features** (Vul-LMGNN style), cached by unique node string. **Fallback:** from-scratch node embeddings if this variant does not beat V1 by the Week 3 checkpoint (log the switch here) | Small per-CWE data; pretrained lexical semantics; lower training risk. Cost: GNN errors correlate more with the CodeBERT path, so measure it |
| D21 | Dataflow-feature ablation | DeepDFA-style abstract dataflow features tested as ablation variant C, not primary V3 | Data-efficient; structurally different from CodeBERT |
| D22 | **Dataset acceptance rule** | A dataset enters training only if it has: project/repo ID, commit hash or date, CWE label, language, function-level code or before/after pairs, stated license + source, and passes integrity checks (no empty code, no error strings like “404: Not Found”, parse rate acceptable). Failing the first two → prototyping or test-probe use only. **Amended by D31: screening threshold is ≥ 100 vulnerable samples per CWE; license/source note still owed (C1).** | Trustworthy splits, per-CWE evaluation, fix pairs, interprocedural context |
| D23 | **Synthetic data rules** | Synthetic samples: **train only**, tagged `source=synthetic`, generated only for CWE/language pairs below the sample threshold found in the audit, capped share of a CWE’s positives (start at 30%, a heuristic to tune), verified (parses; analyzer flags vulnerable and not fixed; human spot-check), and always paired with a **real-only vs real+synthetic ablation**. Never in validation/test | Fill gaps without inflating metrics |
| D24 | **Language plug-in architecture; Java conditional** | Every language is a `LanguageSpec` plug-in (Section 4.2). **Committed:** Python, C/C++. **Java** is enabled at G1 only if (a) Joern spike succeeds on ≥ 90% of 20 Java samples and (b) the audit finds ≥ ~300 deduped vulnerable training samples in ≥ 3 CWEs. Otherwise Java is deferred to Backlog with all plumbing ready. **Resolved at G1: deferred by team decision (D36).** | Data/tooling evidence decides; adding a language later is cheap |
| D25 | **Datasets as built (Week 1)** | C/C++: **MegaVul + Big-Vul + CVEfixes C/C++**. Python: **CVEfixes Python + Zenodo record 13870382 (`data_Python.csv`)**. PyCode-Vul, Python Vulnerabilities Full, DiverseVul and PrimeVul are **not loaded**. Confirm the Python dataset naming (Q13) | Week 1 loaders cover these five sources; CVEfixes became the Python fallback named in the Week 1 risk list |
| D26 | **Unified schema 1.0 has 8 columns** | `code, language, label, cwe, project, commit, fixed_code, source`. `cwe` is a **list** (multi-label). **No `date` and no CVE id.** Schema 1.1 (add `cve`, `date` where the source has them) is decided Monday of Week 2 (Q8, W2-P1-03) | Planned 9th column `date` was dropped by the loaders; chronological splits are therefore unavailable for now (amends D16) |
| D27 | **Joern verdict (G1): GO for Python, C and C++** | Joern **4.0.647**, image `shield-joern`; frontends `PYTHONSRC` (Python) and `NEWC` (C/C++). 60/60 samples exported (20 per C, C++, Python); 5.85 s average per sample; max peak container memory 243.5 MiB; DDG non-empty in 47/60; 30/60 flagged for review (Python 17/20). D4 (`ast` fallback) **not triggered**. File extension is part of the cache key; `.cpp` is the default | Meets the plan’s tooling bar; graph-quality gaps are tracked in W2-P2-04 |
| D28 | **Interprocedural scope narrowed** | Cross-function taint works in **Python** (chains up to 4 functions at default depth, 8 with config) and **C**. It fails through shared object state (py11) and for **C++ calls** under default call resolution. Cross-function claims are limited to Python and C; C++ is intra-function only. Cost of `maxCallDepth = 8` is measured in W2 | Taint spike results (Part A and B); refines D13 |
| D29 | **Taint is a feature generator, not a finding** | YAML source kinds: `call`, `argument` (with `arg`), `parameter`. Sinks: `arg` or `arg_from`. Sanitizers: call-name regexes, matched on the element and the call it is an argument of; `sanitizer_present` computed by us. **Only entries with an observed flow are active.** Queries are generated from the YAML (`shield_core/taint/joern_queries.py`) | Joern passes taint through unresolved calls, so “a flow exists” never means “unsanitized” |
| D30 | **Long-function policy and tokenizer** | CodeBERT pretrained tokenizer. Functions over 512 tokens: sliding windows of 510 tokens, overlap 64, masked-mean pooling per window, **mean-pool across windows**, no window cap (batch size is the VRAM control). Head+tail and max-pool are ablations. **Evaluation must include a length-only baseline** | 19–22% of C/C++ and 36% of Python functions overflow; in MegaVul 60.1% of vulnerable vs 19.7% of clean functions overflow, so length is a shortcut |
| D31 | **CWE scope and screening threshold** | Python registry: **14 CWEs** (12 core ML; CWE-502 and CWE-78 experimental; CWE-95 from the `eval` sink is auxiliary). C/C++ registry: **20 CWEs**, provisional (15 original + 369, 617, 772, 122, 674). Screening threshold **≥ 100 vulnerable samples per CWE**, 300+ independent samples preferred. Multi-label retained. Tables in Section 7.4 | Amends the ≥ ~300 rule in D24 and Section 7.2 item 7; counts are occurrences, not independent vulnerabilities |
| D32 | **Dedupe policy v0** (`shield_core/datasets/pipeline/dedupe.py`) | Token-normalized code hash with a language prefix. One retained row per hash across datasets (source priority decides the owner); CWE labels of identical code are **unioned**; hashes with conflicting binary labels are **excluded from every dataset**. No commit/CVE/project grouping and no semantic-clone detection. Input parquet files are never modified | Report: `docs/datasets/audits/dedupe_report.md`. Group-aware splitting is a separate step (D33) |
| D33 | **Evaluation guard (leakage)** | No random row-level splits. Every `(project, commit)` group stays in one partition; missing ids never form one shared group; CVE connected components where CVE ids are recovered; a **project-disjoint holdout**; per-split, per-CWE counts of rows, projects, groups and CVEs. **Final metrics are blocked until split QA passes** (W2-P5-04). The frozen C/C++ test set is carved out of MegaVul, Big-Vul and CVEfixes by project, and this is reported as a limitation (no PrimeVul) | `docs/datasets/leakage/python_cwe_data_leakage_high_risk.md` and `docs/datasets/leakage/c_cpp_cwe_data_leakage_high_risk.md` (both OPEN) |
| D34 | **Core interface and API contract frozen** | `INTERFACE_VERSION = "1.0"`, `SCHEMA_VERSION = "1.0"`, `docs/api/api_contract.md` 1.0. Five sign-offs on 2026-10-12. `interface.py` wins over the document. Field naming is snake_case (`Result.taint_paths`) | Closes the Part A naming question from the taint spike. A change now needs a new Decisions Log row and a version bump |
| D35 | **Verification verdict for hard-to-verify fixes (decided)** | Each fix template carries a re-detection rating in the template registry (internal, not in the interface): Python CWE-89 Strong; Python CWE-78 and CWE-22 Weak/None (observed: no signal); C CWE-120/787 Weak/None (expected, Week 3). Strong classes: `PASS` needs `syntax_ok`, `redetect_ok` and `tests_ok` not false. Weak/None classes: `PASS` needs `syntax_ok`, the class’s syntactic check and `tests_ok` not false; `redetect_ok` keeps the real detector result and is not a gate. `verification.notes` starts with an `[evidence]` line listing the checks that ran. Clients show which checks ran and say “verified” only if all configured checks passed. No field added; `INTERFACE_VERSION` and `SCHEMA_VERSION` stay 1.0. If the UI needs the levels machine-readable, add an optional field in a 1.x bump before W5-P4-03 | Fixtures py19 and py20 (`docs/taint/taint_spike.md`): correct CWE-78 and CWE-22 fixes are still reported as flows, and the vulnerable shapes also flow, so re-detection cannot separate fixed from unfixed code there. The old rule would reject good fixes, and a bare green badge on these classes would overstate proof. Notes-only keeps the 2026-10-12 freeze intact. Accepted by the team (reported 2026-10-15) |
| D36 | **Java deferred** | Team decision. `java.yaml` stays disabled; no Java spike and no Java data audit were run, so the D24 criteria were not evaluated. Enabled languages: **Python, C/C++**. Plumbing stays ready (Section 4.2); reconsider only after G4 | Resolves D24 and Q6 |
| D37 | **Week 1 ownership changes and Week 2 rebalance** | Registry → P4; `GraphExtractor` interface → P2; Python loaders and dedupe v0 → P3; LLM harness → Week 2; Java spike dropped. **Week 2 is balanced to 15 h per person** (Section 9) | Week 1 wrap-up; the original Week 2 left P4 at about 11 h and P1/P2/P3 at 16–18 h |
| D38 | **PROPOSED: extraction subset policy** | Extract graphs for the **training subset**, not all 455,236 deduped rows: all vulnerable rows in scope CWEs plus a sampled clean set, with a node cap; batch many functions per Joern call; run overnight across machines. Basis: 5.85 s/sample × 455,236 rows ≈ 740 h single-threaded (an estimate; the spike time may include per-run start-up). Decide Monday after the W2-P2-05 benchmark. Benchmark numbers: docs/graphs/extraction_report.md (W2-P2-05). | Full extraction is not feasible in Week 2; vulnerable rows alone number 29,855 (≈ 49 h at the same rate)  |
| D39 | **PROPOSED: Python negatives** | Zenodo Python has only positives (1,906 rows) and CVEfixes Python has 1,982 label-0 rows. Build label-0 rows from the patched code (`fixed_code`) of the same commit, tagged by source and **kept in that commit’s group** (D16). Decide Monday with P3 | Without negatives, Python V1 cannot be trained from Zenodo |
| D40 | **Repository folder layout refactor (R1-R9), no behaviour change** | R1 one importable root: `languages/` and `eval/` moved into `shield_core/`. R2 folders are named for the job (`fixgen` to `fix/templates`, `c_cpp_loaders` and `python_loaders` to `loaders`, `pyg-gnn` to `tutorials/pyg`). R3 `datasets/` follows the data chain: `cvefixes_build/`, then `loaders/`, then `pipeline/`. R4 `scripts/` is grouped by purpose (`data_audit/`, `embeddings/`, `graphs/`, `spikes/`, `training/`, `tutorials/`). R5 `tests/` mirrors `shield_core/`. R6 `docs/` is grouped by topic. R7 no `__file__` arithmetic: paths come from `shield_core/paths.py`. R8 every code folder has a `README.md`, enforced by `tests/test_layout.py`. R9 no folder named `data/` below the repo root. Also: the `.gitignore` rule `sample*/` is anchored to `/sample*/`; `train_v1.py` now reads `docs/datasets/audits/dataset_manifest_v0.json` and writes to `model_artifacts/train_runs/`. | New teammates could not tell audits from training from spikes; moving a file silently broke `parents[N]` path counting; the unanchored `sample*/` rule would have ignored the new `datasets/samples/` folder. Verified: 637 tests passed before and 680 after (637 plus 43 new layout tests), ruff clean, CI green. **Not yet run on real data:** the `dedupe`, `merge` and `splits` commands. Old-to-new map: `docs/project/REFACTOR_PLAN.md`, Appendix A. Merged 2026-10-26 |
| D41 | **Joern graph-quality triage (W2-P2-04)** | Frozen usability thresholds: line-numbered real METHOD, CFG edge, REACHING_DEF when expected flow > 0, and UNKNOWN share ≤5%; GO ≥85%, GO-WITH-LIMITS 70–<85%, NO-GO <70%. Current raw path: Python 45/120 NO-GO (95% Wilson 0.2935–0.4642); verified C 95/100 GO (0.8882–0.9785); C++ 17/20 GO (0.6396–0.9476). BigVul-derived rows labeled C were metadata `cpp` and excluded from C evidence. A triage-only synthetic-class context yielded Python 120/120 usable, but it shifts source lines and is not production evidence until mapping is validated. Recommendation: apply it consistently to indented Python method excerpts in production and correct the source-line offset before extraction. **Rule A** is the provisional first-build stub policy; revisit in the Week-3 ablation. | Manual review, seeded scale checks, `docs/graphs/joern_triage.md`, `docs/graphs/joern_triage_review.csv` |
| D42 | **CPG-to-PyG converter contract (W2-P2-01)** | Converter 1.0 in `shield_core/graph_dataset/`; raw graph schema stays `0.1-draft`. Fixed node/edge ids, hash64 node-text join key, quality diagnostics, Rule A default, Rule B ablation, and skip-not-truncate cap behavior. Shared default cap 750 meets the rule on Python (97.3%, 2.67 pp) and C/C++ (96.7%, 4 pp); 500 is the smallest passing cap for the C/C++ subset alone. Subset results are not corpus-wide; revisit with full P1 splits/cache. | `docs/graphs/pyg_dataset_report.md`, `docs/graphs/pyg_dataset_report_cpp.md` |

### Source-data issues found (status after Week 1)

**From the original plan**

- **Proposal V1 says “Big-Vul or Devign, Python subset.”** Both are C/C++. *Resolved (D25):* Python data is CVEfixes Python + Zenodo 13870382; Big-Vul is on the C/C++ track.
- **Proposal Section 4 excludes C/C++ memory safety.** *Resolved:* included for C/C++ (CWE-119/120/125/787/416/476/190/122 and others, D31).
- **Kaggle re-uploads fail D22.** *Closed:* not used.
- **“Vulnerability Fix Dataset” language coverage disputed.** *Dropped:* not loaded. Fix pairs come from CVEfixes `fixed_code` and the Zenodo `patch` column (W3-P1-02).
- **Known label noise** (Big-Vul ~46%, Devign ~20% in manual studies). *Open:* the hand-check sample was not done in Week 1; the team does it in Week 2 (100 rows, 20 each).
- **CodeBERT 512-token limit.** *Resolved (D30).*

**New findings from Week 1 (act on these)**

1. **No `date` and no CVE id in the schema (D26).** Chronological splits and CVE-level grouping are not possible until schema 1.1.
2. **Zenodo Python rows are all positives** (1,906 of 1,906). Python negatives come from CVEfixes patched functions (1,982) unless D39 is adopted. Zenodo also lacks `commit` on 55 rows and `project` on 2.
3. **Python CWEs are concentrated in few commits.** One commit holds 56.0% of CWE-352, 46.0% of CWE-444, 43.4% of CWE-613, 35.7% of CWE-918, 34.0% of CWE-400. CWE-444 has 9 commit groups, CWE-613 has 11. C/C++ is broader (CWE-190: 19.9% in one group, CWE-400: 17.8%). Row-level deduplication does not make these independent (D33).
4. **Length is a label shortcut in MegaVul and Big-Vul** (vulnerable over 512 tokens: 60.1% vs 19.7% in MegaVul, 41.5% vs 17.3% in Big-Vul). V2’s length features are the most exposed (D30).
5. **The token-length numbers were measured on an earlier dedupe** (for example CVEfixes C/C++ 2,628 rows vs 8,985 in the final dedupe). Re-measure on the final files (W2-P3-05).
6. **Cross-dataset overlap in `dataset_audit.md` is 0 by construction**, because it is computed after dedupe. It checks the dedupe, not independence. The real overlap was 58,206 shared hashes between MegaVul and Big-Vul, plus 3,191 (MegaVul/CVEfixes C++) and 2,248 (Big-Vul/CVEfixes C++).
7. **Label conflicts were excluded, not resolved:** 1,577 (MegaVul), 3,318 (Big-Vul), 1,632 (CVEfixes C++), 346 (CVEfixes Python) hashes with 0/1 conflicts.
8. **No license notes exist** for any dataset (D22, W2-P1-04).
9. **The audit is PRELIMINARY.** It covers schema, empty code and duplicate hashes only. It does not validate that commits are security fixes or that CWE labels are right.

---

---

## 3. SCOPE TIERS (cut in reverse order if we fall behind)

**MUST**

- V1 (CodeBERT frozen + XGBoost) on Python, usable via library + CLI
- V3 (GNN over CPG) and V4 (fusion) on Python + C/C++
- Per-CWE evaluation + ablation (V1 vs V3 vs V4 vs LLM)
- Template-based fix + syntax/re-detection verification
- Web app (minimum: submit code, view results) on FastAPI
- `LanguageSpec` plug-in architecture (Section 4.2)

**SHOULD (full target)**

- Java enabled (deferred at G1, D36; reconsider only after G4)
- File- and repo-level aggregation
- Interprocedural taint (hybrid, D13)
- Web dashboard (repo summary, history, fix diff viewer)
- VS Code extension
- CVE mining pipeline + multi-dataset merge pipeline (runnable on demand)

**STRETCH**

- Augmentation + gated synthetic data generator (D23)
- CodeT5 learned fixes; regression check; ranked multi-candidate fixes
- GitHub OAuth; GitHub Action; scheduled (cron) mining
- Explainability (node/attention highlighting)

**CUT ORDER when behind** (first cut → last): Stretch → GitHub Action/OAuth → CodeT5 → **VS Code extension** → Java (if enabled) → interprocedural depth (keep intra-file) → web dashboard polish (keep submit + results). **Never cut V1, the CLI, or Python + C/C++ core.**

---

## 4. ARCHITECTURE

### 4.1 Pipeline (target end-state)

```
Source (Python, C/C++, [Java])
   │  LanguageSpec registry selects per-language adapters
   ├─ tree-sitter ──► function boundaries, syntax check
   └─ GraphExtractor (Joern) ──► CPG (AST+CFG+DFG+call graph) + taint paths
                                     │
        ┌────────────────────────────┴─────────────┐
   CodeBERT path                              Graph path
   (tokens → embedding, 512-token strategy)   (CPG → PyG Data, CodeBERT node init → GNN → graph embedding)
        └───────────────► FUSION LAYER ◄───────────┘
                               │
                 Classifier: vulnerable? + CWE + confidence
                               │
                 Fix Generator (templates → CodeT5)
                               │
        Verification: syntax → tests (sandboxed) → re-detection → (regression)
                               │
                   PASS → recommended fix / FAIL → reject

   ════════ CORE (W1–W4) ends here: library + CLI ════════
   PRODUCT (W5–W6): Angular web app + VS Code extension → FastAPI → shield_core
                    (+ Celery/Redis, PostgreSQL, Joern server)
```

### 4.2 Language plug-in contract (this is what makes Java easy to add)

Nothing outside the registry may hard-code a language. Each language is one `LanguageSpec` (a config file + small adapters):

| Field | Meaning |
| --- | --- |
| `id`, `extensions` | e.g., `python` / `.py` |
| `treesitter_grammar` | grammar for function extraction and syntax check |
| `joern_frontend` | Joern language frontend and pinned settings |
| `dataset_loaders` | loader + schema map for each dataset covering this language |
| `cwe_list` | final CWE targets after the audit (D22 thresholds) |
| `source_sink_config` | taint sources, sinks, sanitizers for Joern queries |
| `fix_templates` | template fixes per CWE |
| `test_runner` | how the sandbox runs a project’s tests (e.g., pytest) |
| `eval_sets` | test-probe sets and interprocedural cases |

**Checklist: adding a language later (e.g., Java).** Estimated at a few person-days once the registry exists (an estimate, not measured):

- [ ]  Write its `LanguageSpec` file
- [ ]  Joern spike (≥ 20 samples) passes the success threshold
- [ ]  Add loaders/schema maps for its datasets; pass D22; rerun dedupe + merge
- [ ]  Set its CWE list from the audit counts
- [ ]  Batch-extract graphs; cache
- [ ]  Train V1/V3/V4 per-language runs with existing scripts (no new model code)
- [ ]  Add source/sink config and fix templates for top CWEs
- [ ]  Add its eval sets; add rows to the per-CWE tables
- [ ]  Enable it in config (API, web app, and extension read the enabled list automatically)

### 4.3 Repository layout

The tree below is the layout **as built after the folder refactor (D40, 2026-10-26)**. Items marked *(planned)* do not exist yet. Every code folder has its own `README.md`; `tests/test_layout.py` fails CI if one goes missing, if an import stops resolving, or if a README mentions a path that does not exist.

```
shield/
├─ README.md · SHIELD_PLAN.md · pyproject.toml · .pre-commit-config.yaml · .gitignore · .gitattributes
├─ .github/                  # workflows/ci.yml, pull_request_template.md
├─ docker/joern/             # pinned Joern image + smoke test
├─ requirements/             # pinned GPU torch wheel
├─ shield_core/              # THE LIBRARY: everything importable lives here (R1)
│  ├─ interface.py           # D19 dataclasses + predict / scan_repo / suggest_fix
│  ├─ cli.py                 # `shield scan` (built); `scan-repo` and `fix` (planned)
│  ├─ tracking.py            # MLflow / W&B helper (D17)
│  ├─ paths.py               # repo root and data/ docs/ folders; never count .parent from __file__ (R7)
│  ├─ languages/             # registry.py + python.yaml, cpp.yaml, java.yaml (disabled, D36)
│  ├─ datasets/              # the data chain: cvefixes_build/ -> loaders/ -> pipeline/ (R3)
│  │  ├─ schema.py · project_names.py · cwe_taxonomy.py (planned)
│  │  ├─ cvefixes_build/     # CVEfixes zip -> database -> per-language CSV tables
│  │  ├─ loaders/            # one loader per source: MegaVul, Big-Vul, CVEfixes C/C++, CVEfixes Python, Zenodo
│  │  ├─ samples/            # seeded 20-row samples for the spikes
│  │  └─ pipeline/           # dedupe -> project_normalization -> merge -> splits
│  ├─ extraction/            # graph_extractor.py, joern_extractor.py, cache.py (ts_utils.py planned)
│  ├─ taint/                 # joern_queries.py (queries generated from the language YAML)
│  ├─ embeddings/            # embedder.py (functions), node_embeddings.py (graph nodes)
│  ├─ models/                # registry.py + models.yaml; v1_xgb/, gnn/, fusion/ (planned)
│  ├─ fix/templates/         # sql, command, path (+ base, strings, astutil)
│  ├─ verify/                # pysource, pattern_checks, evidence
│  ├─ eval/                  # metrics.py; ablation.py and llm_baseline.py (planned)
│  ├─ synthetic/             # (planned, gated by D23)
│  └─ mining/                # (planned, W3-P1-01)
├─ scripts/                  # runnable entry points, grouped by purpose (R4); may import shield_core, never the reverse
│  ├─ data_audit/            # acceptance_check, explore_*, absent-commit check, split_qa (empty placeholder)
│  ├─ embeddings/            # token lengths, long-function windows, bulk embedding jobs
│  ├─ graphs/                # graphml_to_pyg, try_extractor, filter_counts, inspect_export/
│  ├─ spikes/                # joern/ (go/no-go), taint/ (taint spike driver)
│  ├─ training/              # train_v1.py
│  └─ tutorials/             # demo_tracking.py, pyg/ (PyG lessons + toy GNN)
├─ tests/                    # mirrors shield_core (R5): interface/ languages/ models/ embeddings/ datasets/ extraction/ taint/ fix/ verify/ eval/, plus fixtures/ and test_layout.py
├─ docs/                     # grouped by topic (R6): api/ datasets/{audits,exploration,leakage,project_names}/ graphs/ taint/ fixes/ modeling/ project/
├─ data/                     # raw/ interim/ cache/ (git-ignored; no other folder may be called data/, R9)
├─ model_artifacts/          # model files the registry loads; train_runs/ holds train_v1.py output (git-ignored)
├─ api/                      # created in W5 (FastAPI)
├─ web/                      # created in W5 (Angular)
└─ vscode-ext/               # created in W5 (TypeScript)
```

**Notes on the layout**

- Old-to-new path for every moved file: `docs/project/REFACTOR_PLAN.md`, Appendix A. The README (section 5) has a "Where does my new file go?" table.
- `languages/` and `eval/` used to be top-level packages; they now live in `shield_core/`, so `pyproject.toml` needs no special entries for them.

### 4.4 API contract (written in W1 as a document; implemented in W5)

| Endpoint | Purpose |
| --- | --- |
| `POST /v1/scan/snippet` | `{code, language}` → `{vulnerable, cwe, confidence, findings[], taint_paths[]}` |
| `POST /v1/scan/repo` | repo URL or zip → `{job_id}` (async) |
| `GET /v1/jobs/{id}` | job status + aggregated results |
| `POST /v1/fix` | finding → candidate fix + verification report |
| `GET /v1/scans`, `GET /v1/scans/{id}` | history |
| `GET /v1/languages` | enabled languages (from the registry) |
| `GET /v1/health`, `GET /v1/models` | health, model versions |

Request/response shapes mirror the D19 dataclasses so the backend is a thin wrapper.

---

## 5. TEAM, ROLES, AND HOURS

All five have all skills. Roles are **workstream ownership** with a named cross-reviewer. Ownership shifts in the product phase. Names were filled in at the end of Week 1.

| ID | Name | Core phase (W1–W4) | Product phase (W5–W6) | Reviewer |
| --- | --- | --- | --- | --- |
| P1 | Hatem | **Data & Extraction**: datasets + acceptance audit, merge/dedupe/splits, Joern batch extraction, repo aggregation, CVE mining | Backend: Joern server, Celery/Redis repo jobs, DB | P2 |
| P2 | Eyad | **Graph & Taint**: `GraphExtractor` interface, PyG dataset, GNN (V3), interprocedural taint | **VS Code extension** | P1 |
| P3 | Atef | **Semantic, Fusion & Eval**: CodeBERT, node-embedding cache, XGBoost (V1/V2), V4 fusion, calibration, ablations, Python loaders, dedupe | Final frozen-test evaluation, model cards, serving integration | P4 |
| P4 | Bigad | **Fix, Verification & Contracts**: `interface.py`, API contract, `LanguageSpec` registry, CLI, templates, verification loop, model registry | **FastAPI core** + auth + `/fix` | P3 |
| P5 | Maram | **Tooling, Baselines & Infra**: CI/envs, Joern image, MLflow, LLM baseline, tree-sitter utils, split QA, sandbox runner, repo ingestion, augmentation | **Angular web app** + docker-compose | P4 |

Names come from the interface sign-off table (2026-10-12). Weekly availability is still open (Q2).

**Week 1 ownership changes (D37):** registry P1 → P4, `GraphExtractor` interface P1 → P2, Python loaders and dedupe v0 → P3, Java spike dropped (D36), LLM harness moved to Week 2.

**Week 2 balance (D37):** every person is planned at 15 h (75 h total). By this plan’s own estimates the original Week 2 left P4 at about 11 h and P1, P2, P3 at 16–18 h. Urgent hours still differ (P1 carries the data chain), so each critical task has a named backup in the Week 2 section.

**Suggested hours per person per week:** W1–W3: **15 h**, W4–W5: **20 h**, W6: **18 h** → ≈ **515 person-hours**. Adjust for exams; record real availability in the dashboard.

**Working agreements**

- Feature branches + pull requests; every PR gets one reviewer from the table before merge.
- Daily 10-min async standup. Two 45-min syncs per week (Mon plan, Thu integration).
- `main` is always runnable. CI runs lint + unit tests on every PR.
- Shared interfaces (D19, API contract, `LanguageSpec`) change only by agreement and a Decisions Log row.

---

## 6. COMPUTE PLAN (multiple GPUs; ceiling = RTX 4060, 8 GB VRAM each)

| Job | Feasible approach |
| --- | --- |
| CodeBERT embeddings (frozen, V1 + node text) | Inference only, fp16, batch 32, max_len 512; cache to disk (nodes cached by unique string) |
| CodeBERT fine-tune (optional, V4) | fp16 + gradient accumulation, batch 8; freeze lower layers if OOM |
| GNN (gated GNN / GAT) | Function-level graphs; cap nodes per graph (e.g., 500–1000), drop oversized samples; PyG mini-batching |
| CodeT5 fix model (stretch) | `codet5-small` (or base) + LoRA + fp16 + gradient checkpointing |
| Joern batch extraction | CPU/RAM-bound; overnight, parallel; cache all graphs |

**The team has multiple GPUs; the RTX 4060 (8 GB) is the ceiling per GPU, so every job must fit in 8 GB.** GPUs are on separate machines: no distributed training; parallelism comes from splitting experiments across members.

- Record each member’s GPU model and VRAM in Section 14 (Q5); route heavy jobs to the strongest GPUs. One machine is recorded so far: RTX 4060 Laptop, 8 GB.
- Cache embeddings and graphs once and share them (DVC remote or shared drive).
- Fix seeds and log every run (D17) so results from different machines are comparable.
- Colab/Kaggle only as overflow.

**Measured in Week 1 (RTX 4060 Laptop 8 GB unless noted)**

- CodeBERT fp16, 512-token windows, overlap 64: **131.3 chunks/s at batch 16 (0.40 GB peak)**, 110.2 chunks/s at batch 128 (1.50 GB peak). A larger batch was slower. Full MegaVul needs about 500,000 chunks (1.47 chunks per function on a non-random 5,000-row sample).
- Joern historical spike (60 samples): 5.85 s average (4.23-6.06 s), 214.5 MiB average and 243.5 MiB maximum peak. **Superseded planning estimate:** 740 h for all 455,236 rows was a single-thread extrapolation from that spike. W2-P2-05 measured production-path A at 4.847/5.049/5.451 s/sample (C/C++/Python); E5 A at four workers reached 0.606/0.558/0.503 samples/s. Batched C/b20 was faster but failed per-file fidelity for all tested groups, so current projections use A. Full results: `docs/graphs/extraction_report.md`.
- Toy GNN (MUTAG, 100 epochs): 4.6 s, 17.2 MB peak VRAM. Reproduced on one machine only.

---

## 7. DATA PLAN

### 7.1 Datasets and their role

| Dataset | Language | Role | Notes |
| --- | --- | --- | --- |
| **CVEfixes** (original release + collection script) | multi-language | Primary for Python (and Java if enabled); also C/C++ | Fixes the Python/Java data gap; the script doubles as the CVE mining pipeline. Label noise: all functions in a fix commit are marked vulnerable |
| Python Vulnerabilities Full (Kaggle) | Python | Training | Verify it passes D22 (project, commit/date, CWE) |
| PyCode-Vul | Python | Supplement | Verify D22 |
| **MegaVul** | C/C++ (and Java) | Training + pre-extracted Joern graphs | Commit-heuristic labels; some “undecidable” patches |
| Big-Vul | C/C++ | Training (after audit) | Noisy labels; heavy overlap with others |
| **DiverseVul** (original release) | C/C++ | Training after dedupe | ~60% reported label accuracy; overlaps Big-Vul/MegaVul |
| **PrimeVul** | C/C++ | **Test only** | Deduped, chronological, better labels; excludes multi-function vulnerabilities |
| Juliet C/C++ (and Java) | C/C++ (Java) | Interprocedural eval set; optional training after name-scrubbing | Synthetic, file-level; function names can leak labels, so scrub |
| Vul4J | Java | Verification loop + Java eval (only if Java enabled) | Small; reproducible with tests |
| SecurityEval, SVEN | Python (SVEN also C/C++) | Test probes only | Tiny; do not tune on them |
| Vulnerability Fix Dataset | verify | Fix pairs for templates/CodeT5 | Language coverage disputed; verify |
| CVE & CWE Dataset (1999–2025) | n/a | CVE mining + CWE reference only | Not for training |
| Prototyping only |  | Kaggle “CVEfixes Dataset” re-upload, “DiverseVul-Cleaned” | Fail D22 |
| Excluded |  | CrossVul (poor label accuracy; overlaps CVEfixes), Attacks & Defense 2026, Python OSV/CVSS, CVEs for NLP, Vulnerable C Functions | Not used |

### 7.1a Datasets as built in Week 1 (D25)

Row counts are from `docs/datasets/audits/dedupe_report.md` and `docs/datasets/audits/dataset_audit.md` (post-dedupe, `label` 1 = vulnerable). The role column in 7.1 above is the target; this table is what exists.

| Dataset (`source`) | Language | Raw rows | Deduped rows | Vulnerable (label 1) | Notes |
| --- | --- | --- | --- | --- | --- |
| MegaVul | C/C++ | 353,858 | 336,548 | 16,394 | 15,733 internal duplicates removed |
| Big-Vul | C/C++ | 217,007 | 103,234 | 5,803 | 58,206 rows removed as duplicates of MegaVul |
| CVEfixes C/C++ | C/C++ | 15,222 | 8,985 | 3,171 | 4,386 cross-dataset duplicates removed |
| CVEfixes Python | Python | 4,943 | 4,563 | 2,581 | 1,982 label-0 rows (patched functions); 648 `(project, commit)` groups among positives |
| Zenodo 13870382 `data_Python.csv` (`zenodo_python`) | Python | 2,316 | 1,906 | 1,906 | **positives only**; 55 rows without commit; 436 groups |
| **Total** |  | **593,346** | **455,236** | **29,855** |  |

Not loaded: PyCode-Vul, Python Vulnerabilities Full, DiverseVul, PrimeVul, Juliet, Vul4J, SecurityEval/SVEN. The Zenodo record describes itself as a function-level multi-language set with a commit date column; the loader currently drops the date (D26).

### 7.2 Pipeline rules

1. Run `acceptance_check.py` (D22) on every dataset; record results in the audit report.
2. Normalize all CWE labels to one taxonomy (`cwe_taxonomy.py`).
3. Dedupe **within and across** datasets (normalized-code hash + near-duplicate check + (repo, commit, function) match where available) before splitting.
4. Split by project/commit group; chronological where dates exist; keep a frozen test set no one tunes on (D16).
5. Handle class imbalance (class weights / focal loss / careful sampling) and report it.
6. Audit label noise on a random sample per dataset; record findings.
7. **Per-language CWE targets are set after the W1 audit**: keep a CWE only if it has ≥ ~300 deduped vulnerable training samples in that language (threshold is a heuristic; adjust with evidence). **Amended by D31: the screening threshold is ≥ 100 vulnerable samples, with 300+ independent samples preferred.** Candidates: Python 89/79/78/22/798/502/327; C/C++ memory-safety set; Java 89/79/78/22/502/611/327 (if enabled).
8. **Interprocedural evaluation set** (small, curated): cross-function cases from Juliet (scrubbed) and hand-written Python cases. Verify licensing/availability.

**Status of these rules after Week 1**

1. Acceptance check: **done as a preliminary pass** (`scripts/data_audit/acceptance_check.py`, `docs/datasets/audits/dataset_audit.md`); license/source note still owed (C1).
2. One CWE taxonomy: labels are normalized to `CWE-<n>` lists in `schema.py`; the taxonomy file and parent/child handling (119 vs 120/125/787/122) are W2-P1-01 and Q12.
3. Dedupe within and across datasets: **v0 done** (D32). No commit/CVE grouping and no near-duplicate check yet.
4. Group-aware splits and a frozen test set: **not done; blocks every final metric** (D33, C2).
5. Class imbalance: measured (Big-Vul 5.6% vulnerable, MegaVul 4.9%, CVEfixes C++ 35.3%, CVEfixes Python 56.6%); handling is a V1 task.
6. Label-noise audit: **not done**; Week 2 team hand-check.
7. Per-language CWE targets: **provisional lists are in the YAMLs** (D31); final after split-level counts exist.
8. Interprocedural evaluation set: Week 4, Python and C only (D28).

### 7.3 Synthetic data (D23)

Priority order: (1) more real data (CVEfixes + mining); (2) semantics-preserving augmentation on train only (renaming, reordering independent statements); (3) Juliet-style template code for interprocedural and low-count CWEs; (4) LLM-generated vulnerable/fixed pairs kept only if verified. Synthetic labels from an analyzer may make the model imitate the analyzer: report this as a limitation. Test on real held-out data only.

### 7.4 CWE scope after the Week 1 audit (D31)

Source: `docs/datasets/audits/python_cwe_commit_audit.csv` and `docs/datasets/audits/cpp_cwe_commit_audit.csv` (vulnerable rows only, multi-CWE rows counted once per CWE, groups are unique `(project, commit)` keys). These are **occurrences, not independent vulnerabilities**. A class with few groups cannot support a meaningful per-CWE test result after group-aware splitting.

**Python registry (14 CWEs)**

| CWE | Vulnerable samples | Commit groups | Projects | Largest group share (%) | Scope |
| --- | --- | --- | --- | --- | --- |
| CWE-918 | 319 | 36 | 24 | 35.7 | core |
| CWE-79 | 283 | 118 | 101 | 9.2 | core |
| CWE-601 | 249 | 37 | 33 | 19.3 | core |
| CWE-22 | 242 | 71 | 62 | 14.5 | core |
| CWE-444 | 215 | 9 | 6 | 46.0 | core; very few groups |
| CWE-613 | 198 | 11 | 8 | 43.4 | core; very few groups |
| CWE-352 | 193 | 25 | 19 | 56.0 | core; one commit dominates |
| CWE-94 | 185 | 28 | 26 | 18.4 | core |
| CWE-400 | 156 | 16 | 14 | 34.0 | core; concentrated |
| CWE-20 | 150 | 57 | 41 | 7.3 | core |
| CWE-200 | 126 | 33 | 28 | 18.3 | core |
| CWE-89 | 100 | 31 | 31 | 14.0 | core; exactly on threshold |
| CWE-502 | 86 | 22 | 19 | 24.4 | experimental (below 100) |
| CWE-78 | 64 | 25 | 24 | 10.9 | experimental (below 100) |

**C/C++ registry (20 CWEs, provisional).** The first 15 come from the three-source audit; the five marked “added” were screened in the later combined audit.

| CWE | Vulnerable samples | Commit groups | Projects | Largest group share (%) | Note |
| --- | --- | --- | --- | --- | --- |
| CWE-119 | 2,779 | 1,189 | 275 | 3.9 | original |
| CWE-125 | 2,271 | 1,050 | 263 | 9.0 | original |
| CWE-787 | 2,189 | 952 | 314 | 9.3 | original |
| CWE-20 | 1,899 | 763 | 164 | 4.6 | original |
| CWE-476 | 1,485 | 802 | 203 | 1.8 | original |
| CWE-416 | 1,312 | 629 | 135 | 1.8 | original |
| CWE-190 | 1,100 | 417 | 179 | 19.9 | original; review top commit |
| CWE-200 | 844 | 381 | 91 | 3.8 | original |
| CWE-362 | 685 | 260 | 51 | 5.1 | original |
| CWE-120 | 553 | 240 | 127 | 8.7 | original |
| CWE-400 | 415 | 130 | 52 | 17.8 | original; review top commit |
| CWE-617 | 327 | 146 | 51 | 9.5 | added |
| CWE-835 | 300 | 174 | 61 | 4.3 | original; experimental |
| CWE-401 | 298 | 207 | 67 | 3.4 | original; experimental |
| CWE-415 | 280 | 129 | 73 | 12.1 | original; review top commit |
| CWE-772 | 228 | 163 | 29 | 10.5 | added; experimental |
| CWE-22 | 221 | 97 | 74 | 10.9 | original; review top commit |
| CWE-369 | 193 | 139 | 54 | 4.1 | added |
| CWE-122 | 158 | 72 | 12 | 7.0 | added; only 12 projects |
| CWE-674 | 142 | 54 | 34 | 10.6 | added; experimental |

Notes: CWE-119 is a parent of CWE-120/125/787/122, so single-label training would mix levels (Q12). The Python `eval` sink reports CWE-95, which is not one of the 14; it is exposed as an auxiliary finding. Counts for the C/C++ rows come from the CSV; the older two-source table in `docs/datasets/audits/cwe_lists_python_cpp.md` is not comparable.

---

## 8. EVALUATION PLAN (owner: P3)

- [ ]  Per-CWE, per-language precision / recall / F1 (no single aggregate accuracy)
- [ ]  Models compared: V1 · V2 · V3 (GNN only) · V4 (fusion) · general-purpose LLM baseline (same code, fixed prompt)
- [ ]  Single-step vs multi-step (flow-dependent) breakdown, the ablation that justifies fusion
- [ ]  Interprocedural set: with vs without taint/call-graph features
- [ ]  V3 node-initialization ablation: A (from scratch) vs B (CodeBERT-init) vs C (dataflow features)
- [ ]  Error correlation between GNN and V1 (evidence for or against “complementary failure modes”)
- [ ]  Real-only vs real+synthetic training ablation (if synthetic data is used)
- [ ]  C/C++ generalization check: **PrimeVul is not loaded (D25)**; use the project-disjoint holdout (D33), report the limitation, add a PrimeVul loader only if time allows (Q14)
- [ ]  Fix success rate: % of detections with a verified (syntax-valid + re-detected-as-fixed) fix
- [ ]  Latency/throughput: snippet scan, repo scan (cached vs uncached)
- [ ]  Failure-case analysis and honest limitations section
- [ ]  Reproducibility: seeds, configs, dataset hashes in MLflow/W&B
- [ ]  Split QA report per split and per CWE (rows, projects, commit groups, CVEs, concentration) published with every metrics table (D33)
- [ ]  Length-only baseline next to V2 (D30)
- [ ]  Project-disjoint evaluation, with the CWE coverage it loses (D33)

---

## 9. WEEK-BY-WEEK PLAN WITH CHECKLISTS

Legend: `[ ]` todo · `[~]` in progress · `[x]` done. Task ID = `W<week>-P<person>-<n>`. “Enabled languages” = the list in the dashboard.

# PHASE A — CORE (Weeks 1–4)

### WEEK 1 — Foundations, Spikes, Contracts → Gate G1 (**CLOSED 2026-10-12: passed with conditions**)

**Goal (met):** de-risk Joern, audit data, decide Java, freeze the core interface, start V1. Task IDs below are the **actual** IDs used after the Week 1 rebalance (D37). Full detail, outcomes and evidence: `SHIELD_Week1_Wrapup.md`.

**P1 — Data & Extraction (Hatem)**

- [x]  W1-P1-01 Unified schema + loaders. *Outcome:* 8-column schema (D26); loaders for MegaVul, Big-Vul, CVEfixes C/C++, CVEfixes Python (Python loaders were P3’s task, below); parquet in `data/interim/`. *Residual:* source/version/license note not written → W2-P1-04
- [x]  W1-P1-02 Joern spike (Python, C, C++). *Outcome:* 60/60 exported, GO (D27). *Residual:* graph-quality triage → W2-P2-04
- [x]  W1-P1-04 Dataset acceptance audit (D22). *Outcome:* `docs/datasets/audits/dataset_audit.md` = **PRELIMINARY PASS**; CWE lists and leakage reports written. *Residual:* label-noise hand-check → W2 team task; license note → W2-P1-04

**P2 — Graph & Taint (Eyad)**

- [~] W1-P2-01 PyG setup + toy GNN. *Outcome:* works on one machine (RTX 4060 Laptop). *Residual:* second-machine run and GPU table → W2-P5-05
- [x]  W1-P2-02 CPG → PyG design. *Outcome:* `docs/graphs/graph_schema.md` (`0.1-draft`, TENTATIVE items listed)
- [x]  W1-P2-03 Taint spike. *Outcome:* `docs/taint/taint_spike.md`, sources/sinks/sanitizers in both YAMLs, query generator and driver (D28, D29)
- [x]  W1-P2-04 `GraphExtractor` interface + cache key (was P1). *Outcome:* `extraction/graph_extractor.py`, `cache.py`, `joern_extractor.py`, `tests/extraction/test_graph_cache.py`; the C++ extension bug was found and fixed

**P3 — Semantic, Fusion & Eval (Atef)**

- [x]  W1-P3-01 CodeBERT embedding script. *Outcome:* 131.3 chunks/s at batch 16, 0.40 GB peak VRAM; windowed long-function embedder
- [~] W1-P3-02 Metrics module. *Outcome:* weighted aggregate P/R/F1 and confusion matrix only. *Residual:* per-CWE, per-language, multi-label → W2-P3-03 (C4)
- [x]  W1-P3-03 Long-function strategy. *Outcome:* `docs/modeling/long_function_policy.md` (D30). *Residual:* numbers are from an earlier dedupe → W2-P3-05
- [x]  W1-P3-04 Python loaders (CVEfixes Python, Zenodo Python)
- [x]  W1-P3-05 Dedupe v0. *Outcome:* `shield_core/datasets/pipeline/dedupe.py`, `docs/datasets/audits/dedupe_report.md` (D32)

**P4 — Fix, Verification & Contracts (Bigad)**

- [x]  W1-P4-01 `interface.py` (D19) + sign-off. *Outcome:* v1.0, five sign-offs (D34)
- [x]  W1-P4-02 `docs/api/api_contract.md`. *Outcome:* v1.0, mirrors the dataclasses
- [x]  W1-P4-03 CLI skeleton. *Outcome:* `shield scan` returns a stub `Result`, language errors list enabled languages from the registry
- [x]  W1-P4-04 Fix template survey. *Outcome:* `docs/fixes/fix_template_survey.md`; verdict question → D35 (open)
- [x]  W1-P4-05 `LanguageSpec` registry (was P1). *Outcome:* `shield_core/languages/registry.py`, `python.yaml`, `cpp.yaml`, disabled `java.yaml`, and the no-language-literals test

**P5 — Tooling, Baselines & Infra (Maram)**

- [x]  W1-P5-01 Repo, CI, pre-commit. *Outcome:* `ci.yml` (ruff, format check, pytest on 3.12), pre-commit, PR template. *Confirm on GitHub:* branch protection, failing-PR block, CI green
- [x]  W1-P5-02 Pinned environments, Joern Dockerfile, tree-sitter. *Outcome:* image with Joern 4.0.647, Java 21, tree-sitter Python/C/C++, smoke test (no Java grammar, D36)
- [x]  W1-P5-03 MLflow/W&B helper. *Outcome:* `shield_core/tracking.py` + tests (D17)
- [—] W1-P5-04 LLM-baseline harness. *Moved to Week 2 (W2-P5-01).*
- [—] W1-P5-05 Java Joern spike. *Dropped (D36).*

**Gate G1 checklist (result)**

- [x]  Joern spike results recorded per language (Python, C, C++: GO, D27). Java not spiked (D36). The explicit verdict sentence is now in the plan; add it to `docs/graphs/joern_spike.md` too (W2-P2-04)
- [x]  **D24 decided:** Java deferred (D36); dashboard “Enabled languages” updated
- [x]  Per-language CWE lists recorded in the `LanguageSpec` files (Python 14, C/C++ 20, provisional, D31)
- [x]  Core interface (D19) and API contract frozen, five sign-offs on 2026-10-12 (D34)
- [~] CI green on `main`: ruff, format check and 184 tests pass locally (two torch-dependent test files not run); confirm the GitHub run
- [~] Dataset acceptance audit: preliminary pass; conditions C1–C4 above

---

### WEEK 2 — V1/V2 + Bulk Extraction → Gate G2

**Goal:** Python V1/V2 working via CLI on a **leakage-safe** split; graphs extracted for the training subset of Python and C/C++; Week 1 conditions closed. Full detail, sequence and dependencies: `SHIELD_Week2_Wrapup.md`.

**Balance:** 15 h per person (75 h). Hours are estimates; recalibrate at the Monday sync. Every person also spends 0.5 h on the team label-noise check (Thursday).

**Monday sync: decisions to take first** (log each in Section 2)

- [ ]  D26 / Q8: add `cve` and `date` to the schema (schema 1.1)?
- [x]  D35 / Q10: verification verdict for hard-to-verify fixes (decided, see D35)
- [ ]  D38 / Q9: extraction subset policy (after the W2-P2-05 benchmark numbers)
- [ ]  D39 / Q11: Python negatives from patched code
- [ ]  Q12: CWE hierarchy (multi-label vs parent/child handling) for the V1 CWE head
- [ ]  Q2: weekly availability per person

**P1 — Data & Extraction (Hatem) · 15 h · reviewer P2**

- [ ]  W2-P1-01 [URGENT, 6 h] Merge + CWE normalization + **group-safe split manifest** (train/val/test + project-disjoint holdout, seed and hash logged). **Manifest v0 by end of Day 2**; frozen v1 on Day 4 after split QA is green
- [ ]  W2-P1-02 [URGENT, 4 h] Batch Joern extraction on the agreed subset (D38): parallel runner, overnight, cache hit/miss counters aggregated across workers, failures logged
- [ ]  W2-P1-03 [MILD, 3.5 h] Recover CVE ids and dates for grouping (schema 1.1 if agreed); rerun dedupe and audit on any loader change
- [ ]  W2-P1-04 [SIMPLE, 1 h] `docs/datasets/data_sources.md`: source, version or hash, license for the five datasets (closes C1, Q7)
- [ ]  W2-TEAM-01 [0.5 h] Label-noise hand-check, 20 rows

**P2 — Graph & Taint (Eyad) · 15 h · reviewer P1**

- [x]  W2-P2-05 [URGENT, 1.5 h] Extraction benchmark: batched vs per-sample Joern, 1/2/4 workers, memory; numbers feed D38 (Day 1–2) *Outcome:* E5 A at four workers: 0.606/0.558/0.503 samples/s (C/C++/Python); fastest non-batched E3 B: 0.225/0.224/0.204 samples/s at one worker. E5 C/b20 peaks: 851/825/1,871 MiB, but batching failed fidelity; scale projections use A. S1: 48.58/167.60/2.48 h (C/C++/Python). See `docs/graphs/extraction_report.md`.
- [x]  W2-P2-04 [URGENT, 2 h] Triage the 30 flagged spike samples and 13 empty DDGs; record raw-path verdicts and the triage-only Python context experiment in `docs/graphs/joern_triage.md` and the protected addendum in `docs/graphs/joern_spike.md`; Rule A provisional (D41; closes C3)
- [x]  W2-P2-01 [MILD, 4 h] CPG → PyG dataset builder (size caps, `CONVERTER_VERSION`), first on fixtures then on Python graphs. *Outcome:* converter 1.0, split builder, PyG dataset, statistics/CLI, and CI PyG coverage implemented; all five Python/C/C++ fixture golden counts pass. Extracted balanced 300-row Python and 300-row C/C++ smoke subsets and built Rule A/B datasets. Python cap 750 retains 97.3% with a 2.67 pp label gap; C/C++ cap 500 retains 96.0% with a 4 pp gap (the shared 750 cap also passes for C/C++). Rule B removes 2,860/7,735 nodes and 3,284/17,758 edges on Python/C++. Direct `.c` and `.cpp` Joern extractions both match the 25-node/69-edge golden output. Full-corpus statistics remain pending; see both PyG reports.
- [ ]  W2-P2-02 [MILD, 4.5 h] First GNN on Python: overfit a tiny subset, **variant A** first, **variant B** when node embeddings land (if they land after Day 5, B starts Week 3)
- [ ]  W2-P2-03 [MILD, 2.5 h] Call-graph edge merge prototype (k=1) for **Python and C only** (D28); measure `maxCallDepth` 4 vs 8 cost
- [ ]  W2-TEAM-01 [0.5 h] Label-noise hand-check, 20 rows

**P3 — Semantic, Fusion & Eval (Atef) · 15 h · reviewer P4**

- [ ]  W2-P3-01 [URGENT, 6 h] **V1**: window-pooled frozen CodeBERT → XGBoost, binary + CWE, calibrated confidence, imbalance handled; first on manifest v0, final on frozen v1
- [ ]  W2-P3-03 [URGENT, 3 h] Metrics module upgrade in `shield_core/eval/metrics.py` (per-CWE, per-language, multi-label, support and group counts; closes C4) and the V1/V2 per-CWE table
- [ ]  W2-P3-04 [MILD, 3 h] Embed every CPG node’s code text (fp16, ≤ 512 tokens), cache by unique node string, report cache size and hit rate
- [ ]  W2-P3-02 [MILD, 1.5 h] **V2**: add AST/code-metric features (from W2-P5-02); keep the length-only baseline next to it (D30)
- [ ]  W2-P3-05 [SIMPLE, 1 h] Re-run token-length statistics on the final deduped files; define the length-only baseline
- [ ]  W2-TEAM-01 [0.5 h] Label-noise hand-check, 20 rows

**P4 — Fix, Verification & Contracts (Bigad) · 15 h · reviewer P3**

- [x]  W2-P4-05 [URGENT, 0.5 h] D35 note for the Monday sync (verdict wording for Weak/None re-detection classes)
- [ ]  W2-P4-02 [URGENT, 3 h] Model registry: versioned files + config, V1 as default fallback; test by removing the newer model
- [ ]  W2-P4-01 [URGENT, 3 h] Wire V1/V2 into `interface.predict()` and `shield scan file.py` (stub model first, real artifact on Day 5)
- [ ]  W2-P4-03 [MILD, 5 h] Template fixes for Python CWE-89, CWE-78, CWE-22 stored as `fix_templates` in the registry; tests
- [ ]  W2-P4-04 [MILD, 3 h] Spot-check the top-concentration commits (Python 918/444/613/352/400; C/C++ 190/400/415/22): repo and SHA exist, it is a security fix, label and fix pair match; write `docs/datasets/audits/commit_spotcheck.md`
- [ ]  W2-TEAM-01 [0.5 h] Label-noise hand-check, 20 rows

**P5 — Tooling, Baselines & Infra (Maram) · 15 h · reviewer P4**

- [ ]  W2-P5-04 [URGENT, 3 h] **Split QA tool + CI test** in `scripts/data_audit/split_qa.py` (an empty placeholder today): per-split, per-CWE rows, projects, commit groups, CVEs; concentration; exact-hash overlap across splits; fails if any `(project, commit)` group crosses a split
- [ ]  W2-P5-02 [MILD, 3.5 h] tree-sitter function-boundary utilities (registry-driven) plus code-metric features for V2 (length, cyclomatic complexity, nesting, branch/loop counts); hand to P3 by Day 3
- [ ]  W2-P5-01 [MILD, 5 h] LLM baseline: harness (W1-P5-04) + run on the frozen Python test split; fixed prompt, output schema, versioned, logged
- [ ]  W2-P5-03 [SIMPLE, 2 h] Result-table script (MLflow/W&B → markdown tables)
- [ ]  W2-P5-05 [SIMPLE, 1 h] Housekeeping: commit `SHIELD_PLAN.md` to the repo root; fix stale README/`pyg_setup.md` lines; ~~remove the empty `docs/long_function_strategy.md` template~~ (done in the folder refactor, D40); second-machine toy run and GPU table (Q5)
- [ ]  W2-TEAM-01 [0.5 h] Label-noise hand-check, 20 rows

**Backups if someone slips:** P1 → P2 (extraction run) and P5 (split QA already independent); P3 → P4 (V1 wiring with a stub); P5 → P4 (LLM harness). If manifest v0 is late, P3 prototypes on a provisional manifest and marks every number “not final”.

**Gate G2 checklist**

- [ ]  `shield scan file.py` returns a V1/V2 prediction with CWE + confidence (real artifact, not the stub)
- [ ]  Per-CWE and per-language metrics recorded on the **frozen leakage-safe split**; split QA green; per-CWE group counts reported for every split; classes without independent val/test groups flagged
- [ ]  Graph cache built for the training subset of Python and C/C++ (D38); failures logged; cache hit/miss numbers recorded
- [ ]  D35, D38, D39 decided and logged; Q8 and Q12 answered
- [ ]  Conditions C1–C4 closed; label-noise hand-check result recorded
- [ ]  CI green on `main` (confirmed on GitHub)

---

### WEEK 3 — GNN (V3), Multi-language, Taint → Gate G3

**Goal:** V3 on all enabled languages (≥ 2); taint features; fix + verification modules.

**P1**

- [ ]  W3-P1-01 CVE mining pipeline (NVD/GHSA → fix commit → diff → before/after function → CWE), runnable on demand; reuse the CVEfixes collection logic where possible
- [ ]  W3-P1-02 Fix-pairs dataset prep (CVEfixes before/after + Zenodo `fixed_code` pairs; the “Vulnerability Fix Dataset” is not loaded, D25)
- [ ]  W3-P1-03 Extraction robustness: timeouts, per-file failure isolation

**P2**

- [ ]  W3-P2-01 **V3**: variant B (CodeBERT-init node features, D20) on Python + C/C++ (+ Java if enabled); compare gated GNN vs GAT; add variant C (DeepDFA-style dataflow features, D21) as an ablation. **Checkpoint:** if B does not beat V1 on per-CWE macro-F1 in at least one language, switch to variant A and log it in Section 2
- [ ]  W3-P2-02 Language-agnostic node features (shared node-type embeddings; language as a feature)
- [ ]  W3-P2-03 Joern taint-path features per function (source, sink, path length, sanitizer present), configured by `source_sink_config`; Python and C cross-function, C++ intra-function only (D28)

**P3**

- [ ]  W3-P3-01 V1/V2 extended to C/C++ (and Java if enabled), per-language runs using the same scripts
- [ ]  W3-P3-02 Fusion layer design + code (concat / gated / attention over [CodeBERT ∥ graph]); unit test with dummy tensors
- [ ]  W3-P3-03 Hyperparameter search plan (split across GPUs)

**P4**

- [ ]  W3-P4-01 Verification module: syntax check (tree-sitter re-parse) + re-detection hook
- [ ]  W3-P4-02 Template fixes for C/C++ (and Java if enabled) top CWEs; `shield fix`
- [ ]  W3-P4-03 CLI: JSON output mode (stable schema = D19)

**P5**

- [ ]  W3-P5-01 Sandboxed test runner (Docker, no network, CPU/mem/time limits) for the “functional check if tests exist”, per `test_runner` in the registry
- [ ]  W3-P5-02 LLM baseline on all enabled languages
- [ ]  W3-P5-03 Repo ingestion: clone/unzip, enumerate files, route per language via registry, extract functions
- [ ]  W3-P5-04 **(Stretch, gated by the audit)** Augmentation (train only, group-aware) and verified synthetic generator for CWE/language pairs below threshold (D23); tag `source=synthetic`

**Gate G3 checklist**

- [ ]  V3 metrics recorded on ≥ 2 languages (variants A, B, and C ablation compared)
- [ ]  D20 checkpoint resolved: B kept, or switched to A with a logged reason
- [ ]  Taint features exported for at least the intra-file cases
- [ ]  `shield fix` produces a verified template fix on at least one CWE per enabled language

---

### WEEK 4 — V4, Interprocedural, Repo Aggregation → Gate G4 (CORE FREEZE)

**Goal:** the full core pipeline works end-to-end through the CLI.

**P1**

- [ ]  W4-P1-01 Repo-level aggregation: run function-level model on every function; aggregate per file/repo (counts, top risks, CWE distribution)
- [ ]  W4-P1-02 Performance: parallel extraction, cache hit-rate metrics
- [ ]  W4-P1-03 Multi-dataset merge pipeline rerunnable with one command; docs; verify the “adding a language” checklist (Section 4.2) by dry-running it for a disabled language

**P2**

- [ ]  W4-P2-01 **Interprocedural**: cross-function graph (call-graph edges + callee context, depth k=2) + taint features into V3, **Python and C only (D28)**
- [ ]  W4-P2-02 Build the curated interprocedural evaluation set (Section 7.2 item 8); Python and C cases only (D28)
- [ ]  W4-P2-03 Freeze best GNN config

**P3**

- [ ]  W4-P3-01 **V4**: train fusion (CodeBERT ∥ GNN) per language; compare to V1/V3
- [ ]  W4-P3-02 Ablations: single-step vs multi-step; with/without taint; **error correlation between the GNN and V1** per language; real-only vs real+synthetic if used
- [ ]  W4-P3-03 Confidence calibration on the final classifier

**P4**

- [ ]  W4-P4-01 Full verification loop: syntax → tests (sandboxed, if present) → re-detection with V4; verdict + report
- [ ]  W4-P4-02 `shield scan-repo <path>` end-to-end with aggregated JSON report
- [ ]  W4-P4-03 Registry switching V1/V3/V4; V1 automatic fallback if V4 fails to load (test by killing V4)

**P5**

- [ ]  W4-P5-01 Mined-CVE temporal test set assembled (held out from training)
- [ ]  W4-P5-02 Error-analysis tooling (misclassified samples by CWE/language/size)
- [ ]  W4-P5-03 Regression tests for the CLI, interface, and registry (CI)

**Gate G4 (CORE FREEZE) checklist**

- [ ]  `shield scan-repo` on a real repo returns findings + fix suggestions + verification verdicts
- [ ]  V4 results recorded; V1 fallback verified
- [ ]  Interprocedural set evaluated once (baseline number exists)
- [ ]  From here: core bug fixes only, no new model work

---

# PHASE B — PRODUCT (Weeks 5–6)

### WEEK 5 — Backend, Web App, Extension, Final Evaluation

**Goal:** wrap the frozen core; build the product in parallel against the frozen contract (mock the API until ready).

**P1 + P4 — Backend**

- [ ]  W5-P4-01 FastAPI app implementing the contract (`docs/api/api_contract.md`) as thin wrappers over `shield_core.interface`; `/v1/languages` reads the registry
- [ ]  W5-P4-02 API key auth, CORS, rate limits, input size limits
- [ ]  W5-P1-01 PostgreSQL schema + Alembic; persist scans/jobs/findings
- [ ]  W5-P1-02 Celery/Redis repo-scan jobs with progress; Joern server container + cache
- [ ]  W5-P4-03 `/v1/fix` with verification report; V1 fallback path tested through the API
- [ ]  W5-P1-03 Security review: sandbox escape, path traversal in repo upload, secrets not logged

**P5 — Web app**

- [ ]  W5-P5-01 Angular skeleton + client generated from OpenAPI (mock server until the API is up)
- [ ]  W5-P5-02 Pages: code submission (language dropdown from `/v1/languages`) + results (findings, CWE, confidence, taint path)
- [ ]  W5-P5-03 Pages: scan history, repo submission with job progress
- [ ]  W5-P5-04 `docker-compose.yml` for the full stack (api, postgres, redis, joern, web)

**P2 — VS Code extension**

- [ ]  W5-P2-01 Extension skeleton + settings (API URL/key); activation languages taken from the API
- [ ]  W5-P2-02 Diagnostics (squiggles) with CWE + confidence for the current file
- [ ]  W5-P2-03 Workspace scan command + results tree view
- [ ]  W5-P2-04 Code action “show/apply fix” with confirmation

**P3 — Final evaluation**

- [ ]  W5-P3-01 Final frozen-test evaluation for all models (run **once**, no tuning after), including PrimeVul for C/C++
- [ ]  W5-P3-02 Figures/tables generated by script; failure-case + limitations write-up
- [ ]  W5-P3-03 Model cards for V1/V3/V4; dataset card (with P1)
- [ ]  W5-P3-04 Measure fix success rate and latency (cached vs uncached)

**Stretch (only if ahead):** CodeT5 + LoRA fix model, GitHub Action, GitHub OAuth, scheduled mining, enabling Java if it was deferred and time remains (follow Section 4.2)

**Week 5 checklist**

- [ ]  API up and matches the contract; `/scan/snippet` and `/scan/repo` work through `docker compose up`
- [ ]  Web app submits code and shows results; extension shows diagnostics from the live API
- [ ]  Frozen-test evaluation completed

---

### WEEK 6 — Integration, Polish, Docs, Demo → Gates G5 (mid-week), G6

**Goal:** a clean release and a convincing presentation. **Product freeze mid-week.**

**Integration (all)**

- [ ]  W6-ALL-01 End-to-end run: web app → API → repo scan → dashboard → fix diff
- [ ]  W6-ALL-02 Extension ↔︎ API against the real docker stack
- [ ]  W6-ALL-03 Bug bash (everyone tries to break it); triage and fix
- [ ]  W6-ALL-04 **G5 Product freeze** (Wed/Thu): bug fixes, docs, polish only

**Polish & docs**

- [ ]  W6-P5-01 UI polish: error/loading/empty states; dashboard charts (CWE distribution)
- [ ]  W6-P2-01 Package `.vsix` + install README
- [ ]  W6-P1-01 Data/extraction docs and reproduction commands; “adding a language” guide
- [ ]  W6-P4-01 API docs, deployment notes, sandbox docs
- [ ]  W6-P3-01 Evaluation docs and results section

**Release**

- [ ]  W6-ALL-05 Clean-machine install test: fresh clone → `docker compose up` → demo flow works
- [ ]  W6-ALL-06 Final report (structure in Section 11)
- [ ]  W6-ALL-07 Slides + demo script + **recorded backup demo video**
- [ ]  W6-ALL-08 Rehearsal ×2 with timing; Q&A prep (Section 12)
- [ ]  W6-ALL-09 Release tag; all models versioned

**Gate G6 checklist**

- [ ]  Release tag; report + slides + video ready; clean-machine test passed

---

## 10. RISKS, FALLBACKS, AND TRIGGERS

| Risk | Likelihood | Impact | Trigger | Fallback |
| --- | --- | --- | --- | --- |
| **Product phase is only 2 weeks** (backend + web + extension) | High | High | W5 midweek: API not up | Contract + D19 frozen in W1; mock server so frontend/extension start day 1 of W5; VS Code ext is the first cut; web app stays Must |
| Core overruns into Week 5 | Med | High | G4 missed | Apply cut order (Section 3); keep G4 date; reassign P1/P5 to core finish while P4 starts the API |
| No live demo surface until W5 | Med | Med | W1–W4 | CLI + JSON output is the demo surface; record CLI demos each Friday |
| Joern fails on a language / too slow | Med | High | G1 spike | Python → `ast`; defer the language via D24; smaller caps |
| Java data too thin or Joern Java weak | Med | Low | G1 audit | Defer Java (D24); plumbing stays ready |
| Datasets fail acceptance (missing metadata, corrupted rows) | High | High | W1 audit | Use original releases; run collection scripts; prototype-only use of re-uploads |
| Per-GPU 8 GB VRAM ceiling (OOM); uneven GPUs | Med | Med | OOM / slow runs | Size all jobs to 8 GB; heavy jobs to the strongest GPUs; share caches; Colab/Kaggle overflow |
| GNN unstable / no gain over V1 | Med | High | W3 metrics | Switch to variant A (D20 fallback); ship V1/V2 as primary; report V3/V4 honestly |
| Fusion gain shrinks (CodeBERT-init GNN errors correlate with V1) | Med | Med | W4 error-correlation result | Report as a finding; keep sequence path at function level; test variant C (D21) |
| Data leakage / inflated metrics | Med | High | suspiciously high F1 | Enforce D16/D22; duplicate audit; PrimeVul + temporal test set |
| Synthetic data inflates metrics or teaches analyzer artifacts | Med | Med | real-only vs real+synthetic gap | Enforce D23; drop synthetic if no real-test gain |
| Label noise (Big-Vul etc.) | High | Med | audit | Report noise; filter clear errors; per-CWE minimums |
| Interprocedural weak (esp. Python) | High | Med | W4 eval | Restrict claims to languages where it works; keep depth-1 |
| Interface drift between core and product | Med | High | Thursday syncs | D19/`LanguageSpec` versioned; contract tests in CI (W4-P5-03) |
| Fix verification unsound | High | Med | inherent | State “soft check, not proof”; human merge checkpoint |
| Untrusted code in tests | Med | High | security review | Docker sandbox, no network, limits |
| Member unavailable | Med | Med | standup | Cross-reviewers cover; cut order |
| Scope creep | High | High | any new idea | Section 13 backlog, not the plan |
| **Python data independence** (CWE-444: 9 commit groups, CWE-613: 11, CWE-352: 25; one commit holds up to 56% of a CWE) | High | High | W2 split QA shows too few groups per CWE per split | Group-aware splits (D33); report per-CWE group counts; remove thin classes from per-CWE claims but keep them in the registry |
| **Graph extraction cost** (5.85 s/sample measured; ≈ 740 h single-threaded for 455,236 rows) | High | High | W2-P2-05 benchmark | E5 A w4 measured 0.606/0.558/0.503 samples/s (C/C++/Python); C/b20 was faster but failed fidelity, so use non-batched extraction for now. E5 A projections: C S1 48.58 h, C++ S1 167.60 h, Python S1 2.48 h. See `docs/graphs/extraction_report.md`; D38 subset decision remains with P1 |
| **Python graph quality** (raw path 45/120 usable; 62/100 scale rows lacked a real METHOD) | Med | High | W2-P2-04 (D41) | Raw Python path NO-GO; apply synthetic class context consistently to indented method excerpts in production with source-line offset correction; triage recovered 120/120, but production use requires mapping validation; V1 stays the Python primary |
| **Length shortcut** (vulnerable over 512 tokens: 60.1% vs 19.7% in MegaVul) | High | Med | V2 beats V1 only through length features | Length-only baseline (D30); drop length features if they explain the gain |
| **No PrimeVul, no dates** (no chronological or independent C/C++ test) | High | Med | G4 evaluation | Project-disjoint holdout (D33); report the limitation; PrimeVul loader as stretch; recover dates (W2-P1-03) |
| **Missing license/source notes** (D22) | Med | Med | Day 2 of Week 2 | W2-P1-04 |
| **Critical path concentrated on P1** (manifest then extraction) | Med | High | manifest v0 not out by Day 2 | P5 builds split QA in parallel; P2 runs the benchmark and backs up extraction; P3 prototypes on a provisional manifest and marks numbers “not final” |
| **C++ cross-function taint unsupported** (D28) | High | Low | W4 interprocedural eval | Claims limited to Python and C; C++ intra-function only |

---

## 11. NON-TECHNICAL WORK

- [ ]  Set the real deadline and shift all relative dates (Dashboard)
- [~] Names filled in Section 5 (Week 1); weekly availability still open (Q2)
- [ ]  Mon plan sync + Thu integration sync; decisions recorded in Section 2
- [x]  Git hygiene: branch naming `w<week>-p<person>-<topic>`, PR template, review rule (README + `.github/pull_request_template.md`)
- [ ]  Data/licensing check for every dataset and evaluation suite; cite sources (W2-P1-04; no license notes exist yet)
- [ ]  Ethics note: dual-use risk of vulnerability tooling; no publishing exploits
- [ ]  Friday recorded CLI demo (W1–W4) to keep a visible progress trail
- [ ]  Final report outline: Abstract · Problem · Related work · Data (with acceptance audit) · Method (V1–V4, taint, fix loop) · System · Evaluation · Limitations · Future work
- [ ]  Slides (≈15) + live demo script + backup video
- [ ]  Contribution statement per member

---

## 12. DEMO SCRIPT & Q&A PREP (draft; refine in W6)

**Demo flow (≈6 min):** (1) paste vulnerable Python/C snippet in VS Code → squiggle with CWE + confidence → (2) show taint path across two functions → (3) accept fix → verification passes → (4) web app: submit a repo → aggregated dashboard → (5) per-CWE table and V1 vs V4 ablation.

**Expect:** Why not just an LLM? (baseline numbers) · How did you prevent leakage? (D16/D22, PrimeVul, temporal set) · Why does fusion help? (single vs multi-step ablation, error correlation) · How reliable is fix verification? (soft check) · Did synthetic data help? (real-only vs real+synthetic) · How hard is adding a language? (Section 4.2) · What fails? (failure-case section).

---

## 13. BACKLOG / PARKING LOT (NOT in scope)

- Java (deferred at G1, D36) and other languages: follow Section 4.2
- PrimeVul test-only loader, DiverseVul, PyCode-Vul / Python Vulnerabilities Full loaders (not loaded, D25)
- Semantic-clone detection across splits (D32 does exact normalized-hash dedupe only)
- Adversarial robustness testing · cross-project generalization study · human-in-the-loop active learning · automated exploit verification · formal reliability guarantees · upstream PRs to open-source projects · cloud deployment

---

## 14. OPEN QUESTIONS

| # | Question | Owner | Status |
| --- | --- | --- | --- |
| Q1 | Exact deadline and required deliverables (report / slides / live demo) | team | **open** |
| Q2 | Real names and weekly availability for P1–P5 | team | names filled (Hatem, Eyad, Atef, Bigad, Maram); availability **open** |
| Q3 | Final per-language CWE lists | P1 | **provisional** lists in the YAMLs (Python 14, C/C++ 20, D31); finalize after split-level counts exist (W2) |
| Q4 | Joern go/no-go per language (G1) | P1 | **closed: GO for Python, C, C++ (D27)** |
| Q5 | GPU model and VRAM per member (ceiling is RTX 4060 8 GB) | team | open; one machine recorded (RTX 4060 Laptop, 8 GB); W2-P5-05 collects the rest |
| Q6 | Java enabled or deferred (D24, decided at G1) | P1 | **closed: deferred (D36)** |
| Q7 | Licenses and availability of each dataset | P1 | open; W2-P1-04 (MegaVul, Big-Vul, CVEfixes, Zenodo 13870382; Juliet, Vul4J, PrimeVul only if added) |
| Q8 | Schema 1.1: add `cve` and `date`? | P1 | open; Monday of Week 2 (D26) |
| Q9 | Extraction subset policy | P1 + P2 | open; Monday of Week 2 (D38) |
| Q10 | Verification verdict for hard-to-verify fixes | P4 | **answered: D35 (notes-only, per-class gate)** |
| Q11 | Python negatives from patched code | P1 + P3 | open; Monday of Week 2 (D39) |
| Q12 | CWE hierarchy: multi-label, parent/child handling for 119 vs 120/125/787/122 | P3 | open; W2 |
| Q13 | Which published dataset is the Zenodo Python file? Week 1 notes name “PyCode-Vul” and “Python Vulnerabilities Full”; the repo loads Zenodo 13870382 `data_Python.csv` | P1 | open; fix the names in 7.1 once confirmed |
| Q14 | Add a PrimeVul test-only loader (C/C++)? | P1 | open; stretch |

---

## 15. CHANGELOG (newest first)

| Date | Change | By |
| --- | --- | --- |
| 2026-10-28 | **W2-P2-04 graph-quality triage (D41).** Raw verdicts: Python 45/120 NO-GO, verified C 95/100 GO, C++ 17/20 GO; Rule A provisional. Synthetic class context makes 120/120 Python samples usable in triage, pending production source-line mapping validation. C3 closed. | Eyad |
| 2026-10-31 | **W2-P2-01 CPG → PyG converter (D42).** Added deterministic fixtures, filtering and tensor conversion, split builder and stats, CLI, and CI PyG tests. Fixture counts reproduce on Python/C/C++; full split build awaits P1 cache and manifests. | Eyad |
| 2026-10-26 | **v1.2 (folder layout refactor).** Added D40 (R1-R9). Section 4.3 replaced with the as-built tree. Old paths rewritten to the new folders in Sections 2, 7 and 9 (`docs/` by topic, `scripts/` by purpose, `languages/` and `eval/` inside `shield_core/`). Week 2 tasks W2-P3-03 and W2-P5-04 now name their files; W2-P5-05 no longer owes the empty-template removal. Section 0 points to `docs/project/REFACTOR_PLAN.md`. Dashboard, gate tracker and task status were **not** reviewed in this edit | Eyad |
| 2026-10-12 | **v1.1 (Week 1 close; G1 passed with conditions).** Added D25–D39 (datasets as built, 8-column schema, Joern GO, interprocedural scope, taint contract, long-function policy, CWE scope and ≥100 threshold, dedupe policy, leakage guard, interface freeze, Java deferred, ownership/rebalance; D35, D38, D39 open or proposed). Amended D4, D13, D16, D22, D24 inline. Dashboard and gate tracker updated (G1 result, conditions C1–C4, G2 revised). Section 4.3 layout note; Section 5 names; Section 6 measured numbers; Section 7 datasets as built, rule status, 7.4 CWE tables; Section 8 additions; Week 1 closed; **Week 2 rebalanced to 15 h per person**; targeted W3/W4 edits for D28 and D25; Section 10 +8 risks; Sections 11, 13, 14 updated | Week 1 wrap-up |
| 2026-09-30 | **v1.0 baseline.** Added D22 (dataset acceptance), D23 (synthetic data rules), D24 (language plug-in architecture; Java conditional); new dataset plan (CVEfixes, DiverseVul, PrimeVul, Juliet, Vul4J, SecurityEval/SVEN); Kaggle re-uploads marked prototyping-only; `LanguageSpec` registry and “adding a language” checklist; W1/W3/W4/W5 tasks, gates, risks, evaluation, open questions updated | — |
| 2026-09-30 | V3 node initialization decided (D20: frozen CodeBERT node features, from-scratch fallback) + DeepDFA-style ablation (D21) | — |
| 2026-09-30 | Core-first phasing (D18/D19): backend, web app, VS Code extension moved to W5–W6 | — |
| 2026-09-30 | Compute corrected: multiple GPUs, RTX 4060 8 GB is the per-GPU ceiling | — |
| 2026-09-30 | Initial plan created; decisions D1–D17 recorded | — |
