from dataclasses import dataclass, field

from golemcpp.golem import helpers
from golemcpp.golem import locator
from golemcpp.golem.locator import Locator
from golemcpp.golem.resolved_version import ResolvedVersion


# A cached resource is obtained from a Source. Today a Source is one of two kinds:
# a git repository (cloned) or a local directory (copied as-is).
SOURCE_TYPE_GIT = 'git'
SOURCE_TYPE_DIRECTORY = 'directory'

# Every kind a location may claim. A new kind (an archive, an SVN checkout) is one
# entry here plus its branch in ResourceManager.populate.
SOURCE_KINDS = (SOURCE_TYPE_GIT, SOURCE_TYPE_DIRECTORY)

@dataclass(frozen=True)
class Source:
    '''
    Where a resource comes from, once resolving has said which version of it.

    A RequestedSource is what a configuration spells, a Source is what resolving
    one produces. Only this one can name a commit, and only this one has an
    identity in a cache.
    '''

    # `locator` is where the source is, settled. `resolved` is which version of
    # it resolving landed on, empty when there was nothing to resolve.
    locator: Locator = field(default_factory=Locator)
    resolved: ResolvedVersion = field(default_factory=ResolvedVersion)
    type: str = SOURCE_TYPE_GIT

    # The named constructors take either a Locator or the string spelling one;
    # the field itself takes only a Locator, so a raw string cannot reach it
    # without passing through here or through parsing.

    @classmethod
    def for_repository(cls, locator, resolved=None):
        return cls(locator=Locator(str(locator)),
                   resolved=resolved if resolved is not None else ResolvedVersion(),
                   type=SOURCE_TYPE_GIT)

    @classmethod
    def for_directory(cls, locator):
        # A copied directory is whatever it holds now: nothing resolved it.
        return cls(locator=Locator(str(locator)), resolved=ResolvedVersion(),
                   type=SOURCE_TYPE_DIRECTORY)

    # -- identity serialization (recorded in a resource manifest) ---------

    def to_dict(self) -> dict:
        return {
            'type': self.type,
            'locator': str(self.locator),
            'resolved': self.resolved.to_dict(),
        }

    @classmethod
    def from_dict(cls, source: dict) -> 'Source':
        return cls(
            locator=Locator(helpers.first_non_empty_among_keys(source, 'locator')),
            resolved=ResolvedVersion.from_dict(source.get('resolved') or {}),
            type=helpers.first_non_empty_among_keys(source, 'type') or SOURCE_TYPE_GIT)

    @classmethod
    def from_manifest(cls, manifest) -> 'Source':
        return cls.from_dict((manifest.source or {}) if manifest else {})

    @property
    def label(self) -> str:
        '''Human label, e.g. "<locator> <reference>"; empty when no locator.'''
        if not self.locator:
            return ''
        if self.resolved.reference:
            return '{} {}'.format(self.locator, self.resolved.reference)
        return str(self.locator)
