from dataclasses import dataclass

from golemcpp.golem.requested_source import RequestedSource
from golemcpp.golem.resolved_version import ResolvedVersion
from golemcpp.golem import version_resolver
from golemcpp.golem.version_resolver import VersionResolver


@dataclass
class Overlay:
    '''A configured overlay, at the version its location names.'''

    source: RequestedSource

    resolved: ResolvedVersion = ResolvedVersion()

    @property
    def name(self):
        return self.source.get_id()

    def requested_source(self):
        # What this overlay asks for, which its location said in full.
        return self.source

    def resolved_version(self):
        return self.resolved

    def resolve(self):
        resolved = VersionResolver.resolve_requested(
            self.requested_source(), self.resolved_version()
        )

        # The same one back: a copied directory, or an answer already in hand.
        if resolved is self.resolved:
            return self.resolved

        self.resolved = resolved

        version_resolver.report_resolution(self.name, self.source.version, resolved)

        return self.resolved
