# SHIELD — C/C++ CWE Selection and Analysis Rationale

**Decision status:** Provisional C/C++ CWE scope, pending Gate G1 dataset and detection validation
**Selected classes:** 20 CWEs (provisional)
**Proposed eligibility baseline:** At least **100 vulnerable samples per CWE** for initial experiments
**Preferred support:** 300+ vulnerable samples per CWE when available
**Sources:** `dataset_audit.md`, `taint_spike.md`, `joern_spike.md`, `graph_schema.md`, and the supplied `cpp.yaml`.

> **Updated decision:** Retain the existing 15 CWEs and add **CWE-369 (Divide by Zero), CWE-617 (Reachable Assertion), CWE-772 (Missing Release of Resource), CWE-122 (Heap-based Buffer Overflow), and CWE-674 (Uncontrolled Recursion)** as provisional candidates. The 100-sample threshold is an experimental screening rule, not proof of model readiness. The `system()` taint rule for CWE-78 remains auxiliary because CWE-78 is not among the 20 selected classes.

## 1. Security scope and rationale

| Security family                    | CWEs                                                          | Why it matters                                                                                                                                                     |
| ---------------------------------- | ------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Memory bounds and unsafe copying   | CWE-119, CWE-120, CWE-125, CWE-787, CWE-122                   | Can cause crashes, data disclosure, memory corruption, and sometimes code execution.                                                                               |
| Memory lifetime and pointer safety | CWE-415, CWE-416, CWE-476                                     | Double free, use-after-free, and null dereference can compromise integrity or availability.                                                                        |
| Numeric and input validation       | CWE-190, CWE-20, CWE-369                                      | Overflow and unchecked input can invalidate bounds, allocation, and trust assumptions.                                                                             |
| Path and information security      | CWE-22, CWE-200                                               | Path traversal and unintended information exposure can cross security boundaries.                                                                                  |
| Concurrency and resource safety    | CWE-362, CWE-400, CWE-401, CWE-835, CWE-772, CWE-674, CWE-617 | Races, resource exhaustion, unreleased resources, uncontrolled recursion, reachable assertions, and infinite loops can cause denial of service and other failures. |

**Security priority is not identical to sample count.** MITRE's Top 25 is a useful security-priority reference, but rankings depend on the edition/year and do not imply that a CWE is detectable by SHIELD. See https://cwe.mitre.org/top25/.

## 2. Dataset support — vulnerable sample counts

The first 15 rows below reproduce the **earlier MegaVul + Big-Vul-only audit** (deduplicated, `label=1`, `cpp` language bucket). The five newly added rows are from the **later combined C/C++ commit-concentration audit** covering MegaVul, Big-Vul and CVEfixes C++; they are **not directly comparable to the two-source columns**. All figures are vulnerable sample occurrences, not independent CVEs.

| CWE     | MegaVul (older audit) | Big-Vul (older audit) |                   Reported count | Meets baseline ≥100? |
| ------- | --------------------: | --------------------: | -------------------------------: | :------------------: |
| CWE-119 |                 1,589 |                 1,064 |                        **2,653** |         Yes          |
| CWE-120 |                   424 |                     5 |                          **429** |         Yes          |
| CWE-125 |                 1,443 |                   263 |                        **1,706** |         Yes          |
| CWE-190 |                   708 |                   135 |                          **843** |         Yes          |
| CWE-20  |                 1,070 |                   617 |                        **1,687** |         Yes          |
| CWE-200 |                   560 |                   233 |                          **793** |         Yes          |
| CWE-22  |                   155 |                    25 |                          **180** |         Yes          |
| CWE-362 |                   509 |                   142 |                          **651** |         Yes          |
| CWE-400 |                   313 |                     9 |                          **322** |         Yes          |
| CWE-415 |                   184 |                    42 |                          **226** |         Yes          |
| CWE-416 |                 1,004 |                   178 |                        **1,182** |         Yes          |
| CWE-476 |                 1,286 |                    57 |                        **1,343** |         Yes          |
| CWE-787 |                 1,509 |                   101 |                        **1,610** |         Yes          |
| CWE-401 |                   280 |            Not listed |                         **≥280** |         Yes          |
| CWE-835 |                   251 |                    19 |                          **270** |         Yes          |
| CWE-369 |                     — |                     — | **193** (new three-source audit) |         Yes          |
| CWE-617 |                     — |                     — | **327** (new three-source audit) |         Yes          |
| CWE-772 |                     — |                     — | **228** (new three-source audit) |         Yes          |
| CWE-122 |                     — |                     — | **158** (new three-source audit) |         Yes          |
| CWE-674 |                     — |                     — | **142** (new three-source audit) |         Yes          |

