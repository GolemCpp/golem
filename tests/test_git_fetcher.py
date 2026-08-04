import pytest

from golemcpp.golem import helpers
from golemcpp.golem.fetch_policy import FetchMode
from golemcpp.golem.fetch_policy import FetchPolicy
from golemcpp.golem.fetched import Fetched
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


@pytest.fixture
def make_fetcher(tmp_path):
    '''
    A fetcher rooted where the test may write: populate() creates its root, so a
    hard-coded location would be a real directory outside the temporary tree.
    '''
    def make(policy=None, reference='main'):
        return GitFetcher(
            str(tmp_path / 'r'),
            Source.for_repository('https://host/r.git', reference=reference),
            policy if policy is not None else FetchPolicy(reference='origin/' + reference))

    return make


# -- the git sequence a policy produces -------------------------------------


def test_the_default_policy_clones_and_tracks_the_branch(git_calls, make_fetcher):
    make_fetcher().populate()

    assert git_calls == [
        ['clone', '--filter=blob:none', '--', 'https://host/r.git', '.'],
        ['reset', '--hard', 'origin/main'],
        ['submodule', 'update', '--init', '--recursive', '--filter=blob:none'],
    ]


def test_the_default_policy_refreshes_by_fetching_the_branch(git_calls, make_fetcher):
    make_fetcher().refresh()

    assert git_calls == [
        ['clean', '-ffxd'],
        ['submodule', 'foreach', '--recursive', 'git', 'clean', '-ffxd'],
        ['fetch', '--prune', '--prune-tags', '--tags', 'origin'],
        ['reset', '--hard', 'origin/main'],
        ['submodule', 'foreach', '--recursive', 'git', 'reset', '--hard'],
        ['submodule', 'sync', '--recursive'],
        ['submodule', 'update', '--init', '--recursive', '--filter=blob:none'],
    ]


def test_a_checkout_gives_way_to_the_reset_that_follows_it(git_calls, make_fetcher):
    # Both land on the same commit, and materializing the tree twice is two round
    # trips for the file content under a partial clone.
    make_fetcher(FetchPolicy(checkout='v3.12.0', reference='cafebabe')).populate()

    assert git_calls == [
        ['clone', '--filter=blob:none', '--', 'https://host/r.git', '.'],
        ['reset', '--hard', 'cafebabe'],
        ['submodule', 'update', '--init', '--recursive', '--filter=blob:none'],
    ]


def test_a_checkout_is_kept_when_there_is_nothing_to_reset_onto(git_calls, make_fetcher):
    make_fetcher(FetchPolicy(checkout='v3.12.0', reference='')).populate()

    assert ['checkout', 'v3.12.0'] in git_calls


def test_a_shallow_policy_fetches_only_the_requested_commit(git_calls, make_fetcher):
    make_fetcher(
        FetchPolicy(fetch_mode=FetchMode.SHALLOW, checkout='v3.12.0', reference='cafebabe')).populate()

    assert git_calls == [
        ['init'],
        ['remote', 'add', 'origin', 'https://host/r.git'],
        ['fetch', '--depth=1', 'origin', 'cafebabe'],
        ['reset', '--hard', 'FETCH_HEAD'],
        ['submodule', 'update', '--init', '--recursive', '--depth=1'],
    ]


def test_a_pinned_policy_discards_local_changes_without_fetching(git_calls, make_fetcher):
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
        ['submodule', 'update', '--init', '--recursive', '--filter=blob:none', '--no-fetch'],
    ]
    assert not any(helpers.is_network_git_command(['git'] + args) for args in git_calls)


def test_a_resource_without_submodules_runs_no_submodule_command(monkeypatch, git_calls, make_fetcher):
    # Most resources declare none, and a submodule command in a repository without
    # them is a process spent to do nothing.
    stub_git_probes(monkeypatch, has_submodules=False)

    make_fetcher().populate()
    make_fetcher().refresh()

    assert not any(args[0] == 'submodule' for args in git_calls)


# -- the reference has to be there before anything resets to it -------------


def test_a_missing_reference_is_fetched_before_the_reset(monkeypatch, git_calls, make_fetcher):
    # The commit a resource names is not in this root -- a pin whose cache predates
    # the resolve that produced it. Ask for exactly that commit rather than dying at
    # the reset with git's own error.
    holds = iter([1, 0])
    monkeypatch.setattr(helpers, 'call_git', lambda args, cwd=None, **kwargs: next(holds))

    make_fetcher(FetchPolicy(reference='cafebabe', fetch_remote=False)).refresh()

    assert git_calls.index(['fetch', 'origin', 'cafebabe']) < \
        git_calls.index(['reset', '--hard', 'cafebabe'])


