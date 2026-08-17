from dataclasses import dataclass
from dataclasses import replace

from golemcpp.golem import requested_source
from golemcpp.golem import source
from golemcpp.golem.requested_source import RequestedSource
from golemcpp.golem.resolved_version import ResolvedVersion
from golemcpp.golem import version_resolver
from golemcpp.golem.version_resolver import VersionResolver


@dataclass
class Cookbook:
    '''A configured cookbook of recipes and the version of it a project asked for.'''

    source: RequestedSource

    version: str = ''
    resolved: ResolvedVersion = ResolvedVersion()

    def __post_init__(self):
        # A cookbook asked for without a version is asked for at the version its
        # location names. Naming none either is a question for the resolver,
        # which answers it with the remote's default branch.
        if not self.version:
            self.version = self.source.version

    @property
    def name(self):
        return self.source.get_id()

    def requested(self):
        # What this cookbook asks for. We make sure that if the version was left
        # empty, we use the default version.
        return replace(self.source, version=self.version)

    def resolve(self):
        resolved = VersionResolver.resolve_requested(
            self.requested(), self.resolved)

        # The same one back: a copied directory, or an answer already in hand.
        if resolved is self.resolved:
            return self.resolved
        
        self.resolved = resolved
        
        version_resolver.report_resolution(self.name, self.version, resolved)

        return self.resolved
