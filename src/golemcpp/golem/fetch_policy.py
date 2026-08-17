'''
What a resource kind asks of the fetch.

The policy is the kind's opinion. How much to obtain? What to land on? Whether
a refresh consults the remote?

It carries no mechanism. A Fetcher reads it and decides what that means for
the tool it drives.

The mode is the one part of it nobody has an opinion about: every kind fetches
the same way, because every kind has to be refreshable in place and some follow
a branch. Only a resource that says so for itself, like a heavy dependency asking
to be shallow, departs from it.
'''

import os
from dataclasses import dataclass
from enum import Enum

from golemcpp.golem import helpers


class FetchMode(Enum):
    # Everything the remote has. The only mode whose result is self-contained:
    # a cache populated this way keeps working on a machine that cannot reach
    # the remote at all.
    FULL = 'full'
    # Every commit and every tag, without the content of the files no revision
    # in use needs. `git describe --tags` still works, which is what lets this
    # be the default where `shallow` never could.
    BLOBLESS = 'blobless'
    # The requested commit and nothing else. The cheapest and the most fragile:
    # no history to describe from, and a refresh cannot simply move.
    SHALLOW = 'shallow'


# What a blobless fetch leaves behind: every commit and tree, no file content
# until something reads it.
BLOBLESS_FILTER = 'blob:none'

# Blobless needs three things at once, and the last one is the binding
# constraint: `clone --filter` (git 2.26), `submodule update --filter` (git
# 2.36), and `GIT_NO_LAZY_FETCH` (git 2.45) — without which a partial clone can
# reach a remote outside `golem resolve` and the promise that fetching is a
# resolve step stops being enforceable. Below this, the default is FULL.
BLOBLESS_MINIMUM_GIT_VERSION = (2, 45)


def supports_blobless() -> bool:
    '''
    Whether this git can be trusted with a partial clone. Not only whether it can
    make one: a git that cannot be told to refuse a lazy fetch cannot keep the
    network boundary this cache is built on.
    '''
    return helpers.git_version() >= BLOBLESS_MINIMUM_GIT_VERSION


def default_fetch_jobs() -> int:
    '''
    How many submodules to obtain at once when nobody says. One per processor,
    capped: past a point the remote is the bottleneck, not this machine.
    '''
    return min(os.cpu_count() or 1, 8)


def default_fetch_mode() -> 'FetchMode':
    '''
    What every kind fetches in unless told otherwise. Asked for explicitly, any
    mode is honoured; this is only what nobody asking gets.
    '''
    return FetchMode.BLOBLESS if supports_blobless() else FetchMode.FULL


# The functors the git.fetch-mode setting is read and written through
# (see setting_descriptor.SettingDescriptor).


def parse_fetch_mode(text, context):
    '''The mode a configured name stands for. Raises on an unknown name.'''
    return FetchMode(text)


def format_fetch_mode(fetch_mode, context):
    return fetch_mode.value


@dataclass(frozen=True)
class FetchPolicy:
    '''
    Describes the requirements for a resource kind to be fetched from its source.
    '''

    # How much of the source to obtain. Every kind fetches the same way unless a
    # resource asks for something else of its own.
    fetch_mode: FetchMode = FetchMode.BLOBLESS
    # How many submodules to obtain at once. What makes a superproject with a
    # couple of hundred of them bearable.
    fetch_jobs: int = 1
    # What to reset to. Empty resets to the current HEAD, which is what a
    # resource pinned to a commit wants.
    reference: str = ''
    # Whether refreshing consults the remote. A pinned resource cannot move, so
    # it has nothing to fetch.
    fetch_remote: bool = True
