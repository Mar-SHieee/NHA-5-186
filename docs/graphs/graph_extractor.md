# GraphExtractor and Graph Cache: Explained (W1-P1-03)

This document explains everything in `shield_core/extraction/`: what it is, why it exists,
how it works, and how each part appears in the code. It is written to be read from the
beginning by someone who has not seen the code.

---

## 1. The problem we are solving

SHIELD detects vulnerabilities in source code. One of its models (V3, the GNN) does not read
code as text. It reads code as a **graph**, and a GNN cannot read a `.py` file directly.
Something has to turn source code into a graph first.

**Why a graph?** Take this code:

```python
def get_user(name):
    q = "SELECT * FROM users WHERE name='" + name + "'"
    return db.execute(q)
```

As text, it is a sequence of tokens. A graph can show relationships text hides, such as
"the value of `name` flows into `q`, which flows into `db.execute`". That is exactly the
pattern of an SQL injection, and it is why the plan includes a GNN next to CodeBERT.

**The tool that builds the graph is Joern.** Joern reads source code and produces a
**Code Property Graph (CPG)**: one graph that merges several views of the code.

| Edge type | Meaning |
|---|---|
| AST | syntax tree: "this call contains these arguments" |
| CFG | control flow: "this statement runs after that one" |
| REACHING_DEF | data flow: "the value defined here is used there" |
| CALL | "this call site calls that function" |

Each **node** is a piece of code (a function, a call, a variable, a literal). Each **edge** is
a relationship between two pieces.

**What we built** is the layer between "source code string" and "graph the GNN code can use".
The task was W1-P1-03: a **GraphExtractor interface** plus a **cache key** (decision D5).

---

## 2. The design in one picture

Three layers, each in its own file:

```
your ML code (P2, P3, ...)
        |  only knows: GraphExtractor.extract(code, language) -> CodeGraph
        v
CachedGraphExtractor   (cache.py)            "have I done this before? if yes, load from disk"
        |  if not:
        v
JoernExtractor         (joern_extractor.py)  "run Joern, parse its output"
        |  both use the interface and data classes defined in:
        v
graph_extractor.py                           the interface + the plain data classes
```

**Why not call Joern directly everywhere?** Decision D2 says ML code must never depend on
Joern. If Joern turns out too slow or Java support is weak, you swap the implementation and
the GNN code does not change. This is called *programming against an interface*.

**Why a cache?** Joern takes about 8 seconds per file (measured). The datasets have tens of
thousands of functions, and the same graphs are re-read during every experiment. Without a
cache, every training run would repeat hours of Joern work. With it, the second call took
0.00 s.

---

## 3. File 1: `graph_extractor.py` (the contract)

This file contains **no Joern code**. It defines what a graph looks like and what an
extractor must do.

### 3.1 The data classes

```python
@dataclass(frozen=True)
class GraphNode:
    id: int
    type: str
    code: str = ""
    name: str = ""
    line: int | None = None
```

A `GraphNode` is one point in the graph:

- `id` is Joern's number for the node. It is unique inside one graph but **not** stable
  between runs.
- `type` is the Joern label, such as `METHOD`, `CALL` or `IDENTIFIER`.
- `code` is the source text of that node. Later, CodeBERT turns this text into the node's
  feature vector (decision D20).
- `name` is the function or variable name.
- `line` is the line number, or `None` for stub nodes that have no real position.

`@dataclass` makes Python write `__init__`, `__eq__` and a readable print for you.
`frozen=True` makes the object **immutable**: nobody can change a node after it is created,
which prevents a class of bugs.

```python
@dataclass(frozen=True)
class GraphEdge:
    src: int
    dst: int
    type: str  # AST, CFG, REACHING_DEF, CALL, ARGUMENT, CDG ...
```

An edge goes from the node with id `src` to the node with id `dst`.

```python
@dataclass
class CodeGraph:
    language: str
    extractor: str
    extractor_version: str
    schema_version: str
    nodes: list[GraphNode] = field(default_factory=list)
    edges: list[GraphEdge] = field(default_factory=list)
```

