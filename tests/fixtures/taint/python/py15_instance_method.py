# py15_instance_method.py
# EXPECT: flow for both   (hypothesis: uncertain, the callee is found through
#                          self/an object, not by plain name)
class Repo:
    def build(self, uid):
        return "SELECT * FROM u WHERE id=" + uid

    def handler_py15a(self, request, cur):
        cur.execute(self.build(request.args["id"]))

def handler_py15b(request, cur):
    r = Repo()
    cur.execute(r.build(request.args["id"]))
