import os

from golemcpp.golem import helpers
from golemcpp.golem import cache
from golemcpp.golem import config_store

def get_default_cache_directory() -> str:
    return cache.get_default_cache_directory_path()

def get_cache_directory(project_dir: str, options) -> str | None:
    # Tools share the unified cache directory and are resolved exactly like every
    # other resource kind: this returns the base cache root, and the tools live
    # under its `tools/` subdir (or flat when path minimization is enabled). The
    # `tools/` subdir and any minimization are applied by the resource-location
    # layer (see cache.make_resource_location), not here.
    base_directory = getattr(options, 'cache_directory', '')

    if not base_directory:
        base_directory = config_store.resolve_environ('GOLEM_CACHE_DIRECTORY', project_dir=project_dir)

    if not base_directory:
        base_directory = cache.get_default_cache_directory_path()

    if not base_directory:
        return None

    return helpers.make_absolute_path(base_directory, project_dir)