**Interpretation:** The original 15 exceed the proposed 100-vulnerable-sample threshold **in MegaVul alone**, and the five additions exceed it in the newer combined audit. For CWE-401, the audit contains 280 vulnerable samples in MegaVul but no separate Big-Vul `cpp` row; the combined figure is therefore conservatively shown as **at least 280**, not an exact total. These are sample counts, not proof of independent vulnerabilities. The audit's acceptance status is preliminary and manual label review remains outstanding.

**Label taxonomy warning:** CWE-119 is a broad memory-bounds category, whereas CWE-120, CWE-125, CWE-787, and the newly added CWE-122 are more specific. Review parent/child label overlaps before single-label training; consider a hierarchical or multi-label strategy where justified.

## 3. Taint analysis: what it means

**Taint analysis** tracks data that originates from a potentially untrusted **source**, propagates through program variables and calls, and reaches a security-sensitive **sink**.

```text
Untrusted source → assignments / expressions / function calls → sensitive sink
                             ↘ checks or transformations
```

- **Source:** Untrusted input, e.g. `getenv()`, `argv`, a buffer written by `fgets()`, `read()`, `recv()`, or `scanf()`.
- **Propagation:** How values flow through assignments, arguments, returns, and other data dependencies.
- **Sink:** A sensitive operation, e.g. `system()`, `fopen()`, or a dangerous length passed to `memcpy()`.
- **Validation / sanitizer-like operation:** A context-specific check or transformation that may constrain the value. A named sanitizer is **not** automatically proof of safety.

**Example — command execution:**

```c
char *cmd = getenv("USER_COMMAND");  // potentially untrusted source
system(cmd);                          // sensitive sink
```

A source-to-sink path is a **potentially dangerous flow**, not a confirmed exploit or vulnerability. Whether the source is attacker-controlled, whether a sufficient guard exists, and how the sink is used all matter.

**Example — CWE-22 Path Traversal:**

```c
char *path = getenv("FILE_PATH");
FILE *file = fopen(path, "r");
```

Taint tracking can connect an untrusted path to `fopen()`. However, confirming CWE-22 also requires checking whether the program restricts access to authorized directories. `realpath()` only canonicalizes paths; it does **not** enforce directory confinement.

### What taint does not prove

- **CWE-415 / CWE-416:** Need allocation, free, lifetime, and alias analysis.
- **CWE-476:** Needs nullness and feasible-path reasoning.
- **CWE-190:** Needs arithmetic semantics and numeric-range analysis.
- **CWE-362:** Needs concurrency and synchronization analysis.
- **CWE-401:** Needs ownership and resource-lifetime reasoning.
- **CWE-835 / CWE-674:** Need loop termination or recursion-depth reasoning; a loop or recursive call is not proof of nontermination.
- **CWE-369:** Needs feasible numeric-path and zero-divisor reasoning.
- **CWE-617:** Needs reachability and assertion-failure conditions.
- **CWE-772:** Needs resource ownership and release-path reasoning.
- **CWE-122:** Needs heap allocation sizes, buffer bounds, and write-path reasoning.

## 4. Joern: what it does and why SHIELD uses it

**Joern** is a static code-analysis framework that builds a **Code Property Graph (CPG)** without executing the target program. The CPG exposes multiple kinds of relationships useful for vulnerability analysis.

| Representation                   | Meaning                                              | Potential value                                                       |
| -------------------------------- | ---------------------------------------------------- | --------------------------------------------------------------------- |
| AST — Abstract Syntax Tree       | Syntax and structure of code                         | Identifies calls, operators, expressions, and declarations.           |
| CFG — Control Flow Graph         | Possible execution transitions                       | Shows branches, guards, loops, and execution paths.                   |
| Data flow / reaching definitions | Connections between value definitions and uses       | Supports taint propagation and data-dependency features.              |
| Call relationships               | Which functions call which others                    | Potential interprocedural context, subject to resolution limitations. |
| CDG — Control Dependence Graph   | Which conditions control the execution of operations | Supports validation and guard analysis.                               |

**Joern is not an automatic detector for every CWE.** A CPG can provide useful features even when no source-to-sink taint path exists. The GNN can learn from those graph features, but it cannot reliably recover missing facts such as pointer aliases, allocation sizes, thread synchronization, or precise numeric ranges merely because a graph exists.

```text
C / C++ code
    │
    ▼
Joern → Code Property Graph (CPG)
    ├── AST / CFG / data-flow / CDG / call features ─┐
    └── source → sink taint-path features ───────────┤
                                                     ▼
                                             Graph representation
                                                     │
                                                     ▼
                                              GNN prediction
```

## 5. Compatibility of the 20 CWEs

**Interpretation of ratings:** “Joern useful” means graph information could support analysis or ML features, **not** that detection was validated. “Partial taint” means source-to-sink tracking may contribute evidence but is insufficient on its own.

