from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as package_version
from pathlib import Path

from golemcpp.golem.version import Version


def get_golem_version() -> str:
    try:
        return package_version('golemcpp')
    except PackageNotFoundError:
        return '0.0.0'


def handle_version_command() -> bool:
    print(f'Golem {get_golem_version()}')
    return True
