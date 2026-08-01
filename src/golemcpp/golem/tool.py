from dataclasses import dataclass

from golemcpp.golem import tool_registry
from golemcpp.golem.source import Source
from golemcpp.golem.version_resolver import VersionResolver


@dataclass
class Tool:
    '''An installable tool and the version of it a command asked for.'''

    definition: tool_registry.ToolDefinition
    version: str = ''
    resolved_version: str = ''
    resolved_hash: str = ''

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
            self.definition.repository, reference=self.resolved_version)

    def resolve(self):
        if self.resolved_hash:
            return self.resolved_hash

        self.resolved_version, self.resolved_hash = VersionResolver.resolve(
            self.definition.repository, self.version)

        return self.resolved_hash