| CWE         | Weakness                                                 | Taint analysis             | Joern / CPG contribution                                                         | Decision                             |
| ----------- | -------------------------------------------------------- | -------------------------- | -------------------------------------------------------------------------------- | ------------------------------------ |
| CWE-119     | General memory-bounds weakness                           | Partial                    | Memory operations and control/data-flow context; bounds reasoning still required | Keep provisionally; review hierarchy |
| CWE-120     | Buffer Copy without Checking Size                        | Partial                    | Copy calls, length arguments, and possible guards; destination size needed       | Keep                                 |
| CWE-125     | Out-of-bounds Read                                       | Limited                    | Index expressions, bounds checks, and paths; precise bounds needed               | Keep                                 |
| CWE-190     | Integer Overflow                                         | Limited                    | Arithmetic operations and dependencies; range analysis needed                    | Keep                                 |
| CWE-20      | Improper Input Validation                                | Partial                    | Input flows, validation checks, and control dependence                           | Keep                                 |
| CWE-200     | Exposure of Sensitive Information                        | Partial                    | Potential sensitive-source-to-output flows and data dependencies                 | Keep                                 |
| **CWE-22**  | **Path Traversal**                                       | **Strong candidate**       | **Untrusted path → file operation; must verify confinement**                     | **Keep; taint priority**             |
| CWE-362     | Race Condition                                           | Not conventional taint     | Limited; thread/synchronization semantics not established                        | Experimental                         |
| CWE-400     | Uncontrolled Resource Consumption                        | Limited                    | Loops, allocations, and resource-related control flow                            | Keep; evaluate separately            |
| CWE-415     | Double Free                                              | Not conventional taint     | Allocation/free events and possible paths; lifetime/alias model needed           | Keep                                 |
| CWE-416     | Use After Free                                           | Not conventional taint     | Free/use relationships; lifetime/alias model needed                              | Keep                                 |
| CWE-476     | NULL Pointer Dereference                                 | Not conventional taint     | Dereference operations and null guards; nullness reasoning needed                | Keep                                 |
| CWE-787     | Out-of-bounds Write                                      | Partial                    | Writes, lengths, and guards; buffer bounds needed                                | Keep                                 |
| **CWE-401** | **Memory Leak**                                          | **Not conventional taint** | **Allocation/release paths; ownership/lifetime reasoning needed**                | **Add; experimental**                |
| **CWE-835** | **Infinite Loop**                                        | **Not conventional taint** | **Loop structure and exit conditions; termination proof not supplied**           | **Keep; experimental**               |
| **CWE-369** | **Divide by Zero**                                       | Not conventional taint     | Divisor expressions and branch guards; path feasibility needed                   | Add; provisional                     |
| **CWE-617** | **Reachable Assertion**                                  | Not conventional taint     | Assertion calls, guards, CFG reachability; failing condition needed              | Add; provisional                     |
| **CWE-772** | **Missing Release of Resource after Effective Lifetime** | Not conventional taint     | Acquire/release events and exit paths; ownership needed                          | Add; experimental                    |
| **CWE-122** | **Heap-based Buffer Overflow**                           | Partial                    | Heap allocations, writes, indices and lengths; heap bounds needed                | Add; provisional; review hierarchy   |
| **CWE-674** | **Uncontrolled Recursion**                               | Not conventional taint     | Recursive call graph and guards; recursion-depth reasoning needed                | Add; experimental                    |

**Most relevant to current taint work:** CWE-22; partially CWE-20, CWE-200, CWE-120, and CWE-787. The others may still be worthwhile **CPG/GNN targets**, but need additional semantics and targeted experiments.

## 6. Evidence and limitations from SHIELD's taint spike

The supplied `taint_spike.md` (Part B, C/C++ fixtures) supports the following **observed**, rather than assumed, behavior:

- C source definitions were tested using `getenv`, `fgets` output argument, `read`/`recv` output argument, `scanf` output argument, and `argv`.
- Active sinks with observed flows: `system(1)`, `fopen(1)`, `strcpy(2)`, `memcpy(3)`.
- **Pointer aliasing** and **`strncpy` / `strncat`** caused missed taint flows in the fixtures.
- Default **C++ cross-function call resolution** did not support the tested interprocedural flows reliably.
- An unresolved call can pass taint through; seeing a sanitizer-like call does not establish that all dangerous paths are blocked.
- `realpath()` is not a complete path-traversal sanitizer; `atoi()` is not a sanitizer for an unsafe `memcpy` length.
- CWE-416, CWE-476, and CWE-190 were **not tested as taint-detection tasks** in this spike.
- Small fixtures do **not** establish real-world per-CWE precision or recall.

**Engineering conclusion:** Treat the current Joern taint implementation as a **feature generator** with known false-positive and false-negative risks, not a comprehensive vulnerability detector.

## 7. C/C++ registry configuration (current active settings)

The following is the updated provisional 20-CWE list with the user's existing **active** taint definitions preserved. It does not add unverified sources or sinks.

