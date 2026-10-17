# Fix templates: how they work and where to look when they break

Written after W2-P4-03 was merged. `docs/fix_templates_python.md` says what each template handles,
refuses and cannot prove. This file explains how the code is built, so you can read it, defend it
and change it. All outputs below were produced by running the real templates.

## 1. The idea

A template is a function that takes the text of one vulnerable function and either returns a fixed
version or **refuses with a reason**. It fixes only a few exact code shapes. A wrong fix is worse
than no fix, so every doubt is a refusal.

## 2. Map of the code

| Piece | File | Job |
|---|---|---|
| Metadata | `languages/python.yaml`, `languages/registry.py` | Per CWE: `rating`, `template` name, `pattern_check` name. No code lives here. |
| Templates | `shield_core/models/fixgen/sql.py`, `command.py`, `path.py` | The three rewrites. |
| Template table | `shield_core/models/fixgen/__init__.py` | `TEMPLATES`: name to function. |
| Result type | `fixgen/base.py` | `TemplateResult`, `refuse()`, `finalize()`. |
| String analysis | `fixgen/strings.py` | Takes `+`, f-string, `%` and `.format()` apart into text pieces and values. |
| AST helpers | `fixgen/astutil.py` | Import detection, `single_assignment`, `enclosing_statement`, fresh names. |
| Source helper | `shield_core/verify/pysource.py` | Parse a function, map AST positions to text offsets, apply edits. |
| Pattern checks | `shield_core/verify/pattern_checks.py` | After a fix: a yes/no test of the code's shape. `PATTERN_CHECKS` is the name table. |
| Verdict | `shield_core/verify/evidence.py` | `decide_verdict` and `make_report` (D35). Existed before this step. |

The YAML names the template and the check, the code tables resolve the names.
`tests/test_pattern_checks.py` fails if a name in any YAML has no code behind it.

## 3. What one call does

`template(code, context="")` returns `TemplateResult(applied, fixed_code, reason, required_imports)`.

1. **Parse** with `SourceText.parse`. An indented method does not parse alone, so it is retried
   inside an `if True:` wrapper. If both fail the result is a refusal.
2. **Find the candidate.** Exactly one sink call (`execute`, `os.system`, `open`). None or several
   is a refusal.
3. **Check the shape and the refusal rules** (plan section 4, and the notes doc).
4. **Edit the original text** at exact character offsets. The function is never regenerated, so
   comments, spacing, tabs, CRLF and every other line stay byte-identical.
5. **Re-parse the output** (`finalize`). If it does not parse the result is a refusal, never broken
   code.
6. **Return** the fixed text, a one-line `reason`, and the imports the caller must add (the
   function text has no import lines).

`context` is the rest of the file, **read only**. It is used to see imports (database driver,
whether `subprocess` or `Path` is already imported).

## 4. Worked examples (real output)

### CWE-89, fixed
Input:
```python
import psycopg2


def get_user(request, cursor):
    user_id = request.args["id"]
    query = "SELECT * FROM users WHERE id = " + user_id
    cursor.execute(query)
```
Output (`applied=True`, imports `()`): the assignment is removed and the value becomes a parameter.
The placeholder is `%s` because `psycopg2` is imported (`?` for `sqlite3`).
```python
import psycopg2


def get_user(request, cursor):
    user_id = request.args["id"]
    cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
```

### CWE-89, refused
- `c.execute("SELECT * FROM u ORDER BY " + col)` with `sqlite3`:
  *a value is not directly after a comparison operator (identifier, ORDER BY, IN (...), LIKE or
  LIMIT position)*. A column name cannot be a placeholder.
- The same kind of code with no driver import and no `context`:
  *cannot tell the database driver (no known driver import is visible)*.

### CWE-78, fixed
Input:
```python
import os


def ping(request):
    host = request.form["host"]
    os.system("ping -c 1 " + host)
```
Output (`applied=True`, imports `("import subprocess", "import re")`):
```python
import os


def ping(request):
    host = request.form["host"]
    if not re.fullmatch(r"[A-Za-z0-9_.][A-Za-z0-9_.-]*", host):
        raise ValueError("unsafe command argument")
    subprocess.run(["ping", "-c", "1", host], check=True)
```
The guard is the behaviour change confirmed as O5: a value with `/` or a space now raises.

### CWE-78, refused
`os.system("ping " + h + " | grep ms")`: *the command uses shell features (pipe, redirect, glob,
$, ...)*. The shell was doing real work, so a list cannot replace it.

### CWE-22, fixed
Input:
```python
import os


def read(request):
    name = request.args["file"]
    with open(os.path.join(UPLOAD_DIR, name)) as f:
        return f.read()
```
Output (`applied=True`, imports `("from pathlib import Path",)`):
```python
import os


def read(request):
    name = request.args["file"]
    base = Path(UPLOAD_DIR).resolve()
    target = (base / name).resolve()
    if not target.is_relative_to(base):
        raise ValueError("path escapes base directory")
    with open(target) as f:
        return f.read()
```

### CWE-22, refused
`return open(name).read()`: *no base directory could be found: 'name' is a parameter, its value is
built elsewhere*. With no base directory there is nothing to confine to.

## 5. How the verdict is decided

Our detector (Joern) can only tell fixed from unfixed for CWE-89. For CWE-78 and CWE-22 it still
reports a flow on the correct fix (py19, py20), so a quiet or a loud detector means nothing there.

