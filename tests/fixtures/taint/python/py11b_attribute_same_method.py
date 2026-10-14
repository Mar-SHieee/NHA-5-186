# py11b_attribute_same_method.py
# EXPECT: flow   (same as py11 but write and read in ONE method; isolates
#                 "attribute access" from "state across methods")
class Repo:
    def handler_py11b(self, request, cur):
        self.uid = request.args["id"]
        cur.execute("SELECT * FROM u WHERE id=" + self.uid)