```yaml
name: cpp
enabled: true
# .cpp is the default for snippets without a known filename.
extensions: [".cpp", ".c", ".h", ".cc", ".cxx", ".hpp"]
joern_frontend: NEWC
tree_sitter:
  default: tree_sitter_cpp
  by_extension:
    ".c": tree_sitter_c
cwes:
  [
    "CWE-119",
    "CWE-120",
    "CWE-125",
    "CWE-190",
    "CWE-20",
    "CWE-200",
    "CWE-22",
    "CWE-362",
    "CWE-400",
    "CWE-415",
    "CWE-416",
    "CWE-476",
    "CWE-787",
    "CWE-401",
    "CWE-835",
    "CWE-369",
    "CWE-617",
    "CWE-772",
    "CWE-122",
    "CWE-674",
  ]
# Only patterns with observed flows are active.
sources:
  - { kind: call, name: getenv }
  - { kind: argument, name: fgets, arg: 1 }
  - { kind: argument, name: "read|recv", arg: 2 }
  - { kind: argument, name: scanf, arg: 2 }
  - { kind: parameter, name: argv }
sinks:
  - { name: system, arg: 1, cwe: CWE-78 } # Auxiliary rule; CWE-78 is NOT in the 20 classes.
  - { name: fopen, arg: 1, cwe: CWE-22 }
  - { name: strcpy, arg: 2, cwe: CWE-120 }
  - { name: memcpy, arg: 3, cwe: CWE-787 }
sanitizers:
  - "realpath" # Canonicalization alone does not enforce confinement.
  - "shell_escape" # Fixture helper; not proof of safe shell execution.
# Observed indices but unverified flows remain inactive:
# gets(1), popen(1), strcat(2), sprintf(arg_from=3)
# atoi is NOT a sanitizer. strncpy/strncat may lose taint in the current model.
```

### Registry interpretation

- **Source kinds:** `call` returns tainted data; `argument` marks a buffer written by a function; `parameter` marks a potentially tainted parameter.
- **Sink argument indices:** Joern indexes arguments starting at 1 in these examples. `memcpy` argument 3 is the **length**. `strcpy` argument 2 is the **source string**.
- **CWE-78 mismatch is intentional and documented:** The `system()` sink is useful for taint feature extraction, but CWE-78 is not currently a selected ML class. Decide separately whether auxiliary findings are exposed in product output.
- **Parser settings are not detection guarantees:** `NEWC` and Tree-sitter configure parsing; they do not validate any CWE classifier.
- **Do not add inactive patterns** (`gets`, `popen`, `strcat`, `sprintf`) until a fixture confirms the required flow.

## 8. Dataset and evaluation policy

| Item                          | Decision                                                                         | Why                                                          |
| ----------------------------- | -------------------------------------------------------------------------------- | ------------------------------------------------------------ |
| Candidate scope               | **20 C/C++ CWEs**                                                                | Broad, security-relevant coverage                            |
| Initial eligibility threshold | **≥100 vulnerable samples per CWE**                                              | Allows controlled early experiments                          |
| Preferred target              | **≥300 vulnerable samples per CWE**                                              | Better support for per-class testing, though not a guarantee |
| Experimental cases            | CWE-362, CWE-401, CWE-835, CWE-772, CWE-674; potentially other difficult classes | Detection needs semantics beyond the current taint spike     |
| Taint claims                  | Only observed source-to-sink behavior                                            | Prevents overstating detector coverage                       |
| CPG claims                    | Graph feature availability, not proven vulnerability detection                   | Joern parsing ≠ CWE detection                                |
| Label strategy                | Audit CWE-119 hierarchy and multi-label overlaps                                 | Avoid contradictory class definitions                        |
| Splitting                     | Group by project/CVE where possible; verify overlap                              | Reduce train/test leakage                                    |
| Metrics                       | Per-CWE precision, recall, F1, support, confusion analysis                       | Exposes weak classes hidden by aggregate metrics             |

### Next steps before final acceptance

1. Recompute **all 20** CWE counts using the same final three-source deduplicated dataset; the current table mixes an older two-source audit with a newer three-source audit. Distinguish C from C++ if language-specific claims are required.
2. Complete manual label-noise review and confirm the official D22/G1 acceptance rules.
3. Decide how to map parent/child CWE labels, especially CWE-119 versus CWE-120/125/787.
4. Build targeted graph-feature fixtures for allocation/free lifetime, null guards, integer bounds, **zero divisors, reachable assertions, resource release, heap buffer bounds, recursion**, loops, and concurrency; do not treat taint results as substitutes.
5. Evaluate each CWE independently and demote unsupported classes if data or detection quality is inadequate.
6. Keep auxiliary rule-based findings (such as CWE-78 via `system`) separate from the 20-class GNN output unless explicitly integrated and evaluated.
7. Use group-aware splits and audit project/commit/CVE leakage before reporting final metrics; see `docs/datasets/audits/cpp_cwe_commit_audit.csv` and `docs/datasets/leakage/c_cpp_cwe_data_leakage_high_risk.md`.

