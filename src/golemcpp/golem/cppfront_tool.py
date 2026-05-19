import os
import shutil
import sys
from dataclasses import dataclass

from golemcpp.golem import helpers

CPPFRONT_NAME = 'cppfront'
CPPFRONT_REPOSITORY_URL = 'https://github.com/hsutter/cppfront.git'
DEFAULT_CPPFRONT_VERSION = 'v0.8.1'
CPPFRONT_DESCRIPTION = 'Herb Sutter\'s compiler from an experimental C++ (cpp2) to today\'s C++ syntax (cpp).'

def get_cppfront_binary_name() -> str:
    if sys.platform.startswith('win32'):
        return 'cppfront.exe'
    return 'cppfront'

@dataclass(frozen=True)
class CppFrontCacheInfo:
    cache_root: str
    repository_path: str
    executable_path: str
    include_path: str

    @classmethod
    def from_cache_root(cls, cache_root: str):
        if not cache_root:
            raise ValueError('cache_root is required')

        repository_path = os.path.join(cache_root, 'repository')
        executable_path = os.path.join(cache_root, 'bin', get_cppfront_binary_name())
        include_path = os.path.join(repository_path, 'include')

        return cls(cache_root=cache_root,
                   repository_path=repository_path,
                   executable_path=executable_path,
                   include_path=include_path)

    def is_valid(self) -> bool:
        has_executable = os.path.isfile(self.executable_path)
        has_include = os.path.isdir(self.include_path)
        return has_executable and has_include

def find_cppfront_cache(cache_directory: str) -> CppFrontCacheInfo | None:
    if not cache_directory:
        return None

    cache_info = CppFrontCacheInfo.from_cache_root(os.path.join(cache_directory, CPPFRONT_NAME))

    if not cache_info.is_valid():
        return None

    return cache_info


def write_cppfront_golemfile(project_dir: str) -> str:
    golemfile_path = os.path.join(project_dir, 'golemfile.py')
    golemfile_content = """
def configure(project):
    task = project.program(name='cppfront',
                           source=['source'],
                           cxx_standard=20)
""".lstrip()

    with open(golemfile_path, 'w', encoding='utf-8') as fileout:
        fileout.write(golemfile_content)

    return golemfile_path


def build_cppfront_executable(repository_dir: str, executable_path: str) -> list[list[str]]:
    write_cppfront_golemfile(project_dir=repository_dir)

    build_dir = os.path.join(repository_dir, 'build-golem-cppfront')

    configure_command = helpers.make_golem_command('configure') + [
        '--project-dir=' + repository_dir,
        '--build-dir=' + build_dir,
        '--variant=release',
    ]
    helpers.run_task(configure_command, cwd=repository_dir)

    build_command = helpers.make_golem_command('build') + [
        '--project-dir=' + repository_dir,
        '--build-dir=' + build_dir,
    ]
    helpers.run_task(build_command, cwd=repository_dir)

    built_executable_path = os.path.join(build_dir, 'bin', get_cppfront_binary_name())
    if not os.path.isfile(built_executable_path):
        raise RuntimeError('Golem built cppfront but the executable was not found at {}'.format(built_executable_path))

    os.makedirs(os.path.dirname(executable_path), exist_ok=True)
    shutil.copy2(built_executable_path, executable_path)

    return [configure_command, build_command]


def install_cppfront(version: str, install_root: str) -> None:
    cache_info = CppFrontCacheInfo.from_cache_root(install_root)
    repository_dir = cache_info.repository_path
    executable_path = cache_info.executable_path

    helpers.run_git(['clone', CPPFRONT_REPOSITORY_URL, repository_dir], cwd=cache_info.cache_root)
    helpers.run_git(['checkout', version], cwd=repository_dir)
    build_cppfront_executable(repository_dir=repository_dir, executable_path=executable_path)

