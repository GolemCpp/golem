from golemcpp.golem.cache_manager import get_cache_manager
from golemcpp.golem.resource import Resource
from golemcpp.golem.resource_manager import ResourceManager
from golemcpp.golem.resource_manifest import ResourceKind


class CookbookManager(ResourceManager):
    @staticmethod
    def resource_for(source) -> Resource:
        return Resource(
            kind=ResourceKind.COOKBOOK,
            cache_key=source.get_cache_key(),
            source=source)

    def resolve_cached_resource(self, source):
        '''The cookbook as a cached resource: which cache it belongs to, where it
        lives there and whether it is already fetched, resolved in one go.'''
        return self.cache_manager.resolve_cached_resource(self.resource_for(source))

    def staged_install(self, cached_cookbook, populate) -> str:
        '''Fetch the cookbook source into a staging dir, then atomically swap it
        into place with its manifest (see CacheManager.staged_install).'''
        return self.cache_manager.staged_install(cached_cookbook, populate)


def get_cookbook_manager(cache_configuration) -> CookbookManager:
    '''The single factory for the cookbook resource manager.'''
    return CookbookManager(get_cache_manager(cache_configuration))
