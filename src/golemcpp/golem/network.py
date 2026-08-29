'''
Which commands may reach a remote.

Fetching is a resolve step. Everywhere else reads what resolve put in the cache,
so going online means the cache was not ready and the command should say so
rather than fill it in on its own.

Denied by default. A command opens it for the work it is meant to do.
'''

import contextlib

_allowed = False


def is_allowed() -> bool:
    '''Whether reaching a remote is allowed where we are.'''
    return _allowed


@contextlib.contextmanager
def allowed():
    '''
    Opens network access for a block, restoring what it was on the way out.
    The scopes nest: a project script opens one inside `golem resolve`.
    '''
    global _allowed
    previous = _allowed
    _allowed = True
    try:
        yield
    finally:
        _allowed = previous
