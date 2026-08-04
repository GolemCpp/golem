import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'src'
WAFLIB_SRC = ROOT / 'waflib' / 'waf'

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

if str(WAFLIB_SRC) not in sys.path:
    sys.path.insert(0, str(WAFLIB_SRC))

from golemcpp.golem import helpers  # noqa: E402
from golemcpp.golem.cache_configuration import CacheConfiguration  # noqa: E402
from golemcpp.golem.git_fetcher import GitFetcher  # noqa: E402
from golemcpp.golem.settings import get_settings  # noqa: E402


# The commit a stubbed fetch reports having landed on.
STUB_HEAD = 'cafebabecafebabecafebabecafebabecafebabe'


def stub_git_probes(monkeypatch, head=STUB_HEAD, holds_reference=True, has_submodules=True):
    '''
    What the fetch reads about a repository, stubbed for a test that drives the
    mechanism without one: the reference is present, HEAD reads back as a commit,
    and the resource declares submodules. None of these go through `run_git`, so
    none of them shows up in a recorded command sequence.
    '''
    monkeypatch.setattr(
        helpers, 'call_git', lambda args, cwd=None, **kwargs: 0 if holds_reference else 1)
    monkeypatch.setattr(
        helpers, 'check_git_output', lambda args, cwd=None, **kwargs: head + '\n')
    monkeypatch.setattr(GitFetcher, 'has_submodules', lambda self: has_submodules)


def absolute_path(*parts):
    '''
    An absolute path on every platform. A leading separator is enough on POSIX,
    but Windows also needs a drive: os.path.isabs('/opt/cache') is False there,
    so such a path would still be resolved against the current directory.
    '''
    return os.path.join(os.path.abspath(os.sep), *parts)


def default_setting(name):
    '''The built-in default of a setting, processed as a resolved value is.'''
    return get_settings().get_default(name)


def make_cache_configuration(*locations,
                             resolution_policy=default_setting('GOLEM_CACHE_RESOLUTION_POLICY'),
                             minimization_enabled=default_setting('GOLEM_CACHE_MINIMIZATION_ENABLED'),
                             minimization_length=default_setting('GOLEM_CACHE_MINIMIZATION_LENGTH'),
                             fetch_mode=default_setting('GOLEM_GIT_FETCH_MODE')):
    '''
    A CacheConfiguration for a test that only cares about one of its settings.
    The constructor requires them all, so the built-in defaults are filled here.
    '''
    return CacheConfiguration(
        locations=locations,
        resolution_policy=resolution_policy,
        minimization_enabled=minimization_enabled,
        minimization_length=minimization_length,
        fetch_mode=fetch_mode)