"""Fix templates (W2-P4-03): hand-written rewrites that refuse when behaviour could change.

`TEMPLATES` maps the `template` names in languages/<language>.yaml to their functions. Each has the
signature `(code: str, context: str = "") -> TemplateResult` (see `base`).
Wiring into `suggest_fix()` is W3-P4-02, not here.
"""

from __future__ import annotations

from collections.abc import Callable

from shield_core.models.fixgen.base import TemplateResult
from shield_core.models.fixgen.command import command_argv
from shield_core.models.fixgen.path import path_confine
from shield_core.models.fixgen.sql import sql_parameterize

Template = Callable[..., TemplateResult]

TEMPLATES: dict[str, Template] = {
    "sql_parameterize": sql_parameterize,
    "command_argv": command_argv,
    "path_confine": path_confine,
}


def get_template(name: str) -> Template:
    try:
        return TEMPLATES[name]
    except KeyError:
        raise KeyError(f"unknown fix template {name!r}; known: {', '.join(TEMPLATES)}") from None


__all__ = ["TEMPLATES", "TemplateResult", "get_template"]
