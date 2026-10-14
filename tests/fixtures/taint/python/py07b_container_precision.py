# py07b_container_precision.py
# EXPECT: no-flow   (the safe key "j" is read, not the tainted "k")
def handler_py07b(request, cur):
    d = {"k": request.args["id"], "j": "safe"}
    cur.execute(d["j"])
