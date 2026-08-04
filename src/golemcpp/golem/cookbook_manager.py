from golemcpp.golem.cache_manager import get_cache_manager
from golemcpp.golem.cookbook import Cookbook
from golemcpp.golem.resource import Resource
from golemcpp.golem.resource_manager import ResourceManager
from golemcpp.golem.resource_manifest import ResourceKind


class CookbookManager(ResourceManager):
    '''
    A cookbook is read, never built, so it asks nothing of the fetch policy
    beyond tracking the branch it was configured with.
    '''

    @staticmethod
    def get_cookbook(source, version: str = '') -> Cookbook:
        return Cookbook(source=source, version=version)

    @staticmethod
    def resource_for(cookbook: Cookbook) -> Resource:
        source = CookbookManager.source_for(cookbook)
        return Resource(
            kind=ResourceKind.COOKBOOK,
            cache_key=source.get_cache_key(),
            source=source)

    @staticmethod
    def source_for(cookbook: Cookbook):
        return cookbook.to_source()

    @staticmethod
    def resolve_version(cookbook: Cookbook) -> Cookbook:
        cookbook.resolve()
        return cookbook


def get_cookbook_manager(cache_configuration) -> CookbookManager:
    '''The single factory for the cookbook resource manager.'''
    return CookbookManager(get_cache_manager(cache_configuration))
