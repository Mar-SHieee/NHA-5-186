import sys

import tree_sitter_c as tsc
import tree_sitter_cpp as tscpp
import tree_sitter_python as tspython
from tree_sitter import Language, Parser

SAMPLES = {
    "python": (tspython.language(), b"def f(x):\n    return x\n"),
    "c": (tsc.language(), b"int f(int x) { return x; }\n"),
    "cpp": (tscpp.language(), b"int f(int x) { return x; }\n"),
}


def has_node(node, kind):
    """True if a node of this type exists anywhere in the tree."""
    if node.type == kind:
        return True
    return any(has_node(child, kind) for child in node.children)


failed = False
for name, (lang, code) in SAMPLES.items():
    tree = Parser(Language(lang)).parse(code)
    ok = (not tree.root_node.has_error) and has_node(tree.root_node, "function_definition")
    print(f"tree-sitter {name}: {'ok' if ok else 'FAIL'}")
    failed = failed or not ok

sys.exit(1 if failed else 0)
