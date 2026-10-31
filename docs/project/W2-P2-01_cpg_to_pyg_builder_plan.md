# W2-P2-01: CPG → PyG dataset builder

STATUS: DONE (IMPLEMENTATION + SMOKE BUILD; FULL-CORPUS REBUILD IS A FOLLOW-UP)

> **Single source of truth for this task.** Any chat or person can continue from here.
> Repo path when committed: `docs/project/W2-P2-01_cpg_to_pyg_builder_plan.md`.
> Task id in the team plan: **W2-P2-01** (P2 = Eyad, reviewer P1 = Hatem, MILD, planned 4 h, Step 22 on Day 3, finished on real Python graphs by Day 4).
> Legend: `[ ]` todo · `[~]` in progress · `[x]` done · `[—]` dropped/moved (write why).

---

## 0. RESUME PROTOCOL (read this first if you are a new chat)

1. Read this whole file, then **Section 5 (STATE)**. It says which box was ticked last and what was in progress.
2. Verify reality before trusting the boxes (run from the repo root):
   - `git status` and `git log --oneline -15` (look for commits starting `W2-P2-01:`).
   - `ls shield_core/graph_dataset/ tests/graph_dataset/ tests/fixtures/graphs/` (which files already exist?).
   - `ls data/cache/graphs/` and count cached graphs: `python -c "import pathlib;print(sum(1 for _ in pathlib.Path('data/cache/graphs').rglob('*.json.gz')))"`.
   - `pytest tests/graph_dataset -q`, `ruff check . && ruff format --check .`, `pytest tests/test_layout.py -q`.
3. If the repo contradicts a ticked box, **untick it** and write one line in Section 9 (Handoff log).
4. Continue at the **first unticked box**. Do not redo ticked work.
5. **Working agreement with the user (Eyad):** implement **one step at a time**. At each *REVIEW GATE*: show the diff, explain it
   briefly and precisely, run the tests, and **wait for the user's OK**. Where a step needs the user's machine (Docker, the real
   `data/` folder, PyG) say exactly which command to run and what output to paste back. **Never invent numbers:** every figure in a
   document must come from a file or command output pasted into the chat. The user has no PyG background beyond the Week-1 lessons
   (`scripts/tutorials/pyg/`), so explain every new concept the first time it appears.
6. After every finished step: tick its box, update Section 5 (STATE), append one line to Section 9.
7. The task is only finished when **Phase 9 is ticked and Phase 10 (professor explanation) has been delivered in the chat.**

---

## 1. What the task is, in one page

**Plan text, literally (SHIELD_PLAN.md, W2-P2-01):** implement the converter per `graph_schema.md`: kept node/edge types, node cap
(500–1000), edge-type tensor, `CONVERTER_VERSION` in the processed-dataset path. Test on the fixtures first, then on Python graphs as
they land. Delivers: `scripts/graphml_to_pyg.py` extended or moved into `shield_core/`, a processed dataset, size statistics
(nodes per graph, dropped count).

