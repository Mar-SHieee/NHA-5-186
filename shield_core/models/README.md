# shield_core/models/

Models are selected by `models.yaml`, never hard-coded. If the default cannot load, V1 answers (automatic fallback). Future model code (V1, GNN, fusion) gets its own sub-folder here.

| File / folder | What it is |
| --- | --- |
| `registry.py` | Reads `models.yaml`; default -> fallback -> built-in stub -> error. `register_kind` for new model types. |
| `models.yaml` | Catalogue: `default`, `fallback`, entries `{version, kind, languages, path?, sha256?}`. Today only the `stub` kind. |

Parent: [`shield_core/`](../README.md)
