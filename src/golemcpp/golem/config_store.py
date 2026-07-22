import json
import os
import sys

from golemcpp.golem import helpers


# Configuration scopes, mirroring `git config --global` / `--local`.
GLOBAL_SCOPE = 'global'
LOCAL_SCOPE = 'local'
SCOPES = (LOCAL_SCOPE, GLOBAL_SCOPE)

# Single source of truth for the settings Golem understands.
# Maps a dotted config key to the environment variable that overrides it and a
# short human-readable description. Keeping the mapping here lets both the
# `golem config` command and the settings consumers agree on the same keys.
KNOWN_SETTINGS = {
    'cache.directory': (
        'GOLEM_CACHE_DIRECTORY',
        'Directory used as the writable dependency cache.',
    ),
    'cache.additional-directories': (
        'GOLEM_ADDITIONAL_CACHE_DIRECTORIES',
        'Additional writable cache directories (pipe-separated PATH[=URL_REGEX]).',
    ),
    'cache.additional-read-only-directories': (
        'GOLEM_ADDITIONAL_READ_ONLY_CACHE_DIRECTORIES',
        'Additional read-only cache directories (pipe-separated PATH[=URL_REGEX]).',
    ),
    'cache.resolution-policy': (
        'GOLEM_CACHE_RESOLUTION_POLICY',
        'Cache resolution policy (strict or weak).',
    ),
    'recipes.repositories': (
        'GOLEM_RECIPES_REPOSITORIES',
        'Recipe repositories used to resolve dependencies.',
    ),
    'overrides.configuration': (
        'GOLEM_OVERRIDES_CONFIGURATION',
        'Path to an overrides configuration file.',
    ),
    'overrides.repository': (
        'GOLEM_OVERRIDES_REPOSITORY',
        'Repository providing an overrides configuration.',
    ),
}

# Reverse lookup used by resolve_environ to turn an env var back into its key.
ENV_TO_KEY = {env_name: key for key, (env_name, _) in KNOWN_SETTINGS.items()}


def is_known_key(key):
    return key in KNOWN_SETTINGS


def known_keys():
    return sorted(KNOWN_SETTINGS.keys())


def get_config_home():
    # Windows keeps per-user application data in %APPDATA%, unlike the
    # XDG-style location used on the other platforms.
    if sys.platform.startswith('win32'):
        appdata = helpers.get_environ('APPDATA')
        if appdata:
            return appdata

    config_home = helpers.get_environ('XDG_CONFIG_HOME')
    if config_home:
        return config_home
    home_directory = helpers.get_environ('HOME') or os.path.expanduser('~')
    return os.path.join(home_directory, '.config')


def get_global_config_path():
    return os.path.join(get_config_home(), 'golem', 'config.json')


def get_local_config_path(project_dir):
    return os.path.join(project_dir, '.golem', 'config.json')


def get_config_path(scope, project_dir):
    if scope == GLOBAL_SCOPE:
        return get_global_config_path()
    if scope == LOCAL_SCOPE:
        if not project_dir:
            return None
        return get_local_config_path(project_dir)
    raise ValueError('Unknown configuration scope: {}'.format(scope))


def read_config(path):
    if not path or not os.path.exists(path):
        return {}

    try:
        with open(path, 'r', encoding='utf-8') as fp:
            data = json.load(fp)
    except (ValueError, OSError):
        return {}

    if not isinstance(data, dict):
        return {}

    return data


def write_config(path, data):
    if data:
        directory = os.path.dirname(path)
        if directory:
            helpers.make_directory(directory)
        with open(path, 'w', encoding='utf-8') as fp:
            json.dump(data, fp, indent=4)
    elif os.path.exists(path):
        os.remove(path)


def get_scoped_value(key, scope, project_dir):
    path = get_config_path(scope=scope, project_dir=project_dir)
    return read_config(path).get(key)


def get_value(key, project_dir=None):
    if project_dir:
        local_value = get_scoped_value(key=key, scope=LOCAL_SCOPE, project_dir=project_dir)
        if local_value is not None:
            return local_value

    return get_scoped_value(key=key, scope=GLOBAL_SCOPE, project_dir=project_dir)


def set_value(key, value, scope, project_dir):
    path = get_config_path(scope=scope, project_dir=project_dir)
    if path is None:
        raise ValueError('A project directory is required to set a local configuration value')

    data = read_config(path)
    data[key] = value
    write_config(path, data)


def unset_value(key, scope, project_dir):
    path = get_config_path(scope=scope, project_dir=project_dir)
    if path is None:
        raise ValueError('A project directory is required to unset a local configuration value')

    data = read_config(path)
    if key not in data:
        return False

    del data[key]
    write_config(path, data)
    return True


def list_scoped(scope, project_dir):
    path = get_config_path(scope=scope, project_dir=project_dir)
    return read_config(path)


def list_merged(project_dir=None):
    merged = dict(list_scoped(scope=GLOBAL_SCOPE, project_dir=project_dir))
    if project_dir:
        merged.update(list_scoped(scope=LOCAL_SCOPE, project_dir=project_dir))
    return merged


def resolve_environ(env_name, project_dir=None):
    '''
    Resolves a setting following Golem's precedence: an explicit environment
    variable wins, otherwise the value is read from the local then global
    configuration store. Returns None when the setting is unset, so callers can
    keep their existing `if value:` fallthrough to built-in defaults.
    '''
    value = helpers.get_environ(env_name)
    if value:
        return value

    key = ENV_TO_KEY.get(env_name)
    if key is None:
        return None

    return get_value(key=key, project_dir=project_dir)
