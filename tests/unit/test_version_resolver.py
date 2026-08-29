import pytest

from golemcpp.golem import advertisement_store
from golemcpp.golem import version_resolver
from golemcpp.golem.requested_source import RequestedSource
from golemcpp.golem.resolved_version import ResolvedVersion
from golemcpp.golem.version_resolver import VersionResolver


def test_find_version_matches_semver_spec():
    assert (
        VersionResolver.find_version(["1.2.2", "1.2.3", "1.2.4"], "~1.2.0") == "1.2.4"
    )


def test_find_version_accepts_major_only_tags_in_version_list():
    assert VersionResolver.find_version(["1", "1.2", "2.0.0"], "1") == "1.2"


def test_find_version_accepts_major_minor_tags_in_version_list():
    assert VersionResolver.find_version(["1.2", "1.2.9", "1.3"], "1.2") == "1.2.9"


def test_find_version_preserves_existing_full_semver_behavior():
    assert VersionResolver.find_version(["1.2.2", "1.2.3", "1.2.4"], "1.2.3") == "1.2.3"


def test_find_version_accepts_major_only_tag_with_full_semver_query():
    assert VersionResolver.find_version(["1", "2"], "^1.0.0") == "1"


def test_find_version_accepts_openssl_style_suffix_tags():
    assert (
        VersionResolver.find_version(["OpenSSL_1_1_1i", "OpenSSL_1_1_1j"], "~1.1.1")
        == "OpenSSL_1_1_1j"
    )


def test_find_version_accepts_v_prefixed_major_tag():
    assert VersionResolver.find_version(["v1", "v2"], "1") == "v1"


def test_find_version_accepts_v_prefixed_major_minor_tag():
    assert VersionResolver.find_version(["v5.1", "v5.2"], "5.2") == "v5.2"


def test_find_version_accepts_boost_style_prerelease_suffix_tag():
    assert (
        VersionResolver.find_version(
            ["boost-1.91.0-1", "boost-1.90.0"], ">=1.91.0-0 <1.92.0"
        )
        == "boost-1.91.0-1"
    )


def test_find_version_accepts_prefixed_short_underscore_tag():
    assert VersionResolver.find_version(["foo_1_1", "foo_1_2"], "1.2") == "foo_1_2"


# -- one call, and every selection made from what it answered ---------------


def advertise(monkeypatch, listing, calls=None):
    """
    The one call a resolution makes, answered with what a remote publishes.

    Anything else reaching git is a second round trip, which is what this stage
    removed, so it fails the test rather than being quietly answered.
    """

    def fake_git(args, cwd):
        if calls is not None:
            calls.append(args)
        assert args[0] == "ls-remote", "asked the remote something else: {}".format(
            args
        )
        return listing

    monkeypatch.setattr(version_resolver.helpers, "read_git", fake_git)


MAIN = "ref: refs/heads/main\tHEAD\nabc123\tHEAD\nabc123\trefs/heads/main\n"


def test_resolve_matches_tag_and_returns_hash(monkeypatch):
    advertise(
        monkeypatch,
        MAIN
        + "deadbeef\trefs/tags/v3.11.0\n"
        + "cafebabecafebabe\trefs/tags/v3.12.0\n",
    )

    resolved = VersionResolver.resolve(
        RequestedSource.for_repository("https://github.com/nlohmann/json.git", "^3.0.0")
    )
    assert resolved.reference == "v3.12.0"
    assert resolved.revision == "cafebabecafebabe"


def test_resolve_reads_a_branch_head(monkeypatch):
    advertise(monkeypatch, MAIN)

    resolved = VersionResolver.resolve(
        RequestedSource.for_repository("https://example.com/x.git", "main")
    )
    assert resolved.reference == "main"
    assert resolved.revision == "abc123"


def test_a_ref_the_remote_has_is_taken_verbatim(monkeypatch):
    # The bug this fixes: `v1.2.0` and `v1_2_0` normalize to the same semver, so
    # matching could answer either question with the other tag.
    advertise(
        monkeypatch,
        MAIN
        + "cafebabecafebabe\trefs/tags/v1.2.0\n"
        + "deadbeefdeadbeef\trefs/tags/v1_2_0\n",
    )

    assert VersionResolver.resolve(
        RequestedSource.for_repository("https://host/r.git", "v1.2.0")
    ) == ResolvedVersion(reference="v1.2.0", revision="cafebabecafebabe")