| Class | Rating | PASS needs | Evidence |
|---|---|---|---|
| CWE-89 | strong | syntax ok, **re-detection ok**, tests not false | py13 and py21: no flow on a parameterized query, including our own generated output |
| CWE-78 | none | syntax ok, **pattern check ok**, tests not false | py19: correct fix still flows |
| CWE-22 | none | syntax ok, **pattern check ok**, tests not false | py20: correct fix still flows |

The real CWE-78 report for the fix above:
`PASS`, `redetect_ok=False`, notes
`[evidence] syntax=ok; redetect=false(not decisive); pattern_check=ok; tests=not_run. Not verified by re-detection.`
`redetect_ok` keeps the real detector answer, so the report never lies about it. The notes say what
was and was not checked, and "verified" is only used when every configured check ran and passed.

How a template result becomes a report (for W3):
```python
rating = Rating(spec.rating)
checks = Checks(syntax_ok=..., redetect_ok=<Joern hook>, tests_ok=None,
                pattern_ok=PATTERN_CHECKS[spec.pattern_check](fixed))
report = make_report(rating, checks)
```

## 6. Why it is built this way

- **Text edits, not `ast.unparse`.** Unparsing a whole function would reformat the user's code and
  lose comments. The AST is only used to know where things are.
- **Refuse by default.** Each rule in the survey's "must not apply" lists is code. The v1 supports
  only the shapes in the plan. A long refusal list is acceptable, a wrong fix is not.
- **One candidate only.** With two candidate sinks the template cannot know which one the finding
  is about, so it fixes neither (O4).
- **`ast`, not tree-sitter (O6).** The stdlib parser is exact for Python and has no dependency. Its
  one trap is that column offsets count bytes, which `pysource.py` converts.
- **Metadata in YAML, code in Python (O7).** Adding a language's templates is a YAML edit plus code
  by name, and the registry validates the names' format.

## 7. When something breaks: where to look

| Symptom | Look at |
|---|---|
| A fix is refused and you think it should apply | Read `reason`. It names the rule. Then the matching function: `_build` and `_detect_style` in `sql.py`; `_SHELL_FEATURE` and the word loop in `command.py`; `_is_join` in `path.py` |
| "the code does not parse" for a valid function | `SourceText.parse` in `pysource.py` (the `if True:` wrapper) |
| "not built with +, an f-string, % or .format()" | `decompose` in `strings.py` |
| "assigned more than once", "not in the same block", "is a parameter" | `single_assignment` in `astutil.py` |
| "evaluated conditionally" or "in a ... statement the template does not handle" | `enclosing_statement` in `astutil.py` |
| The edit lands in the wrong place or text is garbled | `SourceText.offset` and `apply` (bytes versus characters, overlapping edits) |
| Fixed code differs from expectation only in quotes or layout | `py_literal` and `value_text` in `strings.py` (f-string values use `ast.unparse` before Python 3.12) |
| A class gets the wrong verdict | The rating in `python.yaml`, then `decide_verdict` in `evidence.py`, then the check in `pattern_checks.py` |
| `KeyError: unknown fix template` | A name in the YAML is missing from `TEMPLATES` or `PATTERN_CHECKS` |
| Registry error mentioning `fix_templates` | `_parse_fix_templates` in `languages/registry.py`; the message names the entry index |

Tests that fail first when you change a rule: `tests/test_fix_template_sql.py`,
`test_fix_template_command.py`, `test_fix_template_path.py` (each has a refusal table to extend).

## 8. Adding a template (for example, another CWE)

1. Write `template(code, context="") -> TemplateResult` in `fixgen/`, using `SourceText`,
   `refuse` and `finalize`. Refuse first, fix last.
2. Register it in `TEMPLATES` in `fixgen/__init__.py`.
3. Write the pattern check and register it in `PATTERN_CHECKS`.
4. Add the entry to `fix_templates` in the language YAML. The CWE must already be in `cwes`.
5. Decide the rating **from evidence** (a fixture pair like py13 or py19 and py20), then record it
   in `docs/taint_spike.md`.
6. Tests: the fixed shape, every refusal, byte-identical outside the sink, a behaviour test where
   it can run, and a `make_report` verdict test.

## 9. What W3 must do with this

- **W3-P4-02, `suggest_fix`:** pass the file text as `context`, otherwise CWE-89 refuses whenever
  the function has no driver import. Put `required_imports` into `FixResult.message`. Map a
  refusal to status `no_fix_available`. The contract does not change.
- **W3-P4-01, verification:** call `make_report` with the real Joern result for `redetect_ok`. In
  the W2 tests it was passed by hand.
- **C templates (CWE-120/787):** rated none, so a pattern check has to be designed for them first.

## 10. Questions you may be asked

- **Why does a "verified" fix show `redetect=false`?** Because for that class the detector cannot
  tell, and the report keeps its real answer. The verdict comes from the syntactic check.
- **Why not add `resolve` or `shlex.quote` to the sanitizer list?** `resolve` is not a confinement,
  and a bare `quote` name also matches `urllib.parse.quote`.
- **Can a template break working code?** Yes, in the ways the notes list (a guard rejecting valid
  values, a non-string value, type conversion in SQL). Each is documented and none is silent.
- **What is not covered?** Other call spellings (`from os import system`), other file functions
  besides `open`, other databases, and every shape in the refusal lists.
- **How do you know the strong rating holds?** py13 (hand-written) and py21 (the template's own
  output) both give no flow, in the driver run of 2026-10-17.
