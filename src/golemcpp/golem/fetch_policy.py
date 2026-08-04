'''
What a resource kind asks of the fetch.

The policy is the kind's opinion. How deep to clone? What to land on? Whether
a refresh consults the remote?

It carries no mechanism. A Fetcher reads it and decides what that means for
the tool it drives.
'''

from dataclasses import dataclass


@dataclass(frozen=True)
class FetchPolicy:
    '''
    Describes the requirements for a resource kind to be fetched from its source.
    '''

    # Fetch only the requested commit instead of the whole history.
    # TODO: Can't use shallow by default because of git describe --tags required for golem repos
    shallow: bool = False
    # Checked out before the reset, when the ref to land on is not the one to
    # check out (a dependency resets to a hash under a version tag).
    checkout: str = ''
    # What to reset to. Empty resets to the current HEAD, which is what a
    # resource pinned to a commit wants.
    reference: str = ''
    # Whether refreshing consults the remote. A pinned resource cannot move, so
    # it has nothing to fetch.
    fetch_remote: bool = True
