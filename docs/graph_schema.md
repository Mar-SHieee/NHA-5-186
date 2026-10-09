# CPG to PyG graph schema (W1-P2-02)

**schema_version: 0.1-draft**

Status: Week 1 deliverable, ready for Gate G1 review. The node set, edge set and feature
layout below are implemented by `scripts/graphml_to_pyg.py` and checked against Joern 4.0.647
on Python (3 samples), C (1 sample) and C++ (1 sample), all tiny. Items marked TENTATIVE rest
on judgement or very little data and need an experiment. Bump `schema_version` whenever the
node set, edge set, feature layout or filter rules change (it is part of the graph cache key,
D5). The version string is unchanged from the first PR because no rule has changed since.

## 1. Granularity

Nodes follow Joern's native CPG, not one node per statement. Evidence: the single statement
`q = "SELECT..." + name + "'"` became 8 nodes (3 operator CALLs, 2 IDENTIFIERs, 2 LITERALs,
1 LOCAL). Operators (`=`, `+`) are CALL nodes named `<operator>.assignment` and
`<operator>.addition`.

## 2. Node types

Kept (TENTATIVE), in one-hot order: METHOD, METHOD_PARAMETER_IN, METHOD_RETURN, BLOCK, CALL,
IDENTIFIER, LITERAL, LOCAL, FIELD_IDENTIFIER, RETURN, METHOD_REF, CONTROL_STRUCTURE.

Dropped (TENTATIVE): FILE, META_DATA, NAMESPACE, NAMESPACE_BLOCK, TYPE, TYPE_DECL, BINDING,
MODIFIER, METHOD_PARAMETER_OUT, CLOSURE_BINDING, and, seen in C/C++ exports, IMPORT and
DEPENDENCY (they come from `#include`).

METHOD nodes in an export fall into three groups:

- Real functions (have a line number): kept.
- Wrapper methods: `<module>` in Python, `<global>` in C (two of them in the C sample, one for
  the file and one for includes). They hold no behaviour of their own but are kept (Rule A).
- Stubs (no line number, no code): `<operator>.*` stubs (assignment, addition, alloc,
  fieldAccess, indexAccess) are removed together with their AST children. Stubs for external
  functions such as `strcpy` (C) are kept under Rule A.

Verified: Python METHOD 6 -> 2, C METHOD 6 -> 4 (`copy`, two `<global>` wrappers, `strcpy`
stub). Not tested on classes, many functions or real project code.

## 3. Edge types

Direction follows Joern. Stored as `edge_type` (one integer per edge, same order as the
columns of `edge_index`). An edge is kept only if its type is in this table and both of its
end nodes are kept.

| id | Joern edge | Meaning | Status |
|---|---|---|---|
| 0 | AST | syntax tree, parent to child | keep |
| 1 | CFG | execution order | keep |
| 2 | REACHING_DEF | data flow (the "DFG") | keep |
| 3 | CALL | call site to callee | keep. Python: 1 edge in a two-function sample, none for a call to an undefined function. C and C++: a call to an external function (`strcpy`) gets a CALL edge to a stub METHOD |
| 4 | ARGUMENT | call to its arguments | keep; duplicates AST for the same node pair, may be redundant |
| 5 | CDG | control dependence | keep, see below |

Dropped (TENTATIVE): EVAL_TYPE, DOMINATE, POST_DOMINATE, CONTAINS, SOURCE_FILE, BINDS,
INHERITS_FROM, IMPORTS. Open: REF, PARAMETER_LINK, CONDITION, TRUE_BODY, CAPTURE, RECEIVER.

CDG evidence (Python branch sample): 5 CDG edges, all from the identifier `safe` (the `if`
condition) to the 5 nodes of `name = escape(name)`. The CFG alone also shows the bypass
(`safe` has two outgoing CFG edges, to the escape and past it), but CDG marks the sanitizer's
own nodes as conditional. Whether it helps the model is an experiment.

## 4. Node features

x = [one-hot node type (12) | is_source | is_sink | is_sanitizer | CodeBERT embedding of CODE].

- The one-hot and the three flag columns are implemented (15 columns). The flags are all 0
  until the taint spike (W1-P2-03) fills `source_sink_config` in the LanguageSpec YAML files.
- The CodeBERT embedding is frozen CodeBERT over the node's `CODE` text, cached by unique
  string (D20). It is added in Week 2 (W2-P3-04) and is not part of the current converter.
  Stub methods have the text `<empty>`; embedding their `NAME` instead is an open question.
- Two different nodes can have identical text (e.g. two `name` identifiers on one line), so
  nodes are keyed by Joern node id, never by text.
- Row order: kept node ids are sorted, so the same file always gives the same rows.
- Type information (buffer sizes, declared types) is dropped with TYPE and EVAL_TYPE. For C
  memory-safety bugs the only trace is the node text (e.g. `buf[8]`).

## 5. Size

Measured, before and after filtering:

| Sample | Lines | Nodes | Edges |
|---|---|---|---|
| Python get_user (vulnerable) | 6 | 96 -> 48 | 499 -> 176 |
| Python get_user with `if` | 6 | 104 -> 54 | 540 -> 194 |
| Python two functions (`clean` + `get_user`) | 7 | n/a -> 60 | n/a -> 207 |
| C `copy` with `strcpy` | 5 | 66 -> 25 | 246 -> 69 |
| C++ `copy` with `std::strcpy` | 5 | n/a -> 25 | n/a -> 69 |

