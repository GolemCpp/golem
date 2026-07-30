'''
Per-kind resource managers.

Every resource kind (dependency, recipes/overrides repository, tool) is cached the
same way — resolve which configured cache it belongs to, compute its on-disk
location, read/write its manifest, install/remove it. That shared plumbing lives
once in `cache_manager.CacheManager`; each kind only knows how to turn its own
object into a `Resource` (via `resource_for`) and delegates every cache access to
the CacheManager it holds.
'''


class ResourceManager:
    '''A per-kind manager holds the shared CacheManager and delegates to it.'''

    def __init__(self, cache_manager):
        self.cache_manager = cache_manager

    @property
    def locations(self):
        return self.cache_manager.locations
