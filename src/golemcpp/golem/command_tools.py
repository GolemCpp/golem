from argparse import ArgumentParser
from argparse import Namespace
from dataclasses import dataclass
from dataclasses import field

from golemcpp.golem import tools_cache
from golemcpp.golem import tools_manager


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
    parser.add_argument('--tools-cache-directory', dest='tools_cache_directory', default='')
    parser.add_argument('--available', action='store_true', dest='available')
    parser.add_argument('-h', '--help', action='store_true', dest='help')
    return parser
def parse_tools_args(args: list[str]) -> Namespace:
    parser = build_tools_parser()
    return parser.parse_args(args)


@dataclass
class ToolsCommandHandler:
    project_dir: str
    options: Namespace
    _manager: tools_manager.ToolsManager | None = field(default=None, init=False, repr=False)

    @staticmethod
    def print_help() -> None:
        print('Usage: golem tools install <tool> [--version=<version>] [--tools-cache-directory=<path>]')
        print('       golem tools uninstall <tool> [--tools-cache-directory=<path>]')
        print('       golem tools list [--available] [--tools-cache-directory=<path>]')
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
        print('  --tools-cache-directory=<path>     Select the tools cache directory')
        print('')
        print('Available tools:')
        for tool in tools_manager.ToolsManager.list_available_tools():
            print('  {}'.format(tool.name))
            print('    Description: {}'.format(tool.description))
            print('    Repository: {}'.format(tool.repository_url))
            if tool.default_version:
                print('    Default version: {}'.format(tool.default_version))
        print('')
        print('Default tools cache directory: {}'.format(tools_cache.get_default_cache_directory()))

    def make_tools_manager(self) -> tools_manager.ToolsManager:
        if self._manager is None:
            self._manager = tools_manager.ToolsManager(
                cache_directory=tools_cache.get_cache_directory(
                    project_dir=self.project_dir,
                    options=self.options,
                ),
            )

        return self._manager

    def print_available_tools(self) -> None:
        print('Supported installable tools:')
        for tool in tools_manager.ToolsManager.list_available_tools():
            print(tool.name)
            print('  Description: {}'.format(tool.description))
            print('  Repository: {}'.format(tool.repository_url))
            if tool.default_version:
                print('  Default version: {}'.format(tool.default_version))

    def print_installed_tools(self, manager: tools_manager.ToolsManager) -> None:
        installed_tools = manager.list_installed_tools()

        if not installed_tools:
            print('No installed tools found.')
            return

        print('Installed tools:')
        for tool in installed_tools:
            print('{} {}'.format(tool.name, tool.version))

    def handle_install(self, manager: tools_manager.ToolsManager) -> int:
        try:
            install_info = manager.install_tool(tool_name=self.options.tool, version=self.options.version)
        except ValueError as error:
            print('ERROR: {}'.format(error))
            self.print_help()
            return 1
        except RuntimeError as error:
            print('ERROR: {}'.format(error))
            return 1

        print('Installed {} {} in {}'.format(install_info.name, install_info.version, install_info.cache_root))
        print('Selected tools cache directory: {}'.format(manager.cache_directory))
        return 0

    def handle_uninstall(self, manager: tools_manager.ToolsManager) -> int:
        try:
            uninstall_info = manager.uninstall_tool(tool_name=self.options.tool)
        except ValueError as error:
            print('ERROR: {}'.format(error))
            self.print_help()
            return 1

        if uninstall_info.removed:
            print('Uninstalled {} from {}'.format(uninstall_info.name, manager.cache_directory))
        else:
            print('{} is not installed in {}'.format(uninstall_info.name, manager.cache_directory))
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
                self.print_installed_tools(manager=self.make_tools_manager())
            return 0

        if self.options.action == 'install' and self.options.tool is not None:
            return self.handle_install(manager=self.make_tools_manager())

        if self.options.action == 'uninstall' and self.options.tool is not None:
            return self.handle_uninstall(manager=self.make_tools_manager())

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
