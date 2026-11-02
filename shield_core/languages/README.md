# shield_core/languages/

A language is **configuration, not code**. Adding one means adding one YAML file here. A test (`tests/languages/test_registry.py`) fails if a language name is hard-coded elsewhere.

| File / folder | What it is |
| --- | --- |
| `registry.py` | Loads and validates every `*.yaml` (unknown keys, bad regexes are errors); lookups like `enabled_languages()`. Also reads the optional `ts_nodes` block. |
| `python.yaml` | Python: enabled, 14 CWEs, taint sources/sinks/sanitizers, 3 fix templates, tree-sitter node names (`ts_nodes`). |
| `cpp.yaml` | C and C++: enabled, 20 CWEs, taint config (no fix templates yet), tree-sitter node names (`ts_nodes`). |
| `java.yaml` | Java: DISABLED placeholder (decision D36). Enabling it later means `enabled: true` **and** adding its `ts_nodes` lists; `tests/extraction/test_ts_utils.py` fails until they exist. |

## `ts_nodes`: tree-sitter node names

`shield_core/extraction/ts_utils.py` reads these lists to measure code, so it never hard-codes a node name. Every enabled language needs all seven. A test checks that each name exists in the language's grammar.

| Key | What it lists |
| --- | --- |
| `branches` | Node types counted in `n_branches`: `if` and `elif`. |
| `loops` | Node types counted in `n_loops`. |
| `decisions` | Extra decision points, counted only in `cyclomatic`: boolean operators, `except` or `catch`, `case`, the conditional expression. |
| `nesting` | Blocks that add one level to `max_nesting`. |
| `skip_nesting_under` | A nesting node whose parent is listed here adds no level (the `if` of an `else if`). |
| `functions` | The node type of a function definition. |
| `name_fields` | Grammar fields to follow from a function node down to its name. |

Parent: [`shield_core/`](../README.md)
