# SHIELD taint spike (W1-P2-03): results for Python and C/C++

> Status: **both parts complete.** Part A = Python, Part B = C/C++. Deliverables of the spike:
> this file, `sources` / `sinks` / `sanitizers` in `languages/python.yaml` and `languages/cpp.yaml`,
> the registry support for them (`languages/registry.py`), the query generator
> (`shield_core/taint/joern_queries.py`) and the driver (`scripts/taint/run_taint_spike.py`).
> Labels: **OBSERVED** = printed by Joern in our session. **INFERENCE** = my reading of observed
> output, not tested directly. **UNTESTED** = no evidence either way. **UNVERIFIED** = written but
> never run against Joern.

---

# Part A: Python
---

## 1. What the spike had to answer

1. Can Joern follow a source to sink flow inside one function? **Yes.**
2. Does it follow flows across functions? **Yes through calls (to a configurable depth), no through shared object state.**
3. What does it miss or over-report, and why? See section 6.
4. Which sources, sinks and sanitizers go into the YAML? See section 4 and section 8.

## 2. Environment

| Item | Value |
|---|---|
| Joern | 4.0.647 (image `shield-joern`, Dockerfile in `docker/joern/`) |
| Host | Windows, PowerShell, Docker Desktop |
| Container start | `docker run --rm -it -v "${PWD}\tests\fixtures\taint:/workspace/sample" shield-joern joern` |
| Python import | `importCode.python("sample/python")` (**not** `importCode.pythonsrc`, which does not exist in this shell; `joern-parse --language pythonsrc` is a different interface and is valid) |
| Default overlays | applied automatically on import; REACHING_DEF edges present |
| Engine defaults | `EngineConfig(maxCallDepth = 4, initialTable = None, shareCacheBetweenTasks = true, maxArgsToAllow = 1000, maxOutputArgsExpansion = 1000)` |

## 3. Shell pitfalls (these cost us several rounds)

1. **A multi-line `def` with `++` at the line ends fails** (`unindent expected, but eof found`). Put every definition on ONE line.
2. Path elements from `reachableByFlows` are typed `AstNode`. `.label`, `.code`, `.lineNumber` and `.astParent` work. `.method` does **not** compile: pattern-match to `CfgNode` first (`import io.shiftleft.codepropertygraph.generated.nodes.CfgNode`) to get `c.method.name` and `c.method.filename`.
3. `.p` output is unreliable for building steps: the `file` column is empty and identifier rows show the whole statement. Build steps from `(label, code, lineNumber)` ourselves.
4. Some `code` strings are multi-line (py06c, py09). Use `.code.split("\n").head`.
5. Always print `src.size` and `snk.size` BEFORE reading flows. An empty result means nothing until both endpoints are known to match.
6. Restart the container after adding fixtures; the CPG is built at import time.
7. Give every handler a unique name. Housekeeping: py01 and py02 both still define `handler`; identify them by `c.method.filename`, or rename them.

## 4. Final Python source and sink definitions

```scala
import io.shiftleft.codepropertygraph.generated.nodes.CfgNode
def src: Iterator[CfgNode] = cpg.call.code("request\\.args\\[.*|request\\.args\\.get\\(.*|request\\.form\\[.*|request\\.get_json\\(.*|input\\(.*|sys\\.argv\\[.*")
def snk: Iterator[CfgNode] = cpg.call.name("execute").argument(1) ++ cpg.call.name("system").code("os\\.system.*").argument(1) ++ cpg.call.name("run").code("subprocess\\.run.*").argument(1) ++ cpg.call.name("open").argument(1) ++ cpg.call.name("loads").code("pickle\\.loads.*").argument(1) ++ cpg.call.name("eval").argument(1)
val flows = snk.reachableByFlows(src).l
```

Rules learned:

