import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'src'
WAFLIB_SRC = ROOT / 'waflib' / 'waf'

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

if str(WAFLIB_SRC) not in sys.path:
    sys.path.insert(0, str(WAFLIB_SRC))

from golemcpp.golem.cache_configuration import CacheConfiguration  # noqa: E402
from golemcpp.golem.settings import get_settings  # noqa: E402


def default_setting(name):
    '''The built-in default of a setting, processed as a resolved value is.'''
    return get_settings().get_default(name)


def make_cache_configuration(*locations,
                             resolution_policy=default_setting('GOLEM_CACHE_RESOLUTION_POLICY'),
                             minimization_enabled=default_setting('GOLEM_CACHE_MINIMIZATION_ENABLED'),
                             minimization_length=default_setting('GOLEM_CACHE_MINIMIZATION_LENGTH')):
    '''
    A CacheConfiguration for a test that only cares about one of its settings.
    The constructor requires them all, so the built-in defaults are filled here.
    '''
    return CacheConfiguration(
        locations=locations,
        resolution_policy=resolution_policy,
        minimization_enabled=minimization_enabled,
        minimization_length=minimization_length)