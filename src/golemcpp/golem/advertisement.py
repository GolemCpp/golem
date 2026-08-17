'''
What a remote publishes, and how a version is looked up in it.

`git ls-remote --symref` answers the branch a repository defaults to and every
ref it has, in one round trip. An `Advertisement` is that answer read into a
value, so what a version names is decided from it rather than by asking again.

A name is looked up the way `gitrevisions` documents, therefore a tag beats a
branch of the same name because git says so, not because anything here prefers
one.
'''

import re
from dataclasses import dataclass, field


# What `ls-remote --symref` puts in front of the ref HEAD points at, and what
# git puts in front of a branch name and a tag name.
SYMREF_PREFIX = 'ref: '
BRANCH_PREFIX = 'refs/heads/'
TAG_PREFIX = 'refs/tags/'

# What git appends to a ref it peeled. The peeled entry names the commit a
# checkout lands on, which is what an annotated tag resolves to.
PEELED_SUFFIX = '^{}'

# Asking for the default branch by name, the way git spells it.
HEAD_VERSION = 'HEAD'

# What to ask a remote to advertise. Under protocol v2 these become server-side
# ref-prefix filters, so the answer leaves out everything else a repository may
# publish. E.g. `refs/pull/*` on a busy forge outnumbers branches and tags by far.
ADVERTISED_PREFIXES = (HEAD_VERSION, BRANCH_PREFIX + '*', TAG_PREFIX + '*')


@dataclass(frozen=True)
class Advertisement:
    '''What a remote publishes: the branch it defaults to, and every ref it has.'''

    # The default branch, read off the symref line and stripped of `refs/heads/`.
    head_reference: str = ''
    # Every advertised ref, by full name, against the commit it lands on.
    refs: dict = field(default_factory=dict)

    @classmethod
    def parse(cls, listing) -> 'Advertisement':
        '''
        Read what `ls-remote --symref` answered.

        A peeled entry overwrites the ref it belongs to, so an annotated tag
        holds the commit it points at rather than the tag object. A lightweight
        tag and a branch have no peeled entry, therefore their own value stands.
        '''
        head_reference = ''
        refs = {}
        for line in listing.splitlines():
            if line.startswith(SYMREF_PREFIX):
                head_reference = line[len(SYMREF_PREFIX):].split(
                    '\t')[0].removeprefix(BRANCH_PREFIX)
                continue

            revision, _, name = line.partition('\t')
            if not name:
                continue
            refs[name.removesuffix(PEELED_SUFFIX)] = revision

        return cls(head_reference=head_reference, refs=refs)

    def revision_of(self, version) -> str:
        '''
        The commit a version names, the way git looks a bare name up.

        `gitrevisions` gives the order, and a tag beating a branch of the same
        name follows from it rather than from a rule of ours. The remote-tracking
        steps git ends with have no equivalent here: a remote advertises none.
        '''
        for candidate in (version, 'refs/' + version,
                          TAG_PREFIX + version, BRANCH_PREFIX + version):
            if candidate in self.refs:
                return self.refs[candidate]

        return ''

    def tags(self, version_regex='') -> list:
        '''
        Every tag advertised, but without whatever `version_regex` rejects.
        '''
        names = [name.removeprefix(TAG_PREFIX)
                 for name in self.refs if name.startswith(TAG_PREFIX)]
        if not version_regex:
            return names

        pattern = re.compile(version_regex)
        return [name for name in names if pattern.match(name)]