def test_a_reference_that_never_arrives_is_refused(monkeypatch, git_calls, make_fetcher):
    # Still missing after asking for it: nothing to reset to, and the error says
    # what to do rather than what git saw.
    monkeypatch.setattr(helpers, 'call_git', lambda args, cwd=None, **kwargs: 1)

    with pytest.raises(RuntimeError, match='Run golem resolve first'):
        make_fetcher(FetchPolicy(reference='cafebabe', fetch_remote=False)).refresh()


def test_a_present_reference_is_reset_to_without_asking_for_it(git_calls, make_fetcher):
    make_fetcher(FetchPolicy(reference='cafebabe', fetch_remote=False)).refresh()

    assert ['fetch', 'origin', 'cafebabe'] not in git_calls


# -- what the fetch reports back --------------------------------------------


def test_a_fetch_reports_the_commit_it_landed_on(git_calls, make_fetcher):
    # What the source names is a branch as often as a commit; what the root holds
    # is always a commit, and that is what the manifest keeps.
    assert make_fetcher().populate().head == STUB_HEAD
    assert make_fetcher().refresh().head == STUB_HEAD


# -- only what reaches the remote speaks ------------------------------------


def test_only_what_reaches_the_remote_is_left_to_speak(quiet_calls, make_fetcher):
    # Moving the working tree around is not worth reading; a command that has a
    # remote to wait on is.
    make_fetcher().populate()
    make_fetcher().refresh()

    assert [args for args, quiet in quiet_calls if not quiet] == [
        ['clone', '--filter=blob:none', '--', 'https://host/r.git', '.'],
        ['submodule', 'update', '--init', '--recursive', '--filter=blob:none'],
        ['fetch', '--prune', '--prune-tags', '--tags', 'origin'],
        ['submodule', 'update', '--init', '--recursive', '--filter=blob:none'],
    ]
    assert all(helpers.is_network_git_command(['git'] + args)
               for args, quiet in quiet_calls if not quiet)


def test_a_shallow_clone_only_speaks_while_it_fetches(quiet_calls, make_fetcher):
    make_fetcher(FetchPolicy(fetch_mode=FetchMode.SHALLOW, reference='cafebabe')).populate()

    assert [args for args, quiet in quiet_calls if not quiet] == [
        ['fetch', '--depth=1', 'origin', 'cafebabe'],
        ['submodule', 'update', '--init', '--recursive', '--depth=1'],
    ]


# -- changing what a root already holds -------------------------------------


def migrating(make_fetcher, git_calls, recorded, target):
    fetcher = make_fetcher(FetchPolicy(fetch_mode=target, reference='origin/main'))
    return fetcher.migrate(Fetched(head=STUB_HEAD, mode=recorded)), git_calls


def test_a_root_already_in_the_asked_mode_is_left_alone(git_calls, make_fetcher):
    migrated, calls = migrating(make_fetcher, git_calls, FetchMode.BLOBLESS, FetchMode.BLOBLESS)

    assert migrated == Fetched(head=STUB_HEAD, mode=FetchMode.BLOBLESS)
    assert calls == []


def test_a_full_root_becomes_blobless_without_transferring_anything(git_calls, make_fetcher):
    # The objects are already here. This only says that later fetches may leave
    # file content behind.
    migrated, calls = migrating(make_fetcher, git_calls, FetchMode.FULL, FetchMode.BLOBLESS)

    # Converted, and still on the commit it was on: a migration changes how much
    # of a history a root holds, never where it stands in it.
    assert migrated == Fetched(head=STUB_HEAD, mode=FetchMode.BLOBLESS)
    assert calls == [
        ['config', 'remote.origin.promisor', 'true'],
        ['config', 'remote.origin.partialclonefilter', 'blob:none'],
    ]
    assert not any(helpers.is_network_git_command(['git'] + args) for args in calls)


def test_a_blobless_root_becomes_full_by_asking_for_what_it_left_out(git_calls, make_fetcher):
    migrated, calls = migrating(make_fetcher, git_calls, FetchMode.BLOBLESS, FetchMode.FULL)

    assert migrated == Fetched(head=STUB_HEAD, mode=FetchMode.FULL)
    assert calls == [['fetch', '--refetch', 'origin']]


def test_a_shallow_root_is_deepened_before_anything_else(git_calls, make_fetcher):
    migrated, calls = migrating(make_fetcher, git_calls, FetchMode.SHALLOW, FetchMode.BLOBLESS)

    assert migrated == Fetched(head=STUB_HEAD, mode=FetchMode.BLOBLESS)
    assert calls[0] == ['fetch', '--unshallow', 'origin']


