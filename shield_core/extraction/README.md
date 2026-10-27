# shield_core/extraction/

ML code imports `graph_extractor.py`, never Joern directly (decision D2).

| File / folder | What it is |
| --- | --- |
| `graph_extractor.py` | `GraphExtractor` abstract class + `CodeGraph`/`GraphNode`/`GraphEdge`; code hashing. |
| `joern_extractor.py` | The Joern implementation: `joern-parse` -> `joern-export` -> `parse_graphml`. |
| `cache.py` | Disk cache keyed by code hash + language + extractor + versions; `CachedGraphExtractor`. |

Parent: [`shield_core/`](../README.md)
