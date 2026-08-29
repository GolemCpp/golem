from golemcpp.golem.cache_manager import get_cache_manager
from golemcpp.golem.cookbook import Cookbook
from golemcpp.golem.resource_manager import ResourceManager
from golemcpp.golem.resource_manifest import ResourceKind


class CookbookManager(ResourceManager):
    '''
    Manages cookbooks, which are repositories containing recipes to help build
    a dependency that has no golemfile.

    Cookbooks are pinned in cache on the version asked. It means that when asking
    a branch on a cookbook, it will update in place to follow this branch at resolve
    time. Same if asking for a Node-like version, it will update in place on
    the same asked version. E.g. "^1.0.0" will follow 1.1.0, then 1.2.0, etc.
    '''

    kind = ResourceKind.COOKBOOK

    @staticmethod
    def get_cookbook(source) -> Cookbook:
        return Cookbook(source=source)


def get_cookbook_manager(cache_configuration) -> CookbookManager:
    '''The single factory for the cookbook resource manager.'''
    return CookbookManager(get_cache_manager(cache_configuration))
