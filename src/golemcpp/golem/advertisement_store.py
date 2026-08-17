'''
What the remotes a resolve reached have advertised.

A resolution costs one `ls-remote`, and every node of a dependency tree resolves
the resources it needs for itself. The cookbook is the one they all reach.
Reading a remote once for a resolve rather than once for a node is what this is
for.

`golem resolve` recurses by spawning a nested one in each dependency's cache
root, therefore the store is a directory and the outermost resolve names it in
the environment. Every resolve under it reads that name and writes there for the
ones after it.

The outermost resolve empties the directory before anything reads it. That is
the whole invalidation rule, so a later `golem resolve` reaches every remote
again. Nothing removes the directory afterwards: what the last resolve read is
worth having when something has to be looked into.

Nothing here may fail a resolve. What cannot be read or written costs the round
trip it was there to save.
'''

import contextlib
import os

from golemcpp.golem import helpers
from golemcpp.golem import locator


# Where a resolve keeps them, under the build directory.
DIRECTORY_NAME = 'resolve'

# What names that directory to the resolves a resolve spawns. Set means a resolve
# is running above this one, which owns the directory. The path is read from here
# rather than worked out again: a nested resolve is handed a build directory of
# its own and would name a directory nobody else writes to.
DIRECTORY_VARIABLE = 'GOLEM_RESOLVE_DIRECTORY'

# How much of an id is kept for reading. An id spells a local repository out of
# its whole path, which has no bound, where a file name does. What identifies it
# past this is the digest behind locator.DIGEST_SEPARATOR, the same convention
# resource_manager.make_revision_component uses for a revision.
NAME_LENGTH = 40


@contextlib.contextmanager
def shared(directory):
    '''
    Open the store for a resolve and for every resolve it spawns.

    The outermost resolve is the one finding no directory named in the
    environment. It empties `directory` and names it for the others, which keep
    the one they were given so the whole tree writes to a single directory.
    '''
    if directory_in_use():
        yield
        return

    try:
        helpers.remove_tree(directory)
        os.makedirs(directory, exist_ok=True)
    except OSError:
        yield
        return

    os.environ[DIRECTORY_VARIABLE] = directory
    try:
        yield
    finally:
        os.environ.pop(DIRECTORY_VARIABLE, None)


def directory_in_use() -> str:
    '''The directory a resolve running above this one opened, or empty.'''
    return helpers.get_environ(DIRECTORY_VARIABLE) or ''


def path_for(url) -> str:
    '''
    Where what a remote advertised is kept, or empty when no resolve opened a
    store.

    Named by `locator.generate_id`, so every spelling of one repository reads one
    file, the way they already share one cache root. A url naming no repository
    answers empty: resolving it fails on its own, and it fails the same either
    way.
    '''
    directory = directory_in_use()
    if not directory:
        return ''

    try:
        name = locator.generate_id(url)
    except ValueError:
        return ''

    if not name:
        return ''

    if len(name) > NAME_LENGTH:
        name = name[:NAME_LENGTH] + locator.DIGEST_SEPARATOR + locator.digest(name)

    return os.path.join(directory, name)


def read(url) -> str:
    '''
    Read what a remote advertised, or empty when this resolve has not asked it.
    '''
    path = path_for(url)
    if not path:
        return ''

    try:
        with open(path, encoding='utf-8') as listing:
            return listing.read()
    except OSError:
        return ''


def write(url, listing):
    '''
    Keep what a remote advertised, for the resolves coming after this one.

    Written under a name of its own and renamed, so a reader never sees half a
    listing. Resolutions run one after another today, and the rename is what
    keeps that true if they stop.
    '''
    path = path_for(url)
    if not path:
        return

    pending = '{}.{}'.format(path, os.getpid())
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(pending, 'w', encoding='utf-8') as file:
            file.write(listing)
        os.replace(pending, path)
    except OSError:
        with contextlib.suppress(OSError):
            os.remove(pending)
