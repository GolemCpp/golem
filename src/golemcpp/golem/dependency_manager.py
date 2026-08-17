from golemcpp.golem.cache_manager import get_cache_manager
from golemcpp.golem.fetch_policy import FetchMode
from golemcpp.golem.resource_manager import Pinning
from golemcpp.golem.resource_manager import ResourceManager
from golemcpp.golem.resource_manifest import ResourceKind


class DependencyManager(ResourceManager):
    '''
    Manages dependencies.

    Dependency are pinned in cache on the commit its version is resolved to.
    '''

    kind = ResourceKind.DEPENDENCY
    pinning = Pinning.REVISION

    def fetch_mode_for(self, dep):
        # Shallow mode: Can be enabled in the project file on a dependency to
        # fetch an extra light version of the repository, but there are drawbacks.
        # Usually longer to clone, and prevents from using `git describe` which
        # can be an issue if the project relies on it to know its own version.
        return FetchMode.SHALLOW if dep.shallow else self.fetch_mode

    def update_cached_resource(self, dep):
        '''(Re)resolve where this dependency lives in the caches.'''
        dep.cached_resource = self.resolve_cached_resource(dep)
        return dep.cached_resource

    def get_cached_resource(self, dep):
        '''
        Where a dependency lives in the caches, resolved on first use and kept on
        the dependency, so every path derived from it comes from one resolution.
        '''
        if dep.cached_resource is None:
            return self.update_cached_resource(dep)
        return dep.cached_resource


def get_dependency_manager(cache_configuration) -> DependencyManager:
    '''The single factory for the dependency resource manager.'''
    return DependencyManager(get_cache_manager(cache_configuration))
