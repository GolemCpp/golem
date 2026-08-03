from argparse import ArgumentParser
from argparse import Namespace
from dataclasses import dataclass
from dataclasses import field

from golemcpp.golem.cache_configuration import get_cache_configuration
from golemcpp.golem import helpers
from golemcpp.golem import network
from golemcpp.golem import settings
from golemcpp.golem import tool_manager


def build_tools_parser() -> ArgumentParser:
    parser = ArgumentParser(
        prog='golem tools',
        add_help=False,
        description='Manage local tools stored in the Golem cache.',
    )
    parser.add_argument('action', nargs='?')
    parser.add_argument('tool', nargs='?')
    parser.add_argument('--version', default='')
    parser.add_argument('--project-dir', dest='project_dir', default='')
    parser.add_argument('--build-dir', dest='build_dir', default='')
    parser.add_argument('--cache-directory', dest='cache_directory', default='')
    parser.add_argument('--cache-minimization-enabled', dest='cache_minimization_enabled', nargs='?', const='on', default='')
    parser.add_argument('--cache-minimization-length', dest='cache_minimization_length', type=int, default=0)
    parser.add_argument('--available', action='store_true', dest='available')
    parser.add_argument('--yes', '-y', action='store_true', dest='yes')
    parser.add_argument('-h', '--help', action='store_true', dest='help')
    return parser
def parse_tools_args(args: list[str]) -> Namespace:
    parser = build_tools_parser()
    return parser.parse_args(args)


@dataclass
class ToolsCommandHandler:
    project_dir: str
    options: Namespace
    _manager: tool_manager.ToolManager | None = field(default=None, init=False, repr=False)

    @staticmethod
    def print_help() -> None:
        print('Usage: golem tools install <tool> [--version=<version>] [--cache-directory=<path>]')
        print('       golem tools uninstall <tool> [--cache-directory=<path>] [--yes]')
        print('       golem tools list [--available] [--cache-directory=<path>]')
        print('Manage installable external tools stored in the Golem tools cache.')
        print('')
        print('Subcommands:')
        print('  install      Install a supported tool into the tools cache')
        print('  uninstall    Remove a supported tool from the tools cache')
        print('  list         List installed tools, or supported tools with --available')
        print('')
        print('Options:')
        print('  --version=<version>                Tool version to install when supported')
        print('  --available                        List supported installable tools')
        print('  --yes, -y                          Do not prompt for confirmation before uninstalling')
        print('  --cache-directory=<path>           Select the base cache directory')
        print('  --cache-minimization-enabled[=<on|off>]  Store tools under short hashed flat paths;')
        print('                                           bare flag means on, omit for the automatic default (on)')
        print('  --cache-minimization-length=<n>    Number of hash characters for minimized tool names (default 8)')
        print('')
        print('Available tools:')
        for tool in tool_manager.ToolManager.list_available_tools():
            print('  {}'.format(tool.name))
            print('    Description: {}'.format(tool.description))
            print('    Repository: {}'.format(tool.repository))
            if tool.default_version:
                print('    Default version: {}'.format(tool.default_version))

    def make_tool_manager(self) -> tool_manager.ToolManager:
        if self._manager is None:
            cache_configuration = get_cache_configuration(settings.get_settings(
                options=self.options,
                build_dir=self.options.build_dir or None,
                project_dir=self.project_dir or None,
            ))
            self._manager = tool_manager.get_tool_manager(cache_configuration)

        return self._manager

    def print_available_tools(self) -> None:
        print('Supported installable tools:')
        for tool in tool_manager.ToolManager.list_available_tools():
            print(tool.name)
            print('  Description: {}'.format(tool.description))
            print('  Repository: {}'.format(tool.repository))
            if tool.default_version:
                print('  Default version: {}'.format(tool.default_version))

    def print_installed_tools(self, manager: tool_manager.ToolManager) -> None:
        installed_tools = manager.list_installed_tools()

        if not installed_tools:
            print('No installed tools found.')
            return

        print('Installed tools:')
        for tool in installed_tools:
            marker = ' (read-only)' if tool.is_read_only else ''
            print('{} {}  ({}{})'.format(
                tool.name, tool.version, tool.cache_root, marker))

    def handle_install(self, manager: tool_manager.ToolManager) -> int:
        try:
            tool = tool_manager.ToolManager.get_tool(
                self.options.tool, version=self.options.version)
            # Installing a tool is what this command is for, so it may reach the
            # remote, both to resolve the version and to fetch the source.
            with network.allowed():
                cached_tool = manager.make_available(tool)
        except ValueError as error:
            print('ERROR: {}'.format(error))
            self.print_help()
            return 1
        except RuntimeError as error:
            print('ERROR: {}'.format(error))
            return 1

        # A read-only location is served as it stands, so say so rather than
        # report an install that did not happen.
        if cached_tool.is_read_only:
            print('{} {} is served from the read-only cache location {}; nothing was installed'
                  .format(tool.name, tool.resolved_version, cached_tool.cache_root))
            return 0

        print('Installed {} {} in {}'.format(
            tool.name, tool.resolved_version, cached_tool.path))
        print('Selected cache location: {}'.format(cached_tool.cache_root))
        return 0

    def handle_uninstall(self, manager: tool_manager.ToolManager) -> int:
        tool_name = self.options.tool

        # Resolve the tool once, so what is shown, confirmed and deleted is the
        # same resource (like `golem cache remove`).
        try:
            tool = tool_manager.ToolManager.get_tool(tool_name)
            cached_tool = manager.resolve_cached_resource(tool, with_version_resolution=False)
        except ValueError as error:
            print('ERROR: {}'.format(error))
            self.print_help()
            return 1

        if not cached_tool.exists():
            print('{} is not installed in {}'.format(tool_name, cached_tool.cache_root))
            return 0

        if cached_tool.is_read_only:
            print('{} is in the read-only cache location {} and was not removed'.format(
                tool_name, cached_tool.cache_root))
            return 0

        print('Uninstall {} from {}'.format(tool_name, cached_tool.path))
        if not helpers.confirm('Proceed?', assume_yes=self.options.yes):
            print('Aborted. Nothing was uninstalled.')
            return 0

        manager.cache_manager.remove_resources([cached_tool])
        print('Uninstalled {} from {}'.format(tool_name, cached_tool.cache_root))
        return 0

    def handle(self, args: list[str]) -> int:
        if self.options.action == 'list':
            if self.options.tool is not None:
                print('ERROR: unsupported tools command: {}'.format(' '.join(args)))
                self.print_help()
                return 1
            if self.options.available:
                self.print_available_tools()
            else:
                self.print_installed_tools(manager=self.make_tool_manager())
            return 0

        if self.options.action == 'install' and self.options.tool is not None:
            return self.handle_install(manager=self.make_tool_manager())

        if self.options.action == 'uninstall' and self.options.tool is not None:
            return self.handle_uninstall(manager=self.make_tool_manager())

        if self.options.action in ('install', 'uninstall') and self.options.tool is None:
            print('ERROR: unsupported tools command: {}'.format(' '.join(args)))
            self.print_help()
            return 1

        print('ERROR: unsupported tools command: {}'.format(' '.join(args)))
        self.print_help()
        return 1


def handle_tools_command(project_dir: str, args: list[str]) -> int:
    try:
        options = parse_tools_args(args)
    except SystemExit:
        ToolsCommandHandler.print_help()
        return 1

    if options.help or options.action is None:
        ToolsCommandHandler.print_help()
        return 0

    return ToolsCommandHandler(project_dir=project_dir, options=options).handle(args)
