import pytest

from golemcpp.golem import version_resolver
from golemcpp.golem.requested_source import RequestedSource
from golemcpp.golem.resolved_version import ResolvedVersion
from golemcpp.golem.version_resolver import VersionResolver


def test_find_version_matches_semver_spec():
    assert VersionResolver.find_version(['1.2.2', '1.2.3', '1.2.4'], '~1.2.0') == '1.2.4'


def test_find_version_accepts_major_only_tags_in_version_list():
    assert VersionResolver.find_version(['1', '1.2', '2.0.0'], '1') == '1.2'


def test_find_version_accepts_major_minor_tags_in_version_list():
    assert VersionResolver.find_version(['1.2', '1.2.9', '1.3'], '1.2') == '1.2.9'


def test_find_version_preserves_existing_full_semver_behavior():
    assert VersionResolver.find_version(['1.2.2', '1.2.3', '1.2.4'], '1.2.3') == '1.2.3'


def test_find_version_accepts_major_only_tag_with_full_semver_query():
    assert VersionResolver.find_version(['1', '2'], '^1.0.0') == '1'


def test_find_version_accepts_openssl_style_suffix_tags():
    assert VersionResolver.find_version(
        ['OpenSSL_1_1_1i', 'OpenSSL_1_1_1j'], '~1.1.1') == 'OpenSSL_1_1_1j'


def test_find_version_accepts_v_prefixed_major_tag():
    assert VersionResolver.find_version(['v1', 'v2'], '1') == 'v1'


def test_find_version_accepts_v_prefixed_major_minor_tag():
    assert VersionResolver.find_version(['v5.1', 'v5.2'], '5.2') == 'v5.2'


def test_find_version_accepts_boost_style_prerelease_suffix_tag():
    assert VersionResolver.find_version(
        ['boost-1.91.0-1', 'boost-1.90.0'], '>=1.91.0-0 <1.92.0') == 'boost-1.91.0-1'


def test_find_version_accepts_prefixed_short_underscore_tag():
    assert VersionResolver.find_version(['foo_1_1', 'foo_1_2'], '1.2') == 'foo_1_2'


def test_resolve_matches_tag_and_returns_hash(monkeypatch):
    def fake_git(args, cwd):
        if args[-1] == 'refs/tags/v3.12.0':
            return 'cafebabecafebabe\trefs/tags/v3.12.0\n'
        if '--tags' in args:
            return 'deadbeef\trefs/tags/v3.11.0\ncafebabe\trefs/tags/v3.12.0\n'
        return ''

    monkeypatch.setattr(version_resolver.helpers, 'read_git', fake_git)

    resolved = VersionResolver.resolve(
        RequestedSource.for_repository('https://github.com/nlohmann/json.git', '^3.0.0'))
    assert resolved.reference == 'v3.12.0'
    assert resolved.revision == 'cafebabecafebabe'


def test_resolve_reads_a_branch_head(monkeypatch):
    def fake_git(args, cwd):
        return 'abc123\trefs/heads/main\n' if args[-1] == 'main' else ''

    monkeypatch.setattr(version_resolver.helpers, 'read_git', fake_git)

    resolved = VersionResolver.resolve(
        RequestedSource.for_repository('https://example.com/x.git', 'main'))
    assert resolved.reference == 'main'
    assert resolved.revision == 'abc123'


# -- what has to be asked of a remote, and what does not --------------------


def test_a_spec_naming_one_ref_is_not_a_range():
    # A branch, a tag, a sha. And an exact version, which semver would accept as
    # a range and which is just as good a tag name -- read as the tag it looks
    # like, so `#1.2.3` keeps meaning what it says.
    for version in ('main', 'develop', 'release/1.2', 'v1.2.0', '1.2.3',
                    '65ee68451d8eb2b5f3a30b410476ab83deb3289b', ''):
        assert not VersionResolver.is_range(version), version


def test_a_spec_carrying_an_operator_is_a_range():
    for version in ('^1.2.0', '~1.2', '>=1.0.0', '<2', '=1.2.3', '1.x', '1.2.X',
                    'x', '*', '1.2.0 - 1.3.0', '1.2 || 1.3'):
        assert VersionResolver.is_range(version), version


def test_a_wildcard_is_read_as_a_whole_segment():
    # Otherwise every ref name holding an `x` would look like a range.
    assert not VersionResolver.is_range('release/x86')
    assert not VersionResolver.is_range('linux')


def test_a_ref_the_remote_has_is_taken_verbatim(monkeypatch):
    # The bug this fixes: `v1.2.0` and `v1_2_0` normalize to the same semver, so
    # matching could answer either question with the other tag.
    calls = []

    def fake_git(args, cwd):
        calls.append(args)
        if args[-1] == 'v1.2.0':
            return 'cafebabecafebabe\trefs/tags/v1.2.0\n'
        raise AssertionError('asked the remote something else: {}'.format(args))

    monkeypatch.setattr(version_resolver.helpers, 'read_git', fake_git)

    assert VersionResolver.resolve(
        RequestedSource.for_repository('https://host/r.git', 'v1.2.0')) == \
        ResolvedVersion(reference='v1.2.0', revision='cafebabecafebabe')
    # One round trip, and no tag listing to match against.
    assert len(calls) == 1


