# py17_other_sources.py
# EXPECT: flow for all four
import sys

def handler_py17a(cur):
    cur.execute("SELECT " + input())

def handler_py17b(cur):
    cur.execute("SELECT " + sys.argv[1])

def handler_py17c(request, cur):
    cur.execute("SELECT " + request.form["x"])

def handler_py17d(request, cur):
    cur.execute("SELECT " + request.get_json())
