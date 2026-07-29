from golemcpp.golem import helpers


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

# Subdirectory inside a cached resource root that holds the fetched source content
# (a git clone or a copied directory).
SOURCE_DIRNAME = 'source'

# Every setting describing the cache. A dependency sub-build inherits all of
# them, so it reaches the same caches with the same layout as its parent.
CACHE_SETTINGS = (
    'GOLEM_CACHE_DIRECTORY',
    'GOLEM_ADDITIONAL_CACHE_DIRECTORIES',
    'GOLEM_ADDITIONAL_READ_ONLY_CACHE_DIRECTORIES',
    'GOLEM_CACHE_RESOLUTION_POLICY',
    'GOLEM_CACHE_MINIMIZATION_ENABLED',
    'GOLEM_CACHE_MINIMIZATION_LENGTH',
)


class CacheConfiguration:
    '''
    Cache settings shared by every class that touches the cache (the CacheManager, the per-kind 
    resource managers) so those settings live in one place instead of being passed loose.
    '''

    def __init__(self, locations, resolution_policy,
                 minimization_enabled, minimization_length):
        for name, value in (('locations', locations),
                            ('resolution_policy', resolution_policy),
                            ('minimization_enabled', minimization_enabled),
                            ('minimization_length', minimization_length)):
            if value is None:
                raise ValueError('CacheConfiguration requires {}'.format(name))

        self.locations = list(locations)
        self.resolution_policy = resolution_policy
        self.minimization_enabled = minimization_enabled
        self.minimization_length = minimization_length

    def __str__(self):
        return helpers.print_obj(self)


def resolve_cache_locations(settings):
    '''
    Every cache location a project uses, in the order they are searched.
    '''
    locations = [settings.get('GOLEM_CACHE_DIRECTORY')]
    locations += settings.get('GOLEM_ADDITIONAL_CACHE_DIRECTORIES')
    locations += settings.get('GOLEM_ADDITIONAL_READ_ONLY_CACHE_DIRECTORIES')

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


def get_cache_configuration(settings):
    '''
    The single factory for a fully-populated CacheConfiguration, so the waf build Context
    and the native `golem cache` / `golem tools` commands resolve the cache the
    same way.
    '''

    return CacheConfiguration(
        locations=resolve_cache_locations(settings),
        resolution_policy=settings.get('GOLEM_CACHE_RESOLUTION_POLICY'),
        minimization_enabled=settings.get('GOLEM_CACHE_MINIMIZATION_ENABLED'),
        minimization_length=settings.get('GOLEM_CACHE_MINIMIZATION_LENGTH'))