from golemcpp.golem import helpers
from golemcpp.golem import cli_arguments
from golemcpp.golem import init_command
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


def print_command_recap() -> None:
    print('Run `golem <command>` from your project root.')
    print('Useful commands:')
    print('  init          Create a documented starter golemfile.py')
    print('  configure     Configure the project with all the needed options')
    print('  resolve       Retrieve and configure dependencies (if dependencies are defined)')
    print('  dependencies  Build dependencies after resolve (if dependencies are defined)')
    print('  build         Build the project')
    print('  package       Generate a package from a successful build')
    print('  clean         Remove built object files')
    print('  distclean     Delete the build directory')
    print('Documentation: https://golemcpp.org/docs/guides/getting-started/')

def main() -> int:
    print("=== Golem C++ Build System ===")
    sys.stdout.flush()

    golem_path = helpers.get_golemcpp_golem_dir()
    golemcpp_data_path = Path(golem_path).parent.joinpath('data')

    command, project_dir, build_dir, command_args = cli_arguments.resolve_cli_arguments(sys.argv, os.getcwd())

    if command is None:
        print_command_recap()
        return 0

    if command in ('init', 'initialize'):
        return init_command.handle_init_command(project_dir=project_dir,
                                   data_dir=golemcpp_data_path,
                                   args=command_args)

    sys.argv = cli_arguments.normalize_argv(sys.argv,
                                           project_dir=project_dir,
                                           build_dir=build_dir)

    golem_out = build_dir
    build_dir = os.path.join(golem_out, 'golem')

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

    if command == 'distclean':
        path = golem_out
        if sys.platform.startswith('win32'):
            from time import sleep
            while os.path.exists(path):
                os.system("rmdir /s /q %s" % path)
                sleep(0.1)
        else:
            if os.path.isfile(path):
                os.remove(path)
            elif os.path.islink(path):
                os.unlink(path)
            elif os.path.isdir(path):
                shutil.rmtree(path)
        return 0

    return 0