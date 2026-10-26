# shield_core/taint/

Taint is a *feature generator*, never a verdict by itself (decision D29).

| File / folder | What it is |
| --- | --- |
| `joern_queries.py` | YAML sources/sinks/sanitizers -> Joern (Scala) script; parses `@@SRC/@@SNK/@@SINK/@@FLOW` output into a `Report`. |

Parent: [`shield_core/`](../README.md)
