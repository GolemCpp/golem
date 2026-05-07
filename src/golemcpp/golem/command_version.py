from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as package_version
from pathlib import Path

from golemcpp.golem.version import Version


def get_golem_version() -> str:
    try:
        return package_version('golemcpp')
    except PackageNotFoundError:
        return Version(working_dir=Path(__file__).resolve().parents[3]).semver


def handle_version_command() -> bool:
    print(f'golem {get_golem_version()}')
    return True
