import re
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

# What separates the major fields of a cache key: `<source id>+<revision>`.
CACHE_KEY_SEPARATOR = '+'

# 40 hex is a SHA-1 object name, 64 a SHA-256 one. Git is migrating to SHA-256 and
# a repository names its objects in one format or the other, so both have to read
# as an object name here.
GIT_OBJECT_NAME = re.compile(r'^([0-9a-f]{40}|[0-9a-f]{64})$')

# What a directory name may hold, on the strictest of the platforms golem runs on.
# Lowercase only: NTFS and APFS are case-insensitive, so case cannot carry meaning
# there the way it does in a git ref name. Anything else becomes
# locator.SUBSTITUTE_MARKER, the same marker an id uses, so `release/1.2.3` reads
# as `release~1.2.3` rather than as a ref that was named `release-1.2.3`.
UNSAFE_IN_COMPONENT = re.compile(r'[^0-9a-z._-]')

# How much of a revision is kept for reading. What identifies it is the digest
# behind locator.DIGEST_SEPARATOR, the same convention an ambiguous id uses.
REVISION_SLUG_LENGTH = 40


def make_revision_component(revision):
    '''
    Makes a revision as one directory-name component.

    It can be a hash: In which case it is abbreviated to 8 characters.
    
    It can be a reference: In which case it can be abbreviated if it is too long.
    But it will also always be appended with a digest of it since the reference
    is processed to be safe for any filesystem, which can be lossy.
    '''
    if not revision:
        return ''

    if GIT_OBJECT_NAME.match(revision):
        return revision[:locator.DIGEST_LENGTH]

    slug = UNSAFE_IN_COMPONENT.sub(locator.SUBSTITUTE_MARKER, revision.lower())

    return '{}{}{}'.format(slug[:REVISION_SLUG_LENGTH], locator.DIGEST_SEPARATOR,
                           locator.digest(revision))


@dataclass(frozen=True)
class Source:
    '''
    Where a resource comes from, once resolving has said which version of it.

    A RequestedSource is what a configuration spells, a Source is what resolving
    one produces. Only this one can name a commit, and only this one identifies
    anything in a cache.
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
