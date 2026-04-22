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


def make_absolute_path(path: str, cwd: str) -> str:
    if os.path.isabs(path):
        return path
    return os.path.join(cwd, path)

def resolve_cli_arguments(argv: list[str], cwd: str) -> tuple[str | None, str, str, list[str]]:
    command = None
    project_dir = cwd
    build_dir = os.path.join(cwd, 'build')
    command_args = []

    has_explicit_build_dir = False

    for index, arg in enumerate(argv[1:], start=1):
        if arg.startswith('--project-dir='):
            requested_dir = arg.split('=', 1)[1]
            if requested_dir:
                project_dir = make_absolute_path(requested_dir, cwd)
            continue

        if arg.startswith('--build-dir='):
            requested_dir = arg.split('=', 1)[1]
            if requested_dir:
                build_dir = make_absolute_path(requested_dir, cwd)
            has_explicit_build_dir = True
            continue

        if not arg.startswith('-') and command is None:
            command = arg
            command_args = argv[index + 1:]

    for index, arg in enumerate(argv[1:], start=1):
        # Deprecated --dir option, still supported for backward compatibility, but overridden by --build-dir if both are present
        if arg.startswith('--dir=') and not has_explicit_build_dir:
            requested_dir = arg.split('=', 1)[1]
            if requested_dir:
                build_dir = make_absolute_path(requested_dir, cwd)
            continue

    return command, project_dir, build_dir, command_args

def normalize_argv(argv: list[str]) -> list[str]:
    normalized_argv = [argv[0]]
    has_build_dir = False

    for arg in argv[1:]:
        if arg.startswith('--build-dir='):
            has_build_dir = True

        normalized_argv.append(arg)

    # Deprecated --dir option, still supported for backward compatibility, but overridden by --build-dir if both are present
    for arg in argv[1:]:
        if arg.startswith('--dir='):
            if not has_build_dir:
                normalized_argv.append('--build-dir=' + arg.split('=', 1)[1])
            continue

        normalized_argv.append(arg)

    return normalized_argv

def initialize_project(project_dir: str, data_dir: Path, force: bool = False) -> int:
    project_path = Path(project_dir).joinpath('golemfile.py')
    alternate_project_path = Path(project_dir).joinpath('golemfile.json')

    if not force:
        project_file_found = False
        if alternate_project_path.exists():
            print("ERROR: golemfile.json already exists in this directory")
            project_file_found = True

        if project_path.exists():
            print("ERROR: golemfile.py already exists in this directory")
            project_file_found = True

        if project_file_found:
            print("Use `golem init --force` to remove existing project files and generate a new golemfile.py.")
            return 1
    else:
        print("WARNING: --force option removes existing golemfile.py and golemfile.json files in the project directory if they exist.")

        if alternate_project_path.exists():
            alternate_project_path.unlink()
            print("Removed {}".format(alternate_project_path))

        if project_path.exists():
            project_path.unlink()
            print("Removed {}".format(project_path))

    template_path = data_dir.joinpath('golemfile.py.template')
    with open(template_path, 'r', encoding='utf-8') as filein:
        content = filein.read()

    with open(project_path, 'w', encoding='utf-8') as fileout:
        fileout.write(content)

    print("Created {}".format(project_path))
    print("Add your sources, then run `golem configure --variant=debug` and `golem build`.")
    return 0

def handle_init_command(project_dir: str, data_dir: Path, args: list[str]) -> int:
    force = False

    for arg in args:
        if arg.startswith('--project-dir='):
            continue
        if arg in ('-h', '--help'):
            print("Usage: golem init [--project-dir=<project_dir>] [--force]")
            print("Generate a commented golemfile.py in the current project directory.")
            return 0
        if arg == '--force':
            force = True
            continue

        print("ERROR: unsupported option for `golem init`: {}".format(arg))
        print("Usage: golem init [--project-dir=<project_dir>] [--force]")
        return 1

    return initialize_project(project_dir=project_dir, data_dir=data_dir, force=force)

def main() -> int:
    print("=== Golem C++ Build System ===")
    sys.stdout.flush()

    golem_path = helpers.get_golemcpp_golem_dir()
    golemcpp_data_path = Path(golem_path).parent.joinpath('data')

    command, project_dir, build_dir, command_args = resolve_cli_arguments(sys.argv, os.getcwd())

    if command in ('init', 'initialize'):
        return handle_init_command(project_dir=project_dir,
                                   data_dir=golemcpp_data_path,
                                   args=command_args)

    sys.argv = normalize_argv(sys.argv)

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