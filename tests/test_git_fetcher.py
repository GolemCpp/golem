import pytest

from golemcpp.golem import helpers
from golemcpp.golem.fetch_policy import FetchPolicy
from golemcpp.golem.git_fetcher import GitFetcher
from golemcpp.golem.source import Source
from conftest import stub_git_probes
from conftest import STUB_HEAD


@pytest.fixture
def git_calls(monkeypatch):
    '''Every git invocation the fetcher makes, in order.'''
    calls = []
    monkeypatch.setattr(
        helpers, 'run_git',
        lambda args, cwd=None, quiet=False: calls.append(args))
    stub_git_probes(monkeypatch)
    return calls


@pytest.fixture
def quiet_calls(monkeypatch):
    '''Every git invocation with what it asked of stdout.'''
    calls = []
    monkeypatch.setattr(
        helpers, 'run_git',
        lambda args, cwd=None, quiet=False: calls.append((args, quiet)))
    stub_git_probes(monkeypatch)
    return calls


def make_fetcher(policy=None, reference='main'):
    return GitFetcher(
        '/cache/r',
        Source.for_repository('https://host/r.git', reference=reference),
        policy if policy is not None else FetchPolicy(reference='origin/' + reference))


# -- the git sequence a policy produces -------------------------------------


def test_the_default_policy_clones_and_tracks_the_branch(git_calls):
    make_fetcher().populate()

    assert git_calls == [
        ['clone', '--', 'https://host/r.git', '.'],
        ['reset', '--hard', 'origin/main'],
        ['submodule', 'update', '--init', '--recursive'],
    ]


def test_the_default_policy_refreshes_by_fetching_the_branch(git_calls):
    make_fetcher().refresh()

    assert git_calls == [
        ['clean', '-ffxd'],
        ['submodule', 'foreach', '--recursive', 'git', 'clean', '-ffxd'],
        ['fetch', '--prune', '--prune-tags', '--tags', 'origin'],
        ['reset', '--hard', 'origin/main'],
        ['submodule', 'foreach', '--recursive', 'git', 'reset', '--hard'],
        ['submodule', 'sync', '--recursive'],
        ['submodule', 'update', '--init', '--recursive'],
    ]


def test_a_checkout_lands_between_the_clone_and_the_reset(git_calls):
    make_fetcher(FetchPolicy(checkout='v3.12.0', reference='cafebabe')).populate()

    assert git_calls == [
        ['clone', '--', 'https://host/r.git', '.'],
        ['checkout', 'v3.12.0'],
        ['reset', '--hard', 'cafebabe'],
        ['submodule', 'update', '--init', '--recursive'],
    ]


def test_a_shallow_policy_fetches_only_the_requested_commit(git_calls):
    make_fetcher(
        FetchPolicy(shallow=True, checkout='v3.12.0', reference='cafebabe')).populate()

    assert git_calls == [
        ['init'],
        ['remote', 'add', 'origin', 'https://host/r.git'],
        ['fetch', '--depth=1', 'origin', 'cafebabe'],
        ['reset', '--hard', 'FETCH_HEAD'],
        ['submodule', 'update', '--init', '--recursive', '--depth=1'],
    ]


def test_a_pinned_policy_discards_local_changes_without_fetching(git_calls):
    # Every resource is cleaned and carries its submodules; a pin only says that
    # a refresh has nothing to fetch and lands back on the commit it holds. That
    # goes for the submodules too: --no-fetch is what keeps the whole refresh off
    # the network, so it stays allowed outside a resolve.
    make_fetcher(FetchPolicy(reference='', fetch_remote=False)).refresh()

    assert git_calls == [
        ['clean', '-ffxd'],
        ['submodule', 'foreach', '--recursive', 'git', 'clean', '-ffxd'],
        ['reset', '--hard'],
        ['submodule', 'foreach', '--recursive', 'git', 'reset', '--hard'],
        ['submodule', 'sync', '--recursive'],
        ['submodule', 'update', '--init', '--recursive', '--no-fetch'],
    ]
    assert not any(helpers.is_network_git_command(['git'] + args) for args in git_calls)


def test_a_resource_without_submodules_runs_no_submodule_command(monkeypatch, git_calls):
    # Most resources declare none, and a submodule command in a repository without
    # them is a process spent to do nothing.
    stub_git_probes(monkeypatch, has_submodules=False)

    make_fetcher().populate()
    make_fetcher().refresh()

    assert not any(args[0] == 'submodule' for args in git_calls)


# -- the reference has to be there before anything resets to it -------------


def test_a_missing_reference_is_fetched_before_the_reset(monkeypatch, git_calls):
    # The commit a resource names is not in this root -- a pin whose cache predates
    # the resolve that produced it. Ask for exactly that commit rather than dying at
    # the reset with git's own error.
    holds = iter([1, 0])
    monkeypatch.setattr(helpers, 'call_git', lambda args, cwd=None, **kwargs: next(holds))

    make_fetcher(FetchPolicy(reference='cafebabe', fetch_remote=False)).refresh()

    assert git_calls.index(['fetch', 'origin', 'cafebabe']) < \
        git_calls.index(['reset', '--hard', 'cafebabe'])


def test_a_reference_that_never_arrives_is_refused(monkeypatch, git_calls):
    # Still missing after asking for it: nothing to reset to, and the error says
    # what to do rather than what git saw.
    monkeypatch.setattr(helpers, 'call_git', lambda args, cwd=None, **kwargs: 1)

    with pytest.raises(RuntimeError, match='Run golem resolve first'):
        make_fetcher(FetchPolicy(reference='cafebabe', fetch_remote=False)).refresh()


def test_a_present_reference_is_reset_to_without_asking_for_it(git_calls):
    make_fetcher(FetchPolicy(reference='cafebabe', fetch_remote=False)).refresh()

    assert ['fetch', 'origin', 'cafebabe'] not in git_calls


# -- what the fetch reports back --------------------------------------------


def test_a_fetch_reports_the_commit_it_landed_on(git_calls):
    # What the source names is a branch as often as a commit; what the root holds
    # is always a commit, and that is what the manifest keeps.
    assert make_fetcher().populate().head == STUB_HEAD
    assert make_fetcher().refresh().head == STUB_HEAD


# -- only what reaches the remote speaks ------------------------------------


def test_only_what_reaches_the_remote_is_left_to_speak(quiet_calls):
    # Moving the working tree around is not worth reading; a command that has a
    # remote to wait on is.
    make_fetcher().populate()
    make_fetcher().refresh()

    assert [args for args, quiet in quiet_calls if not quiet] == [
        ['clone', '--', 'https://host/r.git', '.'],
        ['submodule', 'update', '--init', '--recursive'],
        ['fetch', '--prune', '--prune-tags', '--tags', 'origin'],
        ['submodule', 'update', '--init', '--recursive'],
    ]
    assert all(helpers.is_network_git_command(['git'] + args)
               for args, quiet in quiet_calls if not quiet)


def test_a_shallow_clone_only_speaks_while_it_fetches(quiet_calls):
    make_fetcher(FetchPolicy(shallow=True, reference='cafebabe')).populate()

    assert [args for args, quiet in quiet_calls if not quiet] == [
        ['fetch', '--depth=1', 'origin', 'cafebabe'],
        ['submodule', 'update', '--init', '--recursive', '--depth=1'],
    ]
