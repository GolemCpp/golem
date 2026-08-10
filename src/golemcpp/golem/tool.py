from dataclasses import dataclass, field

from golemcpp.golem import tool_registry
from golemcpp.golem.resolved_version import ResolvedVersion
from golemcpp.golem.source import Source
from golemcpp.golem.version_resolver import VersionResolver


@dataclass
class Tool:
    '''An installable tool and the version of it a command asked for.'''

    definition: tool_registry.ToolDefinition

    version: str = ''
    resolved: ResolvedVersion = field(default_factory=ResolvedVersion)

    def __post_init__(self):
        # A tool asked for without a version is asked for at the one its
        # definition names, so `version` always means what was requested.
        if not self.version:
            self.version = self.definition.default_version or ''

    @property
    def name(self):
        return self.definition.name

    def to_source(self):
        # View the tool as a Source to compute its identity the same way as every
        # other resource kind.
        return Source.for_repository(
            self.definition.repository, reference=self.resolved.reference)

    def resolve(self):
        # Resolves the requested version through VersionResolver
        # Don't do anything if already resolved

        if self.resolved:
            return self.resolved

        self.resolved = VersionResolver.resolve(
            self.definition.repository, self.version)

        return self.resolved
