import hashlib
import json
import os
import re
from enum import Enum
from golemcpp.golem import config_store
from golemcpp.golem import helpers


# Default minimization mode for paths in cache
DEFAULT_MINIMIZATION_ENABLED = True

# Default number of hash characters used for a minimized (flat, hashed) cache
# resource name. Kept small to keep on-disk paths short (see path minimization),
# matching the 8-hex idiom used elsewhere for short ids.
DEFAULT_MINIMIZATION_LENGTH = 8


# Canonical subdirectories carved out of a cache directory, one per resource
# kind, so every consumer agrees on the on-disk layout.
DEPENDENCIES_SUBDIR = 'dependencies'
RECIPES_SUBDIR = 'recipes'
OVERRIDES_SUBDIR = 'overrides'
TOOLS_SUBDIR = 'tools'

# All resource-kind subdirectories, for consumers iterating a cache directory.
RESOURCE_SUBDIRS = (
    DEPENDENCIES_SUBDIR,
    RECIPES_SUBDIR,
    OVERRIDES_SUBDIR,
    TOOLS_SUBDIR,
)


def get_default_cache_directory_path():
    home_directory = helpers.get_environ('HOME') or os.path.expanduser('~')
    return os.path.join(home_directory, '.cache', 'golem')

class CacheDir:
    def __init__(self, location, is_read_only=False, regex=None):
        self._location = location
        self._is_read_only = is_read_only
        self._regex = regex

    def __str__(self):
        return self._location

    @property
    def location(self):
        return self._location

    @property
    def is_read_only(self):
        return self._is_read_only

    @property
    def regex(self):
        return self._regex


def default_cached_dir():
    return CacheDir(get_default_cache_directory_path())


# --- Path minimization -----------------------------------------------------
# Shared by every cache resource kind (dependencies, recipes, overrides, tools)
# so they all resolve on-disk locations identically. Minimization stores a
# resource flat at the cache root under a short hash of "<subdir>/<cache_key>"
# instead of the classic "<subdir>/<cache_key>" layout, to keep paths short
# enough for long-path-limited toolchains (e.g. Windows CL.exe).


def resolve_minimization_enabled(options=None, project_dir=None):
    '''
    Whether cache path minimization is enabled, resolved with precedence
    CLI option -> environment / config store -> built-in default (enabled).
    '''
    value = getattr(options, 'cache_minimization_enabled', '') if options else ''
    if not value:
        value = config_store.resolve_environ(
            'GOLEM_CACHE_MINIMIZATION_ENABLED', project_dir=project_dir)
    if not value:
        return DEFAULT_MINIMIZATION_ENABLED
    return str(value).strip().lower() not in ('off', 'false', '0', 'no')


def resolve_minimization_length(options=None, project_dir=None):
    '''
    Number of hash characters used for minimized resource names, resolved with
    precedence CLI option -> environment / config store -> built-in default.
    '''
    length = getattr(options, 'cache_minimization_length', 0) if options else 0
    if not length:
        value = config_store.resolve_environ(
            'GOLEM_CACHE_MINIMIZATION_LENGTH', project_dir=project_dir)
        if value:
            try:
                length = int(value)
            except ValueError:
                length = 0
    if length and length > 0:
        return length
    return DEFAULT_MINIMIZATION_LENGTH


def make_minimized_resource_name(subdir, cache_key, length):
    '''
    Short flat directory name for a minimized resource. Hashing
    "<subdir>/<cache_key>" keeps names unique across resource kinds once the
    per-kind subdirectory is dropped.
    '''
    digest = hashlib.sha1(
        '{}/{}'.format(subdir, cache_key).encode('utf-8')).hexdigest()
    return digest[:length]


def make_resource_location(cache_root, subdir, cache_key,
                           minimization_enabled, minimization_length):
    '''
    On-disk root of a cache resource. When minimization is disabled the classic
    "<cache_root>/<subdir>/<cache_key>" layout is used. When enabled, a
    pre-existing classic location keeps priority (so caches populated before
    minimization stay usable); otherwise the resource is stored flat at
    "<cache_root>/<hash>".
    '''
    normal_path = os.path.join(cache_root, subdir, cache_key)
    if not minimization_enabled:
        return normal_path
    if os.path.exists(normal_path):
        return normal_path
    return os.path.join(
        cache_root,
        make_minimized_resource_name(subdir, cache_key, minimization_length))


class CacheConf:
    def __init__(self):
        self.remote = ''
        self.locations = []

    def __str__(self):
        return helpers.print_obj(self)

class CacheResolutionPolicy(Enum):
    STRICT = "strict" # Only the first matching cache is considered to find the resource.
    WEAK = "weak" # Every valid matching cache is considered to find the resource.


