import pytest

from golemcpp.golem import helpers
from golemcpp.golem.fetch_policy import FetchMode
from golemcpp.golem.fetch_policy import FetchPolicy
from golemcpp.golem.fetched import Fetched
from golemcpp.golem.git_fetcher import GitFetcher
from golemcpp.golem.resolved_version import ResolvedVersion
from golemcpp.golem.source import Source
from support import stub_git_probes
from support import STUB_HEAD


@pytest.fixture
def git_calls(monkeypatch):
    """Every git invocation the fetcher makes, in order."""
    calls = []
    monkeypatch.setattr(
        helpers, "run_git", lambda args, cwd=None, quiet=False: calls.append(args)
    )
    stub_git_probes(monkeypatch)
    return calls


@pytest.fixture
def quiet_calls(monkeypatch):
    """Every git invocation with what it asked of stdout."""
    calls = []
    monkeypatch.setattr(
        helpers,
        "run_git",
        lambda args, cwd=None, quiet=False: calls.append((args, quiet)),
    )
    stub_git_probes(monkeypatch)
    return calls


# Where the fetcher of the running test works. Kept here rather than passed to
# make_fetcher, so writing a test stays a matter of asking for a fetcher.
_root = None


@pytest.fixture(autouse=True)
def fetch_root(tmp_path):
    """
    A root the test owns, one per test: populate() creates the directory it works
    in, and a hard-coded one would be a real directory outside the run.
    """
    global _root
    _root = str(tmp_path / "r")


# What resolution settles on and hands to the policy: a commit, never a name.
REVISION = "4c83605c369b88eea65e63b90a08c382138ae68d"


def make_fetcher(policy=None, revision=REVISION):
    return GitFetcher(
        _root,
        Source.for_repository(
            "https://host/r.git", ResolvedVersion(reference=revision, revision=revision)
        ),
        policy if policy is not None else FetchPolicy(revision=revision),
    )


# -- the git sequence a policy produces -------------------------------------


def test_the_default_policy_clones_and_tracks_the_branch(git_calls):
    make_fetcher().populate()

    assert git_calls == [
        ["clone", "--filter=blob:none", "--", "https://host/r.git", "."],
        ["reset", "--hard", REVISION],
        ["submodule", "update", "--init", "--recursive", "--filter=blob:none"],
    ]


def test_the_default_policy_refreshes_by_fetching_the_branch(git_calls):
    make_fetcher().refresh()

    assert git_calls == [
        ["clean", "-ffxd"],
        ["submodule", "foreach", "--recursive", "git", "clean", "-ffxd"],
        ["fetch", "--prune", "--prune-tags", "--tags", "origin"],
        ["reset", "--hard", REVISION],
        ["submodule", "foreach", "--recursive", "git", "reset", "--hard"],
        ["submodule", "sync", "--recursive"],
        ["submodule", "update", "--init", "--recursive", "--filter=blob:none"],
    ]


def test_a_clone_lands_on_its_revision_through_the_reset(git_calls):
    # The clone materializes the tree once: the reset is what lands it on the
    # revision, which under a partial clone is one round trip for the content
    # rather than two.
    make_fetcher(FetchPolicy(revision="cafebabe")).populate()

    assert git_calls == [
        ["clone", "--filter=blob:none", "--", "https://host/r.git", "."],
        ["reset", "--hard", "cafebabe"],
        ["submodule", "update", "--init", "--recursive", "--filter=blob:none"],
    ]


def test_a_shallow_policy_fetches_only_the_requested_commit(git_calls):
    make_fetcher(
        FetchPolicy(fetch_mode=FetchMode.SHALLOW, revision="cafebabe")
    ).populate()

    assert git_calls == [
        ["init"],
        ["remote", "add", "origin", "https://host/r.git"],
        ["fetch", "--depth=1", "origin", "cafebabe"],
        ["reset", "--hard", "FETCH_HEAD"],
        ["submodule", "update", "--init", "--recursive", "--depth=1"],
    ]


def test_a_shallow_refresh_asks_for_what_the_clone_asked_for(git_calls):
    # A root given one commit at a depth of one is refreshed the same way. Asking
    # for every tag and every branch is history it was deliberately not given, and
    # one refresh of it would leave a root marked shallow holding what a full clone
    # holds.
    make_fetcher(
        FetchPolicy(fetch_mode=FetchMode.SHALLOW, revision="cafebabe")
    ).refresh()

    assert ["fetch", "--depth=1", "origin", "cafebabe"] in git_calls
    assert ["fetch", "--prune", "--prune-tags", "--tags", "origin"] not in git_calls
    assert not any("--tags" in args for args in git_calls)