def test_a_branch_costs_one_round_trip(monkeypatch):
    def fake_git(args, cwd):
        return 'abc123\trefs/heads/main\n' if args[-1] == 'main' else ''

    monkeypatch.setattr(version_resolver.helpers, 'read_git', fake_git)

    assert VersionResolver.resolve(
        RequestedSource.for_repository('https://example.com/x.git', 'main')) == \
        ResolvedVersion(reference='main', revision='abc123')


def test_a_spec_the_remote_does_not_have_falls_back_to_matching(monkeypatch):
    # `1.2.3` against a repository that tags `v1.2.3`: no such ref, so the spec
    # is matched as a range, which is what it took before this.
    def fake_git(args, cwd):
        if args[-1] == '1.2.3':
            return ''
        if args[-1] == 'refs/tags/v1.2.3':
            return 'cafebabecafebabe\trefs/tags/v1.2.3\n'
        if '--tags' in args:
            return 'cafebabe\trefs/tags/v1.2.3\n'
        return ''

    monkeypatch.setattr(version_resolver.helpers, 'read_git', fake_git)

    assert VersionResolver.resolve(
        RequestedSource.for_repository('https://host/r.git', '1.2.3')) == \
        ResolvedVersion(reference='v1.2.3', revision='cafebabecafebabe')


def test_a_range_is_matched_and_never_asked_for_as_a_ref(monkeypatch):
    calls = []

    def fake_git(args, cwd):
        calls.append(args)
        if args[-1] == 'refs/tags/v3.12.0':
            return 'cafebabecafebabe\trefs/tags/v3.12.0\n'
        if '--tags' in args:
            return 'cafebabe\trefs/tags/v3.12.0\n'
        return ''

    monkeypatch.setattr(version_resolver.helpers, 'read_git', fake_git)

    assert VersionResolver.resolve(
        RequestedSource.for_repository('https://host/r.git', '^3.0.0')) == \
        ResolvedVersion(reference='v3.12.0', revision='cafebabecafebabe')
    assert not any(args[-1] == '^3.0.0' for args in calls)


def test_nothing_matched_leaves_the_spec_standing_for_itself(monkeypatch):
    # Which is what a commit hash does.
    monkeypatch.setattr(
        version_resolver.helpers, 'read_git', lambda args, cwd: '')

    assert VersionResolver.resolve(
        RequestedSource.for_repository('https://host/r.git', '65ee6845')) == \
        ResolvedVersion(reference='65ee6845', revision='65ee6845')


def test_a_resolution_naming_only_a_reference_is_not_resolved_for_a_commit(monkeypatch):
    # A kind keyed on the commit needs the revision, so a resolution carrying
    # only a reference is unfinished and goes back to the remote. Every other
    # kind is keyed on what it asked for, so the same value is answer enough.
    requested = RequestedSource.for_repository('https://host/json.git',
                                               version='v3.12.0')
    half = ResolvedVersion(reference='v3.12.0')
    whole = ResolvedVersion(reference='v3.12.0', revision='65ee6845')
    monkeypatch.setattr(VersionResolver, 'resolve', staticmethod(lambda _: whole))

    assert VersionResolver.resolve_requested(requested, half) is half
    assert VersionResolver.resolve_requested(
        requested, half, require_revision=True) is whole


def test_a_resolution_naming_a_commit_is_answer_enough_either_way(monkeypatch):
    requested = RequestedSource.for_repository('https://host/json.git',
                                               version='v3.12.0')
    resolved = ResolvedVersion(reference='v3.12.0', revision='65ee6845')
    monkeypatch.setattr(VersionResolver, 'resolve', staticmethod(
        lambda _: pytest.fail('the remote must not be reached')))

    assert VersionResolver.resolve_requested(requested, resolved) is resolved
    assert VersionResolver.resolve_requested(
        requested, resolved, require_revision=True) is resolved


def test_a_range_matching_no_tag_is_refused(monkeypatch):
    # A ref the remote does not have is carried forward for git to fail on, but
    # git cannot resolve a semver range at all, so nothing downstream could.
    monkeypatch.setattr(
        version_resolver.helpers, 'read_git', lambda args, cwd: '')

    with pytest.raises(RuntimeError) as error:
        VersionResolver.resolve(
            RequestedSource.for_repository('https://host/r.git', '^99.0.0'))

    assert "matches version range '^99.0.0'" in str(error.value)
    assert 'https://host/r.git' in str(error.value)


def test_asking_for_a_commit_and_getting_none_is_refused(monkeypatch):
    # A repository with no tags, asked for no version: nothing names a commit,
    # and a kind keyed on one cannot name a root without it.
    monkeypatch.setattr(
        version_resolver.helpers, 'read_git', lambda args, cwd: '')
    requested = RequestedSource.for_repository('https://host/r.git', version='')

    assert VersionResolver.resolve_requested(
        requested, ResolvedVersion()) == ResolvedVersion()

    with pytest.raises(RuntimeError) as error:
        VersionResolver.resolve_requested(
            requested, ResolvedVersion(), require_revision=True)

    assert "no commit of 'https://host/r.git'" in str(error.value)
