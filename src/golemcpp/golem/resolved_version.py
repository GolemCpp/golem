'''
What a requested version turned out to be.

A request is a semver spec, a branch, a tag, or a commit. What it resolves to is
two things at once, and both are needed:

- The reference it landed on, which is what gets reported back and read by a
  person.

- The revision that reference points at, which is what identifies the content.

A branch keeps its name while moving from one commit to the next, so neither
stands in for the other.

It travels beside the location in a resource's manifest, and is serialized the
same way: the manifest holds the dict, this holds what it means.
'''

from dataclasses import dataclass


@dataclass(frozen=True)
class ResolvedVersion:
    # The reference the request landed on: a tag, a branch, or the request itself
    # when it named neither.
    reference: str = ''
    # The commit that reference points at, or the request as written when nothing
    # here names a commit.
    # Though, a directory has no commit, and an unreachable remote leaves the request
    # standing for itself.
    revision: str = ''

    def __bool__(self) -> bool:
        '''Whether anything was resolved at all, which is what callers test.'''
        return bool(self.reference or self.revision)

    def to_dict(self) -> dict:
        return {'reference': self.reference, 'revision': self.revision}

    @classmethod
    def from_dict(cls, data) -> 'ResolvedVersion':
        '''
        What a recorded resolution means. Anything absent reads as nothing
        resolved, which is what a manifest written before a field existed says.
        '''
        if not data:
            return cls()

        return cls(reference=data.get('reference', ''),
                   revision=data.get('revision', ''))