def test_every_other_mode_refreshes_every_ref(git_calls):
    # A branch deleted upstream stops being tracked, and a tag that moved is
    # honoured rather than kept at what it used to point to.
    make_fetcher(FetchPolicy(fetch_mode=FetchMode.FULL, revision="main")).refresh()

    assert ["fetch", "--prune", "--prune-tags", "--tags", "origin"] in git_calls


def test_a_blobless_refresh_says_nothing_about_its_filter(git_calls):
    # It is recorded in the repository by the clone, so every later fetch is
    # filtered by it without being told.
    make_fetcher(FetchPolicy(fetch_mode=FetchMode.BLOBLESS, revision="main")).refresh()

    assert not any(
        "--filter=blob:none" in args for args in git_calls if args[0] == "fetch"
    )


def test_a_pinned_policy_discards_local_changes_without_fetching(git_calls):
    # Every resource is cleaned and carries its submodules; a pin only says that
    # a refresh has nothing to fetch and lands back on the commit it holds. That
    # goes for the submodules too: --no-fetch is what keeps the whole refresh off
    # the network, so it stays allowed outside a resolve.
    make_fetcher(FetchPolicy(revision="", fetch_remote=False)).refresh()

    assert git_calls == [
        ["clean", "-ffxd"],
        ["submodule", "foreach", "--recursive", "git", "clean", "-ffxd"],
        ["reset", "--hard"],
        ["submodule", "foreach", "--recursive", "git", "reset", "--hard"],
        ["submodule", "sync", "--recursive"],
        [
            "submodule",
            "update",
            "--init",
            "--recursive",
            "--filter=blob:none",
            "--no-fetch",
        ],
    ]
    assert not any(helpers.is_network_git_command(args) for args in git_calls)


def test_a_resource_without_submodules_runs_no_submodule_command(
    monkeypatch, git_calls
):
    # Most resources declare none, and a submodule command in a repository without
    # them is a process spent to do nothing.
    stub_git_probes(monkeypatch, has_submodules=False)

    make_fetcher().populate()
    make_fetcher().refresh()

    assert not any(args[0] == "submodule" for args in git_calls)


# -- the revision has to be there before anything resets to it -------------


def stub_a_revision_this_root_does_not_hold(monkeypatch):
    """A root answering for no tag, no branch, and not the commit either."""
    monkeypatch.setattr(
        helpers,
        "try_git",
        # Everything else is housekeeping, where nothing is made of the answer.
        lambda params, cwd=None, **kwargs: params[:3]
        != ["rev-parse", "--verify", "--quiet"],
    )


def stub_a_revision_only_a_fetch_answers_for(monkeypatch):
    """A root holding no ref for the revision, and only what a fetch just wrote."""
    monkeypatch.setattr(
        helpers,
        "try_git",
        lambda params, cwd=None, **kwargs: params[:3]
        != ["rev-parse", "--verify", "--quiet"]
        or params[3].startswith("FETCH_HEAD"),
    )


@pytest.mark.parametrize("mode", [FetchMode.BLOBLESS, FetchMode.FULL])
def test_a_revision_no_branch_or_tag_reaches_is_refused(monkeypatch, git_calls, mode):
    # A clone and a pruning fetch bring every branch and every tag with all their
    # ancestors, so a commit missing from one of these roots is one nothing
    # advertises. Asking for it by name would take a server willing to serve an
    # object it advertises to nobody, and what came back could be on its way out of
    # that remote's next collection -- so nothing is asked, and nothing is advised.
    stub_a_revision_this_root_does_not_hold(monkeypatch)

    with pytest.raises(RuntimeError, match="advertises no branch or tag"):
        make_fetcher(
            FetchPolicy(fetch_mode=mode, revision="cafebabe", fetch_remote=False)
        ).refresh()

    assert not any(helpers.is_network_git_command(args) for args in git_calls)


def test_a_shallow_root_reaches_a_commit_nothing_advertises(monkeypatch, git_calls):
    # Asking by name is how a shallow root asks for anything at all, so it lands on a
    # commit no branch and no tag reaches where the other modes refuse. A consequence
    # of the mechanism, not a capability: naming such a commit is unsupported, and
    # this pins the asymmetry so it stays deliberate rather than becoming a promise.
    stub_a_revision_only_a_fetch_answers_for(monkeypatch)

    make_fetcher(
        FetchPolicy(fetch_mode=FetchMode.SHALLOW, revision="cafebabe")
    ).populate()

    assert git_calls.index(
        ["fetch", "--depth=1", "origin", "cafebabe"]
    ) < git_calls.index(["reset", "--hard", "FETCH_HEAD"])