- **A source is the node that PRODUCES the value** (`request.args["id"]`), not a sub-expression. With the field access `request.args` alone as the source, the flow query returned nothing (OBSERVED), although that node exists. Why: unknown. Do not guess in the report.
- **A sink is name + code prefix + argument index.** `db.cursor().execute(q)` is lowered so the receiver is argument 0 (`tmp0`) and `q` is argument 1. Selecting `.argument` without an index gave a second, duplicate flow ending on the receiver. Module-qualified calls (`os.system`, `subprocess.run`, `pickle.loads`) also have the module at index 0; bare calls (`open`, `eval`) do not. The payload is argument 1 in all five (OBSERVED).
- Name alone is not enough for some sinks: our own `run(cur, q)` helper in py04 would match a bare `name("run")`. Hence `code("subprocess\\.run.*")`.
- **Keyword arguments get index -1** (`shell = True` printed as `(-1, "True")`). A tainted value passed by keyword (`subprocess.run(args=x)`) would be missed by `argument(1)`. UNTESTED beyond the printed index.
- The sink receiver type is unknown: `execute` has `methodFullName = <unknownFullName>`, `typeFullName = ANY`, `DYNAMIC_DISPATCH`. Sinks can only be matched by name; any unrelated `.execute(...)` will match.

## 5. Fixture results

Folder: `tests/fixtures/taint/python/`. Each file has `# EXPECT:` written before running. Ground truth is what a human reading the code concludes.

Totals: **33 sources, 33 sinks, 26 flows** at the default depth. The 7 sinks without a flow are py02, py05, py10, py13 (all correct) and py11, py12b, py12e (known misses). With `maxCallDepth = 8`, py12b and py12e were recovered and py11 stayed missing.

| ID | Shape | Ground truth | Joern | Verdict |
|---|---|---|---|---|
| py01 | direct, `+` concatenation | flow | flow | ok |
| py02 | source read, constant reaches sink | no flow | no flow | ok (negative control) |
| py03 | defined helper returns tainted value | flow | flow | ok; path enters `wrap` |
| py04 | sink inside callee (argument to parameter) | flow | flow | ok; sink method is `run` |
| py05 | tainted value overwritten before sink | no flow | no flow | ok (negative control) |
| py06a/b/c | f-string / `%` / `.format` | flow | flow x3 | ok |
| py07 | dict literal, read the same key | flow | flow | ok (my "missed" hypothesis was wrong) |
| py07b | dict, read the SAFE key | no flow | **flow** | false positive: not key-sensitive |
| py08 | helper in another file via import | flow | flow | ok; path enters `build` body (resolved) |
| py09 | `request.args.get("id")` source | flow | flow | ok |
| py10 | tainted object is the RECEIVER, constant argument | no flow | no flow | ok (negative control) |
| py11 | `self.uid` written in one method, read in another | flow | **no flow** | miss; not fixed by depth 8 |
| py11b | same, write and read in one method | flow | flow | ok; isolates the cause of py11 |
| py12a/c/d | helper chains: 2, 3, 4 functions entered | flow | flow | ok |
| py12b/e | chains: 6 and 5 functions entered | flow | no flow at depth 4, flow at depth 8 | depth limit |
| py13 | parameterized query, taint in argument 2 | no flow | no flow | correct (by sink definition) |
| py14 | `int()` cast before use | not exploitable | flow | expected false positive; `int(...)` is visible in the path |
| py15a | `self.build(...)` instance method | flow | flow | path enters `build` (resolved) |
| py15b | `r = Repo(); r.build(...)` | flow | flow | path enters `build` (resolved) |
| py16a-e | `os.system`, `subprocess.run`, `open`, `pickle.loads`, `eval` | flow | flow x5 | ok |
| py17a-d | `input()`, `sys.argv[1]`, `request.form[...]`, `request.get_json()` | flow | flow x4 | ok |

Prediction record: py15a and py15b were predicted to possibly resolve differently; **wrong**, both enter the callee body (`... return ... -> RET -> self.build(...)` and `-> r.build(...)`).

## 6. Findings

### Works (OBSERVED)

