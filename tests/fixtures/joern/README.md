# Joern fixtures

Small Python functions used to study Joern's CPG output (see docs/graph_schema.md).
They are deliberately incomplete: `escape` is never defined, so ruff is configured to skip
this folder.

Generated with Joern 4.0.647, schema_version 0.1-draft:

```
docker run --rm -v "${PWD}\<folder>:/workspace/sample" shield-joern bash -c "joern-parse sample/<file>.py --language pythonsrc -o sample/cpg.bin && joern-export sample/cpg.bin --repr all --format graphml --out sample/export"
python scripts/graphml_to_pyg.py <folder>/export/export.xml
```

Expected converter output (will change if Joern or the schema changes):

| File | Data |
|---|---|
| get_user.py | x=[48, 15], edge_index=[2, 176] |
| branch.py | x=[54, 15], edge_index=[2, 194] (CDG 5) |
| calls.py | x=[60, 15], edge_index=[2, 207] (CALL 1) |
