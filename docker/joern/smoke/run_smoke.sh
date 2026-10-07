#!/bin/sh
# Smoke test: tree-sitter parse + Joern parse, one sample per language.
set -e

python /opt/smoke/smoke_treesitter.py

for lang in python c cpp; do
  joern-parse "/opt/smoke/samples/$lang" --output "/tmp/cpg_$lang.bin"
  test -s "/tmp/cpg_$lang.bin"
  echo "joern $lang: ok"
done

echo "ALL SMOKE TESTS PASSED"
