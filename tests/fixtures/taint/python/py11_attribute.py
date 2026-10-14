# py11_attribute.py
# EXPECT: flow   (ground truth: load() then query() is the normal call order;
#                 hypothesis: Joern MISSES it, no call connects the two methods)
class Repo:
    def load(self, request):
        self.uid = request.args["id"]

    def query(self, cur):
        cur.execute("SELECT * FROM u WHERE id=" + self.uid)
