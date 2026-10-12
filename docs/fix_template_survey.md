# Fix template survey (W1-P4-04)

Status: draft. The CWEs below are provisional. Each language's `cwes` list is set from the
dataset audit at Gate G1 (Steps 25 and 26). If the audit picks different CWEs, add an entry using the
fields in section 2.4 and update the summary table in section 3.

Scope: Python's top 3 CWEs in full (89, 78, 22), a short table of other Python candidates, and an
outline of C memory-safety fixes. Nothing here is implemented. W2-P4-03 builds the Python templates
from this document.

## 1. What this document is for

`suggest_fix(finding)` returns a `FixResult` whose `method` is `"template"` or `"codet5"`. A
template is a hand-written rule: recognise a vulnerable code shape, rewrite it to the standard safe
shape, and refuse to apply when the rewrite could change behaviour. This survey records, for each
CWE, what the safe shape is, when a template must not apply, and whether SHIELD's own detector can
confirm the fix worked (re-detection). The last point decides which fixes may be shown as verified.

## 2. How to read it

### 2.1 The three checks

`VerificationReport` has three booleans. A fix is verified by evidence from these:

- `syntax_ok`: the patched code still parses (tree-sitter grammar chosen by the language registry).
- `tests_ok`: the project's own tests pass. `None` when the project has no tests.
- `redetect_ok`: re-detection, defined next.

### 2.2 Re-detection (working assumption)

Re-detection re-runs the Joern taint configuration of the language (`sources`, `sinks` and
`sanitizers` in `languages/<language>.yaml`) on the patched function and asks whether a
source-to-sink path for the finding's CWE still exists. If none remains, `redetect_ok` is true.
If the plan also re-runs `predict()` and uses its score, treat that as a second signal. It is not
covered here.

Three properties of the current taint configuration shape every rating below:

1. A sink looks at one argument position (`arg`). Keyword arguments get index -1 and are not
   covered (`python.yaml`). So the detector cannot see `shell=True`.
2. Joern cannot see inside a sanitizer. A path through a sanitizer call is still reported, marked
   `sanitizer_present`, and never dropped (`python.yaml`, `cpp.yaml`). A fix that only adds a sanitizer
   call therefore does not make the finding disappear.
3. A guard (an `if` that rejects bad input) is not a data transformation. The detector does not
   understand it, so the data still reaches the sink.

### 2.3 Ratings

| Rating | Meaning |
| --- | --- |
| Strong | The detector can tell fixed from unfixed. Re-detection is good evidence. |
| Weak | Re-detection gives a hint but can be wrong. A syntactic check or a test is also needed. |
| None | Re-detection cannot decide. Only tests, a syntactic check, or runtime tools can. |

Two failure modes to keep in mind:

- False pass: the detector goes quiet but the bug is still there. Example: the fix lost the taint (see
  `strncpy` in section 6), or deleted the code.
- False fail: the fix is correct but the detector still reports it. Example: a guard or a
  canonicalisation call that Joern passes taint through.

### 2.4 Fields of every entry

Vulnerable pattern, standard fix, template feasibility (Easy, Medium, Hard), when a template must not
apply, what re-detection can verify, and what other evidence is needed.

## 3. Summary

| CWE | Standard fix | Template | Re-detection | Other evidence needed |
| --- | --- | --- | --- | --- |
| Python 89, SQL injection | Parameterized query | Medium | Strong (to confirm) | Syntax check, tests |
| Python 78, OS command injection | Argument list, no shell, validated input | Medium | Weak, false fail likely | Syntactic check (no `shell=True`), test |
| Python 22, path traversal | Resolve and confine to a base directory | Medium | None, false fail | Test with `../` and absolute paths |
| C 120 and 787, unbounded copy or length | Bounded copy, length check | Medium to Hard | None, false pass or false fail | Compile, ASan test, fuzz |
| C format string (134) | Constant format string | Easy | Strong once a sink is added | Syntax check |

## 4. Python entries

### 4.1 CWE-89: SQL injection

Vulnerable pattern. Untrusted input is joined into the SQL text, then executed. The same shape
appears with `+`, f-strings, `%` formatting and `.format()`.

```python
user_id = request.args["id"]
query = "SELECT * FROM users WHERE id = " + user_id
cursor.execute(query)
```

Standard fix. A parameterized query: the SQL text is a constant with placeholders, and the values are
passed separately, so the database never reads them as code.

```python
user_id = request.args["id"]
cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
```

Template feasibility: Medium. Easy when the query is built by one concatenation in the same
function as the `execute` call. Harder when it is built across functions or in a loop.

The placeholder style depends on the database driver: `?` for `sqlite3`, `%s` for `psycopg2`,
`PyMySQL` and `mysqlclient`. The placeholder is not wrapped in quotes. The template must read the
driver from the file's imports and must not apply when it cannot tell.

Must not apply when:
- table names, column names or `ORDER BY` direction come from input. These cannot be placeholders.
  The fix there is an allowlist, not a parameter.
- the query has an `IN (...)` list of variable length. The template would have to generate the
  placeholders.
