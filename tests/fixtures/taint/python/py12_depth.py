# py12_depth.py
# EXPECT: flow for both   (tests how deep Joern follows a call chain)
def f6(x):
    return x
def f5(x):
    return f6(x)
def f4(x):
    return f5(x)
def f3(x):
    return f4(x)
def f2(x):
    return f3(x)
def f1(x):
    return f2(x)

def handler_py12a(request, cur):     # depth 2 (f5 -> f6)
    cur.execute("SELECT " + f5(request.args["id"]))

def handler_py12b(request, cur):     # depth 6 (f1 -> ... -> f6)
    cur.execute("SELECT " + f1(request.args["id"]))

def handler_py12c(request, cur):     # 3 functions entered
    cur.execute("SELECT " + f4(request.args["id"]))

def handler_py12d(request, cur):     # 4 functions entered
    cur.execute("SELECT " + f3(request.args["id"]))

def handler_py12e(request, cur):     # 5 functions entered
    cur.execute("SELECT " + f2(request.args["id"]))
