from golemcpp.golem.cache_manager import get_cache_manager
from golemcpp.golem.resource import Resource
from golemcpp.golem.resource_manager import ResourceManager
from golemcpp.golem.resource_manifest import ResourceKind


class DependencyManager(ResourceManager):
    @staticmethod
    def resource_for(dep) -> Resource:
        source = dep.to_source()
        return Resource(
            kind=ResourceKind.DEPENDENCY,
            cache_key=source.get_cache_key(),
            source=source)

    def resolve_cache_directory(self, dep):
        return self.cache_manager.resolve_cache_directory(self.resource_for(dep))

    def get_resource_location(self, cache_dir, dep) -> str:
        return self.cache_manager.get_resource_location(cache_dir, self.resource_for(dep))

    def staged_install(self, cache_dir, dep, populate) -> str:
        '''Clone the dependency's source into a staging dir, then atomically swap
        it into place with its manifest (see CacheManager.staged_install).'''
        return self.cache_manager.staged_install(
            cache_dir, self.resource_for(dep), populate)


def get_dependency_manager(cache_configuration) -> DependencyManager:
    '''The single factory for the dependency resource manager.'''
    return DependencyManager(get_cache_manager(cache_configuration))
