from argparse import ArgumentParser
from argparse import Namespace
from dataclasses import dataclass

from golemcpp.golem import config_store
from golemcpp.golem import settings


def build_config_parser() -> ArgumentParser:
    parser = ArgumentParser(
        prog='golem config',
        add_help=False,
        description='Get and set global or project-local Golem settings.',
    )
    parser.add_argument('key', nargs='?')
    parser.add_argument('value', nargs='?')
    parser.add_argument('--global', action='store_true', dest='use_global')
    parser.add_argument('--local', action='store_true', dest='use_local')
    parser.add_argument('-l', '--list', action='store_true', dest='list')
    parser.add_argument('--unset', action='store_true', dest='unset')
    parser.add_argument('--project-dir', dest='project_dir', default='')
    parser.add_argument('--build-dir', dest='build_dir', default='')
    parser.add_argument('-h', '--help', action='store_true', dest='help')
    return parser


def parse_config_args(args: list[str]) -> Namespace:
    parser = build_config_parser()
    return parser.parse_args(args)


@dataclass
class ConfigCommandHandler:
    project_dir: str
    options: Namespace

    @staticmethod
    def print_help() -> None:
        print('Usage: golem config <key> [<value>] [--global | --local]')
        print('       golem config --unset <key> [--global | --local]')
        print('       golem config --list [--global | --local]')
        print('Get and set global or project-local Golem settings.')
        print('')
        print('Scopes:')
        print('  --local      Project configuration in <project>/.golem/config.json (default)')
        print('  --global     User configuration in {}'.format(config_store.get_global_config_path()))
        print('')
        print('Actions:')
        print('  config <key>            Print the resolved value (local overrides global)')
        print('  config <key> <value>    Set the value in the selected scope')
        print('  config --unset <key>    Remove the value from the selected scope')
        print('  config --list           List settings (merged, or per scope)')
        print('')
        print('Settings are resolved as:')
        print('  1. Command-line option')
        print('  2. Option persisted by golem configure (build directory)')
        print('  3. Environment variable')
        print('  4. Local configuration')
        print('  5. Global configuration')
        print('  6. Built-in default')
        print('')
        print('Available settings:')
        for setting in settings.known_settings():
            print('  {}'.format(setting.key))
            print('    {}'.format(setting.description))
            print('    Environment variable: {}'.format(setting.env_name))
            if setting.option_flag:
                print('    Command-line option: {}'.format(setting.option_flag))
            default = setting.format_value(setting.get_default())
            if default:
                print('    Default: {}'.format(default))

    def selected_scope(self) -> str:
        if self.options.use_global:
            return config_store.GLOBAL_SCOPE
        return config_store.LOCAL_SCOPE

    def validate_key(self, key: str) -> bool:
        if settings.is_known_key(key):
            return True

        print('ERROR: unknown configuration key: {}'.format(key))
        print('Valid keys are:')
        for known in settings.known_keys():
            print('  {}'.format(known))
        return False

    def handle_list(self) -> int:
        if self.options.use_global:
            values = config_store.list_scoped(scope=config_store.GLOBAL_SCOPE, project_dir=self.project_dir)
        elif self.options.use_local:
            values = config_store.list_scoped(scope=config_store.LOCAL_SCOPE, project_dir=self.project_dir)
        else:
            values = config_store.list_merged(project_dir=self.project_dir)

        for key in sorted(values.keys()):
            print('{}={}'.format(key, values[key]))
        return 0

    def handle_unset(self) -> int:
        if not self.options.key:
            print('ERROR: --unset requires a key')
            self.print_help()
            return 1

        if not self.validate_key(self.options.key):
            return 1

        try:
            removed = config_store.unset_value(
                key=self.options.key,
                scope=self.selected_scope(),
                project_dir=self.project_dir,
            )
        except ValueError as error:
            print('ERROR: {}'.format(error))
            return 1

        if not removed:
            print('{} is not set in the {} configuration'.format(self.options.key, self.selected_scope()))
        return 0

    def handle_set(self) -> int:
        if not self.validate_key(self.options.key):
            return 1

        try:
            config_store.set_value(
                key=self.options.key,
                value=self.options.value,
                scope=self.selected_scope(),
                project_dir=self.project_dir,
            )
        except ValueError as error:
            print('ERROR: {}'.format(error))
            return 1

        return 0

    def handle_get(self) -> int:
        if not self.validate_key(self.options.key):
            return 1

        if self.options.use_global:
            value = config_store.get_scoped_value(
                key=self.options.key, scope=config_store.GLOBAL_SCOPE, project_dir=self.project_dir)
        elif self.options.use_local:
            value = config_store.get_scoped_value(
                key=self.options.key, scope=config_store.LOCAL_SCOPE, project_dir=self.project_dir)
        else:
            value = config_store.get_value(key=self.options.key, project_dir=self.project_dir)

        if value is None:
            return 1

        print(value)
        return 0

    def handle(self) -> int:
        if self.options.use_global and self.options.use_local:
            print('ERROR: --global and --local cannot be combined')
            self.print_help()
            return 1

        if self.options.list:
            return self.handle_list()

        if self.options.unset:
            return self.handle_unset()

        if not self.options.key:
            self.print_help()
            return 0

        if self.options.value is not None:
            return self.handle_set()

        return self.handle_get()


def handle_config_command(project_dir: str, args: list[str]) -> int:
    try:
        options = parse_config_args(args)
    except SystemExit:
        ConfigCommandHandler.print_help()
        return 1

    if options.help:
        ConfigCommandHandler.print_help()
        return 0

    return ConfigCommandHandler(project_dir=project_dir, options=options).handle()