## 9. Final decision

**Accept all 20 as the provisional C/C++ CWE candidate list.** Use **100 vulnerable samples** as an early eligibility threshold, **300+** as a preferred support target, and require separate evidence for dataset quality, Joern feature extraction, taint-flow behavior, and real detection performance. Retain **CWE-401**, **CWE-835**, **CWE-772**, and **CWE-674** as experimental candidates; keep **CWE-362** under special scrutiny because the current pipeline does not establish concurrency-aware analysis.

---

### Evidence references

- `dataset_audit.md` — dataset frequency tables, deduplication, preliminary acceptance caveats.
- `cpp_cwe_commit_audit.csv` — later three-source C/C++ CWE sample and independent commit-group audit; supports the five new sample counts.
- `c_cpp_cwe_data_leakage_high_risk.md` — group concentration and leakage-risk handoff.
- `taint_spike.md` — C/C++ source/sink fixture observations and known limitations.
- `joern_spike.md` — Joern parsing and data-dependency spike.
- `graph_schema.md` — intended CPG-to-PyG graph representation.
- User-supplied `cpp.yaml` — active language configuration and taint rules.
- MITRE CWE Top 25 — https://cwe.mitre.org/top25/

---

# SHIELD — Python CWE Selection and Analysis Rationale

**Decision status:** Provisional Python CWE scope, pending post-deduplication label/provenance review and Gate G1 detection validation
**Registry scope:** 14 CWEs (retain all existing entries in `python.yaml`)
**Core ML candidates:** 12 CWEs with reported support of at least **100 vulnerable samples**
**Experimental ML candidates:** CWE-502 and CWE-78 (reported 86 and 64 vulnerable samples)
**Preferred support:** 300+ independent, high-quality vulnerable samples per CWE where feasible
**Evidence basis:** The Python registry YAML provided in the conversation; reported post-dedupe acceptance-audit counts. The detailed Python Joern fixture results and per-CVE distributions were not provided for independent verification here.

> **Decision:** Preserve all **14** Python CWEs in the language registry. Treat **12** as initial ML candidates and **2** as experimental candidates, rather than deleting security-relevant taint rules because their current training sample counts are smaller. `CWE-95` appears in the active `eval` sink but is **not** one of the 14 selected registry classes; it remains an auxiliary finding unless explicitly added and validated.

## 1. Security scope and rationale

| Security family                         | CWEs                                      | Why it matters                                                                                          |
| --------------------------------------- | ----------------------------------------- | ------------------------------------------------------------------------------------------------------- |
| Web injection and request handling      | CWE-79, CWE-89, CWE-918, CWE-352, CWE-444 | Cross-site scripting, SQL injection, SSRF, CSRF, and HTTP request smuggling can cross trust boundaries. |
| Paths and redirects                     | CWE-22, CWE-601                           | Untrusted paths or redirect targets may enable unauthorized access or phishing.                         |
| Code execution and deserialization      | CWE-94, CWE-502, CWE-78                   | Dynamic code evaluation, unsafe deserialization, and OS command injection can enable code execution.    |
| Session and input controls              | CWE-613, CWE-20                           | Insufficient session expiration and improper input validation weaken security assumptions.              |
| Resource and confidentiality protection | CWE-400, CWE-200                          | Resource exhaustion and unintended information exposure can affect availability and confidentiality.    |

**Important:** Sample frequency measures dataset representation, not severity, exploitability, or proven detectability. MITRE's [CWE Top 25](https://cwe.mitre.org/top25/) can inform security priority, but must not be substituted for validation of SHIELD's detectors.

## 2. Dataset support — vulnerable sample counts

The following are the **reported post-deduplication combined Python counts** discussed for the SHIELD audit, not independently reproduced from the underlying Parquet files in this document. They are CWE occurrences among `label = 1` samples; a multi-label sample may contribute to several rows. These counts **do not** establish independent CVEs, repositories, or commits.

| CWE     | Reported vulnerable samples | Initial threshold ≥100? | ML scope                            |
| ------- | --------------------------: | :---------------------: | ----------------------------------- |
| CWE-918 |                         319 |           Yes           | Core                                |
| CWE-79  |                         283 |           Yes           | Core                                |
| CWE-601 |                         249 |           Yes           | Core                                |
| CWE-22  |                         242 |           Yes           | Core                                |
| CWE-444 |                         215 |           Yes           | Core; investigate CVE concentration |
| CWE-613 |                         198 |           Yes           | Core                                |
| CWE-352 |                         193 |           Yes           | Core                                |
| CWE-94  |                         185 |           Yes           | Core                                |
| CWE-400 |                         156 |           Yes           | Core                                |
| CWE-20  |                         150 |           Yes           | Core                                |
| CWE-200 |                         126 |           Yes           | Core                                |
| CWE-89  |                         100 |    Yes (borderline)     | Core; review after split            |
| CWE-502 |                          86 |           No            | Experimental                        |
| CWE-78  |                          64 |           No            | Experimental                        |

