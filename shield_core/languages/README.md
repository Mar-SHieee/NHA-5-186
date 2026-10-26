# shield_core/languages/

A language is **configuration, not code**. Adding one means adding one YAML file here. A test (`tests/languages/test_registry.py`) fails if a language name is hard-coded elsewhere.

| File / folder | What it is |
| --- | --- |
| `registry.py` | Loads and validates every `*.yaml` (unknown keys, bad regexes are errors); lookups like `enabled_languages()`. |
| `python.yaml` | Python: enabled, 14 CWEs, taint sources/sinks/sanitizers, 3 fix templates. |
| `cpp.yaml` | C and C++: enabled, 20 CWEs, taint config (no fix templates yet). |
| `java.yaml` | Java: DISABLED placeholder (decision D36); enabling it later is a one-word change. |

Parent: [`shield_core/`](../README.md)