- Intra-function flows through assignment, `+`, f-string, `%`, `.format`, container literal, and attribute access within one method.
- Cross-function flows through calls: argument to parameter (py04), return value back (py03), chains of up to 4 functions entered (py12a/c/d), cross-file import inside a single CPG (py08), instance-method calls via `self` and via an object (py15).
- Four negative controls gave no flow: constant to sink (py02), overwrite (py05), tainted receiver with constant argument (py10), parameterized query (py13).
- Patterns for CWE-89 (`execute`), CWE-78 (`os.system`, `subprocess.run`), CWE-22 (`open`), CWE-502 (`pickle.loads`) and CWE-95 (`eval`) all match and flow.
- **The sink call can be recovered from every flow.** For all 26 flows, `f.elements.last.astParent` is a `Call`, giving the sink's name and code (e.g. `("execute", "cur.execute(q)")`, `("system", "os.system(request.args[\"x\"])")`). The fixtures use `cur.execute(...)` with a simple receiver; the chained receiver `db.cursor().execute(q)`, which Joern lowers to `tmp0 = db.cursor()` plus `tmp0.execute(q)`, was checked separately and also gives `("execute", "db.cursor().execute(q)")` (section 9, OBSERVED).

### Limits

1. **Call depth is a configured limit.** `maxCallDepth = 4` gives flows through chains entering 2-4 functions and none through 5-6. Setting 8 with `EngineContext(config = EngineConfig(maxCallDepth = 8))` and `reachableByFlows(src)(using deepCtx)` recovered both. The plan's k=2 (W4-P2-01) is well inside the default. (OBSERVED)
2. **State shared across methods is invisible** (py11): no call connects the writer and the reader, and depth does not help. (OBSERVED)
3. **Unresolved calls are pass-throughs** (`escape(s)` in `calls.py`, which is never defined, sits inside a flow path). So "a flow exists" never means "unsanitized". `sanitizer_present` must be computed by us from the path (section 7). (OBSERVED)
4. **Not key-sensitive for containers** (py07b false positive). INFERENCE: the dict object `tmp0` is tainted as a whole.
5. **Joern cannot know that `int()` sanitizes** (py14): the flow is reported, and `int(request.args["id"])` appears as a path element, so a sanitizer-name scan can catch it. (OBSERVED)
6. **Sinks match by name only** (receiver type unknown, section 4). (OBSERVED)
7. **Keyword arguments are not positional** (index -1), so sinks defined as `argument(1)` miss keyword-passed taint. UNTESTED beyond the printed index.

### Lowering artifacts seen in paths

- Temporaries: `tmp0`, `tmp0 = {}`, `tmp0 = request.args` appear as path elements (py06c, py07, py09).
- A synthetic method `<metaClassAdapter>` per class (e.g. `handler_py11b<metaClassAdapter>`); it must not be counted as a real function in `graph_schema.md`.
- Consecutive duplicate elements (`q -> q`, `uid -> uid`).
- py16 paths have ONE element: the sink argument node **is** the source node. Because we select `argument(1)`, every path ends at the argument, which is why the sink call is recovered through `astParent`.

### Not tested (do not claim in the report)

Callbacks, decorators, framework entry points (Flask routes), cross-file flows when files are scanned separately, scale and time (fixtures are tiny; Week 2 measures cost), keyword-argument sinks, the `maxArgsToAllow` and `maxOutputArgsExpansion` caps, `*args`/`**kwargs`, generators, `async`, the chained-receiver sink shape under `astParent`.

### Bottom line

Joern's Python taint is usable for D13 as a **feature generator** (a path exists, its length, a sanitizer-like call in the path, the source and sink kinds). It is not usable as a finding by itself: it over-reports through dicts and unknown sanitizers, and under-reports through object state.

## 7. Mapping a Joern flow to `TaintPath` (`shield_core/interface.py`)

| `TaintPath` field | Source in the Joern flow |
|---|---|
| `source` | `code` of the first element (first line only) |
| `sink` | `name` and first line of `code` of `f.elements.last.astParent` (a `Call`, OBSERVED on 26/26 flows, and on the chained receiver `db.cursor().execute(q)`) |
| `steps` | one `TaintStep(file, line, code)` per element: file = `method.filename` (needs the `CfgNode` cast), line = `lineNumber`, code = first line of `code`; drop `tmpN` temporaries; collapse consecutive duplicates |
| `sanitizer_present` | true if any CALL element's name matches a sanitizer regex from the YAML. Observed examples: `escape(s)` (undefined helper), `int(...)` |

## 8. Design decisions this implies (log in plan Section 2 and Section 15)

