from golemcpp.golem import helpers
from golemcpp.golem import cli_arguments
from golemcpp.golem import command_help
from golemcpp.golem import command_init
from golemcpp.golem import command_tools
from golemcpp.golem import command_version
from string import Template
import shutil
import os
import sys
from waflib import Scripting
from waflib import Context
import inspect
from pathlib import Path

def main() -> int:
    print("=== Golem C++ Build System ===")
    sys.stdout.flush()

    golem_path = helpers.get_golemcpp_golem_dir()
    golemcpp_data_path = Path(golem_path).parent.joinpath('data')

    global_args, command, command_args = cli_arguments.parse_cli_arguments(sys.argv, os.getcwd())

    if '--version' in global_args:
        command_version.handle_version_command()
        return 0
    
    if command is None:
        command_help.handle_help_command()
        return 0

    project_dir, build_dir = cli_arguments.parse_directories_from_arguments(command_args)

    if command in ('init', 'initialize'):
        return command_init.handle_init_command(project_dir=project_dir,
                                                data_dir=golemcpp_data_path,
                                                args=command_args)

    if command == 'tools':
        return command_tools.handle_tools_command(project_dir=project_dir,
                                                  args=command_args)

    # For other commands, we only keep the arguments that are relevant for waf, which are the ones after the command
    sys.argv = [sys.argv[0], command] + command_args

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
        helpers.remove_tree(path)
        return 0

    return 0