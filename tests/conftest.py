'''
What has to happen before any test module is imported.

Golem is not installed when the suite runs, so `src` and the vendored waflib go on
`sys.path` here, at the one place pytest is guaranteed to reach first.

Everything a test calls to build its inputs lives in `support.py`.
'''

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'src'
WAFLIB_SRC = ROOT / 'waflib' / 'waf'

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

if str(WAFLIB_SRC) not in sys.path:
    sys.path.insert(0, str(WAFLIB_SRC))

import pytest  # noqa: E402

from golemcpp.golem import network  # noqa: E402


@pytest.fixture
def resolving():
    '''
    Inside `golem resolve`, where reaching a remote is allowed. Resolving a
    version and installing a resource both happen there and nowhere else, so a
    test doing either says so the way the commands do.
    '''
    with network.allowed():
        yield