> Items 1-3 below were proposals. They are settled in **Part B, section B7**, and implemented in
> `languages/registry.py` and `languages/python.yaml`. Item 4 is still open.

1. **YAML source/sink format.** Current `LanguageSpec` has `sources: tuple[str]` and `sinks: tuple[str]`. We need structured entries. Proposal (NOT yet agreed): a sink is `{name: regex, code: regex (optional), arg: int}`; a source is `{kind: call | argument | parameter, name or code: regex, arg: int (optional)}`. Python only needs `call`. The C batch decides whether `argument` and `parameter` are needed.
2. **Add `sanitizers`** (list of call-name regexes) to the registry. `registry._parse_spec` rejects unknown keys and `_REQUIRED_KEYS` must change, so `tests/test_registry.py` needs updating too. The registry belongs to P4. `graph_schema.md` already defines the `is_sanitizer` node flag.
3. **Draft `python.yaml` content** (proposal; illustrative syntax until decision 1 is agreed):

```yaml
sources:
  - {kind: call, code: 'request\.args\[.*'}
  - {kind: call, code: 'request\.args\.get\(.*'}
  - {kind: call, code: 'request\.form\[.*'}
  - {kind: call, code: 'request\.get_json\(.*'}
  - {kind: call, code: 'input\(.*'}
  - {kind: call, code: 'sys\.argv\[.*'}
sinks:
  - {name: execute, arg: 1}                                  # CWE-89
  - {name: system, code: 'os\.system.*', arg: 1}             # CWE-78
  - {name: run, code: 'subprocess\.run.*', arg: 1}           # CWE-78
  - {name: open, arg: 1}                                     # CWE-22
  - {name: loads, code: 'pickle\.loads.*', arg: 1}           # CWE-502
  - {name: eval, arg: 1}                                     # CWE-95
sanitizers: []   # observed as path elements: int(...), a helper named escape(...)
                 # candidates NOT yet tested: html.escape, shlex.quote, os.path.basename, os.path.realpath
```

4. **Interface naming inconsistency** in `shield_core/interface.py`: `Finding.taint_paths` (snake_case) but `Result.taintPaths` (camelCase). Raise it before the Friday freeze (W1-P4-01).

## 9. Python items still open (all small)

- [x] **Chained-receiver sink check** (closes the caveat in section 6). OBSERVED on `tests/fixtures/joern/calls.py`, where the sink is `db.cursor().execute(q)`: 1 source, 1 sink, 1 flow, and `f.elements.last.astParent` is `("execute", "db.cursor().execute(q)")`. It is the `execute` call with its original source text, not the `tmp0` assignment. So the sink call is recovered for a chained receiver as well; section 6 and `TaintPath.sink` need no special case.
- [ ] Add `tests/fixtures/taint` to the ruff exclude in `pyproject.toml` (fixtures use undefined names on purpose).
- [ ] Rename the two `handler` functions in py01/py02, or keep identifying them by file name.
- [ ] Optional extra fixtures: keyword-argument sink, callback, Flask-route entry point, `*args`.
- [x] `languages/python.yaml` is filled (see Part B, section B7).

## 10. Reproduction commands

```powershell
docker run --rm -it -v "${PWD}\tests\fixtures\taint:/workspace/sample" shield-joern joern
```
```scala
import io.shiftleft.codepropertygraph.generated.nodes.{CfgNode, Call}
importCode.python("sample/python")
// paste the two one-line defs from section 4, then:
src.size                         // expect 33
snk.size                         // expect 33
val flows = snk.reachableByFlows(src).l
flows.size                       // expect 26
flows.map(f => f.elements.last match { case c: CfgNode => c.method.name; case _ => "?" }).sorted.l
flows.map(f => f.elements.last.astParent match { case c: Call => (c.name, c.code.split("\n").head); case o => (o.label, o.code.split("\n").head) }).l
// depth experiment
import io.joern.dataflowengineoss.queryengine.{EngineConfig, EngineContext}
val deepCtx = EngineContext(config = EngineConfig(maxCallDepth = 8))
snk.reachableByFlows(src)(using deepCtx).size
```

## 11. Automated reproduction (driver)

