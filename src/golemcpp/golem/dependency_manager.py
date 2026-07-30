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

    def resolve_cached_resource(self, dep):
        '''The dependency as a cached resource: which cache it belongs to, where it
        lives there and whether it is already cloned, resolved in one go.'''
        return self.cache_manager.resolve_cached_resource(self.resource_for(dep))

    def staged_install(self, cached_dep, populate) -> str:
        '''Clone the dependency's source into a staging dir, then atomically swap
        it into place with its manifest (see CacheManager.staged_install).'''
        return self.cache_manager.staged_install(cached_dep, populate)


def get_dependency_manager(cache_configuration) -> DependencyManager:
    '''The single factory for the dependency resource manager.'''
    return DependencyManager(get_cache_manager(cache_configuration))
