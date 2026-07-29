'''
Per-kind resource managers.

Every resource kind (dependency, recipes/overrides repository, tool) is cached the
same way — resolve which configured cache it belongs to, compute its on-disk
location, read/write its manifest, install/remove it. That shared plumbing lives
once in `cache_manager.CacheManager`; each kind here only knows how to turn its own
object into a `ResourceSpec` (via `spec_for`) and delegates every cache access to
the CacheManager it holds.
'''

from dataclasses import dataclass

from golemcpp.golem import resource_manifest
from golemcpp.golem.cache_manager import get_cache_manager
from golemcpp.golem.resource_manifest import ResourceKind
from golemcpp.golem.source import Source


@dataclass(frozen=True)
class ResourceSpec:
    kind: ResourceKind
    cache_key: str
    source: Source

    @property
    def subdir(self) -> str:
        return self.kind.subdir

    @property
    def location(self):
        return self.source.location


class ResourceManager:
    '''A per-kind manager holds the shared CacheManager and delegates to it.'''

    def __init__(self, cache_manager):
        self.cache_manager = cache_manager

    @property
    def locations(self):
        return self.cache_manager.locations


class DependencyResourceManager(ResourceManager):
    @staticmethod
    def spec_for(dep) -> ResourceSpec:
        source = dep.to_source()
        return ResourceSpec(
            kind=ResourceKind.DEPENDENCY,
            cache_key=source.get_cache_key(),
            source=source)

    def resolve_cache_directory(self, dep):
        return self.cache_manager.resolve_cache_directory(self.spec_for(dep))

    def get_resource_location(self, cache_dir, dep) -> str:
        return self.cache_manager.get_resource_location(cache_dir, self.spec_for(dep))

    def staged_install(self, cache_dir, dep, populate) -> str:
        '''Clone the dependency's source into a staging dir, then atomically swap
        it into place with its manifest (see CacheManager.staged_install).'''
        return self.cache_manager.staged_install(
            cache_dir, self.spec_for(dep), populate)


class RepositoryResourceManager(ResourceManager):
    @staticmethod
    def spec_for(source, kind) -> ResourceSpec:
        return ResourceSpec(
            kind=kind,
            cache_key=source.get_cache_key(),
            source=source)

    def resolve_cache_directory(self, source, kind):
        return self.cache_manager.resolve_cache_directory(self.spec_for(source, kind))

    def get_resource_location(self, cache_dir, source, kind) -> str:
        return self.cache_manager.get_resource_location(
            cache_dir, self.spec_for(source, kind))

    def staged_install(self, cache_dir, source, kind, populate) -> str:
        '''Clone the repository source into a staging dir, then atomically swap it
        into place with its manifest (see CacheManager.staged_install).'''
        return self.cache_manager.staged_install(
            cache_dir, self.spec_for(source, kind), populate)


def get_dependency_manager(cache_configuration) -> DependencyResourceManager:
    '''The single factory for the dependency resource manager.'''
    return DependencyResourceManager(get_cache_manager(cache_configuration))


def get_repository_manager(cache_configuration) -> RepositoryResourceManager:
    '''The single factory for the recipes/overrides repository resource manager.'''
    return RepositoryResourceManager(get_cache_manager(cache_configuration))