@pytest.mark.parametrize(
    "version",
    [
        "",
        "HEAD",
        "main",
        "v1.2.0",
        "^1.0.0",
        "65ee68451d8eb2b5f3a30b410476ab83deb3289b",
    ],
)
def test_every_version_costs_one_round_trip(monkeypatch, version):
    # The point of the stage: whatever is asked for, the remote is asked once and
    # everything after that is decided from its answer.
    calls = []
    advertise(monkeypatch, MAIN + "cafebabe\trefs/tags/v1.2.0\n", calls=calls)

    VersionResolver.resolve(
        RequestedSource.for_repository("https://host/r.git", version)
    )

    assert len(calls) == 1


def test_a_spec_the_remote_does_not_have_falls_back_to_matching(monkeypatch):
    # `1.2.3` against a repository that tags `v1.2.3`: no such ref, so the spec
    # is matched as a range, which is what it took before this.
    advertise(monkeypatch, MAIN + "cafebabecafebabe\trefs/tags/v1.2.3\n")

    assert VersionResolver.resolve(
        RequestedSource.for_repository("https://host/r.git", "1.2.3")
    ) == ResolvedVersion(reference="v1.2.3", revision="cafebabecafebabe")


def test_an_ambiguous_name_resolves_the_way_git_does(monkeypatch):
    # `git rev-parse v1.2.0` answers the tag, warning that the name is ambiguous:
    # `gitrevisions` looks in refs/tags/ before refs/heads/. Golem used to answer
    # the branch, because that is the order ls-remote happens to print them in.
    advertise(
        monkeypatch,
        MAIN + "b2a4c400\trefs/heads/v1.2.0\n" + "ta61e5000\trefs/tags/v1.2.0\n",
    )

    assert VersionResolver.resolve(
        RequestedSource.for_repository("https://host/r.git", "v1.2.0")
    ) == ResolvedVersion(reference="v1.2.0", revision="ta61e5000")


# -- annotated tags ---------------------------------------------------------


ANNOTATED = MAIN + "0bjec7ff\trefs/tags/v2.0.0\n" + "c0mm17ff\trefs/tags/v2.0.0^{}\n"


def test_an_annotated_tag_resolves_to_the_commit_a_checkout_lands_on(monkeypatch):
    # Not the tag object: `git checkout v2.0.0` leaves HEAD at the commit, and a
    # revision is what HEAD holds.
    advertise(monkeypatch, ANNOTATED)

    assert VersionResolver.resolve(
        RequestedSource.for_repository("https://host/r.git", "v2.0.0")
    ) == ResolvedVersion(reference="v2.0.0", revision="c0mm17ff")


def test_an_annotated_tag_is_still_matched_as_a_range(monkeypatch):
    advertise(monkeypatch, ANNOTATED)

    assert VersionResolver.resolve(
        RequestedSource.for_repository("https://host/r.git", "^2.0.0")
    ) == ResolvedVersion(reference="v2.0.0", revision="c0mm17ff")


def test_nothing_matched_leaves_the_spec_standing_for_itself(monkeypatch):
    # Which is what a commit hash does.
    monkeypatch.setattr(version_resolver.helpers, "read_git", lambda args, cwd: "")

    assert VersionResolver.resolve(
        RequestedSource.for_repository("https://host/r.git", "65ee6845")
    ) == ResolvedVersion(reference="65ee6845", revision="65ee6845")


def test_a_resolution_naming_only_a_reference_is_not_resolved_for_a_commit(monkeypatch):
    # A kind keyed on the commit needs the revision, so a resolution carrying
    # only a reference is unfinished and goes back to the remote. Every other
    # kind is keyed on what it asked for, so the same value is answer enough.
    requested = RequestedSource.for_repository(
        "https://host/json.git", version="v3.12.0"
    )
    half = ResolvedVersion(reference="v3.12.0")
    whole = ResolvedVersion(reference="v3.12.0", revision="65ee6845")
    monkeypatch.setattr(VersionResolver, "resolve", staticmethod(lambda _: whole))

    assert VersionResolver.resolve_requested(requested, half) is half
    assert (
        VersionResolver.resolve_requested(requested, half, require_revision=True)
        is whole
    )


def test_a_resolution_naming_a_commit_is_answer_enough_either_way(monkeypatch):
    requested = RequestedSource.for_repository(
        "https://host/json.git", version="v3.12.0"
    )
    resolved = ResolvedVersion(reference="v3.12.0", revision="65ee6845")
    monkeypatch.setattr(
        VersionResolver,
        "resolve",
        staticmethod(lambda _: pytest.fail("the remote must not be reached")),
    )

    assert VersionResolver.resolve_requested(requested, resolved) is resolved
    assert (
        VersionResolver.resolve_requested(requested, resolved, require_revision=True)
        is resolved
    )