**Interpretation:** The 100-sample threshold is an **initial screening convention**, not evidence of model readiness. `CWE-89` sits exactly on the threshold and may fall below it after leakage-safe grouping, provenance filtering, or further label review. The dataset-level contribution of CVEfixes Python versus Zenodo Python must be re-extracted from the current audit if needed; it is not asserted here.

**Independence warning:** The Zenodo Python dataset has multiple rows per commit and CVE; the previously reported 2,255 SHA-bearing rows corresponded to 421 distinct SHAs **before** deduplication. Avoid interpreting hundreds of rows for a CWE as hundreds of independently discovered vulnerabilities.

## 3. Taint analysis: what it means for Python

**Taint analysis** attempts to trace untrusted values from an input **source** through expressions and calls to a sensitive **sink**. A path can be a useful security signal, but does not by itself prove a vulnerability.

```text
HTTP request / input() / sys.argv  →  data flow and transformations  →  sensitive operation
                                               ↓
                                     context-specific guards
```

- **Sources in the supplied Python YAML:** `request.args[...]`, `request.args.get(...)`, `request.form[...]`, `request.get_json(...)`, `input(...)`, and `sys.argv[...]`.
- **Sinks in the supplied YAML:** `execute` (CWE-89), `os.system` / `subprocess.run` (CWE-78), `open` (CWE-22), `pickle.loads` (CWE-502), and `eval` (CWE-95).
- **Sanitizer-like call names in the supplied YAML:** `int`, `escape`. These are **not** blanket proofs of safety; their effects depend on context and the executed path.

**Illustrative example — command injection candidate (CWE-78):**

```python
import os
from flask import request

command = request.args.get("cmd")
os.system(command)  # Potentially unsafe source-to-sink flow
```

This example illustrates the intended data-flow signal; actual vulnerability determination depends on reachability, attacker control, command construction, and effective validation.

**Illustrative example — path traversal candidate (CWE-22):**

```python
from flask import request

filename = request.args.get("file")
with open(filename, "rb") as f:
    content = f.read()
```

A tainted path reaching `open()` merits review; the application may still enforce safe path confinement elsewhere. Conversely, a source-to-sink pattern can miss a real vulnerability when input propagation or keyword arguments are not modeled.

### What taint does not establish on its own

- **CWE-79:** Whether output is encoded safely in the correct HTML/JS context.
- **CWE-918:** Whether URL destinations are actually attacker-controlled and network policies restrict access.
- **CWE-601:** Whether redirect targets are constrained to approved destinations.
- **CWE-444:** HTTP parser/proxy disagreement and request-boundary semantics.
- **CWE-613:** Session expiration, invalidation, and authentication state over time.
- **CWE-352:** Whether CSRF tokens, SameSite cookies, and origin checks protect state-changing requests.
- **CWE-94 / CWE-502:** Dangerous execution/deserialization behavior, reachability, and runtime constraints.
- **CWE-400:** Resource bounds and workload-dependent exhaustion.
- **CWE-200:** Whether exposed values are sensitive and accessible to unauthorized users.

## 4. Joern: what it does and why SHIELD uses it

Joern's `PYTHONSRC` frontend constructs a **Code Property Graph (CPG)** from Python source without executing the target program. The graph can provide syntax, control-flow, and data-dependency features for a GNN, and it may support source-to-sink analysis when the relevant calls and flows are resolved.

| Representation      | Potential use                                        | Limitation                                                        |
| ------------------- | ---------------------------------------------------- | ----------------------------------------------------------------- |
| AST                 | Calls, literals, expressions, access patterns        | Syntax alone does not establish exploitability.                   |
| CFG                 | Branches, guards, and possible paths                 | Framework behavior and runtime dispatch may be missing.           |
| Data-flow relations | Track value propagation to sinks                     | Dynamic attributes, imports, and aliases may be unresolved.       |
| Call relationships  | Connect input handling to downstream functions       | Dynamic dispatch and external library code complicate resolution. |
| CDG                 | Identify conditions controlling sensitive operations | Presence of a guard does not mean the guard is sufficient.        |

```text
Python code
    │
    ▼
Joern (PYTHONSRC) → CPG
    ├── AST / CFG / data-flow / call / guard features ─┐
    └── source → sink taint-path features ──────────────┤
                                                        ▼
                                                 Graph features
                                                        │
                                                        ▼
                                                 GNN prediction
```

