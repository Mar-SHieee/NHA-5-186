# shield_core/extraction/

ML code imports `graph_extractor.py`, never Joern directly (decision D2).

| File / folder        | What it is                                                                                  |
| -------------------- | ------------------------------------------------------------------------------------------- |
| `graph_extractor.py` | `GraphExtractor` abstract class + `CodeGraph`/`GraphNode`/`GraphEdge`; code hashing.        |
| `joern_extractor.py` | The Joern implementation: `joern-parse` -> `joern-export` -> `parse_graphml`.               |
| `cache.py`           | Disk cache keyed by code hash + language + extractor + versions; `CachedGraphExtractor`.    |
| `ts_utils.py`        | tree-sitter helpers: split a file into functions, measure them, build the V2 feature table. |

## `ts_utils.py`

It reads code with tree-sitter, so it needs neither Joern nor Docker.

| Function              | What it does                                                                                           |
| --------------------- | ------------------------------------------------------------------------------------------------------ |
| `extract_functions`   | Splits a source file into its functions (name, first and last line, text).                             |
| `compute_metrics`     | Measures one function: lines, branches, loops, cyclomatic complexity, nesting depth, parse-error flag. |
| `build_feature_table` | Runs `compute_metrics` on every row of a dataset (the V2 features for P3).                             |

The node names it counts come from the `ts_nodes` block of each language YAML.

Parent: [`shield_core/`](../README.md)
