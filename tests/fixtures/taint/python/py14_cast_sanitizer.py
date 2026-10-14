# py14_cast_sanitizer.py
# EXPECT: flow   (Joern cannot know int() sanitizes; WE must detect it.
#                 Ground truth is "not exploitable", so this is an expected Joern false positive.)
def handler_py14(request, cur):
    uid = int(request.args["id"])
    cur.execute("SELECT * FROM u WHERE id=" + str(uid))