**Engineering boundary:** Parsing success, graph construction, and a detected taint path are **not** validated per-CWE precision/recall. The GNN must be evaluated independently.

## 5. Compatibility of the 14 Python CWEs

“Candidate” means the technique may supply useful evidence, **not** that SHIELD has validated detection of that weakness.

| CWE     | Weakness                          | Taint relevance  | Joern / CPG contribution                                                        | Decision                    |
| ------- | --------------------------------- | ---------------- | ------------------------------------------------------------------------------- | --------------------------- |
| CWE-79  | Cross-site Scripting              | Partial          | Input-to-output paths; encoding context not established                         | Core                        |
| CWE-918 | Server-Side Request Forgery       | Strong candidate | User-controlled URL to HTTP client; destination policy still needed             | Core                        |
| CWE-22  | Path Traversal                    | Strong candidate | User-controlled path to file operation; confinement still needed                | Core; active sink           |
| CWE-601 | Open Redirect                     | Strong candidate | Redirect target data flow; allowlist logic still needed                         | Core                        |
| CWE-444 | HTTP Request Smuggling            | Limited          | Request-handling structure; proxy/parser differential outside ordinary CPG      | Core; high-risk feasibility |
| CWE-613 | Insufficient Session Expiration   | Limited          | Session API usage; lifecycle and temporal behavior not established              | Core; high-risk feasibility |
| CWE-94  | Code Injection                    | Partial          | Dynamic execution APIs and argument provenance                                  | Core                        |
| CWE-502 | Deserialization of Untrusted Data | Strong candidate | `pickle.loads` input path; trust and runtime behavior matter                    | Experimental; active sink   |
| CWE-89  | SQL Injection                     | Strong candidate | Input to SQL execution; parameterization and query construction matter          | Core; active sink           |
| CWE-78  | OS Command Injection              | Strong candidate | Input to command execution; shell and argument semantics matter                 | Experimental; active sinks  |
| CWE-20  | Improper Input Validation         | Partial          | Guard and input-flow context; requires policy-specific validation               | Core                        |
| CWE-400 | Uncontrolled Resource Consumption | Limited          | Loops, allocation, recursion, and input-size dependence                         | Core; targeted features     |
| CWE-200 | Exposure of Sensitive Information | Partial          | Sensitive values reaching responses/logs; sensitivity not encoded automatically | Core                        |
| CWE-352 | Cross-Site Request Forgery        | Limited          | State-changing routes and validation checks; framework/cookie semantics needed  | Core; targeted features     |

**CWE-95 note:** The active `eval` sink refers to CWE-95 (Eval Injection), which is **outside the selected 14-CWE registry list**. This is an auxiliary taint finding, not automatically an ML prediction class. Decide whether the product surfaces it independently.

## 6. Evidence and limitations from the Python taint configuration

The following are **configuration facts**, not claims that a real-world detector has been validated:

- The supplied `python.yaml` specifies `PYTHONSRC`, Tree-sitter Python, six source patterns, six sink entries, and two sanitizer-like names.
- Joern patterns are regular expressions; the configuration warns that they must match the whole call text, and that keyword arguments at index `-1` are not covered by the specified sink argument indices.
- `os.system`, `subprocess.run`, `pickle.loads`, `open`, and `eval` are listed as sensitive operations, but a rule's presence is not evidence that every source-to-sink flow is recovered.
- The `eval` sink uses CWE-95 while the registry's selected CWE list contains CWE-94 but not CWE-95. **Do not silently conflate these IDs.**
- The provided configuration comments state that an unresolved call may propagate taint; a path containing `int` or `escape` must not be treated as definitively sanitized.
- No verified Python per-CWE fixture pass rates, false-positive rates, or recall measurements are asserted in this document.

**Engineering conclusion:** Treat Python taint paths as candidate evidence/features, not as a comprehensive vulnerability oracle.

## 7. Python registry configuration (current active settings)

The following preserves the supplied **14-CWE registry scope** and active taint rules. No new unverified source/sink patterns are added.

