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
from golemcpp.golem.fetch_policy import FetchMode  # noqa: E402
from golemcpp.golem.git_fetcher import GitFetcher  # noqa: E402
from golemcpp.golem.settings import get_settings  # noqa: E402


# The commit a stubbed fetch reports having landed on.
STUB_HEAD = 'cafebabecafebabecafebabecafebabecafebabe'


def stub_git_probes(monkeypatch, head=STUB_HEAD, holds_revision=True,
                    has_submodules=True, mode=FetchMode.BLOBLESS,
                    branches=('main',), tags=()):
    '''
    What the fetch reads about a repository, stubbed for a test that drives the
    mechanism without one: HEAD reads back as a commit, the resource declares
    submodules, the root looks like it was fetched the way `mode` says, and the
    refs are the ones `branches` and `tags` name. None of these go through
    `run_git`, so none of them shows up in a recorded command sequence.

    `holds_revision=False` is a repository holding nothing that was asked for,
    whatever its refs would otherwise say.
    '''
    # What a root answers about its own shape, which is how a fetch tells what it
    # is refreshing rather than what a fresh one would be asked for.
    shape = {
        '--is-shallow-repository': mode == FetchMode.SHALLOW,
        'remote.origin.promisor': mode == FetchMode.BLOBLESS,
    }

    def read_git(params, cwd=None, **kwargs):
        for question, answer in shape.items():
            if question in params:
                return ('true' if answer else 'false') + '\n'
        return head + '\n'

    def try_git(params, cwd=None, **kwargs):
        if params[:3] != ['rev-parse', '--verify', '--quiet']:
            # Housekeeping, where nothing is made of the answer.
            return True
        if not holds_revision:
            return False

        # What the probe order asks for, one ref at a time. Anything else is a
        # commit, which a repository asked about its own revision holds.
        wanted = params[3].removesuffix('^{commit}')
        if wanted.startswith('refs/tags/'):
            return wanted[len('refs/tags/'):] in tags
        if wanted.startswith('refs/remotes/origin/'):
            return wanted[len('refs/remotes/origin/'):] in branches
        return True

    monkeypatch.setattr(helpers, 'try_git', try_git)
    monkeypatch.setattr(helpers, 'read_git', read_git)
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
                             fetch_mode=default_setting('GOLEM_GIT_FETCH_MODE'),
                             fetch_jobs=1):
    '''
    A CacheConfiguration for a test that only cares about one of its settings.
    The constructor requires them all, so the built-in defaults are filled here.

    `fetch_jobs` is the exception: its default counts the processors, and a
    recorded command sequence must not read differently on another machine.
    '''
    return CacheConfiguration(
        locations=locations,
        resolution_policy=resolution_policy,
        minimization_enabled=minimization_enabled,
        minimization_length=minimization_length,
        fetch_mode=fetch_mode,
        fetch_jobs=fetch_jobs)