import os
import shutil
import sys
from dataclasses import dataclass

from golemcpp.golem import cache_configuration
from golemcpp.golem import helpers

CPPFRONT_NAME = 'cppfront'
CPPFRONT_REPOSITORY = 'https://github.com/hsutter/cppfront.git'
DEFAULT_CPPFRONT_VERSION = 'v0.8.1'
CPPFRONT_DESCRIPTION = 'Herb Sutter\'s compiler from an experimental C++ (cpp2) to today\'s C++ syntax (cpp).'

def get_cppfront_binary_name() -> str:
    if sys.platform.startswith('win32'):
        return 'cppfront.exe'
    return 'cppfront'

@dataclass(frozen=True)
class CppFrontCacheInfo:
    resource_root: str
    source_path: str
    executable_path: str
    include_path: str

    @classmethod
    def from_tool_root(cls, resource_root: str):
        if not resource_root:
            raise ValueError('resource_root is required')

        source_path = os.path.join(resource_root, cache_configuration.SOURCE_DIRNAME)
        executable_path = os.path.join(resource_root, 'bin', get_cppfront_binary_name())
        include_path = os.path.join(source_path, 'include')

        return cls(resource_root=resource_root,
                   source_path=source_path,
                   executable_path=executable_path,
                   include_path=include_path)

    def is_valid(self) -> bool:
        has_executable = os.path.isfile(self.executable_path)
        has_include = os.path.isdir(self.include_path)
        return has_executable and has_include


def find_cppfront_cache_root(cached_tool_root: str) -> CppFrontCacheInfo | None:
    '''
    Locate an installed cppfront given the already-resolved tool cache root
    (which may be the classic tools/<name> location or a minimized flat path).
    '''
    if not cached_tool_root:
        return None

    cache_info = CppFrontCacheInfo.from_tool_root(cached_tool_root)

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


def build_cppfront(resource_root: str) -> None:
    '''cppfront built from the source already fetched and checked out under the root.'''
    cache_info = CppFrontCacheInfo.from_tool_root(resource_root)
    source_dir = cache_info.source_path
    build_dir = os.path.join(source_dir, 'build-golem-cppfront')

    # cppfront ships no golemfile, so it gets one, and Golem builds it like any
    # other project.
    write_cppfront_golemfile(project_dir=source_dir)

    helpers.run_task(helpers.make_golem_command('configure') + [
        '--project-dir=' + source_dir,
        '--build-dir=' + build_dir,
        '--variant=release',
    ], cwd=source_dir)

    helpers.run_task(helpers.make_golem_command('build') + [
        '--project-dir=' + source_dir,
        '--build-dir=' + build_dir,
    ], cwd=source_dir)

    built_executable_path = os.path.join(build_dir, 'bin', get_cppfront_binary_name())
    if not os.path.isfile(built_executable_path):
        raise RuntimeError('Golem built cppfront but the executable was not found at {}'.format(built_executable_path))

    os.makedirs(os.path.dirname(cache_info.executable_path), exist_ok=True)
    shutil.copy2(built_executable_path, cache_info.executable_path)

