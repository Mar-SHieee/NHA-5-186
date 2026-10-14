# py13_parameterized.py
# EXPECT: no-flow   (SAFE code: the tainted value is a bound parameter, argument 2;
#                    the query string, argument 1, is constant)
def handler_py13(request, cur):
    cur.execute("SELECT * FROM u WHERE id=%s", (request.args["id"],))
