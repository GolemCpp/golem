'''
Getting a source into a directory, whichever way that source is obtained.

A Fetcher is made for one source in one place: it holds the path it works in, the
source it works from and the policy it works under, and answers two questions:
`populate` for a directory that holds nothing yet? `refresh` for one that already
holds an earlier state of the same source? Both hand back a `Fetched` naming what
the directory ended up with.

Which Fetcher a source gets is the source's own business: `fetcher_for` reads its
type. A source obtained some other way; another version control system, an
archive to unpack, is a Fetcher beside these ones and one line here.
'''

import os

from golemcpp.golem.fetched import Fetched
from golemcpp.golem.source import SOURCE_TYPE_DIRECTORY


class Fetcher:
    '''The shape every way of obtaining a source answers to.'''

    def __init__(self, path, source, policy):
        self.path = path
        self.source = source
        self.policy = policy

    def populate(self) -> Fetched:
        '''Materialize the source freshly into a directory holding nothing yet.'''
        raise NotImplementedError

    def refresh(self) -> Fetched:
        '''
        Bring a directory already holding this source back to what the policy
        names, without obtaining it from scratch.
        '''
        raise NotImplementedError

    def migrate(self, recorded) -> bool:
        '''
        Whether a directory holding what `recorded` describes can be brought to
        what the policy now asks for, converting it in place if that takes
        anything. False means it has to be obtained again from scratch.

        Nothing to do by default: a way of obtaining a source that has only one
        way of doing it can never be holding the wrong one.
        '''
        return True

    @property
    def local_path(self):
        '''
        The local path the source lives at, refused here rather than deep inside a
        copy or a clone. None when the source is not local.
        '''
        local_path = self.source.get_local_path()
        if local_path is None:
            return None

        if not os.path.exists(local_path):
            raise RuntimeError(
                "Can't find local source directory: {}".format(local_path))
        if not os.path.isdir(local_path):
            raise RuntimeError(
                "Local source path is not a directory: {}".format(local_path))

        return local_path


def fetcher_for(path, source, policy) -> Fetcher:
    '''The Fetcher that knows how to obtain this source.'''
    # Imported here: every Fetcher reads this module, so none of them can be read
    # from it at import time.
    from golemcpp.golem.directory_fetcher import DirectoryFetcher
    from golemcpp.golem.git_fetcher import GitFetcher

    if source.type == SOURCE_TYPE_DIRECTORY:
        return DirectoryFetcher(path, source, policy)
    return GitFetcher(path, source, policy)
