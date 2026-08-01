from golemcpp.golem.cache_manager import get_cache_manager
from golemcpp.golem.resource import Resource
from golemcpp.golem.resource_manager import ResourceManager
from golemcpp.golem.resource_manifest import ResourceKind


class CookbookManager(ResourceManager):
    '''
    A cookbook is read, never built, so it asks nothing of the fetch mechanism
    beyond tracking the branch it was configured with.
    '''

    @staticmethod
    def resource_for(source) -> Resource:
        return Resource(
            kind=ResourceKind.COOKBOOK,
            cache_key=source.get_cache_key(),
            source=source)


def get_cookbook_manager(cache_configuration) -> CookbookManager:
    '''The single factory for the cookbook resource manager.'''
    return CookbookManager(get_cache_manager(cache_configuration))