Python: about 8 to 9 nodes per source line after filtering. A straight-line extrapolation
would put a 500-node cap near 55 lines and a 1000-node cap near 110 lines. This is a guess
from tiny samples, not a measurement. The C samples are too small to give a ratio.

Node cap: NOT SET (plan suggests 500 to 1000). Choose it from the node-count distribution of
real dataset functions (use P1's Joern spike sample sets), then drop oversized samples.

## 6. Worked example (Python get_user, vulnerable)

```python
def get_user(request, db):
    name = request.args["name"]
    q = "SELECT * FROM u WHERE n='" + name + "'"
    cur = db.cursor()
    cur.execute(q)
    return cur.fetchall()
```

Converter output:

```
Data(x=[48, 15], edge_index=[2, 176], edge_type=[176])
edges per type: AST 47, CFG 38, REACHING_DEF 64, CALL 0, ARGUMENT 27, CDG 0
```

Line 3 as nodes: assignment CALL -> [IDENTIFIER q, addition CALL -> [addition CALL ->
[LITERAL, IDENTIFIER name], LITERAL]]. Taint path inside the line (REACHING_DEF):
`name -> addition -> addition -> q`, then `q` flows on to `q` in the `execute` call. From
`name` on line 2 to `q` on line 5 that is at least 5 hops, and more from the real source
`request.args["name"]`.

Branch variant (`if safe: name = escape(name)` before the query): the identifier `name` on
line 5 receives REACHING_DEF edges from the raw `name` (line 2), the escaped `name` (line 4)
and the METHOD node. Both a sanitized and an unsanitized definition reach the query, so the
function stays vulnerable.

C example:

```c
void copy(char *src) {
    char buf[8];
    strcpy(buf, src);
}
```
Converter output: `Data(x=[25, 15], edge_index=[2, 69], edge_type=[69])`, edges per type
AST 22, CFG 13, REACHING_DEF 27, CALL 1, ARGUMENT 6, CDG 0. The buffer size appears only in
the text `buf[8]`.

## 7. Joern frontends (values for the `joern_frontend` field)

Joern 4.0.647, from `joern-parse --list-languages`:

| Language | `--language` value | Status |
|---|---|---|
| Python | `pythonsrc` | used on 3 samples |
| C | `c` | used; `newc` gave identical counts on the same file |
| C++ | no `cpp` entry; `c` and `newc` both parsed a `.cpp` sample with the same counts as the C sample (export confirmed to come from `vec.cpp`) | one tiny sample, no classes or templates. The `std::strcpy` stub has FULL_NAME `<unresolvedNamespace>.strcpy:<unresolvedSignature>(2)` against `strcpy` in C, so match sources and sinks on NAME, not FULL_NAME |
| Java | `javasrc` is the likely source-code frontend (`java` is probably bytecode) | NOT tested; stays disabled until D24 |

## 8. Open decisions

- Hops vs layers: Joern granularity makes source-to-sink paths several times longer than at
  statement level. The number of GNN rounds is a hyperparameter to tune in Week 2.
  Alternatives: merge sub-nodes per statement, or add shortcut edges. Very deep stacks may
  blur node vectors; measure before choosing.
- Stub methods: Rule A (current) keeps wrapper methods and external-function stubs. Rule B
  drops every METHOD without a line number (removes the `strcpy` stub and its CALL edge, and
  matches Python's behaviour for undefined functions). Decide with a training comparison.
- Hub edges: edges into METHOD_RETURN and out of METHOD may dilute signal. Test with and
  without them.
- A REACHING_DEF edge from METHOD into `name` (Python, line 5) is unexplained (guess: a
  definition at function entry).
- Cross-function data flow is untested: REACHING_DEF may not cross call boundaries, and the
  endpoints of the Python CALL edge were not inspected.
- Source/sink matching must cope with Joern rewrites (`db.cursor().execute(q)` became
  `tmp0 = db.cursor()` plus `tmp0.execute(q)`).
- ARGUMENT vs AST overlap: keep both or drop one.
- Filter rules were tested on five tiny files only; real dataset functions (macros, missing
  headers, incomplete snippets) may parse differently. P1's Joern spike measures this.
- Layers must accept edge types; plain GCNConv ignores `edge_type`, so a relation-aware layer
  is likely needed (check the PyG docs for the exact class and signature).

## 9. Reproduce

```
docker run --rm -v "${PWD}\<folder>:/workspace/sample" shield-joern bash -c "joern-parse sample/<file> --language <value> -o sample/cpg.bin && joern-export sample/cpg.bin --repr all --format graphml --out sample/export"
python scripts/graphml_to_pyg.py <folder>/export/export.xml
```
`joern-export` refuses to write into an existing output folder. Fixtures live in
`tests/fixtures/joern/`; generated exports are not committed.

## Changelog

- 0.1-draft: first version, Joern 4.0.647, Python samples.
- 0.1-draft (notes added, no rule change): C and C++ findings, frontend values, stub-method rules.
