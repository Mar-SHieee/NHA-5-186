"""Result type shared by the fix templates (internal; the public contract is not touched).

A template is a function `(code, context="") -> TemplateResult`:
  code     the source text of the affected function (what `suggest_fix` receives)
  context  optional text of the rest of the file. Used only to SEE imports (the database driver,
           whether `subprocess` is already imported). Never edited.
It never raises for code it does not like: a refusal is a normal answer (later mapped to the
contract status `no_fix_available`).
"""

from __future__ import annotations

from dataclasses import dataclass

from shield_core.verify.pysource import SourceText


@dataclass(frozen=True)
class TemplateResult:
    applied: bool
    fixed_code: str | None
    reason: str  # why it refused, or a one-line summary of the change
    required_imports: tuple[str, ...] = ()  # lines the caller must add; the function text has none


def refuse(reason: str) -> TemplateResult:
    return TemplateResult(applied=False, fixed_code=None, reason=reason)


def finalize(fixed: str, reason: str, imports: tuple[str, ...] = ()) -> TemplateResult:
    """Last safety net: a template never returns code that does not parse."""
    if SourceText.parse(fixed) is None:
        return refuse("internal error: the generated code does not parse")
    return TemplateResult(applied=True, fixed_code=fixed, reason=reason, required_imports=imports)
