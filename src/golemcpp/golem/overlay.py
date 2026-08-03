from dataclasses import dataclass, replace

from golemcpp.golem.source import Source


@dataclass
class Overlay:
    '''A configured overlay and the version of it a project asked for.'''

    source: Source
    
    version: str = ''
    resolved_version: str = ''
    resolved_hash: str = ''

    def __post_init__(self):
        # An overlay asked for without a version is asked for at the reference its
        # location names, so `version` always means what was requested.
        if not self.version:
            self.version = self.source.reference

    @property
    def name(self):
        return self.source.get_id()

    def to_source(self):
        # View the overlay as a Source to compute its identity the same way as every
        # other resource kind. Readable before resolution: an overlay names its
        # reference from the moment it is configured.
        return replace(self.source, reference=self.resolved_version or self.version)

    def resolve(self):
        # For now, an overlay follows the reference it was configured with.
        # 
        # The day an overlay may name a version, this is where 
        # VersionResolver.resolve goes, as the other kinds do.
        # 
        # Naming the hash after the reference is what VersionResolver itself 
        # falls back to when no tag matches.
        self.resolved_version = self.version
        self.resolved_hash = self.version
        return self.resolved_hash