A `CodeGraph` is the whole result: the nodes and edges, plus **metadata about where it came
from**. The metadata records which extractor and version produced the graph, so you can
always tell later. `field(default_factory=list)` is needed because a plain `= []` default
would be shared between all instances, a classic Python trap.

The graph is **raw**. Filtering node types, one-hot encoding and so on belong to the PyG
converter (the later W2 task). That separation is why the node types we drop in
`graph_schema.md` do not affect the cache.

### 3.2 Saving and loading

```python
def to_dict(self):
    return {
        ...
        "nodes": [[n.id, n.type, n.code, n.name, n.line] for n in self.nodes],
        "edges": [[e.src, e.dst, e.type] for e in self.edges],
    }

@classmethod
def from_dict(cls, data):
    ...
    nodes=[GraphNode(*row) for row in data["nodes"]],
```

The cache needs to store a graph as JSON. Each node becomes a short list
`[id, type, code, name, line]` instead of a dictionary with five key names repeated per
node. A graph with thousands of nodes would otherwise waste a lot of space.
`GraphNode(*row)` unpacks the list back into the constructor arguments, so
`[5, "CALL", "f()", "f", 3]` becomes `GraphNode(5, "CALL", "f()", "f", 3)`.

### 3.3 Making the hash stable

```python
def normalize_code(code):
    return code.replace("\r\n", "\n").replace("\r", "\n")


def code_sha256(code):
    return hashlib.sha256(normalize_code(code).encode("utf-8")).hexdigest()
```

A **hash** (SHA-256) turns any text into a fixed-length fingerprint. The same text always
gives the same fingerprint, and a one-character change gives a completely different one. We
use it as the file's identity in the cache.

The catch: Windows saves line endings as `\r\n` and Linux as `\n`. The repo has Windows line
endings. Without normalizing, the same file would hash differently on two teammates'
machines and the cache would never be shared. So we convert to `\n` before hashing. The
Joern extractor then feeds Joern the **same normalized text**, so the cached graph always
matches its key. Line numbers do not change, since only the line-ending characters change.

### 3.4 The extension question

```python
def resolve_extension(language, extension=None):
    spec = registry.require_enabled(language)
    if extension is None:
        return spec.extensions[0]
    ...
```

This was added after we found a real bug (section 6). The short version: **the file
extension changes how Joern parses the file** (`.c` means C, `.cpp` means C++). This
function decides which extension to use. If you know the real one, pass it. If not (a pasted
snippet), it uses the first extension listed for that language in `shield_core/languages/<name>.yaml`.
It also checks that the extension belongs to the language, so `.py` for `cpp` raises an
error. It calls `registry.require_enabled`, so a disabled language such as Java is refused
automatically, which keeps the "no hard-coded languages" rule from the plan.

### 3.5 The interface itself

```python
class GraphExtractor(ABC):
    @property
    @abstractmethod
    def name(self): ...

    @property
    @abstractmethod
    def version(self): ...

    @abstractmethod
    def extract(self, code, language, extension=None) -> CodeGraph: ...
```

`ABC` plus `@abstractmethod` make this class a **contract**. You cannot create a
`GraphExtractor()` directly. Any class that inherits from it **must** provide `name`,
`version` and `extract`, or Python refuses to instantiate it. The schema version has a
default implementation that returns the module constant `GRAPH_SCHEMA_VERSION`.

`ExtractionError` is our own exception type. When Joern fails on a sample, callers can catch
**only that** and skip the sample, without hiding real bugs.

---

## 4. File 2: `cache.py`

### 4.1 The cache key

The plan (D5) says the key is `sha256(file) + joern_version + schema_version`. Ours also
includes the language and the extension. The reason for each part is to answer "when must I
NOT reuse an old graph?":

| Part | Reuse is wrong when... |
|---|---|
| sha256 of code | the code is different |
| extractor + version | a new Joern release might produce a different graph |
| schema version | we changed what a raw graph contains |
| language | a different frontend parses it |
| extension | `.c` and `.cpp` use different grammars |

