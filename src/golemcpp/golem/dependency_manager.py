from golemcpp.golem.cache_manager import get_cache_manager
from golemcpp.golem.resource import Resource
from golemcpp.golem.fetch_policy import FetchMode
from golemcpp.golem.fetch_policy import FetchPolicy
from golemcpp.golem.resource_manager import ResourceManager
from golemcpp.golem.resource_manifest import ResourceKind


class DependencyManager(ResourceManager):
    @staticmethod
    def resource_for(dep) -> Resource:
        source = DependencyManager.source_for(dep)
        return Resource(
            kind=ResourceKind.DEPENDENCY,
            cache_key=source.get_cache_key(),
            source=source)

    @staticmethod
    def source_for(dep):
        return dep.to_source()

    def policy_for(self, dep):
        # Pinned to a resolved commit, so there is nothing to fetch on a refresh
        # and the reset lands on the hash rather than on a moving branch.
        #
        # A dependency is the one resource that departs from the configured mode:
        # `shallow` is asked for in a golemfile, for a repository too heavy to
        # clone whole, and pays for it by having no history to describe from.
        return FetchPolicy(
            fetch_mode=FetchMode.SHALLOW if dep.shallow else self.fetch_mode,
            fetch_jobs=self.fetch_jobs,
            reference=dep.resolved.revision,
            fetch_remote=False)

    @staticmethod
    def resolve_version(dep):
        # The cache key is built from the resolved reference, so a dependency
        # located before this point would name a different resource.
        dep.resolve()
        return dep

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
