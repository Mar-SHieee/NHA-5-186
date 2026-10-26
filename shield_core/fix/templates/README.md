# shield_core/fix/templates/

Every template refuses when unsure and never returns code that does not parse. Registered in `__init__.py` (`TEMPLATES`) and referenced from `languages/python.yaml`.

| File / folder | What it is |
| --- | --- |
| `sql.py` | CWE-89: string-built SQL in `execute(...)` -> constant query + parameters. |
| `command.py` | CWE-78: `os.system(str)` / `shell=True` -> `subprocess.run([argv])`. |
| `path.py` | CWE-22: `open(join(BASE, name))` -> resolve + `is_relative_to` check. |
| `base.py` | `TemplateResult`, `refuse()`, `finalize()`. |
| `strings.py` | Takes string-building expressions apart (`+`, f-string, `%`, `.format`). |
| `astutil.py` | Small AST/import helpers shared by templates. |

Parent: [`shield_core/fix/`](../README.md)