```python
@dataclass(frozen=True)
class CacheKey:
    code_sha: str
    language: str
    extension: str
    extractor: str
    extractor_version: str
    schema_version: str
```

`for_code(...)` builds a key from the code and an extractor. `relative_path()` turns the key
into a file path:

```
data/cache/graphs/0.1-draft/joern-4.0.647/cpp/cpp/ab/ab12cd....json.gz
                   schema    extractor-ver  lang ext shard
```

Putting the versions in **folder names** makes invalidation automatic and visible. When
Joern is upgraded, a new folder is used and the old one can be deleted. The two-character
shard (`ab/`) avoids a single folder holding 100,000 files, which is slow on many file
systems. `_safe()` replaces any odd characters in a version string with `_`, so a path never
breaks.

### 4.2 Reading and writing

```python
def get(self, key):
    path = self.path_for(key)
    if not path.exists():
        return None
    try:
        with gzip.open(path, "rt", encoding="utf-8") as f:
            return CodeGraph.from_dict(json.load(f))
    except (OSError, EOFError, ValueError, KeyError, TypeError):
        path.unlink(missing_ok=True)
        return None
```

A cache hit unzips the file, parses the JSON and rebuilds the `CodeGraph`. If the file is
corrupted (for example an overnight job was killed mid-write), the `except` deletes it and
returns `None`. A damaged cache entry **acts like a miss**, so the graph is simply rebuilt,
never a crash.

```python
def put(self, key, graph):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as gz:
            gz.write(json.dumps(graph.to_dict(), separators=(",", ":")).encode("utf-8"))
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
```

The important line is `os.replace(tmp, path)`. It writes to a **temporary file first**,
then renames it to the real name in one atomic step. Another process reading the cache (you
may run extraction in parallel) either sees no file or the complete file, never a
half-written one. `mtime=0` makes the gzip output identical for identical content.
`separators=(",", ":")` removes spaces from the JSON to save space.

### 4.3 The counters

`GraphCache` has `hits` and `misses` and a `hit_rate` property (hits divided by total). Task
W2-P1-03 asks for "cache hit/miss metrics", so this is already there for it.

### 4.4 The wrapper

```python
class CachedGraphExtractor(GraphExtractor):
    def __init__(self, inner, cache=None):
        self.inner = inner
        self.cache = cache or GraphCache()

    def extract(self, code, language, extension=None):
        extension = resolve_extension(language, extension)
        key = CacheKey.for_code(code, language, self.inner, extension)
        graph = self.cache.get(key)
        if graph is not None:
            self.cache.hits += 1
            return graph
        self.cache.misses += 1
        graph = self.inner.extract(code, language, extension)
        self.cache.put(key, graph)
        return graph
```

This is the **decorator pattern**. `CachedGraphExtractor` *is* a `GraphExtractor` (it
inherits from it) and it also *contains* another one (`inner`). Callers cannot tell the
difference between the cached and uncached version. The steps are: compute the key, look it
up, return on a hit, and on a miss run the real extractor, save the result, then return it.
If `inner.extract` raises, the line after it never runs, so **failures are not cached**.

---

## 5. File 3: `joern_extractor.py` (the real work)

### 5.1 Running Joern

Joern is a command-line tool. By hand, as in the fixtures README, you run two commands:

```
joern-parse code.py --language pythonsrc -o cpg.bin                       # source -> binary CPG
joern-export cpg.bin --repr all --format graphml --out export             # binary -> XML file
```

`JoernExtractor.extract()` automates exactly that:

```python
with tempfile.TemporaryDirectory(prefix="shield_joern_") as tmp:
    work = Path(tmp)
    os.chmod(work, 0o777)
    (work / f"code{ext}").write_text(normalize_code(code), encoding="utf-8")
    self._run_joern(work, f"code{ext}", frontend)
    ...
```

1. It creates a temporary folder that is deleted automatically when the `with` block ends.
2. `chmod 0o777` makes it writable by anyone. The Docker image runs as a non-root user
   (`shield`), so without this the container could not write its output.
