'''
What a fetch left behind.

A Source says what was asked for. It can be a branch, a tag, a commit. A
Fetched says what that turned out to be.

It travels beside the Source in a resource's manifest, and is serialized
the same way: the manifest holds the dict, this holds what it means.
'''

from dataclasses import dataclass


@dataclass(frozen=True)
class Fetched:
    # The commit the fetch landed on. Empty when there was no fetch to speak of,
    # as a copied directory has no commit to name.
    head: str = ''

    def to_dict(self) -> dict:
        return {'head': self.head}

    @classmethod
    def from_dict(cls, data) -> 'Fetched':
        '''
        What a recorded fetch means. Anything absent reads as nothing recorded,
        which is what a manifest written before a field existed says.
        '''
        if not data:
            return cls()
        return cls(head=data.get('head', ''))

    @classmethod
    def from_manifest(cls, manifest) -> 'Fetched':
        '''What a resource's manifest says its root was left holding.'''
        return cls.from_dict(manifest.fetched if manifest else None)
