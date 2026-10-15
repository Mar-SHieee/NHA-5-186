# py20_resolve_guard.py
# EXPECT: flow   (a CORRECT CWE-22 fix: resolve() plus an is_relative_to guard before open().
#                 The code is safe, but resolve() and "/" pass taint through and a guard is not a
#                 data transformation, so we expect Joern to still report a flow. Ground truth is
#                 "not exploitable": an expected false fail.)
from pathlib import Path

UPLOAD_DIR = "/srv/uploads"


def handler_py20(request):
    name = request.args["file"]
    base = Path(UPLOAD_DIR).resolve()
    target = (base / name).resolve()
    if not target.is_relative_to(base):
        raise ValueError("bad path")
    with open(target) as f:
        return f.read()