The interactive commands of section 10 are replaced by the driver, which generates the one-line
definitions from `languages/python.yaml`:

```powershell
python -m scripts.taint.run_taint_spike --lang python                  # default depth 4
python -m scripts.taint.run_taint_spike --lang python --max-depth 8
```

Documented limits are encoded in `scripts/taint/run_taint_spike.py`: `KNOWN_MISSES` (py11),
`KNOWN_DEPTH_MISSES` (py12b, py12e; they apply only at depth <= 4), `KNOWN_FALSE_POSITIVES`
(py07b) and `SANITIZED_SINKS` (py14, through `int(...)`).

OBSERVED (Joern 4.0.647, image `shield-joern`, the prediction made before the run held exactly):

| Run | Counts | Verdicts |
|---|---|---|
| default depth 4 | 33 sources, 33 sinks, 26 flows | 29 OK, 3 KNOWN-MISS (py11, py12b, py12e), 1 KNOWN-FP (py07b), 0 UNEXPECTED |
| `--max-depth 8` | 33 sources, 33 sinks, 28 flows | 31 OK, 1 KNOWN-MISS (py11), 1 KNOWN-FP (py07b), 0 UNEXPECTED |

- The sanitizer column is `yes` for py14 only (through `int(...)`) and `-` on every other row.
- The 26 flows agree with section 5, and so do the four correct negative controls (py02, py05, py10, py13).
- Depth 8 recovers exactly py12b and py12e; py11 stays missing, as in section 6.
- The driver reproduces the interactive results of sections 4 to 6 with queries generated from `languages/python.yaml`, so the YAML is a faithful copy of the verified definitions.

---

# Part B: C/C++

## B1. What the spike had to answer

1. Can Joern follow a source to a sink in C, for each of the three source shapes (a call that returns the value, a call that writes it into an argument, a function parameter)?
2. Does it follow flows across functions, and how deep?
3. What does it miss or over-report: aliasing, libc semantics, C++ calls?
4. What goes into `languages/cpp.yaml`, and does the Python YAML format carry over?

## B2. Environment

| Item | Value |
|---|---|
| Joern | 4.0.647 (image `shield-joern`) |
| C import | `importCode.c("sample/c")` (OBSERVED). `.c` and `.cpp` files were picked up by the same call (OBSERVED with 4 `.cpp` fixtures; not tested on a whole C++ codebase) |
| Fixtures | `tests/fixtures/taint/c/c01 ... c24`, first line `// EXPECT: ...` written from the code, not from Joern |
| Shell rules | the Python rules (section 3 of Part A) held: one-line `def`s, count `src`/`snk` before reading flows, restart the container after adding fixtures |

## B3. Final C source and sink definitions

These lines are what the generator prints for `cpp.yaml` (`python -m scripts.taint.run_taint_spike --lang cpp --print-script`):

```scala
def src: Iterator[CfgNode] = cpg.call.name("getenv") ++ cpg.call.name("fgets").argument(1) ++ cpg.call.name("read|recv").argument(2) ++ cpg.call.name("scanf").argument(2) ++ cpg.method.parameter.name("argv")
def snk: Iterator[CfgNode] = cpg.call.name("system").argument(1) ++ cpg.call.name("fopen").argument(1) ++ cpg.call.name("strcpy").argument(2) ++ cpg.call.name("memcpy").argument(3)
```

Rules learned:

- **Three source shapes, all needed** (OBSERVED). `getenv` is a call that returns the value. `fgets`, `read`, `recv` and `scanf` write into an argument; the source must be that argument. With the `fgets` **call** as the only source, c03 gave **0 flows**; with `fgets` argument 1 it gave a flow. `argv` is a parameter node (c04).
- **Out-parameter indices** (OBSERVED, fixture c10): `fgets` buffer 1; `read` and `recv` buffer 2 (fd is 1); `scanf` first buffer 2 (format is 1); `gets` buffer 1.
- **Sink indices** (OBSERVED, c10): `system`, `popen`, `fopen` payload 1; `strcpy` and `strcat` destination 1 and source 2; `memcpy` destination 1, source 2, length 3; `sprintf` destination 1, format 2, values from 3 (variadic).
- **Every flow's sink call is recoverable** with `f.elements.last.astParent`: it was a `Call` in every C flow (OBSERVED, 13/13 in the run that printed it, which included the `memcpy` sink), although `system`, `strcpy` and `memcpy` are external stub methods.

