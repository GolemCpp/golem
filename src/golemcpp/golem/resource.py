from dataclasses import dataclass

from golemcpp.golem.resource_manifest import ResourceKind
from golemcpp.golem.source import Source


@dataclass(frozen=True)
class Resource:
    '''
    What the cache layer caches: the kind it belongs to, the key identifying it
    within that kind, and where its content comes from. Each per-kind manager
    turns its own object (a dependency, a repository source, a tool) into one.
    '''

    kind: ResourceKind
    cache_key: str
    source: Source

    @property
    def subdir(self) -> str:
        return self.kind.subdir

    @property
    def location(self):
        return self.source.location
