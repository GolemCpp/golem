'''
What a fetch left behind.

A Source names the resolved request: which reference, and which revision that
reference pointed at when it was resolved. A Fetched says what the fetch then
landed on.

It travels beside the Source in a resource's manifest, and is serialized
the same way: the manifest holds the dict, this holds what it means.
'''

from dataclasses import dataclass

from golemcpp.golem.fetch_policy import FetchMode


@dataclass(frozen=True)
class Fetched:
    # The commit the fetch landed on. Empty when there was no fetch to speak of,
    # as a copied directory has no commit to name.
    head: str = ''
    # How much of the source was obtained. What a root already holds decides what
    # it takes to give it something else: see GitFetcher.migrate.
    mode: FetchMode = None

    def to_dict(self) -> dict:
        return {'head': self.head, 'mode': self.mode.value if self.mode else ''}

    @classmethod
    def from_dict(cls, data) -> 'Fetched':
        '''
        What a recorded fetch means. Anything absent reads as nothing recorded,
        which is what a manifest written before a field existed says.
        
        An unrecognised mode reads the same way, since a root fetched by a golem
        that knows modes this one does not is a root this one cannot reason about.
        '''
        if not data:
            return cls()

        try:
            mode = FetchMode(data['mode']) if data.get('mode') else None
        except ValueError:
            mode = None

        return cls(head=data.get('head', ''), mode=mode)

    @classmethod
    def from_manifest(cls, manifest) -> 'Fetched':
        '''What a resource's manifest says its root was left holding.'''
        return cls.from_dict(manifest.fetched if manifest else None)
