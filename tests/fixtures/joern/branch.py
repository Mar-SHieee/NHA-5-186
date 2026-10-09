def get_user(request, db, safe):
    name = request.args["name"]
    if safe:
        name = escape(name)
    q = "SELECT * FROM u WHERE n='" + name + "'"
    db.cursor().execute(q)