## B4. Fixture results

Totals at the default depth for c01-c24 (OBSERVED, in the order they were run): the flow lists below are the ones printed in the session.

| ID | Shape | Ground truth | Joern | Verdict |
|---|---|---|---|---|
| c01 | `getenv` to `system` | flow | flow | ok |
| c02 | constant reaches the sink | no flow | no flow | ok (negative control) |
| c03 | `fgets(buf)` then `system(buf)` | flow | flow | ok, only with the argument as source |
| c04 | `argv[1]` into `strcpy` | flow | flow | ok, source is a parameter node |
| c05a | tainted value returned from a callee | flow | flow | ok, path crosses `RET` of `read_cmd` |
| c05b | sink inside a callee | flow | flow | ok, sink method is `run` |
| c06 | tainted value overwritten | no flow | no flow | ok (negative control) |
| c07 | `p = buf` BEFORE `fgets(buf)`, then `system(p)` | flow | **no flow** | miss |
| c07b | `fgets(buf)`, THEN `p = buf`, `system(p)` | flow | flow | ok (`buf -> buf -> p -> p`) |
| c07c | `p = buf`, `fgets(p)`, `system(buf)` | flow | **no flow** | miss |
| c08 | `snprintf` between source and sink | flow | flow | ok |
| c09 | length check before `system` | flow | flow | ok: a check does not stop injection |
| c10 | argument-index listing | not a flow fixture | n/a | used for B3 |
| c11, c12, c13 | `read`, `recv`, `scanf` then `system` | flow | flow x3 | ok |
| c14 | tainted length (via `atoi`) into `memcpy` argument 3 | flow | flow | ok, `atoi(...)` is a path element |
| c15 | `s.cmd = getenv(..)`, `system(s.cmd)` | flow | flow | ok |
| c16 | C++ `r.launch(getenv(..))`, sink in the method | flow | **no flow** | miss, call not linked |
| c17 | C++ source and sink inside one method | flow | flow | ok |
| c18 | C++ static call `Stat::launch_s(..)` | flow | **no flow** | miss, call not linked |
| c19 | C++ unqualified member call | flow | **no flow** | miss, call not linked |
| c20 | chain of 1 to 6 functions entered | flow x6 | 4 at depth 4, 6 at depth 8 | depth limit, same as Python |
| c21 | `strncpy` between source and `system` | flow | **no flow** | miss |
| c22a | `realpath` writes an output parameter, then `fopen` | flow | flow | ok; the `realpath` call is NOT a path element |
| c22b | `realpath` returns the value, then `fopen` | flow | flow | ok; `realpath(p, NULL)` IS a path element |
| c23 | `shell_escape` on one branch only, then `system` | flow | 1 flow, the sanitized path | see B5 |
| c24a-g | seven copy functions then `system` | flow x7 | 4 | `strcpy`, `strcat`, `memcpy`, `sprintf` flow; `strncpy` (x2) and `strncat` do not |

## B5. Findings

### Works (OBSERVED)

- Intra-function flows through assignment, struct field with the same access expression (c15), `snprintf`, `sprintf`, `strcpy`, `strcat`, `memcpy`, and the numeric conversion `atoi`.
- Cross-function flows through plain C calls in both directions (return value c05a, argument into callee c05b).
- Depth: the default `maxCallDepth = 4` follows chains entering 1 to 4 functions; `EngineContext(config = EngineConfig(maxCallDepth = 8))` recovered 5 and 6 (c20). Same behavior as Python. The cost of the higher depth is not measured.
- All four out-parameter sources work when the argument is the source: `fgets`, `read`, `recv`, `scanf`.
- Negative controls (c02, c06) gave no flow.

### Misses (OBSERVED; causes are partly explained, see below)