- a `LIKE` pattern is built with `%` around the input. The `%` belongs in the parameter value.
- the query is assembled conditionally from several pieces.

Re-detection: Strong, to confirm with a fixture. The configured sink is `execute` argument 1,
which is the SQL text. After the fix the text is a constant and the tainted value sits in argument 2,
which is not a sink argument, so the flow should disappear. This proves only that the SQL text no
longer depends on input. It does not prove the placeholder style matches the driver.

Other evidence: `syntax_ok`, `tests_ok`, and a cheap syntactic check that the first argument of
`execute` is a string literal.

### 4.2 CWE-78: OS command injection

Vulnerable pattern. Input is joined into a command string run by a shell.

```python
host = request.form["host"]
os.system("ping -c 1 " + host)
subprocess.run("ping -c 1 " + host, shell=True)
```

Standard fix. Do not use a shell. Pass the command and each argument separately, and validate the
value. The OWASP cheat sheet ranks the options: avoid calling OS commands at all, then
parameterization together with input validation. Escaping is the weakest and still leaves argument
injection.

```python
if not re.fullmatch(r"[A-Za-z0-9.-]+", host):
    abort(400)
subprocess.run(["ping", "-c", "1", host], check=True)
```

Argument injection is the part templates forget. A value starting with `-` is read as an option.
Where the command supports it, put `--` before the value. If a shell cannot be avoided,
`shlex.quote(host)` is the fallback, never string concatenation.

Template feasibility: Medium. Mechanical when the command is a literal plus one variable. Hard when
it is built from several variables, or when it uses pipes, redirects or globs, because then the shell
was doing real work.

Must not apply when the string uses shell features, when the value is part of a larger quoted
expression, or when the command name itself comes from input.

Re-detection: Weak, and likely a false fail. The configuration covers `os.system` and
`subprocess.run` positional argument 1 only, and cannot see `shell=True`. After the correct fix the
tainted value is an element of a list in argument 1. We expect taint to follow it, so the detector
would still report a correct fix. This must be confirmed with a fixture. Replacing `os.system` with
`subprocess.run` changes the sink, not the flow. The correct fix passes re-detection only if the
validation call is recognised as a sanitizer, and the current list is `int` and `escape`.

Other evidence: a syntactic check (first argument of `subprocess.run` is a list literal, no
`shell=True`), plus a test that passes `a; id` and `--version` and expects an error or a harmless
result. For numeric parameters, `int(x)` is a valid fix and is already in the sanitizer list.

### 4.3 CWE-22: path traversal

Vulnerable pattern. Input becomes part of a file path and nothing confines it to a directory.

```python
name = request.args["file"]
with open(os.path.join(UPLOAD_DIR, name)) as f:
    data = f.read()
```

Standard fix. Resolve the final path and require that it stays inside the base directory.

```python
base = Path(UPLOAD_DIR).resolve()
target = (base / name).resolve()
if not target.is_relative_to(base):
    abort(400)
with open(target) as f:
    data = f.read()
```

Alternatives: an allowlist of known names or ids; `werkzeug.utils.secure_filename` for uploaded file
names (it changes the name). Do not use a check for `".."` in the string: absolute paths, encodings
and symlinks bypass it. Note that `os.path.join(base, name)` silently drops `base` when `name` is
absolute, and `os.path.realpath` alone only canonicalises. It does not confine. The same point is made in
`cpp.yaml` for `realpath`.

Template feasibility: Medium. It needs the base directory expression. If the code has no base
directory, there is nothing to confine to and the template must not apply.

Must not apply when the path is meant to be absolute, when several directories are allowed, or when
a race between the check and the open matters (check-then-use is not atomic).

Re-detection: None, and a false fail. The check is a guard, and `resolve()` and `/` are calls Joern
passes taint through, so the value still reaches `open` argument 1. `resolve` must not be added to
the sanitizer list, for the same reason `realpath` is not a confinement.

Other evidence: tests that feed `../../etc/passwd` and an absolute path and expect a rejection, plus
a syntactic check that `resolve`, `is_relative_to` and a rejection appear before the `open`.

## 5. Other Python candidates

The taint configuration already has sinks for two more CWEs. The last two rows are not in the taint
configuration, so re-detection cannot see them today.

| CWE | Vulnerable | Standard fix | Template | Re-detection |
| --- | --- | --- | --- | --- |
| 502, unsafe deserialization (`pickle.loads`) | Untrusted bytes unpickled | Use a data format such as JSON, or authenticate the data before loading | Hard, the format changes for callers | Strong that the sink is gone, tests needed for behaviour |
| 95, code injection (`eval`) | `eval(user_text)` | `ast.literal_eval` if the input is a literal, else a lookup table | Medium | Strong that the sink is gone, tests needed because non-literal input now fails |
| 79, cross-site scripting | Input in HTML | Auto-escaping templates, `markupsafe.escape` | Medium | None, no sink configured |
| 798, hard-coded credentials | Secret in source | Read from environment or a secret store | Medium | None, a pattern scan is needed, not taint |

## 6. C memory-safety outline

