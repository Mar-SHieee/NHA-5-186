# py21_template_cwe89_output.py
# EXPECT: no-flow   (output of sql_parameterize on a py01-style vulnerable function:
#                    the SQL text is constant, the tainted value is execute argument 2)
import psycopg2

def handler_py21(request, cursor):
    user_id = request.args["id"]
    cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
