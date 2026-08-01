from golemcpp.golem.cache_manager import get_cache_manager
from golemcpp.golem.resource import Resource
from golemcpp.golem.resource_manager import FetchPolicy
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

    @classmethod
    def policy_for(cls, dep):
        # Pinned to a resolved commit, so there is nothing to fetch on a refresh
        # and the reset lands on the hash rather than on a moving branch.
        return FetchPolicy(
            shallow=dep.shallow,
            checkout=dep.resolved_version,
            reference=dep.resolved_hash,
            submodules=True,
            clean=True,
            fetch_remote=False)

    @staticmethod
    def prepare(dep):
        # The policy is built from the resolved version and hash, so they have to
        # exist before the first fetch. A refresh already has them.
        dep.resolve()


def get_dependency_manager(cache_configuration) -> DependencyManager:
    '''The single factory for the dependency resource manager.'''
    return DependencyManager(get_cache_manager(cache_configuration))