**In plain words.** Joern gives one big raw graph per function (the `CodeGraph` cached by P1's extraction). A GNN cannot eat that. It
needs, per function, a `torch_geometric.data.Data` object: a feature matrix `x`, a list of edges `edge_index`, and the type of each
edge `edge_type`, plus the label. This task builds the machine that does the conversion **reproducibly**, applies the filtering rules
of `docs/graphs/graph_schema.md`, enforces a node cap, writes a versioned **processed dataset** per split, and reports size statistics.

**Who waits for this:** W2-P2-02 (first GNN, Step 29) needs the processed dataset; W2-P3-04 (node text embeddings) needs the
`node_text_hash` contract (Section 3.3); W3-P2-01 (V3) and W3-P2-03 (taint flags) extend this converter.

**Deliverables (all required):**

| # | Deliverable | Path |
| --- | --- | --- |
| D1 | Constants, `CONVERTER_VERSION`, `ConverterConfig`, `text_hash64` | `shield_core/graph_dataset/schema.py` |
| D2 | Pure-Python filtering (no torch): `CodeGraph` → `FilteredGraph` (Rule A/B, cap check, diagnostics) | `shield_core/graph_dataset/filtering.py` |
| D3 | `FilteredGraph` → PyG `Data` | `shield_core/graph_dataset/to_pyg.py` |
| D4 | Split builder: manifest rows + graph cache → list of `Data` + per-row report | `shield_core/graph_dataset/builder.py` |
| D5 | `ShieldGraphDataset` (an `InMemoryDataset`) that loads the processed files | `shield_core/graph_dataset/dataset.py` |
| D6 | Size statistics and cap table (overall, per label, per CWE) | `shield_core/graph_dataset/stats.py` |
| D7 | Folder README and package `__init__.py` | `shield_core/graph_dataset/{README.md,__init__.py}` |
| D8 | CLI: build the dataset, print and write the report | `scripts/graphs/build_pyg_dataset.py` |
| D9 | The old prototype becomes a thin wrapper over the new code (same printed output) | `scripts/graphs/graphml_to_pyg.py` |
| D10 | Fixture maker (GraphML export → committed `CodeGraph` fixture) | `scripts/graphs/export_to_fixture.py` |
| D11 | Fixtures (5 real tiny graphs) | `tests/fixtures/graphs/*.json.gz` |
| D12 | Tests | `tests/graph_dataset/test_{schema,filtering,to_pyg,builder,dataset,stats}.py`, `conftest.py` |
| D13 | Path constants | `shield_core/paths.py` (`PROCESSED_DIR`, `PYG_DATASET_DIR`) |
| D14 | Generated size report (real numbers) | `docs/graphs/pyg_dataset_report.md` |
| D15 | Schema doc updated (converter version, new fields, cap decision, Rule A/B status) | `docs/graphs/graph_schema.md` |
| D16 | Decision **D42** (node cap + converter contract) logged, task ticked with *Outcome* | `SHIELD_PLAN.md` |
| D17 | Docs kept in step (README update procedure, Section 7) | root `README.md`, `shield_core/README.md`, `scripts/graphs/README.md`, `tests/README.md`, `docs/README.md`, `tests/fixtures/joern/README.md` |
| D18 | Short message to P2-self/P3 about the `node_text_hash` contract | Phase 8 |
| D19 | Professor-style explanation of every concept and file, **delivered in the chat** at the very end | Section 10 |

**Out of scope (do NOT do here):** running Joern or changing `shield_core/extraction/*` (the builder only READS the cache); the
production Python class-wrapper / line-offset fix (P1's extraction, D41); CodeBERT node embeddings themselves (W2-P3-04); training a
GNN (W2-P2-02); filling the three taint-flag columns (W3-P2-03, they stay 0 now); Java.

---

## 2. Facts verified in the repo copy (so nobody re-discovers them)

| Fact | Where | Why it matters |
| --- | --- | --- |
| The existing prototype reads **GraphML through `networkx`**, but `networkx` is **not** in `pyproject.toml` dependencies. The real pipeline stores **`CodeGraph`** objects (plain Python dataclasses) as gzip JSON in `data/cache/graphs/`. | `scripts/graphs/graphml_to_pyg.py`, `shield_core/extraction/cache.py` | The new converter must take a `CodeGraph`, not GraphML. No networkx. GraphML stays only as the input of the fixture maker, through the existing `parse_graphml`. |
| `CodeGraph.nodes` = `GraphNode(id, type, code, name, line)`; `CodeGraph.edges` = `GraphEdge(src, dst, type)`. `parse_graphml` sorts nodes by id and edges by `(src, dst, type)`. | `graph_extractor.py`, `joern_extractor.py` | Row order of `x` = sorted Joern ids. Deterministic for a given cached graph. Joern ids are NOT stable across Joern runs, so never use them as a cross-run key. |
| **Golden numbers reproduced** by running `parse_graphml` + the old filter rules on the five sample exports in the zip (`sample1`…`sample5`): get_user 96→48 nodes, 499→176 edges; branch 104→54, 540→194 (CDG 5); calls 115→60, 580→207 (CALL 1); C overflow 66→25, 246→69; C++ vec 66→25, 246→69. They match `graph_schema.md` §5–6. | `sample*/export*/export.xml` | These are the golden tests. The new code must reproduce them exactly under Rule A. |
| Edge counts per type (Rule A): get_user AST 47 / CFG 38 / REACHING_DEF 64 / CALL 0 / ARGUMENT 27 / CDG 0. branch: 53/40/70/0/26/5. calls: 59/43/76/1/28/0. C: 22/13/27/1/6/0. | same | Golden per-type counts. |
| **Rule B measured** (drop every line-less METHOD and its AST children, on top of Rule A): Python samples unchanged (Rule A already removes the operator stubs). C and C++ samples: 25→20 nodes, 69→59 edges, CALL 1→0, AST 22→18, CFG 13→12, REACHING_DEF 27→23, ARGUMENT 6→6. | computed on the zip copy | Golden numbers for Rule B. The `strcpy` stub is the only difference. |
| Kept node types (12, one-hot order fixed): METHOD, METHOD_PARAMETER_IN, METHOD_RETURN, BLOCK, CALL, IDENTIFIER, LITERAL, LOCAL, FIELD_IDENTIFIER, RETURN, METHOD_REF, CONTROL_STRUCTURE. Edge ids fixed: AST 0, CFG 1, REACHING_DEF 2, CALL 3, ARGUMENT 4, CDG 5. `x` has 15 columns (12 one-hot + 3 zero taint flags). | `graph_schema.md` §2–4 | Do not renumber; saved models and docs depend on it. |
| `UNKNOWN` is a real Joern node **type**; it is not in the kept list, so it is dropped by the type filter. | `triage_core.graph_metrics` | The builder counts UNKNOWN nodes before dropping them (quality diagnostic). |
| `scripts/spikes/joern/triage_core.py` already has `graph_metrics(CodeGraph)` and `stub_rule_impact`. | file | Use as a **reference** for the quality definition. `shield_core` must never import from `scripts` (README rule), so re-implement the few lines in `filtering.py`. |
| **D41:** raw Python graphs were NO-GO (45/120 usable), C GO (95/100), C++ GO (17/20). Rule A is provisional. A synthetic class-context wrapper recovers Python in triage only; production use is P1's job. | `SHIELD_PLAN.md` D41, `docs/graphs/joern_triage.md` | The builder converts **whatever the cache holds**. It records quality diagnostics per graph and can optionally drop unusable ones. It does not hide bad graphs silently. |
| `batch_extract.py` keys the cache with `CacheKey.for_code(code, language, JoernExtractor(docker_image="shield-joern"))` using the row's `code` **unchanged**. Parquet languages are `python` and `cpp` (C and C++ share the `cpp` registry entry). | `scripts/graphs/batch_extract.py` | The builder must compute the cache key the same way. `JoernExtractor(...)` construction does not run Docker. If P1 later adds a code transform (the Python wrapper), the builder needs the same transform (Section 8, risk R2). |
| Split files are `data/interim/splits/{train,val,test,holdout}.parquet` with the 10 schema columns: `code, language, label, cwe (list), project, commit, date, cve (list), fixed_code, source`. After a parquet round trip, list columns come back as numpy arrays; `schema.from_parquet` converts them. | `shield_core/paths.py`, `datasets/schema.py` | Row identity inside a split = parquet row position + `code_sha256`. |
| **CI installs only `.[dev,data,ml]` on Python 3.12 with CPU torch. `torch_geometric` is NOT installed in CI** (it is in the `gnn` extra). `tests/test_layout.py`: every code folder has `__init__.py` + `README.md`; every backticked path in root `README.md` starting `shield_core/ scripts/ docs/ tests/ docker/ .github/ requirements/` must exist; first-party imports must resolve; `*.pt` and `data/` are git-ignored. | `.github/workflows/ci.yml`, `pyproject.toml`, `tests/test_layout.py`, `.gitignore` | Drives the test strategy (Section 3.7): the filtering logic is torch-free so CI always tests it; PyG tests use `pytest.importorskip` AND CI gets the `gnn` extra (Phase 1 decision). |
| The existing `CPGNodeEmbedder` caches node vectors by `sha256(utf-8 text)`. | `shield_core/embeddings/node_embeddings.py` | The `node_text_hash` contract reuses that hash, so P3's cache and our graphs join without a vocabulary file. |
| The zip has **no `data/` folder**: real graphs and splits were NOT visible when this plan was written. | — | Every statement about real-data sizes is unknown until Phase 7. |

---

## 3. Design (decisions locked unless the user overrides them in Phase 1)

### 3.1 Package layout

```
shield_core/graph_dataset/
    __init__.py      exports the public names
    README.md        folder README (required by tests/test_layout.py)
    schema.py        NODE_TYPES, EDGE_TYPES, CONVERTER_VERSION, ConverterConfig, text_hash64
    filtering.py     CodeGraph -> FilteredGraph          (pure Python, no torch)
    to_pyg.py        FilteredGraph -> torch_geometric Data
    builder.py       parquet split + graph cache -> list[Data] + per-row report
    dataset.py       ShieldGraphDataset(InMemoryDataset): load/save processed files
    stats.py         size statistics, cap table, report text
scripts/graphs/
    build_pyg_dataset.py   CLI
    export_to_fixture.py   GraphML export -> tests/fixtures/graphs/<name>.json.gz
    graphml_to_pyg.py      thin wrapper (keeps the old command and printed output)
```

Why a new package and not `shield_core/extraction/`: extraction = "code → raw graph" (Joern-specific, cached). This package = "raw
graph → ML tensors" (PyG-specific). The README rule "ML code imports `graph_extractor.py`, never Joern" is respected: this package
imports only `CodeGraph` and `GraphCache`/`CacheKey`.

### 3.2 Data flow

```
data/interim/splits/<split>.parquet ──┐ (code, label, cwe, ...)
                                      ├─ builder.build_split ──> list[Data] + rows report
data/cache/graphs/**.json.gz ─────────┘      │       ▲
   (CodeGraph per code string)               │       └── ConverterConfig (stub rule, node cap, edge types, drop_unusable)
                                             ▼
   filtering.filter_graph  (CodeGraph -> FilteredGraph, or a skip reason)
   to_pyg.to_data          (FilteredGraph -> Data)
                                             ▼
data/processed/pyg/<converter>/<graph-schema>/<language>/<config-fingerprint>/
      config.json · processed/<split>.pt · reports/<split>_rows.parquet · build_summary.json · cwe_vocab.json
                                             ▼
   dataset.ShieldGraphDataset(...)  ──>  DataLoader  ──>  W2-P2-02 GNN
```

### 3.3 The `Data` contract (fields every graph carries)

| Field | Shape / type | Meaning | Used by |
| --- | --- | --- | --- |
| `x` | `[N, 15]` float | 12 one-hot node type + `is_source`, `is_sink`, `is_sanitizer` (all 0 until W3-P2-03) | all variants |
| `edge_index` | `[2, E]` long | Joern direction (src → dst), rows are `x` rows | all |
| `edge_type` | `[E]` long | ids from `EDGE_TYPES` (0..5), same order as `edge_index` columns | relation-aware layer |
| `node_type` | `[N]` long | index into `NODE_TYPES` (same info as the one-hot, as an integer) | variant A `nn.Embedding` |
| `node_text_hash` | `[N]` long | `text_hash64(node.code)`: first 16 hex digits of `sha256(code)` read as a signed 64-bit int | variant B: join to P3's CodeBERT cache |
| `line` | `[N]` long | Joern `LINE_NUMBER`, `-1` when absent (stubs) | debugging, taint/line mapping |
| `joern_id` | `[N]` long | Joern node id (debug only, not stable across Joern runs) | debugging |
| `y` | `[1]` long | label, 1 = vulnerable | training |
| `cwe_multihot` | `[1, K]` float | multi-label CWE over `cwe_vocab.json` (vocabulary = CWEs seen in TRAIN label-1 rows, sorted; unseen CWEs in other splits are dropped and counted in the report) | per-CWE table |
| `code_sha` | str | `code_sha256(code)`: links back to the graph cache and the parquet row | provenance |
| `row` | int | zero-based parquet row position inside the split file | provenance |

A graph with **zero edges** is still a valid `Data` (`edge_index` shape `[2, 0]`). Taint flag columns stay zero.

### 3.4 Rules

- **Node filter (identical to the prototype):** keep a node iff its type is in `NODE_TYPES` and it is not an `<operator>*` stub METHOD
  or a direct AST child of one (its parameters and return node).
- **Rule A (default, provisional per D41):** the filter above only. Wrapper methods (`<module>`, `<global>`) and external-function
  stubs (`strcpy`) stay.
- **Rule B (option):** Rule A **plus** drop every METHOD with no line number and its direct AST children.
- **Edge filter:** keep an edge iff its type is in `config.edge_types` (default all six) and both ends are kept nodes. Edge ids stay the
  global ones even if a subset is selected (no renumbering), so `num_relations` is always 6.
- **Node cap (`max_nodes`):** a graph with more kept nodes than the cap is **skipped, never truncated** (truncating would cut real
  data-flow paths and silently create a different graph). Default **1000** until Phase 7 measures the distribution; the final value is
  decided from data and logged as D42. The cap is part of the config fingerprint.
- **Quality diagnostics (always computed, from the RAW graph):** `has_real_method` (a METHOD with a line number whose name is not
  `<module>`/`<global>`), `n_unknown`, `unknown_share`, `n_cfg`, `n_reaching_def`, `n_meta_class_adapter` (nodes whose name contains
  `<metaClassAdapter>`; open decision in `graph_schema.md` §4.1, we only count them). `usable` = real method AND ≥1 CFG edge AND
  `unknown_share` ≤ 0.05 (the D41 criteria minus the expected-flow test, which needs the source code). `drop_unusable=False` by
  default: recorded, not enforced.
- **Skip reasons (exactly these strings):** `ok`, `no_graph_in_cache`, `bad_code`, `empty_after_filter`, `over_node_cap`, `unusable`.

### 3.5 Versioning and paths

- `CONVERTER_VERSION = "1.0"` in `schema.py`. Bump it **by hand** whenever the meaning of the output changes (kept types, one-hot
  order, filter semantics, new `Data` fields). `GRAPH_SCHEMA_VERSION` (raw extractor output) is NOT touched.
- `ConverterConfig.fingerprint()` = first 10 hex chars of `sha256` of the config as sorted JSON. Two configs with different cap or
  rule can never share a folder.
- Processed folder: `data/processed/pyg/<CONVERTER_VERSION>/<GRAPH_SCHEMA_VERSION>/<language>/<fingerprint>/`. New constants in
  `shield_core/paths.py`: `PROCESSED_DIR = DATA_DIR / "processed"`, `PYG_DATASET_DIR = PROCESSED_DIR / "pyg"`. (`data/` is git-ignored.)
- `config.json` stores: converter version, graph schema version, extractor name+version used for the cache key, the config, the
  `cwe_vocab`, a hash of each split parquet (use `shield_core.tracking` helpers if a dataset-hash function exists there; otherwise
  `sha256` of the file bytes), and the build date. This is what W2-P2-02's MLflow run logs as "dataset hash".

### 3.6 Storage

PyG's `InMemoryDataset` pattern: all graphs of a split are collated into one big `Data` plus slice indices and saved with
`torch.save`. Loading is one file read. Check the exact method names and signatures in the **installed** PyG (2.8.0.post1) before
coding, do not trust memory: `python -c "import inspect, torch_geometric.data as d; print(inspect.signature(d.InMemoryDataset.save)); print(inspect.signature(d.InMemoryDataset.load))"`.

### 3.7 Test strategy (the CI problem)

CI has no PyG. Therefore:
1. `filtering.py` and `schema.py` import **no torch** → their tests run in CI always and carry the golden numbers.
2. `to_pyg.py`, `builder.py`, `dataset.py` tests start with `pytest.importorskip("torch_geometric")`.
3. Phase 1 decision (needs user OK because the CI file is shared): change the CI install line to `pip install -e ".[dev,data,ml,gnn]"`
   so the PyG tests also run on GitHub. `torch_geometric` is pure Python, installing it on top of CPU torch is light.
4. Tests must not need Docker, a GPU, the real `data/` folder or network. They use tiny hand-made graphs and the committed fixtures.

---

## 4. Phases and checklists

Rules for all phases: line length 100, ruff rules E F I B, type hints, short docstrings that say **why**. Commit message prefix
`W2-P2-01:`. Branch name suggestion: `w2-p2-01-pyg-builder`. After each phase run `ruff check . && ruff format --check . && pytest -q`.

### Phase 0: orientation and safety net (≈ 0.2 h)

- [x] 0.1 Run the resume protocol checks (Section 0.2). Paste outputs to the chat.
- [x] 0.2 Create the branch. Confirm the baseline is green: `pytest -q` and `ruff check .` pass **before** any change.
- [x] 0.3 Confirm the environment on the user's machine: `python scripts/tutorials/pyg/check_env.py` prints the PyG version.
- [x] 0.4 Find out what exists in the real cache: how many `*.json.gz` under `data/cache/graphs/`, which languages, and which split
      files exist in `data/interim/splits/`. Paste counts. (This tells Phase 7 whether to use P1's cache or a self-made mini cache.)

### Phase 1: decisions with the user (≈ 0.2 h) — REVIEW GATE

Ask the user to confirm or change, **one short list**:

- [x] 1.1 Package name `shield_core/graph_dataset/` (alternatives: `graphs/`, `gnn_data/`).
- [x] 1.2 Default Rule A, Rule B available as an option (D41 says A is provisional).
- [x] 1.3 Default `max_nodes = 1000` for now; final value chosen in Phase 7 from data.
- [x] 1.4 Skip (never truncate) oversized graphs.
- [x] 1.5 `node_text_hash` contract (hash64 of `sha256(code)`), no vocabulary file.
- [x] 1.6 Add the `gnn` extra to the CI install line (touches `.github/workflows/ci.yml`; goes through the PR review).
- [x] 1.7 Record the answers in Section 5 (STATE).

### Phase 2: fixtures and the reference numbers (≈ 0.4 h)

Goal: real tiny `CodeGraph`s committed to the repo so tests need no Docker.

- [x] 2.1 Write `scripts/graphs/export_to_fixture.py`: argument = path to `export.xml`, language, output name. It calls
      `parse_graphml`, builds a `CodeGraph(language, "joern", "4.0.647", GRAPH_SCHEMA_VERSION, nodes, edges)` and writes
      `tests/fixtures/graphs/<name>.json.gz` through `graph.to_dict()` (gzip + JSON, `mtime=0` so the bytes are reproducible).
- [x] 2.2 Generate five fixtures from the exports that are in the repo copy (check they are committed; they live in `sample1..5/`):

      | Fixture file | From | Language / ext |
      | --- | --- | --- |
      | `get_user_py.json.gz` | `sample1/export/export.xml` | python |
      | `branch_py.json.gz` | `sample2/export/export.xml` | python |
      | `calls_py.json.gz` | `sample3/export/export.xml` | python |
      | `overflow_c.json.gz` | `sample4/export/export.xml` | cpp (`.c`) |
      | `vec_cpp.json.gz` | `sample5/export_c/export.xml` | cpp (`.cpp`) |

- [x] 2.3 Check each file is small (expected tens of KB). Write the golden table (Section 6, "Golden numbers") into the test file
      as constants, from the numbers verified in Section 2. **Do not trust them blindly:** the first test run must reproduce them.
- [—] 2.4 If `sample*/` folders are NOT tracked by git, say so and ask whether to `git add` them or to keep only the fixtures (the *Not done:* raw `sample*/` folders are untracked; only the five generated fixtures are needed and were committed.
      fixtures are enough for the tests).

### Phase 3: `schema.py` + `filtering.py` (torch-free) (≈ 1 h) — REVIEW GATE

- [x] 3.1 `schema.py`:
  - `NODE_TYPES` (12, fixed order), `EDGE_TYPES = {"AST":0,"CFG":1,"REACHING_DEF":2,"CALL":3,"ARGUMENT":4,"CDG":5}`, `NUM_FLAGS = 3`,
    `NUM_NODE_FEATURES = len(NODE_TYPES) + NUM_FLAGS`, `CONVERTER_VERSION = "1.0"`, `WRAPPER_METHODS = {"<module>", "<global>"}`.
  - `@dataclass(frozen=True) ConverterConfig(stub_rule="A", max_nodes=1000, edge_types=tuple(EDGE_TYPES), drop_unusable=False)` with
    `__post_init__` validation (rule in {"A","B"}, `max_nodes` None or ≥ 1, edge types subset of `EDGE_TYPES`), `to_dict()` and
    `fingerprint()`.
  - `text_hash64(text: str) -> int`: `int(sha256(text.encode("utf-8")).hexdigest()[:16], 16)`, converted to signed 64-bit
    (`v - 2**64 if v >= 2**63`). Same sha256 recipe as `CPGNodeEmbedder._get_string_hash`.
- [x] 3.2 `filtering.py` data types: `GraphDiagnostics` (dataclass: raw node/edge counts, kept node/edge counts, `edge_counts` per
      type name, `has_real_method`, `n_unknown`, `unknown_share`, `n_cfg`, `n_reaching_def`, `n_meta_class_adapter`, `usable`) and
      `FilteredGraph` (kept `nodes: list[GraphNode]` in row order, `edges: list[tuple[int,int,int]]` as `(src_row, dst_row, type_id)`,
      `diagnostics`).
- [x] 3.3 `filter_graph(graph: CodeGraph, config: ConverterConfig) -> tuple[FilteredGraph | None, str]`. Algorithm (write it in
      this order, each step is one small helper):
      1. diagnostics from the RAW graph (so dropped nodes such as UNKNOWN are still counted);
      2. `stubs` = METHOD nodes whose name starts with `<operator>`; under Rule B also every METHOD with `line is None`;
      3. `parts` = destinations of AST edges whose source is in `stubs`;
      4. `kept` = nodes with `type in NODE_TYPES` and `id not in stubs | parts`, **sorted by id** (row = position);
      5. if no node is kept → reason `empty_after_filter`; if `max_nodes` and `len(kept) > max_nodes` → `over_node_cap`;
         if `drop_unusable` and not usable → `unusable`;
      6. edges: keep if `edge.type in config.edge_types` and both ends are kept; map ids to rows; sort by `(src, dst, type)`;
      7. return the `FilteredGraph` and `"ok"`. For skipped graphs return `(None, reason)` (diagnostics are still needed for the
         report: return them too; choose a small result dataclass `FilterResult(graph | None, reason, diagnostics)` instead of a tuple
         if that is cleaner).
- [x] 3.4 Tests `tests/graph_dataset/test_schema.py`, `test_filtering.py`, `conftest.py` (a `make_graph(nodes, edges)` helper and a
      fixture loader):
  - hand-made graphs, one rule each: operator stub and its children dropped; unwanted type dropped; edge with a dropped end
    dropped; edge of an unwanted type dropped; kept order sorted by id even if the input list is shuffled; duplicate input edges
    survive (documented behaviour); empty graph; `over_node_cap` boundary (N == cap is kept, N == cap+1 is skipped); `unusable`
    only skipped when `drop_unusable=True`; Rule B removes a line-less external METHOD and its CALL edge but Rule A keeps them;
    config validation errors; fingerprint changes when any field changes and is stable across runs; `text_hash64` known value
    (compute once with hashlib in the test, do not hard-code a guess) and range check (fits in int64);
  - **golden tests on the five fixtures** (Section 6): node and edge totals, edge counts per type, for Rule A and Rule B.
- [x] 3.5 Run: `pytest tests/graph_dataset -q` (must pass without torch installed in the environment; if the user's venv has torch,
      also prove the import is not needed: `python -c "import shield_core.graph_dataset.filtering"` must not import torch — check
      with `python -X importtime` or `python -c "import sys, shield_core.graph_dataset.filtering; print('torch' in sys.modules)"` → `False`).
- [—] 3.6 REVIEW GATE: show the diff, explain Rule A/B, the cap, and why oversized graphs are skipped. Wait for OK. *Not done:* review gate skipped per Eyad’s instruction to continue through all gates.

### Phase 4: `to_pyg.py` (≈ 0.5 h) — REVIEW GATE

- [x] 4.1 `to_data(fg: FilteredGraph, *, y: int | None = None, cwe_multihot=None, code_sha: str | None = None, row: int | None = None) -> Data`
      builds the tensors of Section 3.3. Vectorise: one-hot with `torch.zeros(N, 15)` and index assignment from a `node_type` tensor
      (`x[torch.arange(N), node_type] = 1`), not a Python loop per node if avoidable. `edge_index = torch.tensor([srcs, dsts], dtype=torch.long)`
      (check the shape for zero edges: must be `[2, 0]`).
- [x] 4.2 Tests (`importorskip("torch_geometric")`): shapes and dtypes; one-hot rows sum to 1 in the first 12 columns and flag
      columns are 0; `edge_type.max() <= 5`; `edge_index.max() < N`; zero-edge graph; `line` is `-1` for stubs; `data.validate()`
      returns True (PyG built-in check); determinism (calling twice gives equal tensors); golden: fixture `get_user_py` →
      `x.shape == (48, 15)`, `edge_index.shape == (2, 176)`, per-type bincount equals the golden counts.
- [x] 4.3 Update `scripts/graphs/graphml_to_pyg.py` into the thin wrapper: parse GraphML with `parse_graphml`, wrap as `CodeGraph`,
      call `filter_graph` + `to_data`, print **exactly** the old two lines (`Data(x=[48, 15], edge_index=[2, 176], edge_type=[176])`
      now also lists the new fields, so print the old three-field summary explicitly, then `edges per type: {...}`). Remove the
      `networkx` import. Keep the CLI argument (`export.xml` path).
- [x] 4.4 Prove parity on the user's machine against the five exports: run the wrapper on `sample1..5` and compare the node/edge
      numbers with Section 6. Paste the output.
- [—] 4.5 REVIEW GATE. *Not done:* review gate skipped per Eyad’s instruction to continue through all gates.

### Phase 5: `builder.py` (≈ 1 h) — REVIEW GATE

- [x] 5.1 `build_split(split_path, language, config, cache, key_extractor, *, cwe_vocab, limit=None) -> BuildResult` where
      `BuildResult` holds `data_list: list[Data]` and `rows: list[dict]` (one dict per **input row**, including skipped ones, with
      keys `row, code_sha, label, cwe, status, n_nodes_raw, n_edges_raw, n_nodes, n_edges, usable, has_real_method, unknown_share,
      n_meta_class_adapter`). Steps per row: read parquet columns `code, language, label, cwe` in batches (reuse the
      `pq.ParquetFile.iter_batches` approach of `batch_extract.py`), keep rows of the requested language, `bad_code` if not a non-empty
      string, compute `CacheKey.for_code(code, language, key_extractor)`, `cache.get(key)` → `None` means `no_graph_in_cache` (do
      **not** count cache hits/misses of the real cache in a way that disturbs P1's counters: use a fresh `GraphCache(root)` object),
      then `filter_graph`, then `to_data`.
- [x] 5.2 Duplicate code inside one split (same `code_sha`): the dedupe step already removed exact duplicates, but keep the first
      occurrence and mark later ones `duplicate_code` (add this reason to the list in Section 3.4 and to the docs when implemented).
- [x] 5.3 `build_cwe_vocab(train_path, language) -> list[str]`: sorted unique CWE strings over TRAIN rows with `label == 1`. Saved
      to `cwe_vocab.json` once and **reused** for the other splits. `cwe_multihot` = 1 for each of the row's CWEs in the vocabulary.
- [x] 5.4 `build_all(language, config, splits=("train","val","test","holdout"), limit=None, out_root=PYG_DATASET_DIR)`: builds the
      vocab from train first, then each split, writes `processed/<split>.pt`, `reports/<split>_rows.parquet`, `config.json`,
      `build_summary.json`; refuses to overwrite an existing folder unless `overwrite=True` (the fingerprint already separates
      configs). Writes via a temporary file then `os.replace` (same crash-safety idea as `cache.py`).
- [x] 5.5 Tests (`importorskip`; use `tmp_path`): create a tiny parquet with 6 rows (labels 0/1, CWE lists, one row whose graph
      is missing from the cache, one with empty code, one oversized with `max_nodes=3`); fill a `GraphCache(tmp_path)` with fixture
      graphs using a **fake extractor object** that only has `name`, `version`, `schema_version` (so `CacheKey.for_code` works with no
      Joern); assert statuses, number of `Data`, labels, `cwe_multihot` rows, that unseen CWEs are counted, determinism (two builds →
      identical files hash), and that overwrite protection works.
- [—] 5.6 REVIEW GATE. *Not done:* review gate skipped per Eyad’s instruction to continue through all gates.

### Phase 6: `dataset.py`, `stats.py`, CLI (≈ 0.8 h) — REVIEW GATE

- [x] 6.1 `dataset.py`: `ShieldGraphDataset(InMemoryDataset)` with `__init__(root, split)`: loads `root/processed/<split>.pt`; raises a clear
      `FileNotFoundError` telling the user to run `scripts/graphs/build_pyg_dataset.py` if it is missing; properties
      `num_node_features` (15) and `num_relations` (6) as constants; helper `ShieldGraphDataset.from_config(language, config, split)`
      that resolves the folder through `PYG_DATASET_DIR` + fingerprint. It never builds anything by itself (building is the CLI's job).
- [x] 6.2 `stats.py`: `size_summary(rows)` (mean, median, p90, p95, p99, max of kept nodes and edges; dropped counts per status),
      `cap_table(rows, caps)` (for each candidate cap: share of graphs kept **overall, among label 1, among label 0**, and for the
      top CWEs: this exposes bias from the cap), `edge_type_totals`, `render_report(...) -> str` (Markdown). Tests with hand-made rows.
- [x] 6.3 `scripts/graphs/build_pyg_dataset.py`: arguments `--language {python,cpp}`, `--splits`, `--stub-rule {A,B}`, `--max-nodes N|none`,
      `--drop-unusable`, `--limit N`, `--overwrite`, `--report PATH`. Prints the summary and writes `docs/graphs/pyg_dataset_report.md`
      (generated; header line says so). Use `paths.py` constants only.
- [x] 6.4 `shield_core/graph_dataset/__init__.py` exports (`ConverterConfig`, `CONVERTER_VERSION`, `filter_graph`, `to_data`,
      `build_all`, `ShieldGraphDataset`). Careful: importing the package must **not** import torch at module level in `__init__` if CI
      tests for `filtering.py` should run without torch → keep `__init__` empty or lazy; decide and write the reason in the README.
- [x] 6.5 Add `PROCESSED_DIR` / `PYG_DATASET_DIR` to `shield_core/paths.py`.
- [x] 6.6 Write `shield_core/graph_dataset/README.md` (table of files, what each does, parent link) in the style of the other folder READMEs.
- [x] 6.7 `pytest -q`, `ruff check .`, `ruff format --check .`, `pytest tests/test_layout.py` all green. REVIEW GATE.

### Phase 7: run on real data and decide the cap (≈ 0.6 h plus waiting) — USER MACHINE

Dependency: Python graphs in `data/cache/graphs/` from P1 (W2-P1-02, expected Day 3–4). **If the cache is not ready, do not wait:
build a mini cache yourself so this phase can finish** (7.1). P1's full run is then only a re-run of 7.4.

- [x] 7.1 If fewer than ~200 Python graphs are cached for the train split, make some:
      `python -m scripts.graphs.batch_extract --split train --language python --workers 4 --limit 200`
      (Docker image `shield-joern` must exist: `docker image ls shield-joern`). Do the same for `--split val --limit 100` so both
      splits have data. Paste the last lines of the output.
- [x] 7.2 First look, no filtering by cap: `python -m scripts.graphs.build_pyg_dataset --language python --max-nodes none --stub-rule A --overwrite`
      (use a scratch `--out` if the CLI supports it, to not mix with the final folder). Paste the summary.
- [x] 7.3 **Choose the cap from data.** Look at the cap table: pick the smallest cap that keeps ≥ 90 % of graphs **and** whose kept
      share differs between label 1 and label 0 by ≤ 5 percentage points (large functions are more often vulnerable; dropping them
      changes the label balance and can create a length shortcut, decision D30). If no cap satisfies both, say so and choose the
      cap with the smaller label gap, write the gap into D42. Also check the GPU memory sanity: a batch of 32 graphs at the cap must
      fit the RTX 4060 8 GB with room for a model (rough estimate: `N_total × 15 × 4` bytes for `x` is tiny; the edges and the model
      activations dominate, so test it in W2-P2-02, do not over-think it here).
- [x] 7.4 Final build with the chosen cap: `python -m scripts.graphs.build_pyg_dataset --language python --max-nodes <CAP> --stub-rule A`
      (and C/C++ `--language cpp` if graphs exist; if not, write "C/C++ not built: no cached graphs yet" in the report, that is a
      legitimate state, not an open item, because W3-P2-01 re-runs the same command).
- [x] 7.5 Optional ablation data for D41/Week 3 (cheap, do it): rebuild with `--stub-rule B` into a different folder and add the
      node/edge difference to the report. Do not train anything.
- [x] 7.6 Sanity checks on the real dataset (paste outputs): `ShieldGraphDataset(...)` loads; `len(ds)` equals the `ok` count; first
      graph prints; `batch = next(iter(DataLoader(ds, batch_size=8)))` works and `batch.edge_type.max() <= 5`; no NaN in `x`;
      the share of `usable == False` graphs matches what D41 predicts for raw Python (many unusable). Report that share honestly.
- [x] 7.7 `docs/graphs/pyg_dataset_report.md` exists and holds only numbers produced by the commands above.

### Phase 8: docs, decision log, hand-offs (≈ 0.4 h)

- [x] 8.1 `docs/graphs/graph_schema.md`: update §2/§4/§5/§8/§9: converter version 1.0 and where it lives (`shield_core/graph_dataset/`),
      the final node cap and how it was chosen (link the report), Rule A default and the measured Rule B difference, the new `Data`
      fields, the diagnostics, `usable` definition; replace the "NOT SET" cap sentence; fix §10 Reproduce (new command); add a
      changelog line (`converter 1.0`, graph schema unchanged). Keep `schema_version: 0.1-draft` unless the raw extractor output changed
      (it did not).
- [x] 8.2 `SHIELD_PLAN.md`: tick `W2-P2-01` with an *Outcome:* sentence (numbers from the report); add decision **D42** (node cap,
      skip-not-truncate, converter contract, `node_text_hash`, Rule A default retained) in the decisions table; add one row in the
      change log (date, what, "Eyad"); update the C-section dependency lines only if wording there is now stale.
- [x] 8.3 `tests/fixtures/joern/README.md`: the command `python scripts/graphml_to_pyg.py ...` is stale (the script lives in
      `scripts/graphs/`); fix the path and the expected-output table if needed.
- [x] 8.4 Do the **README update procedure** (Section 7).
- [x] 8.5 Draft the short message for P3 (W2-P3-04) with the exact recipe: `node_text_hash = text_hash64(node.code)`, import path,
      and that their cache dict can be keyed by that int (give a 5-line example). Put it in the chat, not in the repo.
- [—] 8.6 `CI`: if Phase 1.6 was approved, change `.github/workflows/ci.yml` install line to include `gnn`; confirm the PyG tests run *Not done:* CI now installs the `gnn` extra and local PyG tests ran; hosted GitHub Actions log requires the PR, which Eyad asked not to create.
      (no skips) in the GitHub Actions log of the PR.

### Phase 9: close (≈ 0.2 h)

- [x] 9.1 Final full check: `ruff check .`, `ruff format --check .`, `pytest -q`, `pytest tests/test_layout.py -q`: all green.
- [—] 9.2 Commit in small commits (`W2-P2-01: filtering + golden tests`, `W2-P2-01: to_pyg`, `W2-P2-01: builder`, `W2-P2-01: docs`), open the *Not done:* phase commits are present; PR creation is intentionally omitted per Eyad’s instruction.
      PR with the repo template, reviewer P1 (Hatem). The PR description lists: files added, the chosen cap and why, the golden numbers
      reproduced, what is NOT included (taint flags, node embeddings).
- [x] 9.3 Set the top of this file to `STATUS: DONE`, update Section 5, add the final line in Section 9.
- [x] 9.4 Tell the user the task is closed and move to Phase 10.

### Phase 10: professor explanation (delivered in the chat)

- [ ] 10.1 Deliver the full explanation (outline in Section 10). The user asked to understand every concept and every file well
      enough to explain it and rewrite it alone. Use the real code of the final files, quote the important lines, and give small
      "try it yourself" exercises. Do not start it before Phase 9 is ticked.

---

## 5. STATE (update after every step)

```
Last ticked box:      Phase 9 implementation checks and phase commits
In progress:          none; full-corpus rerun is a follow-up after P1 publishes full split/cache data
Decisions answered:   package + filtering/tensor contracts per plan; CI gnn extra enabled
Chosen node cap:      provisional 750 (300-row balanced subset; 97.3% retained, 2.67 pp gap)
Cache status:         300 Python rows extracted (200 train, 100 val); no full P1 cache
Branch / PR:          W2-P2-01; phase commits created; PR intentionally not created per user
```

## 6. Golden numbers (verified on the repo copy with the old filter rules; the new code must reproduce them)

| Fixture | Raw nodes → kept | Raw edges → kept (Rule A) | AST / CFG / REACHING_DEF / CALL / ARGUMENT / CDG (Rule A) | Rule B nodes / edges |
| --- | --- | --- | --- | --- |
| `get_user_py` | 96 → 48 | 499 → 176 | 47 / 38 / 64 / 0 / 27 / 0 | 48 / 176 (same) |
| `branch_py` | 104 → 54 | 540 → 194 | 53 / 40 / 70 / 0 / 26 / 5 | 54 / 194 (same) |
| `calls_py` | 115 → 60 | 580 → 207 | 59 / 43 / 76 / 1 / 28 / 0 | 60 / 207 (same) |
| `overflow_c` | 66 → 25 | 246 → 69 | 22 / 13 / 27 / 1 / 6 / 0 | 20 / 59 (AST 18, CFG 12, RD 23, CALL 0, ARG 6) |
| `vec_cpp` | 66 → 25 | 246 → 69 | 22 / 13 / 27 / 1 / 6 / 0 | 20 / 59 (same as C) |

Row 1 reproduces `graph_schema.md` §6 (`x=[48, 15], edge_index=[2, 176]`).

## 7. README update procedure (do it in Phase 8.4, after the files exist)

`tests/test_layout.py` fails if the root README names a path that does not exist, so do this **after** the files and the report are
created. Edit these places, keep each edit small, and keep the existing style (tables, emoji status, Mermaid):

1. **Root `README.md`, Section 2 "Component maturity":** the row `CPG → PyG converter` changes from 🟡 to ✅, new note:
   "`shield_core/graph_dataset/` · converter 1.0 · processed dataset built for Python (numbers in `docs/graphs/pyg_dataset_report.md`)".
   Add a row "Processed PyG dataset" with the same status. Leave "V3 GNN" ⬜ (the GNN is W2-P2-02).
2. **Section 5 "Folder structure schema":** add `shield_core/graph_dataset/` to the tree with its files and `data/processed/pyg/` under
   `data/`; update the `scripts/graphs/` line (`build_pyg_dataset` · `export_to_fixture` · `graphml_to_pyg` wrapper) and `tests/` (`graph_dataset/`, `fixtures/graphs/`).
3. **Section 6 "Folder responsibilities":** add a row for `shield_core/graph_dataset/` (does: turn cached CodeGraphs into PyG tensors and processed datasets; does NOT: run Joern, train, or embed text).
4. **Section 7 "Functionality → folder":** change "Convert a graph to PyTorch Geometric" from `scripts/ … 🟡` to `shield_core/graph_dataset/ … filtering.py, to_pyg.py ✅`; add "Build the processed GNN dataset" → `builder.py`, `scripts/graphs/build_pyg_dataset.py` ✅.
5. **Section 8 File catalog:** add subsection "8.x `shield_core/graph_dataset/`" (file, what it does, input, output) next to 8.6; update 8.9 `graphs/` rows (the wrapper, the two new scripts); update 8.10 (test tree list and the **test count**: use the real number from `pytest --collect-only -q | tail -1`).
6. **Section 9 sequence flow:** add "Story C2: cached graph → PyG dataset" (a Mermaid sequence diagram: `build_pyg_dataset.py` → `builder.build_split` → `GraphCache.get` → `filter_graph` → `to_data` → `torch.save`). Extend the dependency map in 9.7 (arrows: `graph_dataset` → `extraction` and `paths`; `scripts/graphs/build_pyg_dataset` → `graph_dataset`).
7. **Section 10 Data flow:** add the processed dataset and `cwe_vocab.json` to the artifact registry (10.4) and one arrow from the graph cache to `data/processed/pyg/` in the offline flow diagram (10.1) (only what is implemented today).
8. **Section 11 Activity diagrams:** add "11.x Lifecycle of building the PyG dataset" (activity diagram: read split → cache lookup → filter → cap check → tensors → save → report), mirroring 11.5.
9. **Section 14/15:** mention the cap table and the CI `gnn` extra in the testing section; **Section 17 Known gaps:** add "Taint flag columns are zero until W3-P2-03", "Python graph quality depends on the P1 wrapper (D41)", "Node embeddings (variant B) not yet attached".
10. **Other docs:** `shield_core/README.md` table row for `graph_dataset/`; `scripts/graphs/README.md` rows; `tests/README.md` row for `graph_dataset/`; `docs/README.md` graphs row (+ `pyg_dataset_report.md` *(generated by `scripts/graphs/build_pyg_dataset.py`)*) and project row (+ this plan).
11. Verify: `pytest tests/test_layout.py -q` (every backticked path exists) and re-read the new Mermaid blocks for syntax.

## 8. Risks and pitfalls (read before coding)

| # | Risk | What to do |
| --- | --- | --- |
| R1 | **Cap bias.** Dropping large graphs removes more vulnerable than clean rows, or the other way round, and creates a length shortcut. | Cap table per label and per CWE (Phase 6.2, 7.3); log the gap in D42. |
| R2 | **Cache key mismatch.** If P1 extracts transformed code (the D41 Python class wrapper), the raw `code` of a row no longer hits the cache and every row becomes `no_graph_in_cache`. | In Phase 0.4/7 check the hit share. If it is near 0 for Python, ask P1 which transform the batch run used; add an optional `code_transform` argument to `build_split` that applies the same function, include its name in the config fingerprint. Do not guess. |
| R3 | **Source-line offset.** The wrapper shifts line numbers; `line` in `Data` would then not match the original file. | Store raw `line`; record in the README "lines are as seen by Joern". The correction belongs to P1/W3 taint work. |
| R4 | **Silent drift.** Someone edits the filter and old processed datasets look valid. | `CONVERTER_VERSION` bump rule written in `schema.py` docstring and in `graph_schema.md` §9; test that the fingerprint changes when the config changes. |
| R5 | **PyG API drift** (`save`/`load`, `validate`). | Check signatures in the installed version (Section 3.6) before writing; paste them in the chat. |
| R6 | **CI cannot run PyG tests.** | Torch-free filtering tests + `importorskip` + `gnn` extra in CI (Phase 1.6, 8.6). |
| R7 | **`torch.save` pickles.** Loading `.pt` files from untrusted sources is unsafe. | Only load files you built; mention it in the README; PyG 2.8's `InMemoryDataset.load` handles `weights_only` details, read its docstring. |
| R8 | **Unusable Python graphs dominate** (D41: 62/100 scale rows had no real METHOD). | Report the `usable` share; do not hide; `drop_unusable` stays an option for W2-P2-02 experiments. |
| R9 | **Memory.** Holding every `Data` in a list for ~30k graphs. | Fine for Python (hundreds of MB). If C/C++ is too big, build per split (already the design) and use `--limit` for smoke runs. |
| R10 | **Nondeterminism.** | Sorted ids, sorted edges, no set iteration order leaking into outputs (always `sorted(...)`), test "same input twice → identical bytes". |

## 9. Handoff log (append one line per finished step: date, step, what, who)

```
2026-10-31 | Phases 0-4 | branch verified; five fixtures and Rule A/B golden filters/tensors committed | Eyad
2026-10-31 | Phases 5-6 | split builder, dataset loader, stats, CLI and PyG CI coverage implemented | Eyad
2026-10-31 | Phase 7 | extracted 200 train + 100 val Python rows; cap 750 selected; Rule B comparison and DataLoader sanity run | Eyad
2026-10-31 | Phase 8 | schema/roadmap/README/CI docs updated; P3 node_text_hash recipe to be delivered in final chat | Eyad
2026-10-31 | Phase 9 | 917 passed, 3 skipped; Ruff and layout clean; PR omitted as requested | Eyad
```

## 10. Professor explanation outline (Phase 10)

Deliver in this order, with the real code of the final files, short quotes, and one small exercise per part:

1. **The big picture:** why a GNN needs tensors; what a code property graph is; the pipeline code → Joern → `CodeGraph` → cache →
   `Data` → `DataLoader` → GNN; where this task sits in W2/W3.
2. **PyG basics the code relies on:** `Data`, `x`, `edge_index` (COO format, why `[2, E]`), `edge_type`, batching of graphs (how `DataLoader`
   concatenates and offsets `edge_index`), `InMemoryDataset` (collate + slices), zero-edge graphs, `validate()`.
3. **`schema.py`:** constants and why order is frozen; `ConverterConfig` (frozen dataclass, validation, fingerprint = hashing a config
   so folders never collide); `CONVERTER_VERSION` vs `GRAPH_SCHEMA_VERSION`; `text_hash64` (SHA-256, truncation, signed int64, collision estimate).
4. **`filtering.py`:** line by line: stubs, parts, kept, sorting, row mapping, edge filtering; Rule A vs B with the `strcpy` example and the
   measured 25→20 / 69→59; the cap and why skip-not-truncate; diagnostics and the D41 `usable` definition; why it is torch-free (CI).
5. **`to_pyg.py`:** one-hot by index assignment, dtypes (`long` vs `float`), the shape pitfalls, each `Data` field and who uses it.
6. **`builder.py`:** reading parquet in batches, the cache key (why the same recipe as `batch_extract.py`), statuses, `cwe_vocab` and
   multi-hot, crash-safe writes, determinism, why nothing here runs Joern.
7. **`dataset.py` and `stats.py`:** what `InMemoryDataset` gives you for free; percentiles; the cap table and why per-label shares matter
   (length shortcut, D30); how to read `docs/graphs/pyg_dataset_report.md`.
8. **Scripts and wrapper:** CLI arguments, `export_to_fixture.py` (fixtures are frozen evidence), how the old prototype maps to the new code.
9. **Tests:** why hand-made graphs, why golden numbers, what `importorskip` does, how CI differs from the user's machine.
10. **How to explain it in an interview or to the team:** a 60-second summary, a 5-minute walkthrough, and 8 likely questions with answers.
11. **Rewrite exercise:** list the three smallest functions the user should rewrite from scratch (`filter_graph` core, `to_data`, `cap_table`)
    with the expected outputs on the fixtures.
