def get_user(request, db):
    name = request.args["name"]
    q = "SELECT * FROM u WHERE n='" + name + "'"
    cur = db.cursor()
    cur.execute(q)
    return cur.fetchall()
