# shield_core/embeddings/

Frozen `microsoft/codebert-base`, fp16 on GPU. Long functions use 510-token sliding windows with mean pooling (decision D30).

| File / folder | What it is |
| --- | --- |
| `embedder.py` | `CodeBERTEmbedder`: batch inference + on-disk cache keyed by `sha256(code)`. |
| `node_embeddings.py` | `CPGNodeEmbedder`: embeds a graph node's code text (in-memory cache only, for now). |

Parent: [`shield_core/`](../README.md)
