'''
One golem at a time in a resource root.

Two golem processes sharing a cache reach the same root: one cleans and resets a
tree the other is reading back, or both stage a fresh install into the same
directory. Nothing in a cache coordinates them, so the file system does.

The lock is the operating system's own, taken on an open file rather than written
into one. The kernel drops it when the process ends, however it ends, so there is
no stale lock to detect and none to break: a golem that crashed leaves an unlocked
file behind and the next one walks straight in.

Per root rather than per cache: two resources being installed at once are two
processes doing unrelated work, and there is nothing to protect them from.

The lock file itself is never removed. Removing it is what makes a lock file racy;
one process deleting what another has just opened. Leaving it costs an empty file
that nothing reads: the cache inventory only looks at directories.
'''

import os
import time
from contextlib import contextmanager

try:
    import fcntl
    msvcrt = None
except ImportError:  # Windows, which locks byte ranges instead.
    fcntl = None
    import msvcrt


# How long to wait for whoever holds a root before giving up on it. Long enough
# for a heavy repository to be cloned whole, short enough that a build says
# something rather than hanging until somebody wonders why.
WAIT_TIMEOUT_SECONDS = 30 * 60

# How often to ask again while waiting.
POLL_SECONDS = 0.5


def try_lock(handle) -> bool:
    '''Whether this process now holds the lock. False when somebody else does.'''
    try:
        if fcntl is not None:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        else:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        return True
    except OSError:
        return False


def unlock(handle) -> None:
    '''Released here rather than left to the process ending, which also would.'''
    if fcntl is not None:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    else:
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)


@contextmanager
def held(path, timeout=WAIT_TIMEOUT_SECONDS):
    '''
    The lock at `path`, held for the block.

    Waits for whoever has it, saying so once rather than looking hung, and gives
    up naming the path: waiting this long is a golem that will not finish rather
    than one that is slow.
    '''
    os.makedirs(os.path.dirname(path), exist_ok=True)

    with open(path, 'a+') as handle:
        give_up_at = time.monotonic() + timeout
        announced = False

        while not try_lock(handle):
            if not announced:
                print('Waiting for another golem to be done with {}'.format(path))
                announced = True

            if time.monotonic() >= give_up_at:
                raise RuntimeError(
                    'Gave up after {}s waiting for another golem to be done with '
                    '{}. Nothing was changed there.'.format(timeout, path))

            time.sleep(POLL_SECONDS)

        try:
            yield path
        finally:
            unlock(handle)
