def clean(s):
    return escape(s)


def get_user(request, db):
    name = clean(request.args["name"])
    q = "SELECT * FROM u WHERE n='" + name + "'"
    db.cursor().execute(q)