@pytest.mark.parametrize("version", ["^99.0.0", "develp"])
def test_a_version_nothing_answers_is_refused(monkeypatch, version):
    # Raised while the version asked for is still at hand, rather than handed to
    # git as a revision it cannot resolve either.
    monkeypatch.setattr(version_resolver.helpers, "read_git", lambda args, cwd: "")

    with pytest.raises(RuntimeError) as error:
        VersionResolver.resolve(
            RequestedSource.for_repository("https://host/r.git", version)
        )

    assert "answers version '{}'".format(version) in str(error.value)
    assert "https://host/r.git" in str(error.value)


def test_a_tag_that_reads_as_a_range_is_still_found(monkeypatch):
    # `v1.x.0` is a real tag that semver reads as a range, and matching it as one
    # answers v1.2.0. Looking it up as a name first is what keeps them apart.
    advertise(
        monkeypatch,
        MAIN + "cafebabe\trefs/tags/v1.2.0\n" + "cafebabecafebabe\trefs/tags/v1.x.0\n",
    )

    assert VersionResolver.find_version(["v1.2.0", "v1.x.0"], "v1.x.0") == "v1.2.0"
    assert VersionResolver.resolve(
        RequestedSource.for_repository("https://host/r.git", "v1.x.0")
    ) == ResolvedVersion(reference="v1.x.0", revision="cafebabecafebabe")


@pytest.mark.parametrize("version", ["", "HEAD"])
def test_no_version_and_HEAD_both_name_the_default_branch(monkeypatch, version):
    # --symref answers with the branch and its commit at once, so the reference
    # records `master` rather than the HEAD that was asked for.
    def fake_git(args, cwd):
        if "--symref" in args:
            return "ref: refs/heads/master\tHEAD\n831b49bc\tHEAD\n"
        raise AssertionError("asked the remote something else: {}".format(args))

    monkeypatch.setattr(version_resolver.helpers, "read_git", fake_git)

    assert VersionResolver.resolve(
        RequestedSource.for_repository("https://host/r.git", version)
    ) == ResolvedVersion(reference="master", revision="831b49bc")


@pytest.mark.parametrize("version", ["", "HEAD"])
def test_a_remote_advertising_no_head_is_refused(monkeypatch, version):
    # An empty repository advertises nothing at all, not even a symref, so there
    # is no default branch to fall back on.
    monkeypatch.setattr(version_resolver.helpers, "read_git", lambda args, cwd: "")

    with pytest.raises(RuntimeError) as error:
        VersionResolver.resolve(
            RequestedSource.for_repository("https://host/r.git", version)
        )

    assert "answers version '{}'".format(version) in str(error.value)


# -- one remote read once for a whole resolve -------------------------------


def test_a_remote_is_read_once_for_a_resolve(monkeypatch, tmp_path):
    # What stage 3 exists for: a repository two dependencies both need is asked
    # by the first of them and read from the store by the second.
    calls = []
    advertise(monkeypatch, MAIN + "cafebabe\trefs/tags/v1.2.0\n", calls=calls)
    requested = RequestedSource.for_repository("https://host/r.git", "v1.2.0")

    with advertisement_store.shared(str(tmp_path / "resolve")):
        first = VersionResolver.resolve(requested)
        second = VersionResolver.resolve(requested)

    assert first == second
    assert len(calls) == 1


def test_each_remote_is_read_once(monkeypatch, tmp_path):
    calls = []
    advertise(monkeypatch, MAIN, calls=calls)

    with advertisement_store.shared(str(tmp_path / "resolve")):
        for url in (
            "https://host/one.git",
            "https://host/two.git",
            "https://host/one.git",
        ):
            VersionResolver.resolve(RequestedSource.for_repository(url, "main"))

    assert len(calls) == 2


def test_a_remote_that_could_not_be_reached_is_asked_again(monkeypatch, tmp_path):
    # A refused connection is routine, which is why read_git retries one. Keeping
    # a failure would make it fail every resolution after it instead.
    calls = []

    def fake_git(args, cwd):
        calls.append(args)
        if len(calls) == 1:
            raise RuntimeError("Could not read from remote repository")
        return MAIN

    monkeypatch.setattr(version_resolver.helpers, "read_git", fake_git)
    requested = RequestedSource.for_repository("https://host/r.git", "main")

    with advertisement_store.shared(str(tmp_path / "resolve")):
        with pytest.raises(RuntimeError):
            VersionResolver.resolve(requested)

        assert VersionResolver.resolve(requested).revision == "abc123"

    assert len(calls) == 2