def test_a_present_revision_is_reset_to_without_asking_for_it(git_calls):
    make_fetcher(FetchPolicy(revision="cafebabe", fetch_remote=False)).refresh()

    assert ["fetch", "origin", "cafebabe"] not in git_calls


# -- what a revision turns out to name -------------------------------------


def reset_onto(git_calls):
    """What the reset landed on."""
    return next(args[2] for args in git_calls if args[:2] == ["reset", "--hard"])


def test_the_revision_is_used_as_it_was_given(monkeypatch, git_calls):
    # Resolution settled which commit this is, so the fetcher interprets nothing.
    # A tag and a branch sharing the name are there to be ignored.
    stub_git_probes(monkeypatch, branches=("main",), tags=("main",))

    make_fetcher(revision=REVISION).populate()

    assert reset_onto(git_calls) == REVISION


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
        ["clone", "--filter=blob:none", "--", "https://host/r.git", "."],
        ["submodule", "update", "--init", "--recursive", "--filter=blob:none"],
        ["fetch", "--prune", "--prune-tags", "--tags", "origin"],
        ["submodule", "update", "--init", "--recursive", "--filter=blob:none"],
    ]
    assert all(
        helpers.is_network_git_command(args) for args, quiet in quiet_calls if not quiet
    )


def test_a_shallow_clone_only_speaks_while_it_fetches(quiet_calls):
    make_fetcher(
        FetchPolicy(fetch_mode=FetchMode.SHALLOW, revision="cafebabe")
    ).populate()

    assert [args for args, quiet in quiet_calls if not quiet] == [
        ["fetch", "--depth=1", "origin", "cafebabe"],
        ["submodule", "update", "--init", "--recursive", "--depth=1"],
    ]


# -- changing what a root already holds -------------------------------------


def migrating(git_calls, recorded, target):
    fetcher = make_fetcher(FetchPolicy(fetch_mode=target, revision="main"))
    return fetcher.migrate(Fetched(head=STUB_HEAD, mode=recorded)), git_calls


def test_a_root_already_in_the_asked_mode_is_left_alone(git_calls):
    migrated, calls = migrating(git_calls, FetchMode.BLOBLESS, FetchMode.BLOBLESS)

    assert migrated == Fetched(head=STUB_HEAD, mode=FetchMode.BLOBLESS)
    assert calls == []


def test_a_full_root_becomes_blobless_without_transferring_anything(git_calls):
    # The objects are already here. This only says that later fetches may leave
    # file content behind.
    migrated, calls = migrating(git_calls, FetchMode.FULL, FetchMode.BLOBLESS)

    # Converted, and still on the commit it was on: a migration changes how much
    # of a history a root holds, never where it stands in it.
    assert migrated == Fetched(head=STUB_HEAD, mode=FetchMode.BLOBLESS)
    assert calls == [
        ["config", "remote.origin.promisor", "true"],
        ["config", "remote.origin.partialclonefilter", "blob:none"],
    ]
    assert not any(helpers.is_network_git_command(args) for args in calls)


def test_a_blobless_root_becomes_full_by_asking_for_what_it_left_out(git_calls):
    migrated, calls = migrating(git_calls, FetchMode.BLOBLESS, FetchMode.FULL)

    assert migrated == Fetched(head=STUB_HEAD, mode=FetchMode.FULL)
    assert calls == [["fetch", "--refetch", "origin"]]


def test_a_shallow_root_is_deepened_before_anything_else(git_calls):
    migrated, calls = migrating(git_calls, FetchMode.SHALLOW, FetchMode.BLOBLESS)

    assert migrated == Fetched(head=STUB_HEAD, mode=FetchMode.BLOBLESS)
    assert calls[0] == ["fetch", "--unshallow", "origin"]


def test_becoming_shallow_is_not_worth_converting_in_place(git_calls):
    # Truncating a history in place is subtle, and whoever asked for shallow wants
    # the cheap thing anyway: obtaining it again is both.
    migrated, calls = migrating(git_calls, FetchMode.FULL, FetchMode.SHALLOW)

    assert migrated is None
    assert calls == []


def test_a_root_that_recorded_nothing_is_recognised_rather_than_re_cloned(
    monkeypatch, git_calls
):
    # Every cache populated before golem recorded a mode says nothing. Upgrading
    # must not re-clone all of them.
    monkeypatch.setattr(GitFetcher, "detected_mode", lambda self: FetchMode.FULL)

    fetcher = make_fetcher(FetchPolicy(fetch_mode=FetchMode.FULL, revision="main"))

    # What it was detected as is handed back, so the manifest can record it and
    # the next resolve has nothing left to detect.
    assert fetcher.migrate(Fetched(head=STUB_HEAD)) == Fetched(
        head=STUB_HEAD, mode=FetchMode.FULL
    )
    assert git_calls == []