The C configuration (`cpp.yaml`) has sinks `system`, `fopen`, `strcpy` (CWE-120) and `memcpy` length
(CWE-787). These labels are provisional like the rest. Templates for C are harder than for Python
because the correct fix depends on sizes and ownership the detector often cannot see.

1. Unbounded string copy or format (CWE-120 family: `strcpy`, `strcat`, `sprintf`, `gets`).
   - Fix: `snprintf(dst, sizeof dst, "%s", src)`, or `fgets` instead of `gets`.
   - Template: Medium, and only when `dst` is a real array in scope. In a function that receives
     `char *dst`, `sizeof dst` is the size of the pointer, which silently breaks the fix.
   - Re-detection: None, a false pass. `cpp.yaml` records that `strncpy` and `strncat` lose taint, so
     the detector reports "fixed" for a replacement that may still truncate or leave a string
     without a terminator.
   - Evidence: compile, then run a long input under AddressSanitizer.

2. Tainted length or index (CWE-787, 125; `memcpy` length is the configured sink).
   - Fix: check the length against the destination size before the copy.
   - Template: Medium to Hard, because the destination size must be known.
   - Re-detection: None, a false fail. The check is a guard and the value still reaches `memcpy`.
     `atoi` is explicitly not a sanitizer in `cpp.yaml`.
   - Evidence: tests with boundary lengths, AddressSanitizer, fuzzing.

3. Integer overflow before an allocation (CWE-190).
   - Fix: check `n > SIZE_MAX / sizeof *p` first, or use `calloc(n, size)`.
   - Template: Hard. Re-detection: None, there is no taint configuration for it.

4. Use after free and double free (CWE-416, 415).
   - Fix: set the pointer to `NULL` after `free`, or narrow the ownership.
   - Template: Hard, ownership is a design question. Re-detection: None, it is not a source-to-sink
     flow. It needs a different query or a runtime tool.

5. NULL dereference (CWE-476).
   - Fix: check the result of `malloc` or `fopen` before use.
   - Template: Easy for "result used immediately". Re-detection: None today. A Joern query for "result
     used without a prior check" could make it Weak.

6. Format string (CWE-134).
   - Fix: `printf(buf)` becomes `printf("%s", buf)`.
   - Template: Easy, and the best C candidate. Re-detection: Strong once the `printf` family is added
     as sinks. It is not in the sink list today.

7. Command injection (`system`) and path traversal (`fopen`).
   - Same fixes as sections 4.2 and 4.3 (`execv`-style argument arrays, confinement with a prefix
     check after `realpath`) and the same limits: Weak and None.

For fixes where re-detection is None, the evidence has to come from compiling with warnings, running
the existing tests, and re-running the triggering input under AddressSanitizer and
UndefinedBehaviorSanitizer.

## 7. Decision needed: the verdict for hard-to-verify fixes

`VerificationReport.verdict` is `"PASS"` or `"FAIL"`. Proposal:

- PASS needs `syntax_ok` and `redetect_ok` and `tests_ok` not false.
- For fix classes rated Weak or None in this document, re-detection cannot be the evidence. The
  result should say so in `verification.notes` and must not be shown as "verified" until a test or a
  syntactic check passes.

This touches the frozen interface and the UI wording, so it needs the team's decision before the
Friday freeze.

## 8. To confirm before the templates are built

1. A fixture where the SQL text is constant and the tainted value is the second argument of
   `execute`. Expected: no flow. (Supports the Strong rating in 4.1.)
2. A fixture where a tainted value is an element of a list passed to `subprocess.run`. Expected: a
   flow is reported. (Supports the false fail in 4.2.)
3. A fixture with `resolve()` and an `is_relative_to` guard before `open`. Expected: a flow is
   reported. (Supports 4.3.)
4. Whether `shlex.quote` should be a sanitizer. Sanitizers match by call name, so `quote` would also
   match `urllib.parse.quote`, which is not a shell sanitizer.
5. The final CWE list per language from the audit (section 3 and 5 may change).

## 9. Sources

- CWE entries: <https://cwe.mitre.org/data/definitions/89.html>, `/78.html`, `/22.html`, `/502.html`,
  `/95.html`, `/79.html`, `/798.html`, `/120.html`, `/787.html`, `/125.html`, `/190.html`, `/416.html`,
  `/476.html`, `/134.html` on the same site.
- OWASP SQL Injection Prevention Cheat Sheet:
  <https://cheatsheetseries.owasp.org/cheatsheets/SQL_Injection_Prevention_Cheat_Sheet.html>
- OWASP OS Command Injection Defense Cheat Sheet:
  <https://cheatsheetseries.owasp.org/cheatsheets/OS_Command_Injection_Defense_Cheat_Sheet.html>
- OWASP Path Traversal: <https://owasp.org/www-community/attacks/Path_Traversal>
- Python `subprocess` security considerations:
  <https://docs.python.org/3/library/subprocess.html#security-considerations>
- Python `pathlib`: <https://docs.python.org/3/library/pathlib.html>
- SEI CERT C Coding Standard: <https://wiki.sei.cmu.edu/confluence/display/c>
- Project files: `languages/python.yaml`, `languages/cpp.yaml`, `docs/taint_spike.md`,
  `shield_core/interface.py`.
