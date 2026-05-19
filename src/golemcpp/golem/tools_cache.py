import os

from golemcpp.golem import helpers
from golemcpp.golem import cache

def get_default_cache_directory() -> str:
    return os.path.join(cache.get_default_cache_directory_path(), 'tools')

def get_cache_directory(project_dir: str, options) -> str | None:
    cache_directory = getattr(options, 'tools_cache_directory', '')

    if not cache_directory:
        cache_directory = helpers.get_environ('GOLEM_TOOLS_CACHE_DIRECTORY')

    if not cache_directory:
        cache_directory = get_default_cache_directory()

    if not cache_directory:
        return None

    return helpers.make_absolute_path(cache_directory, project_dir)