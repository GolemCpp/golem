import os

from golemcpp.golem import helpers
from golemcpp.golem import cache
from golemcpp.golem import config_store

def get_default_cache_directory() -> str:
    return os.path.join(cache.get_default_cache_directory_path(), cache.TOOLS_SUBDIR)

def get_cache_directory(project_dir: str, options) -> str | None:
    # Tools share the unified cache directory and live in its `tools/` subdir,
    # resolved the same way as the main dependency cache.
    base_directory = getattr(options, 'cache_directory', '')

    if not base_directory:
        base_directory = config_store.resolve_environ('GOLEM_CACHE_DIRECTORY', project_dir=project_dir)

    if not base_directory:
        base_directory = cache.get_default_cache_directory_path()

    if not base_directory:
        return None

    cache_directory = os.path.join(base_directory, cache.TOOLS_SUBDIR)

    return helpers.make_absolute_path(cache_directory, project_dir)