3. It writes the code into `code.py` or `code.cpp`, using the normalized text.
4. It runs Joern.
5. It reads `export/export.xml` and parses it.

The frontend name comes from the registry: `spec.joern_frontend.lower()` turns `PYTHONSRC`
into `pythonsrc` and `NEWC` into `newc`.

### 5.2 Local or Docker

```python
self.use_docker = docker_image is not None or shutil.which("joern-parse") is None
```

`shutil.which` checks whether `joern-parse` exists on your PATH. If it does, Joern runs
locally. If not, it uses Docker. In Docker mode:

```
docker run --rm -v <tempfolder>:/workspace/sample -w /workspace/sample shield-joern \
    bash -c "joern-parse ... && joern-export ..."
```

`-v` shares the temp folder with the container so Joern can read the code and write its
result back. `--rm` deletes the container afterwards. The two Joern commands are joined with
`&&` so the second only runs if the first succeeded.

### 5.3 Handling failure

`_exec` runs a command with `subprocess.run` and converts the three ways it can go wrong into
one `ExtractionError`: a timeout (default 300 s), a missing program (Docker not running), and
a non-zero exit code (the last 500 characters of Joern's error output are kept). Every
failure looks the same to callers, as the interface promises.

### 5.4 Reading Joern's output

Joern's output is **GraphML**, an XML format:

```xml
<key id="labelV" for="node" attr.name="labelV"/>
...
<node id="10"><data key="labelV">METHOD</data><data key="NAME">f</data>...</node>
<edge source="10" target="20"><data key="labelE">AST</data></edge>
```

`parse_graphml` reads it with Python's built-in `xml.etree`, so there is **no new
dependency**. The `<key>` entries map short ids to attribute names. For each `<node>` it
collects its `<data>` children into a dictionary and builds a `GraphNode`. The same happens
for edges. The `_GRAPHML = "{http://graphml.graphdrawing.org/xmlns}"` prefix is XML
namespace syntax, needed because the file declares a namespace.

At the end both lists are **sorted**:

```python
nodes.sort(key=lambda n: n.id)
edges.sort(key=lambda e: (e.src, e.dst, e.type))
```

Joern may emit elements in a different order each time, but sorting guarantees the same file
always gives the same graph. The schema doc requires this (the "row order" rule), because GNN
row numbers must be reproducible.

### 5.5 Testability: the `runner` argument

```python
runner: Callable[..., subprocess.CompletedProcess] = subprocess.run
```

The runner is passed in so tests can replace the real `subprocess.run` with a fake. That is
how the 13 tests run in well under a second with no Joern installed.

---

## 6. The C++ bug, and why `cpp.yaml` changed

The first run on `shapes.cpp` gave 22 kept nodes and an `UNKNOWN` node type, and the method
`f` was missing. The cause: every cpp-language sample was written to `code.c`, because `.c`
was the first extension in `cpp.yaml`. Joern's C/C++ frontend picks the grammar from the
extension, so it read C++ code (class, template) with the C parser and did not understand it.
The unreadable parts became `UNKNOWN` nodes.

The fix had three parts:

1. `extract()` takes an optional `extension`, so callers who know the real file name pass it.
2. The extension went into the cache key, since `.c` and `.cpp` now give different graphs for
   the same text.
3. In `cpp.yaml` the default became `.cpp`, by moving it to the front of the list. The C++
   parser accepts nearly all C, but C cannot read C++.

After the fix: 109 raw nodes, 51 kept, and `f`, `id` and `main` all appeared.

**Practical rule for dataset loaders:** when the file name is known (Big-Vul, MegaVul, repo
scans), pass its real extension. Use the default only for pasted snippets.

---

## 7. The tests (`tests/extraction/test_graph_cache.py`)

Each test protects one promise:

| Test | Promise |
|---|---|
| `key_ignores_line_endings` | CRLF and LF give the same key |
| `key_changes_with_each_part` | different code, language or version means a different key |
| `miss_then_hit` | the second call does not run the extractor (1 hit, 1 miss) |
| `version_bump_invalidates` | a new Joern version does not reuse old graphs |
| `corrupted_file_is_a_miss` | a damaged file is rebuilt, not a crash |
| `failures_are_not_cached` | an error leaves no file on disk |
| `parse_graphml` | the XML becomes the right nodes and edges, sorted |
| `joern_extractor_with_fake_runner` | the right commands run in the right order |
| `joern_failure_raises` | a Joern error becomes `ExtractionError` |
| `disabled_language_rejected` | Java (disabled) is refused |
| `default_extension_for_cpp_is_cpp` | `.cpp` is the default, wrong extensions are rejected |
| `c_and_cpp_files_get_different_keys` | `.c` and `.cpp` never share a cache entry |
| `joern_gets_the_right_file_name` | Joern receives `code.cpp` or `code.c` as requested |

They use a `FakeExtractor` that counts how many times it runs, so you can prove the cache
works by checking the count. Pytest's `tmp_path` gives each test a fresh empty folder.

---

## 8. `scripts/graphs/try_extractor.py`

This is not a test. It is the **real-world check**: it runs real Joern through the real cache
on a file you give it.

```powershell
python -m scripts.graphs.try_extractor tests/fixtures/joern/get_user.py python
```

Calling `extract` twice shows that call 1 takes about 8 s and call 2 takes 0.00 s. The
`kept after filtering: 48` line reuses the `NODE_TYPES` filter from `graphml_to_pyg.py` to
show the extractor reproduces the earlier manual results.

Measured results:

| Sample | Raw nodes | Kept | Notes |
|---|---|---|---|
| `get_user.py` | 96 | 48 | matches the fixture README |
| `a.c` / `a.cpp` | 66 | 25 | methods `f`, `strcpy` |
| `shapes.cpp` | 109 | 51 | `f`, `id`, `main` all found |

---

## 9. Documentation decisions

- **The version rule.** The graph cache stores **raw** graphs. Filtering (which node types to
  keep) happens later in the converter. So `GRAPH_SCHEMA_VERSION` should only change if the
  **raw extractor output** changes. Changes to kept node types or feature columns bump a
  separate converter version. Otherwise hours of cached Joern work would be thrown away for a
  filter change.
- **`TYPE_REF` was dropped.** It is rare, carries little signal, and adding it would change
  the feature vector size. Revisit after the W2 bulk extraction.
- **C++ templates** can produce several METHOD nodes for one source function (for example the
  implicit constructor `A` and a second `id`), the same effect the fixtures README explains.

---

## 10. What happens in one call

`ex.extract(code, "cpp")`, step by step:

1. `resolve_extension("cpp", None)` returns `.cpp`.
2. A key is built from the SHA-256 of the normalized code plus language, extension, Joern
   version and schema version.
3. The key becomes a path, and the cache looks there.
4. **Hit:** unzip, rebuild `CodeGraph`, return (0.00 s).
5. **Miss:** write the code to a temp `code.cpp`, run `joern-parse`, run `joern-export`, parse
   `export.xml` into nodes and edges, build a `CodeGraph`, save it atomically, return (about
   8 s).

---

## 11. Known follow-ups

- Update the comment above `GRAPH_SCHEMA_VERSION` in `graph_extractor.py` to match the
  versioning rule in section 9:

  ```python
  # Bump ONLY when the raw extractor output changes (different Joern flags, different
  # attributes stored per node/edge). It is part of the cache key (D5), so a bump invalidates
  # every cached graph. Changes to which node/edge types are KEPT belong to the converter
  # version instead (see docs/graphs/graph_schema.md, "Versions").
  ```

- Add `CONVERTER_VERSION` to `scripts/graphs/graphml_to_pyg.py` when building W2-P2-01, and put it in
  the processed-dataset cache path.
- Hit/miss counters live on the cache and are updated by `CachedGraphExtractor`; if several
  worker processes extract in parallel (W2-P1-02), each has its own counters, so aggregate
  them at the end.
- Joern is pinned in two places (`DEFAULT_JOERN_VERSION` and the Dockerfile). Keep them equal,
  or the cache key will describe a different Joern than the one that ran.
