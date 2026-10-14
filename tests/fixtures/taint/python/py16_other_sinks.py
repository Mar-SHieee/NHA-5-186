# py16_other_sinks.py
# EXPECT: flow for all five
import os
import pickle
import subprocess

def handler_py16a(request):
    os.system(request.args["x"])

def handler_py16b(request):
    subprocess.run(request.args["x"], shell=True)

def handler_py16c(request):
    open(request.args["x"])

def handler_py16d(request):
    pickle.loads(request.args["x"])

def handler_py16e(request):
    eval(request.args["x"])
