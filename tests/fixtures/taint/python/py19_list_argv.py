# py19_list_argv.py
# EXPECT: flow   (a CORRECT CWE-78 fix: argument list, no shell. The code is safe, but we expect
#                 taint to follow the list element into subprocess.run argument 1, so Joern still
#                 reports a flow. Ground truth is "not exploitable": an expected false fail.)
import subprocess


def handler_py19(request):
    host = request.form["host"]
    subprocess.run(["ping", "-c", "1", host], check=True)