```yaml
name: python
enabled: true
extensions: [".py"]
joern_frontend: PYTHONSRC
tree_sitter:
  default: tree_sitter_python
cwes:
  [
    "CWE-79",
    "CWE-918",
    "CWE-22",
    "CWE-601",
    "CWE-444",
    "CWE-613",
    "CWE-94",
    "CWE-502",
    "CWE-89",
    "CWE-78",
    "CWE-20",
    "CWE-400",
    "CWE-200",
    "CWE-352",
  ]

# Taint configuration (W1-P2-03). Evidence: docs/taint/taint_spike.md.
# Joern regex patterns match the WHOLE text; use trailing .* for prefix matches.
sources:
  - { kind: call, code: 'request\.args\[.*' }
  - { kind: call, code: 'request\.args\.get\(.*' }
  - { kind: call, code: 'request\.form\[.*' }
  - { kind: call, code: 'request\.get_json\(.*' }
  - { kind: call, code: 'input\(.*' }
  - { kind: call, code: 'sys\.argv\[.*' }

# arg is Joern argument index of the dangerous value.
# Keyword arguments (index -1) are not covered by these sink definitions.
sinks:
  - { name: execute, arg: 1, cwe: CWE-89 }
  - { name: system, code: 'os\.system.*', arg: 1, cwe: CWE-78 }
  - { name: run, code: 'subprocess\.run.*', arg: 1, cwe: CWE-78 }
  - { name: open, arg: 1, cwe: CWE-22 }
  - { name: loads, code: 'pickle\.loads.*', arg: 1, cwe: CWE-502 }
  - { name: eval, arg: 1, cwe: CWE-95 } # Auxiliary rule; not in the 14 classes.

# Sanitizer-like names are not proofs of safety.
sanitizers:
  - "int"
  - "escape"
```

### Registry interpretation

- **Registry `cwes`:** All **14** remain enabled for Python. This is a language-level scope, not an automatic guarantee of 14 independently trained, validated classifiers.
- **ML core subset:** 12 classes meeting the reported 100-sample screening threshold; set this subset in **training configuration**, not by deleting CWE-502/CWE-78 from `python.yaml`.
- **ML experimental subset:** CWE-502 and CWE-78. Their taint sinks remain enabled.
- **Auxiliary taint finding:** CWE-95 from `eval`, distinct from CWE-94. Decide how to expose auxiliary findings in product output.
- **No new untested patterns:** Keep active rules unchanged until targeted fixtures establish coverage.

## 8. Dataset and evaluation policy

| Item                          | Decision                                                  | Why                                                                 |
| ----------------------------- | --------------------------------------------------------- | ------------------------------------------------------------------- |
| Registry scope                | **14 Python CWEs**                                        | Preserve security scope and existing taint configuration            |
| Core ML scope                 | **12 CWEs**                                               | Reported ≥100 vulnerable samples each                               |
| Experimental ML scope         | **CWE-502, CWE-78**                                       | Security-relevant but currently below 100 samples                   |
| Initial eligibility threshold | **≥100 vulnerable samples per CWE**                       | Consistent with C/C++ provisional screening policy                  |
| Preferred target              | **≥300 independent, high-quality samples per CWE**        | Better support for held-out evaluation; not sufficient alone        |
| Taint claims                  | Only source/sink configuration and verified flows         | Avoid equating a YAML rule with validated detection                 |
| CPG claims                    | Graph-feature potential, not guaranteed detection         | Joern graph construction ≠ vulnerability confirmation               |
| Multi-label strategy          | Preserve multiple valid CWE labels per code sample        | The unified schema supports CWE lists; audit contradictory taxonomy |
| Splitting                     | Group by project/CVE when possible; assess commit overlap | Prevent leakage from related fixes and duplicate snippets           |
| Metrics                       | Per-CWE precision, recall, F1, support and error analysis | Expose classes that underperform despite aggregate accuracy         |

### Next steps before final acceptance

1. Recalculate Python CWE counts from the **current deduplicated Parquet files** and compare against the reported table above.
2. Recover or preserve CVE identifiers and project/commit provenance for group-aware splitting; the eight-column schema alone does not retain CVE IDs.
3. Measure **unique CVEs, projects, and commits per CWE**, particularly for CWE-444, CWE-89, CWE-502, and CWE-78.
4. Build targeted Python Joern/taint fixtures for each active sink, including keyword-argument and framework-routing edge cases.
5. Test whether CWE-444, CWE-613, and CWE-352 have sufficient structural/semantic signal for reliable classification; demote unsupported classes if necessary.
6. Keep CWE-95 auxiliary output distinct from the 14 selected ML classes unless it is deliberately added and evaluated.

## 9. Final decision

**Keep all 14 Python CWEs in `python.yaml`.** Treat **12** as initial core ML candidates and **2** (CWE-502 and CWE-78) as experimental candidates. Preserve the existing taint rules, including the auxiliary CWE-95 `eval` rule. Confirm sample counts and independence after the final dataset merge and leakage-safe split, and validate detection performance separately from Joern parsing and taint feature extraction.

---

### Evidence references

- Reported SHIELD post-deduplication Python CWE counts from the earlier acceptance-audit discussion — **not independently re-extracted for this document**.
- User-supplied `python.yaml` — language registry and active taint configuration.
- `dataset_audit.md` — intended source for reproducible per-dataset and per-CWE counts; rerun for final numbers.
- `taint_spike.md` — intended source for verified fixture observations; no additional unverified Python fixture results claimed here.
- `joern_spike.md` and `graph_schema.md` — Joern/CPG engineering context.
- MITRE CWE Top 25 — https://cwe.mitre.org/top25/.