def test_what_a_root_looks_like_when_its_manifest_does_not_say(monkeypatch):
    fetcher = make_fetcher()
    answers = {}
    monkeypatch.setattr(
        GitFetcher, "reads_true", lambda self, args: answers.get(tuple(args), False)
    )

    assert fetcher.detected_mode() == FetchMode.FULL

    answers[("config", "--get", "remote.origin.promisor")] = True
    assert fetcher.detected_mode() == FetchMode.BLOBLESS

    answers[("rev-parse", "--is-shallow-repository")] = True
    assert fetcher.detected_mode() == FetchMode.SHALLOW


# -- a refresh that would do nothing ----------------------------------------


def pinned(revision="cafebabe"):
    return FetchPolicy(revision=revision, fetch_remote=False)


def test_a_pinned_root_already_on_its_commit_is_left_alone(monkeypatch, git_calls):
    # Nothing is consulted, so nothing can have moved. This is what golem does to
    # a dependency it is about to rebuild, where the sequence costs the most for
    # the least.
    monkeypatch.setattr(GitFetcher, "is_at", lambda self, revision: True)
    monkeypatch.setattr(GitFetcher, "is_dirty", lambda self: False)

    assert make_fetcher(pinned()).refresh().head == STUB_HEAD
    assert git_calls == []


def test_a_pinned_root_that_drifted_is_refreshed(monkeypatch, git_calls):
    monkeypatch.setattr(GitFetcher, "is_at", lambda self, revision: False)
    monkeypatch.setattr(GitFetcher, "is_dirty", lambda self: False)

    make_fetcher(pinned()).refresh()

    assert ["reset", "--hard", "cafebabe"] in git_calls


def test_a_dirty_root_is_refreshed_even_on_its_commit(monkeypatch, git_calls):
    # `status --porcelain` answers for the submodules too: untracked content in
    # one, a modified file, a moved HEAD all count as dirty here.
    monkeypatch.setattr(GitFetcher, "is_at", lambda self, revision: True)
    monkeypatch.setattr(GitFetcher, "is_dirty", lambda self: True)

    make_fetcher(pinned()).refresh()

    assert ["clean", "-ffxd"] in git_calls


def test_a_root_that_consults_its_remote_is_always_refreshed(monkeypatch, git_calls):
    # It may have moved since it was last looked at, and only the fetch can say.
    monkeypatch.setattr(GitFetcher, "is_at", lambda self, revision: True)
    monkeypatch.setattr(GitFetcher, "is_dirty", lambda self: False)

    make_fetcher().refresh()

    assert ["fetch", "--prune", "--prune-tags", "--tags", "origin"] in git_calls


# -- keeping a long-lived root from growing unboundedly ---------------------


@pytest.fixture
def housekeeping(monkeypatch, git_calls):
    """What the fetcher asks git about, where nothing is made of the answer."""
    asked = []
    monkeypatch.setattr(
        helpers,
        "try_git",
        lambda params, cwd=None, **kwargs: asked.append(params) or True,
    )
    return asked


def test_a_refreshed_root_is_handed_to_git_to_keep_tidy(housekeeping):
    # A cache root is fetched into for as long as it is kept, and nothing else
    # would ever pack what those fetches leave loose. Git decides whether it is
    # due; this only asks.
    make_fetcher().refresh()

    assert ["gc", "--auto"] in housekeeping


def test_a_root_nothing_was_done_to_is_not_packed_either(monkeypatch, housekeeping):
    monkeypatch.setattr(GitFetcher, "is_at", lambda self, revision: True)
    monkeypatch.setattr(GitFetcher, "is_dirty", lambda self: False)

    make_fetcher(pinned()).refresh()

    assert ["gc", "--auto"] not in housekeeping


def test_what_cannot_be_read_is_not_taken_for_clean(monkeypatch):
    monkeypatch.setattr(
        helpers,
        "read_git",
        lambda params, cwd=None, **kwargs: (_ for _ in ()).throw(
            RuntimeError("no repo")
        ),
    )

    assert make_fetcher().is_dirty() is True
    assert make_fetcher().is_at("cafebabe") is False


# -- submodules fetched at once ---------------------------------------------


def test_submodules_are_fetched_in_parallel_when_asked(git_calls):
    make_fetcher(FetchPolicy(revision="main", fetch_jobs=4)).populate()

    assert git_calls[-1] == [
        "submodule",
        "update",
        "--init",
        "--recursive",
        "--filter=blob:none",
        "--jobs",
        "4",
    ]


def test_one_job_is_left_unsaid(git_calls):
    make_fetcher(FetchPolicy(revision="main", fetch_jobs=1)).populate()

    assert "--jobs" not in git_calls[-1]