1. **Aliasing is not modeled.** A copy made after the write is followed (c07b); an alias made before the write is not, in either direction (c07, c07c). INFERENCE: taint is copied at assignment and there is no points-to analysis. Real code often reaches a buffer through another pointer, so taint features are an under-approximation there.
2. **`strncpy` and `strncat` lose the flow** (c21, c24b, c24d, c24g). The length expression is not the cause (constant `63` and `sizeof buf - 1` both fail). They are the bounded copies developers consider safe, so this hides taint behind the most common idiom.
3. **C++ calls are not linked to their methods.** For `r.launch(..)` (c16), `Stat::launch_s(..)` (c18) and an unqualified member call (c19) the call is bound to `<unresolvedNamespace>.name:<unresolvedSignature>` while the method is `Class.name:...`. A stub method with parameters `p0`, `p1` and no body is created, so taint never enters the real body. A flow entirely inside one method works (c17). Cause of the naming mismatch: UNTESTED.

### What is and is not known about the `strncpy` miss

This was investigated for several rounds. Recording it so nobody repeats the dead ends.

- The shipped default semantics contain entries for only four string functions: `strcmp`, `strlen`, `strncat`, `strncpy` (OBSERVED). `strcpy`, `strcat`, `memcpy`, `sprintf` and `snprintf` have none, and all of them flow.
- The shipped `strncpy` and `strncat` entries have the mappings 1 to 1, 2 to 2, 3 to 3, 1 to return, 2 to return, and no 2 to 1 (OBSERVED).
- **Query-time semantics work** (OBSERVED): giving `memcpy` an explicit entry without 2 to 1 removed its flow (c24e); adding 2 to 1 brought it back.
- **Query-time semantics do NOT fix `strncpy`** (OBSERVED): adding, replacing, and removing the `strncpy`/`strncat` entries all left the result at 4 of 7.
- Reaching-def edges (OBSERVED): for the working `memcpy`, the source argument `c` has an edge to a `buf` identifier. For the failing `strncpy` calls it has none, only the call itself and `RET`. The edge from the destination argument onward exists for both.
- INFERENCE (not proved): the data-dependence edge from the source argument to the destination is missing in the graph built at import, so no query-time setting can add it.
- UNTESTED: supplying semantics when the graph is built (import time). Not claimed to work.

Consequence for the project: `strncpy`/`strncat` flows are known false negatives. No `propagators` field was added to the YAML, because nothing verified would use it.

### Sanitizers

- A sanitizer is visible in a path in two different ways (OBSERVED, c22): when it returns the value (`realpath(p, NULL)`, c22b) the call is a path element; when it writes an output parameter (c22a) the elements are its arguments (`p`, `resolved`), and `realpath` is only their `astParent`. The matcher must therefore test, per path element, the element's own call name AND the name of the call it is an argument of. Confirmed on `realpath` by the driver (both forms); INFERENCE for other output-parameter functions.
- Unresolved calls pass taint through (`shell_escape`, `atoi`), as in Python. So "a flow exists" never means "unsanitized".
- **c23: only the sanitized path was reported** although the path that skips `shell_escape` exists in the code. Whether the engine merged the two paths or found only one is not established. Consequence: `sanitizer_present = true` means "at least one reported path to this sink passes a sanitizer", and must not be read as "the sink is protected".
- `realpath` canonicalizes but does not confine a path to a directory, so it is a weak sanitizer for CWE-22 on its own.
- `atoi` is not a sanitizer in C: the tainted number still reaches `memcpy`'s length (c14).

### Not tested (do not claim in the report)

`popen`, `strcat`, `sprintf` (variadic) and `gets` as sinks (indices observed, no flow tested); `gets` as a source; macros and function pointers; flows through heap structures and arrays of structs; `execl*`/`execv*`; multiple `scanf` buffers; real-size C++ code; CWE-416, CWE-476 and CWE-190, which are not taint problems and are outside what this spike can serve; scale and time (fixtures are tiny; Week 2 measures cost); whether `importCode.c` handles a project with include paths.

### Bottom line

Joern's C taint is usable as a **feature generator**: a path exists, its length, a sanitizer-like call in it, the source and sink kinds. It under-reports through aliasing, `strncpy`/`strncat`, and all C++ calls into callees; it over-reports through unresolved calls and incomplete sanitizer knowledge. For W2-P2-03 and W4-P2-01 this is a reason to scope interprocedural claims to C and Python and to treat C++ cross-function taint as not supported by the default call resolution.

