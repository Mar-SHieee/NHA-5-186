# shield_core/verify/

Implements the D35 verdict rule: a fix is only called verified when the checks that *can* judge it all passed.

| File / folder | What it is |
| --- | --- |
| `pysource.py` | `SourceText`: parse a function and apply text-range edits so untouched lines stay byte-identical. Shared by `fix/` and `verify/`. |
| `pattern_checks.py` | Cheap structural proofs on patched code, one per CWE class. |
| `evidence.py` | `Rating`, `Checks`, `decide_verdict`, `make_report` -> `VerificationReport`. |

Parent: [`shield_core/`](../README.md)