class CachedResourceResolver:
    def __init__(self,
                 identifier,
                 cache_conf,
                 policy,
                 exists_in_cache=None):
        self._identifier = identifier
        self._cache_conf = cache_conf
        self._policy = policy
        self._exists_in_cache = exists_in_cache

    def _find_matching_caches(self, is_read_only, with_regex):
        found_caches = []

        for cache_dir in self._cache_conf.locations:
            if with_regex and not cache_dir.regex:
                continue
            if not with_regex and cache_dir.regex:
                continue
            if is_read_only and not cache_dir.is_read_only:
                continue
            if with_regex:
                pattern = re.compile(cache_dir.regex)
                if not pattern.match(self._identifier):
                    continue
            found_caches.append(cache_dir)

        return found_caches

    def _select_cache(self, candidates):
        if not candidates:
            return None

        if self._policy == CacheResolutionPolicy.STRICT:
            return candidates[0]

        if self._exists_in_cache is not None:
            for cache_dir in candidates:
                if self._exists_in_cache(cache_dir):
                    return cache_dir

        return None

    def resolve(self):
        read_only_caches_with_regex = self._find_matching_caches(
            is_read_only=True,
            with_regex=True)
        cache_dir = self._select_cache(read_only_caches_with_regex)
        if cache_dir is not None:
            return cache_dir

        read_only_caches_without_regex = self._find_matching_caches(
            is_read_only=True,
            with_regex=False)
        cache_dir = self._select_cache(read_only_caches_without_regex)
        if cache_dir is not None:
            return cache_dir

        writable_caches_with_regex = self._find_matching_caches(
            is_read_only=False,
            with_regex=True)
        cache_dir = self._select_cache(writable_caches_with_regex)
        if cache_dir is not None:
            return cache_dir

        writable_caches_without_regex = self._find_matching_caches(
            is_read_only=False,
            with_regex=False)
        cache_dir = self._select_cache(writable_caches_without_regex)
        if cache_dir is not None:
            return cache_dir

        if writable_caches_with_regex:
            return writable_caches_with_regex[0]
        if writable_caches_without_regex:
            return writable_caches_without_regex[0]

        raise RuntimeError("Can't find any writable cache location")


def parse_cache_entries(entries, is_read_only, base_dir):
    '''
    Parse a list of `PATH[=URL_REGEX]` cache entries into CacheDir objects,
    resolving relative paths against base_dir. Shared by the waf build context
    and the native `golem cache` command so both interpret cache options
    identically.
    '''
    dirs = []
    for entry in entries or []:
        if not entry:
            continue

        cache_path, _, cache_regex = entry.partition('=')
        if not cache_path:
            raise RuntimeError("Bad cache definition: {}".format(entry))

        if cache_regex:
            re.compile(cache_regex)
        else:
            cache_regex = None

        cache_path = helpers.make_absolute_path(cache_path, base_dir)

        dirs.append(CacheDir(location=cache_path,
                             is_read_only=is_read_only,
                             regex=cache_regex))

    return dirs


def get_persisted_configure_options(build_dir):
    '''
    Recover the option dict persisted by `golem configure` from the waf env
    cache (see Context.save_options). This lets native commands honour cache
    options (e.g. --additional-cache-directory) the project was configured with,
    without the user re-passing them. Returns None when nothing is persisted or
    the waf machinery is unavailable.
    '''
    if not build_dir:
        return None

    c4che_path = os.path.join(build_dir, 'golem', 'obj', 'c4che', 'main_cache.py')
    if not os.path.isfile(c4che_path):
        return None

    try:
        from waflib.ConfigSet import ConfigSet
    except ImportError:
        return None

    try:
        env = ConfigSet()
        env.load(c4che_path)
        options_json = getattr(env, 'OPTIONS', None)
        if not options_json:
            return None
        return json.loads(options_json)
    except Exception:
        return None


def _first_non_empty(*values):
    for value in values:
        if value:
            return value
    return None


def _resolve_additional_entries(cli, persisted, env_name, project_dir):
    if cli:
        return list(cli)
    if persisted:
        return list(persisted)
    env_string = config_store.resolve_environ(env_name, project_dir=project_dir)
    if env_string:
        return env_string.split('|')
    return []


def resolve_cache_locations(project_dir=None, build_dir=None, options=None):
    '''
    Resolve every cache location a project uses, mirroring
    Context.make_cache_dirs so the native `golem cache` command operates on
    exactly the caches a build would. Precedence for each setting:
    explicit `golem cache` CLI option -> persisted `golem configure` option ->
    environment / config store -> built-in default.
    '''
    persisted = get_persisted_configure_options(build_dir) or {}

    cli_cache_dir = getattr(options, 'cache_directory', '') if options else ''
    cli_additional = getattr(options, 'additional_cache_directory', None) if options else None
    cli_read_only = getattr(options, 'additional_read_only_cache_directory', None) if options else None

    locations = []

    cache_dir = _first_non_empty(
        cli_cache_dir,
        persisted.get('cache_directory'),
        config_store.resolve_environ('GOLEM_CACHE_DIRECTORY', project_dir=project_dir),
    ) or get_default_cache_directory_path()
    locations.append(CacheDir(location=helpers.make_absolute_path(cache_dir, project_dir),
                              is_read_only=False))

    additional = _resolve_additional_entries(
        cli=cli_additional,
        persisted=persisted.get('additional_cache_directory'),
        env_name='GOLEM_ADDITIONAL_CACHE_DIRECTORIES',
        project_dir=project_dir)
    locations += parse_cache_entries(additional, is_read_only=False, base_dir=project_dir)

    read_only = _resolve_additional_entries(
        cli=cli_read_only,
        persisted=persisted.get('additional_read_only_cache_directory'),
        env_name='GOLEM_ADDITIONAL_READ_ONLY_CACHE_DIRECTORIES',
        project_dir=project_dir)
    locations += parse_cache_entries(read_only, is_read_only=True, base_dir=project_dir)

    return _deduplicate_locations(locations)


def _deduplicate_locations(locations):
    seen = set()
    unique = []
    for cache_dir in locations:
        identity = (cache_dir.location, cache_dir.is_read_only, cache_dir.regex)
        if identity in seen:
            continue
        seen.add(identity)
        unique.append(cache_dir)
    return unique