## B6. Mapping a Joern flow to `TaintPath`

Same as Part A, section 7, with one change for the sanitizer flag:

| `TaintPath` field | Source in the Joern flow |
|---|---|
| `source` | `code` of the first element (first line only) |
| `sink` | name and first line of `code` of `f.elements.last.astParent` (a `Call` in every observed flow) |
| `steps` | one `TaintStep(file, line, code)` per element; drop `tmpN`; collapse consecutive duplicates (`clean_steps`) |
| `sanitizer_present` | true if, for any element, **the element is a call** or **its parent is a call** whose name fully matches a sanitizer regex from the YAML (`callNames` in the generated script) |

## B7. Decisions this implies (log in plan Section 2 and Section 15)

These replace the proposals in Part A, section 8.

1. **YAML source kinds: `call`, `argument` (with `arg`), `parameter`.** Needed by C, implemented in `registry._parse_sources`. An `argument` source names the call and the written argument index.
2. **Sinks take `arg` or `arg_from`, exactly one.** `arg_from` serves variadic calls such as `sprintf`. No active entry uses it yet (UNTESTED sink).
3. **Sanitizers stay a list of call-name regexes**, matched on the element and on the call it is an argument of (B6).
4. **No `propagators` field** (see the `strncpy` section): record the misses, do not invent a field without a verified effect.
5. **Entries are active only when their flow was observed.** Observed indices without an observed flow are comments in `cpp.yaml`.
6. **Queries are generated from the YAML** (`shield_core/taint/joern_queries.py`); nobody writes Scala by hand any more.
7. Plan edits: add rows to Section 2 and Section 15, tick W1-P2-03, and add the Part A item 4 naming question (`Finding.taint_paths` vs `Result.taintPaths`) to the Thursday sync.

## B8. Reproduction

Interactive (verified path):

```powershell
docker run --rm -it -v "${PWD}\tests\fixtures\taint:/workspace/sample" shield-joern joern
```
```scala
importCode.c("sample/c")
// paste the two one-line defs from B3, then:
src.size    // 41 with all fixtures c01-c24
snk.size    // 38
```

Automated (VERIFIED on Joern 4.0.647, image `shield-joern`):

```powershell
python -m scripts.taint.run_taint_spike --lang cpp                  # runs Docker and Joern
python -m scripts.taint.run_taint_spike --lang cpp --print-script   # only print the Scala
python -m scripts.taint.run_taint_spike --lang cpp --from-output out.txt
```

The driver prints one row per sink call (OK, KNOWN-MISS, NOW-OK, UNEXPECTED, SKIP) and a `sanitizer` column. The documented misses are listed in `KNOWN_MISSES` in `scripts/taint/run_taint_spike.py`.

Observed result with c01-c24 (OBSERVED): `sources: 41  sinks: 38  flows: 26` at the default depth, with 26 OK, 9 KNOWN-MISS, 3 SKIP and 0 UNEXPECTED. With `--max-depth 8` the flows are 28 (the two chains of 5 and 6 functions in c20 are recovered) and the verdicts are unchanged. The sanitizer column is checked against `SANITIZED_SINKS` (c22a, c22b, c23); OBSERVED: the column shows `yes` for exactly c22a, c22b and c23 and `-` for every other row. So the matcher (element is a call, or its parent is a call, matching the YAML list) works for `realpath` in both forms, and for the c23 path that passes `shell_escape`.

## B9. Open items

- [x] Driver run against Joern (default depth and `--max-depth 8`).
- [x] Driver re-run with the sanitizer column: `yes` for c22a, c22b and c23 only.
- [ ] Fixtures for the untested sinks (`popen`, `strcat`, `sprintf`, `gets`) and `execl*`; then enable them in `cpp.yaml`.
- [ ] Whether import-time semantics can fix `strncpy`/`strncat` (UNTESTED).
- [ ] Why C++ calls stay unresolved (names, missing type information?).
- [ ] Multi-line fixtures: the one-line `f_c24x` functions cannot show which `buf` identifier an edge reaches.
- [ ] Measure the time cost of `maxCallDepth = 8` in Week 2.
