from golemcpp.golem import helpers
from shutil import copytree
from string import Template
import subprocess
import shutil
import string
import importlib.util
import importlib.machinery
import os
import sys
from waflib import Scripting
from waflib import Context
import inspect
from pathlib import Path

def main() -> int:
    print("=== Golem C++ Build System ===")
    sys.stdout.flush()

    project_path = os.path.join(os.getcwd(), 'golem.json')
    project_path_alt = os.path.join(os.getcwd(), 'golemfile.py')
    if not os.path.exists(project_path_alt):
        project_path_alt = os.path.join(os.getcwd(), 'golem.py')
    if not os.path.exists(project_path_alt):
        project_path_alt = os.path.join(os.getcwd(), 'project.glm')

    golem_path = os.path.abspath(os.path.dirname(os.path.realpath(__file__)))
    golemcpp_data_path = Path(golem_path).parent.joinpath('data')

    user_defined_dir = None

    for idx, arg in enumerate(sys.argv):
        if arg.startswith('--dir='):
            user_defined_dir = arg.split('=')[1]
            sys.argv[idx] = '--dir=' + os.getcwd()

    golem_out = os.path.join('build')
    if user_defined_dir:
        golem_out = user_defined_dir

    sys.argv += ([] if user_defined_dir else ['--dir=' + os.getcwd()])

    build_dir = os.path.join(os.getcwd(), golem_out, 'golem')

    filein = open(os.path.join(golemcpp_data_path, 'wscript'))
    src = Template(filein.read())
    filein.close()
    out = src.substitute(
        builder_path=os.path.join(golem_path, 'builder.py').replace('\\', '\\\\'))

    if not os.path.exists(build_dir):
        os.makedirs(build_dir)

    fileout = open(os.path.join(build_dir, 'wscript'), 'w+')
    fileout.write(out)
    fileout.close()

    wafdir = os.path.abspath(inspect.getfile(inspect.getmodule(Scripting)))
    wafdir = str(Path(wafdir).parent.parent.absolute())

    Scripting.waf_entry_point(build_dir, Context.WAFVERSION, wafdir)

    if sys.argv[1] == 'distclean':
        path = golem_out
        if sys.platform.startswith('win32'):
            from time import sleep
            while os.path.exists(path):
                os.system("rmdir /s /q %s" % path)
                sleep(0.1)
        else:
            shutil.rmtree(path)
        return 0

    return 0