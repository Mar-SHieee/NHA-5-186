# Python fix templates (W2-P4-03)

Templates for CWE-89, CWE-78 and CWE-22. Source of the rules: `docs/fixes/fix_template_survey.md`
(sections 4.1 to 4.3). Verdict rule: D35 (`shield_core/verify/evidence.py`).

## How they work

- Code: `shield_core/fix/templates/` (`sql.py`, `command.py`, `path.py`; shared `strings.py`,
  `astutil.py`, `base.py`). Metadata: `fix_templates` in `shield_core/languages/python.yaml` (cwe, rating,
  template name, pattern-check name). Checks: `shield_core/verify/pattern_checks.py`.
- Signature: `template(code, context="") -> TemplateResult(applied, fixed_code, reason,
  required_imports)`. `code` is the function text. `context` is optional text of the rest of the
  file and is **only read** (to see the database driver and existing imports).
- The code is understood with `ast` and edited as text: only the sink lines change, everything
  else stays byte-identical (comments, spacing, line endings, tabs).
- **Conservative:** a template applies only when it finds exactly one candidate sink and every
  refusal condition is clear. A refusal returns a reason and no code. Code that does not parse is a
  refusal, never an error.
- Imports cannot be added (only the function is rewritten), so `required_imports` lists what the
  caller must add (W3 puts it in `FixResult.message`).
- Verdict: `Rating(spec.rating)`, then `make_report(rating, Checks(...))`. CWE-89 is **strong**
  (re-detection gates PASS). CWE-78 and CWE-22 are **none**: re-detection still reports a flow on
  the correct fix (py19, py20), so PASS comes from syntax, the pattern check and tests.

## CWE-89, `sql_parameterize` (rating strong)

**Handles** one `<obj>.execute(sql)` where `sql` is built with `+`, an f-string, `%s` formatting or
`.format()`, inline or in a variable assigned once earlier in the same block and used once.
Values go in a tuple as the second argument; quotes around a value are removed. Placeholder by
driver import: `sqlite3` gives `?`; `psycopg2`, `pymysql`, `MySQLdb` give `%s` (a literal `%` in the
SQL is doubled for those).

**Refuses:** driver unknown, unsupported (SQLAlchemy, psycopg 3, ...) or several; a table, column,
`ORDER BY`, `IN (...)`, `LIKE` or `LIMIT` position (a value is only accepted right after `=`, `<`,
`>`, `<=`, `>=`, `!=`, `<>`); a value inside a SQL string or glued to a word; `%d`, `%(name)s`,
`!r`, format specs, keyword `.format`; parameters already passed; more than one candidate
`execute`; conditional, piecewise (`+=`), loop or cross-function building; a query variable that is
a parameter, used twice, or defined in another block; a value reassigned between the assignment and
the call.

**Pattern check** `execute_literal_sql` (recorded, not a gate for a strong class): every `execute`
call has a string literal as its first argument.

**Cannot prove**
- The placeholder style matches the driver the application really uses (read from imports only).
- Other `execute` calls in the file are safe: only the matched one changes.
- `id = ?` with a string parameter behaves like the old integer comparison: type affinity and
  implicit conversion differ by database (an unquoted `id = 5` now receives the string `"5"`).
- Removing quotes preserved intent in unusual SQL (comments, `--`, dialect quoting).
- A value expression with side effects (or one mutated by a method call) behaves the same when it
  is evaluated at the `execute` line instead of at the old assignment line.
- Re-detection (strong): it shows the SQL text no longer depends on input. It does not show the
  query is correct.

## CWE-78, `command_argv` (rating none)

**Handles** `os.system(<string>)` (as a bare statement) and `subprocess.run(<string>, shell=True,
...)`, where the string is literal words plus variables, each variable a whole shell word. Output:
`subprocess.run([...], check=True)` (other `subprocess.run` keywords are kept, `shell=True` is
dropped), plus a validation guard (decision O5): a value must match
`[A-Za-z0-9_.][A-Za-z0-9_.-]*` or `ValueError` is raised. Non-name values are evaluated once into
`cmd_arg`.

**Refuses:** shell features in the literal text (`| & ; < > ( ) $ ` * ? [ ] { } ~ # ! \`, and `%`
`^` for cmd.exe); a value that is part of a word or a quoted expression; the command name from
input; an environment assignment prefix; `os.system` whose result is used; a call evaluated
conditionally or later (`and`, lambda, comprehension, `while` test); `shell=` other than literal
`True`; keywords it does not understand; a command not built inside the call; more than one
candidate; a function that rebinds `re` or `subprocess`.

**Pattern check** `argv_list_no_shell` (the gate): every `subprocess.run` gets a list literal, no
`shell=` other than `False` anywhere, no `os.system` left.

**Cannot prove**
- The value is safe as an argument: the guard stops a leading `-`, but a command can still treat a
  value as a file name or a dangerous operand. Putting `--` before the value is not added.
- No shell feature was doing real work in the original (the template refuses the obvious ones).
- The guard fits the real use. **It changes behaviour** for legitimate values with other characters
  (spaces, `/`, `:`): the pattern is a placeholder to tighten per command. `guard=False` gives
  list form only.
- Values that are not `str` now raise `TypeError` in `subprocess.run` (the shell form converted
  them). `os.system` returned a status; the rewrite raises on failure (`check=True`).
- Re-detection: still reports a flow for the correct fix (py19), so it says nothing here.
- `from os import system`, `import subprocess as sp` and `subprocess.call/Popen/check_output` are
  not recognised.

## CWE-22, `path_confine` (rating none)

**Handles** `open(os.path.join(<base>, <name>))`, inline or through one plain assignment
(`p = os.path.join(...)`: the assignment is replaced by the guard, `open(p)` and later uses stay).
Output: `base = Path(<base>).resolve()`, `target = (base / <name>).resolve()`, a rejection with
`is_relative_to`, then `open(target)`. `base` and `target` get unused names if they already occur.
An absolute input is rejected too (`Path("/srv") / "/etc/passwd"` is `/etc/passwd`).

**Refuses:** no base directory (not a two-argument `os.path.join`, a parameter, `+` concatenation);
several directories; more than one candidate `open`; an `open` evaluated conditionally or in a
`while` test; a variable that is assigned twice or in another block; a function that rebinds
`Path`.

**Pattern check** `resolve_confine_before_open` (the gate): `resolve()`, an `is_relative_to` guard
whose branch raises or returns, all before the first `open`. The fixture `py20_resolve_guard.py`
is a positive example.

**Cannot prove**
- Check-then-use is not atomic: a race between the check and the open remains.
- Windows path rules (case, `\`, drive letters, reserved names) were not tested.
- Only `open` is covered, not `os.remove`, `send_file`, `shutil` or other file calls.
- The base directory expression itself may be wrong or too wide.
- Paths that are meant to be absolute or to live in several directories (not detectable).
- Re-detection: still reports a flow for the correct fix (py20), so it says nothing here.
- In the variable form the variable now holds the resolved absolute path, which differs from the
  joined path if code later prints or compares it.

## Decisions (plan section 5), confirmed by Bigad on 2026-10-17

O1 `shield_core/fix/templates/` · O2 `fix_templates` optional, default `()` · O3 `required_imports`
returned, no interface change · O4 refuse on more than one candidate · O5 list form plus guard ·
O6 stdlib `ast` plus text splice · O7 YAML metadata plus named code. All as recommended.

Added during the build: the optional `context` argument (the survey says the driver is read from
the file's imports, but `suggest_fix` only passes the function). Without it CWE-89 refuses
whenever the function text has no driver import.
