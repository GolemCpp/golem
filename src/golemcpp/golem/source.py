import re
from dataclasses import dataclass, field

from golemcpp.golem import helpers
from golemcpp.golem import locator
from golemcpp.golem.locator import Locator


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
    # `locator` is where the source is, settled. `version` is what was asked of
    # it, empty when the location named nothing.
    locator: Locator = field(default_factory=Locator)
    reference: str = 'main'
    type: str = SOURCE_TYPE_GIT

    # The named constructors take either a Locator or the string spelling one;
    # the field itself takes only a Locator, so a raw string cannot reach it
    # without passing through here or through parsing.

    @classmethod
    def for_repository(cls, locator, reference='main'):
        return cls(locator=Locator(str(locator)), reference=reference,
                   type=SOURCE_TYPE_GIT)

    @classmethod
    def for_directory(cls, locator):
        return cls(locator=Locator(str(locator)), reference='',
                   type=SOURCE_TYPE_DIRECTORY)

    # -- identity serialization (recorded in a resource manifest) ---------

    def to_dict(self) -> dict:
        return {
            'type': self.type,
            'locator': str(self.locator),
            'reference': self.reference,
        }

    @classmethod
    def from_dict(cls, source: dict) -> 'Source':
        return cls(
            locator=Locator(helpers.first_non_empty_among_keys(source, 'locator')),
            reference=helpers.first_non_empty_among_keys(source, 'reference'),
            type=helpers.first_non_empty_among_keys(source, 'type') or SOURCE_TYPE_GIT)

    @classmethod
    def from_manifest(cls, manifest) -> 'Source':
        return cls.from_dict((manifest.source or {}) if manifest else {})

    @property
    def label(self) -> str:
        '''Human label, e.g. "<locator> <reference>"; empty when no locator.'''
        if not self.locator:
            return ''
        if self.reference:
            return '{} {}'.format(self.locator, self.reference)
        return str(self.locator)

    def get_cache_key(self):
        '''
        What identifies this source in a cache, as one directory name: which
        repository it is, and which revision of it.

        A source with no revision to name (e.g. a copied directory) is identified
        by the repository alone, rather than by a separator with nothing after it.
        '''
        component = make_revision_component(str(self.reference))

        if not component:
            return self.locator.get_id()

        return self.locator.get_id() + CACHE_KEY_SEPARATOR + component
