from dataclasses import dataclass

from golemcpp.golem import tool_registry
from golemcpp.golem.requested_source import RequestedSource
from golemcpp.golem.resolved_version import ResolvedVersion
from golemcpp.golem import version_resolver
from golemcpp.golem.version_resolver import VersionResolver


@dataclass
class Tool:
    '''An installable tool and the version of it a command asked for.'''

    definition: tool_registry.ToolDefinition

    version: str = ''
    resolved: ResolvedVersion = ResolvedVersion()

    def __post_init__(self):
        # A tool asked for without a version is asked for at the one its
        # definition names, so `version` always means what was requested.
        if not self.version:
            self.version = self.definition.default_version or ''

    @property
    def name(self):
        return self.definition.name

    def requested(self):
        # What this tool asks for.
        return RequestedSource.for_repository(
            self.definition.repository, version=self.version)

    def resolve(self):
        resolved = VersionResolver.resolve_requested(
            self.requested(), self.resolved)

        # The same one back: a copied directory, or an answer already in hand.
        if resolved is self.resolved:
            return self.resolved

        self.resolved = resolved

        version_resolver.report_resolution(self.name, self.version, resolved)

        return self.resolved