def test_becoming_shallow_is_not_worth_converting_in_place(git_calls, make_fetcher):
    # Truncating a history in place is subtle, and whoever asked for shallow wants
    # the cheap thing anyway: obtaining it again is both.
    migrated, calls = migrating(make_fetcher, git_calls, FetchMode.FULL, FetchMode.SHALLOW)

    assert migrated is None
    assert calls == []


def test_a_root_that_recorded_nothing_is_recognised_rather_than_re_cloned(
        monkeypatch, git_calls, make_fetcher):
    # Every cache populated before golem recorded a mode says nothing. Upgrading
    # must not re-clone all of them.
    monkeypatch.setattr(GitFetcher, 'detected_mode', lambda self: FetchMode.FULL)

    fetcher = make_fetcher(FetchPolicy(fetch_mode=FetchMode.FULL, reference='origin/main'))

    # What it was detected as is handed back, so the manifest can record it and
    # the next resolve has nothing left to detect.
    assert fetcher.migrate(Fetched(head=STUB_HEAD)) == \
        Fetched(head=STUB_HEAD, mode=FetchMode.FULL)
    assert git_calls == []


def test_what_a_root_looks_like_when_its_manifest_does_not_say(monkeypatch, make_fetcher):
    fetcher = make_fetcher()
    answers = {}
    monkeypatch.setattr(
        GitFetcher, 'reads_true', lambda self, args: answers.get(tuple(args), False))

    assert fetcher.detected_mode() == FetchMode.FULL

    answers[('config', '--get', 'remote.origin.promisor')] = True
    assert fetcher.detected_mode() == FetchMode.BLOBLESS

    answers[('rev-parse', '--is-shallow-repository')] = True
    assert fetcher.detected_mode() == FetchMode.SHALLOW


# -- a refresh that would do nothing ----------------------------------------


def pinned(reference='cafebabe'):
    return FetchPolicy(reference=reference, fetch_remote=False)


def test_a_pinned_root_already_on_its_commit_is_left_alone(monkeypatch, git_calls, make_fetcher):
    # Nothing is consulted, so nothing can have moved. Dependencies refresh on
    # every configure, which makes this the common path rather than a rare one.
    monkeypatch.setattr(GitFetcher, 'is_at', lambda self, reference: True)
    monkeypatch.setattr(GitFetcher, 'is_dirty', lambda self: False)

    assert make_fetcher(pinned()).refresh().head == STUB_HEAD
    assert git_calls == []


def test_a_pinned_root_that_drifted_is_refreshed(monkeypatch, git_calls, make_fetcher):
    monkeypatch.setattr(GitFetcher, 'is_at', lambda self, reference: False)
    monkeypatch.setattr(GitFetcher, 'is_dirty', lambda self: False)

    make_fetcher(pinned()).refresh()

    assert ['reset', '--hard', 'cafebabe'] in git_calls


def test_a_dirty_root_is_refreshed_even_on_its_commit(monkeypatch, git_calls, make_fetcher):
    # `status --porcelain` answers for the submodules too: untracked content in
    # one, a modified file, a moved HEAD all count as dirty here.
    monkeypatch.setattr(GitFetcher, 'is_at', lambda self, reference: True)
    monkeypatch.setattr(GitFetcher, 'is_dirty', lambda self: True)

    make_fetcher(pinned()).refresh()

    assert ['clean', '-ffxd'] in git_calls


def test_a_root_that_consults_its_remote_is_always_refreshed(monkeypatch, git_calls, make_fetcher):
    # It may have moved since it was last looked at, and only the fetch can say.
    monkeypatch.setattr(GitFetcher, 'is_at', lambda self, reference: True)
    monkeypatch.setattr(GitFetcher, 'is_dirty', lambda self: False)

    make_fetcher().refresh()

    assert ['fetch', '--prune', '--prune-tags', '--tags', 'origin'] in git_calls


def test_what_cannot_be_read_is_not_taken_for_clean(monkeypatch, make_fetcher):
    monkeypatch.setattr(
        helpers, 'check_git_output',
        lambda args, cwd=None, **kwargs: (_ for _ in ()).throw(RuntimeError('no repo')))

    assert make_fetcher().is_dirty() is True
    assert make_fetcher().is_at('cafebabe') is False


# -- submodules fetched at once ---------------------------------------------


def test_submodules_are_fetched_in_parallel_when_asked(git_calls, make_fetcher):
    make_fetcher(FetchPolicy(reference='origin/main', fetch_jobs=4)).populate()

    assert git_calls[-1] == [
        'submodule', 'update', '--init', '--recursive', '--filter=blob:none',
        '--jobs', '4',
    ]


def test_one_job_is_left_unsaid(git_calls, make_fetcher):
    make_fetcher(FetchPolicy(reference='origin/main', fetch_jobs=1)).populate()

    assert '--jobs' not in git_calls[-1]
