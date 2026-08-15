from dataclasses import dataclass

from golemcpp.golem import requested_source
from golemcpp.golem import source
from golemcpp.golem.requested_source import RequestedSource
from golemcpp.golem.resolved_version import ResolvedVersion


@dataclass
class Overlay:
    '''A configured overlay and the version of it a project asked for.'''

    source: RequestedSource
    
    version: str = ''
    resolved: ResolvedVersion = ResolvedVersion()

    def __post_init__(self):
        # An overlay asked for without a version is asked for at the version its
        # location names, and at the default branch when it names none either.
        if not self.version:
            self.version = self.source.version
        if not self.version and self.source.type == source.SOURCE_TYPE_GIT:
            self.version = requested_source.DEFAULT_GIT_VERSION

    @property
    def name(self):
        return self.source.get_id()

    def to_source(self):
        # View the overlay as a Source to compute its identity the same way as every
        # other resource kind. Readable before resolution: an overlay names its
        # reference from the moment it is configured.
        return self.source.resolved_at(self.resolved.reference or self.version)

    def resolve(self):
        # For now, an overlay follows the version it was configured with, without
        # asking a remote what that version resolves to.

        # This is where VersionResolver.resolve goes, as the other kinds do, the
        # day an overlay may name a version a remote has to be asked about.

        # Naming the revision after the reference is what VersionResolver itself
        # falls back to when no tag matches.
        self.resolved = ResolvedVersion(reference=self.version, revision=self.version)
        return self.resolved
